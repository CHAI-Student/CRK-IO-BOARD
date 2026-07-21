"""polling 서비스용 DataSource 정의.

PollingService가 주기적으로 fetch하는 데이터 소스(loadcell, IO status)를
정의한다. fetch 결과는 성공(DataSourceResult) 또는 실패(DataSourceError)
로 감싸져 StreamQueue를 통해 구독자에게 전달된다.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import services.io_board.commands

logger = logging.getLogger(__name__)


@dataclass
class DataSourceResult:
    """fetch 성공 결과 (데이터 + 수집 시각)."""
    data: Any
    timestamp: float = field(default_factory=time.time)


@dataclass
class DataSourceError:
    """fetch 실패 결과 (예외 + 발생 시각). 소비 시점에 다시 raise된다."""
    error: BaseException
    timestamp: float = field(default_factory=time.time)


class DataSource:
    """polling 대상 데이터 소스의 base 클래스."""

    async def fetch(self) -> DataSourceResult | DataSourceError:
        raise NotImplementedError("Subclasses must implement this method")


class LoadCellsDataSource(DataSource):
    """loadcell 판독값 데이터 소스 (throttle/sanitizer 적용된 command 사용)."""

    async def fetch(self):
        try:
            loadcells = await services.io_board.commands.get_loadcells()
            return DataSourceResult(data=loadcells)
        except Exception as e:
            return DataSourceError(error=e)


class IOStatusDataSource(DataSource):
    """door/deadbolt IO status 데이터 소스."""

    async def fetch(self):
        try:
            io_status = await services.io_board.commands.get_status()
            return DataSourceResult(data=io_status)
        except Exception as e:
            return DataSourceError(error=e)
