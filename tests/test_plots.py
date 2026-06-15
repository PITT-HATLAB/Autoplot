"""Tests for plot nodes."""

import numpy as np
import xarray as xr
import pytest

from autoplot.nodes import Node
from autoplot.plots.value import ValuePlot
from autoplot.plots.complex_hist import ComplexHist
from autoplot.plots.magnitude_phase import MagnitudePhasePlot


class TestValuePlot:
    def test_fit_axis_options(self):
        ds = xr.Dataset({
            "I": (["x"], np.array([1.0, 2.0, 3.0])),
            "Q": (["x"], np.array([4.0, 5.0, 6.0])),
        }, coords={"x": [0, 1, 2]})

        plot = ValuePlot(data_in=ds)
        plot.process()
        opts = plot.fit_axis_options()
        assert "I" in opts
        assert "Q" in opts


class TestComplexHist:
    def test_complex_dependents(self):
        ds = xr.Dataset({
            "I_Re": (["x"], np.array([1.0, 2.0])),
            "I_Im": (["x"], np.array([0.5, 1.0])),
            "Q_Re": (["x"], np.array([3.0, 4.0])),
            "Q_Im": (["x"], np.array([1.5, 2.0])),
        }, coords={"x": [0, 1]})

        plot = ComplexHist(data_in=ds)
        plot.process()
        deps = Node.complex_dependents(plot.data_out)
        assert "I" in deps
        assert "Q" in deps
        assert deps["I"] == {"real": "I_Re", "imag": "I_Im"}


class TestMagnitudePhasePlot:
    def test_process_adds_magnitude_phase(self):
        x = np.linspace(0, 10, 5)
        ds = xr.Dataset({
            "I_Re": (["freq"], np.cos(x)),
            "I_Im": (["freq"], np.sin(x)),
        }, coords={"freq": x})

        plot = MagnitudePhasePlot(data_in=ds)
        plot.process()

        out = plot.data_out
        assert "Magnitude" in out.data_vars
        assert "Phase" in out.data_vars
        assert "Phase_unwrap" in out.data_vars
        assert "Phase_unwrap_sub" in out.data_vars
