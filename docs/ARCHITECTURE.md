# Architecture and extension contracts

The current application is a Python/PySide6 desktop with native Qt editors,
KLayout geometry and independently executed simulation/verification engines.
The table below describes the experimental source; the versioned implementation
notes afterward retain their original scope.

| Responsibility | Current implementation |
| --- | --- |
| Documents and edits | `model.py`, `document.py`, `design_ops.py`: validated transactions, stable object identities, monotonic revisions and isolated job inputs |
| Native electrical hierarchy | `wiring.py`, `native_vectors.py`: geometric connectivity and ordered bounded bus/array expansion; [semantics](NATIVE_VECTORS.md) |
| Physical hierarchy | `layout_import.py`, `layout_scene.py`, `physical_cells.py`, `physical_variants.py`: hierarchy-preserving imports, spatial queries, linked placements and reviewed parameter-specific masters |
| Analog work | `analog_workspace.py`, `analog_optimizer.py`, `verification_campaigns.py`: saved testbenches, search and durable campaigns; [workflow](ANALOG_CLOSURE.md) |
| Digital work | `digital_workspace.py`, `digital_runtime.py`: RTL documents, simulation/implementation jobs and managed tool setup; [workspace](DIGITAL_WORKSPACE.md) |
| Mixed signal and lessons | `mixed_signal.py`, `student_hub.py`, `student_projects.py`: bounded ngspice/Icarus coupling, lesson documents and evidence-linked progress |
| Recovery | `recovery_snapshot.py`, `recovery_queue.py`, `recovery.py`: isolated snapshots, ordered writes, byte-verified receipts and previous-valid fallback |
| Collaboration | `live_protocol.py`, `live_store.py`, `live_client.py`: protocol 2 transactions and SQLite database 3; `review_outbox.py` and `review_drafts.py` retain submitted requests and unsent text separately |
| Physical engines | `external_tools.py`, `silicon_flow.py`, `hierarchical_flow.py`: included/custom engines, locked process inputs, retained raw results and bounded extraction normalization |
| Automation | `cli.py`, `design_automation.py`, `verification_campaigns.py`: local CLI/RPC, reviewed edit batches and resumable campaign workers |

Rendering caches remain transient. Native schematic/layout data stays separate
from result artifacts, PDK installations, workspace preferences and private
collaboration credentials. Source tests, engine qualification and packaged/native
desktop acceptance are separate evidence categories; see [release status](RELEASE_STATUS.md).

## Historical architecture additions: dev20 and earlier

The following notes explain earlier changes. Statements about unavailable
features describe those versions, not a current capability inventory. Current
physical extraction and parameter variants are documented in
[analog implementation extensions](ANALOG_IMPLEMENTATION_EXTENSIONS.md), and
current editing/recovery in [reliable workflows](RELIABLE_DESIGN_WORKFLOWS.md).

### Dev20 additions

`dc_startup.seed_deck` solves the circuit at the first sweep point in the selected
mode, preserves temperature and user nodesets, and supplies finite voltage hints
for the full DC sweep. The native Analysis panel persists this optional setting.
The original and startup decks, raw results and hints remain in the run directory.
The detector workflow verifies a checksum-bound upstream resistor extraction
backport, compares the flattened physical circuit strictly, and creates an editable
bench with embedded models. No general LVS parser or tolerance is relaxed.

### Dev19 additions

`xschem_libraries.prepare` discovers PDK references through the reachable local
schematic hierarchy. `xschem_vectors` resolves bounded vectors into scalar native
devices after connectivity extraction. `layout_attach` validates a cell mapping
and returns an isolated candidate without replacing schematic identities.
`magic_dependencies` audits the native cell closure before conversion.

`review_outbox` persists one submitted mutation before network dispatch, bound to
server/workspace/actor. The review panel restores it independently of the design
journal and retains the same server idempotency ID. Recovery snapshots still copy
mutable project state before crossing the worker boundary. The selection fast
path only skips ownership grouping when every selected shape is unowned.

The [real-project script](../scripts/qualify_open_project.py) separates import
fidelity, nominal simulation and physical consistency in its evidence schema.
See [open projects](OPEN_PROJECTS.md) and [review recovery](REVIEW_RECOVERY.md).

The existing schema 1 gains optional project `testbenches` and cell `layout_ports`. Older projects remain readable. A saved bench identifies its fixture cell, one DUT instance, analysis, initial conditions, observed nets and measurement definitions. `testbenches.py` validates these references and generates the same fixture around the native or extracted circuit. `testbench_ui.py` owns its native editor. Bench changes participate in the design digest and undo history.

`physical_cells.py` links each physical placement to a schematic X instance, derives parent terminal coordinates from transformed child ports, maps nets while rendering hierarchy, and audits missing/duplicate placements and parameter variants. `ring_oscillator.py` reuses one inverter layout three times. `sky130_fingers.py` adds alternating shared source/drain diffusion with total W distributed over nf gates. Recorded source recipes are separate from proof of physical correctness.

`hierarchical_flow.py` runs the selected DUT hierarchy through independent Magic, Netgen and ngspice stages. The schematic LVS reference is numerically flattened to resolve cell parameters; the native project, GDS and extracted subcircuits retain physical hierarchy. Every saved fixture is reused unchanged for both simulations. Worker publication validates the selected fixture or DUT cell ID and design hash even when the user starts the job from a different view.

`hierarchy_ui.py` adds the testbench manager, linked placement/port actions, parent navigation, transforms, vertex editing and terminal routing. GDSII/OASIS property 126 stores `icstudio:<instance-id>` to preserve placement links through supported external edits. Without that marker, exact cell/transform matching can recover existing placements; unmatched instances require explicit relinking. Generic imports retain the existing review and format limits.

The older architecture sections below are historical. The 0.8 bounded physical flow included actual DRC/LVS and extracted capacitance; later releases added the separately bounded resistance/capacitance and hierarchy paths described above. No flow establishes fabrication signoff or complete KLayout/Xschem parity.

### Manual wiring in 0.3.1

`wiring.py` resolves stored orthogonal polylines, explicit junctions and named pin labels into electrical nets. Validation, flattening, SPICE, jobs and native project persistence use that model. Interior crossings remain separate; branch and terminal contacts join. Legacy conversion checks preservation of the prior nets before accepting inferred geometry. `wire_canvas.py` owns click/bend gestures, snap targets and cached wire rendering; `schematic_ui.py` owns undoable wire/device transactions and shared keyboard actions. This supersedes older descriptions of net-name-only wiring below.

### Architecture additions in 0.3

`design_ops.py` adds safe parameter resolution, bus expansion, structural Verilog and physical hierarchy traversal. `symbol_editor.py` provides the native reusable-symbol drawing pad. `spatial.py` implements an immutable bounding-volume index used for physical viewport and hit queries. The core remains PySide6/Qt Widgets with the existing C++ numerical helper; this is not a C++/Qt Quick rewrite or a 64-bit geometry migration.

`studies.py` runs immutable parameter/PVT/tolerance cases through the existing simulators and writes per-case inputs/results. `physical.py` performs routing collision checks, recipe regeneration, geometric terminal connectivity and explicit-coefficient ground-capacitance estimates. `workflow_jobs.py` exposes DRC/connectivity/extraction estimates in the existing cancellable process protocol. `feature_ui.py` connects these workflows to grouped native menus and results. A saved package/source hash identifies the workflow implementation.

`project_store.py` commits content-addressed per-cell snapshots through one atomic manifest. `pdks.py` verifies local technology packages and model dependencies. `import_review.py` produces an explicit geometry change proposal using XOR; `xschem_io.py` imports continued edits to known generated packages and rejects unsupported symbol changes. `feature_cli.py` exposes the additional workflows for automation.

The original architectural details below describe the 0.2 baseline. Their statements that spatial indexing, PDK model binding, per-cell snapshots or parasitic estimates are absent are superseded by this section; the limits on foundry verification, untrusted plugin isolation, 32-bit geometry and platform qualification remain.

---

### Original 0.2 implementation notes

`model.py` owns schema 1. A History transaction copies the current snapshot, applies a command, validates invariants, and publishes a revision. Failed validation leaves the current project unchanged. Undo/redo publishes a new monotonic revision. Design hashes exclude waiver/review timestamps so review-only metadata does not change the circuit identity. Result revision comparison remains conservative after undo.

In the original baseline, `canvas.py` painted each viewport on one native QWidget and culled by scanning the object list. Current layout hierarchy uses `layout_scene.py` spatial queries and bounded rendering; this earlier description predates that index. Shapes store integer nanometres and layer names; schematic positions use drawing units. Cell/device IDs remain separate from display names.

`simulation.py` builds modified nodal equations for RLC circuits and independent sources. MOS devices contribute finite-difference derivatives of an elementary square-law drain-current function. Newton iteration uses step damping. DC, operating point and backward-Euler transient systems call `native/solver.cpp` via a narrow C ABI when present; complex AC/noise systems use the Python Gaussian-elimination path. Each backend checks pivots and reports singular systems. This is an educational engine, not an ngspice replacement.

`worker.py` is launched as a child process by QProcess, including in the frozen app. It consumes a JSON snapshot and settings, emits JSON progress lines, and atomically writes result JSON. The GUI never mutates that snapshot. Cancellation terminates the worker; Windows uses taskkill on its process tree. External engine calls use argument arrays with shell disabled. Engine jobs have timeouts. Rule decks remain trusted code and are not sandboxed.

`interchange.py` emits explicit pin-ordered decks and native KLayout geometry files. The original sidecar path restored richer data only for unchanged exports. Current exchange metadata additionally supports reviewed changes against the original project; independent imports preserve supported physical hierarchy without inferring schematic links. See [interoperability](INTEROPERABILITY.md). Preservation limits are data in exported reports, not hidden assumptions. File manifests and release archives use conventional SHA256 checksums.

`layout.py` delegates exact Boolean geometry, hole handling and basic width/spacing checks to KLayout. Model links are not extracted connectivity, and this generic geometry layer does not provide PDK signoff. The separate physical flows now provide bounded process and calibrated parasitic extraction; see [extraction scope](ANALOG_IMPLEMENTATION_EXTENSIONS.md#process-rc-integrity).

## CLI / automation

Examples:

```sh
python main.py --cli simulate examples/rc.icproj --analysis ac --set start=100 --set end=1meg --output run.json
python main.py --cli export examples/rc.icproj --output new-handoff
python main.py --cli plugin plugins/guard-ring.json examples/empty.icproj --output ring.icproj
python main.py --cli rpc
```

In the packaged Linux application, replace `python main.py` with `./ICDesignStudio`.

JSON-RPC 2.0 uses newline-delimited UTF-8 messages on standard input/output. Current methods are `capabilities`, `validate`, `simulate`, `erc`, `connectivity`, `parasitics`, and `automation.capabilities`, `automation.inspect`, `automation.preview`, `automation.apply`. `simulate` receives an embedded project snapshot, optional cell ID, and optional settings. This RPC transport has no network listener; the separately launched collaboration service uses HTTP(S). Caller termination is the cancellation mechanism for the synchronous RPC process. Error code -32602 is returned for unsupported/invalid requests in this preview.

## Python command SDK

The explicit `plugin` CLI command accepts API 1.0 manifest files that declare capability `commands`. Entry files must resolve inside their package. A separate Python worker receives project JSON and returns a command array. Allowed operations are `add_shape`, `add_device`, and `set_parameter`; all pass the same project validation transaction. The included generator is reproducible except for its fresh object IDs. Third-party code is not imported into the main editor process, but it retains the operating-system permissions of the user. This is not an untrusted-plugin sandbox.

## Build surface

The normal package uses pinned PySide6 Essentials, PySide6 Addons and KLayout wheels. PyInstaller creates a directory bundle so Qt's dynamically loaded libraries remain separate/replaceable. Generated digital/physical runtimes and VGA assets are additional build inputs; installing Python requirements alone does not create them. The C++20 solver can be rebuilt with CMake or the direct compiler script. Python fallback behavior is tested. Runtime/model sources and retained modifications are identified in [third-party notices](../THIRD_PARTY_NOTICES.md).
