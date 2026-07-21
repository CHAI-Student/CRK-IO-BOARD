# StreamQueue의 타입 stub — get()/get_nowait()이 (data, timestamp)
# 튜플로 unwrap해 반환한다는 사실을 타입 체커에 알린다.
import asyncio
from typing import Any

class StreamQueue(asyncio.Queue):
    def __init__(self, maxsize: int = 0) -> None: ...

    async def get(self) -> tuple[Any, float]: ...
    
    def get_nowait(self) -> tuple[Any, float]: ...