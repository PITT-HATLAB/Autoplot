"""ValuePlot: line/scatter plot for 1D data, heatmap/quadmesh for 2D."""

import pandas as pd
import panel as pn
import param
import xarray as xr

from ..nodes import Node, XYSelect
from .base import PlotNode, plot_df_as_2d, plot_xr_as_2d


class ValuePlot(PlotNode):
    """Plot data values as line + scatter (1D) or heatmap/quadmesh (2D)."""

    def __init__(self, *args, **kwargs):
        self.xy_select = XYSelect()
        self._old_indep = []

        super().__init__(*args, **kwargs)

        self.graph_types = {"None": None, "Value": ValuePlot}
        self._update_graph_type_options()

    def _update_graph_type_options(self):
        self.plot_type_select.options = list(self.graph_types.keys())
        if "Value" in self.graph_types:
            self.plot_type_select.value = "Value"

    @pn.depends("data_out")
    def plot_options_panel(self):
        indep, dep = self.data_dims(self.data_out)

        opts = ["None"]
        if indep is not None:
            opts += indep
        self.xy_select.options = opts

        if indep != self._old_indep and dep:
            if len(opts) > 2:
                self.xy_select.value = (opts[-2], opts[-1])
            elif len(opts) > 1:
                self.xy_select.value = (opts[-1], "None")
        self._old_indep = indep

        return self.xy_select

    @pn.depends("data_out", "xy_select.value", "refresh_graph")
    def plot_panel(self):
        self.refresh_graph = False
        plot = "*No valid options chosen.*"
        x, y = self.xy_select.value

        if x in ["None", None]:
            pass

        elif y in ["None", None]:
            if isinstance(self.data_out, pd.DataFrame):
                plot = self.data_out.hvplot.line(
                    x=x, xlabel=self.dim_label(x),
                    y=self.get_data_fit_names(self.fit_axis_options()),
                ) * self.data_out.hvplot.scatter(x=x)

            elif isinstance(self.data_out, xr.Dataset):
                plot = self.data_out.hvplot.line(
                    x=x, xlabel=self.dim_label(x),
                    y=self.get_data_fit_names(self.fit_axis_options()),
                ) * self.data_out.hvplot.scatter(x=x)
            else:
                raise NotImplementedError

        else:
            if isinstance(self.data_out, pd.DataFrame):
                plot = plot_df_as_2d(
                    self.data_out, x, y,
                    dim_labels=self.dim_labels(),
                    graph_axes=self.get_data_fit_names(
                        self.fit_axis_options()),
                )
            elif isinstance(self.data_out, xr.Dataset):
                plot = plot_xr_as_2d(
                    self.data_out, x, y,
                    dim_labels=self.dim_labels(),
                    graph_axes=self.get_data_fit_names(
                        self.fit_axis_options()),
                )
            else:
                raise NotImplementedError
            try:
                plot = plot.cols(2)
            except Exception:
                pass

        return plot

    def fit_axis_options(self):
        _, dep = self.data_dims(self.data_out)
        return list(dep) if dep else []

    def get_plot(self):
        return self.plot_panel()
