# IC Design Studio 0.12.0 — schematic and symbol capture

This release extends the native desktop application with familiar capture
workflows for Xschem and Virtuoso users. Its editable profiles are inspired by
those tools; they are starting points, not a promise of identical vendor behavior.
The complete 0.11 layout workspace and existing analog/process workflows remain.

## Work in the schematic

Choose **Tools → Schematic command profile**. Keyboard bindings apply only while
the schematic canvas has focus. Symbol editing has its own **Keys** dialog, and
layout retains its separate Studio/Virtuoso/KLayout profiles. Duplicate bindings
are rejected. Each schematic profile also stores optional Ctrl-drag stretch and
Alt-right-click wire cutting. Middle drag pans and the wheel zooms.

| Command | Studio | Xschem-inspired | Virtuoso-inspired |
|---|---|---|---|
| Component browser | I | Shift+I | I |
| Wire / label / ground | W / L / G | W / L / G | W / L / G |
| Move / stretch / copy | M / Shift+S / C | M / Ctrl+M / C | M / S / C |
| Properties / fit | Q / F | Q / F | Q / F |
| Rotate / mirror | R / Shift+F | Shift+R / Shift+F | R / Shift+F |
| Enter schematic / symbol | E / Shift+E | E / I | Shift+E / Ctrl+E |
| Return to parent | Ctrl+B | Backspace | Ctrl+B |
| Undo / redo | Ctrl+Z / Ctrl+Shift+Z | U / Shift+U | U / Shift+U |
| Check and Save | Shift+X | Shift+X | Shift+X |
| Cut / repeat command | Shift+W / F4 | Shift+W / F4 | Shift+W / F4 |

Xschem-inspired Ctrl+Z zooms out and Shift+Z zooms in. Text fields retain normal
text editing. While drawing a wire, Backspace still removes the last bend.
Escape cancels an active gesture. Commands are also available in **Design →
Schematic editor**, the **Capture** dropdown, and the compact **More** menu.

Select objects, start Move, Stretch or Copy, click a reference point and then a
destination. The live preview does not commit. **Move** relocates selected
geometry without extending leads; **Stretch** keeps existing device connections
and stretches the leads. Normal device dragging also preserves connections;
optional Ctrl-left-drag explicitly invokes stretch. Selected whole wires move as
whole wires. Named labels continue to connect equal names even across a gap.

Cut removes a ten-unit gap inside a wire segment. Choose a point away from an
endpoint, pin or junction. Select two wires and choose Rejoin to connect their
nearest ends with an orthogonal bridge. Junction dots, isolated crossings,
snapping to terminals and wire ends, and label/ground placement remain the same
stored electrical operations used by the existing editor.

The persistent **Devices** browser now includes a vector preview. **Repeat
placement** places another uniquely named instance after each click. Rotate or
mirror its preview before placing it. Escape finishes. For several selected
devices, Q opens Bulk Parameters; choose a shared value or parameter. The entire
operation must pass validation, including PDK limits, and undoes in one step.

## Edit the symbol and its electrical interface

Open a cell's Symbol view or enter the selected instance's symbol. Generate
arranges its schematic ports around a labelled body. Inputs and outputs occupy
opposite sides; power/ground roles occupy top/bottom. Inout/passive terminals
are balanced across the sides. Generate can be undone before saving.

Artwork tools include lines, rectangles, ellipses, polygons, arcs and text.
Drag a marquee to select artwork/pins; Shift adds to selection. Copy, rotate,
mirror, align and distribute work on selected artwork. Rotate/mirror also apply
to selected pins. Endpoint Handles moves a selected primitive's vertex; exact
vertices, arc angles, line width, fill, color, font size and bold text are editable
in Properties. Finish a polygon with Enter, double-click or right-click.

The terminal table edits name, exact X/Y, direction, role, optional bus membership
and label visibility. Up/down controls **netlist order**, independently of artwork
order. Bus metadata describes individual scalar pins such as data[0] belonging
to data[3:0]; existing schematic bus operations provide scalar expansion.
Directions are in/out/inout/passive. Roles are signal/power/ground/clock/analog.

Every terminal gets a stable identity. Moving or renaming a reusable cell pin
updates referencing instances and retargets their attached leads in the same
project transaction. Reordering changes the cell's ordered electrical interface.
Connected terminal deletion is rejected until the interface is disconnected;
renaming an interface tied to physical ports or a saved testbench is guarded.
Device model terminals remain fixed. New unconnected cell terminals can be added.
The editor displays changed terminal definitions; invalid changes stay in the
editor with an explanation. Save commits the complete symbol/interface; Cancel
discards its local undo history.

Use @name, @value and @parameter in symbol text for instance-dependent labels;
@symname displays the referenced cell name. Attributes are declarative strings.
Native symbol JSON retains the complete definition. Xschem .sym import/export
retains pins, ordering, directions and supported artwork; a checked native payload
preserves additional styles only when the visible artwork has not changed.
External artwork edits take precedence over that payload. No Tcl is executed.
Generated package import still requires its original symbol lock: use the native
symbol Import command to reconcile separately edited symbols before exporting a
new package. This is not an arbitrary Xschem library or Cadence/OpenAccess reader.

## Turn circuitry into a reusable cell

Select devices and choose **Make cell from selection**. Nets shared with remaining
devices or parent ports become cell terminals; ground remains global. The parent
receives an instance at the former contacts and the child retains the electrical
implementation. One undo restores the original flat circuit. Linked physical
implementations and saved-DUT contracts require reconciliation before extraction.
The native symbol coordinate and project-size limits still apply.

Enter Schematic descends into the selected reusable cell. Parent restores its
selection, zoom and viewport. The breadcrumb shows the navigation path. Editing
a shared child updates all its instances. Enter Symbol opens the shared symbol.

**Check and Save** runs active-cell ERC and project interface checks, including
unused ports, overlapping symbol pins, inconsistent order and multiple output
pins driving a net. Click a finding to open its cell and object. Electrical errors
block Check and Save; ordinary File → Save can retain unfinished work. These
checks are connectivity/editor checks, not analog correctness or physical signoff.

## Included acceptance project

Open amplifier-testbench.icproj in the companion Examples archive. It contains a
generic transistor amplifier extracted from selected circuitry, a customized
symbol, and a saved AC testbench. Enter its schematic, edit RD, return to the
fixture and run the saved testbench using configured ngspice. This teaching model
requires no external PDK; the existing process examples retain their locked PDKs.

## Validation and next work

The handoff's verification/RELEASE-RESULTS.json records the exact final tests,
source/build hashes, real-engine runs, packaged 100%/200% probes, and recovered
archives. Historical reports retain their original release scope. All 555 locked
PDK files are rechecked unchanged. Fresh-OS Linux/Windows installation and real
graphics-driver qualification remain unexecuted on this build host.

Future work includes richer electrical rule policies, large-design performance,
advanced bus harnesses, reusable multi-library organization, constraint-driven
analog placement/routing, and broader interoperability. Full vendor parity and
fabrication signoff remain outside this engineering preview.
