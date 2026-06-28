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

from .notify import notify_warning

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

    @staticmethod
    def units_from_dataset(data: Optional[Data]) -> dict[str, str]:
        if data is None or isinstance(data, pd.DataFrame):
            return {}
        units = {}
        for dim in list(data.dims) + list(data.data_vars):
            if dim in data.coords:
                unit = data.coords[dim].attrs.get("units", None)
            elif dim in data.data_vars:
                unit = data[dim].attrs.get("units", None)
            else:
                unit = None
            if unit is not None:
                units[dim] = unit
        return units

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
        units = {}
        for node in self._nodes:
            node.data_in = data
            node.units_in = units
            node.process()
            data = node.data_out
            if data is not None and not node.units_out:
                node.units_out = Node.units_from_dataset(data)
            units = node.units_out
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
            dims = [d.strip() for d in self.dim_name.split(",") if d.strip()]
            data = self.data_in
            for d in dims:
                try:
                    indep, _ = self.data_dims(data)
                    if indep and d in indep:
                        data = self.mean(data, d)
                    else:
                        notify_warning(
                            f"Dimension '{d}' not found for averaging"
                        )
                except Exception as e:
                    notify_warning(
                        f"Failed to average over dimension '{d}': {e}"
                    )
            self.data_out = data
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


class WhereFilterNode(Node):
    """Preprocessor: filters data with chained coordinate conditions."""

    enabled = param.Boolean(True)

    def __init__(self, **params):
        self._conditions = []
        self._pipeline_cb = None

        super().__init__(**params)

        self._toggle = pn.widgets.Switch(
            value=False, name="Truncate", align="center")
        self._toggle.param.watch(self._on_toggle, "value")

        self._add_btn = pn.widgets.Button(
            name="+ Add condition", button_type="default")
        self._add_btn.on_click(self._add_condition)

        self._cond_column = pn.Column()

        self.layout = pn.Column(
            self._toggle, self._cond_column, self._add_btn)

    def set_pipeline_callback(self, cb):
        self._pipeline_cb = cb

    def _notify_change(self):
        if getattr(self, '_pipeline_cb', None):
            self._pipeline_cb()

    def _on_toggle(self, *events):
        self.enabled = self._toggle.value
        self._notify_change()

    @pn.depends("data_in", watch=True)
    def _update_coord_options(self):
        coords = self._get_independent_coords()
        for cond in self._conditions:
            current = cond["coord_select"].value
            cond["coord_select"].options = coords
            if current not in coords:
                cond["coord_select"].value = None

    def _get_independent_coords(self):
        if self.data_in is None:
            return []
        try:
            indep, _ = self.data_dims(self.data_in)
            return list(indep or [])
        except Exception:
            if isinstance(self.data_in, xr.Dataset):
                return list(self.data_in.dims)
            return []

    def _add_condition(self, event=None):
        coords = self._get_independent_coords()

        coord_select = pn.widgets.Select(options=coords, width=70, height=35,
                                         margin=(0, 1, 0, 0))
        op_select = pn.widgets.Select(options=[">", "<", ">=", "<=", "==", "sel near"],
                                      width=50, height=20, margin=(2, 1, 0, 0))
        val_input = pn.widgets.FloatInput(value=0.0, width=70, height=35,
                                          margin=(0, 1, 0, 0), align='center')
        remove_btn = pn.widgets.Button(name="X", width=25, height=25,
                                       button_type="danger", margin=(0, 0, 0, 0),align='center')

        def on_remove(event=None):
            for i, c in enumerate(self._conditions):
                if c["row"] is row:
                    self._conditions.pop(i)
                    break
            for i, o in enumerate(self._cond_column.objects):
                if o is row:
                    self._cond_column.pop(i)
                    break
            self._notify_change()

        remove_btn.on_click(on_remove)

        def on_change(*events):
            self._notify_change()

        coord_select.param.watch(on_change, "value")
        op_select.param.watch(on_change, "value")
        val_input.param.watch(on_change, "value")

        row = pn.Row(coord_select, op_select, val_input, remove_btn,
                     margin=(0, 1, 0, 1), align='center')

        self._conditions.append({
            "coord_select": coord_select,
            "op_select": op_select,
            "val_input": val_input,
            "row": row,
        })
        self._cond_column.append(row)

    def process(self):
        if self.data_in is None or not self.enabled:
            self.data_out = self.data_in
            return

        active = [c for c in self._conditions
                  if c["coord_select"].value is not None]
        if not active:
            self.data_out = self.data_in
            return

        data = self.data_in
        for cond in active:
            coord = cond["coord_select"].value
            op = cond["op_select"].value
            val = cond["val_input"].value

            if isinstance(data, xr.Dataset):
                data = self._apply_where_xr(data, coord, op, val)
            elif isinstance(data, pd.DataFrame):
                data = self._apply_where_pd(data, coord, op, val)

        self.data_out = data

    @staticmethod
    def _apply_where_xr(data, coord, op, val):
        if coord not in data.coords and coord not in data.data_vars:
            return data
        c = data[coord]
        if op == ">":      return data.where(c > val, drop=True)
        elif op == "<":    return data.where(c < val, drop=True)
        elif op == ">=":   return data.where(c >= val, drop=True)
        elif op == "<=":   return data.where(c <= val, drop=True)
        elif op == "==":   return data.where(c == val, drop=True)
        elif op == "sel near": return data.sel({coord: val}, method="nearest")
        return data

    @staticmethod
    def _apply_where_pd(data, coord, op, val):
        if isinstance(data.index, pd.MultiIndex) and coord in data.index.names:
            vals = data.index.get_level_values(coord)
            if op == "sel near":
                nearest = vals[(vals - val).abs().argmin()]
                return data.xs(nearest, level=coord)
        elif data.index.name == coord:
            vals = data.index
            if op == "sel near":
                nearest = vals[(vals - val).abs().argmin()]
                return data.xs(nearest)
        elif coord in data.columns:
            vals = data[coord]
            if op == "sel near":
                nearest_idx = (vals - val).abs().idxmin()
                return data.loc[[nearest_idx]]
        else:
            return data
        if op == ">":      mask = vals > val
        elif op == "<":    mask = vals < val
        elif op == ">=":   mask = vals >= val
        elif op == "<=":   mask = vals <= val
        elif op == "==":   mask = vals == val
        else:              return data
        return data[mask]


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
