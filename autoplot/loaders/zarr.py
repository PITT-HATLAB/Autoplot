from pathlib import Path

import xarray as xr

from .base import BaseLoader


class ZarrLoader(BaseLoader):
    """Loads data from Zarr stores using xarray.open_zarr."""

    @property
    def extensions(self) -> list[str]:
        return [".zarr"]

    def load(self, path: Path) -> xr.Dataset:
        return xr.open_zarr(str(path))
