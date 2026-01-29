import asyncio
from typing import Any

from .data_sources import DataSourceError, DataSourceResult

class StreamQueue(asyncio.Queue):
    def __init__(self, maxsize: int = 0) -> None: ...

    async def get(self) -> tuple[Any, float]: ...
    
    def get_nowait(self) -> tuple[Any, float]: ...