from pathlib import Path

import xarray as xr


class BaseLoader:
    """Data loader interface.

    Subclasses implement load() to return an xarray Dataset from a file path.
    Override extensions property and can_handle() for auto-detection.
    """

    def load(self, path: Path) -> xr.Dataset:
        raise NotImplementedError

    def can_handle(self, path: Path) -> bool:
        return path.suffix in self.extensions

    @property
    def extensions(self) -> list[str]:
        return []
