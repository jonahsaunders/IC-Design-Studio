# IC Design Studio 0.23.0 — desktop engineering preview

0.23.0 prepares a public desktop release with Windows x64 installer and portable
downloads alongside the Linux x86_64 archive. The application remains an
**engineering preview** with the platform and process limits below. The public
destination is [release v0.23.0](https://github.com/jonahsaunders/IC-Design-Studio/releases/tag/v0.23.0);
assets become available after fresh qualification and publication complete.

## Downloads and build identity

The release preparation requires these matching application assets:

| Asset | Purpose |
|---|---|
| `IC-Design-Studio-0.23.0-Windows-x64-Setup.exe` | Per-user Windows installer |
| `IC-Design-Studio-0.23.0-Windows-x64-Portable.zip` | Complete portable Windows desktop |
| `IC-Design-Studio-0.23.0-Linux-x86_64.tar.gz` | Complete Linux desktop archive |
| `IC-Design-Studio-0.23.0-Source-Windows.zip` / `IC-Design-Studio-0.23.0-Source-Linux.zip` | Corresponding source for each platform's package |
| `IC-Design-Studio-0.23.0-Validation-*.json` / `IC-Design-Studio-0.23.0-Evidence-*.zip` | Exact build identity, asset hashes and retained execution evidence |
| `SHA256SUMS-0.23.0.txt` | Checksums over the final released files |

Additional qualification archives can be split into numbered parts with a
`.zip.parts.json` manifest. Use the supplied reassembly helper and verify the
reconstructed hash; see [large evidence archives](RELEASING.md#large-evidence-archives).
[Downloads](DOWNLOADS.md) explains installation, first setup and checksum checks.
Keep the complete extracted directory, including `_internal`, beside the app.

All seven release gates must pass for the same clean 0.23.0 source commit:
desktop/package, external interoperability, pinned physical, digital, VGA,
statistical campaigns and reference compatibility. Windows installer and
portable execution, Linux archive execution and frozen-app checks must match
the supplied files. Earlier dev25 checks do not qualify renamed 0.23.0 binaries.
The release's validation records provide the actual run, commit and results;
these notes do not substitute for those records.

## Editing and simulation repairs

- Project-tree context menus preserve the active editor and pending properties
  when dismissed. An action on another cell resolves the existing draft before
  visibly switching to that cell.
- Undo and redo resolve unapplied property edits consistently. Invalid property
  input stays available for correction rather than being lost during history
  navigation.
- Save rejects invalid analysis input without silently saving another analysis.
  Closing or replacing a document offers a recoverable Cancel/Discard decision,
  including navigation from the example gallery and Project Hub.
- Stop honors a selected active simulation and falls back to the running worker
  when the selected result has already completed.
- Manual wiring preserves the correct schematic position while drawing and
  extending wires.

## Engine setup and navigation

Student Hub Digital lessons honor the selected Included or Custom toolchain.
When setup is needed, a lesson run continues once after successful setup;
changing the lesson design or cancelling the request requires a fresh run.
Existing custom executable paths are preserved, and equivalent paths no longer
cause false duplicate-tool failures.

SAR experiments, Mixed Signal lessons and the capstone check their separate
native `ngspice`, `iverilog` and `vvp` prerequisites and open the matching setup
guidance. Their native engine requirements remain separate from the included
managed digital/physical runtime. See [lesson engines](STUDENT_HUB.md#engines-and-models)
and [SAR setup](MIXED_SIGNAL_SAR.md#local-engine-setup).

Project Hub fits smaller logical displays, provides compact navigation and
scrolls its creation controls into reach. Workspace sizing honors the active
Design or Student Hub minimum through queued display fitting, monitor changes,
maximized windows and fullscreen transitions.

F1 opens the current rendered, linked user guide. Enter and Shift+Enter move to
the next and previous document search matches without closing the help reader.
Historical documentation remains separately accessible. Source archives with an
unknown Git identity open README links on `main`; identified builds retain
their exact source revision.

Student progress now distinguishes the selected inverter PDK course from the
overall total across available PDK revisions. Each revision keeps its own
progress identity.

## Supported scope and remaining acceptance

- Windows x64 packages use the existing **unsigned** installer/portable recipe.
  The managed digital/physical runtime uses Studio's private WSL 2 distribution;
  enabling Windows support can require internet access, elevation and a restart.
- Linux x86_64 targets Ubuntu 24.04 with glibc 2.39 or newer. macOS has no
  qualified desktop package.
- Included analog simulation subsets are not complete foundry PDKs. Physical
  verification requires matching locked decks/assets; qualification applies to
  the recorded fixtures and supported process scope, not fabrication signoff.
- Hosted Windows/Linux checks remain separate from all clean consumer-machine,
  mixed-monitor, screen-reader and physical LAN/VPN observations. See
  [release follow-ups](RELEASE_FOLLOWUPS.md) and
  [native acceptance](NATIVE_DESKTOP_ACCEPTANCE.md).
- General offline collaborative editing, managed internet hosting and an
  automatic application updater remain outside this release's supported scope.

Public publication uses the canonical `v0.23.0` tag after the required assets and
same-commit gates pass. Ordinary automatic branch previews remain drafts.
See [public release preparation](RELEASING.md#public-release-preparation).
