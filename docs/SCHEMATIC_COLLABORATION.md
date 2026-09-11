# Collaborating on schematics and layouts

Available in **0.22.0.dev15**. Open **Tools → Collaboration**, share a project or
join an invitation, and switch between **Schematic** and **Layout** normally.
Both views use one workspace, revision history and set of review checkpoints.

## Working together

- Place, move, rotate, copy or delete components; change values and parameters;
  draw wires, move connected components, edit labels and toggle junctions.
- Each gesture commits its complete change, including stretched wires and
  electrical connections. The server rebuilds connectivity before publishing it.
- Different components and disjoint schematic/layout edits can merge. Editing
  the same object, connected net or overlapping connection area can require review.
  Newly drawn wires are checked even when they have different object IDs.
- Colored cursors and selection outlines appear in the correct view and cell.
  The **Live workspace** participant list shows where each person is working.
  Double-click a teammate to visit their view after finishing your current edit.
- Undo and redo affect your accepted transactions. They preserve compatible
  changes by teammates and refuse to overwrite intervening conflicting changes.

An unfinished circuit can be shared. **Check schematic** runs electrical checks;
ordinary ERC findings do not prevent drawing the next part of the circuit.
Malformed wires, contradictory labels and invalid hierarchy still reject the
complete transaction. A rejected proposal remains available for review or saving.

## Hierarchy and linked layout

Cell creation/deletion, project settings, cell parameters, symbol artwork and
supported port-interface edits use transactions covering the affected objects.
Hierarchy and settings changes require a current revision across the workspace;
they are deliberately more conservative than independent component edits.
The existing symbol editor updates affected instances together. Its restrictions
on removing connected terminals and changing physical/testbench contracts remain.

After schematic changes, the dashboard identifies the changed cells. Choose
**Review schematic and layout** to inspect device-link status, connections and
verification. Existing results retain their saved inputs and become stale when
their design hash no longer matches. Review and apply layout updates explicitly.

## Reviewing changes

In **Team review**, save a named checkpoint and choose **Compare revisions**.
Use the **Schematic / Layout** selector to inspect either view. Schematic review
shows the complete cell with changed objects highlighted, plus component values,
parameters and connections in the comparison table. Hover over a table entry to
read its full displayed detail. Wheel to zoom and drag to pan.

To attach a comment, select **Attach to current selection**, then choose:

| Attachment | What to select |
|---|---|
| Object | One component, wire, label or layout object |
| Terminal | A component, then one of its terminals |
| Highlighted net | A highlighted schematic net |
| Electrical finding | A finding from the current cell's electrical checks |

The server validates attachments against the selected checkpoint. If the design
has changed, save/select the appropriate checkpoint first. **Go to object** opens
the current target. If a target was removed or renamed, inspect its checkpoint.
Approvals apply only to their checkpoint. Viewers can inspect reviews; posting
and recording decisions still require edit access.

Conflicting component edits open a three-version schematic comparison: before
your edit, the shared revision, and your retained proposal. Parameter conflicts
require an explicit manual edit after review; reapply never silently overwrites
someone else's value. Save your version if you need to preserve both alternatives.

## Shared-folder workspaces

Use the same dashboard's **Shared folder** tab. Claim the whole cell to publish
schematic edits. Layer claims authorize layout changes on those layers only.
Choose **Whole project (hierarchy and settings)** for cell creation/deletion,
symbol/port interfaces and project settings. Publish and refresh explicitly.
Claims expire and are renewed while connected, as in earlier builds.

## Updating an existing team

Update the server and every participating desktop to dev15 together. The HTTP
API is `/v2/workspaces`; old `/v1` clients receive an update message. New clients
refuse incompatible server snapshots. The server upgrades its SQLite schema to
version 2 while retaining projects, sessions, accepted edits, reviews and retry
identities. Older servers reject that database version. Back up the server using
the procedure in [Live collaboration](LIVE_COLLABORATION.md#server-persistence-and-limits)
before upgrading; use the backup if you must return to the older server.

Old desktop recovery journals can be resumed against the upgraded server,
including pending layout transactions with their original request IDs. Joining
an old shared folder upgrades its journal to version 2; older clients must update
before their next refresh/publication. Workspace and project files are retained.

## Current limits

PDK changes and reordering existing objects/cells require leaving collaboration.
Junction lists and bus edits reserve a whole cell; interface/settings changes
reserve the whole workspace. Spatial connection checks are conservative, so some
nonconnecting crossings may also need review. Only one live edit can await an
acknowledgement; connection loss preserves it and pauses further edits.

The live limit is 8 MiB / 20,000 stored schematic and layout objects, with 2,000
changed records per transaction. A cell metadata change counts as one record;
whole-project limits still apply. Large revision comparisons list the first
2,000 changes. Simulation engines and matching PDK assets remain local.

## Acceptance checks

`tests/test_schematic_collaboration.py` exercises real HTTP clients for concurrent
editing, connection races, authoritative connectivity, undo, hierarchy, viewer
permissions, server restart/retry and checkpoint attachments, plus shared-folder
claims. `tests/gui_schematic_collaboration.py` drives two actual Qt windows through
wire drawing, connected movement, presence, visual review, comments, conflicting
values, desktop recovery and remote cell deletion. Windows and Linux CI run both;
the installed application probe also edits and undoes a schematic and renders a
schematic revision comparison.
