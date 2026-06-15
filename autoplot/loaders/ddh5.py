import asyncio
from datetime import datetime
from pathlib import Path

import param
import panel as pn
import xarray as xr

from .base import BaseLoader
from ..nodes import Node


class DDH5Loader(BaseLoader, Node):
    """Loads data from DDH5 files using labcore.data.ddh5_xr.ddh5_to_xarray."""

    file_path = param.Parameter(None)

    grid_on_load_toggle = param.Boolean(True)
    auto_load_toggle = param.Boolean(False)

    def __init__(self, **params):
        super().__init__(**params)

        self._refresh_callback = None
        self._refresh_task = None

        self.refresh_widget = pn.widgets.Select(
            name="Auto-refresh",
            options={
                "None": None,
                "2 s": 2,
                "5 s": 5,
                "10 s": 10,
                "1 min": 60,
                "10 min": 600,
            },
            value="None",
            width=80,
        )
        self.refresh_widget.param.watch(self._on_refresh_changed, "value")

        self.grid_toggle = pn.widgets.Switch(
            value=True, name="Auto-grid", align="end"
        )
        self.auto_load_switch = pn.widgets.Switch(
            value=False, name="Auto-load on select", align="center"
        )
        self.load_button = pn.widgets.Button(
            name="Load data", align="center", button_type="primary"
        )

        self.status = pn.widgets.StaticText(
            name="Info", align="start", value="No data loaded."
        )

        self.loading_card = pn.Card(
            pn.Row(
                pn.Column(
                    self.grid_toggle,
                    self.auto_load_switch,
                    self.refresh_widget,
                    align="center",
                ),
            ),
            title="Loading Options",
            collapsed=True,
        )

        self.layout = pn.Column(
            pn.Row(
                self.load_button,
                self.loading_card,
            ),
            self.status,
        )

    def __panel__(self):
        return self.layout

    @property
    def extensions(self) -> list[str]:
        return [".ddh5"]

    def load(self, path: Path) -> xr.Dataset:
        from labcore.data.ddh5_xr import ddh5_to_xarray

        data_dir = path.parent
        gridded_path = data_dir / "data_gridded.ddh5"
        if gridded_path.exists():
            load_path = gridded_path
        else:
            load_path = data_dir / "data.ddh5"

        return ddh5_to_xarray(str(load_path))

    def process(self) -> None:
        if self.file_path is None or str(self.file_path) == "":
            self.status.value = (
                "Please select data to load. "
                "If there is no data, try running in a higher directory."
            )
            self.data_out = None
            return

        t0 = datetime.now()
        ds = self.load(Path(self.file_path))

        if not self.grid_toggle.value:
            from labcore.data.tools import split_complex
            ds = split_complex(ds).to_dataframe()

        t1 = datetime.now()
        elapsed_ms = (t1 - t0).microseconds * 1e-3
        self.status.value = (
            f"Loaded data at {t1.strftime('%Y-%m-%d %H:%M:%S')} "
            f"(in {elapsed_ms:.0f} ms)."
        )
        self.data_out = ds

    def set_refresh_callback(self, callback):
        self._refresh_callback = callback

    def _on_refresh_changed(self, *events):
        value = self.refresh_widget.value
        if value is None:
            if self._refresh_task is not None:
                self._refresh_task.cancel()
            self._refresh_task = None
        elif self._refresh_task is None:
            self._refresh_task = asyncio.ensure_future(self._run_auto_refresh())

    async def _run_auto_refresh(self):
        try:
            while self.refresh_widget.value is not None:
                interval = self.refresh_widget.value
                await asyncio.sleep(interval)
                if self._refresh_callback:
                    self._refresh_callback()
        except asyncio.CancelledError:
            pass
