"""Fit registry — discovers fit function classes from config."""

import importlib
import logging
from pathlib import Path
from typing import Optional

from labcore.analysis.fit import Fit, FitResult, fit_and_add_to_ds, plot_ds_2d_with_fit

logger = logging.getLogger(__name__)

_registry: dict[str, type] = {}


def discover_from_config(fits_config: list[str]) -> dict[str, type]:
    """Given ['module.ClassName', ...], import and register all fit classes."""
    for dotted_path in fits_config:
        try:
            modname, clsname = dotted_path.rsplit(".", 1)
            module = importlib.import_module(modname)
            cls = getattr(module, clsname)
            _registry[clsname] = cls
        except Exception as e:
            logger.error(
                "Could not load fit '%s': %s", dotted_path, e)
    return _registry


def load_fits(fits_config: Optional[list[str]] = None) -> None:
    """Load and register all fit classes.

    If *fits_config* is given, register those classes directly.
    Otherwise, read fits from ``autoplotConfig.yml`` in the current
    working directory (backward-compatible default).
    """
    if fits_config is not None:
        discover_from_config(fits_config)
        return

    import ruamel.yaml
    cwd = Path.cwd()
    config_path = cwd / "autoplotConfig.yml"
    if not config_path.exists():
        logger.warning(
            "No autoplotConfig.yml found at %s. "
            "Run 'autoplot' to create a default config first.",
            config_path,
        )
        return

    yaml = ruamel.yaml.YAML()
    with open(config_path, "r") as f:
        raw_config = yaml.load(f)

    fits_config = raw_config.get("fits", []) if raw_config else []
    discover_from_config(fits_config)
