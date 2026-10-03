# IC Design Studio user guide

This guide covers the current experimental source. Start with [your first circuit](GETTING_STARTED.md) or [Student Hub](STUDENT_HUB.md), then use the [documentation index](INDEX.md) for complete feature guides. **Ctrl+K** finds commands by name. Versioned update documents preserve the behavior and evidence of their original releases.

For the larger workflows, see [analog design](ANALOG_WORKSPACE.md), [digital design](DIGITAL_WORKSPACE.md), [mixed-signal experiments](MIXED_SIGNAL_SAR.md), [physical hierarchy and extraction](ANALOG_IMPLEMENTATION_EXTENSIONS.md), and [collaboration](LIVE_COLLABORATION.md).

## Appearance

View → Toggle light / dark (Ctrl+Shift+T) changes the appearance and remembers your explicit choice.

## Project workflow

An `.icproj` is a readable UTF-8 JSON project containing cells, devices, stored wire paths, explicit net labels, layout geometry, a technology descriptor, analysis settings, revision metadata, and review waivers. All electrical ground references use the net name `0`.

The circuit workspace switches between Schematic, Layout, and Linked views. The project navigator selects cells and devices. The inspector edits the selected object. Results contains waveforms, checks, and job logs. Panels can be resized, floated, closed, and reopened from **Window** or the visible panel toggles. Their layout and window geometry are remembered. **Window → Reset workspace** restores the default. The digital workspace provides separate Design, Debug and Implement modes; **Circuit workspace** returns to schematic/layout editing.

Local design work needs no account or hosted service. Copying a project file preserves its design; copy its result directories separately to retain historical waveforms. Optional [self-hosted collaboration](LIVE_COLLABORATION.md) shares schematic/layout edits and reviews. Start or join a session explicitly through **Tools → Collaboration**.

## Schematic editing

Choose **Schematic → Place component…** or press **P** in the default Studio profile. Search the Devices panel, select a component, then choose Place component (or double-click the device). A preview follows your pointer; click the canvas to place it, or press Esc to cancel. Click a symbol or select it in the Components list. Edit its electrical values and connections in Properties; expand Position for coordinates. Apply changes commits a validated, undoable edit. Moving to another object commits valid drafts; invalid drafts remain with an inline error until corrected or Reset. Multiple selection exposes group actions; individual property editing requires one object. Values use SPICE suffixes: `k`, `meg`, `m`, `u`, `n`, `p`, `f`. `M` means milli, as in SPICE; use `meg` for a million.

Press **W** (or click Wire) to place a physical wire path. Click a pin, an existing wire, or empty space to start. Each click fixes a bend; the dashed final elbow previews the next segment. Space or Tab switches the elbow direction. Finish by clicking a pin/wire, or press Enter to finish at the last clicked point. Backspace undoes the last click. Esc discards the pending path without changing the circuit; Esc again returns to Select. Right-click cancels and selects. Use middle-drag to pan while wiring.

The saved wire geometry determines connectivity. A wire endpoint or pin touching a wire connects to it. A solid junction dot marks a branch; a bridge marks an interior crossing that does not connect. Point at a crossing and press J to add/remove an explicit junction. Drawing an intentional wire between named conductors merges the entire connected nets (ground takes precedence, otherwise the starting named conductor); the status line reports renamed labels and Ctrl+Z reverses the whole edit.

Select a wire and drag a segment perpendicular to itself to reshape its path. Its endpoints and branches remain attached through local lead segments. Delete removes the selected wire and recalculates the circuit; it does not leave a hidden logical connection behind. Explicit identical net labels still connect distant conductors intentionally. Device moves and rotations stretch terminal leads while preserving remote wire bends. Repositioning geometry that would join contradictory explicit labels is rejected with an explanation.

**New and duplicated devices start with open terminals.** They are not automatically grounded. In the Connections inspector, enter `0` to ground a conductor or a name such as `vout` to label it. An empty field means no explicit label; its placeholder shows the computed connection where applicable. Clear a label to remove its named connection. R rotates clockwise and Shift+R counterclockwise, both during placement and after selection. The Rotate toolbar control and Position section provide mouse access.

Legacy projects keep their original net assignments. Their previously inferred routes become stored paths only when the resulting geometry preserves every original connection. Ambiguous old drawings instead retain explicit pin labels and omit misleading inferred lines. Coincident legacy pins on conflicting nets must be moved apart before manual wiring can be enabled. These compatibility labels intentionally preserve old named connections; remove/edit the labels if you want connectivity exclusively from new wires. Use the new version to edit projects containing stored paths.

Drag selected objects to move them with a live preview; drag empty space to box-select. Ctrl+click or Shift+click adds or removes objects. Arrow keys nudge a selection while the canvas has focus; Shift increases the nudge. Delete removes selected objects. Undo/redo operates on validated project transactions. Duplicate copies a device with a fresh object ID and name; its terminals start unlabelled. Copy devices and wires together to duplicate a wired group; touching existing geometry still connects normally.

Create cells with Design → Add cell. Define external ports using Edit cell ports. Instantiate another cell with Design → Instantiate cell. Hierarchy recursion is rejected. Each cell can be simulated independently, or used under the top cell. New hierarchical instance pins start unconnected; wire them or add explicit net labels before simulation. Physical hierarchy uses separately reviewed placements and ports linked to the schematic instances.

**Schematic → Configure instance array…** and ordered terminal/label expressions such as `data[7:0]` provide bounded native bus and array editing. Simulation expands their members in the declared order. Read [Native buses and instance arrays](NATIVE_VECTORS.md) for width checks, broadcasts, floating terminals and exchange limits.

## Layout editing

Select a layer and choose Rectangle, Polygon, or Path. Rectangles support dragging or clicking two corners. Polygons and paths use vertex clicks; Enter or a double-click finishes. A path's Enter action includes the preview endpoint; **Finish** completes at the last clicked point. Escape or right-click cancels pending vertices. Coordinates are exact integer nanometres. Layout snapping can follow the visible grid or a fixed process-grid multiple; the generic teaching process has a 5 nm manufacturing grid. The inspector displays geometry in micrometres: rectangle position/size, or a vertex table for polygons and paths. Changes must resolve to whole nanometres (0.001 µm). Assign the layer, net, and linked component by name. See [grid and drawing controls](DRAWING_0.22.md).

Layers may be hidden in the Layers tab. Pan with the middle mouse button or Space+drag. The mouse wheel zooms around the pointer. Press F while the canvas is focused to fit.

Ctrl+click selects multiple shapes. Boolean union, subtraction, intersection, and XOR operate on shapes on the same layer with the same net label. Subtraction uses selection order: select the source first. Hole geometry is retained through Boolean operations and GDS export. Arrays repeat selected shapes on an integer pitch; their net/device labels remain unchanged.

A generic MOS generator creates illustrative geometry linked to a selected transistor. Its fingers and shapes are not a foundry PCell and do not establish correct electrical device width or contact enclosure. **Generate metal guard ring…** creates a metal ring; process-specific contacted guards and device recipes are separate operations requiring suitable technology bindings. Imported layer descriptors do not enable physical recipes automatically.

Use **Schematic → Place schematic devices in layout…** to review missing supported implementations, then **Layout → Review schematic changes in layout…** after edits. **Layout → Cells and arrays → Resolve and regenerate physical variants…** materializes supported parameter overrides; **Expand linked instance array…** prepares compact arrays for independent physical placement. Preview and apply changes, then rerun connectivity and process verification. See [physical hierarchy](ANALOG_IMPLEMENTATION_EXTENSIONS.md#parameter-correct-physical-hierarchy) and [layout workflow](LAYOUT_SCALE_AND_COLLABORATION.md).

Select a transistor in the schematic to highlight linked shapes. Choose a shape's Component in the inspector to create your own mapping. Selecting mapped layout geometry also highlights its schematic component in Linked views. Net labels connect waveform highlighting with both editors, but do not constitute physical extraction.

## Simulation

Inspector → Analysis (or Ctrl+Enter) opens persistent analysis settings. Only fields for the selected analysis appear. F5 or Run starts the current setup; invalid settings appear inline. The built-in solver handles generic linear RLC networks and elementary square-law MOS devices. Its analyses are:

- Operating point: node voltages at time zero using the configured source waveform.
- Transient: fixed time-step backward Euler with previous capacitor voltages and inductor currents.
- DC sweep: sweep one voltage or current source.
- AC: small-signal response at logarithmically spaced frequencies; source AC amplitudes are used. Output is voltage magnitude in volts, not normalized gain or dB.
- Noise: uncorrelated resistor thermal noise in a linear RLC circuit. Resistor tc1/tc2 coefficients can also affect resistance versus temperature; the generic MOS solver rejects non-nominal temperature. Semiconductor noise is not supported.

MOS models omit body effect, subthreshold current, junction effects, intrinsic device capacitance, and statistical distributions. Built-in transient pulse sources have ideal edges; the exported ngspice deck uses short finite edges. Sources should be configured for the intended testbench. The built-in solver adds 1 pS at each node for numerical conditioning. Its preview limits are 80 unknowns, 20,000 transient steps, and 5,001 DC points.

Jobs run in a separate process. Cancel job terminates the active job. Results are saved with the immutable project snapshot, settings, revision, engine hash, technology hash, and rule hash. Editing marks old results stale. Historical curves remain available for comparison; stale check markers are not used to navigate the new design.

The waveform list enables or hides signals. Clicking a signal highlights its named net. Use the waveform tools for X cursors, Y limits and X/Y checks; **Markers…** edits exact coordinates and numerical comparisons. CSV export retains the underlying values. Calculated waveforms support expressions and AC magnitude/phase analysis; saved specifications and variation cases compare results against explicit requirements. See [simulation and studies](PROFESSIONAL_WORKFLOWS.md).

## Verification and waivers

ERC checks connectivity and configured electrical rules. Inspect findings and configure the applicable rules through **Verify → Electrical check rules…**. Passing the configured checks does not establish circuit performance or process signoff.

Geometry DRC uses KLayout to check width and spacing on each layer plus the descriptor's grid. It does not check the foundry's complete rule set, enclosures, antenna, density, latch-up, or device recognition. A zero-error result means only that these listed checks found no violations.

The mapping audit checks device-to-shape links. It is not LVS. Supported physical workflows run Magic extraction, Netgen comparison and saved-testbench simulations using matching locked process assets. Standalone netlist comparison also accepts explicitly supplied decks. Inspect raw reports and the selected flow's limits; an engine exit code alone does not establish signoff. See [PDK setup](PDK_GUIDE.md), [analog closure](ANALOG_CLOSURE.md) and [reference qualification](REFERENCE_QUALIFICATION.md).

Select a current violation to navigate to its object. Waivers require a reason and remain tied to the exact design revision. They are review metadata, not a change to the geometric design or proof of acceptance.

## Files, recovery, and export

Save explicitly to choose your project file. Committed edits queue session-specific recovery snapshots under your platform's application-data directory. The status distinguishes pending, available and failed recovery; a write is acknowledged only after its receipt matches the saved bytes. One previous valid snapshot is retained. On a later startup, recover an interrupted project when prompted and save it to a normal project file. **File → Recovery** offers retry and a different recovery folder. Explicitly discarding edits removes that session's recovery records. Saved replacement uses a synchronized temporary file and atomic replacement. See [recovery verification](RELIABLE_DESIGN_WORKFLOWS.md).

Data directories use Qt's AppLocalDataLocation under ICDesignStudio. Job folders contain `input.json`, `result.json`, and, where applicable, the engine deck/log. Recovery and job data can be removed manually when no longer needed. The app does not perform automatic cloud backup or update.

A handoff exports the authoritative project, SPICE deck, GDSII, OASIS, Xschem package, layer properties, technology descriptor, dependency snapshot, and a preservation report. Read the report. Exported PCells are geometry. The Magic native path runs the actual installed Magic executable with an explicit technology file; the app never pretends a renamed GDS file is native Magic data.

GDSII/OASIS imports with unchanged matching export metadata recover the full application project. Changed exports with valid exchange metadata go through review; conflicting changes must be reconciled against the original project. A standalone import retains supported physical hierarchy, arrays, transforms and text, but has no inferred schematic/device mapping. Imported layers initially have zero width/spacing rules, so assign meaningful technology rules before interpreting DRC. [Interoperability](INTEROPERABILITY.md) describes supported Xschem, Magic and KLayout exchange; [native catalog migration](NATIVE_CATALOG_MIGRATION.md) describes editable imported process devices. Unsupported source constructs are reported explicitly.

## Engines and extensions

**Tools → Engine diagnostics and paths…** configures local executables. The KLayout geometry Python library is included. **Tools → Physical tools setup…** selects included or custom Magic, Netgen and ngspice tools; matching locked PDK files remain necessary. Complete desktop packages provide the managed runtime, using a private Linux environment on Windows. A source checkout must build that runtime or select custom tools. [Downloads](DOWNLOADS.md), [digital setup](DIGITAL_FLOW.md#included-tools-and-first-setup) and the [PDK guide](PDK_GUIDE.md) distinguish engine setup from process qualification. Student Hub Digital lessons use the selected Included or Custom digital toolchain and open setup when needed. Mixed Signal lessons, the capstone and the SAR bridge require separately selected native local executables.

The source CLI supports a trusted local Python plugin example. A manifest declares API 1.0, an entry file, and command capability. The worker receives a snapshot and returns commands, which pass normal validation atomically. This is process isolation, not an OS security sandbox. Do not run untrusted plugins or rule decks. The frozen app does not execute arbitrary Python plugins.

## Keyboard reference

Ctrl+N: new. Ctrl+O: open. Ctrl+S: save. Ctrl+Shift+S: save as. Ctrl+Z: undo. Ctrl+Shift+Z: redo. Ctrl+D: duplicate. Ctrl+K: searchable command palette (Up/Down selects, Enter executes). Ctrl+1/2/3: toggle Project, Inspector, Results. Ctrl+Shift+F: focus canvas/restore panels. Alt+1/2/3: schematic/layout/linked views. Ctrl+Enter: analysis setup. P: device library. W: manual wire. R / Shift+R: rotate in either direction, including placement. J: junction at pointer. These editor shortcuts also work from project/component selection; typing fields retain their own keys. Ctrl+/: wiring and keyboard help. Underlined menu letters are real mnemonics: Alt+letter opens the menu, then the underlined command letter invokes it. Ctrl+E: handoff. F5: run current analysis. Shift+F5: cancel. F6: ERC. F7: geometry DRC. F1: current linked help (Enter finds the next match; Shift+Enter finds the previous match). Ctrl+Shift+T: theme. F / arrows / Space / Enter / Escape: canvas controls.

General screen-reader behavior and full keyboard reachability of every CAD editing action have not been qualified. Numeric inspector editing provides a keyboard-accessible alternative for coordinates and connections.

## Place net names and ground

Press **L**, type a name, then click the wire or pin. Press **G** to place ground. A ground symbol placed on empty space can be wired from its anchor. Dragging the artwork moves its position without disconnecting the conductor; choose **Reattach…** in Properties to change the electrical anchor. **R / Shift+R** rotates artwork. Select a label to edit its name and placement; **N** highlights and inspects the complete net, including remote connections made by matching labels. **More…** holds these tools in compact windows.

Naming another conductor with the same name deliberately joins the nets within the active cell. A label at a crossing attaches to one wire and does not create a junction. **J** still controls explicit crossing junctions. Deleting a placed label removes its named connection unless another label remains on that conductor.

Recovery now keeps session-specific files and one previous valid snapshot. If a file changes in another editor, normal Save stops before replacing it; use Save As to preserve your edits and review both versions.


## Schematic and symbol capture

See [UPDATE_0.12.md](UPDATE_0.12.md) for capture profiles, explicit move/stretch,
wire cut/rejoin, repeated placement, bulk properties, make-cell hierarchy, rich
symbol artwork, electrical terminals and Check and Save.
