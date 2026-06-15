import asyncio
import logging
from time import time

from services.io_board.io_types import DeadboltAction, DeadboltState, DoorState, IOStatusData
from services.polling import PollingService, StreamQueue


logger = logging.getLogger(__name__)

class ErrorStateManagementService:
    def __init__(self, polling_service: PollingService, name: str = ""):
        self.polling_service: PollingService = polling_service
        self.name: str = name

        self.door_last_state: DoorState | None = None
        self.door_open_time: float | None = None
        self.deadbolt_engaged_time: float | None = None
        self.deadbolt_engaged_state: DeadboltState | None = None

        self._queue = StreamQueue()
        
        self._recording_task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self):
        """Starts the background service."""
        self._running = True
        self._recording_task = asyncio.create_task(self._loop())
        logger.info(f"Service [{self.name}]: Started (Idle)")
        await self.polling_service.subscribe(self._queue)

    async def stop(self):
        """Stops the service gracefully."""
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
        # if it was over 3minutes since the last recording, return False to indicate that the system is in an error state
        if self.door_open_time and (time() - self.door_open_time) > 180:
            return False
        return True
    
    async def set_deadbolt_action(self, action: DeadboltAction):
        self.deadbolt_engaged_state = DeadboltState.LOCKED if action == DeadboltAction.CLOSE else DeadboltState.UNLOCK
        self.deadbolt_engaged_time = time()
    
    async def deadbolt_error(self) -> bool:
        if self.deadbolt_engaged_state is None:
            return True
        if self.deadbolt_engaged_time and (time() - self.deadbolt_engaged_time) > 5:
            return False
        return True
    
    async def _loop(self):
        """The background job."""
        while self._running:
            try:
                result, timestamp = await self._queue.get()
                result: IOStatusData

                if result['door'] == DoorState.CLOSED:
                    self.door_open_time = timestamp
                
                if self.deadbolt_engaged_state is not None and result['deadbolt'] == self.deadbolt_engaged_state:
                    self.deadbolt_engaged_state = None
                    self.deadbolt_engaged_time = None

            except asyncio.QueueShutDown:
                pass
            except Exception as e:
                logger.error(f"Service [{self.name}]: Error in loop: {e}", exc_info=e)