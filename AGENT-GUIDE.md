# Agent Handoff — Autoplot

## Purpose

Autoplot is a Panel/HoloViews/Xarray library for interactive visualization of experimental data. It provides a GUI application for browsing datasets, loading data, applying preprocessing, fitting, and exporting plots.

## Project Layout

Every file under `autoplot/` is listed below with its role and any decisions embedded in it that must be preserved.

```
autoplot/
├── pyproject.toml              # Build config. Entry point: autoplot.cli:main
├── setup.py                    # Minimal shim: setup()
├── autoplotConfig.yml          # (Auto-generated) Default config with comments
├── AGENTS.md                   # This file
└── autoplot/                   # Package source
    ├── __init__.py             # Public API. Imports all public classes, sets __version__.
    ├── cli.py                  # argparse, main(). Auto-creates config if missing.
    ├── config.py               # Config schema (dataclass), YAML load/write/validate, CLI overrides.
    ├── app.py                  # DataSelect widget (file browser) + make_template() (app assembly).
    ├── nodes.py                # Node, Pipeline, XYSelect, preprocessor nodes, labeled_widget, plot_data.
    ├── styles.py               # CSS stylesheets for monospace fonts.
    ├── notify.py               # logger + pn.state.notifications dual-output helpers.
    ├── loaders/
    │   ├── __init__.py         # Registry, discover_from_config(), auto_detect().
    │   ├── base.py             # BaseLoader interface. NOT an ABC — see metaclass note.
    │   ├── ddh5.py             # DDH5Loader(BaseLoader, Node) — the primary loader with UI.
    │   ├── netcdf.py           # NetCDFLoader(BaseLoader) — xr.open_dataset.
    │   └── zarr.py             # ZarrLoader(BaseLoader) — xr.open_zarr.
    ├── plots/
    │   ├── __init__.py         # Plot type registry, discover_from_config().
    │   ├── base.py             # PlotNode — fitting, saving, 2D helpers, labeled_widget shim.
    │   ├── value.py            # ValuePlot — line/scatter/heatmap/quadmesh.
    │   ├── complex_hist.py     # ComplexHist — IQ hexbin histograms.
    │   └── magnitude_phase.py  # MagnitudePhasePlot — computes Mag/Phase/Unwrap from complex.
    └── fits/
        └── __init__.py         # Fit registry, load_fits().
```

## Architecture — Why Things Are The Way They Are

### 1. The Pipeline Is Imperative, Not Reactive

The `Pipeline` class does NOT use `param` watchers to chain nodes. Instead, `Pipeline.run()` iterates the node list explicitly:

```python
def run(self) -> None:
    data = None
    for node in self._nodes:
        node.data_in = data
        node.process()
        data = node.data_out
    self.data_out = data
```

**Why:** Watcher chains (`append`/`detach` from the old design) cause orphaned callback references and are hard to debug. An imperative loop gives clear ownership: the Pipeline holds the node list; no node holds references to other nodes. When `run()` returns, the intermediate `data` references are eligible for garbage collection.

**Rule:** `Node.process()` reads `self.data_in` and writes `self.data_out`. It is a synchronous, pure function of its inputs. It is called manually by `Pipeline.run()`. Do NOT add `@pn.depends("data_in", watch=True)` to `Node.process()` — this would cause double-processing when `Pipeline.run()` also calls it.

**Exception:** The plot node is NOT in the pipeline. It observes `pipeline.data_out` via a single `param.watch` callback that sets `plot_node.data_in` AND explicitly calls `plot_node.process()`. This single reactive edge replaces the old watcher chain.

### 2. All Extensibility Is Plugin-Based via Config

Loaders, plot types, and fit functions are all discovered from `autoplotConfig.yml`. There are no hardcoded registries in any source file. The registries in `loaders/__init__.py`, `plots/__init__.py`, and `fits/__init__.py` are populated by reading the config.

**Why:** Adding a new visualization or fit should require only: (1) writing a class, (2) adding one line to the YAML. No source edits.

**Rule:** When writing a new plot type, loader, or fit, add its dotted path to the config. The registry inits are lazy — they import only when `discover_from_config()` is called.

### 3. Single Config File Controls Everything

One `autoplotConfig.yml` holds server settings, watch settings, loader list, plot map, and fit list. The CLI accepts only `-c/--config` (config path), `-d/--directory` (override watch directory), and `--verbose` (debug logging). Port, address, and websocket origins are set in the config, not as CLI flags.

**Why:** A single file is the single source of truth. A user or agent can see the entire application configuration in one place. The CLI `-d` flag overrides `watch.directory` for convenience, but nothing else.

**Auto-creation:** If `-c` points to a path that does not exist, `write_default_config()` writes a commented YAML file with all defaults, logs a message, and proceeds. Existing configs are never overwritten.

### 4. Xarray Is the Primary Data Type; Pandas Is Legacy

All pipeline operations prefer `xr.Dataset`. The `Node.mean()`, `Node.split_complex()`, and `Node.rotate_iq()` static methods handle both `xr.Dataset` and `pd.DataFrame`, but the xarray path is the primary, optimized one. The `grid_toggle` on the loader controls whether output is xr.Dataset (gridded) or pd.DataFrame (flat).

**Why:** xarray provides lazy evaluation, copy-on-write semantics, and native dimension-aware operations. The pandas path exists only for backward compatibility when users disable auto-grid.

**Rule:** New preprocessor nodes should use xarray operations (`.mean()`, array arithmetic). They should NOT deep-copy data — xarray's CoW handles that.

### 5. The Plot Node Owns Fit Management and Saving

`PlotNode` (base class of `ValuePlot`, `ComplexHist`, `MagnitudePhasePlot`) contains the entire fit lifecycle: loading fit classes from config, creating the fit UI box (FloatInputs for parameters, Run/Reguess/Save/Refit buttons), executing fits via `lmfit`, saving results to JSON, and overlaying fit curves on plots.

**Why:** Fits are a visualization concern. They add overlay data to a plot. They do not transform the input data — they annotate it. Keeping fits on the plot node means: (a) the data pipeline doesn't need to know about fits, (b) each plot type can define which axes are fittable via `fit_axis_options()`, (c) fit state is naturally scoped to one plot.

**Rule:** New plot types must override `fit_axis_options()` to return a list of axis names. The base `PlotNode.process()` auto-adds saved fit overlays for those axes. The `get_data_fit_names()` and `update_dataset_by_fit_and_axis()` methods handle the overlay logic.

### 6. No Data Copies in the Pipeline

The pipeline's preprocessing nodes (SplitComplex, Average, RotateIQ) return derived xarray objects. `SplitComplexNode.process()` returns a new Dataset with renamed variables (no array copy). `AverageNode.process()` returns `data.mean(dim)` — an xarray reduction. `RotateIQNode.process()` computes new arrays — but only one reference to the result exists at any time, since `Pipeline.run()` overwrites the previous `data` variable each iteration.

**Why:** For memory efficiency with large experimental datasets.

## Core Classes — Reference

### `Node` (`nodes.py` — line 23)

Base class for all processing nodes. Inherits from `pn.viewable.Viewer`.

**Parameters:** `data_in` (Data|None), `data_out` (Data|None), `units_in` (dict), `units_out` (dict).

**Methods to override:**
- `process()` — reads `data_in`, writes `data_out`. Default: identity.

**Static helpers (callable without instantiation):**
- `Node.data_dims(data) -> (independents, dependents)` — delegates to `labcore.data.tools.data_dims`
- `Node.mean(data, *dims) -> Data` — uses xr.Dataset.mean() or pd.groupby
- `Node.split_complex(data) -> Data` — delegates to `labcore.data.tools.split_complex`
- `Node.rotate_iq(data, angle_deg) -> Data` — numpy rotation on Re/Im variable pairs
- `Node.complex_dependents(data) -> dict` — finds Re/Im pairs, returns `{base: {real, imag}}`
- `Node.dim_label(dim) -> str` — appends units, defaults to "(a.u.)"
- `Node.dim_labels() -> dict[str, str]` — all dims with labels

**Important:** These helpers call `labcore` at function scope (inside the method body, not at module top level). This keeps the `Node` class importable for unit tests without requiring labcore.

### `Pipeline` (`nodes.py` — line 146)

Holds an ordered list of Node instances. `PipeLine.run()` feeds data through the chain and stores the final output in `self.data_out`.

**Constructor:** `Pipeline(nodes: list[Node])`

The first node is typically the loader. The last node's `data_out` becomes `pipeline.data_out`. The pipeline itself is a `pn.viewable.Viewer` and has a `layout` property for its UI.

### `DDH5Loader` (`loaders/ddh5.py`)

The primary data loader. Extends both `BaseLoader` and `Node`.

**Key points:**
- `file_path` param holds the path to `data.ddh5` (full path including filename).
- `process()` calls `self.load(Path(self.file_path))`, respects `grid_toggle` for xr.Dataset vs DataFrame output, updates `status` widget.
- `load(path)` uses `path.parent` to find the data directory, prefers `data_gridded.ddh5` over `data.ddh5`.
- Has a `grid_toggle` Switch, `auto_load_switch`, `refresh_widget` Select, and `load_button` as Panel widgets.
- `set_refresh_callback(cb)` allows the template to inject a callback for the auto-refresh timer.
- The "Load data" button's `on_click` is set in `make_template()`, NOT in the loader constructor. This ensures the button always triggers the full pipeline.

**Load flow:**
1. `file_path` = `Path(".../2026-06-10T182450_abc123-VNA_R1_Can1_Power_Sweep/data.ddh5")`
2. `load(path)` → `data_dir = path.parent` → `".../2026-06-10T182450_abc123-VNA_R1_Can1_Power_Sweep/"`
3. Looks for `data_dir / "data_gridded.ddh5"`, falls back to `data_dir / "data.ddh5"`
4. Returns `ddh5_to_xarray(str(load_path))` → xr.Dataset

### `PlotNode` (`plots/base.py` — line 31)

Base class for all plot types. Extends `Node`.

**Fit system:**
- `PlotNode.FITS` — class-level dict loaded from config. Populated by `load_fits_from_config()`.
- `fit_dict` — per-instance dict: `{axis_name: {fit_function, start_params, params}}`. Saved fit data is loaded from `fit_data.json` in the data directory.
- `fit_button` — `pn.widgets.MenuButton` with fit function names from config.
- `select_fit_axis` — `pn.widgets.Select` for choosing which axis to fit.
- `add_fit_box()` / `remove_fit_box()` — creates/removes the parameter input UI.
- `model_fit()` — runs the fit via `lmfit`, stores result in `fit_result`.
- `save_fit()` — writes `fit_params.json` and `fit_result.txt`.
- `update_dataset_by_fit_and_axis()` — adds `{axis}_fit` or `{axis}_fit*` DataArray to `data_out`.

**Save system:**
- `save_html()` — `hvplot.save(plot, filename)`
- `save_png()` — renders to bokeh, then `bokeh.io.export.export_png()`
- `get_plot()` — override to return a HoloViews object for saving.

**Graph type switching:**
- `graph_types` — dict `{name: PlotClass}`. Subclasses add their own entry.
- `plot_type_select` — RBG widget. Must be created BEFORE `super().__init__()` because `@pn.depends` references in subclass `plot_panel()` methods resolve during `super().__init__()`.

### `DataSelect` (`app.py` — line 23)

File browser widget for datasets organized by date.

**Parameters:** `selected_path` (Path|None), `search_term` (str|None), `group_options`.

**Key details:**
- `selected_path` is set to the FULL path including `data.ddh5` filename (e.g., `Path(".../folder/data.ddh5")`), not just the folder. This matches what the loader expects.
- `_data_select_widget.value` is a `Path` to the dataset folder. `info_panel()` transforms it: `display_path = path / DATAFILE` for display and `selected_path = display_path` for downstream use.
- The loader receives `selected_path` and calls `.parent` to get the directory.
- Watchdog observer monitors the configured directory for new `.ddh5` files.

**Features preserved from existing design:**
- Tag buttons (star, trash, bad, error) create/delete `__{tag}__.tag` files in the dataset folder.
- Image feed shows PNG/JPG files from the dataset folder.
- Notes.md editor opens in a FloatPanel with save capability.
- JSON browser opens in a FloatPanel with search and expand/collapse.
- Data schema preview loads asynchronously via `ddh5_schema()`.

### `make_template()` (`app.py` — line 635)

Assembles the full Panel application.

**Wiring it sets up:**

1. **Data selection → loader:** `ds.param.watch(on_data_selected, ["selected_path"])` sets `loader.file_path`. If `auto_load_switch` is on, also calls `pipeline.run()`.

2. **Load button → pipeline:** `loader.load_button.on_click(lambda event: pipeline.run())`.

3. **Auto-refresh → pipeline:** `loader.set_refresh_callback(pipeline.run)`.

4. **Pipeline output → plot node:** `pipeline.param.watch(on_pipeline_output, ["data_out"])` sets `plot_node.data_in` AND calls `plot_node.process()`.

5. **Preprocessor widget changes → pipeline re-run:** Watchers on `avg_node._toggle.value`, `avg_node._dim_input.value`, `rotate_node._toggle.value`, `rotate_node._angle_input.value`, and `loader.grid_toggle.value` all call `pipeline.run()`.

6. **Plot rendering:** `plot_options_panel` and `plot_panel` use `@pn.depends("data_out", ...)` to reactively re-render when `data_out` changes.

**Layout structure (matching existing UI):**
- Top: DataSelect widget (dates, datasets, search, tags, images, info)
- Row of collapsible cards: Load button, Loading Options, Pre-processing, Fit, Save
- Status line
- Plot area with buffer column (width=10, height=600) + plot

### Preprocessor Nodes (`nodes.py` — lines 169-251)

Each extends `Node` with a `process()` override and Panel widgets.

**`SplitComplexNode`:** No widgets. Always splits complex variables into Re/Im. `process()` calls `self.split_complex(self.data_in)`.

**`AverageNode`:** Has `enabled` (Boolean) and `dim_name` (String) params. UI: Switch + TextInput. `process()`: calls `self.mean(data_in, dim_name)` if enabled and dim_name is an independent dim.

**`RotateIQNode`:** Has `enabled` (Boolean) and `angle` (Number) params. UI: Switch + FloatInput. `process()`: calls `self.rotate_iq(data_in, angle)` if enabled.

The template watches the UI widgets to re-trigger `pipeline.run()`.

## Data Flow — End to End

```
1. Dataset selected in DataSelect dropdown
   → DataSelect.selected_path = Path(".../folder/data.ddh5")

2. on_data_selected watcher fires
   → loader.file_path = ".../folder/data.ddh5"
   → (if auto_load_switch is on) pipeline.run()

3. User clicks "Load data" OR auto-refresh timer fires OR preprocessor widget changes
   → pipeline.run()

4. Pipeline.run() iterates nodes:

   a. loader.process()
      → self.load(Path(self.file_path))
      → ddh5_to_xarray(".../folder/data.ddh5") or data_gridded.ddh5
      → if grid_toggle is off: split_complex + .to_dataframe()
      → loader.data_out = xr.Dataset (or pd.DataFrame)

   b. split_node.process()
      → self.split_complex(self.data_in)
      → complex vars become {name}_Re, {name}_Im
      → split_node.data_out

   c. avg_node.process()
      → if enabled AND dim_name in independent dims:
          self.mean(self.data_in, self.dim_name)
      → avg_node.data_out

   d. rotate_node.process()
      → if enabled:
          self.rotate_iq(self.data_in, self.angle)
      → rotate_node.data_out

   e. pipeline.data_out = rotate_node.data_out

5. on_pipeline_output watcher fires
   → plot_node.data_in = pipeline.data_out
   → plot_node.process()
      → self.data_out = copy.copy(self.data_in)
      → adds fit overlay DataArrays for saved fits
      → plot_node.data_out is set

6. @pn.depends("data_out") triggers re-render
   → plot_options_panel() re-evaluates → XYSelect options updated
   → plot_panel() re-evaluates → hvplot.line/scatter/quadmesh/hexbin rendered
```

## Extending The Library

### Adding a new plot type

**Step 1: Create the class**

```python
# autoplot/plots/my_plot.py
import panel as pn
import param
from autoplot.plots.base import PlotNode

class MyPlot(PlotNode):
    def __init__(self, *args, **kwargs):
        # Create any widgets BEFORE super().__init__()
        # because @pn.depends resolves during super().__init__()
        super().__init__(*args, **kwargs)

        # Register this plot type
        self.graph_types = {"None": None, "My Plot": MyPlot}
        self.plot_type_select.options = list(self.graph_types.keys())
        self.plot_type_select.value = "My Plot"

    # Override to provide the plot
    @pn.depends("data_out", "refresh_graph")
    def plot_panel(self):
        # self.data_out is an xr.Dataset or pd.DataFrame
        # Return a HoloViews object or Panel layout
        if self.data_out is None:
            return pn.pane.Markdown("*No data*")
        return self.data_out.hvplot(...)

    # Override to provide axes available for fitting
    def fit_axis_options(self):
        _, dep = self.data_dims(self.data_out)
        return list(dep) if dep else []

    # Override to return a HoloViews object for PNG/HTML save
    def get_plot(self):
        return self.plot_panel()
```

**Step 2: Register in config**

```yaml
# autoplotConfig.yml
plots:
  value: autoplot.plots.value.ValuePlot
  readout_hist: autoplot.plots.complex_hist.ComplexHist
  magnitude_phase: autoplot.plots.magnitude_phase.MagnitudePhasePlot
  my_plot: autoplot.plots.my_plot.MyPlot   # <-- add this line
```

**Step 3 (optional): Add to default config**

Edit `config.py`'s `DEFAULT_CONFIG_YAML` string to include the new entry in the `plots:` section.

### Adding a new preprocessor node

**Step 1: Create the node**

```python
# autoplot/nodes.py (or a separate file)
class NormalizeNode(Node):
    enabled = param.Boolean(True)

    def __init__(self, **params):
        super().__init__(**params)
        self._toggle = pn.widgets.Switch(value=True, name="Normalize")
        self._toggle.param.watch(self._on_toggle, "value")
        self.layout = pn.Column(self._toggle)

    def _on_toggle(self, *events):
        self.enabled = self._toggle.value

    def process(self):
        if self.data_in is not None and self.enabled:
            ds = self.data_in
            result = ds.copy(deep=False)
            for var in ds.data_vars:
                vmax = float(ds[var].max())
                if vmax != 0:
                    result[var] = ds[var] / vmax
            self.data_out = result
        else:
            self.data_out = self.data_in
```

**Step 2: Wire into Pipeline in `make_template()`**

```python
# In make_template() in app.py
norm_node = NormalizeNode()
pipeline = Pipeline([loader, split_node, norm_node, avg_node, rotate_node])

# Wire widget to trigger re-run
norm_node._toggle.param.watch(lambda e: pipeline.run(), "value")
```

### Adding a new fit function

A fit function class must:
1. Extend `labcore.analysis.fit.Fit`
2. Have a static `model(coordinates, **params) -> np.ndarray` method
3. Have a static `guess(coordinates, data) -> dict[str, float]` method

```python
class Lorentzian(Fit):
    @staticmethod
    def model(coordinates, A, x0, gamma, of=0):
        x = coordinates
        return A * gamma**2 / ((x - x0)**2 + gamma**2) + of

    @staticmethod
    def guess(coords, data):
        idx_max = np.argmax(data)
        half_max = data.max() / 2
        above_half = np.where(data > half_max)[0]
        if len(above_half) > 1:
            gamma = (coords[above_half[-1]] - coords[above_half[0]]) / 2
        else:
            gamma = 1.0
        return {
            "A": float(data.max()),
            "x0": float(coords[idx_max]),
            "gamma": gamma,
            "of": 0.0,
        }
```

Register in `autoplotConfig.yml`:
```yaml
fits:
  - my_module.Lorentzian
```

### Adding a new data loader

```python
# autoplot/loaders/csv_loader.py
from pathlib import Path
import pandas as pd
import xarray as xr
from .base import BaseLoader
from ..nodes import Node

class CSVLoader(BaseLoader, Node):
    def __init__(self, **params):
        super().__init__(**params)
        # Build Panel UI for this loader
        ...

    @property
    def extensions(self) -> list[str]:
        return [".csv"]

    def load(self, path: Path) -> xr.Dataset:
        df = pd.read_csv(path)
        return df.to_xarray()

    def process(self) -> None:
        if self.file_path is None:
            self.data_out = None
            return
        self.data_out = self.load(Path(self.file_path))
```

Register in config:
```yaml
loaders:
  - autoplot.loaders.ddh5.DDH5Loader
  - autoplot.loaders.csv_loader.CSVLoader
```

Then wire in `make_template()` to select the appropriate loader based on file extension. Currently `make_template()` hardcodes `DDH5Loader`. For multi-loader support, use `auto_detect(path, loaders)` from `loaders/__init__.py`.

## Critical Rules — Do NOT Violate These

### Metaclass: No ABC

`BaseLoader` must NOT use `abc.ABC` or `abc.abstractmethod`. The `Node` base class inherits from `pn.viewable.Viewer`, which uses `param`'s `ParameterizedMetaclass`. `ABCMeta` and `ParameterizedMetaclass` are incompatible. Instead, `BaseLoader` raises `NotImplementedError` for abstract methods. Any new class that inherits both `BaseLoader` and `Node` (like `DDH5Loader`) will hit a `TypeError: metaclass conflict` if `BaseLoader` uses `ABC`.

### `plot_type_select` widget must exist before `super().__init__()`

In `PlotNode` and its subclasses (`ValuePlot`, `ComplexHist`, `MagnitudePhasePlot`), create `self.plot_type_select` BEFORE calling `super().__init__()`. The `@pn.depends("plot_type_select.value")` decorator on `plot_panel()` is resolved during `super().__init__()` by `param._update_deps()`. If the widget doesn't exist yet, param raises `AttributeError: Dependency 'plot_type_select' could not be resolved`.

This means all Node subclass widgets referenced in `@pn.depends` strings must be created before the `super().__init__()` call in `PlotNode`. Currently `XYSelect` (used by ValuePlot, MagnitudePhasePlot) and `gb_select` (used by ComplexHist) are created before `super().__init__()`.

### `selected_path` must include the filename

`DataSelect.selected_path` is `Path(".../folder/data.ddh5")`, not `Path(".../folder/")`. The loader's `load(path)` method does `data_dir = path.parent` to recover the folder. If a change causes `selected_path` to exclude the filename, the loader will try `path.parent.parent` and miss the data directory.

### Plot node process() must be called manually after setting data_in

```python
plot_node.data_in = data
plot_node.process()   # <-- REQUIRED
```

`Node.process()` is NOT decorated with `@pn.depends("data_in", watch=True)`. Setting `data_in` alone does nothing. The template's `on_pipeline_output` watcher calls both.

### Button wiring is in the template, not the loader

`DDH5Loader.load_button.on_click()` is set in `make_template()`. The `DDH5Loader.__init__()` does NOT wire its own button. This avoids the button triggering both an internal load AND a pipeline run (double execution).

### Buffer column is required for scroll stability

The plot area layout:
```python
pn.Row(
    pn.Column(height=600, width=10),   # buffer — do NOT remove or change height
    pn.Column(
        plot_node.plot_options_panel,
        plot_node.plot_panel,
    ),
)
```

The 600px-height empty column prevents the Row from collapsing to zero height when the plot content is replaced during re-render. Removing it causes the browser to scroll to top on every plot update.

### Labcore imports are function-scoped, not module-scoped

All `import labcore...` statements are inside method bodies (e.g., inside `load()`, `process()`, `load_fits_from_config()`). This allows the package modules to be imported for unit testing without requiring labcore to be installed. Do NOT move labcore imports to module top level.

### Loaders extending Node must also extend BaseLoader first

`class DDH5Loader(BaseLoader, Node):` — MRO puts BaseLoader before Node. This ensures the `Node.process()` method is available without shadowing. The `BaseLoader` provides `can_handle()` and the `extensions` property.

### autoplotConfig.yml is auto-created, never overwritten

If `-c` points to a nonexistent file, the CLI writes a default config and proceeds. If the file exists, it is loaded as-is. The `write_default_config()` function is only called by the CLI when the file is missing. It is never called automatically otherwise.

## Testing

```bash
cd D:\Sync_GauravHatlabPC\CODE\Libraries_UIUC_Github\autoplot
python -m pytest tests -v
```

39 tests. `test_config.py` validates YAML loading and CLI overrides. `test_nodes.py` tests each preprocessor node with synthetic xr.Dataset instances. `test_loaders.py` tests NetCDF read and auto-detection. `test_plots.py` tests fit_axis_options and plot node process methods. `test_app.py` tests DataSelect utility functions (dot-key nesting, JSON pruning, date labels).

`conftest.py` provides shared fixtures. All tests are pure unit tests — no Panel server is started.

## Development Install

```bash
pip install -e D:\Sync_GauravHatlabPC\CODE\Libraries_UIUC_Github\autoplot
```

The package entry point `autoplot` conflicts with an older labcore entry point. Use `python -m autoplot.cli` to invoke the correct version if both are installed.
