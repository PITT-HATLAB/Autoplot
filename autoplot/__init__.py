"""Autoplot — interactive experiment data visualization library.

Provides a Panel/HoloViews/Xarray-based visualization application
for exploring experimental data. Includes a CLI (`autoplot`),
a file browser widget (`DataSelect`), a node-based data pipeline,
and plugin-based plot types and fit functions.

Usage:
    autoplot -c /path/to/autoplotConfig.yml -d /path/to/data --verbose

Or programmatically:
    from autoplot import make_template, load_config
    config = load_config(Path("autoplotConfig.yml"))
    template = make_template(config)
    template.servable()
"""

__version__ = "0.1.0"

from .nodes import Node, Pipeline, Data, SplitComplexNode, AverageNode, RotateIQNode, XYSelect, labeled_widget, plot_data
from .loaders import BaseLoader
from .loaders.ddh5 import DDH5Loader
from .loaders.netcdf import NetCDFLoader
from .loaders.zarr import ZarrLoader
from .plots.value import ValuePlot
from .plots.complex_hist import ComplexHist
from .plots.magnitude_phase import MagnitudePhasePlot
from .plots.base import PlotNode
from .app import DataSelect, make_template
from .config import AutoplotConfig, load_config, write_default_config, apply_cli_overrides
from .cli import main

__all__ = [
    "__version__",
    "Node",
    "Pipeline",
    "Data",
    "SplitComplexNode",
    "AverageNode",
    "RotateIQNode",
    "XYSelect",
    "labeled_widget",
    "plot_data",
    "BaseLoader",
    "DDH5Loader",
    "NetCDFLoader",
    "ZarrLoader",
    "ValuePlot",
    "ComplexHist",
    "MagnitudePhasePlot",
    "PlotNode",
    "DataSelect",
    "make_template",
    "AutoplotConfig",
    "load_config",
    "write_default_config",
    "apply_cli_overrides",
    "main",
]
