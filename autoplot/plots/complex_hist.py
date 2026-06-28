"""ComplexHist: hexbin histograms of IQ readout data."""

import time

import panel as pn
import param

from ..nodes import Node, labeled_widget
from .base import PlotNode


class ComplexHist(PlotNode):
    """IQ hexbin histogram plot — hexbin plot of complex-valued readout data."""

    logz = param.Boolean(default=False, doc="Use logarithmic color scale.")

    def __init__(self, *args, **kwargs):
        self.gb_select = pn.widgets.CheckButtonGroup(
            name="Group by",
            options=[],
            value=[],
        )
        super().__init__(*args, **kwargs)

        self.logz_cb = pn.widgets.Checkbox.from_param(
            self.param.logz, name="Log color scale"
        )
        self.graph_types = {"None": None, "Readout hist.": ComplexHist}
        self._update_graph_type_options()

    def _update_graph_type_options(self):
        self.plot_type_select.options = list(self.graph_types.keys())
        if "Readout hist." in self.graph_types:
            self.plot_type_select.value = "Readout hist."

    @pn.depends("data_out", watch=True)
    def _sync_options(self):
        indep, _ = self.data_dims(self.data_out)
        if isinstance(indep, list):
            self.gb_select.options = indep

    @pn.depends("data_out")
    def plot_options_panel(self):
        return self.logz_cb

    @pn.depends("data_out", "gb_select.value", "logz", "refresh_graph")
    def plot_panel(self):
        self.refresh_graph = False
        layout = pn.Column()

        for k, v in self.complex_dependents(self.data_out).items():
            xlim = (
                float(self.data_out[v["real"]].min()),
                float(self.data_out[v["real"]].max()),
            )
            ylim = (
                float(self.data_out[v["imag"]].min()),
                float(self.data_out[v["imag"]].max()),
            )
            p = self.data_out.hvplot(
                kind="hexbin",
                aspect=1,
                groupby=self.gb_select.value,
                x=v["real"],
                y=v["imag"],
                xlim=xlim,
                ylim=ylim,
                clabel="count",
                title=self.plot_title,
                logz=self.logz,
            )
            layout.append(p)

        return layout if len(layout.objects) > 0 else "*No valid options chosen.*"

    def get_plot(self):
        plt = self.plot_panel()
        objs = getattr(plt, "objects", [])
        if objs and hasattr(objs[0], "object"):
            return objs[0].object
        return plt

    def fit_axis_options(self):
        _dict = dict(self.complex_dependents(self.data_out).items())
        return list(_dict.keys())
