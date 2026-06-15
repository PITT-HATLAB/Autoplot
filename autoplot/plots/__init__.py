"""Plot registry — discovers and manages plot types from config."""

import importlib
import logging

from .base import PlotNode, plot_df_as_2d, plot_xr_as_2d
from .value import ValuePlot
from .complex_hist import ComplexHist
from .magnitude_phase import MagnitudePhasePlot

logger = logging.getLogger(__name__)

_registry: dict[str, type] = {}


def discover_from_config(plots_config: dict[str, str]) -> dict[str, type]:
    """Given {'name': 'module.ClassName', ...}, import and register."""
    for name, dotted_path in plots_config.items():
        try:
            modname, clsname = dotted_path.rsplit(".", 1)
            module = importlib.import_module(modname)
            cls = getattr(module, clsname)
            _registry[name] = cls
        except Exception as e:
            logger.error("Could not load plot '%s' (%s): %s", name, dotted_path, e)
    return _registry


def get_graph_types() -> dict:
    """Return graph types dict for Node.graph_types."""
    return {name: cls for name, cls in _registry.items()}
