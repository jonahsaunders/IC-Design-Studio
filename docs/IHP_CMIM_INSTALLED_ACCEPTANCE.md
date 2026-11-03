# Installed IHP catalog capacitor acceptance

The installed gate checks the repaired ordinary `cap_cmim` workflow through the
actual packaged application. It requires one fresh catalog/editor lifecycle and
two fresh managed native jobs: Magic/Netgen and public IHP KLayout/Netgen.
Implementation and source-development checks are complete; a passing result
from both newly built platform candidates is still required. The older desktop
candidate does not contain this gate or the ordinary-reference repair.

## Finite selection

The GUI installs the shipped IHP package in its registry, places the ordinary
catalog device, connects its two terminals, edits width from 7 to 8 and back to
7 micrometres, saves, closes and reopens the document. It exports the actual
schematic, GDS and OASIS and captures the application's ordinary X reference.
The shipped mask-only fixture provides the previously audited 7 by 7 micrometre
imported layout; it supplies no schematic, model or hand-written LVS reference.
Its provenance and original Apache-2.0 notice are retained beside the fixture.

The parent checker launches the same installed executable for both native jobs
and independently rechecks the saved projects, ordered electrodes, original and
projected references, raw extraction, complete native stages, zero DRC findings
and strict LVS results. Source dimensions, area, perimeter and multiplicity are
read exactly; a rounded nearby value cannot satisfy the default-device check.
The gate validates normal managed-runtime readiness before and after the GUI
lifecycle. The parent independently rechecks runtime files and distributed
resources around both native jobs. Explicit reuse of a stale source-development
setup cannot satisfy this gate.

For a clean, exact candidate with its normal runtime setup complete:

```text
python scripts/verify_frozen_ihp_cmim.py --executable PATH_TO_INSTALLED_EXECUTABLE --expected-commit FULL_COMMIT_SHA --timeout 900 --out FRESH_EVIDENCE_DIRECTORY
python scripts/verify_frozen_ihp_cmim.py --readback RETAINED_EVIDENCE_DIRECTORY --expected-commit FULL_COMMIT_SHA
```

Offline readback uses the candidate's Git blobs and retained raw evidence. It
does not require the original installation path to exist and interprets recorded
paths on their original operating system. A source GUI run is useful during
development but explicitly fails the installed-only header checks.

## Desktop and release integration

Windows runs this gate against the actual installed executable before uninstall.
Linux runs it against the frozen distribution with its normally prepared managed
runtime. Both execute it before the longer IHP resistor acceptance. Complete
diagnostics are retained even when a later gate fails.
The early release-tools job installs the already pinned KLayout 0.30.5 reader
for the saved-stream controls; GUI dependencies are unnecessary in that job.

Release preparation, cross-platform assembly and publication each rederive the
raw receipt and compare it with the platform result. They also require the full
tested distribution to match the delivered ZIP or tar, including confined Linux
file links. Windows uninstaller metadata is recorded separately from portable
application bytes. Missing evidence, changed files, extra executable/resources,
unsafe archive paths, inconsistent receipts and expanded qualification claims
fail validation. No additional full runtime archive is copied into the evidence.

The Windows CI workflow now builds the native component before the existing full
core suite, requires it to load in the ordinary test environment, and checks its
source/compiler/binary identity again before packaging. This removes the former
second compilation and full core suite inside the installer build. Standalone
`build_windows.ps1` retains its original default checks. Hosted time savings and
the real compiler path still require measurement on the new candidate.

## Scope and remaining work

This is a finite installed integration gate for one default rectangular device
and two checking routes. Physical fault controls and maximum-area boundaries
retain their separate [source acceptance](IHP_CMIM_LVS_REFERENCE.md); this gate
does not repeat or inherit their negative-control execution. It does not qualify
continuous operating ranges, other geometry classes, arrays, electrical/model
calibration, statistical behavior, reliability or the complete family.

The [remaining device requirements](IHP_CMIM_REQUIREMENTS.md),
[progress tracker](QUALIFICATION_PROGRESS.md) and
[source integration record](validation/ihp-cmim-installed-source-integration-2026-11-02.json)
distinguish implemented checks from completed frozen acceptance. The chunk 7
gate and all partial device statuses remain unchanged.
