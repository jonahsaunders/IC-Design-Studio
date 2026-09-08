# IC Design Studio 0.13.0

Native desktop workspace for IC schematics, simulation and layout. Built with PySide6/Qt Widgets and KLayout, with an optional C++ numerical helper.

**Engineering preview.** Linux desktop/user acceptance and Windows qualification remain unexecuted. See [release status](docs/RELEASE_STATUS.md) for the validation boundaries.

This release adds reviewed terminal updates across schematics, symbols, linked layouts and saved benches; configurable hierarchy-aware electrical checks; an occurrence and net cross-probe browser; clearer capture controls and overlap selection; and measured improvements to wire lookup, large-layout redraws and symbol rendering. Existing Xschem-inspired, Virtuoso-inspired and KLayout-inspired profiles and analog/process workflows remain. Read [the 0.13 guide](docs/UPDATE_0.13.md), [capability matrix](docs/CAPABILITY_MATRIX_0.13.md) and [desktop/user acceptance protocol](docs/DESKTOP_ACCEPTANCE_0.13.md).

## Run from source

Python 3.12:

```sh
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py
```

Open a project directly with `python main.py --project /path/to/design.icproj`.

The separate Linux bundle includes Python, Qt and KLayout. Keep its `_internal` directory beside the executable. No Windows executable or installation qualification is included.

## PDK setup

Download the companion PDK package archive and extract it. In **Tools → PDK manager → Install package**, choose `package.json` inside `sky130A`, `gf180mcuC` or `ihp-sg13g2`. Then select the installed revision and **Link to project**. Alternatively use **Add folder** to index an existing supported stock PDK installation. Existing projects can use **Tools → Migrate PDK revision** to review an upgrade. The packages now lock and install their Magic/Netgen assets too.

Open the companion archive's `ring-oscillator.icproj`, select `ring_oscillator`, and open **View → Physical workflow**. Configure Magic, Netgen and ngspice in **Tools → Engine diagnostics & paths**, then choose **Run physical verification**. Three linked placements share one inverter physical cell. **View → Saved testbenches** edits analysis, model corner, temperature, startup, probes and measurements; **Open fixture** exposes the actual sources and loads. `custom-inverter.icproj` and 2/3/4/8-finger examples are included too.

Use the **Devices** category and search fields to place a model. Configure ngspice in Engine diagnostics and select it in the Analysis panel. For IHP, compile its Verilog-A models using `scripts/compile_ihp_osdi.py` and select the resulting libraries in **Tools → Simulation runtime**. Native model binaries must match the simulator interface and host platform; the supplied source and build instructions cover this setup.

## Development

- `icstudio/`: native application and domain modules.
- `tests/`: core regressions and native Qt interaction checks.
- `examples/`: generic circuits and pinned reference definitions.
- `scripts/`: native helper, packaging and release tools.
- `docs/UPDATE_0.13.md`: current release guide.
- `docs/handoff/`: preserved 0.13 continuation notes and original result summaries.
- `docs/`: detailed/historical workflow documentation; older release claims retain their original scope.
- `native/`: optional C++20 solver.
- `packaging/`, `.github/`: Windows build and installer definitions; not evidence of an executed Windows release.

```sh
python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen python tests/gui_project_pdk.py
QT_QPA_PLATFORM=offscreen python tests/gui_wiring.py
QT_QPA_PLATFORM=offscreen python tests/gui_labels.py
```

Install `requirements-build.txt` to build a standalone bundle with `python scripts/package.py`. Desktop runtime libraries must be present on the build host. The desktop GitHub Actions workflow runs on pushes to `main`/`master`, relevant pull requests and manual dispatch; it tests and packages Linux and Windows builds, then saves workflow artifacts. It does not publish a GitHub Release. See `docs/WINDOWS_RELEASE.md` for the unexecuted Windows pipeline.

License: GPL-3.0-or-later. Third-party components retain their licenses; see `THIRD_PARTY_NOTICES.md` and `licenses/`.
