"""Tests for config.py — load, write, validate, CLI overrides."""

from pathlib import Path

import pytest

from autoplot.config import (
    AutoplotConfig,
    ServerConfig,
    WatchConfig,
    load_config,
    write_default_config,
    apply_cli_overrides,
)


class TestWriteDefaultConfig:
    def test_creates_file(self, tmp_path):
        p = tmp_path / "test_config.yml"
        write_default_config(p)
        assert p.exists()
        content = p.read_text()
        assert "server:" in content
        assert "watch:" in content
        assert "loaders:" in content
        assert "plots:" in content
        assert "fits:" in content


class TestLoadConfig:
    def test_loads_full_config(self, tmp_path):
        p = tmp_path / "test_config.yml"
        p.write_text("""\
server:
  port: 12345
  address: "127.0.0.1"
  allow_origin: ["*"]

watch:
  directory: "/data"
  extensions: [".ddh5", ".nc"]

loaders:
  - autoplot.loaders.ddh5.DDH5Loader

plots:
  value: autoplot.plots.value.ValuePlot

fits:
  - labcore.analysis.fitfuncs.generic.Cosine
""")
        config = load_config(p)
        assert config.server.port == 12345
        assert config.server.address == "127.0.0.1"
        assert config.server.allow_origin == ["*"]
        assert config.watch.directory == "/data"
        assert config.watch.extensions == [".ddh5", ".nc"]
        assert len(config.loaders) == 1
        assert config.plots["value"] == "autoplot.plots.value.ValuePlot"
        assert len(config.fits) == 1

    def test_loads_defaults_for_missing_keys(self, tmp_path):
        p = tmp_path / "empty.yml"
        p.write_text("")
        config = load_config(p)
        assert config.server.port == 19530
        assert config.watch.extensions == [".ddh5"]

    def test_validates_port(self, tmp_path):
        p = tmp_path / "bad.yml"
        p.write_text("server:\n  port: 0\n")
        with pytest.raises(ValueError, match="1024"):
            load_config(p)

    def test_validates_extensions(self, tmp_path):
        p = tmp_path / "bad.yml"
        p.write_text("watch:\n  extensions: [ddh5]\n")
        with pytest.raises(ValueError, match="start with"):
            load_config(p)


class TestApplyCLIOverrides:
    def test_overrides_directory(self):
        config = AutoplotConfig()
        config.watch.directory = "."
        result = apply_cli_overrides(config, directory="/other/path")
        assert result.watch.directory == "/other/path"

    def test_no_overrides_when_none(self):
        config = AutoplotConfig()
        original = config.watch.directory
        result = apply_cli_overrides(config, directory=None)
        assert result.watch.directory == original
