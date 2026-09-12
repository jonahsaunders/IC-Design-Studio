# Experimental dev21: component shortcuts, workflow and recovery

This increment targets `experimental`. It includes the earlier source/library
selector, vector symbol previews, wire selection, bulk layout placement,
hierarchy menu actions and native floating frames, plus the following work.

## Components and selection

Both the standard Devices panel and imported-symbol browser offer **Favorites**
and **Recently placed**. **Add to favorites** applies to the selected component
from its original library. The source selector is remembered between openings;
project cell and native definition identities stay scoped to their projects.
Arrow keys choose visible results while focus remains in search; Enter begins
placement. An empty search result cannot place the previous selection. Large
symbol lists debounce typing and cache a bounded number of symbol previews.

In Select mode, the schematic and layout canvases outline the object a normal
click will select. The hint names overlapping objects and the next selection
for **Tab** or **Alt+click**. Layer locks and selection filters apply to the hint
and the actual hit test. Hovering does not edit the design or its selection.

## A persistent design workflow

Choose **Workflow** on the main toolbar or **Schematic/Layout → Design workflow**.
The dock follows the current circuit or selected testbench. Its summary separates
missing implementations, unsupported devices, connection findings and matching
findings. **Findings** lists the object and reason; double-click or choose
**Go to finding** to select it in the relevant editor. Changed designs invalidate
old findings immediately. Verification results retain their original revision.

**Place missing devices** opens the existing reviewed layout transaction. It
does not invent implementations for unsupported parts. The **Steps** and
**Physical comparison** tabs retain the existing verification and review tools.
The dock is saved with the workspace and can float using a native frame.

## Durable unsent review drafts

Text typed into a checkpoint's review composer is saved locally after a short
pause, and flushed when switching checkpoints, hiding the panel or closing the
app. Reopening the same session restores the checkpoint's text and reply context.
Attachments must be reviewed again before posting. Restoring a draft never sends
it to the server.

The private `.review-drafts` sidecar is bound to server, workspace and participant.
It contains text and checkpoint/thread identities, without access tokens. Drafts
are limited to 100 checkpoints and 1 MiB total. Storage errors keep text visible
and preserve the last durable draft. Closing is blocked while a draft cannot be
saved; copy or clear the text explicitly if storage cannot be repaired.

The submitted-action outbox still owns retry IDs. A successful acknowledgement
clears only the matching draft, preserving newer text entered during the request.
No collaboration protocol or server database migration is required.

Recovery snapshots now reuse unchanged parts of a previous **isolated** snapshot.
They still compare mutable caller data and preserve JSON scalar types, including
changes made in place. Writers remain ordered; full validation, serialization,
previous-file retention and durable writes keep their existing semantics.
Initial snapshots and scanning large projects still cost time on the UI thread.

## Packages and native desktop acceptance

About includes the exact source commit, branch and a copyable display/build
diagnostic report. Packaging requires committed source and embeds its identity;
archive qualification checks it against the expected commit.

The preview workflow accepts `experimental` and uses an immutable
`experimental-vVERSION-COMMIT` draft tag. It waits for both desktop packages,
interoperability and physical qualification, then assembles source, packages,
evidence and checksums. `main` promotion remains separate. PR desktop workflows
also retain downloadable `release-Windows` and `release-Linux` payloads.

The packaged release probe includes component shortcuts, hover selection,
workflow findings, diagonal floating resize, restored size and offscreen window
recovery. Unplugging a display brings an unreachable floating title bar back to
an available screen. Hosted execution does not prove consumer desktop behavior.

Run the native acceptance tool on an installed Windows or Ubuntu desktop:

```text
ICDesignStudio --desktop-acceptance acceptance-dev21
```

On Windows use `ICDesignStudio.exe`. The tool creates an isolated test profile,
runs desktop gestures, then keeps the app open for the [native observations](NATIVE_DESKTOP_ACCEPTANCE.md).
It records the selected download's hash, build identity, display geometry/scales,
screenshots, automated results and separate operator observations. Unperformed
checks stay pending. Offscreen/minimal Qt cannot qualify native acceptance.

See [release status](RELEASE_STATUS.md) for executed evidence. Consumer Windows
10/11, native Ubuntu, mixed displays, accessibility and upgrade acceptance still
require records from those environments. Signing and public publication are
separate maintainer decisions.
