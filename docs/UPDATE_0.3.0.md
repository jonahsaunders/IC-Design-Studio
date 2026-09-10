# IC Design Studio 0.3.0

This update adds working design and analysis workflows to the standalone native desktop application. It remains an engineering preview. It does **not** complete every requirement or professional-release gate in the supplied blueprint.

## Added in this update

| Area | Working additions | Practical boundary |
|---|---|---|
| Schematic reuse | Native vector symbol editor; scoped cell parameters and per-instance overrides; safe arithmetic expressions | Three vector primitives; expressions use basic arithmetic; parameterized SPICE exports resolve and flatten instances |
| Circuit organization | Named bus expansion and pin assignment; editable annotations; structural Verilog export | Named scalar bus nets rather than a bus/tap drawing system; analog primitives are Verilog black boxes |
| Simulation studies | Parameter sweeps, declared PVT combinations, seeded tolerance Monte Carlo, per-case snapshots, measurements, CSV and run navigation | User-declared independent tolerances; no bundled foundry statistical models or correlated mismatch flow |
| External simulation | Locked PDK model includes and device bindings; temperature settings; ngspice device noise; explicit extracted SPICE testbench execution | Models and complete testbenches must be supplied; model qualification remains process-specific |
| Physical hierarchy | Reusable recipe-backed cells, regeneration, physical instances and arrays; move, rotate, duplicate and delete; hierarchical GDSII/OASIS export | Generic generators; no general import of third-party PCell code |
| Physical editing | Clearance-checked Manhattan route suggestions; rectangular erase; common-centroid placement and centroid checks | Same-layer routes with up to two bends; no full constraint solver, automatic multilayer routing or continuous paint brush |
| Physical verification | Background DRC; real conductor-contact checks for opens, shorts and explicit terminal assignments; clickable findings | Terminal connectivity is not mask-based device extraction or foundry LVS |
| Parasitics | Ground-capacitance estimates from area/perimeter coefficients; immutable post-layout estimate simulations; pre/post comparisons | Estimates omit coupling and distributed resistance; coefficients require calibration |
| Extraction engines | Separate Magic LVS and RC extraction profiles; retained scripts, logs, deck and input hashes | Profile construction tested; actual Magic/foundry extraction was unavailable for qualification |
| PDK management | Checksummed local packages, side-by-side revisions, activation/rollback, locked model assets and explicit pin/unit bindings | No automatic open_pdks build/download, complete dependency resolver, OpenVAF compilation or foundry package qualification |
| Project persistence | Atomic per-cell snapshot folders and dependency locks; recent saved-run recovery | Folder snapshots are explicitly published; old snapshots are retained without garbage collection |
| Interoperability | XOR-based layout change review before applying edits; bounded import of edited Studio-generated Xschem packages | Changed layout geometry is flattened; text edits need review; arbitrary Xschem libraries and complete destination-tool round trips remain open |
| Responsiveness | Bounding-volume index for layout viewport and hit queries; physical checks run in workers | No accelerated canvas, hierarchical index, million-shape GUI benchmark or certified frame/latency result |
| Automation | CLI commands for studies, extraction, estimates, project folders, PDKs, routing and Verilog; physical checks exposed through RPC | Manual local/remote shell execution; no managed remote scheduler or WSL setup |

The desktop keeps the dark default, slimmer component artwork, grouped inspector and on-demand results. New commands are grouped under Schematic tools, Physical cells, Routing and terminals, Project folders, and Physical verification and extraction, and are searchable with Ctrl+K.

## Try it

1. Open the normal RC example, choose AC in Analysis, then use **Analysis → Parameter sweep / PVT / Monte Carlo**. Sweep `R1.value` through `5k, 10k, 20k` and measure `vout`.
2. Inspect the Studies table and open a selected case waveform. Export its table as CSV.
3. Open `examples/physical_rc.icproj`. Run **Physical terminal connectivity**, then **Estimate ground capacitance** and **Simulate with estimated parasitics**.
4. Create a reusable layout cell from **Design → Physical cells**, place an array in another cell, and regenerate the source cell.
5. Use **Design → Schematic tools → Edit active cell symbol** to draw a reusable cell’s artwork and place its declared pins.
6. The example `examples/pdk-educational/package.json` demonstrates a local checksummed technology package. Its models and capacitance coefficients are explicitly educational.

Detailed controls, file formats, command examples and limitations are in `docs/WORKFLOWS_0.3.md`, also included in searchable in-app help.

## Validation performed

- **50 core tests passed**, including new parameter scoping, unsafe-expression rejection, immutable studies, deterministic tolerances, temperature/model gates, interrupted folder saves, PDK tampering, physical hierarchy/array export, exact routing/erase geometry, opens/shorts, stale extraction protection, unlabeled-conductor mapping, import review, Xschem continued edits and spatial queries.
- Existing desktop interaction, usability and dark-mode/job-state tests passed.
- New native end-to-end checks passed for submitting a study form, opening a case waveform, background physical checks, extraction estimates, post-layout simulation, an actual missing-conductor failure, physical instance edits, drawing/saving a symbol, study cancellation and saved-run recovery.
- Actual **ngspice 42** runs checked resistor noise against its analytic density, checksummed model loading, four supply-voltage/temperature cases and an explicit external SPICE testbench.
- The rebuilt standalone Linux executable passed startup, a three-case study and a post-layout estimate simulation without the development Python environment.
- Dark desktop screenshots were inspected. Tests used native Qt’s offscreen platform on the Linux host.

Magic command-profile tests use a fixture runner. They are not evidence of successful Magic extraction. The new physical connectivity tests do not establish device recognition, foundry LVS or fabrication signoff. Windows execution remains unverified.

## Still unfinished from the blueprint

These remain real development and qualification tasks; this update does not relabel them as completed:

| Requirement | Remaining work |
|---|---|
| Qualified SKY130, GF180MCU and IHP flows | Supply/build pinned packages; bind and validate the selected device/voltage/process options; run actual simulator, DRC, LVS, extraction and post-layout golden fixtures |
| Verilog-A / OpenVAF / OSDI | Compile and distribute compatible model binaries; check engine/OS/architecture compatibility; qualify testbenches and statistical coverage |
| Full physical verification | Qualified mask-based device recognition, device parameter comparison, complete rule decks, foundry parasitics and regression evidence; integrate reviewed extraction mappings |
| Native import fidelity | General Xschem parser/symbol resolver, opaque graphics preservation in destination files, hierarchy-preserving external layout import, editable third-party PCells, general Magic/CIF import and destination-GUI regressions |
| Advanced design editing | Full bus/tap editor, advanced ERC, arbitrary symbol primitives, general analog matching constraints, multilayer assisted routing, vias and continuous paint editing |
| Architecture | C++20/Qt Quick migration if retained as a project requirement, accelerated rendering, true 64-bit geometry throughout, hierarchical spatial indexing, level of detail and remaining geometry work off the UI thread |
| Extension platform | Versioned format/simulator/verification/PDK/PCell/UI provider interfaces, stable C++ APIs, capability enforcement, dependency contracts and operating-system file/network sandboxing |
| Managed workers | WSL installation/configuration, remote transport/scheduling, asynchronous remote job lifecycle, restart policies and platform-specific process cleanup qualification |
| Windows and distribution | Actual Windows builds and testing, signed installers/updates, rollback, X11/Wayland and selected Linux compatibility; high-DPI and accessibility coverage |
| Professional release evidence | One-million-shape benchmark on the declared reference PC, latency/fps measurements, full crash/recovery campaign, external designer pilots, license/source review and every advertised PDK/tool/OS regression |

The first foundry target in the blueprint is still a pinned SKY130 inverter flow. Completing that gate requires the actual selected PDK/model/rule/extraction assets and execution on the intended Windows/Linux environments. No such foundry qualification or signed release is claimed here.

## Install/update

**Windows source launcher:** extract `IC-Design-Studio-0.3.0-Source.zip` into a new folder and run `launch-windows.bat` with 64-bit Python 3.12 installed. The launcher installs its pinned Python dependencies on first use. Open saved `.icproj` files through File → Open project. This package is source with a launcher, not a prebuilt Windows executable.

**Linux standalone:** extract `IC-Design-Studio-0.3.0-Linux-x86_64.tar.gz`, keep `_internal` next to `ICDesignStudio`, and run the executable. The bundle targets Ubuntu 24.04 x86_64 / glibc 2.39 or newer and contains its Python/Qt runtime.

Existing 0.2 projects load without a required migration. Earlier application versions do not provide the newly added editing features. Save a copy before moving a new-feature project back to an older version.

## Implementation references

- KLayout cell instances: https://www.klayout.de/doc-qt5/code/class_CellInstArray.html
- KLayout polygon regions: https://www.klayout.de/doc-qt5/code/class_Region.html
- ngspice manual and documentation: https://ngspice.sourceforge.io/docs.html
- Magic extraction profiles: https://opencircuitdesign.com/magic/commandref/ext2spice.html
- Magic distributed resistance extraction: https://opencircuitdesign.com/magic/commandref/extresist.html
