# IC Design Studio 0.11.0 — native layout editor

This release makes everyday layout work more familiar to engineers who use
Virtuoso or KLayout. It extends the existing Python/PySide6 desktop application
and preserves the 0.10 analog, verification and process workflows. The keyboard
presets are editable, workflow-inspired starting points; they are not claims of
exact vendor defaults or full product compatibility.

## Start a layout session

1. Open a project, then use **View → Library / cell / view browser** to choose
   a cell and its Schematic, Layout or Symbol view. The browser shows the current
   project and links to the installed PDK device library.
2. Choose **Tools → Layout keyboard profile**. Select Studio,
   Virtuoso-inspired or KLayout-inspired and edit individual bindings. Conflicting
   or reserved shortcuts are rejected. Bindings act only on the layout canvas;
   typing in forms and schematic shortcuts retain their normal behavior.
3. Open the **Layers** tab. V controls visibility, S controls selectability,
   and L locks the layer against supported editing commands. Double-click a
   layer to change its color or Solid, Outline, Dense, Hatch or Cross pattern.
   Search by layer name or GDS layer/datatype. The process masks remain unchanged.
4. Arrange the project, inspector and results docks; choose Layout or Linked
   views. **View → Save named workspace** stores that arrangement, splitter,
   selection filters and keyboard profile. The last accepted session also restores.

Display preferences are stored per process revision in application settings.
They are separate from the project geometry and immutable PDK files.

## Selection and commands

The layout selection filters distinguish local shapes, physical cell instances,
terminals and labels. An instance selects as one object when viewing a parent.
Use Tab or Alt-click to cycle overlapping candidates at the pointer. Box selection
can include crossing objects or require complete enclosure. Hidden, unselectable
or locked layers are excluded from normal hit selection.

**Design → Layout editor** and the **Edit** dropdown expose the commands. The
options row follows the active tool: path width in micrometres, routing net,
snapping, via connection and cell rotation appear where relevant. Mouse previews
show the reference displacement or live drawing dimensions. Escape cancels;
Enter or Finish completes a path or polygon. F4 repeats the last layout tool.

| Action | Virtuoso-inspired | KLayout-inspired |
|---|---|---|
| Rectangle / polygon / path | R / Shift+P / P | B / P / Shift+P |
| Move / copy by reference | M / C | M / C |
| Edge / vertex editing | S / Shift+S | S / V |
| Place via / physical cell | O / I | Shift+V / I |
| Properties / fit / ruler | Q / F / K | Q / F / K |
| Rotate clockwise / counterclockwise | Shift+R / Ctrl+R | R / Shift+R |
| Enter / leave hierarchy context | Shift+E / Ctrl+B | Shift+E / Ctrl+B |

For reference move/copy, select objects, start the command, click the reference
point, then click the destination. Edges and vertices have visible drag handles.
Rectangle edits can become polygons. Edge stretching currently requires a
Manhattan edge; hole boundaries use polygon operations. Invalid, collapsed or
off-grid results reject the whole transaction.

Multi-object properties change layer, routing net or path width together, with
one undo step. Size grows/shrinks selected geometry; Chop subtracts a rectangular
area, retaining holes and net/device metadata. Existing Boolean operations,
alignment, path forms, transforms, rulers and GDS/OASIS workflows remain available.

## Routing and placement

Start Path and set width and net in the options row. While a path is in progress,
choosing a conductor layer with a supported native connection commits the prior
segment and a complete via stack, then continues from the same point on the new
layer. SKY130 supports M1/M2 and local-interconnect/M1; GF180 supports M1/M2.
An unrelated or unsupported layer and a locked participating layer reject the
transition while retaining the original path. Via placement is also a standalone
command. This is manual routing with process-specific via recipes; full automatic
obstacle avoidance, shoving, differential-pair routing and route optimization are
future work. Geometry still needs independent DRC and LVS.

Place physical cell presents unplaced linked schematic instances with layout,
plus reusable geometry-only cells. Actual child geometry follows the pointer;
choose 0°, 90°, 180° or 270° before placement. A linked placement preserves its
schematic identity. Repeated placement of geometry-only cells remains active.

## Hierarchy and electrical identity

Select a single physical instance and enter context. A breadcrumb identifies the
active cell and parent. Parent/sibling geometry appears faintly in the child's
coordinate system, including rotated and mirrored placements, and is read-only.
Edits change the shared child and therefore affect every instance of that cell.
Use **Make selected instance a cell variant** before independent editing; it
updates that physical instance and its linked schematic instance together.

Resolve array turns a geometry-only array into independent placements with exact
transforms. Flatten selected physical instances expands geometry-only cells.
Linked electrical instances retain hierarchy; arbitrary electrical flattening is
not implemented. Resolve an array before entering a particular element in context.
Copying generated devices or linked instances starts from the schematic, so a
geometry copy cannot silently manufacture a second electrical device.

Terminal inspection is read-only. Port label changes use the existing explicit
cell-port assignment workflow to keep interfaces together. Ordinary local layout
labels have a property form. Parent routes do not silently follow modified child
ports. Complete device/via selection is required for reference moves and copies.

## Verification and performance

Findings can be filtered by rule, cell, net or message while retaining exact
navigation and stale-result checks. Existing full Magic DRC, Netgen unique-match
LVS, extracted capacitance, saved benches, comparison traces and measurement gates
remain decisive. GUI display settings do not create a verification waiver.

The renderer reuses flattened hierarchy geometry across selection changes and
invalidates it on project revision, cell or display-depth changes. The packaged
evidence records the measured synthetic hierarchy benchmark; this is not a claim
of production-scale database performance. The existing 100,000 flattened-shape
limit remains. Large connectivity analysis and arbitrary foundry databases need
separate scalability work.

The release evidence names exact executed core, native Qt, real-engine and frozen
application checks. The Linux x86_64 app includes Python, Qt and KLayout and targets
glibc 2.39 or newer. Fresh-profile offscreen checks at two display scales are
distinct from fresh-OS installation and real desktop-driver qualification, which
remain unexecuted. Windows build definitions remain unqualified.

Read [CAPABILITY_MATRIX_0.11.md](CAPABILITY_MATRIX_0.11.md) for the broader roadmap,
[UPDATE_0.10.md](UPDATE_0.10.md) for process geometry limits, and
[LINUX_SETUP.md](LINUX_SETUP.md) for external-engine setup.
