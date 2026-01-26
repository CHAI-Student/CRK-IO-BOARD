import asyncio

from .data_sources import DataSourceError, DataSourceResult

class Queue(asyncio.Queue):
    def __init__(self, maxsize: int = 0):
        super().__init__(maxsize=maxsize)
    
    async def get(self):
        item: DataSourceResult | DataSourceError = await super().get()
        if isinstance(item, DataSourceError):
            raise item.error
        return item.data
    
    def get_nowait(self):
        item: DataSourceResult | DataSourceError = super().get_nowait()
        if isinstance(item, DataSourceError):
            raise item.error
        return item.data
