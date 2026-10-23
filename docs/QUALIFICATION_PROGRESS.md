# Chunks 1–12: progress and forecast

**Snapshot: October 23, 2026.** Latest local evidence:
[RF qualification and CI recovery](validation/chunk7-ci-recovery-2026-10-23.json),
with exact source hashes and baseline
[`b4e00d9`](https://github.com/jonahsaunders/IC-Design-Studio/commit/b4e00d9bb89546feb3d9dfc728d57c2558bcdc18)
on `experimental`. This tracker is updated during project work, without a
scheduled background monitor.

The [latest CI review](CHUNK7_CI_RECOVERY.md) found **nine successful, four failed
and three cancelled workflows** at `b4e00d9`. This supersedes its earlier pending
snapshot. All three RF runners now reconstruct and verify the original corner
inputs; both hosts pass the full branch, reverse-bias/noise and transient batches,
the application checks and 21 focused tests. An independent inventory audit
verifies 8,730 retained raw files per host. Inputs, equations and thresholds are
unchanged. The initial incompatible Linux engine rejection is retained; the
reviewed RF engine passes the complete rerun.

IHP's global job budget and the affected dependency-download bounds are fixed
without removing any qualification gate. Fresh hosted and final installed
acceptance are still required. The requested rough 60% estimate remains low
confidence; these repairs do not justify increasing it or promoting any of the
286 partial entries. Seven required bindings and the broader device gates remain
open.

A verified 154.1 MB archive retains 1.71 GB of logical evidence. Restoring 1,203 source/input files reproduces all eight RF bias pilot cases and both transient pilot conditions. All original failure logs and the incompatible-engine rejection remain retained. The 35 additional evidence/matrix checks and release-document checks pass. Verified temporary copies were removed: 494.0 MB from Windows and 1.07 GB inside Linux; no administrator access or disk compaction was used.

The [MiM parameter correction](SKY130_MIM_MULTIPLICITY.md) fixes unused VM emission in a
separately versioned default and exact-source local import. **Both hosts pass 54 native
runs and all 1,728 faulty instances**, plus independent raw/deck audits. Both final
pilots, both source desktops, twelve rotated square layouts and six physical faults
pass. **Both complete source suites pass 3,301 tests** (Windows 65 skips, Linux 58). The
old default and upstream assets remain recoverable; saved projects are not silently
migrated.

A verified 90.4 MB archive retains 1.06 GB of logical evidence. Restoring 1,924
source/input files reproduces 18 native runs and all 72 faulty instances with identical
source and engine hashes. The local Git test-harness mistake was repaired with checked
source preservation, and final Linux tests verify that the live Git metadata stays
unchanged. These results close the reviewed parameter defect without promoting any
device or completing chunk 7. Exact new-revision hosted/installed acceptance remains
pending.

Final evidence bookkeeping also passes 32 checks and the release-document/workflow checks. The verified 10.3 MB checkpoint retains the restored replay and full-suite logs. Archived temporary copies were removed: 375.3 MB from Windows and 595.4 MB inside Linux. This used no administrator access or WSL disk compaction.

Final follow-up: these application fixes and the main tracker are pushed as
[`b4e00d9`](https://github.com/jonahsaunders/IC-Design-Studio/commit/b4e00d9bb89546feb3d9dfc728d57c2558bcdc18),
and the remote `experimental` branch matches. The exact-revision hosted snapshot
has four successful, three running, four pending and five queued workflows;
none has reported failure. Pending and queued runs are not acceptance results.
This follow-up note is local until the next code push, preserving the active
acceptance runs. The completed batch removes the reviewed MiM parameter defect;
seven unavailable required bindings, complete operating ranges, wider physical
and process-option coverage, and exact final installed acceptance still prevent
chunk-7 closure. The rectangular MiM rotation issue remains open: the pinned
public generator provides a physical orientation convention, but a separately
tested extraction correction has not yet been implemented.

The preceding [second MiM layout batch](SKY130_SECOND_MIM_LAYOUT.md) adds square
SKY130 metal4/cap2m/metal5 capacitors. **28 rotated layouts, 35 detected faults
and 21 extracted electrical comparisons pass.** Both host audits, 32 distinct
targeted tests per host, both source editors and Windows/local-native handoff
pass. The original small-landing failure was fixed. Rectangular rotation still
exchanges native W/L and fails strict comparison; the new recipe rejects it.
Those failures remain visible. This advances one physical recipe without
promoting device statuses or completing chunk 7.

A verified 95.3 MB archive retains 1.90 GB of logical evidence. Restoring 2,363
source/input files reproduces one layout, one electrical comparison and all
five faults. Both hosts pass the additional 32 evidence/matrix checks and the
release-document checks, bringing this batch to 64 distinct targeted tests per
host.
The older GF180 gate retains the exact originally tested source bytes; it is
not reassigned to this changed application.

At the start of this batch, experimental matched GitHub at `3c1b4b8`; hosted
checks were still in progress (latest snapshot: seven passed, seven running,
three pending; no failures reported). An empty exact-revision API response was followed
by a successful query showing all 17 runs, so the empty response is not a test
result. The new capacitor changes require their own hosted acceptance.

Final local follow-up: application and main tracker changes are pushed as
[`cf59069`](https://github.com/jonahsaunders/IC-Design-Studio/commit/cf590699f11b30c6edd7b103416e71c0ddd9a068),
and the remote experimental branch matches. The new revision has four successful,
five running, two pending and six queued workflows, with no failure reported
at this snapshot. This is not final hosted acceptance. Both verified archives
(95.3 MB evidence plus 10.4 MB checkpoint) retain the results and restored-source
replay. Verified temporary copies were removed: 94.9 MB from Windows and
2.04 GB inside Linux, without administrator access or disk compaction. That
follow-up note was retained locally until this code batch.

The latest [SKY130 default-geometry batch](validation/sky130-mos-defaults-2026-10-22.json)
fixes seven newly placed short symbols that failed model selection. Both hosts
pass **14 independent DC/AC cases for all 42 available MOS defaults**, with
588 valid device comparisons and 756 detected faulty instances per host.
Independent raw audits verify 92 files and 177,112 current samples across both
hosts. All 67 distinct affected tests and seven source-editor workflows pass
per host. The original model/package bytes and existing chosen dimensions are
preserved; the [guide](SKY130_MOS_DEFAULTS.md) records the exact source checks.

The 28.3 MB deduplicated archive preserves 5.05 GB of logical evidence, including
the original seven failures. Restoring 1,911 source/input files reproduces the
42-device pilot and all 84 faulty instances. These seven corrected defaults are
separate from the seven unavailable real-device bindings. This batch closes a
placement defect; it does not complete device envelopes, add 16 V physical
generation or promote any device/chunk status. Earlier hosted acceptance retains
its exact revision, and the new application needs its own hosted results.

Final follow-up: both hosts also pass 32 qualification/evidence checks, bringing
this batch to 99 distinct targeted tests per host; release-document checks pass.
The Windows-mounted Linux evidence attempt was interrupted while resolving PDK
paths. Unchanged tests from a verified Linux-local snapshot of `3c1b4b8` pass in
10.1 seconds (32.4 seconds including extraction and verification). This gives
future validation a faster execution path without changing qualification scope.
This follow-up note is retained locally to avoid restarting the active CI runs.

**Six gates are closed within their declared scope, one is active, and five
remain pending. This is not a 50% estimate of the remaining engineering work.**
The later gates include device qualification, complete chips and manufacturing
acceptance, which are substantially broader than the early reference gates.
No process is currently qualified for complete-chip tapeout.

The [qualification matrix](qualification/pdk-matrix.json) governs status. The
[twelve-chunk plan](PDK_QUALIFICATION_PLAN.md#sequence-and-gates) defines the
completion gates. Forecasts below are engineering judgment, not acceptance
evidence or promised dates.

## Current tracker

| Chunk | Work | Verified status | Work needed to close the gate / preserve the result | Expected progression |
| --- | --- | --- | --- | --- |
| 1 | Qualification matrix | **Defined; planning gate closed.** All bundled requirements have contracts and statuses. | Keep inventory, source identities and gaps current. Full upstream coverage and device limits remain visible in later work. | Maintenance as supported inputs change. High confidence in the existing planning status. |
| 2 | Toolchain | **Reference gate closed.** [Acceptance](validation/toolchain-2026-10-07.json). | Preserve the exact tested runtime scope; qualify changed distributed runtimes separately. | Mostly regression work unless engines or packaging change. |
| 3 | GF180 geometry | **Reference gate closed.** [Acceptance](validation/gf180-geometry-2026-10-07.json). | Maintain separate C/D geometry, timing and equivalence evidence for the declared production references. | Mostly regression work; new designs do not inherit qualification. |
| 4 | GF180 density | **Reference gate closed.** [Acceptance](validation/gf180-fill-closure-2026-10-09.json). | Preserve the six reference layouts' fill, exclusions and post-fill checks. | Mostly regression work; different floorplans need new evidence. |
| 5 | IHP geometry and fill | **Reference gate closed.** [Acceptance](validation/ihp-fill-closure-2026-10-11.json). | Preserve the declared counter/UART/APB geometry, connectivity and extracted-performance coverage. | Mostly regression work; device and full-chip coverage remain separate. |
| 6 | SKY130 public physical checks | **Approved public-baseline gate closed.** [Acceptance](validation/sky130-public-baseline-2026-10-16.json). | Maintain local DRC, antenna, LVS, density/fill and generic export for the versioned baseline and its exclusions. Full foundry signoff remains excluded. | Stable baseline with regression work. The user-approved narrower boundary applies only to this chunk. |
| 7 | Device families | **In progress.** 286 catalog entries remain partial; seven real device bindings remain unavailable, alongside nine utility entries. | Resolve required model bindings; finish source-backed operating ranges, physical/extracted geometry classes and upstream process-option coverage; verify the applicable installed workflows. | **Current critical path; high uncertainty.** Expect individual families to advance unevenly. More passing samples alone do not close the full gate. |
| 8 | Extraction and corners | **Pending formal qualification.** Coupon, extraction and corner tooling already exists. | Cover required routing layers/vias/device parasitics, coupling/fill and independent RC corners against source-backed references; execute the complete required condition pairs. | More structured once device and corner inputs are settled. **Medium-to-high uncertainty:** GF180/IHP additional independent RC data is an explicit gap. |
| 9 | Analog blocks | **Pending formal qualification.** Amplifier, reference and other example workflows provide a starting point. | Freeze per-process numerical specifications, then qualify mirror, differential pair, amplifier, reference, oscillator, noise/statistics and relevant IHP bipolar/RF cases before and after extraction. | Substantial design-and-verification iteration. **Medium-to-high uncertainty** from corner failures, startup, stability and parasitics. |
| 10 | Larger digital and mixed-signal designs | **Pending formal qualification.** Counter/UART/APB and teaching mixed-signal flows provide groundwork. | Lock a larger controller and per-target mixed-signal demonstrator; cover functionality, clock/reset crossings, actual interfaces, all-mode timing and final physical checks. | Existing flows should help. Planning can overlap chunk 9 once device/RC inputs are usable. **Medium-to-high uncertainty** at scale and at analog/digital boundaries. |
| 11 | Complete test chips | **Pending.** Macro and block results do not establish complete-chip acceptance. | Assemble the actual chip/pad/package configurations; pass final physical, electrical, ESD/latch-up, current-density/voltage-drop and I/O/package checks. | **Likely the next major bottleneck after device qualification. Very high uncertainty** until chip, pad, package and reliability inputs are defined. |
| 12 | Delivery and tapeout | **Pending.** Desktop packaging and export verification exist, with incomplete full-scope acceptance. | Qualify exact Windows/Ubuntu deliverables and reproduce complete handoffs; satisfy the existing gate's written manufacturing acceptance for the exact design and revisions. | Software packaging is relatively predictable after inputs freeze. **Manufacturing acceptance has no defensible date** before a target and its requirements are resolved. |

“Closed” refers to the recorded gate and its exact reference scope. A changed
PDK, tool, design or required condition needs its own evidence. Pending chunks
can have useful code and successful samples without having a completed gate.

## Evidence behind the current forecast

The acceptance records dated October 7 cover toolchain and GF180 geometry;
October 9 covers GF180 fill; October 11 covers IHP fill; October 16 closes the
explicit SKY130 public baseline. These are record dates, not measurements of
uninterrupted engineering time. Chunk 7 is still open in the October 22 matrix.
This history does not support extrapolating one fixed duration per chunk.

Recent chunk-7 work has produced concrete fixes and reusable verification:

- The [SKY130 MOS default correction](validation/sky130-mos-defaults-2026-10-22.json)
  replaces seven invalid starting dimensions with source-checked values. Each
  host passes 14 independent cases, 67 distinct tests, seven editor workflows,
  and all 756 faulty device instances. Saved/custom dimensions survive exchange.
  The original failures, raw audits and successful restored-source replay are
  retained; complete operating ranges and missing bindings remain open.

- The [SKY130 voltage layouts](validation/sky130-voltage-layouts-2026-10-22.json)
  add eight views covering four models. **128 layouts and 257 fault controls
  pass**, including all 20 native nominal model-bin centers and the corrected
  25 µm body-tap geometry. Both independent audits, eight editor workflows per
  host, 66 tests per host and four Windows/native handoffs plus four faults pass.
  An 81.9 MB archive preserves 3.06 GB of logical evidence; restored-source
  execution reproduces four positives and 31 faults. No device status is promoted.

- The [SKY130 threshold layouts](validation/sky130-threshold-layouts-2026-10-21.json)
  add six ordinary/per-finger views covering three models. **60 rotated layouts
  and 120 deliberate fault controls pass**, including both geometry checkers,
  exact native model/terminal/dimension readback and GDS/OASIS exchange. Both
  source desktops pass all six views; Windows/native handoff passes three valid
  layouts and three implant-fault controls. Each host passes 30 affected tests
  and 32 additional catalog/layout tests. Independent audits and restored-source
  replay pass. This removes a concrete generator/recognition gap, without closing
  the complete physical or operating envelope.

- The [SKY130 MOS voltage-boundary batch](validation/sky130-mos-bias-2026-10-21.json)
  passes all **60 local Linux cases for 33 symbol views / 11 models**, with
  6,300 valid device comparisons and 12,600 detected faulty instances. Final
  Windows/Linux pilots and 15 affected tests on each host pass. Independent
  audits verify the public voltage limits and actual terminal data; restored
  archive replay passes. This closes the declared finite boundary batch, while
  complete operating-envelope and physical qualification remain open.

- IHP isolation keeps its three physical terminals and internal tap/body
  connections. Two repeated cells retain distinct internal bodies.
- The latest isolation work passes **32 layout cases and 86 deliberate fault
  controls**, plus separate legacy tap and contact-boundary regressions.
- Affected source tests, Windows staging/local native execution, independent
  native-output audits and restored-archive replays pass. See the
  [physical record](validation/ihp-isolation-physical-2026-10-21.json) and
  [hierarchy record](validation/ihp-isolation-hierarchy-2026-10-21.json).
- Those results leave all 286 available catalog entries at `partial`; they do
  not resolve the seven unavailable real-device bindings or prove complete
  operating envelopes. See the [device guide](DEVICE_ADAPTER_QUALIFICATION.md).

The wider requirement matrix also shows why later chunks cannot yet be called
nearly finished: chunk 8 has 11 `not_run` and one `partial` target/test rows;
chunk 9 has 30 `not_run`; chunk 10 has 12 `not_run`; chunk 11 has 20 `not_run`;
chunk 12 has eight `partial` and four `needs_definition`. These are **formal
coverage rows, not estimates of code written or equal units of effort**.

The [October 22 hosted acceptance record](validation/chunk7-hosted-acceptance-2026-10-22.json)
verifies **all 17 workflows passing at `e29cfd6`**, including desktop verification
and protected release preparation. Push and pull-request runs are counted
separately. Draft release `420396486` contains 24 assets; downloaded validation
and checksum records match their GitHub digests, and all remote asset digests
match the checksum inventory. Large payload binaries were not independently
downloaded or executed during this review.

The retained frozen tests cover hosted Windows Server 2022 installed scales
1/1.5/2 and portable mode, and Ubuntu 24.04 with an offscreen display. Clean
consumer Windows/Ubuntu manual checks, upgrades, multiple monitors and
accessibility remain separate. The statistical coordinator passes its sampling
and recovery gate with 99/128 numerical design trials passing their specifications;
29 failed design trials remain visible. This is not 128/128 design yield.

The older [release run](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/39640899481)
at `ae5a7a1` failed to create its draft with HTTP 403. The new successful draft
supersedes that open publication blockage. Earlier investigation suggested a
workflow-token/default-branch restriction; current success does not establish
the cause of the historical error. No permissions or credentials were changed.
The voltage-device and starting-dimension application changes still need their
own exact-revision hosted and final installed acceptance. The intermediate
`e8ac8bc` hosted snapshot had six successful, five running and six queued
workflows. The new `3c1b4b8` snapshot has six successful, six running, three
pending and two queued workflows. These unfinished snapshots are not final
hosted or installed acceptance results.

## How progress is likely to unfold

At the user's request, the **rough engineering estimate for chunk 7 is about
60% complete**, with a broad planning range of **50–70% and low confidence**
(October 22, 2026; application revision `b4e00d9`). This is a judgment about the
implemented integration and accumulated verification work relative to the
remaining gate, not a measured coverage score or a fraction of time remaining.
Working device interfaces, selected electrical/physical batches and reusable
verification infrastructure are well advanced. Missing required model bindings,
complete source-backed operating ranges, broader physical/process-option
coverage and final installed acceptance still represent substantial work.
The estimate is not derived from test counts or the six earlier closed chunks;
it does not promote any device or change the chunk-7 gate. Revise it as those
remaining requirements become better defined. No overall project percentage or
completion date is implied.

1. **Device completion comes first.** Separate missing model/source information
   from implementation defects and finite test batches. Track each family by
   its remaining gate conditions; repeated sample additions can improve the
   product without moving overall completion proportionally.
2. **Extraction should become more systematic.** Reuse the native execution,
   fault controls, exact-source records and archive replay infrastructure from
   earlier chunks. Missing independent corner data can still hold a target open.
3. **Analog and larger digital work can share infrastructure.** Plan their
   specifications and fixtures together; qualify results only against the
   settled device, RC and process inputs. Mixed-signal and clock/reset coverage
   will require additional work beyond the current small references.
4. **Expect another slowdown at complete chips.** Pads, protection, power,
   package and reliability introduce requirements that block-level DRC/LVS
   cannot establish. This is a major remaining workload, even after chunks
   7–10 pass.
5. **Freeze inputs before final delivery acceptance.** Package and handoff
   reproduction should become more predictable at that point. All technical
   checks remain local. The existing chunk-12 gate separately requires written
   manufacturer/shuttle acceptance of the exact design; no submission is
   authorized by this tracker, and that dependency currently has no date.

I do not assign an overall percentage or calendar finish date while the device
and complete-chip inputs remain unresolved. The useful forecast is that **7 and
11 carry the largest discovery risk; 8–10 should benefit from existing tooling;
12 has a separate manufacturing dependency**. This is a conditional assessment,
not a guarantee that those middle chunks will be quick.

A credible time estimate requires finite remaining device/condition lists,
source-backed limits and RC corners, frozen block specifications, actual
chip/pad/package choices and measured durations for representative batches.
Once those exist, estimate each batch's implementation time, native run time and
likely repair cycles, then revise the forecast after execution. Until then,
an hours-to-finish claim would hide the largest uncertainties.

## Update history

| Date | Change | Effect on forecast |
| --- | --- | --- |
| 2026-10-23 | Repaired stale RF corner guards; both hosts pass 360 branch cases, 360 bias/noise cases, 90 transient conditions, application checks and 21 focused tests. Corrected IHP total-job and dependency-download limits. | Removes confirmed qualification regressions. Fresh hosted acceptance is pending; no device promotion or increase to the low-confidence 60% estimate. |
| 2026-10-22 | Pushed `b4e00d9`: source-locked MiM multiplicity correction and saved-revision preservation; 54 native runs per host, both 3,301-test source suites, independent audits and archive replay pass. Recovered the isolated test-harness Git mistake without losing source changes. | One concrete integration defect is closed. All device statuses remain unchanged; exact-revision hosted acceptance is still running. This final sync note is local until the next code push. |
| 2026-10-22 | Verified all 17 workflows and exact-release validation at `e29cfd6`; application commit `1647800` adds four voltage/native MOS generators passing 128 layouts and 257 faults after fixing the 25 µm substrate-tap violation; both-host regressions, source desktops and archived-source replay pass. | The older release-publication blockage is superseded by an observed successful draft. Device envelopes, seven missing bindings and new-source acceptance remain open. |
| 2026-10-21 | Initial tracker created from the matrix and acceptance records at `5095283`; isolated-body fixes and repeated-cell regression recorded. | Six scoped gates closed; chunk 7 remains the active critical path. No later gate promoted. |
| 2026-10-21 | Completed the 60-case SKY130 public MOS bias-boundary batch, both final host pilots, independent raw audits and restored-source replay; added ongoing pilot checks. | The finite boundary coverage for 33 views is now verified. Missing bindings, full envelopes and physical coverage still prevent chunk-7 closure; no overall finish date follows from this batch. |
| 2026-10-21 | Preserved qualification commit `e7c3aa9` locally; 13 existing remote workflows pass and three remain active. Verified archives and replay allow redundant generated runs to be removed. | Push is deferred to preserve ongoing acceptance. No hosted result is claimed for the new pilot configuration. |
| 2026-10-21 | Completed three SKY130 threshold-model generators: 60 layouts, 120 faults, both desktop paths, Windows/native handoff and independent archive replay. Retained 62 distinct affected/catalog tests per host. Changed desktop CI to preserve active acceptance while queuing updates. | Six symbol views gain verified sampled physical support. Seven missing bindings and complete envelopes still block chunk 7; the older draft release also exposed a GitHub 403. |
| 2026-10-21 | Pushed through `e29cfd6`; verified evidence restore before removing this batch's redundant runs. Reviewed the new workflow snapshot and documented the default-branch/workflow-token restriction matching the older release failure. | Local qualification is retained and current hosted checks are progressing. Device blockers and publication authorization remain open; the later documentation note is local pending the next appropriate push. |

During subsequent project work, update the snapshot and affected rows, append a
brief history entry for meaningful changes, and explain whether the remaining
work became smaller, larger or better defined. Keep verified status separate
from confidence and estimates. Preserve prior failures and acceptance scopes.

Cleanup for this batch removed 1,764,806,858 bytes of verified Windows test
copies and 3,788,445,812 bytes inside Linux. The 28.3 MB primary archive and
87.9 MB checkpoint retain the evidence and exact committed source snapshot.
No Windows administrator action or disk compaction was used.
