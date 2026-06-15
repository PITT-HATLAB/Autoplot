from pathlib import Path
from typing import Any

import param
import xarray as xr

from ..notify import notify_warning
from .base import BaseLoader


class NetCDFLoader(BaseLoader):
    """Loads data from NetCDF files using xarray.open_dataset."""

    @property
    def extensions(self) -> list[str]:
        return [".nc", ".netcdf"]

    def load(self, path: Path) -> xr.Dataset:
        return xr.open_dataset(str(path))
