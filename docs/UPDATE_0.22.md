# Layout development — 0.22.0.dev6

Current workflow additions, alignment behavior and validation limits are in [the dev6 guide](PRIORITIES_0.22.md). The performance implementation and measurements below describe dev5 unless a version is explicitly stated.

This source snapshot extends the existing Python/Qt desktop application. It retains the native exchange fixes from [0.21.1](UPDATE_0.21.1.md). It is an engineering preview; the existing 0.21.0 portable binaries do not include these changes.

## Earlier performance priorities 1–5 (dev5)

Version 0.22.0.dev5 completes a bounded implementation of the five performance priorities:

1. **Complete-edit profiling.** `scripts/benchmark_layout_pipeline.py` measures an actual Studio connected move, history, durable recovery, targeted refresh, first paint and live checks. It also verifies recovery by reopening the saved project and captures a separate CPU profile. Results separate first-use setup from subsequent samples. `benchmark-windows.bat` runs it with the existing short-path dependency environment; benchmark Qt settings are isolated from normal application preferences.
2. **Incremental local editing.** Ordinary local, unowned shapes and attached Manhattan leads use a constrained transaction. It copies changed geometry and ancestors, checks the same geometry schema, grid transforms, locks, polygon contact partition and spacing, then stores the exact reversible change. Generated footprints, linked devices, arrays and complex edits retain the general isolated, fully validated transaction. The geometry-only UI refresh preserves the unchanged cell tree, layer controls and circuit. Recovery still writes a complete atomic, fsynced snapshot and retains a verified previous snapshot. It uses compact JSON and a content hash to avoid revalidating an unchanged previous file; recovery reads still fully validate.
3. **Faster viewport rendering.** Consecutive nonoverlapping rectangles with compatible styles are batched. Overlap and patterned translated geometry retain ordered individual drawing. A padded native Qt vector recording replays static geometry during pan and repeated overview paints. Selection, style, zoom, data and DPI changes invalidate it; drag previews and findings remain separate. Pixel tests compare cached and uncached rendering, including overlap, alpha, holes and paths.
4. **Hierarchy-aware viewport queries.** A persistent KLayout database holds one copy of each master and native regular arrays. Only shapes in a padded visible region become drawing rows. Hit-testing, snapping, selection bounds, array identity, net mapping and display depth use that hierarchy. Changed masters are rebuilt independently. The saved project format and export flows remain unchanged.
5. **Incremental connectivity and declared-rule DRC.** Contact edges incident to changed polygons are rebuilt; affected component closure handles both joins and splits. Flat-cell width, spacing, grid and enclosure findings are cached by complete rule-influence components. Changed components use whole polygons in a native region check, avoiding clipped edges. Rule changes invalidate the cache. Hierarchical checks and local-cache failures use complete checks. One serial background worker owns its cache; revision checks reject stale results. Terminal reports use linear grouping instead of repeated whole-shape scans.

The original delta history, drag cache, connected editing, launcher repair and earlier layout features remain included. Arbitrary editing callbacks still receive an isolated working copy and global validation. Undo/redo preserve exact cell data and monotonic revision numbers. Process contracts and locked-asset checks are unchanged.

```sh
python scripts/benchmark_layout_pipeline.py --out pipeline-results
python scripts/benchmark_layout.py --out viewport-results.json
python tests/gui_layout_pipeline.py --out gui-pipeline
python tests/gui_layout_performance.py --out gui-performance
```

On Windows, double-click `benchmark-windows.bat` after installing 64-bit Python 3.12. Results go to a timestamped folder under `benchmark-results`. This entry point is supplied for native measurement; it has not been executed on Windows in this handoff.

Measurements use synthetic 1,000- and 10,000-shape layouts and compact arrays. The pipeline benchmark includes synchronous durable recovery; the Canvas benchmark excludes Studio overhead and solver work. Native Qt/KLayout allocations are excluded from Python allocation measurements. First-use compilation, overview cache rebuilds, general edits and full hierarchical checks remain more expensive than warm local operations. Existing 100-cell, 100,000 expanded-shape and 20,000 conducting-shape limits remain. Local checks do not qualify manufacturing decks, extracted devices or timing. No monitor FPS, Windows/macOS parity or universal latency guarantee is claimed.

The enclosing handoff includes raw samples, CPU profiles, before/after comparisons and GUI evidence under `evidence/development-0.22-dev5/`. Six final-source GUI pixel/hierarchy checks passed. Complete pipeline timing was captured before final renderer refinements and is labeled with its measured hash. Later full-suite, recovery and worker tests encountered host `os.fsync` I/O errors, reproduced by a standalone probe; those durable-I/O gates remain blocked and must be rerun before release qualification.

## Windows source startup repair

Version 0.22.0.dev3 fixes the source launcher's incomplete-install recovery. A failed pip installation previously left `.venv\Scripts\python.exe` behind, causing the next launch to skip setup. The launcher now delegates to a standard-library bootstrap that creates a short, isolated environment under `%LOCALAPPDATA%\ICStudio\venvs`, records readiness only after installation, dependency checks and native imports succeed, and force-reinstalls packages after unfinished setup. The existing project-local `.venv` is preserved. The batch file prefers Python 3.12 and preserves forwarded application arguments.

Seven regression tests simulate subprocess outcomes for interrupted setup, retries, stale readiness, import failures and environment reuse. They are installation-state evidence on Linux, not Windows execution. See the source setup instructions in the [README](../README.md).

## Added capabilities

| Desktop command | Implemented behavior | Boundary |
| --- | --- | --- |
| Layout → Preserve connections on move / stretch | Enabled by default. Translates complete footprints and their terminals, adjusts attached Manhattan path ends, and preserves endpoint and branch contact during segment stretching. | Translation and path stretching only. Complex interior contacts can be rejected. Free geometry mode, rotate, align, Boolean editing and deletion retain their existing behavior. |
| Layout → Multilayer routing → Plan route | Obstacle-derived A* search across declared conductor layers, with automatic via stacks and width/spacing/enclosure checks. | Manhattan routes; declared recipes only; at most 200,000 search nodes through the API, 50,000 by default. Registered native process vias still require locked physical assets. |
| Plan matched pair | Routes two distinct nets and tunes the shorter route within a clear corridor. Reports both centreline lengths and skew. | Tuning requires one straight shorter path. Geometric length does not establish equal delay, resistance, coupling or via count. |
| Shield selected route | Creates two parallel shields and routes both ties to an existing conductor labeled with the reference net. | A straight two-point signal path; no automatic reference-net inference, shielding-effectiveness or RF guarantee. |
| Layout → PCell library | Imports reusable JSON definitions, creates cells, regenerates parameters with stable shape roles/IDs, and reports changed definitions, technology or geometry. | Rectangles, Manhattan paths, bounded repetition and arithmetic. No arbitrary Python/Ruby execution or process device-recognition claim. |
| Layout → Inspection and finishing → Query layout | Searches hierarchical geometry by layer, exact net and minimum area. Reports instance path and location. | Native flattening limit remains 100,000 shapes; at most 5,000 displayed rows by default. |
| Compare against GDSII / OASIS | Compares hierarchical polygon coverage by GDS layer/datatype. Reports exact added/removed area and locatable difference boxes. Copies the reference into the saved job for replay. | Up to 500,000 expanded shapes by default and 256 MB per input. Text, properties, hierarchy structure and electrical equivalence are separate checks. |
| Measure layer density / Insert dummy fill | Measures merged polygon area by tile and inserts square fill with all-layer geometric keepout. | Up to 10,000 tiles or candidate squares. No automatic process density closure or calibrated parasitic control. |
| Round selected corners | Rounds polygon corners, snaps vertices to the project grid, and checks existing physical contact. | Polygon approximation; run DRC afterward. |
| Verify → Run bundled KLayout rules | Snapshots a selected rule folder, preserves relative helper files, checks its hash, and runs from the captured folder. | UTF-8 text dependencies: 256 files, 2 MB each, 16 MB total. External/dynamic dependencies are not discovered automatically. |

## Connected editing

The editor compares actual polygon components before and after an edit. Conductor labels do not create contact. The comparison includes stable identities for hierarchical geometry, physical terminals and named ports; an existing component cannot silently split or join another one. Adjusted conductors must also clear other physical components under the declared layer spacing.

Select complete generated footprints and via stacks. Process terminals and parametric-device terminals follow their owning footprints. Attached local Manhattan paths are retargeted. Stretching keeps route endpoints and branch anchors fixed; repeated branch stretching reuses its lead instead of adding one every time. Unsupported contacts, locked layers, collapsed paths, shorts and failed validation leave the document unchanged. Undo/redo uses the existing document transaction system.

This does not repair a pre-existing open or short, recognize transistor connectivity from diffusion, or replace process LVS. Connected editing is bounded to 20,000 conducting shapes. Use explicit free geometry editing when intentionally changing topology, then verify the result.

## Plan, inspect and install a route

1. Open a small layout and choose **Layout → Multilayer routing → Plan route**. Enter endpoint coordinates in micrometres, endpoint layers, net, width and allowed layers.
2. The existing run queue performs the search in a separate worker. Use its cancellation control if needed.
3. Review the highlighted proposed geometry, shape table, via count and lengths. **Install route** commits all shapes as one undoable operation.
4. If the design or layer locks changed, installation rejects the stale proposal. Plan again. A saved result can be reopened through **Review selected route result**.
5. Run connectivity, process DRC/LVS and the appropriate extraction flow.

Routes require on-grid endpoints and widths divisible by twice the grid, so centred paths and vias remain on-grid. The generic teaching technology declares an M1/VIA1/M2 recipe. Custom technologies must declare matching `connectivity.conductors`, `connectivity.vias` and `routing_vias` entries. A routing via has `name`, `lower`, `cut`, `upper`, integer `size`, and integer `enclosure`, in nanometres. Native SKY130/GF180 recipes use their existing adapter contracts and locked-asset requirements.

## Reusable PCells

Import [metal_comb.json](../examples/pcells/metal_comb.json) through **Layout → PCell library → Import definition**, then choose **Create cell from library**. Its fingers, width, pitch and height are editable integers; geometric dimensions are nanometres. Place the resulting cell with the existing physical cell/array command.

Definitions specify version 1, name/revision, integer parameter bounds/defaults/steps, shape templates with unique roles, and optional named ports. Expressions use braces and support numbers, parameter names, `+`, `-`, `*`, `/`, and repetition index `i`. Repetition is bounded to 256 copies per template and 5,000 generated shapes total. Ports must land on geometry with their own net name.

Definitions are stored inside the native project. Regeneration preserves shape IDs by role, records definition/technology/geometry hashes, and checks affected parent connectivity. Manually edited generated geometry must be restored before regeneration. The catalog example is generic geometry; existing process-specific MOS generators remain separate and retain their current qualification limits.

## Verification and saved evidence

The existing saved-testbench DRC → LVS → extraction → post-layout simulation workflows remain available. This update improves layout input generation and KLayout rule dependency capture; it does not generalize those process flows to every device or add a field solver.

For a bundled KLayout job, select its entry script and dependency folder. Relative file references are resolved from that captured folder. Scripts retain the existing `$input`, `$top` and `$report` interface. The executable hash, bundle contents/hash, exported GDS hash, command, log and report remain with the job. Keep all runtime dependencies inside the selected folder; symbolic links and path traversal are rejected. Zero findings mean only that the chosen script reported none.

GDS/OASIS comparison uses a common exact integer database unit. Incommensurate units are rejected instead of silently rounded. A saved reference checksum is verified on replay, including after the original source is removed. Double-click a difference to locate its bounding box; navigation rejects stale design results. “Added” means present in the reference and absent from the current design.

## Reproduce validation

From the source root with the project dependencies installed:

```sh
python -m unittest discover -s tests -v
python scripts/check_release.py
python scripts/verify_layout_development.py --out layout-validation --gui
```

The last command creates a small route example, executes actual routing and comparison workers, compares equivalent GDS/OASIS files containing 10,000 hierarchical squares, and attempts Qt command/proposal/undo/redo acceptance. Without `--gui`, it explicitly records the GUI case as not run. On a displayless Linux host, set `QT_QPA_PLATFORM=offscreen` when appropriate.

Fresh evidence is included in the enclosing AI handoff. Core regressions and real layout workers ran on Linux with Python 3.12.13 and KLayout 0.30.5. On retry, the missing EGL dependency was installed into the test workspace. Offscreen Linux startup, stale-route rejection, route preview/installation, visible layout navigation and exact undo/redo now pass. The acceptance fixture was corrected to plan from the opened document after editor metadata initialization; route installation now switches to the Layout tab. Other GUI features, native display behavior, Windows/macOS and DPI still require separate acceptance. Real ngspice, Magic, Netgen and external KLayout process-deck execution were not newly qualified. No new Windows/macOS binary or hosted CI execution is claimed.

## Remaining development

Full interactive route shove and healing across arbitrary contacts, equal electrical-length routing, diffusion abutment and folding, a general scripted PCell IDE, expanded process-qualified devices/corners, hierarchical calibrated RC extraction, complete layout property/text comparison, density-rule-driven fill, large-layout viewport qualification, EM/IR and RF analysis, floorplanning and concurrent collaboration remain open. The additions above are bounded working features, not full production-layout parity.
