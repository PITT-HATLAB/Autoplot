from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import logging

import ruamel.yaml

logger = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    port: int = 19530
    address: str = "0.0.0.0"
    allow_origin: list[str] = field(default_factory=list)


@dataclass
class WatchConfig:
    directory: str = "."
    extensions: list[str] = field(default_factory=lambda: [".ddh5"])


@dataclass
class AutoplotConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    watch: WatchConfig = field(default_factory=WatchConfig)
    loaders: list[str] = field(default_factory=lambda: [
        "autoplot.loaders.ddh5.DDH5Loader",
    ])
    plots: dict[str, str] = field(default_factory=lambda: {
        "value": "autoplot.plots.value.ValuePlot",
        "readout_hist": "autoplot.plots.complex_hist.ComplexHist",
        "magnitude_phase": "autoplot.plots.magnitude_phase.MagnitudePhasePlot",
        "data_table": "autoplot.plots.datatable.DataTable",
    })
    fits: list[str] = field(default_factory=lambda: [
        "labcore.analysis.fitfuncs.generic.Cosine",
        "labcore.analysis.fitfuncs.generic.Exponential",
        "labcore.analysis.fitfuncs.generic.ExponentialDecay",
        "labcore.analysis.fitfuncs.generic.ExponentiallyDecayingSine",
    ])


DEFAULT_CONFIG_YAML = """\
# Autoplot Configuration
# Generated automatically. Edit to customize.

server:
  port: 19530
  address: "0.0.0.0"
  allow_origin: []
  # allow_origin: ["host1:19530", "host2:19530"]

watch:
  directory: "."
  extensions: [".ddh5"]

loaders:
  - autoplot.loaders.ddh5.DDH5Loader
  # - autoplot.loaders.netcdf.NetCDFLoader
  # - autoplot.loaders.zarr.ZarrLoader

plots:
  value: autoplot.plots.value.ValuePlot
  readout_hist: autoplot.plots.complex_hist.ComplexHist
  magnitude_phase: autoplot.plots.magnitude_phase.MagnitudePhasePlot
  data_table: autoplot.plots.datatable.DataTable

fits:
  - labcore.analysis.fitfuncs.generic.Cosine
  - labcore.analysis.fitfuncs.generic.Exponential
  - labcore.analysis.fitfuncs.generic.ExponentialDecay
  - labcore.analysis.fitfuncs.generic.ExponentiallyDecayingSine
"""


def _dict_to_server(raw: dict) -> ServerConfig:
    return ServerConfig(
        port=int(raw.get("port", 19530)),
        address=str(raw.get("address", "0.0.0.0")),
        allow_origin=list(raw.get("allow_origin", [])),
    )


def _dict_to_watch(raw: dict) -> WatchConfig:
    return WatchConfig(
        directory=str(raw.get("directory", ".")),
        extensions=list(raw.get("extensions", [".ddh5"])),
    )


def load_config(path: Path) -> AutoplotConfig:
    yaml = ruamel.yaml.YAML()
    with open(path, "r") as f:
        raw = yaml.load(f)

    if raw is None:
        raw = {}

    server = _dict_to_server(raw.get("server", {}))
    watch = _dict_to_watch(raw.get("watch", {}))
    loaders = list(raw.get("loaders", [
        "autoplot.loaders.ddh5.DDH5Loader",
    ]))
    plots = dict(raw.get("plots", {
        "value": "autoplot.plots.value.ValuePlot",
        "readout_hist": "autoplot.plots.complex_hist.ComplexHist",
        "magnitude_phase": "autoplot.plots.magnitude_phase.MagnitudePhasePlot",
    }))
    fits = list(raw.get("fits", [
        "labcore.analysis.fitfuncs.generic.Cosine",
        "labcore.analysis.fitfuncs.generic.Exponential",
        "labcore.analysis.fitfuncs.generic.ExponentialDecay",
        "labcore.analysis.fitfuncs.generic.ExponentiallyDecayingSine",
    ]))

    _validate(server, watch, loaders, plots, fits)

    return AutoplotConfig(
        server=server,
        watch=watch,
        loaders=loaders,
        plots=plots,
        fits=fits,
    )


def _validate(server, watch, loaders, plots, fits) -> None:
    if not (1024 <= server.port <= 65535):
        raise ValueError(f"server.port must be 1024-65535, got {server.port}")
    for ext in watch.extensions:
        if not ext.startswith("."):
            raise ValueError(f"watch.extensions must start with '.', got '{ext}'")
    for entry in loaders:
        if not isinstance(entry, str) or "." not in entry:
            raise ValueError(f"loader entry must be 'module.ClassName', got '{entry}'")
    for name, entry in plots.items():
        if not isinstance(entry, str) or "." not in entry:
            raise ValueError(
                f"plots entry must be 'module.ClassName', got '{entry}' for '{name}'")


def write_default_config(path: Path) -> None:
    path.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
    logger.info(f"Created default config at {path}")


def apply_cli_overrides(config: AutoplotConfig,
                        directory: Optional[str] = None,
                        verbose: bool = False) -> AutoplotConfig:
    if directory is not None:
        config.watch.directory = directory
    return config
