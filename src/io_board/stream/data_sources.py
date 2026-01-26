from dataclasses import dataclass
import logging
from typing import Any

import io_board.commands

logger = logging.getLogger(__name__)

@dataclass
class DataSourceResult:
    data: Any

@dataclass
class DataSourceError:
    error: BaseException

class DataSource:
    async def fetch(self):
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
            io_status = await io_board.commands.get_io_status()
            return DataSourceResult(data=io_status)
        except Exception as e:
            return DataSourceError(error=e)