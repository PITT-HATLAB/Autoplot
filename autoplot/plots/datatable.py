"""DataTable: renders xarray datasets using xarray's built-in HTML repr."""

import panel as pn
import xarray as xr

from .base import PlotNode


class DataTable(PlotNode):
    """Display loaded xarray dataset using xarray's _repr_html_()."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.graph_types = {"None": None, "Data Table": DataTable}
        self._update_graph_type_options()
        self.layout = pn.Column(
            pn.Row(self.plot_type_select),
            self.save_card,
            self.fit_card,
        )

    def _update_graph_type_options(self):
        self.plot_type_select.options = list(self.graph_types.keys())
        if "Data Table" in self.graph_types:
            self.plot_type_select.value = "Data Table"

    def process(self):
        self.refresh_graph = True
        super().process()

    @pn.depends("data_out", "plot_type_select.value", "refresh_graph")
    def plot_panel(self):
        self.refresh_graph = False
        if self.data_out is None or not isinstance(self.data_out, xr.Dataset):
            return "*No data loaded.*"

        return pn.pane.HTML(self.data_out._repr_html_(), sizing_mode="stretch_width")

    def fit_axis_options(self):
        return []

    def get_plot(self):
        return self.plot_panel()
