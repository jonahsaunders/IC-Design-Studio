# Dev25 package acceptance handoff

Reviewed 2026-09-21. The existing unpublished [dev25 draft](https://github.com/jonahsaunders/IC-Design-Studio/releases/tag/untagged-a3463df6d52385cb7532)
targets `a88cfe1cfe20254638b7bd97ec9128e843578282`, whose source tree matches
experimental commit `a2df5e81654e7509f82aa9dceaf099cc476f4d6a`. All six hosted
gates passed in [run 35550664971](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/35550664971).
The [review record](validation/dev25/release-acceptance-review.json) identifies
the 16 assets, GitHub-reported SHA-256 digests and job results. These results do
not cover later experimental performance changes or establish consumer acceptance.

## 1. Exact-package consumer checks

Download the draft's setup executable or complete archive and checksum file.
Verify the bytes on each test machine before execution. The package digests
reported by GitHub for this draft are:

| Package suffix (prefix `IC-Design-Studio-0.22.0.dev25-`) | SHA-256 |
|---|---|
| `Windows-x64-Setup.exe` | `36385a2882ee2292bbb0c775bf9fbd507256e26d70a6a4d8b307ea79903efe54` |
| `Windows-x64-Portable.zip` | `7d3149eaed4baec170b4f3c03d4e3f6ba1685bf8a51dc1d64c71c8ebaaa4bd79` |
| `Linux-x86_64.tar.gz` | `1096a4a651a02c87767d86193074ec33f9a96e7f672f1a897dc941bac7c5abb3` |

Use a clean test account without a preinstalled Python/EDA toolchain. Keep the
complete application directory. From that directory, run:

```powershell
.\ICDesignStudio.exe --desktop-acceptance acceptance-dev25-win11-100
```

```sh
./ICDesignStudio --desktop-acceptance acceptance-dev25-ubuntu24
```

Select the downloaded installer/archive in the acceptance window. Verify **About**
identifies the full package commit above. Use a new evidence directory for every
OS/build/display configuration. Follow the full [native checklist](NATIVE_DESKTOP_ACCEPTANCE.md):
first waveform and supported PDK example; save/reopen; cancellation/recovery;
paths with spaces; installer and portable launch; upgrade/settings preservation;
100/150/200% and mixed-monitor scaling; keyboard/screen-reader controls; offline
VGA presets with real sound and keyboard/Gamepad input; uninstall preserving projects.

Attach the saved acceptance JSON, screenshots, OS/build and package digest to
[Windows #8](https://github.com/jonahsaunders/IC-Design-Studio/issues/8) or
[Ubuntu #9](https://github.com/jonahsaunders/IC-Design-Studio/issues/9).
Do not mark unperformed observations passed. This follow-up ran no consumer
machine checks; the hosted Windows Server and virtual/offscreen Linux evidence
remain separate. Failed checks need a reproducible defect and a new qualified
package if application changes are required.

## 2. Signing decision and physical collaboration

The signing decision in [#10](https://github.com/jonahsaunders/IC-Design-Studio/issues/10)
is still **pending**. Record one maintainer decision before public distribution:

| Choice | Required record/action |
|---|---|
| Signed preview | Identify the certificate/service and configure credentials; sign before execution and checksums, rebuild, then verify the exact downloadable installer and application signatures. |
| Unsigned engineering preview | Explicitly approve that distribution policy in #10, keep download instructions accurate, and retain actual clean-machine installation observations. |

Neither choice is selected by this document. The existing draft remains unpublished.
Signing changes the package bytes, so the digests above cannot qualify signed replacements.

For [physical LAN/VPN #31](https://github.com/jonahsaunders/IC-Design-Studio/issues/31),
use two separate physical computers running identified packages. Record each
OS/build, package digest, firewall and network/VPN configuration. Exercise:

- TLS certificate trust and incorrect-certificate rejection; server restart/reconnect.
- View/edit invitations, expiry/revocation, concurrent schematic/layout edits,
  conflict rejection, reservations and personal undo.
- Network interruption during an edit/review, client restart and exactly-once recovery.
- The intended VPN and a firewall-restricted LAN, with actionable failure diagnostics.

Retain sanitized logs/screenshots and observations in #31; exclude invitation
secrets and private project data. Physical LAN/VPN checks were not executed here.
Distributed campaign workers have a separate [two-host protocol](CAMPAIGN_WORKER_ACCEPTANCE.md)
and are not qualified by collaboration or same-host tests.

## 3. Source and release records

The release status, downloads, dev25 notes and source checkout instructions now
identify the merged implementation and successful draft. Historical numerical
evidence keeps its original source identity. New experimental changes need all
six hosted gates on their own commit, and new package acceptance records.
The `Prepare draft preview release` workflow supports manual dispatch on
`experimental`; ordinary source changes do not necessarily match its push filters.
Creating a draft does not publish it or close the manual gates.

## 4. Editing responsiveness

The follow-up removes layout copying from electrical flattening, avoids a second
full-cell copy during schematic transaction repair, and reuses device icons
within each outline refresh. See [desktop responsiveness](DESKTOP_RESPONSIVENESS.md)
for retained measurements, correctness checks, explicit budgets and remaining work.
