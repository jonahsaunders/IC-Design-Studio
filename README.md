<p align="center">
  <img src="docs/images/banner.svg" alt="IC Design Studio — Design. Simulate. Understand." width="100%">
</p>

<p align="center">
  <strong>An open desktop workspace for circuit design, simulation and layout.</strong><br>
  Start with a small circuit. Grow into reusable cells, native projects and open PDK workflows.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.21.0-4269e8" alt="Version 0.21.0">
  <img src="https://img.shields.io/badge/status-engineering_preview-f0b44d" alt="Engineering preview">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0--or--later-2f9d89" alt="GPL-3.0-or-later"></a>
  <img src="https://img.shields.io/badge/interface-native_Qt_6-58738f" alt="Native Qt 6 interface">
</p>

<p align="center">
  <a href="docs/GETTING_STARTED.md"><strong>Get started</strong></a> ·
  <a href="examples/README.md">Examples</a> ·
  <a href="docs/PDK_GUIDE.md">Open PDKs</a> ·
  <a href="docs/ROADMAP.md">Roadmap</a> ·
  <a href="docs/RELEASE_0.21.md">Release notes</a> ·
  <a href="CONTRIBUTING.md">Contribute</a>
</p>

![The native desktop showing a CMOS inverter, linked teaching layout and a completed transient waveform](docs/images/workspace.png)

## One workspace, from schematic to results

IC Design Studio brings schematic capture, a simulation run table, waveform inspection and layout editing into one local application. Use it to learn circuit design, develop small analog blocks, migrate supported Xschem projects, and build reproducible experiments around open-source engines. No account or cloud service is required for local work.

| Capture and organize | Simulate and understand | Build and verify |
|---|---|---|
| Visible grids, snapping and manual wires | Queued runs with individual status and logs | Linked schematic and layout views |
| Reusable cells, symbols and hierarchy | ngspice OP, transient, DC, AC and noise | GDSII / OASIS import and export |
| Native migration and reviewed Xschem exchange | X/Y markers, thresholds and waveform calculations | Parametric devices and placement constraints |
| Dockable windows and searchable commands | Specifications, PVT cases and parameter studies | KLayout report navigation and external rule jobs |
| Undo, recovery and revision-linked results | Sensitivity and bounded parameter search | Declared interconnect RC comparisons |

**0.21 makes the first steps easier:** a searchable example gallery, six guided projects, background discovery of multiple PDK variants, batch registration, and a direct path from a registered PDK to a new project.

This is an **engineering preview**. It has working end-to-end workflows and a growing regression suite; it is not a manufacturing signoff environment. Supported exchange subsets, model requirements and executed validation are documented in the [release notes](docs/RELEASE_0.21.md).

## Start in three steps

1. **Open the app.** For the Windows portable package, extract the entire archive and launch `ICDesignStudio.exe`. Python, Qt and ngspice are included. See [download and platform guidance](docs/DOWNLOADS.md).
2. **Choose “Your first waveform.”** The startup gallery opens it as a fresh copy. This example uses the included educational solver and needs no PDK installation.
3. **Press F5.** Inspect the output under **Results → Waveforms**, place markers, then save your own project with **Ctrl+S**.

Reopen the gallery any time with **File → Start here / example gallery**. Use **Ctrl+K** to find commands and **Window** to arrange the workspace.

<details>
<summary><strong>Run from source</strong> — Python 3.12</summary>

From the repository directory:

```sh
python -m venv .venv
```

Activate the environment:

```sh
# Linux / macOS
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Then install and launch:

```sh
python -m pip install -r requirements.txt
python main.py
```

The repository does not contain a Windows simulator executable. Install a native ngspice and select it in **Tools → Engine diagnostics and paths**, or set `ICSTUDIO_NGSPICE` to its executable. The downloadable **Source** archive additionally includes the Windows ngspice runtime; the **GitHub** archive is the clean repository tree.

Open a saved design directly with `python main.py --project examples/native-divider.icproj`. Opening examples from the gallery is preferable for everyday exploration because it creates independent copies.

Linux is exercised by the current regression suite. Windows execution is a release gate in CI; this locally prepared portable build has static packaging checks. macOS is a source workflow that still needs platform qualification.

</details>

## Learn with included projects

Every project below is installed with the app and available from its example gallery. These are small exercises, not long-running benchmark circuits.

| Example | What you learn | Requirements |
|---|---|---|
| [RC low-pass](examples/rc.icproj) | Run a transient; inspect a waveform with markers | Included solver |
| [Native divider](examples/native-divider.icproj) | Verify a 0.5 V operating point; explore parameter studies | ngspice; no external PDK |
| [Inverter and layout](examples/inverter_layout.icproj) | Move between schematic, teaching geometry and results | Included solver |
| [Native RC comparison](examples/native-rc.icproj) | Compare a baseline with declared layout parasitics | ngspice; illustrative coefficients |
| [Reusable divider](examples/reusable-divider.icproj) | Navigate a hierarchical circuit and its ports | Included solver |
| [Common-centroid resistors](examples/common-centroid-resistors.icproj) | Review matching constraints and device placement | No simulator needed |

Follow the [example walkthroughs](examples/README.md), or try the [small hierarchical Xschem exchange example](examples/xschem-amplifier/amplifier.sch).

![The searchable example gallery with a short walkthrough and an Open a copy button](docs/images/start-here.png)

## Open PDKs with an explicit setup path

Choose **Tools → Set up an open PDK**. The assistant can discover enabled installations under `PDK_ROOT`, Ciel and common local PDK folders. **Add folder** also accepts a parent containing several variants or the extracted companion adapter collection. Check the desired entries, choose **Check and register**, then **New project with this PDK**.

| PDK family | Stock adapter | Additional setup |
|---|---|---|
| **SkyWater SKY130** | Installed `sky130A` / `sky130B` models, symbols and layer maps | ngspice for process models; matching decks and external tools for physical verification |
| **GlobalFoundries GF180MCU** | Installed `gf180mcuA/B/C/D` variants and consistent model corner groups | ngspice; physical verification needs the corresponding decks |
| **IHP SG13G2** | Installed `ihp-sg13g2` models, symbols and layer maps | Compatible ngspice plus compiled OSDI model libraries |
| **Other open PDKs** | Custom technology and checksummed package interface | An explicit model, terminal, layer and verification adapter is required |

Use [Ciel](https://github.com/fossi-foundation/ciel) for prebuilt PDK management, [open_pdks](https://github.com/fossi-foundation/open-pdks) for supported source builds, or the [IHP installation guide](https://ihp-open-pdk-docs.readthedocs.io/en/latest/install/installation.html). A raw foundry source checkout and an installed tool-ready PDK are different inputs.

The optional release adapter collection contains pinned **SKY130A, GF180MCUC and IHP SG13G2 subsets**, including license notices and provenance. It is not a complete PDK distribution. Registration checks assets; it does not establish model or physical qualification. Unsupported dynamic symbols remain visible with an explanation.

Read the [PDK guide](docs/PDK_GUIDE.md) for installation, IHP OSDI setup, revision management and troubleshooting.

## Work with open-source tools

| Tool | Integration |
|---|---|
| **Xschem** | Hierarchical import, source-preserving review, supported native migration, and reviewed exchange back to Xschem |
| **ngspice** | Native graphical analyses and supported saved control programs, short or multi-case jobs, logs and retained waveforms |
| **KLayout** | Geometry library, GDSII/OASIS exchange, `.lyrdb` findings and external self-contained rule scripts |
| **Magic / Netgen** | Configurable external extraction and netlist comparison for supported process workflows |
| **OpenVAF** | Compile IHP Verilog-A models for a compatible OSDI runtime |

The application does not execute arbitrary Xschem Tcl as part of migration. Review unsupported constructs and compare the imported circuit with a small reference run. Details: [native migration](docs/UPDATE_0.19.md), [native analyses and exchange](docs/UPDATE_0.20.md), and the in-app **Help → Compatibility matrix**.

## The path forward

Our direction is an independent, approachable design environment with strong open-tool compatibility. The next milestones prioritize trustworthy workflows before expanding the analysis catalogue.

| Priority | Milestone | What success looks like |
|---|---|---|
| **1 · Reliable releases** | Fresh-machine Windows and Linux validation, signed Windows distribution, accessibility and high-DPI checks | A new user can install, simulate, save and reopen without setup surprises |
| **2 · Stronger native design** | Broader parameterized hierarchy, bus editing, richer symbols, migration fidelity and connection-preserving edits | Substantial designs remain understandable and editable after migration |
| **3 · PDK confidence** | Managed version downloads, more device adapters, representative corner tests and matching verification decks | Each supported process revision has a reproducible evidence-backed workflow |
| **4 · Deeper verification** | More parametric geometry, hierarchical extraction, calibrated RC and connected DRC/LVS review | Electrical and physical changes can be compared with traceable results |
| **5 · Simulation depth and scale** | Richer optimization, statistical reporting, performance work and advanced periodic/RF analyses | Larger experiments remain responsive and every result retains its inputs |

These are **planned milestones, not delivered features or committed dates**. See the [detailed roadmap and acceptance criteria](docs/ROADMAP.md) to help shape the work.

## Contribute

Useful contributions include small failing circuits, reproducible PDK adapter tests, accessibility feedback, documentation fixes and focused pull requests. Start with [CONTRIBUTING.md](CONTRIBUTING.md). Bug and feature request templates are included.

```sh
python -m unittest discover -s tests -v
```

The [desktop CI workflow](.github/workflows/build-desktop.yml) also runs native Qt and real ngspice acceptance checks and builds desktop artifacts. The [maintainer release guide](docs/RELEASING.md) covers versioning, checksums and publication. A workflow file is not evidence that a hosted run has passed; see the [validation record](docs/RELEASE_0.21.md).

## License

Application source: **GPL-3.0-or-later**. Bundled tools, libraries, symbols and model files retain their licenses and notices. See [LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [licenses/](licenses/).
