"""loadcell 데이터 recording 서비스.

PollingService를 구독해 수신한 frame을 timestamp와 함께 메모리에
축적한다. /recording API를 통해 시작/정지/조회된다.
"""

import asyncio
import logging
from typing import Any

from pydantic import BaseModel

from services.polling import PollingService, StreamQueue

logger = logging.getLogger(__name__)

class RecordingData(BaseModel):
    """기록 항목 1건 (데이터 + 수집 timestamp)."""
    data: Any
    timestamp: float

class RecordingService:
    """polling 데이터를 구독해 메모리에 기록하는 서비스."""

    def __init__(self, polling_service: PollingService, name: str = ""):
        self.polling_service: PollingService = polling_service
        self.name: str = name

        self._queue = StreamQueue()

        self.recordings: list[RecordingData] = []

        # recording 루프를 제어하는 event.
        # Unset(False) = 기록 중지, Set(True) = 기록 수행.
        self._recording_running = asyncio.Event()

        self._recording_task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self):
        """백그라운드 서비스를 시작한다 (기록은 start_recording 전까지 Idle)."""
        self._running = True
        self._recording_task = asyncio.create_task(self._loop())
        logger.info(f"Service [{self.name}]: Started (Idle)")

    async def stop(self):
        """서비스를 gracefully 정지한다."""
        self._running = False
        if self._recording_task:
            self._recording_task.cancel()
            try:
                await self._recording_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Service [{self.name}]: Stopped")

    async def start_recording(self, clear=True):
        """기록을 시작한다 (clear=True면 기존 기록 삭제 후 시작)."""
        if clear:
            self.recordings.clear()

        self._recording_running.set()
        await self.polling_service.subscribe(self._queue)

    async def stop_recording(self):
        """기록을 정지하고 queue를 새로 교체한다."""
        self._recording_running.clear()
        await self.polling_service.unsubscribe(self._queue)
        self._queue.shutdown()
        self._queue = StreamQueue()

    async def retrieve_recording(self):
        """지금까지 축적된 기록을 반환한다."""
        return self.recordings

    async def _loop(self):
        """백그라운드 recording 루프."""
        while self._running:
            await self._recording_running.wait()

            try:
                result, timestamp = await self._queue.get()
                self.recordings.append(RecordingData(
                    data=result,
                    timestamp=timestamp,
                ))
            except asyncio.QueueShutDown:
                pass
            except Exception as e:
                logger.error(f"Service [{self.name}]: Error in loop: {e}", exc_info=e)