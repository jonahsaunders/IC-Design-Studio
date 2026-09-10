# Architecture additions in 0.8

The existing schema 1 gains optional project `testbenches` and cell `layout_ports`. Older projects remain readable. A saved bench identifies its fixture cell, one DUT instance, analysis, initial conditions, observed nets and measurement definitions. `testbenches.py` validates these references and generates the same fixture around the native or extracted circuit. `testbench_ui.py` owns its native editor. Bench changes participate in the design digest and undo history.

`physical_cells.py` links each physical placement to a schematic X instance, derives parent terminal coordinates from transformed child ports, maps nets while rendering hierarchy, and audits missing/duplicate placements and parameter variants. `ring_oscillator.py` reuses one inverter layout three times. `sky130_fingers.py` adds alternating shared source/drain diffusion with total W distributed over nf gates. Recorded source recipes are separate from proof of physical correctness.

`hierarchical_flow.py` runs the selected DUT hierarchy through independent Magic, Netgen and ngspice stages. The schematic LVS reference is numerically flattened to resolve cell parameters; the native project, GDS and extracted subcircuits retain physical hierarchy. Every saved fixture is reused unchanged for both simulations. Worker publication validates the selected fixture or DUT cell ID and design hash even when the user starts the job from a different view.

`hierarchy_ui.py` adds the testbench manager, linked placement/port actions, parent navigation, transforms, vertex editing and terminal routing. GDSII/OASIS property 126 stores `icstudio:<instance-id>` to preserve placement links through supported external edits. Without that marker, exact cell/transform matching can recover existing placements; unmatched instances require explicit relinking. Generic imports retain the existing review and format limits.

The older architecture sections below are historical. The current bounded physical flow includes actual DRC/LVS and extracted capacitance; it does not provide fabrication signoff, distributed resistance extraction or complete KLayout/Xschem parity.

# Manual wiring in 0.3.1

`wiring.py` resolves stored orthogonal polylines, explicit junctions and named pin labels into electrical nets. Validation, flattening, SPICE, jobs and native project persistence use that model. Interior crossings remain separate; branch and terminal contacts join. Legacy conversion checks preservation of the prior nets before accepting inferred geometry. `wire_canvas.py` owns click/bend gestures, snap targets and cached wire rendering; `schematic_ui.py` owns undoable wire/device transactions and shared keyboard actions. This supersedes older descriptions of net-name-only wiring below.

# Architecture additions in 0.3

`design_ops.py` adds safe parameter resolution, bus expansion, structural Verilog and physical hierarchy traversal. `symbol_editor.py` provides the native reusable-symbol drawing pad. `spatial.py` implements an immutable bounding-volume index used for physical viewport and hit queries. The core remains PySide6/Qt Widgets with the existing C++ numerical helper; this is not a C++/Qt Quick rewrite or a 64-bit geometry migration.

`studies.py` runs immutable parameter/PVT/tolerance cases through the existing simulators and writes per-case inputs/results. `physical.py` performs routing collision checks, recipe regeneration, geometric terminal connectivity and explicit-coefficient ground-capacitance estimates. `workflow_jobs.py` exposes DRC/connectivity/extraction estimates in the existing cancellable process protocol. `feature_ui.py` connects these workflows to grouped native menus and results. A saved package/source hash identifies the workflow implementation.

`project_store.py` commits content-addressed per-cell snapshots through one atomic manifest. `pdks.py` verifies local technology packages and model dependencies. `import_review.py` produces an explicit geometry change proposal using XOR; `xschem_io.py` imports continued edits to known generated packages and rejects unsupported symbol changes. `feature_cli.py` exposes the additional workflows for automation.

The original architectural details below describe the 0.2 baseline. Their statements that spatial indexing, PDK model binding, per-cell snapshots or parasitic estimates are absent are superseded by this section; the limits on foundry verification, untrusted plugin isolation, 32-bit geometry and platform qualification remain.

---

# Architecture and extension contracts

`model.py` owns schema 1. A History transaction copies the current snapshot, applies a command, validates invariants, and publishes a revision. Failed validation leaves the current project unchanged. Undo/redo publishes a new monotonic revision. Design hashes exclude waiver/review timestamps so review-only metadata does not change the circuit identity. Result revision comparison remains conservative after undo.

`canvas.py` paints each viewport on one native QWidget, with no DOM or browser. It culls objects outside the viewport but scans the object list; a large-layout spatial index is not implemented. Shapes store integer nanometres and layer names; schematic positions use drawing units. Cell/device IDs remain separate from display names.

`simulation.py` builds modified nodal equations for RLC circuits and independent sources. MOS devices contribute finite-difference derivatives of an elementary square-law drain-current function. Newton iteration uses step damping. DC, operating point and backward-Euler transient systems call `native/solver.cpp` via a narrow C ABI when present; complex AC/noise systems use the Python Gaussian-elimination path. Each backend checks pivots and reports singular systems. This is an educational engine, not an ngspice replacement.

`worker.py` is launched as a child process by QProcess, including in the frozen app. It consumes a JSON snapshot and settings, emits JSON progress lines, and atomically writes result JSON. The GUI never mutates that snapshot. Cancellation terminates the worker; Windows uses taskkill on its process tree. External engine calls use argument arrays with shell disabled. Engine jobs have timeouts. Rule decks remain trusted code and are not sandboxed.

`interchange.py` emits explicit pin-ordered decks and native KLayout geometry files. Sidecars restore richer data only when the exported file hash still matches. A changed external file becomes a new layout-only imported project. Preservation limits are data in exported reports, not hidden assumptions. File manifests and release archives use conventional SHA256 checksums.

`layout.py` delegates exact Boolean geometry, hole handling and basic width/spacing checks to KLayout. Model links are not extracted connectivity. There is no PDK signoff or parasitic extractor.

## CLI / automation

Examples:

```sh
python main.py --cli simulate examples/rc.icproj --analysis ac --set start=100 --set end=1meg --output run.json
python main.py --cli export examples/rc.icproj --output new-handoff
python main.py --cli plugin plugins/guard-ring.json examples/empty.icproj --output ring.icproj
python main.py --cli rpc
```

In the packaged Linux application, replace `python main.py` with `./ICDesignStudio`.

JSON-RPC 2.0 uses newline-delimited UTF-8 messages on standard input/output. API methods are `capabilities`, `validate`, `simulate`, and `erc`. `simulate` receives an embedded project snapshot, optional cell ID, and optional settings. There is no network listener. Caller termination is the cancellation mechanism for the synchronous RPC process. Error code -32602 is returned for unsupported/invalid requests in this preview.

## Python command SDK

The explicit `plugin` CLI command accepts API 1.0 manifest files that declare capability `commands`. Entry files must resolve inside their package. A separate Python worker receives project JSON and returns a command array. Allowed operations are `add_shape`, `add_device`, and `set_parameter`; all pass the same project validation transaction. The included generator is reproducible except for its fresh object IDs. Third-party code is not imported into the main editor process, but it retains the operating-system permissions of the user. This is not an untrusted-plugin sandbox.

## Build surface

The normal package uses pinned PySide6 Essentials and KLayout wheels. PyInstaller creates a directory bundle so Qt's dynamically loaded libraries remain separate/replacable. The C++20 solver can be rebuilt with CMake or the direct compiler script. Python fallback behavior is tested. No third-party source tree is modified by the application.
