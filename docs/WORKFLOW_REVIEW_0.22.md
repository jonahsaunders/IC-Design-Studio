# Workflow and team review — 0.22.0.dev16

## Dev19 recovery and import additions

[Submitted review recovery](REVIEW_RECOVERY.md) extends the threaded review flow
with durable retries across restart. [Real-project qualification](OPEN_PROJECTS.md)
adds layout attachment and independently recorded import/physical results. The
new attachment reviews cell names and does not create device-level LVS mappings.

This increment improves the existing design workflow, linked layout-change
inspection and checkpoint discussions. It does not add a new physical process
qualification or increase the supported collaboration size limits.

## One workflow from either editor

Open **Schematic → Design workflow** or **Layout → Design workflow**. Both open
the same window. Choose the saved testbench explicitly; its corner and temperature
appear beside it. Switching between schematic and layout retains the selection.

The next-action button links to the relevant existing tool. Device-link,
connectivity and matching checks run on an isolated background snapshot, then
update after edits. An old worker result is discarded when its project, cell or
revision no longer matches. Inspection waits while a drawing gesture or property
draft is active. Completed jobs update the comparison for the selected testbench.
The displayed corner belongs to that saved testbench; edit its settings or use a
test plan to run other conditions.

The comparison retains the original results and clearly identifies stale inputs.
Opening the workflow never runs a simulation or applies a layout change. A manual
refresh remains available to retry a failed inspection.

## Inspect a schematic-to-layout change

Choose **Review changes** in the workflow, then select a device in the change
list. Its parameters, connected net names and physical-object counts appear below.
**Show in schematic** and **Show in layout** select its linked objects in the
corresponding editor. Missing physical implementations disable the layout button.

Select the updates to preview. The proposal lists affected devices, nets, object
counts and adjusted routes. **Inspect geometry before and after** opens a visual
revision comparison; switch between schematic and layout and zoom as needed.
Applying the reviewed candidate is one undoable transaction. If the project
changes, reopen the change review. Existing connectivity, layer-lock and stale
candidate checks continue to apply.

## Invite a reviewer and discuss a checkpoint

All collaboration controls remain under **Tools → Collaboration**. The owner can
choose **Can review · comment and approve** when creating an invitation.

| Permission | View | Discuss and decide | Edit design | Save checkpoints / share runs | Manage invitations |
| --- | --- | --- | --- | --- | --- |
| View | Yes | No | No | No | No |
| Review | Yes | Yes | No | No | No |
| Edit | Yes | Yes | Yes | Yes | No |
| Owner | Yes | Yes | Yes | Yes | Yes |

Reviewers never reserve design objects and cannot perform design undo/redo.
The server enforces these permissions independently of the desktop controls.

In **Team review**, select a comment and choose **Reply to discussion**. The reply
inherits the root discussion's checkpoint and attachment. Replies appear together
under that discussion. Select either a root or reply to navigate to its object.
The root author or owner can resolve or reopen the complete discussion. A new
reply changes the discussion version, preventing an outdated resolution from
silently closing an unseen reply. Reopen resolved discussions before replying.

Posting uses stable request IDs: retrying a lost acknowledgement does not create
duplicate replies. Accepted discussions survive server restarts. Pending review
requests still live in desktop memory; restart-durable review drafts, assignments,
notifications and a multi-edit offline queue remain future work.

## Upgrade and compatibility

Back up the server using [the consistent backup procedure](LIVE_COLLABORATION.md#server-persistence-and-limits)
before updating. Dev16 migrates SQLite **database version 2 to 3**, retaining
existing comments as root discussions and preserving accepted retry identities.
Older servers refuse database version 3; use the backup to roll back.

The document transport remains protocol 2. Dev16 advertises review API 2. Use a
dev16 server and desktops for reviewer invitations and threaded discussions.
Dev15 editing sessions remain compatible with the document transport, but their
review UI cannot present threads or accept reviewer sessions. The shared-folder
journal remains version 2.

## Editing performance and validation

Connected editing reuses unchanged geometry records, contact adjacency sets and
shape-component partitions. Candidate graphs remain isolated: a rejected join,
split or spacing violation cannot corrupt the accepted graph. Snapshot copying
for durable recovery still happens on the UI thread; this increment does not
claim to remove that remaining latency source.

Run `scripts/benchmark_layout_pipeline.py` to measure the complete editor gesture,
painting, durable recovery and declared-rule checks. The release's measured
results are recorded in `docs/validation/0.22.0.dev16.json`.

Linux/offscreen medians from three samples per workload, compared with dev15
commit `ef8e46c` on the same host:

| Workload | Dev15 | Dev16 |
| --- | ---: | ---: |
| 10,000 shapes: connected edit | 172.5 ms | 41.3 ms |
| 10,000 shapes: edit, paint, recovery and checks | 405.3 ms | 242.3 ms |
| 1,000 shapes: edit, paint, recovery and checks | 55.2 ms | 66.8 ms |

The smaller workload regressed in this sample. These observations do not establish
a uniform speedup or native-display frame rate. Initial loading and recovery
reopening are measured separately in the evidence.

`tests/gui_workflow_review.py` exercises workflow selection across both editors,
automatic refresh, linked device navigation, visual previews, exact undo/redo,
stale-review rejection and two HTTP-connected desktops exchanging review replies.
The Windows and Linux desktop jobs run it and retain screenshots. The installed
application probe also opens the background workflow and posts a reviewer comment
with a threaded response. Core tests cover authorization, migration, retry and
restart behavior, and speculative graph isolation.
