import asyncio
import logging
from typing import Any

from pydantic import BaseModel

from services.polling import DataSourceResult, PollingService, StreamQueue

logger = logging.getLogger(__name__)

class RecordingData(BaseModel):
    data: Any
    timestamp: float

class RecordingService:
    def __init__(self, polling_service: PollingService, name: str = ""):
        self.polling_service: PollingService = polling_service
        self.name: str = name

        self._queue = StreamQueue()

        self.recordings: list[RecordingData] = []
        
        # This event controls the loop. 
        # Unset (False) = Stop Polling. Set (True) = Poll.
        self._recording_running = asyncio.Event()
        
        self._recording_task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self):
        """Starts the background service."""
        self._running = True
        self._recording_task = asyncio.create_task(self._loop())
        logger.info(f"Service [{self.name}]: Started (Idle)")

    async def stop(self):
        """Stops the service gracefully."""
        self._running = False
        if self._recording_task:
            self._recording_task.cancel()
            try:
                await self._recording_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Service [{self.name}]: Stopped")
    
    async def start_recording(self, clear=True):
        if clear:
            self.recordings.clear()

        self._recording_running.set()
        await self.polling_service.subscribe(self._queue)
    
    async def stop_recording(self):
        self._recording_running.clear()
        await self.polling_service.unsubscribe(self._queue)
    
    async def retrieve_recording(self):
        return self.recordings

    async def _loop(self):
        """The background job."""
        while self._running:
            await self._recording_running.wait()

            try:
                result: DataSourceResult = await self._queue.get()
                if result is None or not isinstance(result, DataSourceResult):
                    continue
                self.recordings.append(RecordingData(
                    data=result.data,
                    timestamp=result.timestamp,
                ))
            except Exception as e:
                logger.error(f"Service [{self.name}]: Error in loop: {e}", exc_info=e)