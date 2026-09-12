# Experimental dev21 source update

The [dev21 workflow and recovery update](UPDATE_0.22_DEV21.md) targets `experimental`.
Its versioned packages must pass checks for their own source commit. The dev20
draft below does not contain these changes. Local and hosted validation for this
update is recorded in [the dev21 validation record](validation/experimental-dev21.json).
Native consumer and mixed-monitor acceptance remains pending; use the
[native acceptance tool](NATIVE_DESKTOP_ACCEPTANCE.md) to record actual observations.

# Release status — 0.22.0.dev20 candidate

Dev20 resolves the detector's resistor extraction mismatch and internal pin-alias
findings with a verified upstream technology backport and strict full-circuit
LVS. The new optional DC startup setting supplies first-point voltage guesses,
allowing HSA to complete without relaxing timeouts or accuracy. The generated
native testbench includes both DUT views, supplies and embedded models.

## Confirmed dev20 hosted checkpoint

The experimental branch was merged through [PR #13](https://github.com/jonahsaunders/IC-Design-Studio/pull/13)
on September 12, 2026. Main commit `6b1e30f3d13c1dcb8d662523fd6cf4919f1b2a0d`
contains the completed via/Autovia and README changes from PRs #16 and #17.
[Release run 34703715977](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/34703715977)
passed both desktop/package targets, interoperability and physical qualification,
including the imported-detector Autovia test. Draft `v0.22.0.dev20` has all 12
expected assets uploaded; it has not been published.

The separate [main physical run 34703715839](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/34703715839)
was cancelled during the final Autovia GUI step near its 30-minute job limit.
The release workflow's physical job on the same commit passed in 29 minutes
37 seconds. This is evidence of little aggregate timing margin, not proof of an
application crash. Physical CI now separates inverter, analog, detector and
desktop work while retaining the `sky130` aggregate check and release evidence
artifact. Individual circuit timeouts, numerical tolerances and fault gates are
unchanged. New source commits still need their own hosted results.

Clean consumer Windows 10/11, native Ubuntu display/upgrade/accessibility,
physical LAN/VPN and signing decisions remain outstanding. See issues
[#8](https://github.com/jonahsaunders/IC-Design-Studio/issues/8),
[#9](https://github.com/jonahsaunders/IC-Design-Studio/issues/9),
[#10](https://github.com/jonahsaunders/IC-Design-Studio/issues/10) and
[release follow-ups](RELEASE_FOLLOWUPS.md).

## Executed dev20 evidence

The [validation record](validation/0.22.0.dev20.json) records the actual checks,
source hashes and engine evidence. See [the reproduction guide](OPEN_PROJECTS.md)
for commands, the extraction correction and the runnable testbench.

| Check | Result |
|---|---|
| Core regressions | 611 tests; 3 environment skips |
| Detector strict LVS | Full physical circuit matches uniquely; top pins equivalent; no property errors |
| Negative controls | Enable open, child substrate miswire and 14.10→13.94 µm length fault all detected |
| HSA detector sweeps | All 16 codes compared with the independent source reference, 301 points each |
| Native desktop bench | Saved/reopened project runs in HSA through the app engine; code 0 agrees with the reference |
| Desktop editing | Attachment, move/undo, both-view persistence, DC startup undo/reopen and the F5 analysis action checked in offscreen Qt |
| Layout exchange | 38 cells; exact region, text and hierarchy/array comparisons |

The HSA startup point and full sweep each retain the existing 120-second
qualification limit. Solver and LVS tolerances remain unchanged. Local Linux
execution needed the same temporary-file path shim and offscreen Qt platform
as dev19. Package and platform claims require the exact commit's Windows/Linux
Actions results; no signed release is implied.

Two upstream HVI parent/child warnings remain in Magic's source-to-GDS conversion.
This LVS result uses fresh extraction of the original native Magic cells; exact
GDS/native/GDS roundtrip does not certify the earlier conversion step. Transient
hysteresis, full PVT and extracted simulation remain outside this detector's
nominal DC gate.


The previous dev19 update added [real open-project import qualification](OPEN_PROJECTS.md), reviewed
layout attachment, native array expansion, layout text preservation and
[restart recovery for submitted review actions](REVIEW_RECOVERY.md). New imported
layers remain visible when reloading saved layer preferences. Unowned shape moves
avoid reconstructing unrelated footprint groups.

## Earlier dev19 source evidence

The [local validation record](validation/0.22.0.dev19.json) records Linux/Python
3.12 source execution, exact source/deck hashes and its environment limits.

| Executed check | Result |
|---|---|
| Core regression | 607 tests, 3 environment skips; the skipped Magic exchange also passed separately with the pinned engine |
| Pinned physical inverter | All 4 nominal and deliberate-fault cases passed |
| Analog qualification | All 45 simulation, extraction and deliberate-fault cases passed |
| Bundled PDK simulation | GF180 startup, SKY130 inverter and native catalog paths with spaces passed |
| Review recovery desktop | 5 scenarios passed, including real lost HTTP acknowledgement, panel reconstruction and exactly-once retry |
| Imported detector desktop | Reviewed attachment, exact undo/redo, move/undo, save/reopen, child navigation and visible layer restoration passed |
| 3D software viewer | 5 desktop scenarios passed with the offscreen renderer |
| Detector schematic | Native/reference and exported/reimported hierarchy matched through pinned Netgen |
| Detector nominal DC | All 16 codes passed; switching thresholds 3.30–5.46 V matched the reference on the same 10 mV step |
| Detector layout exchange | 38 cells and 1,368 cell/layer comparisons passed exact geometry, text and hierarchy checks |
| Detector full physical consistency | Historical dev19 failure; resolved by the dev20 extraction correction above |
| Detector app-default HSA | Historical dev19 timeout; resolved for the dev20 bench using DC startup hints |

These results were produced from the dev19 working tree based on `c3e3503`.
The sandbox needed a temporary-file path shim for ngspice and an offscreen Qt
platform. They do not qualify packaged binaries, native displays or physical
networks. The Windows/Linux and external-tool workflows must pass on this PR's
exact commit. A release has not been published.

For the 10,000-shape workload on this host, median commit time changed from
40.59 to 34.77 ms and complete edit/check/recovery time from 259.17 to 236.67 ms.
The baseline used three samples and dev19 five; these are small local samples,
not a cross-machine performance guarantee. The evidence retains stage medians;
recovery snapshot copying and broader workloads remain open.

Physical LAN/VPN/firewall acceptance, consumer-machine installation/upgrade,
accessibility, signing and macOS qualification remain tracked in
[release follow-ups](RELEASE_FOLLOWUPS.md). General offline design editing and
unsent review draft recovery also remain roadmap items.

## Earlier candidate updates

Dev18 adds [guided encrypted network hosting](LIVE_COLLABORATION.md#host-a-session-on-your-network),
automatic host certificates, invitation-scoped trust, connection checks and
saved HTTPS workspace restart. Schematic annotations support direct selection,
dragging, text editing, duplication, deletion and personal undo in shared sessions.
Source and packaged desktop acceptance exercise two editors over real HTTPS on
an isolated loopback test interface, including wrong-certificate and hostname
rejection. Physical LAN/VPN devices and firewall configurations require separate
acceptance. Use dev18 desktops for certificate-bearing invitations; database 3,
document protocol 2 and recovery journal 2 remain unchanged. Consult this commit's
Windows/Linux Actions results for package qualification.

Dev17 adds [button-driven local hosting](LIVE_COLLABORATION.md#start-a-local-server-with-a-button),
automatic host key handling, persistent server identity and automatic restart
when resuming saved local workspaces. Source and installed Windows/Linux checks
exercise two editors, startup failures, credential isolation and undo after
restart. This adds no database or document protocol migration.

Dev16 adds [automatic workflows and threaded review](WORKFLOW_REVIEW_0.22.md),
with an explicit testbench context, visual ECO inspection and server-enforced
reviewer permissions. The server database upgrades to version 3; document
protocol 2 and shared-folder version 2 remain unchanged. Each platform must pass
its exact-commit checks before its packages are considered qualified.

Dev15 adds [schematic and layout collaboration](SCHEMATIC_COLLABORATION.md),
protocol/database version 2, atomic hierarchy edits, electrical conflict detection,
schematic presence and checkpoint comparisons. Windows/Linux CI includes a new
two-editor desktop acceptance run and installed schematic editing/review probes.

Dev14 implements the six [engineering workflow areas](PROFESSIONAL_WORKFLOWS.md):
precise editing, document/recovery services, parameterized physical variants,
analog qualification, verification test plans, and revision-based team review.
The Windows/Linux workflows include actual simulation, new desktop acceptance
scenarios, failed-storage recovery and installed application checks. The physical
gate adds 45 analog reference and deliberate-fault cases to the pinned inverter.
Consult the exact commit’s Actions results before preparing release artifacts;
this source update does not publish a release or claim commercial/foundry signoff.

## Historical release evidence

The current source adds release payload verification, native hierarchy/bus
qualification and a pinned physical gate. A build is a release candidate until
its exact commit and downloadable files pass the workflows and are recorded in
the attached validation manifests. No published release is implied by this file.

## Release-gate baseline before the dev12 feature update

The exported Xschem hierarchy now resolves child schematics and preserves literal
quotes in scalar-bus simulation commands. [Interoperability run 34527794472](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/34527794472)
and [physical run 34527794460](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/34527794460)
passed. [Desktop run 34524685553](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/34524685553)
previously passed both packaged desktop targets for the release-payload changes.
These runs establish the release-gate baseline, not qualification of later dev12
feature commits. Consult the dev12 PR and draft release for their exact checks.

Dev12 adds [capacity, hierarchy ECO and concurrent editing](LAYOUT_SCALE_AND_COLLABORATION.md).
Local checks include 502 full-suite tests (two external-tool skips), seven focused
capacity/ECO tests including the subsequently added GDS/OASIS and route-retarget
cases, and three desktop scenarios with two editor windows. The million-instance
synthetic overview took approximately 0.72 seconds in the local offscreen test.
Consumer machines and network-filesystem semantics are not covered by that run.

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

The dev12 workflows qualify their own outputs. Consult the specific PR or draft
release records for completion; the dev10 results cannot substitute for them.
Clean Windows 10/11 consumer-machine tests, native Linux display review, upgrades,
accessibility and signing still need their own evidence. macOS is not qualified.
See [release notes](RELEASE_0.22.md), [downloads](DOWNLOADS.md), and
[reproducible qualification](QUALIFICATION_0.22.md).
