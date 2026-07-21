"""polling 구독자용 stream queue.

PollingService가 넣은 DataSourceResult/DataSourceError를 소비하는
asyncio.Queue 확장. 성공 결과는 (data, timestamp) 튜플로 풀어서
반환하고, 에러 결과는 소비 시점에 원래 예외를 다시 raise한다.
(async get()도 내부적으로 get_nowait()을 거치므로 동일하게 동작한다.)
"""

import asyncio

from .data_sources import DataSourceError, DataSourceResult

class StreamQueue(asyncio.Queue):
    """결과 unwrap과 에러 re-raise를 수행하는 polling 구독 queue."""

    def __init__(self, maxsize: int = 0):
        super().__init__(maxsize=maxsize)

    def get_nowait(self):
        item: DataSourceResult | DataSourceError = super().get_nowait()
        if isinstance(item, DataSourceError):
            raise item.error
        return item.data, item.timestamp
