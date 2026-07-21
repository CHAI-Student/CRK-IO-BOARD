"""주기적 데이터 수집 polling 서비스.

DataSource를 지정된 interval로 polling해 구독자(StreamQueue)들에게
broadcast한다. 구독자가 없으면 polling을 멈추고 대기해 serial 트래픽과
CPU를 아낀다 (구독자 기반 on-demand polling).
"""

import asyncio
import logging

from .data_sources import DataSource
from .stream_queues import StreamQueue

logger = logging.getLogger(__name__)

class PollingService:
    """DataSource를 주기적으로 polling해 구독 queue에 broadcast하는 서비스."""

    def __init__(self, data_source: DataSource, interval: float = 1.0, name: str = ""):
        self.data_source: DataSource = data_source
        self.subscribers: set[StreamQueue] = set()
        self.interval: float = interval
        self.name: str = name

        # polling 루프를 제어하는 event.
        # Unset(False) = polling 중지, Set(True) = polling 수행.
        self._has_subscribers = asyncio.Event()

        self._polling_task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self):
        """백그라운드 서비스를 시작한다 (구독자 없으면 Idle)."""
        self._running = True
        self._polling_task = asyncio.create_task(self._loop())
        logger.info(f"Service [{self.name}]: Started (Idle)")

    async def stop(self):
        """서비스를 gracefully 정지한다."""
        self._running = False
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Service [{self.name}]: Stopped")

    async def subscribe(self, queue: StreamQueue):
        """구독자 queue를 등록한다."""
        self.subscribers.add(queue)
        logger.info(f"Service [{self.name}]: Subscriber added. Total: {len(self.subscribers)}")

        # 첫 구독자면 polling 루프를 깨운다
        if len(self.subscribers) == 1:
            self._has_subscribers.set()
            logger.info(f"Service [{self.name}]: >>> Polling RESUMED <<<")

    async def unsubscribe(self, queue: StreamQueue):
        """구독자 queue를 해제한다."""
        if queue in self.subscribers:
            self.subscribers.remove(queue)
            logger.info(f"Service [{self.name}]: Subscriber removed. Total: {len(self.subscribers)}")

            # 구독자가 없으면 polling 루프를 멈춘다
            if len(self.subscribers) == 0:
                self._has_subscribers.clear()
                logger.info(f"Service [{self.name}]: >>> Polling PAUSED <<<")

    async def _loop(self):
        """백그라운드 polling 루프."""
        while self._running:
            # 1. WAIT: set()이 호출될 때까지 무기한 대기.
            # 대기 중에는 CPU를 소비하지 않는다.
            await self._has_subscribers.wait()

            # 2. POLL: 데이터 조회
            try:
                timestamp = asyncio.get_event_loop().time()

                data = await self.data_source.fetch()
                logger.debug(f"Service [{self.name}]: Polled Data [{data}]")

                # 3. BROADCAST: 모든 활성 queue에 전송.
                # 순회 중 구독 해제될 수 있으므로 list() 복사본을 순회한다.
                for q in list(self.subscribers):
                    await q.put(data)

                # 4. INTERVAL: fetch 소요 시간을 제외하고 다음 poll까지 대기.
                # fetch가 interval보다 오래 걸려도 음수 sleep이 되지 않게 한다.
                await asyncio.sleep(
                    max(0.0, self.interval - (asyncio.get_event_loop().time() - timestamp))
                )

            except Exception as e:
                logger.error(f"Service [{self.name}]: Error in loop: {e}")
                await asyncio.sleep(self.interval)  # 에러 시 backoff