"""Tests for nodes.py — Node, Pipeline, preprocessor nodes."""

import numpy as np
import xarray as xr
import pandas as pd
import panel as pn
import pytest

from autoplot.nodes import (
    Node,
    Pipeline,
    SplitComplexNode,
    AverageNode,
    RotateIQNode,
    XYSelect,
    WhereFilterNode,
)


class TestNode:
    def test_identity_process(self):
        n = Node()
        n.data_in = 42
        n.process()
        assert n.data_out == 42

    @pytest.mark.parametrize("data,expected", [
        (None, "No data"),
    ])
    def test_render_data_none(self, data, expected):
        result = Node.render_data(data)
        assert result == expected

    def test_render_data_dataframe(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        result = Node.render_data(df)
        assert isinstance(result, pn.pane.DataFrame)

    def test_render_data_dataset(self):
        ds = xr.Dataset({"x": ("t", [1, 2, 3])})
        result = Node.render_data(ds)
        assert isinstance(result, xr.Dataset)

    def test_data_dims(self):
        ds = xr.Dataset(
            {"I": (["x", "rep"], np.zeros((2, 2))), "Q": (["x", "rep"], np.zeros((2, 2)))},
            coords={"x": [0, 1], "rep": [0, 1]},
        )
        indep, dep = Node.data_dims(ds)
        assert "x" in indep
        assert "rep" in indep
        assert "I" in dep
        assert "Q" in dep


class TestPipeline:
    def test_chains_nodes(self):
        class AddOne(Node):
            def process(self):
                self.data_out = (self.data_in or 0) + 1

        pipeline = Pipeline([AddOne(), AddOne(), AddOne()])
        pipeline.run()
        assert pipeline.data_out == 3

    def test_handles_none_input(self):
        class IdentityNode(Node):
            def process(self):
                self.data_out = self.data_in

        pipeline = Pipeline([IdentityNode()])
        pipeline.run()
        assert pipeline.data_out is None


class TestSplitComplexNode:
    def test_splits_complex_data(self):
        x = np.linspace(0, 1, 5)
        real = np.cos(x)
        imag = np.sin(x)
        ds = xr.Dataset({
            "I": (["x", "rep"],
                  np.array([real, real * 1.1]).T +
                  1j * np.array([imag, imag * 1.1]).T),
        }, coords={"x": x, "rep": [0, 1]})

        node = SplitComplexNode()
        node.data_in = ds
        node.process()

        assert "I_Re" in node.data_out.data_vars
        assert "I_Im" in node.data_out.data_vars
        assert "I" not in node.data_out.data_vars


class TestAverageNode:
    def test_averages_dimension(self):
        ds = xr.Dataset({
            "I": (["x", "rep"], np.arange(6).reshape(3, 2).astype(float)),
        }, coords={"x": [0, 1, 2], "rep": [0, 1]})

        node = AverageNode(enabled=True, dim_name="rep")
        node.data_in = ds
        node.process()

        assert "rep" not in node.data_out.dims
        assert "x" in node.data_out.dims

    def test_disabled_passes_through(self):
        ds = xr.Dataset({"I": (["rep"], [1, 2])}, coords={"rep": [0, 1]})
        node = AverageNode(enabled=False)
        node.data_in = ds
        node.process()
        assert "rep" in node.data_out.dims


class TestRotateIQNode:
    def test_rotates_iq_data(self):
        ds = xr.Dataset({
            "I_Re": (["t"], [1.0, 2.0, 3.0]),
            "I_Im": (["t"], [0.0, 0.0, 0.0]),
        }, coords={"t": [0, 1, 2]})

        node = RotateIQNode(enabled=True, angle=90)
        node.data_in = ds
        node.process()

        out = node.data_out
        assert np.allclose(out["I_Re"].values, [0, 0, 0], atol=1e-10)
        assert np.allclose(out["I_Im"].values, [1, 2, 3], atol=1e-10)

    def test_disabled_passes_through(self):
        ds = xr.Dataset({
            "I_Re": (["t"], [1.0, 2.0]), "I_Im": (["t"], [0.5, 1.0]),
        }, coords={"t": [0, 1]})

        node = RotateIQNode(enabled=False)
        node.data_in = ds
        node.process()
        assert node.data_out["I_Re"].values[0] == 1.0


class TestWhereFilterNode:
    def test_single_where_xr(self):
        ds = xr.Dataset({
            "I": (["time"], [1.0, 2.0, 3.0, 4.0, 5.0]),
        }, coords={"time": [0.0, 0.5, 1.0, 1.5, 2.0]})

        node = WhereFilterNode(enabled=True)
        node._conditions = [{
            "coord_select": type("S", (), {"value": "time"})(),
            "op_select": type("S", (), {"value": ">"})(),
            "val_input": type("S", (), {"value": 0.6})(),
        }]
        node.data_in = ds
        node.process()

        out = node.data_out
        assert len(out.time) == 3
        assert np.allclose(out.time.values, [1.0, 1.5, 2.0])

    def test_chained_where_xr(self):
        ds = xr.Dataset({
            "I": (["time"], [1.0, 2.0, 3.0, 4.0, 5.0]),
        }, coords={"time": [0.0, 0.5, 1.0, 1.5, 2.0]})

        node = WhereFilterNode(enabled=True)
        node._conditions = [
            {"coord_select": type("S", (), {"value": "time"})(),
             "op_select": type("S", (), {"value": ">"})(),
             "val_input": type("S", (), {"value": 0.6})()},
            {"coord_select": type("S", (), {"value": "time"})(),
             "op_select": type("S", (), {"value": "<"})(),
             "val_input": type("S", (), {"value": 1.8})()},
        ]
        node.data_in = ds
        node.process()

        out = node.data_out
        assert len(out.time) == 2
        assert np.allclose(out.time.values, [1.0, 1.5])

    def test_disabled_passes_through(self):
        ds = xr.Dataset({
            "I": (["time"], [1.0, 2.0, 3.0]),
        }, coords={"time": [0.0, 1.0, 2.0]})

        node = WhereFilterNode(enabled=False)
        node._conditions = [{
            "coord_select": type("S", (), {"value": "time"})(),
            "op_select": type("S", (), {"value": ">"})(),
            "val_input": type("S", (), {"value": 0.5})(),
        }]
        node.data_in = ds
        node.process()
        assert len(node.data_out.time) == 3

    def test_no_conditions_passes_through(self):
        ds = xr.Dataset({
            "I": (["time"], [1.0, 2.0, 3.0]),
        }, coords={"time": [0.0, 1.0, 2.0]})

        node = WhereFilterNode(enabled=True)
        node._conditions = []
        node.data_in = ds
        node.process()
        assert len(node.data_out.time) == 3

    def test_none_data_in(self):
        node = WhereFilterNode()
        node.data_in = None
        node.process()
        assert node.data_out is None

