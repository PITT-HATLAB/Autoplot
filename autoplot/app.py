"""Data selection browser and app assembly for autoplot."""

import asyncio
import json
import logging
import re
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import nest_asyncio
nest_asyncio.apply()

import pandas as pd
import panel as pn
import param
from panel.widgets import Select
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from labcore.data.ddh5_xr import find_data, timestamp_from_path, ddh5_schema

from .nodes import Pipeline
from .notify import notify_error, notify_warning, notify_info
from .styles import selector_stylesheet

logger = logging.getLogger(__name__)

pn.extension("floatpanel")

DATAFILE = "data.ddh5"

SYM = {
    "complete": "\u2705",
    "star": "\U0001f601",
    "bad": "\U0001f62d",
    "trash": "\u274c",
    "poop": "\U0001f4a9",
}


class Handler(FileSystemEventHandler):
    DEBOUNCE_S = 0.5

    def __init__(self, update_callback):
        self.update_callback = update_callback
        self._last_fire = 0.0

    def on_created(self, event):
        if not event.is_directory:
            file_type = Path(event.src_path).suffix
            if file_type == ".ddh5":
                now = time.monotonic()
                if now - self._last_fire >= self.DEBOUNCE_S:
                    self._last_fire = now
                    self.update_callback(event)


class DataSelect(pn.viewable.Viewer):
    """File browser widget for selecting datasets organized by date.

    Features:
    - Date-based grouping with checkboxes
    - Dataset dropdown with search filtering
    - Tag buttons (star, trash, bad, error)
    - Image/PDF feed for attached screenshots
    - DataFrame schema preview (async)
    - Notes.md editor (FloatPanel)
    - JSON file browser (FloatPanel)
    - Watchdog auto-refresh on new data
    """

    selected_path = param.Parameter(None)
    search_term = param.Parameter(None)
    group_options = param.Parameter(None)

    def __init__(self, data_root, size=15):
        super().__init__()

        self.size = size
        self.data_root = data_root
        self.data_sets = self.group_data(find_data(root=data_root))
        self._search_regex = re.compile(".*")

        self.layout = pn.Column()

        # Search bar
        self.search_label = pn.widgets.StaticText(
            value="Search:", align="center")
        self.text_input = pn.widgets.TextInput(
            placeholder="Enter a search term here...")

        # Refresh button
        self.refresh_button = pn.widgets.Button(
            name="\U0001f504 Refresh", width=100, button_type="default")
        self.refresh_button.on_click(self._on_refresh_clicked)

        # Tag buttons
        self.star_button = pn.widgets.Button(
            name="\U0001f601 Star", width=100, button_type="default")
        self.star_button.on_click(self._on_star_clicked)

        self.trash_button = pn.widgets.Button(
            name="\u274c Trash", width=100, button_type="default")
        self.trash_button.on_click(self._on_trash_clicked)

        self.bad_button = pn.widgets.Button(
            name="\U0001f62d Bad", width=100, button_type="default")
        self.bad_button.on_click(self._on_bad_clicked)

        self.poop_button = pn.widgets.Button(
            name="\U0001f4a9 Error", width=100, button_type="default")
        self.poop_button.on_click(self._on_poop_clicked)

        self.layout.append(
            pn.Row(
                self.search_label, self.text_input, self.refresh_button,
                self.star_button, self.trash_button,
                self.bad_button, self.poop_button,
            )
        )

        # Current search display
        self.typed_value = pn.widgets.StaticText(
            stylesheets=[selector_stylesheet],
            css_classes=["ttlabel"],
        )
        self.layout.append(self.text_input_repeater)

        self.image_feed_width = 400
        self.feed_scroll_width = 40

        # Date selector
        self._group_select_widget = pn.widgets.CheckBoxGroup(
            name="Date",
            width=200 - self.feed_scroll_width,
            stylesheets=[selector_stylesheet],
        )
        self._group_select_feed = pn.layout.Feed(
            objects=[self._group_select_widget],
            height=(self.size - 1) * 20,
            width=200,
        )
        self._group_select = pn.Column(
            pn.widgets.StaticText(
                stylesheets=[selector_stylesheet],
                css_classes=["ttlabel"],
                value="Date",
            ),
            self._group_select_feed,
        )

        # Dataset selector
        self._data_select_widget = Select(
            name="Data set",
            size=self.size,
            width=800,
            stylesheets=[selector_stylesheet],
        )

        # Image feed
        self.data_images_feed = pn.layout.Feed(None, sizing_mode="fixed")
        self.data_info = pn.pane.DataFrame(None)

        self.layout.append(
            pn.Row(
                self._group_select,
                self.data_select,
                self.data_info,
                self.data_images_feed,
            )
        )

        # Info label
        self.lbl = pn.widgets.StaticText(
            stylesheets=[selector_stylesheet],
            css_classes=["ttlabel"],
        )

        # FloatPanel management
        self._active_float_panels = []
        self._float_panel_container = pn.Column(
            sizing_mode="fixed", height=0, width=0, margin=0
        )

        self.layout.append(pn.Row(self.info_panel))
        self.layout.append(self._float_panel_container)

        # Initialize date options
        opts = OrderedDict()
        for k in sorted(self.data_sets.keys())[::-1]:
            lbl = self.date2label(k) + f" [{len(self.data_sets[k])}]"
            opts[lbl] = k
        self._group_select_widget.options = opts

        # Watchdog
        self.DIRECTORY_TO_WATCH = str(data_root)
        self.observer = Observer()
        self.handler = Handler(self.update_group_options)
        self.start()

    def start(self):
        try:
            self.observer.schedule(
                self.handler, self.DIRECTORY_TO_WATCH, recursive=True
            )
            self.observer.start()
        except Exception as e:
            notify_warning(f"Watchdog could not start: {e}")

    @staticmethod
    def date2label(date_tuple):
        return "-".join(str(k) for k in date_tuple)

    @staticmethod
    def label2date(label):
        return tuple(int(l) for l in label[:10].split("-"))

    @staticmethod
    def group_data(data_list):
        ret = {}
        for path, info in data_list.items():
            ts = timestamp_from_path(path)
            date = (ts.year, ts.month, ts.day)
            if date not in ret:
                ret[date] = {}
            ret[date][path] = (info[0], info[1], ts)
        return ret

    def __panel__(self):
        return self.layout

    @pn.depends("_group_select_widget.value")
    def data_select(self):
        active_search = bool(self.text_input.value_input)
        opts = self.get_data_options(active_search, self._search_regex)

        old_value = self._data_select_widget.value
        self._data_select_widget.options = opts
        if self._data_select_widget.value != old_value:
            self._data_select_widget.value = old_value
        return self._data_select_widget

    def get_data_options(self, active_search=True, r=None):
        if r is None:
            r = re.compile(".*")
        opts = OrderedDict()
        for d in self._group_select_widget.value:
            for dset in sorted(self.data_sets[d].keys())[::-1]:
                dirs, files, ts = self.data_sets[d][dset]
                if active_search and not r.match(str(dset) + " " + str(ts)):
                    continue
                time_str = f"{ts.hour:02d}:{ts.minute:02d}:{ts.second:02d}"
                uuid = f"{dset.stem[18:26]}"
                name = f"{dset.stem[27:]}"
                date_str = f"{ts.date()}"
                lbl = f"{date_str} - {time_str} - {uuid} - {name} "
                for k in ["complete", "star", "bad", "trash", "poop"]:
                    if f"__{k}__.tag" in files:
                        lbl += SYM[k]
                opts[lbl] = dset
        return opts

    @pn.depends("_data_select_widget.value")
    def info_panel(self):
        path = self._data_select_widget.value
        if path is not None:
            abs_path = path.absolute()
            self._close_active_float_panels()
            self.data_images_feed.objects = []
            self.data_info.object = None

            try:
                self.data_images_feed.objects = self._build_feed(abs_path)
                self.data_images_feed.width = (
                    self.image_feed_width + self.feed_scroll_width
                )
            except Exception as e:
                logger.warning("Could not build file feed from %s: %s", abs_path, e)

            asyncio.ensure_future(self._load_data_info_async(abs_path))
        else:
            self._close_active_float_panels()
            self.data_images_feed.objects = []
            self.data_info.object = None

        if isinstance(path, Path):
            display_path = path / DATAFILE
        else:
            display_path = path
        self.lbl.value = f"Path: {display_path}"
        self.selected_path = display_path
        return self.lbl

    async def _load_data_info_async(self, abs_path):
        try:
            loop = asyncio.get_event_loop()
            schema = await loop.run_in_executor(
                None,
                lambda: ddh5_schema(str(abs_path) + "/data", swmr=True),
            )

            current = self._data_select_widget.value
            if current is None or current.absolute() != abs_path:
                return

            dict_for_dataframe = {}
            for name, fi in schema.fields.items():
                depends_on = fi.axes if fi.axes else "Independent"
                dict_for_dataframe[name] = [list(fi.shape), depends_on]

            df = pd.DataFrame.from_dict(
                data=dict_for_dataframe,
                orient="index",
                columns=["Shape", "Depends on"],
            )

            current = self._data_select_widget.value
            if current is None or current.absolute() != abs_path:
                return

            self.data_info.object = df
        except Exception as e:
            logger.warning("Could not load data from %s: %s", abs_path, e)
            current = self._data_select_widget.value
            if current is not None and current.absolute() == abs_path:
                self.data_info.object = f"Error loading data: {e}"

    def _close_active_float_panels(self):
        for fp in self._active_float_panels:
            try:
                self._float_panel_container.remove(fp)
            except Exception:
                pass
        self._active_float_panels = []

    def _build_feed(self, abs_path):
        objects = []
        has_notes_md = False
        try:
            for file in sorted(Path(abs_path).iterdir(), key=lambda p: p.name):
                suffix = file.suffix.lower()
                if suffix == ".png":
                    img = pn.pane.PNG(
                        str(file), sizing_mode="fixed",
                        width=self.image_feed_width,
                    )
                    objects.append(img)
                    objects.append(pn.Spacer(height=img.height))
                elif suffix in (".jpg", ".jpeg"):
                    img = pn.pane.JPG(
                        str(file), sizing_mode="fixed",
                        width=self.image_feed_width,
                    )
                    objects.append(img)
                    objects.append(pn.Spacer(height=img.height))
                elif suffix == ".html":
                    btn = pn.widgets.Button(
                        name=f"Open HTML: {file.name}",
                        width=self.image_feed_width,
                    )
                    btn.on_click(
                        lambda event, f=file: self._open_html_file(f)
                    )
                    objects.append(btn)
                elif file.name.lower() == "notes.md":
                    has_notes_md = True
                    objects.append(self._make_md_control(file))
                elif suffix == ".json":
                    btn = pn.widgets.Button(
                        name=f"Browse JSON: {file.name}",
                        width=self.image_feed_width,
                    )
                    btn.on_click(
                        lambda event, f=file: self._open_json_browser(f)
                    )
                    objects.append(btn)
        except Exception as e:
            logger.warning("Could not iterate directory %s: %s", abs_path, e)

        if not has_notes_md:
            objects.append(self._make_md_control(abs_path / "notes.md"))
        return objects

    def _open_html_file(self, file_path):
        import webbrowser
        try:
            webbrowser.open(file_path.absolute().as_uri())
        except Exception as e:
            notify_warning(f"Could not open {file_path}: {e}")

    def _make_md_control(self, file_path):
        if file_path.exists():
            return self._make_md_preview(file_path)
        btn = pn.widgets.Button(
            name="Create notes.md", width=self.image_feed_width
        )
        btn.on_click(
            lambda event, p=file_path.parent: self._create_and_open_md(p)
        )
        return btn

    def _make_md_preview(self, file_path):
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as e:
            text = f"*Error reading file: {e}*"

        preview = pn.pane.Markdown(
            text,
            height=200,
            width=self.image_feed_width,
            styles={"overflow-y": "auto"},
        )
        edit_btn = pn.widgets.Button(
            name="Edit notes.md", width=self.image_feed_width
        )
        edit_btn.on_click(
            lambda event, f=file_path: self._open_md_editor(f)
        )
        return pn.Column(preview, edit_btn)

    def _create_and_open_md(self, dir_path):
        file_path = dir_path / "notes.md"
        try:
            file_path.write_text("# Notes\n\n", encoding="utf-8")
            self.data_images_feed.objects = self._build_feed(dir_path)
            self._open_md_editor(file_path)
        except Exception as e:
            notify_error(f"Could not create notes.md: {e}")

    def _open_md_editor(self, file_path):
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            content = ""
            logger.error("Could not read notes.md: %s", e)

        text_area = pn.widgets.TextAreaInput(
            value=content, height=350, width=400
        )
        save_btn = pn.widgets.Button(name="Save", button_type="primary")

        def save_callback(event):
            try:
                file_path.write_text(text_area.value, encoding="utf-8")
                self.data_images_feed.objects = self._build_feed(
                    file_path.parent
                )
                for fp in list(self._active_float_panels):
                    if getattr(fp, "_md_file_path", None) == file_path:
                        try:
                            self._float_panel_container.remove(fp)
                        except Exception:
                            pass
                self._active_float_panels = [
                    fp for fp in self._active_float_panels
                    if getattr(fp, "_md_file_path", None) != file_path
                ]
            except Exception as e:
                notify_error(f"Could not save notes.md: {e}")

        save_btn.on_click(save_callback)

        fp = pn.layout.FloatPanel(
            pn.Column(text_area, save_btn),
            name="Edit notes.md",
            contained=False,
            position="center",
            width=450,
            height=480,
        )
        fp._md_file_path = file_path
        self._float_panel_container.append(fp)
        self._active_float_panels.append(fp)

    def _open_json_browser(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            notify_error(f"Could not load JSON {file_path}: {e}")
            return

        data = self._dot_keys_to_nested(data)

        search_input = pn.widgets.TextInput(
            name="Search", placeholder="Filter keys or values...", width=300
        )
        json_pane = pn.pane.JSON(None, width=600, height=400)

        def update_json(event):
            pruned = self._prune_json(data, search_input.value)
            json_pane.object = pruned if pruned is not None else {}

        search_input.param.watch(update_json, "value")
        update_json(None)

        expand_btn = pn.widgets.Button(name="Expand All", width=140)

        def toggle_expand(event):
            if json_pane.depth == 1:
                json_pane.depth = 100
                expand_btn.name = "Collapse All"
            else:
                json_pane.depth = 1
                expand_btn.name = "Expand All"

        expand_btn.on_click(toggle_expand)

        fp = pn.layout.FloatPanel(
            pn.Column(pn.Row(search_input, expand_btn), json_pane),
            name=f"JSON: {file_path.name}",
            contained=False,
            position="center",
            width=650,
            height=500,
        )
        fp._json_file_path = file_path
        self._float_panel_container.append(fp)
        self._active_float_panels.append(fp)

    @staticmethod
    def _dot_keys_to_nested(data):
        if isinstance(data, list):
            return [DataSelect._dot_keys_to_nested(item) for item in data]
        if not isinstance(data, dict):
            return data
        nested = {}
        for k, v in data.items():
            v = DataSelect._dot_keys_to_nested(v)
            parts = k.split(".")
            if len(parts) > 1:
                d = nested
                can_nest = True
                for p in parts[:-1]:
                    if p not in d:
                        d[p] = {}
                    elif not isinstance(d[p], dict):
                        can_nest = False
                        break
                    d = d[p]
                if can_nest:
                    d[parts[-1]] = v
                else:
                    nested[k] = v
            else:
                nested[k] = v
        return nested

    @staticmethod
    def _prune_json(data, term):
        if not term:
            return data
        term = term.lower()
        if isinstance(data, dict):
            pruned = {}
            for k, v in data.items():
                if term in str(k).lower():
                    pruned[k] = v
                else:
                    pv = DataSelect._prune_json(v, term)
                    if pv is not None:
                        pruned[k] = pv
            return pruned if pruned else None
        elif isinstance(data, list):
            pruned = [DataSelect._prune_json(v, term) for v in data
                      if DataSelect._prune_json(v, term) is not None]
            return pruned if pruned else None
        else:
            return data if term in str(data).lower() else None

    @pn.depends("text_input.value_input")
    def text_input_repeater(self):
        val = self.text_input.value_input
        self.typed_value.value = f"Current Search: {val}"
        self.search_term = val
        if val:
            self._search_regex = re.compile(".*" + re.escape(val) + ".*")
        else:
            self._search_regex = re.compile(".*")
        return self.typed_value

    def update_group_options(self, event):
        if hasattr(pn.state, "curdoc") and pn.state.curdoc is not None:
            pn.state.curdoc.add_next_tick_callback(self._refresh_data_sets)
        else:
            self._refresh_data_sets()

    def _refresh_data_sets(self):
        try:
            new_data_set = self.group_data(find_data(root=self.data_root))
            new_opts = OrderedDict()
            for k in sorted(new_data_set.keys())[::-1]:
                lbl = self.date2label(k) + f" [{len(new_data_set[k])}]"
                new_opts[lbl] = k
            self.data_sets = new_data_set
            self._group_select_widget.options = new_opts
            self._data_select_widget.options = self.get_data_options()
            self._group_select_feed.objects = [self._group_select_widget]
        except Exception as e:
            notify_warning(f"Could not refresh data sets: {e}")

    def _on_refresh_clicked(self, event):
        self._refresh_data_sets()

    def _toggle_tag(self, tag_name, event):
        selected = self._data_select_widget.value
        if selected is None:
            notify_warning(f"No dataset selected to add {tag_name} tag")
            return

        tag_file = selected / f"__{tag_name}__.tag"
        try:
            if tag_file.exists():
                tag_file.unlink()
            else:
                tag_file.touch()
            self._data_select_widget.options = self.get_data_options()
        except Exception as e:
            notify_error(f"Error toggling {tag_name} tag: {e}")

    def _on_star_clicked(self, event):
        self._toggle_tag("star", event)

    def _on_trash_clicked(self, event):
        self._toggle_tag("trash", event)

    def _on_bad_clicked(self, event):
        self._toggle_tag("bad", event)

    def _on_poop_clicked(self, event):
        self._toggle_tag("poop", event)


def make_template(config):
    """Build the full autoplot application from config.

    Assembles DataSelect, DDH5Loader, preprocessor Pipeline,
    and plot nodes into a BootstrapTemplate.
    """
    import hvplot  # noqa: F401
    import holoviews as hv  # noqa: F401

    from pathlib import Path

    from .loaders.ddh5 import DDH5Loader
    from .nodes import Pipeline, SplitComplexNode, AverageNode, RotateIQNode

    from .fits import load_fits
    load_fits(config.fits)

    from .plots.base import PlotNode
    PlotNode.load_fits_from_config(config.fits)

    data_root = Path(config.watch.directory)
    ds = DataSelect(data_root)

    loader = DDH5Loader()
    split_node = SplitComplexNode()
    avg_node = AverageNode()
    rotate_node = RotateIQNode()

    pipeline_nodes = [loader, split_node, avg_node, rotate_node]
    pipeline = Pipeline(pipeline_nodes)

    preproc_card = pn.Card(
        pn.Row(
            pn.Column(
                avg_node._toggle,
                avg_node._dim_input,
                align="center",
            ),
            pn.Column(
                rotate_node._toggle,
                rotate_node._angle_input,
                align="center",
            ),
        ),
        title="Pre-processing",
        collapsed=True,
    )

    from .plots import discover_from_config as discover_plots, get_graph_types
    discover_plots(config.plots)
    plot_types = get_graph_types()

    plot_nodes = {}
    for name, cls in plot_types.items():
        plot_nodes[name] = cls()

    plot_type_radio = pn.widgets.RadioButtonGroup(
        name="Plot Types",
        options=list(plot_types.keys()),
        value="value" if "value" in plot_types else list(plot_types.keys())[0],
        button_type="default",
        styles={"background": "white"},
    )

    @pn.depends(plot_type_radio.param.value)
    def fit_save_row(selected):
        node = plot_nodes.get(selected or "")
        if node is None:
            return pn.Row()
        return pn.Row(node.fit_card, node.save_card)

    @pn.depends(plot_type_radio.param.value)
    def plot_area(selected):
        if not selected:
            return pn.pane.Markdown("*No plot types selected.*")
        node = plot_nodes.get(selected)
        if node is None:
            return pn.pane.Markdown("*No plot types selected.*")
        option_items = []
        if hasattr(node, "plot_options_panel"):
            option_items.append(node.plot_options_panel)
        else:
            option_items.append(node.plot_type_select)
        if hasattr(node, "gb_select"):
            option_items.append(node.gb_select)
        return pn.Column(
            plot_type_radio,
            pn.Row(*option_items),
            node.plot_panel,
            sizing_mode="stretch_width",
        )

    def on_data_selected(*events):
        path = events[0].new
        if path is None:
            return
        loader.file_path = path
        if loader.auto_load_switch.value:
            pipeline.run()

    def on_pipeline_output(*events):
        data = events[0].new
        if data is not None:
            from .nodes import Node as _Node
            units = _Node.units_from_dataset(data)
            for node in plot_nodes.values():
                node.data_in = data
                node.units_in = units
                node.units_out = units
                node.path = loader.file_path
                node.fit_data_path = Path(loader.file_path).parent / "fit_data.json"
                node.process()
                node.toggle_save_buttons()

    ds.param.watch(on_data_selected, ["selected_path"])
    pipeline.param.watch(on_pipeline_output, ["data_out"])

    loader.load_button.on_click(lambda event: pipeline.run())
    loader.set_refresh_callback(pipeline.run)

    def on_preprocess_change(*events):
        pipeline.run()

    avg_node._toggle.param.watch(on_preprocess_change, "value")
    avg_node._dim_input.param.watch(on_preprocess_change, "value")
    rotate_node._toggle.param.watch(on_preprocess_change, "value")
    rotate_node._angle_input.param.watch(on_preprocess_change, "value")
    loader.grid_toggle.param.watch(on_preprocess_change, "value")

    temp = pn.template.BootstrapTemplate(
        site="autoplot",
        title="Autoplot",
        sidebar=[],
        main=[
            ds,
            pn.Column(
                pn.Row(
                    loader.load_button,
                    loader.loading_card,
                    preproc_card,
                    fit_save_row,
                ),
                loader.status,
                pn.Row(
                    pn.Column(height=600, width=10),
                    plot_area,
                ),
            ),
        ],
    )

    return temp
