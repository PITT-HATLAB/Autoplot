import importlib
import logging
from pathlib import Path
from typing import Optional

from .base import BaseLoader
from .ddh5 import DDH5Loader
from .netcdf import NetCDFLoader
from .zarr import ZarrLoader

logger = logging.getLogger(__name__)

_registry: dict[str, type[BaseLoader]] = {}


def _import_class(dotted_path: str):
    modname, clsname = dotted_path.rsplit(".", 1)
    module = importlib.import_module(modname)
    return getattr(module, clsname)


def discover_from_config(loader_config: list[str]) -> list[BaseLoader]:
    instances: list[BaseLoader] = []
    for entry in loader_config:
        try:
            cls = _import_class(entry)
            instance = cls()
            instances.append(instance)
            _registry[entry] = cls
        except Exception as e:
            logger.error("Could not load loader '%s': %s", entry, e)
    return instances


def auto_detect(path: Path, loaders: list[BaseLoader]) -> Optional[BaseLoader]:
    for loader in loaders:
        if loader.can_handle(path):
            return loader
    return None
