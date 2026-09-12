<p align="center">
  <img src="docs/images/banner.svg" alt="IC Design Studio — From first waveform to physical layout." width="100%">
</p>

<p align="center">
  <strong>An open desktop workspace for circuit design.</strong><br>
  Draw schematics, run simulations, build layouts, and review designs together.<br>
  Keep your cells, models, testbenches, and results in one project.
</p>

<p align="center">
  <a href="docs/RELEASE_STATUS.md"><img src="https://img.shields.io/badge/version-0.22.0.dev21-65d6bd?style=flat-square&amp;labelColor=182331" alt="Version 0.22.0.dev21"></a>
  <a href="docs/RELEASE_STATUS.md"><img src="https://img.shields.io/badge/status-engineering_preview-f0bc78?style=flat-square&amp;labelColor=182331" alt="Engineering preview"></a>
  <a href="https://github.com/jonahsaunders/IC-Design-Studio/actions/workflows/build-desktop.yml"><img src="https://github.com/jonahsaunders/IC-Design-Studio/actions/workflows/build-desktop.yml/badge.svg?branch=experimental" alt="Desktop build and verification"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0--or--later-9bbafa?style=flat-square&amp;labelColor=182331" alt="GPL-3.0-or-later license"></a>
</p>

<p align="center">
  <a href="#start-in-three-steps"><strong>Get started</strong></a> &nbsp;·&nbsp;
  <a href="docs/DOWNLOADS.md">Downloads</a> &nbsp;·&nbsp;
  <a href="#explore-the-workspace">Feature tour</a> &nbsp;·&nbsp;
  <a href="#feature-reference">All features</a> &nbsp;·&nbsp;
  <a href="docs/INDEX.md">Documentation</a> &nbsp;·&nbsp;
  <a href="CONTRIBUTING.md">Contribute</a>
</p>

<p align="center">
  <a href="docs/GETTING_STARTED.md">
    <picture>
      <source media="(prefers-color-scheme: light)" srcset="docs/images/readme/simulation-light.png">
      <img src="docs/images/readme/simulation-dark.png" alt="The RC example in IC Design Studio: an editable schematic above the completed input and output transient waveforms." width="100%">
    </picture>
  </a>
  <br>
  <sub>A real simulation in the native desktop. The README preview follows your light or dark theme.</sub>
</p>

## Explore the workspace

Start with a small circuit, or bring an existing open design. Local design work needs no account or hosted service. The native `.icproj` format keeps editable documents and revision-linked evidence together.

<table>
<tr>
<td width="33%" valign="top">
<h3>Draw the circuit</h3>
<p>Capture devices and wires, create custom symbols, and build reusable cell hierarchies.</p>
<a href="docs/UPDATE_0.12.md">Schematic and symbol tools →</a>
</td>
<td width="33%" valign="top">
<h3>Explore its behavior</h3>
<p>Run ngspice analyses, inspect waveforms, and compare measurements across testbenches and corners.</p>
<a href="docs/PROFESSIONAL_WORKFLOWS.md">Simulation and studies →</a>
</td>
<td width="33%" valign="top">
<h3>Shape the layout</h3>
<p>Edit physical geometry, route connections, place arrays, and inspect a layer stack in 3D.</p>
<a href="docs/PRIORITIES_0.22.md">Layout workflows →</a>
</td>
</tr>
<tr>
<td valign="top">
<h3>Connect both views</h3>
<p>Cross-probe linked objects and review device, parameter, and geometry changes before applying them.</p>
<a href="docs/WORKFLOW_REVIEW_0.22.md">Linked design review →</a>
</td>
<td valign="top">
<h3>Use open processes</h3>
<p>Start with included SKY130 and GF180 simulation models, or register a compatible PDK revision.</p>
<a href="docs/PDK_GUIDE.md">PDK setup →</a>
</td>
<td valign="top">
<h3>Work together</h3>
<p>Share editing sessions, discuss checkpoints, compare revisions, and attach simulation evidence.</p>
<a href="docs/LIVE_COLLABORATION.md">Collaboration →</a>
</td>
</tr>
</table>

### One cell. Both views.

Switch between **Schematic**, **Layout**, and **Linked views** while staying in the same cell. Import an existing schematic, attach its physical hierarchy, and inspect the design at the level that matters.

[![The real SKY130 overvoltage detector's level_shifter cell, with its native schematic and imported physical layout side by side.](docs/images/readme/overvoltage-linked.png)](docs/OPEN_PROJECTS.md)

<sub>The level shifter from the Apache-2.0 overvoltage design by the Von Braun Labs contributors. Cell-view attachment and device-level LVS correspondence are separate. [Source, attribution, and reproduction](docs/OPEN_PROJECTS.md).</sub>

### Inspect the layers in 3D

Orbit, pan, zoom, hide layers, adjust display heights, or separate the stack with an exploded view. Export a PNG when you want to share what you see.

[![IC Design Studio's 3D viewer displaying the imported SKY130 level shifter, with layer visibility and display-height controls.](docs/images/readme/overvoltage-3d.png)](docs/LAYOUT_3D.md)

<sub>Actual app capture of the same imported cell. This read-only extrusion uses illustrative display heights; it is a geometry inspection view, not a fabrication cross-section. [3D viewer guide](docs/LAYOUT_3D.md).</sub>

### Review a design together

Share a schematic or layout session, save a named checkpoint, and discuss the exact revision. Reviewers can reply, resolve discussions, and record decisions; completed runs can travel with their saved inputs.

[![Team review in a local two-client demonstration: a named checkpoint, a reviewer question, the designer's threaded reply, and a revision-specific approval.](docs/images/readme/team-review.png)](docs/WORKFLOW_REVIEW_0.22.md)

<sub>A local demonstration with two desktop clients. [Live editing](docs/LIVE_COLLABORATION.md) · [Review roles and discussions](docs/WORKFLOW_REVIEW_0.22.md).</sub>

See the [component browser, bulk layout placement and floating-panel update](docs/USABILITY_FEEDBACK.md) for the latest development-source interaction improvements.

### A comfortable place to design

Use the searchable example gallery to get moving, then arrange the workspace around your circuit. Dark and light themes, dockable panels, named workspaces, and command search keep frequently used tools close.

<table>
<tr>
<td width="50%" valign="top">
<a href="docs/GETTING_STARTED.md"><img src="docs/images/readme/example-gallery.png" alt="The example gallery with nine guided circuits, setup requirements, and expected results." width="100%"></a>
<p><strong>Learn with a working circuit.</strong><br>Each gallery example opens as an independent copy with its analysis and next steps ready.</p>
</td>
<td width="50%" valign="top">
<a href="docs/PRIORITIES_0.22.md"><img src="docs/images/readme/overvoltage-layout.png" alt="The imported level shifter in the layout editor, with searchable mask layers and the drawing toolbar." width="100%"></a>
<p><strong>Give the layout room.</strong><br>Search and filter layers, control hierarchy depth, and hide panels when you need more canvas.</p>
</td>
</tr>
</table>

## Start in three steps

1. **Open the app.** Use the [download guide](docs/DOWNLOADS.md), or run from source below.
2. **Choose “Your first waveform.”** Open a copy from the example gallery. This RC circuit uses the included educational solver, so no external simulator or PDK is needed.
3. **Press F5.** Inspect the waveform, change a value, run again, and save your project with **Ctrl+S**.

| Your next step | Where to go |
|---|---|
| Try another circuit | [Nine guided examples](examples/README.md) |
| Use real transistor models | [Open PDK setup](docs/PDK_GUIDE.md) |
| Bring an existing design | [Xschem, Magic, and KLayout exchange](docs/INTEROPERABILITY.md) |
| Find a command | **Ctrl+K** |
| Switch the active view | **Alt+1** schematic · **Alt+2** layout · **Alt+3** linked |
| Restore panels | **Window → Reset workspace** |

<details>
<summary><strong>Run from source</strong> · Python 3.12</summary>

**Windows:** install 64-bit Python 3.12, extract the source to a short path such as `C:\ICStudio`, and double-click `launch-windows.bat`. The launcher creates an isolated environment under `%LOCALAPPDATA%\ICStudio`, downloads and verifies the pinned ngspice runtime, and checks dependencies and a real simulation before opening the app.

**Linux / macOS:**

```sh
git clone --branch experimental https://github.com/jonahsaunders/IC-Design-Studio.git
cd IC-Design-Studio
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/check_simulation_assets.py
python main.py
```

For ngspice analyses, install the native engine and select it in **Tools → Engine diagnostics and paths**, or set `ICSTUDIO_NGSPICE`. On Ubuntu, use `sudo apt install ngspice`; on macOS, use `brew install ngspice`. Magic and Netgen are additional tools for physical verification.

Windows packages include Python, Qt, ngspice, and the bundled simulation subsets. See [downloads](docs/DOWNLOADS.md) for published assets and [release status](docs/RELEASE_STATUS.md) for platform acceptance. macOS is a source workflow awaiting qualification.

</details>

## Feature reference

Expand a category for the detailed inventory. Features requiring an external engine, a technology mapping, or a supported import subset are identified in their guides.

<details>
<summary><strong>Schematic capture, symbols, and hierarchy</strong></summary>

| Capability | Included tools |
|---|---|
| Circuit drawing | Device placement; repeated placement; manual wires; labels and ground; annotations; rotation, mirroring, duplication, and bulk parameter editing |
| Electrical editing | Connection-preserving stretch; explicit move; wire cut/rejoin; junction control; full-net inspection; terminal inspection; scalar bus connections |
| Custom symbols | Generated or hand-edited artwork; lines, polygons, and text; pin identity, direction, and ordering; symbol properties |
| Reusable circuits | Named cells and ports; hierarchy navigation; make a cell from a selection; cell and instance parameters; schematic, symbol, and layout views |
| Editing controls | Selection filters; coordinate editing; capture profiles and keyboard commands; preview/cancel; undo/redo; Check and Save |

[Capture guide](docs/UPDATE_0.12.md) · [User guide](docs/USER_GUIDE.md)

</details>

<details>
<summary><strong>Simulation and waveform analysis</strong></summary>

| Capability | Included tools |
|---|---|
| Analyses | Built-in educational solver; native ngspice operating point, transient, DC sweep, AC response, and noise; graphical source/output/temperature configuration |
| Existing simulation programs | Supported imported SPICE control programs; analysis tables and measurements; saved programs and original source retention; optional first-point DC voltage guesses |
| Run management | Queued and cancellable runs; progress and logs; immutable saved inputs; failed-run inspection; rerun from saved input; revision-aware history |
| Waveform inspection | Voltage and current traces; pan/zoom and fit; X/Y markers; exact-coordinate and threshold inspection; previous-run comparison |
| Calculations and export | Saved multi-panel plots; complex AC arithmetic, phase and dB; FFT for uniform time samples; derivatives and integrals; RMS, peaks, crossings, settling, frequency, and delay measurements; schematic readouts; CSV export |

[Simulation setup](SIMULATION_SETUP.md) · [Native analyses](docs/UPDATE_0.20.md) · [Waveform tools](docs/UPDATE_0.16.md)

</details>

<details>
<summary><strong>Testbenches, characterization, and design studies</strong></summary>

| Capability | Included tools |
|---|---|
| Reusable tests | Saved circuit testbenches; configured analyses and stimuli; repeatable measurements; specification limits and pass/fail results |
| Variation | Parameter sweeps; process/voltage/temperature matrices; seeded Monte Carlo parameter variation; technology-declared statistical bindings; individual case review, editing, and enable/disable controls |
| Exploration | Finite-difference sensitivity; bounded sampled parameter search; review and undo when applying a candidate |
| Verification plans | Multiple tests and operating conditions; parallel job execution; saved-input resume/retry; baseline deltas; requirement matrices, margins, and distributions; CSV reports |
| Physical comparison | Schematic versus post-layout measurements; extracted-SPICE testbenches; retained DRC/LVS stages and failure evidence |

Monte Carlo varies declared parameters; it does not imply foundry statistical mismatch qualification. Parameter search evaluates bounded samples.

[Test plans](docs/PROFESSIONAL_WORKFLOWS.md) · [Studies and search](docs/UPDATE_0.20.md)

</details>

<details>
<summary><strong>Layout drawing, routing, and placement</strong></summary>

| Capability | Included tools |
|---|---|
| Drawing | Rectangles; polygons with holes; paths; reference-point move/copy; edge stretch; vertex editing; rotation; precise transforms |
| Geometry operations | Union, subtraction, intersection, and XOR; sizing; chopping; area erase; alignment and distribution |
| Canvas controls | Configurable grid spacing, origin, appearance, and snapping; object snapping; Manhattan/45°/free paths; rulers; layer search, visibility, selection, locks, and fills |
| Hierarchy | Physical cells and regular arrays; reusable masters; edit in context; hierarchy depth; flattening; concrete parameter variants |
| Connections | Manual vias and previewed Autovia arrays in selected conductor overlaps; coordinate and linked-terminal routing; saved route constraints; route preview; terminal and cell-port assignment; connected path editing |
| Analog placement | Common-centroid, matching, symmetry, and spacing constraints; declared-rule resistor/capacitor/MOS/contact/guard-ring generators; supported PDK device recipes and analog reference layouts |

**Autovia:** select overlapping metal shapes, choose **Autovia**, review the preview, then choose **Place vias**. Manual placement and Autovia use the project's configured layers, including imported SKY130 layouts. [Via placement guide](docs/LAYOUT_VIAS.md).

[Drawing](docs/DRAWING_0.22.md) · [Layout tools](docs/PRIORITIES_0.22.md) · [Layout editor reference](docs/UPDATE_0.11.md) · [Parametric geometry](docs/UPDATE_0.16.md)

</details>

<details>
<summary><strong>Linked design and 3D inspection</strong></summary>

| Capability | Included tools |
|---|---|
| Schematic/layout connection | Linked device footprints; cross-probing; whole-net highlighting; terminal connectivity; device mapping audits |
| Design changes | Missing/changed device review; resolved parameter variants; geometry proposals; route impact; before/after comparison; one-step application and undo |
| Workflow inspection | Active circuit or saved-testbench status; device links; missing connections; matching findings; stale-result identification; next-action navigation |
| 3D geometry | Extruded active cell or cropped viewport; nested instances and arrays; paths and holes; orbit/pan/zoom; isometric/top/front presets |
| 3D presentation | Layer visibility; editable display elevation/thickness; vertical scale; exploded views; refresh after edits; PNG export |

[Linked workflow](docs/WORKFLOW_REVIEW_0.22.md) · [3D viewer and display-height scope](docs/LAYOUT_3D.md)

</details>

<details>
<summary><strong>Verification and parasitic comparison</strong></summary>

| Capability | Included tools |
|---|---|
| Native checks | Configurable electrical rule checks; declared geometry rules; grid, width, spacing, and enclosure findings; live checks; revision-specific waivers |
| Connectivity | Physical net inspection; opens/shorts and terminal mapping; cross-probing; navigable findings |
| External engines | Configured external rule jobs; pinned Magic DRC/extraction and Netgen LVS flows; KLayout extraction and LVS report navigation |
| Parasitics | Ground-capacitance estimation; declared distributed interconnect RC and same-layer coupling; coupon calibration; baseline and specification comparison |
| Evidence | Saved decks, tool/model revisions, checksums, logs, reports, measurements, and deliberate-fault regression fixtures |

Native rules and RC estimates use declared technology data. Foundry qualification is limited to the exact processes and fixtures in the evidence; see the [qualification guide](docs/QUALIFICATION_0.22.md).

[Physical workflows](docs/PROFESSIONAL_WORKFLOWS.md) · [RC estimation scope](docs/UPDATE_0.16.md) · [External verification](docs/INTEROPERABILITY.md)

</details>

<details>
<summary><strong>PDKs, libraries, and external file exchange</strong></summary>

| Capability | Included tools |
|---|---|
| Technology management | Bundled SKY130/GF180 simulation subsets; installed PDK discovery; package registration; device catalogs; corners; immutable revisions and dependency checksums |
| Project bindings | Explicit device/terminal/layer/model mappings; PDK folder relinking; reviewed revision migration; compatibility and qualification status |
| Xschem | Dependency and hierarchy review; migration to editable native cells; supported array expansion; custom-library resolution; export and reviewed reimport; archived source material |
| External Xschem execution | Installed-engine netlisting for vector buses and Tcl-driven formats, with captured configuration and provenance |
| Physical exchange | GDSII/OASIS import/export; hierarchy, transforms, arrays, and text; reviewed external changes; original-file recovery; Magic workspace import/export; layout-to-schematic attachment |
| Other handoffs | Supported SPICE circuit/component import and deck export; saved testbench export; structural Verilog export; project folders; reproducible handoff bundles |

[PDK guide](docs/PDK_GUIDE.md) · [Exchange guide](docs/INTEROPERABILITY.md) · [Import a real project](docs/OPEN_PROJECTS.md)

</details>

<details>
<summary><strong>Live collaboration and team review</strong></summary>

| Capability | Included tools |
|---|---|
| Sharing | Local shared-folder workspaces; local or encrypted network hosting; invitations; owner/editor/reviewer/viewer roles |
| Joint editing | Shared schematic/layout changes and hierarchy; presence; object reservations; concurrent-edit conflict review; personal undo |
| Checkpoints | Named immutable revisions; visual schematic/layout comparison; object, terminal, net, and finding attachments |
| Discussion | Threaded comments and replies; resolve/reopen; checkpoint-specific approvals and decisions; read-only review roles |
| Shared evidence | Attach completed simulation or physical runs; inspect saved inputs; rerun locally with matching tools and PDKs |
| Recovery | Durable retry of submitted review actions across restart; retained conflict edits; server persistence and backups |

General offline design-edit queuing remains planned. [Collaboration limits and hosting](docs/LIVE_COLLABORATION.md) · [Team review](docs/WORKFLOW_REVIEW_0.22.md) · [Review recovery](docs/REVIEW_RECOVERY.md)

</details>

<details>
<summary><strong>Projects, workspace, recovery, and developer tools</strong></summary>

| Capability | Included tools |
|---|---|
| Project organization | Project Hub; create/open/rename/duplicate; independent example copies; project/cell/view browser; search; portable native JSON documents |
| Workspace | Dark/light themes; dockable and floating panels; saved window arrangements; focused canvas; command palette; keyboard profiles; searchable help |
| Persistence | Undo/redo; session recovery snapshots; previous valid recovery state; pending/failed-write status and retry; protection against overwriting externally changed files |
| Setup | Engine diagnostics and paths; simulation runtime configuration; PDK checks; Windows source launcher; desktop packaging workflows |
| Automation and extension | Source CLI workflows; reproducible qualification and benchmark scripts; documented trusted local plugin example in source mode |

[Project Hub](docs/PROJECT_HUB.md) · [Recovery and editing](docs/STABILITY_0.22.md) · [Architecture](docs/ARCHITECTURE.md) · [CLI and plugin scope](docs/USER_GUIDE.md)

</details>

## Work with real open designs

| Project | Explore | Evidence |
|---|---|---|
| **SKY130 overvoltage detector** | Hierarchical schematic, attached Magic layout, and a portable native DC testbench with embedded models | Strict full-circuit LVS with the pinned extraction correction; all 16 HSA trip codes and three deliberate fault controls. [Reproduce it](docs/OPEN_PROJECTS.md) |
| **GF180 bandgap reference** | A quick startup run, a six-case compatibility circuit, or the original 144-analysis characterization | Schematic/simulation compatibility across captured, native, and exported paths. [Project guide](docs/BANDGAP_COMPATIBILITY.md) |
| **SKY130 transistor inverter** | Transistor-level Xschem import and switching behavior with included models | Simulation example plus separate pinned physical fixtures. [Examples](examples/README.md) · [Physical reference](docs/SKY130_REFERENCE.md) |
| **Native analog references** | Current mirror, differential pair, and amplifier designs; saved operating-point/AC tests and corner comparisons | Bounded SKY130 simulation and physical flows with deliberate defects. [Engineering guide](docs/PROFESSIONAL_WORKFLOWS.md) |

**Opening the overvoltage bench:** follow the reproduction guide to obtain `overvoltage-bench.icproj`. It opens on `detector_dc_bench` for **F5** simulation. For the embedded layout, select **`sky130_vbl_ip__overvoltage` → Linked views**, or choose **`level_shifter`** for a detailed view. The separate `overvoltage.icproj` opens the bare DUT.

## Open PDKs, explicit revisions

Choose the circuit and technology in **File → Project Hub**. Register included packages offline, discover existing installations, or select a PDK folder. Projects retain the chosen revision and dependency checksums.

| Process | Available path | For additional workflows |
|---|---|---|
| **SkyWater SKY130** | `sky130A/B` adapters; included `sky130A` simulation subset | Matching physical decks and engines for layout verification |
| **GlobalFoundries GF180MCU** | `gf180mcuA/B/C/D` adapters; included simulation subset | Corresponding physical rule decks |
| **IHP SG13G2** | Installed `ihp-sg13g2` adapter | Compatible ngspice and compiled OSDI models |
| **Custom technology** | Checksummed package interface | Explicit terminal, layer, model, and verification bindings |

Bundled simulation subsets contain models and symbols; full physical flows need additional PDK assets. [Set up a PDK](docs/PDK_GUIDE.md) · [Simulation runtime](SIMULATION_SETUP.md) · [Third-party sources](THIRD_PARTY_NOTICES.md)

## Project status

**0.22.0.dev21 is an engineering preview.** The [workflow and recovery update](docs/UPDATE_0.22_DEV21.md) adds component favorites and recent choices, a persistent design workflow, selection previews, unsent review drafts, faster recovery snapshots and identifiable experimental packages. [Release status](docs/RELEASE_STATUS.md) records what has actually run and which desktop packages have been published.

The [roadmap](docs/ROADMAP.md) tracks consumer Windows/Linux acceptance, physical LAN/VPN testing, broader PVT/transient and real-project coverage, larger editing/recovery workloads, and offline collaboration. A passing fixture qualifies that recorded case; it does not establish arbitrary-design or fabrication signoff. Source-to-GDS warnings for the detector remain documented.

## Contribute and verify

Bring a small failing circuit, a reproducible PDK fixture, a usability improvement, or a focused fix. [CONTRIBUTING.md](CONTRIBUTING.md) explains the code map and review process.

```sh
python -m unittest discover -s tests -v
python scripts/check_release.py
```

[Desktop builds](.github/workflows/build-desktop.yml) · [External interoperability](.github/workflows/interoperability.yml) · [Physical qualification](.github/workflows/physical-qualification.yml) · [Screenshot sources](docs/images/readme/README.md)

<p align="center">
  <br>
  <strong>Open tools. Your design.</strong><br>
  <sub>Built with Python, Qt, KLayout, and the open circuit-design ecosystem.</sub><br>
  <sub><a href="LICENSE">GPL-3.0-or-later</a> · <a href="THIRD_PARTY_NOTICES.md">Third-party licenses and source</a> · <a href="docs/INDEX.md">Read the docs</a></sub>
</p>
