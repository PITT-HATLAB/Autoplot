"""Core node classes and pipeline architecture for autoplot.

Provides:
- Node: base class for all processing nodes
- Pipeline: imperative chain of processing nodes
- Preprocessor nodes: SplitComplexNode, AverageNode, RotateIQNode
- XYSelect: widget for selecting x/y plot axes
- Utility functions: labeled_widget, plot_data
"""

from typing import Any, Optional, Union

import numpy as np
import pandas as pd
import panel as pn
import param
import xarray as xr
from panel.widgets import RadioButtonGroup as RBG

Data = Union[xr.Dataset, pd.DataFrame]
DataDisplay = Optional[Union[pn.pane.DataFrame, xr.Dataset, str]]


class Node(pn.viewable.Viewer):
    """Base class for all processing nodes.

    Each node has data_in/data_out params for Panel reactivity.
    Subclasses override process() to implement data transforms.
    No watcher chains between nodes — Pipeline manages the flow imperatively.
    """

    data_in = param.Parameter(None)
    data_out = param.Parameter(None)

    units_in = param.Parameter({})
    units_out = param.Parameter({})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.layout = pn.Column()

    def __panel__(self):
        return self.layout

    def process(self) -> None:
        self.data_out = self.data_in

    @staticmethod
    def render_data(data: Optional[Data]) -> DataDisplay:
        if data is None:
            return "No data"
        if isinstance(data, pd.DataFrame):
            return pn.pane.DataFrame(data, max_rows=20, show_dimensions=True)
        elif isinstance(data, xr.Dataset):
            return data
        else:
            raise NotImplementedError(
                f"render_data not implemented for type {type(data)}")

    @staticmethod
    def data_dims(data: Optional[Data]) -> tuple[list[str], list[str]]:
        from labcore.data.tools import data_dims as _data_dims
        return _data_dims(data)

    @staticmethod
    def mean(data: Data, *dims: str) -> Data:
        if isinstance(data, pd.DataFrame):
            indep, _ = Node.data_dims(data)
            for d in dims:
                if d in indep:
                    indep.remove(d)
            return data.groupby(level=tuple(indep)).mean()
        elif isinstance(data, xr.Dataset):
            for d in dims:
                data = data.mean(d, skipna=True)
            return data
        else:
            raise NotImplementedError(
                f"mean not implemented for type {type(data)}")

    @staticmethod
    def split_complex(data: Data) -> Data:
        from labcore.data.tools import split_complex as _split_complex
        return _split_complex(data)

    @staticmethod
    def rotate_iq(data: Data, angle_deg: float) -> Data:
        angle_rad = np.deg2rad(angle_deg)
        cos_a = np.cos(angle_rad)
        sin_a = np.sin(angle_rad)

        if isinstance(data, pd.DataFrame):
            data_rot = data.copy()
            re_cols = [col for col in data.columns if col.endswith('_Re')]
            for re_col in re_cols:
                im_col = re_col[:-3] + '_Im'
                if im_col in data.columns:
                    re = data[re_col].values
                    im = data[im_col].values
                    data_rot[re_col] = cos_a * re - sin_a * im
                    data_rot[im_col] = sin_a * re + cos_a * im
            return data_rot
        elif isinstance(data, xr.Dataset):
            data_rot = data.copy(deep=False)
            re_vars = [var for var in data.data_vars if var.endswith('_Re')]
            for re_var in re_vars:
                im_var = re_var[:-3] + '_Im'
                if im_var in data.data_vars:
                    data_rot[re_var] = (
                        cos_a * data[re_var] - sin_a * data[im_var])
                    data_rot[im_var] = (
                        sin_a * data[re_var] + cos_a * data[im_var])
            return data_rot
        else:
            raise NotImplementedError(
                f"rotate_iq not implemented for type {type(data)}")

    @staticmethod
    def complex_dependents(data: Optional[Data]) -> dict[str, dict[str, str]]:
        ret = {}
        _, dep = Node.data_dims(data)
        if dep is None:
            return ret
        for d in dep:
            if d.endswith("_Re"):
                im_dep = d[:-3] + "_Im"
                if im_dep in dep:
                    ret[d[:-3]] = dict(real=d, imag=im_dep)
        return ret

    def dim_label(self, dim: str, which: str = "out") -> str:
        units = self.units_out if which == "out" else self.units_in
        if dim in units and units[dim] is not None:
            return f"{dim} ({units[dim]})"
        return f"{dim} (a.u.)"

    def dim_labels(self, which: str = "out") -> dict[str, str]:
        indep, dep = (
            self.data_dims(self.data_out) if which == "out"
            else self.data_dims(self.data_in)
        )
        dims = (indep or []) + (dep or [])
        return {d: self.dim_label(d, which=which) for d in dims}


class Pipeline(pn.viewable.Viewer):
    """Imperative pipeline of processing nodes.

    Pipeline.run(path) orchestrates: Loader → Preprocessors → data_out.
    The result is stored on self.data_out for downstream watchers.
    """

    data_out = param.Parameter(None)

    def __init__(self, nodes: list[Node], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._nodes = nodes
        self.layout = pn.Column()

    def __panel__(self):
        return self.layout

    def run(self) -> None:
        data = None
        for node in self._nodes:
            node.data_in = data
            node.process()
            data = node.data_out
        self.data_out = data


class XYSelect(pn.viewable.Viewer):
    """Widget for selecting x and y axes from a list of options."""

    value = param.Tuple(default=("None", "None"))
    options = param.List(default=["None"])

    def __init__(self):
        self._xrbg = RBG(options=self.options, name="x")
        self._yrbg = RBG(options=self.options, name="y")
        super().__init__()
        self._layout = pn.Column(
            labeled_widget(self._xrbg),
            labeled_widget(self._yrbg),
        )
        self._sync_x()
        self._sync_y()

    def __panel__(self):
        return self._layout

    @param.depends("options", watch=True)
    def on_option_change(self):
        self._xrbg.options = self.options
        self._yrbg.options = self.options

    @param.depends("value", watch=True)
    def _sync_widgets(self):
        if self.value[0] == self.value[1] and self.value[0] != "None":
            self.value = (self.value[0], "None")
        self._xrbg.value = self.value[0]
        self._yrbg.value = self.value[1]

    @param.depends("_xrbg.value", watch=True)
    def _sync_x(self):
        x = self._xrbg.value
        y = self.value[1]
        if y == x:
            y = "None"
        self.value = (x, y)

    @param.depends("_yrbg.value", watch=True)
    def _sync_y(self):
        y = self._yrbg.value
        x = self.value[0]
        if y == x:
            x = "None"
        self.value = (x, y)


class SplitComplexNode(Node):
    """Preprocessor: splits complex-valued dependent variables into Re/Im parts."""

    def process(self) -> None:
        if self.data_in is not None:
            self.data_out = self.split_complex(self.data_in)
        else:
            self.data_out = None


class AverageNode(Node):
    """Preprocessor: averages data along a specified dimension."""

    enabled = param.Boolean(True)
    dim_name = param.String("rep")

    def __init__(self, **params):
        super().__init__(**params)
        self._toggle = pn.widgets.Switch(
            value=True, name="Average", align="center")
        self._dim_input = pn.widgets.TextInput(
            value="rep", name="Average dim.", width=100, align="end")
        self._toggle.param.watch(self._on_toggle, "value")
        self._dim_input.param.watch(self._on_dim_change, "value")

        self.layout = pn.Column(
            self._toggle,
            self._dim_input,
        )

    def _on_toggle(self, *events):
        self.enabled = self._toggle.value

    def _on_dim_change(self, *events):
        self.dim_name = self._dim_input.value

    def process(self) -> None:
        if self.data_in is not None and self.enabled:
            indep, _ = self.data_dims(self.data_in)
            if indep and self.dim_name in indep:
                self.data_out = self.mean(self.data_in, self.dim_name)
            else:
                self.data_out = self.data_in
        else:
            self.data_out = self.data_in


class RotateIQNode(Node):
    """Preprocessor: rotates IQ data by a specified angle in degrees."""

    enabled = param.Boolean(False)
    angle = param.Number(0.0)

    def __init__(self, **params):
        super().__init__(**params)
        self._toggle = pn.widgets.Switch(
            value=False, name="Rotate IQ", align="center")
        self._angle_input = pn.widgets.FloatInput(
            value=0.0, name="Rotate angle (deg)", width=100, align="end")
        self._toggle.param.watch(self._on_toggle, "value")
        self._angle_input.param.watch(self._on_angle_change, "value")

        self.layout = pn.Column(
            self._toggle,
            self._angle_input,
        )

    def _on_toggle(self, *events):
        self.enabled = self._toggle.value

    def _on_angle_change(self, *events):
        self.angle = self._angle_input.value

    def process(self) -> None:
        if self.data_in is not None and self.enabled:
            self.data_out = self.rotate_iq(self.data_in, self.angle)
        else:
            self.data_out = self.data_in


def labeled_widget(w, lbl=None):
    m = w.margin
    if lbl is None:
        lbl = w.name
    lbl_w = pn.widgets.StaticText(value=lbl, margin=(m[0], m[1], 0, m[1]))
    w.margin = (0, m[1], m[0], m[1])
    return pn.Column(lbl_w, w)


def plot_data(data: Data) -> pn.viewable.Viewable:
    n = Node(data_in=data, name="plot")
    return pn.Column(n, n.plot)
