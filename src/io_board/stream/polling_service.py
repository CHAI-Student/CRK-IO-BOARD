import asyncio
import logging

from .data_sources import DataSource
from .stream_queues import Queue

logger = logging.getLogger(__name__)

class PollingService:
    def __init__(self, data_source: DataSource, interval: float = 1.0, name: str = ""):
        self.data_source: DataSource = data_source
        self.subscribers: set[Queue] = set()
        self.interval: float = interval
        self.name: str = name
        
        # This event controls the loop. 
        # Unset (False) = Stop Polling. Set (True) = Poll.
        self._has_subscribers = asyncio.Event()
        
        self._polling_task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self):
        """Starts the background service."""
        self._running = True
        self._polling_task = asyncio.create_task(self._loop())
        logger.info(f"Service [{self.name}]: Started (Idle)")

    async def stop(self):
        """Stops the service gracefully."""
        self._running = False
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Service [{self.name}]: Stopped")

    async def subscribe(self, queue: Queue):
        """Register a subscriber queue."""
        self.subscribers.add(queue)
        logger.info(f"Service [{self.name}]: Subscriber added. Total: {len(self.subscribers)}")
        
        # If this is the first subscriber, wake up the loop
        if len(self.subscribers) == 1:
            self._has_subscribers.set()
            logger.info(f"Service [{self.name}]: >>> Polling RESUMED <<<")

    async def unsubscribe(self, queue: Queue):
        """Unregister a subscriber queue."""
        if queue in self.subscribers:
            self.subscribers.remove(queue)
            logger.info(f"Service [{self.name}]: Subscriber removed. Total: {len(self.subscribers)}")
            
            # If no subscribers left, pause the loop
            if len(self.subscribers) == 0:
                self._has_subscribers.clear()
                logger.info(f"Service [{self.name}]: >>> Polling PAUSED <<<")

    async def _loop(self):
        """The background job."""
        while self._running:
            # 1. WAIT: This blocks here indefinitely until set() is called.
            # Does not consume CPU while waiting.
            await self._has_subscribers.wait()

            # 2. POLL: Fetch data
            try:
                data = await self.data_source.fetch()
                logger.info(f"Service [{self.name}]: Polled Data [{data}]")

                # 3. BROADCAST: Send to all active queues
                # We iterate over a copy list() in case a subscriber leaves during iteration
                for q in list(self.subscribers):
                    await q.put(data)

                # 4. INTERVAL: Wait before next poll
                await asyncio.sleep(self.interval)

            except Exception as e:
                logger.error(f"Service [{self.name}]: Error in loop: {e}")
                await asyncio.sleep(self.interval) # Backoff on error