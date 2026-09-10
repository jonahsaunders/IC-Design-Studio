<p align="center">
  <img src="docs/images/banner.svg" alt="IC Design Studio — Design. Simulate. Understand." width="100%">
</p>

<p align="center">
  <strong>An open desktop workspace for circuit design, NGSpice simulation and layout.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.22.0.dev10-4269e8" alt="Version 0.22.0.dev10">
  <img src="https://img.shields.io/badge/status-engineering_preview-f0b44d" alt="Engineering preview">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0--or--later-2f9d89" alt="GPL-3.0-or-later"></a>
</p>

<p align="center">
  <a href="https://github.com/jonahsaunders/IC-Design-Studio/releases"><strong>Download</strong></a> ·
  <a href="SIMULATION_SETUP.md">Simulation setup</a> ·
  <a href="examples/README.md">Examples</a> ·
  <a href="docs/PDK_GUIDE.md">PDK guide</a> ·
  <a href="CONTRIBUTING.md">Contribute</a>
</p>

![IC Design Studio showing a CMOS inverter, linked teaching layout and a completed transient waveform](docs/images/workspace.png)

IC Design Studio brings schematic capture, simulation results and layout editing into one local application. Start with a working example, inspect its waveforms, then build your own circuit. Local work requires no account or cloud service.

**New in 0.22.0.dev10:** the Windows portable package includes **NGSpice 42, Python, Qt, and GF180MCU/SKY130 simulation PDK subsets**. Windows source setup downloads and checks NGSpice automatically. The gallery includes a GF180 bandgap startup, its full 144-analysis characterization, and a SKY130 transistor inverter.

This is an **engineering preview** for learning and circuit experimentation. Linux simulation and offscreen GUI checks are recorded below. Native Windows and macOS desktop qualification remains pending; the included PDK subsets do not provide manufacturing signoff.

## Run the packaged app on Windows

1. Open [Releases](https://github.com/jonahsaunders/IC-Design-Studio/releases) and download `IC-Design-Studio-0.22.0.dev10-Windows-x64.zip` from the dev10 prerelease assets.
2. Extract the **entire ZIP** to a folder. Keep `app` and `python` beside `ICDesignStudio.exe`.
3. Double-click **ICDesignStudio.exe**.
4. Choose **07 · GF180 bandgap startup**, select **Open a copy**, and press **F5**.
5. Open **Simulate → Program analyses** to inspect the waveform and measurements.

No separate Python, NGSpice or PDK installation is needed for these examples, and the portable package requires no first-launch download. It targets Windows 10/11 x64 and is unsigned. Use `ICDesignStudio-Console.exe` for startup diagnostics.

GitHub's automatic **Source code** downloads contain source, not the portable desktop application. See [download options and checksums](docs/DOWNLOADS.md).

![The example gallery with the GF180 and SKY130 simulation examples](docs/images/start-here-dev10.png)

## Run from source

Use **64-bit Python 3.12**. The GF180MCU and SKY130 model files are included in the repository.

### Windows

Clone this repository or use **Code → Download ZIP**, extract it, then double-click:

```bat
launch-windows.bat
```

The launcher creates a virtual environment, installs Python dependencies, downloads the pinned Windows NGSpice runtime if needed, checks its SHA-256 and required DLL, and runs a small simulation before opening the app. Internet access is required for first-time source setup. Later launches reuse the verified environment. No global PATH edits are needed.

### Linux and macOS

Install a native NGSpice first: on Ubuntu, `sudo apt install ngspice`; on macOS with Homebrew, `brew install ngspice`. Then, from the source directory:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/check_simulation_assets.py
python main.py
```

If NGSpice is installed in a custom location, select it under **Tools → Engine diagnostics and paths**, or set `ICSTUDIO_NGSPICE` to its executable. More troubleshooting and offline provisioning instructions are in [SIMULATION_SETUP.md](SIMULATION_SETUP.md).

## Try the included circuits

Open **File → Start here / example gallery** to make a fresh working copy of an example.

| Example | What it demonstrates | Simulator |
|---|---|---|
| Your first waveform | RC transient and waveform inspection | Included educational solver |
| Native divider | Operating point and parameter studies | NGSpice |
| Inverter and layout | Linked schematic and teaching geometry | Included educational solver |
| Native RC comparison | Baseline versus declared layout parasitics | NGSpice |
| Reusable divider | Hierarchical cells and ports | Included educational solver |
| Common-centroid resistors | Matching constraints and placement | No simulation required |
| **07 · GF180 bandgap startup** | Short 5 V, 25 °C startup using process models | NGSpice + included GF180 |
| **08 · GF180 full characterization** | Original bandgap circuit, all 144 analyses; allow several minutes or longer | NGSpice + included GF180 |
| **09 · SKY130 transistor inverter** | 1.8 V transistor switching | NGSpice + included SKY130 |

The [original bandgap schematic](examples/gf180-bandgap/5vfullv2-original.sch) is preserved byte for byte. Its [startup companion](examples/gf180-bandgap/5vfullv2-startup.sch) changes only the simulation control block. The app resolves the original `/foss/pdks/...` model paths and redirects generated tables into the run's output directory.

## Included open PDK models

For a new native project, choose **Tools → Set up an open PDK → Use included PDKs**, select a registered revision, then **New project with this PDK**. Registration works offline and verifies file hashes.

| Package | Placeable / indexed symbols | Included assets |
|---|---:|---|
| GF180MCU D adapter | 64 / 68 | Primitive device models, symbols and display layers |
| SKY130A | 71 / 74 | Primitive corner model closure, symbols and display layers |

These are **simulation subsets**, with pinned provenance and upstream license notices. They exclude standard cells, fabrication collateral, Magic/Netgen verification decks and IHP OSDI binaries. The GF180 D adapter uses the pinned primitive model family; it does not substitute for a complete option-specific foundry PDK. External installed PDKs remain supported through the [PDK setup guide](docs/PDK_GUIDE.md).

## Design and inspect

- **Schematics:** grids, snapping, wires, reusable cells, hierarchy, undo and recovery.
- **Simulation:** NGSpice operating point, transient, DC, AC and noise workflows; run queues, logs, waveform markers and measurements.
- **Layout:** linked views, layer controls, rectangle and path drawing, GDSII/OASIS exchange and KLayout report navigation.
- **Interoperability:** reviewed Xschem import and supported native migration; external Magic/Netgen workflows when matching tools and decks are installed.

See [getting started](docs/GETTING_STARTED.md), [layout drawing](docs/DRAWING_0.22.md), and the in-app **Help → Compatibility matrix** for supported workflows. Xschem migration does not execute arbitrary Tcl. Planned work is tracked in the [roadmap](docs/ROADMAP.md).

## Validation and development

The [dev10 validation record](docs/validation/0.22.0.dev10.json) reports:

- **439 unit/integration tests passed**, with no failures or skips.
- All **nine gallery examples opened** in offscreen GUI checks; seven short simulations ran through the GUI worker.
- The unchanged GF180 circuit completed **144 of 144 analyses** with real Linux NGSpice 42.
- GF180 and SKY130 native model runs passed from folders containing spaces.

These results establish execution of the recorded cases, not compliance with every circuit specification. The locally assembled Windows package passed file-integrity checks; native Windows desktop/installer execution and native macOS execution were not performed. Hosted workflow results are separate evidence, available under [Actions](https://github.com/jonahsaunders/IC-Design-Studio/actions).

```sh
python scripts/check_simulation_assets.py
python scripts/verify_bundled_simulation.py --output build/simulation-check
python -m unittest discover -s tests -v
python scripts/check_release.py
```

Add `--full` to the simulation verifier to run the original 144-analysis characterization. An installed NGSpice is required for real-engine checks; set `ICSTUDIO_TEST_NGSPICE` if it is not on PATH.

Contributions and reduced failing circuits are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) for development guidance and [the release guide](docs/RELEASING.md) for packaging. Report reproducible problems through [Issues](https://github.com/jonahsaunders/IC-Design-Studio/issues).

## License

Application source is **GPL-3.0-or-later**. Bundled tools, libraries, symbols and models retain their own licenses. See [LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and [licenses/](licenses/).
