"""PlotNode base class with fit management and HTML/PNG save."""

import asyncio
import copy
import importlib
import inspect
import json
import logging
from pathlib import Path
from typing import Optional, Union

import numpy as np
import panel as pn
import param
import ruamel.yaml
from panel.widgets import RadioButtonGroup as RBG

from ..nodes import Node, Data

logger = logging.getLogger(__name__)


class PlotNode(Node):
    """Base class for plot nodes with fit management and save capability.

    Each PlotNode receives data_in from the pipeline output and
    renders a visualization with optional fit overlays.
    """

    FITS = None
    refresh_graph = param.Parameter(None)

    @staticmethod
    def load_fits_from_config(config_fits: Optional[list[str]] = None):
        if config_fits is None:
            yaml = ruamel.yaml.YAML()
            cwd = Path.cwd()
            config_path = cwd / "autoplotConfig.yml"
            if not config_path.exists():
                raise FileNotFoundError(
                    f"Could not find config file at {config_path}. "
                    "Please add autoplotConfig.yml wherever you are running autoplot."
                )
            raw_config = yaml.load(config_path)
            config_fits = raw_config.get("fits", [])

        PlotNode.FITS = {}
        for ff in config_fits:
            modname = str(ff).rsplit(".", 1)
            mod = modname[0]
            try:
                module = importlib.import_module(mod)
                name = modname[1]
                PlotNode.FITS[name] = getattr(module, name)
            except Exception as e:
                msg = (
                    f"Could not access Class {modname[1]} from module {mod}. "
                    f"Exception: {e}"
                )
                logger.error(msg)

    def __init__(self, path=None, *args, **kwargs):
        self.path = path

        if PlotNode.FITS is None:
            self.load_fits_from_config()

        self.fit_dict: dict = {}

        if path in (".", "", None):
            self.fit_data_path = None
        else:
            _dir = Path(path).parent
            self.fit_data_path = _dir.joinpath("fit_data.json")

        self.fit_result = None
        self._fit_axis_options = []

        self.fit_inputs = None
        self.save_fit_button = None
        self.reguess_fit_button = None
        self.model_fit_button = None
        self.refit_button = None
        self.fit_box = None

        self.refresh_graph = True

        self.graph_types = {"None": None}
        self.plot_type_select = RBG(
            options=list(self.graph_types.keys()),
            value="None",
            name="View as",
        )
        self._plot_obj = None

        super().__init__(*args, **kwargs)

        fit_options = list(PlotNode.FITS.keys()) if PlotNode.FITS else []
        fit_options.append("None")
        self.fit_button = pn.widgets.MenuButton(
            name="Fit", items=fit_options, button_type="success", width=100
        )
        self.fit_button.on_click(self.set_fit_box)

        self.select_fit_axis = pn.widgets.Select(
            name="Fit Axis",
            options=self._fit_axis_options or [],
        )
        self.select_fit_axis.param.watch(self.set_fit_box, "value")

        self.fit_layout = pn.Column(
            pn.Row(self.fit_button, self.select_fit_axis),
        )

        self.html_button = pn.widgets.Button(
            name="Make HTML", align="end", button_type="default", disabled=True
        )
        self.html_button.on_click(self.save_html)

        self.png_button = pn.widgets.Button(
            name="Make PNG", align="end", button_type="default", disabled=True
        )
        self.png_button.on_click(self.save_png)

        self.save_card = pn.Card(
            pn.Row(self.html_button, self.png_button),
            title="Save",
            collapsed=True,
        )

        self.fit_card = pn.Card(
            self.fit_layout,
            title="Fit",
            collapsed=True,
        )

        self.layout = pn.Column(
            pn.Row(self.plot_type_select),
            self.save_card,
            self.fit_card,
            self.plot_panel,
        )

    @pn.depends("data_out", "plot_type_select.value", "refresh_graph")
    def plot_panel(self):
        return pn.pane.Markdown("*No valid options chosen.*")

    def get_plot(self):
        return self.plot_panel()

    def get_fit_panel(self):
        return self.fit_layout

    def fit_axis_options(self) -> list:
        return []

    def process(self):
        self.data_out = self.data_in.copy(deep=False) if self.data_in is not None else None
        self._fit_axis_options = self.fit_axis_options()
        if list(self.select_fit_axis.options) != self._fit_axis_options:
            self.select_fit_axis = pn.widgets.Select(
                name="Fit Axis",
                options=self._fit_axis_options,
            )
            self.select_fit_axis.param.watch(self.set_fit_box, "value")
            self.fit_layout[0] = pn.Row(self.fit_button, self.select_fit_axis)
        for axis in self.fit_axis_options():
            if axis in self.fit_dict:
                func_name = self.fit_dict[axis].get("fit_function", "")
                saved_args = self.get_values(axis)
                if func_name in (PlotNode.FITS or {}):
                    self.update_dataset_by_fit_and_axis(
                        PlotNode.FITS[func_name], saved_args, axis, True
                    )
                elif func_name:
                    msg = (
                        f"Axis {axis} has a fit of type {func_name} saved, "
                        "which you don't have access to."
                    )
                    logger.warning(msg)
                    pn.state.notifications.error(msg, duration=0)

    def set_fit_box(self, *events, fitted=None):
        if self.select_fit_axis.value is None:
            pn.state.notifications.error(
                "Please select a Fit Axis first.", duration=3000)
            return
        if fitted is None:
            fitted = False
            if self.select_fit_axis.value in self.fit_dict:
                if "start_params" not in self.fit_dict[self.select_fit_axis.value]:
                    fitted = True
        if self.select_fit_axis.value in self.fit_dict:
            if "start_params" in self.fit_dict[self.select_fit_axis.value]:
                del self.fit_dict[self.select_fit_axis.value]["start_params"]
        self.set_fit_box_helper(
            self.fit_button.clicked != "None",
            self.fit_button.clicked,
            fitted=fitted,
        )

    def set_fit_box_helper(self, new_box: bool, fit_func_name: str,
                           fitted: bool = False):
        if self.fit_box is None:
            if not new_box:
                return
            self.fit_box = self.add_fit_box(fit_func_name, fitted=fitted)
        else:
            self.remove_fit_box()
            if new_box:
                self.fit_box = self.add_fit_box(fit_func_name, fitted=fitted)

    def remove_fit_box(self):
        fit_box = self.fit_layout.objects[len(self.fit_layout.objects) - 1]
        if hasattr(fit_box, "objects"):
            for obj in fit_box.objects:
                if hasattr(obj, "param") and hasattr(obj.param, "_watchers"):
                    watchers = list(obj.param._watchers.get("value", []))
                    for w in watchers:
                        obj.param.unwatch(w)

        no_fit_objects = self.fit_layout.objects[:-1]
        self.fit_layout.objects = no_fit_objects
        self.fit_inputs = None
        self.save_fit_button = None
        self.fit_box = None

    def add_fit_box(self, selected=None, fitted=False):
        if selected is None:
            selected = self.fit_button.clicked
        if self.select_fit_axis.value in self.fit_dict:
            if (self.fit_dict[self.select_fit_axis.value].get("fit_function")
                    != selected):
                fitted = False

        objs = [
            pn.widgets.StaticText(
                name="FITTED" if fitted else "Setup",
                value=selected,
                align="center",
            )
        ]
        fit_class = PlotNode.FITS[selected]
        saved_args = self.get_arguments()
        sig_params = list(inspect.signature(fit_class.model).parameters.keys())
        for var in sig_params:
            if var == "coordinates":
                continue
            name = var
            if fitted:
                stderr = (
                    self.fit_dict[self.select_fit_axis.value]
                    .get("params", {})
                    .get(var, {})
                    .get("stderr", "?")
                )
                objs.append(
                    pn.widgets.StaticText(
                        name=var,
                        value=(f"{saved_args.get(var, '?')}"
                               f" +/- {stderr}"),
                        align="start",
                    )
                )
            else:
                objs.append(
                    pn.widgets.FloatInput(
                        name=name,
                        value=saved_args.get(var, 0),
                    )
                )
            objs[-1].param.watch(self.update_fit_args, "value")

        self.reguess_fit_button = pn.widgets.Button(
            name="Reguess", align="center", button_type="default", disabled=False
        )
        self.reguess_fit_button.on_click(self.reguess_fit)

        self.save_fit_button = pn.widgets.Button(
            name="Save", align="center", button_type="success", disabled=False
        )
        self.save_fit_button.on_click(self.save_fit)

        self.model_fit_button = pn.widgets.Button(
            name="Run Fit", align="center", button_type="default", disabled=False
        )
        self.model_fit_button.on_click(self.model_fit)

        self.refit_button = pn.widgets.Button(
            name="Refit", align="center", button_type="default", disabled=False
        )
        self.refit_button.on_click(self.set_fit_box)

        if fitted:
            objs.append(pn.Row(self.save_fit_button, self.refit_button))
        else:
            objs.append(pn.Row(self.model_fit_button, self.reguess_fit_button))

        self.fit_inputs = pn.WidgetBox(name=selected, objects=objs)
        self.fit_layout.append(
            pn.Row(objects=[self.fit_inputs], name="fit_box"))

        if self.select_fit_axis.value not in self.fit_dict:
            self.fit_dict[self.select_fit_axis.value] = {
                "fit_function": self.fit_button.clicked,
                "start_params": saved_args,
                "params": {},
            }
        elif "start_params" not in self.fit_dict[self.select_fit_axis.value]:
            self.fit_dict[self.select_fit_axis.value]["start_params"] = saved_args

        self.fit_dict[self.select_fit_axis.value]["fit_function"] = (
            self.fit_button.clicked)
        self.update_fit_args(None)
        return self.fit_inputs

    def save_fit(self, *events):
        from labcore.data.ddh5_xr import NumpyEncoder
        from labcore.utils.misc import add_end_number_to_repeated_file

        params_dict = self.fit_result.params_to_dict()
        params_path = add_end_number_to_repeated_file(
            Path(self.path).parent.joinpath("fit_params.json")
        )
        result_path = add_end_number_to_repeated_file(
            Path(self.path).parent.joinpath("fit_result.txt")
        )

        with open(params_path, "w") as outfile:
            json.dump(params_dict, outfile, cls=NumpyEncoder)

        fit_report = self.fit_result.lmfit_result.fit_report()
        with open(result_path, "w") as outfile:
            outfile.write(fit_report)

    def reguess_fit(self, event):
        store_params = self.fit_dict[self.select_fit_axis.value].copy()
        del self.fit_dict[self.select_fit_axis.value]
        self.set_fit_box_helper(True, store_params["fit_function"])
        self.fit_dict[self.select_fit_axis.value]["params"] = store_params.get(
            "params", {})
        self.refresh_graph = True

    def model_fit(self, *events):
        from labcore.analysis.fit import Fit

        fit_class = PlotNode.FITS[self.fit_button.clicked]
        data_key = self.select_fit_axis.value

        np_data = [self.data_out[var].values for var in self.data_out.coords]
        coord_dim = self.indep_dims()
        coords = np_data[0] if coord_dim < 2 else np_data[0:2]
        vals = self.data_out.data_vars[data_key].to_numpy()

        fit = fit_class(coords, vals)
        run_kwargs = self.fit_dict[self.select_fit_axis.value].get(
            "start_params", {})
        self.fit_result = fit.run(**run_kwargs)

        params_dict = self.fit_result.params_to_dict()
        fit_params = {k: v["value"] for k, v in params_dict.items()}

        name = self.select_fit_axis.value
        self.update_dataset_by_fit_and_axis(fit_class, fit_params, name, saved=True)
        self.fit_dict[self.select_fit_axis.value]["params"] = params_dict

        self.set_fit_box(None, fitted=True)
        self.refresh_graph = True

    def get_arguments(self):
        axis = self.select_fit_axis.value
        fit_name = self.fit_button.clicked
        if (axis in self.fit_dict
                and self.fit_dict[axis].get("fit_function") == fit_name):
            return self.get_values(axis)
        return self.get_ansatz()

    def get_ansatz(self):
        fit_class = PlotNode.FITS[self.fit_button.clicked]
        data_key = self.select_fit_axis.value
        np_data = [self.data_out[var].values for var in self.data_out.coords]
        coord_dim = self.indep_dims()
        coords = np_data[0] if coord_dim < 2 else np_data[0:2]
        return fit_class.guess(
            coords, self.data_out.data_vars[data_key].to_numpy()
        )

    def update_fit_args(self, event):
        if self.select_fit_axis.value not in self.fit_dict:
            self.fit_dict[self.select_fit_axis.value] = {
                "fit_function": self.fit_button.clicked,
                "start_params": {},
            }
        for i, obj in enumerate(self.fit_inputs.objects):
            if isinstance(obj, pn.widgets.FloatInput):
                self.fit_dict[self.select_fit_axis.value]["start_params"][
                    obj.name
                ] = self.fit_inputs[i].value

        fit_class = PlotNode.FITS[self.fit_button.clicked]
        params = self.fit_dict[self.select_fit_axis.value]["start_params"]
        self.update_dataset_by_fit_and_axis(
            fit_class, params, self.select_fit_axis.value
        )
        self.refresh_graph = True

    def update_dataset_by_fit_and_axis(self, fit_class,
                                       model_args: dict,
                                       model_axis_name: str,
                                       saved: bool = False):
        np_data = [self.data_out[var].values for var in self.data_out.coords]
        coord_dim = self.indep_dims()
        coords = np_data[0] if coord_dim < 2 else np_data[0:2]

        fit_data = fit_class.model(coords, **model_args)
        fit_name = model_axis_name + "_fit"
        fit_name_temp = model_axis_name + "_fit*"

        if not saved:
            if fit_name in self.data_out:
                del self.data_out[fit_name]
            fit_name = fit_name_temp
        else:
            if fit_name_temp in self.data_out:
                del self.data_out[fit_name_temp]

        self.update_dataset_by_data(fit_data, fit_name)

    def update_dataset_by_data(self, fit_data: np.ndarray, name: str):
        indep, _ = self.data_dims(self.data_out)
        self.data_out[name] = (indep, fit_data)

    def get_data_fit_names(self, axis_name, omit_axes=None):
        if omit_axes is None:
            omit_axes = ["Magnitude", "Phase"]

        if isinstance(axis_name, list):
            ret = []
            for name in axis_name:
                ret = ret + self.get_data_fit_names(name, omit_axes)
            return ret

        if axis_name in omit_axes:
            return []

        ret = [axis_name]
        fit_name = axis_name + "_fit"
        if fit_name + "*" in self.data_out.data_vars:
            ret.append(fit_name + "*")
        elif fit_name in self.data_out.data_vars:
            ret.append(fit_name)
        return ret

    def get_values(self, axis: str):
        if "params" not in self.fit_dict.get(axis, {}):
            return self.fit_dict.get(axis, {}).get("start_params", {})
        _dict = self.fit_dict[axis]["params"]
        return {k: v["value"] for k, v in _dict.items()}

    def indep_dims(self) -> int:
        indep, _ = self.data_dims(self.data_out)
        if isinstance(indep, list):
            return len(indep)
        if indep is not None:
            return 1
        return 0

    def toggle_save_buttons(self):
        if self.fit_data_path is None:
            return
        self.html_button.disabled = False
        self.png_button.disabled = False

    def save_html(self, *events):
        import hvplot
        from labcore.utils.misc import add_end_number_to_repeated_file

        plot = self.get_plot()
        try:
            file_name = add_end_number_to_repeated_file(
                Path(self.path).parent / f"{Path(self.path).parent.name}.html"
            )
            hvplot.save(plot, str(file_name))
        except Exception as e:
            logger.error("Could not save HTML: %s", e)

    def save_png(self, *events):
        from bokeh.io.export import export_png
        from labcore.utils.misc import add_end_number_to_repeated_file

        try:
            p = self.get_plot()
            if hasattr(p, "object") and hasattr(p.object, "traverse"):
                hv_obj = p.object
            elif hasattr(p, "traverse"):
                hv_obj = p
            else:
                logger.warning(f"Skipping object of type {type(p)}")
                return

            import holoviews as hv
            bokeh_plot = hv.render(hv_obj)
            path = add_end_number_to_repeated_file(
                Path(self.path).parent.joinpath(
                    f"{Path(self.path).parent.name}.png"
                )
            )
            export_png(bokeh_plot, filename=str(path))
        except Exception as e:
            logger.error("Could not save PNG: %s", e)

    @pn.depends("data_out")
    def plot(self):
        return [
            labeled_widget(self.plot_type_select),
            self.plot_panel,
        ]

    @pn.depends("plot_type_select.value", watch=True)
    def _update_graph_types(self):
        pass


def plot_df_as_2d(df, x, y, dim_labels=None, graph_axes=None):
    import numpy as np

    if graph_axes is None:
        graph_axes = []
    if dim_labels is None:
        dim_labels = {}

    indeps, deps = Node.data_dims(df)
    if graph_axes:
        deps = graph_axes

    if x in (indeps or []) and y in (indeps or []):
        return pn.Column(
            *[
                df.hvplot.heatmap(
                    x=x, y=y, C=d,
                    xlabel=dim_labels.get(x, x),
                    ylabel=dim_labels.get(y, y),
                    clabel=f"Mean {dim_labels.get(d, d)}",
                ).aggregate(function=np.mean)
                for d in (deps or [])
            ]
        )
    elif x in (deps or []) + (indeps or []) and y in (deps or []):
        return df.hvplot.scatter(
            x=x, y=y,
            xlabel=dim_labels.get(x, x),
            ylabel=dim_labels.get(y, y),
        )
    return "*that's currently not supported :(*"


def plot_xr_as_2d(ds, x, y, dim_labels=None, graph_axes=None):
    if graph_axes is None:
        graph_axes = []
    if dim_labels is None:
        dim_labels = {}

    if ds is None:
        return "Nothing to plot."

    indeps, deps = Node.data_dims(ds)
    plot = None

    if graph_axes:
        deps = graph_axes

    if x + "_fit" in ds:
        from labcore.analysis.fit import plot_ds_2d_with_fit
        return plot_ds_2d_with_fit(ds, dim_labels.get(x, x), x, y)

    if x in (indeps or []) and y in (indeps or []):
        for d in (deps or []):
            if plot is None:
                plot = ds.get(d).hvplot.quadmesh(
                    x=x, y=y,
                    xlabel=dim_labels.get(x, x),
                    ylabel=dim_labels.get(y, y),
                    clabel=f"Mean {dim_labels.get(d, d)}",
                )
            else:
                plot += ds.get(d).hvplot.quadmesh(
                    x=x, y=y,
                    xlabel=dim_labels.get(x, x),
                    ylabel=dim_labels.get(y, y),
                    clabel=f"Mean {dim_labels.get(d, d)}",
                )
        try:
            return plot.cols(1)
        except AttributeError:
            return "*Not a valid plot* Attribute Error occurred"
    return "*Not a valid plot*"


def labeled_widget(w, lbl=None):
    from ..nodes import labeled_widget as _lw
    return _lw(w, lbl)
