"""door/deadbolt 에러 상태 관리 서비스.

IO status polling을 구독해 door 열림 시간과 deadbolt 동작 반영 여부를
추적하고, /health 엔드포인트의 door/deadbolt 판정에 사용된다:
- door_error: door가 door_open_error_seconds(기본 180s) 넘게 열려 있으면 에러
- deadbolt_error: deadbolt 제어 후 deadbolt_apply_timeout_seconds(기본 5s) 내
  상태가 반영되지 않으면 에러

임계값은 Settings.health (IO_BOARD__HEALTH__*)로 오버라이드할 수 있다.
"""

import asyncio
import logging
from time import time

from services.io_board.io_types import DeadboltAction, DeadboltState, DoorState, IOStatusData
from services.polling import PollingService, StreamQueue


logger = logging.getLogger(__name__)

class ErrorStateManagementService:
    """IO status를 구독해 door/deadbolt 에러 상태를 추적하는 서비스."""

    def __init__(
        self,
        polling_service: PollingService,
        name: str = "",
        door_open_error_seconds: float = 180.0,
        deadbolt_apply_timeout_seconds: float = 5.0,
    ):
        self.polling_service: PollingService = polling_service
        self.name: str = name

        # /health 판정 임계값 (기본값은 기존 하드코딩 값과 동일: 180s / 5s)
        self.door_open_error_seconds: float = door_open_error_seconds
        self.deadbolt_apply_timeout_seconds: float = deadbolt_apply_timeout_seconds

        # 마지막으로 door "닫힘"이 관측된 시각 (None이면 아직 관측 없음)
        self.door_last_closed_time: float | None = None
        self.deadbolt_engaged_time: float | None = None
        self.deadbolt_engaged_state: DeadboltState | None = None

        self._queue = StreamQueue()

        self._recording_task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self):
        """백그라운드 서비스를 시작하고 polling을 구독한다."""
        self._running = True
        self._recording_task = asyncio.create_task(self._loop())
        logger.info(f"Service [{self.name}]: Started (Idle)")
        await self.polling_service.subscribe(self._queue)

    async def stop(self):
        """구독을 해제하고 서비스를 gracefully 정지한다."""
        await self.polling_service.unsubscribe(self._queue)
        self._queue.shutdown()
        self._queue = StreamQueue()

        self._running = False
        if self._recording_task:
            self._recording_task.cancel()
            try:
                await self._recording_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Service [{self.name}]: Stopped")

    async def door_error(self) -> bool:
        """door 상태 정상 여부.

        마지막 닫힘 관측 후 door_open_error_seconds(기본 180s) 초과 시
        False (에러).
        """
        if self.door_last_closed_time and (
            time() - self.door_last_closed_time
        ) > self.door_open_error_seconds:
            return False
        return True

    async def set_deadbolt_action(self, action: DeadboltAction):
        """deadbolt 제어 요청을 기록한다 (기대 상태 + 요청 시각)."""
        self.deadbolt_engaged_state = DeadboltState.LOCKED if action == DeadboltAction.CLOSE else DeadboltState.UNLOCK
        self.deadbolt_engaged_time = time()

    async def deadbolt_error(self) -> bool:
        """deadbolt 정상 여부.

        제어 후 deadbolt_apply_timeout_seconds(기본 5s) 내 기대 상태 미반영 시
        False (에러).
        """
        if self.deadbolt_engaged_state is None:
            return True
        if self.deadbolt_engaged_time and (
            time() - self.deadbolt_engaged_time
        ) > self.deadbolt_apply_timeout_seconds:
            return False
        return True

    async def _loop(self):
        """백그라운드 상태 추적 루프."""
        while self._running:
            try:
                result, timestamp = await self._queue.get()
                result: IOStatusData

                # door가 닫혀 있으면 기준 시각을 갱신한다
                # (열린 채로 door_open_error_seconds가 지나면 door_error가
                # 에러를 보고)
                if result['door'] == DoorState.CLOSED:
                    self.door_last_closed_time = timestamp

                # deadbolt가 기대 상태에 도달하면 추적을 종료한다
                if self.deadbolt_engaged_state is not None and result['deadbolt'] == self.deadbolt_engaged_state:
                    self.deadbolt_engaged_state = None
                    self.deadbolt_engaged_time = None

            except asyncio.QueueShutDown:
                pass
            except Exception as e:
                logger.error(f"Service [{self.name}]: Error in loop: {e}", exc_info=e)