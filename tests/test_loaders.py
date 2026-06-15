"""Tests for loaders."""

import tempfile
from pathlib import Path

import numpy as np
import xarray as xr
import pytest

from autoplot.loaders import BaseLoader, NetCDFLoader, ZarrLoader, auto_detect


class TestBaseLoader:
    def test_can_handle_by_extension(self):
        class ExtLoader(BaseLoader):
            @property
            def extensions(self):
                return [".test"]
            def load(self, path):
                return xr.Dataset()
        loader = ExtLoader()
        assert loader.can_handle(Path("file.test"))
        assert not loader.can_handle(Path("file.other"))

    def test_load_raises(self):
        loader = BaseLoader()
        with pytest.raises(NotImplementedError):
            loader.load(Path("dummy"))


class TestNetCDFLoader:
    def test_can_handle(self):
        loader = NetCDFLoader()
        assert loader.can_handle(Path("data.nc"))
        assert loader.can_handle(Path("data.netcdf"))
        assert not loader.can_handle(Path("data.ddh5"))

    def test_load_netcdf(self):
        ds = xr.Dataset({"x": ("t", [1, 2, 3])})
        with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as f:
            fname = f.name
            ds.to_netcdf(fname)

        try:
            loader = NetCDFLoader()
            loaded = loader.load(Path(fname))
            assert isinstance(loaded, xr.Dataset)
            assert loaded.sizes["t"] == 3
            loaded.close()
        finally:
            try:
                Path(fname).unlink(missing_ok=True)
            except PermissionError:
                pass


class TestAutoDetect:
    def test_finds_matching_loader(self):
        nc = NetCDFLoader()
        result = auto_detect(Path("test.nc"), [nc])
        assert result is nc

    def test_returns_none_when_no_match(self):
        nc = NetCDFLoader()
        result = auto_detect(Path("test.unknown"), [nc])
        assert result is None
