# IC Design Studio 0.13.0

0.13 connects the schematic, symbol, physical-interface and saved-testbench
workflows and improves the responsiveness of everyday editing. It remains a
native PySide6/Qt desktop engineering preview, with schema 1 and the existing
atomic project history. The supplied PDK packages are unchanged.

## Review an interface change

Open a cell's symbol through its Symbol view or Capture → Enter symbol. Edit
terminal names, add/remove rows, or change row order, then Save. A review opens
before the project changes. Coordinate, artwork and metadata-only edits still
save directly and preserve connected leads.

1. Map each existing terminal to a proposed terminal. Stable identities suggest
   renames. A removed terminal requires an explicit replacement or **Disconnect**.
   Each target can have only one source; net merging remains a wiring operation.
2. In **Instance connections**, connect each added pin for each use of the cell.
   A blank net leaves that terminal unconnected. The app never defaults it to ground.
3. In **Physical ports**, optionally assign added ports to a conductor layer and
   grid-aligned coordinates in nanometres. Missing assignments become findings.
4. **Refresh review** shows affected instances, old nets, physical interfaces,
   saved benches and any disconnections. Removing invalid probes and their
   dependent measurements requires the explicit checkbox and is listed.
5. **Apply reviewed update** commits all views together. One Undo restores them.
   If the project changes after preparation, Apply refuses the stale candidate.

Renames preserve each parent's external net while changing the child's internal
net, symbol identity, pin anchors, physical port, exact port labels and generated
device net metadata. Parent wire leads follow moved pins. Removed pins retain
wire stubs and named point anchors. Removing a port does not delete its internal
circuitry. Fix newly unused/floating connections explicitly. Port order remains
the SPICE subcircuit terminal order. The last 20 interface receipts travel with
the cell. Existing simulation/extraction results become stale after edits.

Generated process dimensions are never refreshed merely by renaming a net.
Stale transistor geometry remains stale. Review and rerun physical verification
after an interface change, especially when parent routes or child ports move.

## Electrical checks

**Tools → Electrical check rules** stores scope and rule severities in the
project. Each rule can be off, warning or error. Scope is the active hierarchy or
all project cells. **F6**, **Check**, and **Check and Save** use this policy.
Check and Save stops on errors; normal File → Save can retain unfinished work.

Checks cover empty circuits, ground, shorted primitive terminals, dangling nets,
multiple output drivers, undriven inputs, scalar bus width/order, symbol/port
agreement, overlapping pins, unused ports and missing physical ports. Findings
carry the hierarchy occurrence; clicking a row opens the associated cell/view.
Primitive findings target the device/pin. Physical-port findings open layout.

The symbol table offers dropdown editors for direction, role, visibility and
**Req.** (required). Optional terminals omit unused/dangling warnings. Required
metadata survives native saving and symbol `.sym` exchange. Scalar bus checks
do not introduce bus harnesses, vector-valued device terminals, timing analysis
or a complete analog electrical-rule engine.

## Navigate schematic and layout together

**Design → Schematic / layout cross-probe** lists instances with full occurrence
paths, placement status and missing terminals. Reused cell definitions remain
distinct occurrences. Open the schematic or layout, place an eligible missing
cell, or inspect geometric connection guidance. Sources are identified as bench
elements. Unsupported primitive footprints still need manual/imported geometry.

Switch to **Net occurrences** to follow a root net through actual instance
terminal mappings. Child net names can differ; same-named internal nets in
unrelated occurrences are not conflated. Opening a row edits its shared cell
definition and retains a parent navigation path. **Connection guidance** uses
actual conductor contact and existing terminal assignments in that cell. Dashed
guides identify disconnected groups; they do not constitute automatic routed
closure or extracted LVS. Refresh after project edits before using old rows.

## Editor responsiveness and clarity

- The capture bar shows the active command with relevant Finish/Cancel controls.
  Compact views retain readable controls and expose other commands through More.
- **Tab** or **Alt+click** cycles overlapping schematic objects. Capture's
  **Selection filter** controls devices, wires and labels; wiring snaps still
  consider electrical targets. A hovered pin shows its instance and terminal.
- Move/stretch previews copy the active cell and skip repeated grid positions.
  They do not mutate the project. The symbol editor fits its artwork on opening.
- Wire topology, junctions, hover lookup and viewport queries use spatial
  indexes. Immutable geometry/painter caches survive selection changes and
  invalidate after edits/undo. Symbol redraw reuses vector artwork recordings.

Reproducible measurements are in `tests/gui_capture_performance.py` and
`tests/gui_editor_performance.py`. The handoff includes baseline and release
reports on the same build host. Workloads use 500 devices/2,000 wires, 1,000
symbol primitives and 10,000 flattened layout shapes. Initial paint, topology,
snapping and selection are reported separately; an improvement in one is not a
claim that every operation improved. Existing data limits remain unchanged.

## Acceptance and distribution

The release includes source, the Linux x86_64 bundle, portable examples,
continuation patch and evidence. Open `amplifier-interface-update.icproj` for
the saved edited amplifier fixture; it uses generic transistor models and an
illustrative linked physical-port view. It is not a verified silicon amplifier.
`sky130-renamed-mirror.icproj` exercises a reviewed process interface rename.

Automated acceptance changes the amplifier interface, applies mappings, undoes
and redoes once, resolves findings, follows hierarchy/net links, simulates with
actual ngspice and saves/reopens the result. A separate SKY130 mirror rename
passes full DRC, extracted Netgen LVS and pre/post-layout simulation. Packaged
checks cover both 100% and 200% scaling and existing SKY130/GF180 workflows.
Exact counts and source/executable hashes are in `verification/RELEASE-RESULTS.json`.

Fresh Linux desktop/graphics-driver and experienced-user sessions are **not
executed** on this build host. The release supplies a reproducible protocol and
an unfilled results template in DESKTOP_ACCEPTANCE_0.13.md and its companion JSON.
Windows installation and full vendor parity remain unqualified. Differential
pair physical recipes, richer constraints/routing and broader process generation
remain subsequent work; existing extraction is capacitance-only engineering
verification, not fabrication signoff.
