# Release status — 0.22.0.dev11 candidate

The current source adds release payload verification, native hierarchy/bus
qualification and a pinned physical gate. A build is a release candidate until
its exact commit and downloadable files pass the workflows and are recorded in
the attached validation manifests. No published release is implied by this file.

## Confirmed hosted baseline: dev10

On September 10, 2026, [desktop run 34515234695](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/34515234695)
and [interoperability run 34515234864](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/34515234864)
completed successfully for PR #3, whose head was
`3bea7edc5b6d3760a72d9ff05c46a3f0ef75961d`, merged into `main` at `993adc3`.

| Executed gate | Result |
|---|---|
| Ubuntu 24.04 core suite | 484 tests; 1 skipped (Magic runs in the separate interoperability job) |
| Windows Server 2022 core suite | 484 tests; 3 skipped (Xschem, Magic, POSIX process-group check) |
| Linux desktop and frozen application | Passed |
| Windows installer and installed application | Passed, including 100/150/200% scale, shortcut, file association and uninstall |
| Independent GF180 six-case comparison | Passed on Linux |
| External interoperability suite | 43 tests passed, including real Xschem and Magic |

These are hosted results, superseding the earlier blanket statement that Windows
installer execution was pending. The [original dev10 local record](validation/0.22.0.dev10.json)
remains unchanged: its `not_executed` entries describe that earlier local run.
The separately assembled embedded-Python portable ZIP was a different artifact
and is not qualified by the CI installer's success.

## Remaining release acceptance

The dev11 workflows qualify their own outputs. Consult the specific PR or draft
release records for completion; the dev10 results cannot substitute for them.
Clean Windows 10/11 consumer-machine tests, native Linux display review, upgrades,
accessibility and signing still need their own evidence. macOS is not qualified.
See [release notes](RELEASE_0.22.md), [downloads](DOWNLOADS.md), and
[reproducible qualification](QUALIFICATION_0.22.md).
