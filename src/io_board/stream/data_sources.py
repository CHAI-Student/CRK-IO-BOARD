import logging
import time
from dataclasses import dataclass, field
from typing import Any

import io_board.commands

logger = logging.getLogger(__name__)


@dataclass
class DataSourceResult:
    data: Any
    timestamp: float = field(default_factory=time.time)


@dataclass
class DataSourceError:
    error: BaseException
    timestamp: float = field(default_factory=time.time)


class DataSource:
    async def fetch(self) -> DataSourceResult | DataSourceError:
        raise NotImplementedError("Subclasses must implement this method")


class LoadCellsDataSource(DataSource):
    async def fetch(self):
        try:
            loadcells = await io_board.commands.get_loadcells()
            return DataSourceResult(data=loadcells)
        except Exception as e:
            return DataSourceError(error=e)


class IOStatusDataSource(DataSource):
    async def fetch(self):
        try:
            io_status = await io_board.commands.get_status()
            return DataSourceResult(data=io_status)
        except Exception as e:
            return DataSourceError(error=e)
