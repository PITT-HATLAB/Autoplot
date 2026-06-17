"""MagnitudePhasePlot: magnitude and phase visualization for complex S-parameter data."""

import numpy as np
import panel as pn
import param
import xarray as xr

from ..nodes import Node, XYSelect
from .base import PlotNode, plot_xr_as_2d


class MagnitudePhasePlot(PlotNode):
    """Plot magnitude and phase (including unwrapped/delay-corrected)."""

    def __init__(self, *args, **kwargs):
        self.xy_select = XYSelect()
        self._old_indep = []

        super().__init__(*args, **kwargs)

        self.graph_types = {
            "None": None,
            "Magnitude & Phase": MagnitudePhasePlot,
        }
        self._update_graph_type_options()

    def _update_graph_type_options(self):
        self.plot_type_select.options = list(self.graph_types.keys())
        if "Magnitude & Phase" in self.graph_types:
            self.plot_type_select.value = "Magnitude & Phase"

    def process(self):

        assert isinstance(
            self.data_in, xr.Dataset
        ), "MagnitudePhasePlot needs an xr.Dataset."

        indep, dep = self.data_dims(self.data_in)
        keylist = list(self.data_in.data_vars.keys())
        real = self.data_in.variables[keylist[0]]
        imaginary = self.data_in.variables[keylist[1]]
        complex_data = real + 1j * imaginary

        magnitude = np.abs(complex_data).T
        phase_rad = np.angle(complex_data)
        phase = np.rad2deg(phase_rad).T

        freq_dim = indep[0] if isinstance(indep, list) and indep else indep
        phase_rad_values = (
            phase_rad.values
            if hasattr(phase_rad, "values")
            else phase_rad
        )
        phase_unwrap_rad = np.unwrap(
            phase_rad_values, axis=real.get_axis_num(freq_dim)
        )

        phase_coords = {dim: self.data_in.coords[dim] for dim in real.dims}
        phase_unwrap = xr.DataArray(
            phase_unwrap_rad * 180 / np.pi,
            coords=phase_coords,
            dims=real.dims,
        ).T

        try:
            freq = self.data_in.coords[freq_dim]
            mean_phase = phase_unwrap_rad
            if np.ndim(phase_rad_values) > 1:
                mean_phase = np.nanmean(
                    phase_unwrap_rad,
                    axis=tuple(
                        i for i, d in enumerate(real.dims)
                        if d != freq_dim
                    ),
                )
            coeffs = np.polyfit(freq.values, mean_phase, 1)
            tau = -coeffs[0] / (2 * np.pi)
            phase_unwrap_sub = xr.DataArray(
                (phase_unwrap_rad + 2 * np.pi * tau * freq.values)
                * 180 / np.pi,
                coords=phase_coords,
                dims=real.dims,
            ).T
        except Exception:
            phase_unwrap_sub = phase_unwrap.copy(deep=True)

        phase_unwrap = phase_unwrap - phase_unwrap.mean()
        phase_unwrap_sub = phase_unwrap_sub - phase_unwrap_sub.mean()

        super().process()

        self.data_out["Magnitude"] = (indep, magnitude)
        self.data_out["Phase"] = (indep, phase)
        self.data_out["Phase_unwrap"] = phase_unwrap
        self.data_out["Phase_unwrap_sub"] = phase_unwrap_sub

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

        else:
            if y in ["None", None]:
                plot_m = self.data_out.hvplot.line(
                    x=x,
                    xlabel=self.dim_label(x),
                    y=self.get_data_fit_names("Magnitude"),
                    shared_axes=False,
                )
                phase_plot = self.data_out.hvplot.line(
                    x=x,
                    xlabel=self.dim_label(x),
                    y=self.get_data_fit_names("Phase"),
                    shared_axes=False,
                )
                phase_unwrap_plot = self.data_out.hvplot.line(
                    x=x,
                    xlabel=self.dim_label(x),
                    y="Phase_unwrap",
                    shared_axes=False,
                )
                phase_unwrap_sub_plot = self.data_out.hvplot.line(
                    x=x,
                    xlabel=self.dim_label(x),
                    y="Phase_unwrap_sub",
                    shared_axes=False,
                )
                plot = pn.Column(
                    plot_m,
                    phase_plot,
                    phase_unwrap_plot,
                    phase_unwrap_sub_plot,
                )
            else:
                plot = plot_xr_as_2d(
                    self.data_out, x, y,
                    dim_labels=self.dim_labels(),
                    graph_axes=self.get_data_fit_names(
                        self.fit_axis_options(),
                    ),
                )
                try:
                    plot = plot.cols(2)
                except Exception:
                    pass

        return plot

    def fit_axis_options(self):
        return ["Magnitude", "Phase"]

    def get_data_fit_names(self, axis_name, omit_axes=None):
        if omit_axes is None:
            omit_axes = []
        return PlotNode.get_data_fit_names(self, axis_name, omit_axes=omit_axes)
