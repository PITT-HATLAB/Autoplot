import numpy as np
import xarray as xr
import pytest
from pathlib import Path


@pytest.fixture
def simple_dataset():
    return xr.Dataset(
        {"I": (["x"], np.array([1.0, 2.0, 3.0]))},
        coords={"x": [0, 1, 2]},
    )


@pytest.fixture
def sample_config_path(tmp_path):
    p = tmp_path / "test_config.yml"
    p.write_text("""\
server:
  port: 19530
  address: "0.0.0.0"
  allow_origin: []

watch:
  directory: "."
  extensions: [".ddh5"]

loaders:
  - autoplot.loaders.ddh5.DDH5Loader

plots:
  value: autoplot.plots.value.ValuePlot

fits:
  - labcore.analysis.fitfuncs.generic.Cosine
""")
    return p
