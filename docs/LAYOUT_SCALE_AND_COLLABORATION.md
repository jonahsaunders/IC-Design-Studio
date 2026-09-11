# Large layouts, schematic-driven changes and concurrent editing

This engineering preview extends the native layout workflow. It does not imply
Virtuoso feature parity or foundry signoff of arbitrary designs.

## Capacity and rendering

| Operation | Current bound |
|---|---|
| Stored native hierarchy | 2,048 cells, 250,000 shapes per master, 1,000,000 stored shapes per project |
| Regular arrays | Up to 1,024 rows and 1,024 columns; masters remain shared |
| Native project file | 512 MiB; directory projects retain per-cell snapshots |
| Hierarchical viewport | 12,000 drawing rows, then a labeled hierarchy outline; zoom in for exact geometry |
| Exact hierarchy selection query | 100,000 shapes; excessive selections fail explicitly |
| Connected editing | 100,000 conducting shapes; 2,000,000 candidate contact pairs per update |
| Operations that flatten the hierarchy | 100,000 shapes; select a smaller cell when a check reaches its budget |

Rendering does not flatten or change the saved design. A reduced-detail outline
is not a density map, a selection result or physical metal. Point picking and
snapping bypass the drawing cache and retain source IDs, instance paths and net
mapping. A close-up returns exact geometry. The hierarchy tree expands each
shared master once; double-click a reused master to inspect it independently.

`test_layout_expansion.py` checks 256 native cells and a connection-preserving
edit among 50,000 conductors, including exact undo/redo and one rebuilt polygon.
`test_layout_pipeline.py` checks two million expanded shapes with two stored
master shapes. `gui_layout_expansion.py` records first overview timing and
screenshots for one million instances. These synthetic measurements are not
universal interactive latency guarantees. Flattening-based DRC, extraction and
routing retain their separately documented limits.

## Schematic-driven layout

Use **Layout → Review schematic changes in layout**. Include the schematic
hierarchy to review each shared cell master once. Select individual actionable
rows, choose an origin and pitch for new footprints, then preview the transaction.

- Add missing declared process MOS or parametric R/C/MOS implementations and
  physical child instances. Child masters are processed before their parents.
- Regenerate changed parameters, terminal nets or declared parametric recipes.
  Generated role IDs, terminal IDs and supported saved placements are preserved.
- Review and rebind changed physical child links at the existing instance origin
  and orientation. Every physical child port must be assigned.
- Remove selected orphan generated footprints or linked instances. Independent
  routes remain for review; unselected devices remain untouched.
- Retarget attached route endpoints where possible and check surviving terminal
  connectivity and clearance. Fixed-coordinate review permits intentional
  connectivity changes. Connectivity findings include affected ancestors.

The preview applies as one undoable operation and rejects a changed source
project. Locked footprint/route layers reject the proposal. Full DRC/LVS must
follow an ECO. A recipe is usable only when the technology declares it; generic
teaching geometry retains its existing qualification notice. Native devices
require explicit electrical-to-physical bindings. Differing hierarchical
parameter overrides require a concrete physical cell variant; this release does
not automatically synthesize variants, infer missing process recipes, place
physical ports or repair arbitrary routing.

## Concurrent layout sessions

The following section describes the shared-folder mode. The separate
[live desktop collaboration mode](LIVE_COLLABORATION.md) adds a self-hosted
network service, invitation permissions, automatic updates and personal undo.

Use **Layout → Concurrent editing → Create shared workspace** or **Join shared
workspace**. A workspace directory contains an atomic project journal and an OS
lock file. Editors must have trusted read/write access to the same directory and
synchronized clocks and a filesystem that correctly implements cross-process file locks and atomic
replacement. Cloud-sync folders and independent copied folders are unsupported;
a hosted collaboration server, authentication and internet synchronization are
not included. Validate a network filesystem's locking semantics before use.

1. Enter your editor name and claim a whole cell or named layers in a cell.
   Two editors can work in the same cell on disjoint layers. Overlapping claims
   are rejected. Generated footprints and hierarchy require whole-cell claims.
2. Edit locally. **Publish layout changes** validates ownership, technology and
   schematic consistency, then merges stable object IDs against the latest
   shared revision. Unclaimed, expired or conflicting changes are retained
   locally and rejected from publication.
3. **Refresh shared layout** merges others' changes while retaining unpublished
   local edits. A conflicting edit must be resolved explicitly; it is never
   silently overwritten. Save a local copy before leaving a conflicted session.
4. Release claims or leave when finished. Claims renew every minute in the
   desktop and expire after five minutes if an editor disconnects or crashes.
   Expiration does not authorize an old session to publish without a new claim.

Claims coordinate publication; local canvas editing is still permitted outside
a claim so work can be saved independently. Schematic, technology, cell creation,
project settings and object reordering require leaving the layout-only session.
Native text collections lack stable IDs and merge as one atomic collection.
No automatic geometric/DRC conflict resolution is implied by an object merge.
Run physical verification after combining edits. All participants must resolve
the same locked PDK assets locally when running external verification.

Tests use two independent Python processes, a crashed process holding the OS lock, expired/reclaimed leases, overlap,
three-way conflicts, interrupted atomic writes and two complete desktop windows.
Hosted Windows Server and Linux checks do not establish consumer Windows or
arbitrary network-filesystem qualification.
