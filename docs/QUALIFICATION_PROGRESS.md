# Chunks 1–12: progress and forecast

**Snapshot: October 23, 2026; integration work on `b6c623b`.**
The [IHP standard 3.3 V MOS addition](IHP_HV_MOS_LAYOUTS.md) passes 168 sampled
layout checks and 158 deliberate fault controls using full Magic and public
KLayout checks. Independent readback verifies 5,414 native channels and exported
mask channels. Both hosts pass 56 affected tests and two source editor cases;
378 sampled LV geometries match the parent exactly. The original broad run
retains one faulty PMOS negative-test expectation, corrected with a fresh full
case and a combined audit. The audit binds both exact runners and unchanged
production sources; it does not claim a complete rerun with the new classifier.
Earlier failed pilots and interrupted full suites remain evidence, not passes.
Review fixes strengthen failed-integrity and malformed-parameter detection;
the final checker revalidates all 158 retained fault controls. The verified
archive preserves 68,096 file bindings in 143.1 MB. Restoring it reproduces
the affected PMOS case (16 valid checks and 16 faults) and its nine then-current
tests; the final stricter checker separately passes 13 focused tests per host.

[Fast feedback](CI_FEEDBACK.md) now separates Windows/Linux PR and merge-queue
checks from selected immutable acceptance candidates. Existing release gates
remain. All 11 workflow definitions pass schema/expression validation. The
[final local feedback lane](validation/ci-feedback-integration-2026-10-23.json)
passes 211 tests, release-document checks and both GUI probes per host in
67.3 seconds on Windows and 33.9 seconds on Linux. Linux uses a verified native
filesystem copy: its test stage takes 6.2 seconds versus 262 seconds through
the Windows mount. The earlier mounted run remains invalid because an auditor
changed during execution; that failure and all passing stage logs are retained.
The [shared reference toolchain](REFERENCE_TOOLCHAIN_REUSE.md) reduces ten
per-corner engine builds to two per acceptance run and verifies their artifact
before each fresh corner suite. Transfer/failure-control tests pass locally;
hosted setup and latency are still unverified. The repository currently has no
branch protection or rulesets: **PR feedback is not yet an enforced required
check**. No protection policy was changed.

The [family closure plan](CHUNK7_DEVICE_FAMILY_CLOSURE.md) now has a completed
selected SKY130 LI milestone. Its [source contract](SKY130_LI_REQUIREMENTS.md)
binds 24 source hashes and 12 requirements, and identifies that prior nominal,
ss and ff selections all used typical LI resistor parameters. The selectable
[linked runner](validation/sky130-li-linked-2026-10-23.json) passes ten fresh
cases across five distinct passive sections and two orientations at 2x5 um,
27 C and multiplicity one. Actual native extraction, application export and a
literal reference pass 80 DC/AC/transient/noise comparisons; 60 electrical and
five physical faults are detected. The independent audit rereads 180 raw files
and rejects all five deliberately altered evidence sets. Both hosts pass 17
focused tests, and a fresh archive replay reproduces one selected case.
The immutable source contract keeps its historical pre-execution status; the
new record closes only the selected examples. Full operating definitions,
physical classes and installed acceptance remain open. General result reuse
remains deferred until complete loaded-dependency identity and an explicit
semantic reuse audit are implemented. The current audit verifies fresh results;
more samples or cached success cannot close missing source requirements.

**Chunk 7 remains about 60% complete, low confidence (50–70%).** This is an
engineering estimate, not a percentage of devices qualified. The matrix still
has 287 partial entries, six unavailable real bindings and nine utilities.
The official bond-pad file remains an empty electrical placeholder. Full
operating envelopes, remaining physical classes, extracted behavior and exact
installed acceptance keep the chunk open. No device status or completion gate
was promoted. Chunk 8–12 forecasts remain conditional on these dependencies;
hosted speedups and family closure rates need actual measurements before a
completion-date forecast is credible.

**Snapshot: October 23, 2026; GF180 public current specifications on `da9759c`.**
Final sync: the batch and tracker are pushed as
[`b6c623b`](https://github.com/jonahsaunders/IC-Design-Studio/commit/b6c623b44ba7ad2e30adb5a8c00a1e13807d8db5),
and remote `experimental` matches. Its initial exact-revision snapshot has
seven queued and eight pending workflows; none has completed. The estimate
remains 60%, low confidence. This sync-only note stays local for the next
appropriate project push so it does not restart the active checks. Pending
hosted work is not acceptance.

The [new numerical specification checks](GF180_MOS_SPECIFICATIONS.md) compare
standard 3.3 V devices against pinned public GF180 values at W/L = 10/0.28 um
and 25 C. Both hosts complete ten corner/variant cases and detect all 240
faulty instances each. Independent audits reread 80 native files, 1,585,920
terminal-current samples and 400 model-file bindings per host. Reported currents
match exactly across Windows and Linux; all 47 affected tests pass on each.

Eight cases meet the printed current bounds. The two ff cases retain NMOS
590.277446 versus maximum 590 uA/um and PMOS -290.390199 versus minimum -290
uA/um. Direct public-model defaults reproduce the discrepancy. The work isolates
it from application export; it does not resolve its upstream cause. Limits are
unchanged, and the maximum-gm threshold estimate remains diagnostic because
the retained public source does not supply the complete extraction equation.

Both final native batches and audits were repeated after correcting the recorded
corner on deliberate wrong-corner tests. Initial numerical-pilot failures,
Windows sandbox test errors, exact sources and native evidence are retained.
The source bundle keeps its upstream Apache-2.0 license. This adds independent
acceptance evidence but does not promote any device or change a completion gate.

The verified archives preserve exact sources, public licenses, both complete
native batches and failed attempts. Restoring the archived sources reproduces
both nominal cases, 48 faulty instances and all seven new tests. After verifying
23,337 recoverable files, cleanup removed 1.04 GB from Windows and 1.43 GB inside
Linux. Archives and working sources remain; no administrator access or virtual
disk compaction was used. Final source tests and release-document checks pass.

**Chunk 7 remains about 60% complete, low confidence (50–70%).** The matrix still
has 287 partial entries, six unavailable real bindings and nine utilities.
Complete device envelopes, broader physical/process coverage, unresolved
specification differences and final installed acceptance remain open. The
next useful work is source-defined numerical/operating coverage for the remaining
families and resolution of required bindings; a completion date is not yet reliable.

**Snapshot: October 23, 2026; GF180/IHP shared fingers on `e44f7f3`.**
Final sync: this batch and its tracker are pushed as
[`da9759c`](https://github.com/jonahsaunders/IC-Design-Studio/commit/da9759cd46592ac43b7e8562559f2bc572628e17),
and remote `experimental` matches. Its first exact-revision hosted snapshot has
six running, eight pending and three queued workflows; none has completed.
The estimate remains 60%, low confidence. This sync-only note stays local for
the next appropriate project push so it does not restart the active checks.
Pending CI is not acceptance.

The [shared-finger layouts](MOS_FINGER_LAYOUTS.md) add 1–8 gate fingers per
device and retain separate 1–16-copy multiplicity. All 156 native layout
contexts pass; the qualification runner detects all 222 faults. Independent
readback checks 7,182 channels in both extracted netlists and exported masks,
plus 10,098 evidence bindings. Diffusion-group checks catch wrong physical
grouping that electrical comparisons cannot distinguish. All 216 prior
single-finger configurations remain identical, and six source editor cases
pass on each host.

The final isolated Linux suite passes **3,341 tests** (43 skips). Both hosts
pass all **58 affected tests** (two skips each). The earlier Windows full run
retains one obsolete single-finger expectation among 3,340 tests, with 67
skips; corrected coverage now passes in the affected suite. No final complete
Windows or installed-release pass is claimed. Initial failures remain retained.

The verified 183.9 MB archive and 3.0 MB checkpoint retain exact sources,
native results, initial failures and regressions. Archive restoration reproduces
nine native contexts, 72 faults and all 58 affected tests. Model and PDK assets
are unchanged; no new third-party asset was imported.

The parent hosted snapshot has six successful workflows, nine running, one
pending and one failure during OS dependency setup. The coil workflow now
avoids downloading an older KLayout immediately before the checksum-locked
version. Edited shell steps pass syntax checks; fresh hosted setup and final
installed acceptance remain outstanding.

All 35 evidence/matrix/release tests and release-document checks pass.
Before cleanup, every one of 74,227 non-bytecode files in this batch's temporary
trees was verified recoverable. Removing those copies freed 378.5 MB on Windows
and 4.51 GB inside Linux. Archives, repository, PDKs and engines are retained;
no administrator access or virtual-disk compaction was used.

**Chunk 7 remains about 60% complete, low confidence (50–70%).** There are
still 287 partial entries, six unavailable required bindings and nine utilities.
This closes the bounded GF180/IHP shared-finger implementation gap. Full device
envelopes, unsampled geometry, broader physical/tool-view coverage and final
acceptance keep chunk 7 open. No device status or completion gate was promoted.

**Snapshot: October 23, 2026; GF180/IHP parallel MOS on `16761b2`.**
Final sync: the batch and tracker are pushed as
[`e44f7f3`](https://github.com/jonahsaunders/IC-Design-Studio/commit/e44f7f318e428c764d9faae9ae5a879da483522a),
and remote `experimental` matches. Its first exact-revision hosted snapshot has
six pending and eleven queued workflows; none has completed. The estimate stays
60%, low confidence. This sync-only note remains local for the next appropriate
push so it does not restart the active checks. Pending CI is not acceptance.

The [parallel MOS layouts](MOS_PARALLEL_LAYOUTS.md) add 1–16 separately contacted
units to the standard GF180 C/D 3.3 V and IHP 1.2 V generators. Inverter placement
uses the full array height. All 144 rotated/mirrored device layouts and twelve
inverter contexts pass full native DRC and strict LVS; all 156 faults are detected.
Independent readback verifies 1,134 native transistors and 8,008 evidence bindings.
All 72 prior single-unit characterization sizes retain identical geometry,
terminals, roles and specifications. The legacy GF180 binding regression found
by the full suites is fixed; the original failing test remains unchanged.

The isolated Linux suite passes **3,328 tests** (42 skips). The Windows run of
3,328 tests retains one campaign-directory rename error and 67 skips. A bounded
publication retry now passes an actual Windows reader-lock test, permanent-error
and competing-destination controls. Final affected suites pass **64 tests** on
each host; the complete suites retain their earlier source snapshots and outcomes.
The final custom-emission guard rejects mismatched physical/model multiplicity;
272 positive GF180 cases retain identical geometry on each host. No fresh full
suite or installed-release pass is claimed for the final guards.

All six source editor workflows pass on each host. Restoring the verified source
archive and compatibility delta reproduces nine native contexts, 51 faults and
46 affected tests. Applying the final exact source delta passes the 64 affected
tests again on the reconstructed Linux source. Failed runs retain their own
records. A verified 107.1 MB main archive and final checkpoint retain the exact
sources, native results, editor evidence and replays. The parent `16761b2`
public-layout regression passed its pull-request and release-preparation jobs;
fresh hosted and installed acceptance remains separate.

The final evidence/matrix/release tests and historical GF180 source checks pass.
The earlier GF180 acceptance retains its exact tested campaign source; it does
not certify the newly changed application. The verified 48.8 MB checkpoint
retains final source deltas, regressions and replay. Verified temporary copies
were removed: 458.9 MB from Windows and 2.38 GB inside Linux, without administrator
access or virtual-disk compaction. Repository, tools, PDKs and archives remain.

The latest parent hosted snapshot has ten successful workflows, two running,
two pending and three queued. One job within a pending workflow timed out while
installing Ubuntu dependencies: downloading 46.9 MB took 20 minutes. It did not
reach qualification. Fresh hosted and installed acceptance remains outstanding.

**Chunk 7 remains about 60% complete, low confidence (50–70%).** The matrix still
has 287 partial entries, six unavailable required bindings and nine utilities.
Shared fingers, full operating envelopes, wider physical/process coverage and
final acceptance remain open. No device status or completion gate was promoted.

**Snapshot: October 23, 2026; RF default/public-layout follow-up on `2173746`.**
Final sync: this batch is pushed as
[`16761b2`](https://github.com/jonahsaunders/IC-Design-Studio/commit/16761b2ae4cdabbed9f3ebdeb18a2758dad3860d),
and remote `experimental` matches the local commit. Its first exact-revision
hosted snapshot has ten running, three pending and four queued workflows;
none has completed yet. This sync-only note remains local for the next appropriate
push so it does not restart the active checks. The estimate remains 60% with low
confidence; pending hosted work is not acceptance.

The [new default RF n-well binding](SKY130_RF_DEFAULT.md) resolves one previously
unavailable simulation choice. New SKY130 projects use `b26f7f28e659ddc1`; older
assets, candidates and saved project identities remain recoverable. Public model
originals and their Apache-2.0 license are retained with an explicit derivative
notice. The p-well RF candidate remains separate.

Both hosts pass nine corner/temperature conditions, 54 detected faulty instances,
54 runtime proofs and three incompatible-engine routes. Independent readback
checks 1,512 current samples per host; cross-host values match exactly. All 302
catalog interfaces pass or produce their expected rejection. Both complete
source suites pass **3,322 tests** (Windows 65 skips; Linux 42), with the final
isolated fixture correction separately checked on both hosts. Original failures
and source-change flags are retained and reconciled explicitly in the
[execution record](validation/sky130-rf-default-2026-10-23.json).

The hosted MiM contact-topology regression is repaired locally. All thirteen
public physical routes and both deliberate faults produce expected results;
the original amplifier polarity error remains a required mismatch. Independent
audit checks 854 file/rule bindings and 42 native capacitors without changing
their native extraction bytes. Both complete orientation batches also pass:
128 layouts, 94 physical/reference faults and 48 electrical conditions, with
400 capacitors and 2,400 integrity bindings independently re-read.

A verified archive retains the exact source, native results and initial failures;
restoring it reproduces the RF pilot, public comparator, both fault controls and
eighteen regression tests. Fresh hosted and final installed acceptance are still
required. The latest parent snapshot has nine successful workflows and two
public-layout job failures corresponding to the locally repaired regression;
other workflows remain running/pending. This batch has not claimed a hosted pass.

A verified 38.7 MB checkpoint retains the restored replay and final checks.
All 35 evidence/matrix/release tests, release-document checks and both workflow
checks pass. Verified temporary copies were removed: 3.37 GB from Windows and
8.32 GB inside Linux. Permanent evidence, the working repository, PDKs and engines
remain; no administrator access or virtual-disk compaction was used.

**Chunk 7 remains approximately 60% complete, low confidence (50–70%).** The
matrix now has **287 partial entries, six unavailable real bindings and nine
utilities**. Full operating envelopes, remaining models, wider physical/process
coverage and final acceptance remain open. No completion gate was reduced.

**Snapshot: October 23, 2026; first-MiM follow-up on `1461c4a`.**
The [first-MiM correction](SKY130_FIRST_MIM_LAYOUT.md) fixes two reproduced defects:
rotations exchanged model W/L, and some fractional dimensions placed contact cuts
too near an electrode edge. Both corrections retain original model/package bytes
and the existing geometry bounds.

**Final local results pass:** 64 first-MiM and 64 second-MiM layouts, 47 fault
controls for each family, plus eight mixed-family layouts and four mixed faults.
Independent audits check 416 native capacitors and 2,556 integrity bindings.
Both hosts pass all 24 first-MiM electrical conditions; the second-MiM Linux
regression passes its 24 conditions. Four corrupted-output controls are rejected.
Both source desktops, Windows/native staging and checked receipt, and 40 affected
tests on each host pass. The earlier complete suites retain their own revision;
this batch does not claim a new full-suite or installed-release acceptance.

A verified 146.1 MB archive retains 6.81 GB of logical source/evidence, including
the original failures. Restoring its exact sources and adapter reproduces two
native orientations, all six fault controls and one electrical condition.
The new full first-family and mixed-family checks are required in CI.
All 47 evidence/matrix/release tests and release-document checks pass. A verified
6.1 MB checkpoint retains the restored pilot and final checks. Verified redundant
copies were removed: 925.6 MB from Windows and 6.31 GB inside Linux. The permanent
archives, working repository, PDKs and engines remain; no administrator access or
virtual-disk compaction was used.

**Chunk 7 remains incomplete, approximately 60% by low-confidence engineering
estimate.** The matrix still has 286 partial entries, seven unavailable real
bindings and nine utilities. Complete device envelopes, broader physical/process
coverage and exact final hosted/installed acceptance remain required. No gate or
device status changed. The latest read-only hosted snapshot at `1461c4a` has six
successful, five running, two pending and three queued workflows; it is not final
acceptance. This batch will receive its own revision and hosted checks.

Final sync follow-up: the fixes, retained regression fixtures, main tracker and
public-source review are pushed as
[`2173746`](https://github.com/jonahsaunders/IC-Design-Studio/commit/21737469388cf68e4985ebb653e29b5390fd7375).
Remote `experimental` matches. Its first exact-revision hosted snapshot has seven
running, six pending and three queued workflows; none has reported failure.
Pending work is not acceptance. This sync/CI note remains local until the next
appropriate push so it does not restart the active checks.

**Previous completed batch, October 23, 2026.** Local evidence:
[rectangular SKY130 second-MiM extraction](validation/sky130-mim-orientation-2026-10-23.json),
with exact source hashes and baseline `096c275` on `experimental`. The tracker is
updated during project work, without a scheduled monitor.

The [rectangular-capacitor blocker](SKY130_MIM_ORIENTATION.md) is resolved for the
declared flat-layout adapter: **64 translated rotations/mirrors, 47 detected
physical/reference faults and 24 electrical conditions on each host pass**.
The independent audit verifies 200 extracted capacitors, 128 stream comparisons,
1,200 integrity bindings and raw complex responses. All 21 asymmetric electrical
controls per host detect swapped width/length through series resistance. Four
corruptions are rejected even when changed extraction checksums are rebound.

Both source desktops, Windows staging/receipt and 25 focused tests per host pass.
Both complete source suites pass **3,311 tests** (Windows 65 skips, Linux 58).
An 82.0 MB verified archive retains 3.63 GB of logical evidence. Restoring 6,755
source/input files reproduces two native orientations, all six faults and the
electrical pilot. The full batch and independent audit are now required by CI.

The verified 6.1 MB checkpoint retains final suite logs and replay outputs; a
53.2 MB supplement preserves original nested ZIP fixtures found by the cleanup
precheck. After checking every retained input, temporary copies were removed:
918.4 MB from Windows and 3.15 GB inside Linux. No administrator access or virtual
disk compaction was used. All 35 evidence/matrix checks and release-document
checks pass. The working repository, persistent PDKs and engine runtimes remain
in place.

The last hosted snapshot for the preceding `096c275` repair commit has eight
successful and eight running workflows, with no reported failure; pending work is
not acceptance. Exact new-revision hosted/installed acceptance is still required.
**Chunk 7 remains in progress:** 286 partial catalog entries, seven unavailable
real-device bindings and nine utility entries. The rough 60% estimate remains
low confidence. This batch resolves a concrete rotation defect without changing
the completion gate, promoting a device or proving measured RF accuracy.

Final follow-up: the RF/CI repairs and rectangular-MiM fix are pushed through
[`1461c4a`](https://github.com/jonahsaunders/IC-Design-Studio/commit/1461c4a8ec66a8a133096300d0ba39d7e6d2e11f),
and remote `experimental` matches. Its hosted snapshot has four successful,
eight running and four pending workflows; none has reported failure. This is
not final hosted acceptance.

A [fresh public-source review](validation/chunk7-public-source-review-2026-10-23.json)
confirms the upstream IHP bondpad is still a placeholder and does not establish
replacement bindings for the missing SKY130 ESD/VPP or IHP coil models. Existing
RF candidates retain their separate electrical/isolation limitations. Both
upstream trees and four source files are retained with verified identities.
No alias, device promotion or completion-gate change was made. This final source
review and sync note were held locally and are included with the first-MiM
follow-up. Their original source identities and limited scope are unchanged.

The [preceding CI review](CHUNK7_CI_RECOVERY.md) found **nine successful, four failed
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

Historical follow-up for the preceding MiM-parameter batch: those application fixes and the tracker were pushed as
[`b4e00d9`](https://github.com/jonahsaunders/IC-Design-Studio/commit/b4e00d9bb89546feb3d9dfc728d57c2558bcdc18),
and the remote `experimental` branch matches. The exact-revision hosted snapshot
has four successful, three running, four pending and five queued workflows;
none has reported failure. Pending and queued runs are not acceptance results.
This follow-up note is local until the next code push, preserving the active
acceptance runs. The completed batch removes the reviewed MiM parameter defect;
seven unavailable required bindings, complete operating ranges, wider physical
and process-option coverage, and exact final installed acceptance still prevent
chunk-7 closure. At that checkpoint the rectangular MiM rotation issue remained open. The separate
October 23 adapter and its bounded acceptance above now address that defect.

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
| 7 | Device families | **In progress.** 287 catalog entries remain partial; six real device bindings remain unavailable, alongside nine utility entries. | Resolve required model bindings; finish source-backed operating ranges, physical/extracted geometry classes and upstream process-option coverage; verify the applicable installed workflows. | **Current critical path; high uncertainty.** Expect individual families to advance unevenly. More passing samples alone do not close the full gate. |
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
uninterrupted engineering time. Chunk 7 is still open in the October 23 matrix.
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
- The current default has 287 available catalog entries at `partial`; six real
  bindings remain unavailable. The RF default integration resolves one binding
  without proving complete operating envelopes. See the [device guide](DEVICE_ADAPTER_QUALIFICATION.md).

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
(October 23, 2026; baseline `e44f7f3` plus the recorded shared-finger correction). This is a judgment about the
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
| 2026-10-23 | Added source-locked GF180 current specifications: ten completed cases and 240 detected faults per host, identical current measurements, independent raw audits and both 47-test passes. Two fast-corner cases retain literal published-bound mismatches, also present with direct public-model defaults. | Stronger independent numerical evidence; full device qualification is still open. Estimate remains 60%, low confidence. |
| 2026-10-23 | Added bounded GF180/IHP shared MOS fingers: 156 valid layouts, 222 detected faults, 7,182 independently read channels, preserved single-finger behavior, final Linux 3,341-test pass and both 58-test affected passes. Verified archive restore and reduced redundant hosted setup downloads. | Closes sampled shared-finger support; full device envelopes, missing bindings and final acceptance remain. Estimate stays 60%, low confidence. |
| 2026-10-23 | Added GF180 C/D and IHP standard MOS parallel layouts: 156 valid native contexts, 156 detected faults, 1,134 independently checked transistors, preserved single-unit behavior, the 3,328-test Linux suite and both final 64-test affected suites. The Windows full-suite campaign lock failure is retained and addressed by a tested retry. | Closes a concrete physical multiplicity gap. Shared fingers, full device envelopes, six unavailable bindings and final acceptance keep chunk 7 open; estimate remains 60%, low confidence. |
| 2026-10-23 | Added the sampled RF n-well default binding; unavailable real models fall from seven to six. Repaired the public MiM contact-topology regression with original fault controls. Both 3,322-test suites, independent audits and archive replay pass. | A concrete model-availability blocker is closed; all 287 available entries remain partial. Broader envelopes and final hosted/installed acceptance remain open. Estimate stays about 60%, low confidence. |
| 2026-10-23 | Closed bounded rectangular second-MiM orientation: 64 layouts, 47 faults, both 24-condition electrical batches, independent audits, both 3,311-test suites and archive replay pass. | Removes the identified rotation defect. Full device, remaining-model and installed-release gates remain open; no increase to the low-confidence 60% estimate. |
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
