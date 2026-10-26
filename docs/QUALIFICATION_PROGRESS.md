# Chunks 1–12: progress and forecast

Updated October 26, 2026. Chunk 7 is approximately **67% complete**, with low
confidence (55–75%); this is an engineering estimate, not verified acceptance.
The small increase reflects completed imported-hierarchy and editable physical
parallel-array milestones. Full family statuses and completion gates remain
unchanged; the estimate is not calculated from passing test counts.

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

## Latest work and retained checkpoints

**Completed local MiM hierarchy source milestone, based on `f081d172`.**
The [new imported repeated-cell example](SKY130_MIM_HIERARCHY.md) passes both
capacitor constructions: four native clean layouts, eight native fault jobs,
ten stream controls and fourteen distinct rehashed evidence controls. Both
601-test source lanes and all six stages pass; all 1,402 feedback source hashes
match, and all 837 captured native source bindings are independently verified.
The 19.92 MB archive restores all 1,264 full-run files at their original paths
and reproduces the unchanged independent audit. The original pilot checker
failures and later corrections remain separately identified. Generic producer
geometry helpers are shared without changing their function syntax trees.
This closes one predefined imported class, not a complete capacitor family;
chunk 7 remains approximately 67% (55–75%, low confidence).

**Published repair baseline: `f081d172cb7132ca579c0bd3ff3e187ddbd1e35e`.**
The Windows temporary-path fixture repair is pushed to `experimental`.
[Fresh hosted feedback](validation/sky130-metal-parallel-repair-hosted-feedback-2026-10-26.json)
passes both 582-test, six-stage lanes and the required aggregate: Windows
204.5 seconds with fifteen skips, Linux 131.3 seconds with four skips, excluding
setup/queue time. Both downloaded archives pass complete readback; all 1,398
source hashes match the candidate and the accepted local repair lanes. Actual
synthetic-merge parents match the candidate and current `main`. The original
failed hosted run remains retained separately. The following source/acceptance
records keep their own immutable identities. This hosted-result record accompanies the next implementation batch above;
no status-only rerun is needed.

The [bounded public-source recheck](validation/chunk7-public-source-review-2026-10-26.json)
finds no new exact binding in the inspected maintained SKY130 source paths,
and no local unit/corner error resolving GF180's published fast-corner mismatch.
The exact missing generating fixture/threshold definition and model-versus-spec
reconciliation remain listed. Six real bindings and full device limits remain
open; no approximate model substitutions or relaxed limits are accepted.

**Installed-array source candidate: `7a44a9485f83acb7155393bf16b589cdf482b0b9`.**
The complete installed-array source rehearsal and required desktop hooks are
pushed to `experimental`; all 1,398 feedback and 861 electrical/checker source
bindings match its Git blobs. Its automatic Linux feedback passes all six
stages, but Windows stops on one new direct-helper test fixture. The
[retained failure and repair](validation/sky130-metal-parallel-temp-alias-fix-2026-10-26.json)
reproduces the same receipt mismatch under a real Windows abbreviated path.
The fixture now resolves a deliberate parent-directory alias before calling
helpers, matching the application's existing entry points. All three path
variants and four focused tests pass; production checking and native evidence
are unchanged. The exact original hosted TEMP spelling was not recorded.
The repaired fixture now passes both complete 582-test source lanes and all
six stages, with four Linux skips and sixteen Windows skips. All 1,398
source hashes agree; only the test fixture differs from the published
source candidate. The original hosted failure remains retained separately.
The subsequent `f081d172` candidate and hosted result above complete this source repair.

**Published hierarchy/array implementation: `79a3fd4803ed0652fc5f3db8b06999186f6fdbb2`.**
The imported-hierarchy and editable-array work, final source regression and
67% estimate are pushed to `experimental`. The [hosted merge feedback](validation/sky130-metal-parallel-hosted-feedback-2026-10-26.json)
passes both 550-test, six-stage lanes and the required aggregate. Linux has
four skips and Windows fifteen. Downloaded artifacts pass complete readback;
all 1,386 source hashes match the committed candidate and both accepted local
lanes. The actual synthetic merge parents are verified against the candidate
and `main`. The hosted-result record accompanies the subsequent installed-array
integration below. No installed-array or full-family acceptance is inferred.

After the hosted readback, three additional Windows test-output copies were
verified file-for-file against their retained archives and removed:
382,509,653 logical bytes. Their separate cleanup receipt is retained beside
the permanent source-feedback archive. Source, tools, PDKs and all verified
archives remain; no administrator operation was used.

**Selected desktop candidate: `e3fa0cc60da18cee8359817bb5321923587abc50`.**
The tested capability repair is pushed to `experimental`. All 1,377 source
identities match the committed Git blobs. One replacement
[full desktop run](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/40340500387)
has been dispatched; its result remains pending. The
[automatic merge feedback](validation/chunk7-desktop-repair-hosted-feedback-2026-10-26.json)
passes all five stages on both hosts: 506 tests per host, four Linux and fifteen
Windows skips. Both downloaded artifacts pass complete readback; all 1,377
source identities match the exact candidate Git blobs. The full desktop run
has passed its five prerequisite jobs and both runtime verifications; Windows
runtime verification took 67 minutes 31 seconds. Linux dependency installation
passed in 64 minutes 6 seconds, and its full core stage passed at 16:36:26 UTC
after 18 minutes 41 seconds. Windows core also passed at 17:09:01 UTC
after 42 minutes 37 seconds. Linux installed resistor GUI/native acceptance
passed in 6 minutes 26 seconds, and installed electrical acceptance with
independent readback passed in 7 minutes 20 seconds. The entire Linux desktop
job is successful. Its [retained Linux evidence](validation/sky130-metal-installed-linux-2026-10-26.json)
passes independent raw readback of all 42 native jobs, 90 electrical contexts,
7,829,496 samples and 4,680 controls, with all 851 captured sources authenticated
against `e3fa0cc`. The exact 147.38 MB diagnostic archive and 3.01 MB isolated
source archive are retained. Two earlier local readback setup failures remain
separately recorded; the accepted run used unchanged exact-candidate checkers.
Windows installer construction passed in 56 minutes 7 seconds, and its
packaged digital-engine verification was running at 18:29:11 UTC. The
two-platform installed milestone remains pending. This candidate stays
separate from the newer arrays.

**Installed-array workflow passes its complete source rehearsal.** The
[new additive gate](SKY130_METAL_PARALLEL_INSTALLED_ACCEPTANCE.md) now verifies
30 actual LI/M1–M4 arrays, 20 routed count transitions, five late-lock rejections
and 43 queued native/fault/repair requests. All 42 native executions pass their
expected positive or fault outcome. Fresh actual array netlists and extraction
feed all 60 DC/AC runs and 3,870 application/extracted/analytical path samples;
neither input is regenerated. Independent full readback and all 31 rehashed
component corruption controls pass. Both 582-test, six-stage feedback lanes
pass, with 16 Windows and four Linux skips; all 1,398 source hashes agree.
The complete Linux suite passes 3,759 tests with 61 skips. The
[execution record](validation/sky130-metal-parallel-installed-source-2026-10-26.json)
retains every attempt, source/runtime identity and original result. Its
44.96 MB archive covers 800.49 MB of logical evidence; all 3,447 objects pass
independent readback, and restoration of 4,233 actual GUI/electrical files at
their original paths reproduces both unchanged full audits. Both platform
workflows now require this gate alongside every existing gate. Fresh packaged
Windows/Linux array acceptance remains pending. The 67% estimate, all 287
partial device statuses and six unavailable real bindings are unchanged.
After successful archive recovery, four byte-verified duplicate Linux output
directories were removed: 8,466 files totaling 1,040,869,650 logical bytes.
The permanent archive, source fixture, tools, PDKs and Windows outputs remain;
this is not a claim that the Linux disk file shrank on C:.


**October 26 imported resistor hierarchy complete within its declared scope.**
The [new source milestone](SKY130_METAL_RESISTOR_HIERARCHY.md) verifies all five
LI/M1–M4 models with a reused 2 × 5 µm child, independent top terminals and
rotated/mirrored placements. Ten clean layouts pass native DRC/strict LVS;
twenty native connectivity/geometry faults and twenty-five actual exchange
corruptions are detected. Independent raw readback, twelve rehashed evidence
controls and restoration of 1,743 full-run files pass. The 8.14 MB permanent
archive retains all original attempts and the separately identified later
checker. This closes the selected imported repeated-cell class. Parameterized
arrays have their own result below; electrical hierarchy response, full ranges
and installed hierarchy remain open. The full `LI-PHYSICAL-CLASSES` row stays
partial.

**Physical parallel resistor capability and full source selection pass.** The
[new generator](SKY130_METAL_RESISTOR_PARALLEL.md) replaces the former
`mult != 1` rejection with integer counts 1–16 for LI/M1–M4. Single-unit
geometry remains unchanged. Actual source Qt transitions through 3, 16, 2 and
1 pass for all five models, preserving both attached wires, terminal identities,
review/apply, undo/redo and save/reopen. Independent readback verifies all twenty
transitions and five late layer-lock rejections. All 280 clean native layouts,
twenty-five faults and thirty actual-array DC/AC contexts pass the frozen
contract and independent full audit, including GDS and OASIS round trips.
The sixty electrical runs use actual array extraction; 3,870 path samples pass
with maximum normalized error 7.51 × 10⁻⁸ against limit one. Forty exact
serialized comparisons preserve the earlier single-unit implementation.
The two failed pilots remain retained. The [execution record](validation/sky130-metal-parallel-2026-10-26.json)
includes complete recovery of 15,103 full-run files and independent raw audit.
All 9,890 archive objects pass independent readback. The [final combined feedback](validation/sky130-metal-parallel-source-feedback-2026-10-26.json)
passes all six stages on both hosts: 550 tests each, four Linux and sixteen
Windows skips. All 1,386 source identities agree. Complete native-Linux unit
discovery also passes 3,725 tests with 61 skips. Installed array acceptance and
full family limits remain separate requirements. After verified recovery,
six exact disposable Linux output directories were removed, totaling
5,337,865,592 logical bytes; the permanent archives, tools, PDKs and source
fixture remain. No physical C: reclamation or Windows administrator action is
claimed.

**Linux setup delay addressed locally.** The earlier package download took
1 hour 46 minutes 11 seconds. The [dependency change](OPENEMS_BUILD_DEPENDENCIES.md)
installs five build-only openEMS packages only when the restored runtime fails
its existing file/native verification. Seven command control-flow checks pass;
all original preparation, native and release gates remain. A future hosted
candidate must establish the actual behavior and any speedup. The running
`e3fa0cc` candidate uses the earlier workflow.

**October 26 desktop failure review, candidate
`38fccf7242bac4c86117982ce03c78dd07302cf2`.** This was the previous selected
candidate, now superseded by the repair above. The
[full desktop run](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/40216858937)
finished with five prerequisite jobs passing and both package jobs failing the
same core capability test. Each platform ran 3,680 tests; Linux reports one
failure and 37 skips, Windows one failure and 40 skips. The expected capability
list in `test_analog` omitted the newly implemented `metal_resistor` capability.
The selected installed resistor gates were not reached and remain pending.
The [repair](validation/chunk7-desktop-capability-repair-2026-10-26.json)
retains the exact capability assertions and adds this single regression to the
fast lane. Both final source lanes pass 506 tests and all five stages, with
1,377 matching source bindings. Windows has 16 skips; Linux has four. A new
immutable desktop candidate still must pass the complete installed workflow.

The [prior automatic merge feedback](validation/chunk7-metal-installed-hosted-feedback-2026-10-25.json)
passed all five stages on both hosts: 504 tests per host, with four Linux and
fifteen Windows skips. Both retained artifacts pass readback, and all 1,377
source identities match that candidate. This was focused source feedback; it
omitted the capability test that failed full discovery. The complete original
failure logs are retained separately from the repair and any subsequent run.

**October 25 GF180 discrepancy provenance resolved.** The
[upstream reference review](validation/gf180-mos-upstream-discrepancy-2026-10-25.json)
confirms that the two retained fast-corner current overshoots already appear
in the released model-reference workbook; its values agree with independently
re-read historical direct-model results at the workbook's displayed precision.
The latest reviewed upstream MOS model is unchanged. This removes application
export as the origin of that conflict; the literal specification failures and
incomplete threshold definition remain open. No new simulation or relaxed limit
is claimed. The 269 KB source/evidence archive passes complete readback. This
review and its documentation are included in the selected `e3fa0cc` candidate.

**October 25 next milestone in progress, based on `489b0ea`: installed resistor
acceptance.** The new versioned contract fixes 30 actual editor/native inputs
across LI/M1–M4, three geometries and two orientations. Twenty-four M1–M4
inputs must feed the unchanged 90-batch electrical selection from the installed
app’s actual references, fresh extraction and shipped simulator. The 30-case Qt source lifecycle and
independent checker tests pass. Windows installer and Linux frozen-app hooks
now require the new selected GUI/native and electrical aggregate. The fresh
Linux source-native run passes all 30 layouts and 43 queued jobs in 94.737
seconds, including all five width faults/repairs, a DRC fault/repair and the
missing-engine rejection. The first failed driver attempt is retained; the
current inspector-field fix has an actual Qt regression. Independent raw
readback and all 90 electrical batches pass on the actual 24 received M1–M4
inputs: 720 conditions each for DC/AC/transient, 120 noise conditions and
4,680 detected controls, with no tolerance changes. Sixteen copied-evidence
component corruptions reject. Both final source-feedback lanes pass 504 tests
and all three GUI checks (Windows 123.171 seconds, Linux 51.488 seconds).
All 1,377 source/workflow/dependency identities match the reviewed checkout.
The Linux snapshot-only missing-document attempt is preserved separately.
[Source execution record](validation/sky130-metal-installed-source-2026-10-25.json).
The Windows ngspice46 portability check also passes all 90 contexts and
4,680 controls on exact copied GUI/native inputs, with 851 unchanged source
bindings. Its worst selected transient error is 0.97998234 against the fixed
normalized limit of 1; installed execution must pass independently.
The 87.2 MB permanent archive passes full readback of 37,015 logical files
and recovery of 25 selected files from authenticated objects; original failures,
source versions and both platforms’ raw results remain recoverable.
The exact packaged candidate is next. Source pilots
remain development evidence; a selected installed result requires both exact
candidate deliverables and the existing release gates. This work does not yet
raise the 65% estimate or change a device status.

**Previous accepted source candidate: `489b0ea0310aea74a7c298b842362e7851f3f868`.**
The [automatic GitHub merge checks](validation/chunk7-metal-hosted-feedback-2026-10-25.json)
pass on `e0965a0bcc55ebfd9ad84c7fb257eff9a1f686b9`: both 442-test lanes,
release contracts and all three GUI workflows, with four Linux and fifteen
Windows skips. All 1,365 reported source hashes match the exact candidate Git
blobs; the post-commit check also binds the unchanged CRLF contract, for 1,366
identities. Both complete small artifacts and merge-parent evidence are verified
and retained. The published implementation, milestone record and 65% estimate
are on `experimental`; this final hosted receipt/status note stays local for
the next substantive push, avoiding another CI run solely for a result note.
After verified archive readback, exactly seven disposable Linux output folders
were removed (2,168,874,044 logical bytes). Tools, PDKs, reusable source fixture,
receipts and archives remain; no Windows-admin or physical C:/VHD reclaim is
claimed. Chunk 7 remains **65% complete (55–75%, low confidence)**.

**October 25 capability milestone, based on `6a9980b`: native resistor editing
and independently audited four-model electrical linkage.** The editor now
places and regenerates straight LI and M1–M4 resistors through the ordinary
preview/apply workflow, with persistent terminals, undo/redo and saved package
identity. Live connectivity uses the actual resistor marker masks, and
connected edits enforce terminal spacing in flat and hierarchical layouts.
The full editor batch passes 30 coupons, 60 native orientations and 150 detected
physical/reference faults; independent readback verifies every native device
and 360 exported mask comparisons.

A separate M1–M4 contract now joins application export, actual extracted devices
and analytical references across five passive sections and three temperatures.
All 90 native batches pass: 720 selected conditions each for DC, AC and transient,
120 noise conditions and 4,680 detected branch/context faults. Independent raw
readback and twelve rehashed evidence-corruption controls pass. All 24 relevant
editor-generated extractions are byte-identical to the electrically tested
inputs. Multiplicity three means three electrical copies, not a qualified
physical array. The transient pilot failure remains retained; tighter numerical
integration settings repair it without changing the fixed tolerance.

This delivers missing editing capability for five device types and closes a
specific extracted-electrical integration gap for four models. On that basis,
the engineering estimate rises to **65% (55–75%, low confidence)**. This is not
computed from test counts: all 287 device entries remain partial, six required
bindings remain unavailable, and full envelopes, additional physical classes,
calibration/reliability and applicable installed workflows remain open.
Final Windows and Linux source feedback pass 442 tests each (16/four skips),
release contracts and all three GUI probes in 124.828/55.642 seconds. All 1,365
reported source identities match the reviewed checkout. The GF180 historical
identity failure is repaired with exact original Git blobs. A separate Windows
PDK publication failure is fixed with bounded retries and no-overwrite/path
checks; actual lock/junction tests pass. Linux retains its original operation.
The native batches retain their exact pre-repair sources; explicit source deltas
and focused tests bind the final changes without relabelling old execution.
[Execution record](validation/sky130-metal-editor-linked-2026-10-25.json).
The 93.8 MB compact archive passes full readback of 66,920 logical files through
verified local and pinned dependency objects. It retains original failures and
source versions without repeatedly copying toolchains. The source milestone is
pushed and its automatic GitHub merge feedback passes, as recorded above.

**Previous source candidate: `6a9980bc83e7594d86b65034ff5b115b03cc14ef`, pushed
and verified against GitHub.** The [automatic PR feedback](validation/chunk7-mim-alias-hosted-feedback-2026-10-24.json)
passes on actual merge `cdf0b6589aeb0a39ec22765ddc616a1c159abe9c`:
399 tests per host (15 Windows skips, two Linux skips), release contracts and
both GUI checks. All 1,356 reported source hashes match the exact Git blobs;
the separate post-commit native/source binding verifies 1,358 Python, contract,
workflow and dependency identities. Both complete hosted artifact ZIPs and merge
parents are verified and retained. The exact installed desktop result below
remains bound to `65614924`; this source-only qualification update does not
claim a new package build. The implementation, acceptance records and tracker
checkpoint are pushed. This final hosted receipt and status note remain local
for the next appropriate push, avoiding another run for status alone. Chunk 7
remains **60% complete (50–70%, low confidence)**.

**Desktop acceptance passed: `65614924f125200db068d66669af6fe102c71e45`.**
The [selected desktop run](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/40047259255)
completed all seven required jobs on its first attempt in 5:26:20. Windows
installation, 100/150/200% display probes and uninstallation pass; Linux frozen
desktop acceptance passes. Both hosts discover 3,558 core tests with no failures
(35 Linux skips, 40 Windows skips). All platform-specific skips pass on the
other host, but 22 tool-configuration-dependent core tests remain skipped on both;
the separate runtime gates do not retroactively pass those exact tests.

The [installed MiM acceptance](validation/sky130-mim-installed-acceptance-2026-10-24.json)
closes the selected configured workflow on both hosts: four fresh GUI/native
layouts, three current/historical binding states, actual DRC failure and repair,
missing-engine rejection, four clean public-deck layouts and one detected width
fault across 255 categories. Each host passes 60 selected electrical contexts,
480 AC samples, 60 operating points, 180 bias faults, five domain rejections and
40 bias-invariance comparisons. The shipped simulation package and engines are
used with the separately locked physical PDK adapter. Independent receipt review
and full archive readback verify all 7,361 selected inventory files, 470 source/
contract Git-blob identities per host, 600 raw electrical files and ten public
outputs. Complete diagnostic ZIPs are retained; duplicate multi-GB installers
were not downloaded. Four deliberate digital fault verdicts and four
informational pre-layout timing failures remain explicitly classified; required
equivalence and extracted timing pass. Code signing remains unconfigured.

The original `MIM-INSTALLED` recipe is completed for this exact candidate.
Full family qualification and chunk 7 remain open: the completed recipe does
not establish all physical classes, operating envelopes,
calibrated statistics or reliability. The
[actual mismatch-alias execution](validation/sky130-mim-mismatch-aliases-2026-10-24.json)
now completes the selected source-integration gap: 45 native runs on each host,
independent readback of 1,080 device-frequency observations and 20 detected
control conditions per host across all five selected sections. The actual
application aliases set the switches; no manual override substitutes for them.
Four fixed replicas remain an integration sample, with empirical statistical
calibration still open. Sixteen rehashed controls reject altered evidence or
source provenance. The original and new predefined contracts are unchanged.

Both final combined lanes pass 399 tests (15 Windows skips, two Linux skips),
release contracts and both GUI probes in 122.547/47.110 seconds. All 1,356 source
identities match. Earlier Windows temporary-folder/junction/cleanup failures
and the Linux mounted-checkout 300-second timeout remain retained; the same
sources pass using short ordinary-user Windows temporary storage and a verified
Linux-local fixture. No Windows admin, increased timeout, weakened test or
repeated successful native batch was needed. A 20.6 MB archive retains 3,911
logical files through 1,247 distinct objects; complete readback and restored
pilot/full Windows/full Linux audits pass. The application, models and PDK
package revisions remain unchanged. The estimate remains **60% (low confidence,
50–70%)**; six unavailable real bindings, complete operating limits, broader
physical classes and full family qualification still remain.

**Current hosted reference candidate: `c61eeaa3a416800cbd83c03a0409c475d638573a`, pushed and
verified against GitHub.** The guarded rebuild and MiM shape corrections,
local acceptance records and tracker are committed on `experimental`.
The [full reference run](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/40039513837)
passes all ten jobs for that exact candidate in a 24:21 job span, with one dispatch
and no retries or cancellations. Its [automatic PR feedback](validation/chunk7-identity-hosted-feedback-2026-10-23.json)
passes in 2:08 overall: 320 tests per host (two Linux skips, 14 Windows skips),
syntax, release contracts and both GUI probes. All 1,340 source hashes match
the exact candidate Git blobs, and both full artifact ZIPs are verified.
All five toolchain readiness steps have now passed: nominal, ff and fs executed
real hosted builds after version-only mismatches; ss and sf reused the producer.
All five pass the unchanged full native suite: each has 106 nets, 3,261 resistors,
103 devices, four PVT cases and twelve startup ramps. The
[hosted recovery record](validation/reference-toolchain-recovery-2026-10-23.json)
binds all five complete reports, producer and rebuilt tool archives, candidate
sources and independent review. All independent schematic/physical jobs pass;
the known optional raw hierarchical Magic stream still has 288 DRC findings,
while its required canonical-stream checks pass. Blocked optional scopes remain
recorded separately. The 33.3 MB recovery
archive passes readback. This closes the specific toolchain identity blocker;
it does not close chunk 7 or establish foundry signoff.
Verified archive recovery also allowed removal of the disposable Linux source
feedback copy (283.5 MB of logical file data). This status note is local for the
next appropriate push, avoiding another run for documentation alone.

**Resolved investigation: exact toolchain mismatch identified at `51917f7`.**
The [instrumented reference run](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/40037005574)
records the producer's `ImageVersion` as `20261012.334.1` and the failed ss
consumer's as `20261023.334.3`. Candidate, workspace, all seven source inputs,
operating-system marker, system and architecture match. This establishes the
environment-marker difference for this attempt; it does not establish different
runtime contents or retroactively identify the missing field in the old fs
failures. The producer archive and failed consumer's full artifact are retained
and verified. The superseded diagnostic run was cancelled once after capturing
the cause; it is not a complete five-corner acceptance.

The [locally verified repair](validation/reference-toolchain-identity-2026-10-23.json)
preserves strict rejection of the transferred tools and
allows a fresh, locked build on the consumer only for a verified image-version
cache miss. Corrupt archives and all other identity failures remain errors.
Freshly built tools must receive their own manifest and probes before the
unchanged native qualification. Independent review passes 46 Linux tests and
15 actual CLI fixture cases, including corrupt payloads, drift and incomplete
builds. The [combined integration](validation/chunk7-identity-integration-2026-10-23.json)
passes 320 tests per host (15 Windows skips, two Linux skips), release contracts
and both GUI probes in 77.7 seconds on Windows and 37.2 seconds on Linux. All
1,340 source bindings match the tested snapshot. Fixture builders are synthetic;
the separate `c61eeaa` hosted record above verifies the real engines and full
native acceptance. The earlier scheduling change is verified:
all five consumers started when the producer was ready while physical checks
continued. Every physical, five-corner and release gate remains required.

The [automatic PR feedback for `51917f7`](validation/chunk7-scheduling-hosted-feedback-2026-10-23.json)
passes in 2:22 overall, with 294 tests discovered per host (two Linux skips,
14 Windows skips), release contracts and both GUI probes. All 1,340 source
hashes match that exact Git candidate. Separately, the
[MiM shape correction](validation/sky130-mim-physical-scope-2026-10-23.json)
fixes a reproduced bypass for nonrectangular electrodes with square bounding
boxes. Nineteen focused tests pass on each host, and three fresh native layout
cases pass DRC/LVS, public checks and direct extraction checks. Independent
readback and a fresh mixed-case replay from archived sources pass. Four malformed
layout controls reject before engine execution. True square electrodes retain
their existing native path. Verified recovery precedes removal of 637.5 MB of
Linux temporary files and 84.9 MB of Windows duplicates; no administrator access
or Windows virtual-disk shrink is claimed. No device or chunk status has changed.

**Historical pre-build plan, superseded by the October 24 acceptance above.**
The next executable MiM requirement at that checkpoint was exact installed Windows/Linux acceptance:
place/edit/save/reopen, preserved old package bindings, rotated native exports
and the predefined electrical cases through the shipped engines. The existing
frozen physical probe covers an inverter, so a MiM-specific in-app probe must
precede a new package build. Retained desktop artifacts from `e44f7f3` predate
these fixes and cannot qualify this candidate. Their successful full build took
5:36 overall (Windows package job 4:37; Linux 1:16). A comparable future build
may take roughly 4–6 hours, with low confidence and additional risk from queueing,
cache misses or new failures; this is a forecast for that build, not chunk 7.
The [staged Windows preflight](validation/sky130-mim-windows-preflight-2026-10-23.json)
now passes 546 multiplier comparisons and four linked MiM contexts: four actual
operating points, 32 AC samples, ten bias faults and five domain rejections.
Independent review verifies 800 source files against `c61eeaa`, the unchanged
models/runtime and selected historical extraction members. Its scope is tt,
0°, 0/+5 V, with no fresh physical execution or installed acceptance. Verified
archive recovery permits removal of 168 MB of temporary Windows copies.
The separate [Linux runtime preflight](validation/sky130-mim-linux-runtime-preflight-2026-10-23.json)
passes 546 analytical multiplier comparisons on the existing apt ngspice 42.
It supplies no PDK or installed-desktop acceptance and does not require a
runtime replacement for the known unpatched-47 parsing issue.

After the verified toolchain recovery, the built-in MiM editor/native-layout
probe and separate installed-output checker pass
[source bring-up](validation/sky130-mim-installed-probe-source-2026-10-23.json).
Four actual GUI cases cover both capacitor bindings at 0/90 degrees, plus three
current/historical save/reopen states. Seven queued source jobs exercise four
clean native layouts, an actual DRC failure, fresh repair and missing-engine
blocking in 17.3 seconds on Linux. Independent readback verifies all six native
outputs and rejects ten rehashed corruptions; the installed checker correctly
rejects this source/custom-engine report. There is no new package build or
installed acceptance yet. The [public-deck source record](validation/sky130-mim-installed-public-drc-source-2026-10-23.json)
passes four clean exports and one narrow-metal fault through all 255 public
categories. The [electrical source record](validation/sky130-mim-installed-electrical-source-2026-10-23.json)
passes sixty contexts in 469.6 seconds: sixty operating
points, 480 AC samples, 180 bias faults, five domain rejections and forty
zero-bias comparisons. Both use the same four fresh GUI/native inputs.
Independent readback rejects ten public-output and thirteen electrical-output
corruptions, and the compact recovery archives are verified. The new aggregate
checker binds the original GUI jobs, raw inventories and independent electrical
audit; resealed cross-case substitutions and qualification overclaims reject.
These runners are now mandatory in Windows installation and Linux frozen-app
acceptance, before release archive assembly. The original `MIM-INSTALLED`
requirement and complete family gate remain open; no catalog entry is promoted.
The first combined source feedback retains seven failures per host, all from
the old GF180 gate detecting the changed application entry point. A new
historical source snapshot preserves the exact original `__main__.py` Git blob
and acceptance hash without editing the old record or weakening its checker.
The [final combined feedback](validation/chunk7-mim-installed-integration-2026-10-23.json)
passes 384 tests per host (16 Windows skips, two Linux skips), release contracts
and both GUI checks: 102.0 seconds on Windows and 42.8 seconds on Linux. All
1,352 checked source hashes match the retained snapshot. The earlier failure,
all 6,467 source files and final GUI evidence are recoverable from verified
compact archives. No new GF180 execution is claimed by the historical snapshot
correction. A new selected package build is the next acceptance step; no
installed result is inferred from this source feedback.

**Prior hosted follow-up: `1260cec`.**
Its [automatic PR feedback](validation/chunk7-bias-hosted-feedback-2026-10-23.json)
passes on actual merge `4c1267ff` in 2:43 overall. Both hosts discover 293 tests
(two Linux skips, 14 Windows skips), and syntax, release contracts and both
GUI probes pass. Both artifact ZIPs and all 1,340 source hashes are verified.
This follow-up receipt and tracker note are included with the next meaningful
workflow change, avoiding a separate launch for status alone. Implementation
and the preceding qualification records are already pushed. Shared-toolchain
five-corner acceptance remains incomplete because fs failed its identity gate.


**Working snapshot: October 23, 2026; integration based on `d38615c`.**
The hosted reference run retains immutable candidate
[`d38615c`](https://github.com/jonahsaunders/IC-Design-Studio/commit/d38615c77ecb7b09ff4128d591c6d6294ce4d57b).
This integration includes the subsequent signed-bias implementation, toolchain
mismatch diagnostics, hosted receipts and cleanup records. Later source
identities are recorded separately from that hosted candidate.
The [hosted PR feedback](validation/chunk7-focused-integration-2026-10-23.json)
also passes on actual merge commit `a0ea2451`: 260 tests discovered per host
(two Linux skips, 14 Windows skips), release contracts and both GUI probes.
The workflow finishes in 2:24 including queue/setup; source feedback itself
takes 53.4 seconds on Linux and 86.8 seconds on Windows. Both downloaded
artifacts match all 1,336 checked source hashes.
The new [MiM source contract](SKY130_MIM_REQUIREMENTS.md) and
[execution record](validation/sky130-mim-passive-corners-2026-10-23.json)
close a concrete execution gap: both capacitor
constructions now pass the predefined twenty contexts across five genuine
passive sections and two orientations, with four fresh native layouts,
twelve physical faults and 120 electrical faults. All eighteen initial focused
tests pass on both hosts. The complete archived data passes independent readback
on Windows, and archived sources reproduce a fresh selected case on Linux.
Subsequent independent review found incomplete execution-script bindings in
both the capacitor and LI reuse auditors. Both fixes now reject all five
previously accepted script alterations, with pristine evidence still passing.
The capacitor checker passes all 23 final focused tests on both hosts and
the complete Windows/Linux readback; LI passes 21 tests and 21 native controls,
plus five independent review controls. The native results and earlier checker
versions remain preserved separately.
The [subsequent voltage source map](qualification/sky130-mim-bias-source-map-v1.json)
verifies twelve source hashes and four historical native inputs. The later
[signed-bias execution](validation/sky130-mim-bias-boundaries-2026-10-23.json)
passes all sixty selected −5/0/+5 V contexts with sixty actual operating points,
480 AC samples and 180 detected bias faults. Its strengthened independent audit
also verifies five domain rejections and forty zero-bias comparisons. All
twenty-nine rehashed evidence controls are rejected. Four historical physical
inputs retain their identities; no physical layouts were rerun. The mapping
remains an explicitly reviewed construction inference, and the result does
not establish the full operating or reliability envelope.
Archive-restored source reproduces four fresh electrical contexts and both
independent live audits. Verified recovery precedes removal of 3.13 GB of
unique Linux file data and 84.9 MB of Windows source ZIP duplicates. These
figures do not claim a Windows virtual-disk shrink; no administrator access
was used.

The [selected LI development runner](SKY130_LI_DEVELOPMENT_REUSE.md) has demonstrated a real original-execution
cache hit. Its latest guarded fresh run takes 13.9 seconds and reuse takes
9.4 seconds; native execution alone takes 4.5 seconds. This establishes safe
reuse mechanics under the declared runtime profile, not a speedup over the
original tiny unkeyed native case. Final independent review passes; verified
archives preserve the sources, failures and original execution identity.
Default/exhaustive/release callers remain fresh.

The [first shared-toolchain hosted trial](validation/reference-toolchain-reuse-2026-10-23.json)
retains its package-download failure and five skipped consumers. The subsequent
[immutable `d38615c` trial](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/40028442049)
builds both engines once: dependency setup takes 32 seconds, engine builds
234 seconds and packing four seconds. Its archive and seven source inputs
pass readback. Nominal, ss, ff and sf have completed native qualification with
verified selected report members. The fs consumer failed
the strict toolchain identity check before simulation. Its exact mismatched
field is unresolved, and the original failure remains evidence. A local
diagnostic improvement records the differing identity fields without weakening
the gate; it has not repaired or validated that failed hosted consumer. One
retry of only fs failed the same gate; debug logs still do not retain the exact
differing field. No successful corner or toolchain producer was restarted. Full
shared-environment acceptance requires all five corners. Consumer ZIP digests
are API-reported where only selected report members were downloaded.

The [earlier combined local feedback](validation/chunk7-focused-integration-2026-10-23.json)
passes 260 focused tests per host (15 Windows skips, two Linux skips), release
document validation and both GUI probes. It takes 72.9 seconds on Windows and
36.6 seconds on a verified Linux-local source copy, excluding setup. All 1,336
code/workflow/dependency bindings match the tested sources. That implementation,
source contracts and those local-test results are pushed. The
[subsequent local integration](validation/chunk7-bias-integration-2026-10-23.json)
passes 293 tests per host (15 Windows skips, two Linux skips), release-document
validation and both GUI probes. It takes 81.7 seconds on Windows and 39.0 seconds
on native Linux storage, with all 1,340 code/workflow/dependency bindings checked.
The final source snapshot has verified archive recovery; removing its temporary
Linux copy recovers 283.2 MB of logical file data, without a Windows disk-size
claim. **Chunk 7 remains about 60% complete, low confidence
(50–70%).** The 287 partial entries and six unavailable bindings are unchanged.
The selected MiM milestone does not close missing envelopes, physical classes
or installed acceptance. Chunks 8–12 remain conditional on those dependencies.

Verified archive recovery allowed another 280.5 MB of Windows duplicates and
974.4 MB of Linux temporary data to be removed. Separate LI and review-copy
cleanup receipts retain their own totals. These are file sizes, not a claim
that Linux deletions shrink the Windows virtual disk; no administrator access
was used.

**Snapshot: October 23, 2026; integration pushed as `43a04bb`.**
Local `experimental` and GitHub match
[`43a04bb`](https://github.com/jonahsaunders/IC-Design-Studio/commit/43a04bb00af3118fe97d3d177ec73599056027b6).
The [first hosted feedback run](validation/chunk7-integration-feedback-2026-10-23.json)
passes on the actual PR merge commit: 211 focused tests per host (13 Windows
skips, two Linux skips), release-document validation and both GUI probes.
Including setup, Linux finishes in 1:35 and Windows in 2:29. The final aggregate
passes at 4:07, including its 91-second queue wait. Both downloaded artifacts
match all 1,328 current source identity bindings. `main` now requires the
GitHub Actions **PR feedback** check with an up-to-date base; the default
administrator bypass is available. Four unfinished workflows on the superseded
candidate were cancelled. Native shared-toolchain and merge-queue execution
remain unverified by this PR run.

Verified archives retain exact sources, failed attempts, native results and
final audits. Cleanup removes 0.52 GB of temporary Windows files and 4.17 GB
inside Linux; no administrator access or virtual-disk compaction was used.
The new hosted receipt and this sync/cleanup note are local documentation
updates for the next project push, avoiding a second run for status alone.
The implementation, family evidence and earlier tracker snapshot are pushed.

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
hosted shared-toolchain setup and latency are still unverified. At this local
checkpoint the repository had no protection policy. The later hosted run and
required-check configuration are recorded above.

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
67% complete**, with a broad planning range of **55–75% and low confidence**
(October 26, 2026; baseline `e3fa0cc` plus the independently audited imported
hierarchy and editable physical parallel-array milestones). This is a judgment about the
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
| 2026-10-26 | Completed the new parallel-array source rehearsal: 30 fresh GUI/native arrays, 20 routed edits, 60 received-input electrical runs, 31 rejected corruptions, both 582-test lanes, 3,759-test Linux discovery and exact-path restored independent audits. Added mandatory Windows/Linux installed gates. Linux earlier straight-resistor desktop and retained raw readback also pass. | Closes the selected source integration; fresh packaged array acceptance and full-family gates remain open. Estimate stays 67%, low confidence (55–75%). |
| 2026-10-26 | Completed the selected imported hierarchy class and editable physical parallel arrays for all five LI/M1–M4 models, with independent native/electrical audits, exact single-unit preservation and archive recovery. Both six-stage source lanes and complete 3,725-test Linux discovery pass. Reduced repeated Linux build dependencies while preserving release gates; retained original desktop failure and exact repaired candidate separately. | Concrete hierarchy and physical-array gaps close within their declared scope. Estimate rises to 67%, low confidence (55–75%). Full device envelopes, six bindings and applicable installed acceptance remain open. |
| 2026-10-25 | Delivered native straight LI/M1–M4 editing and separate M1–M4 extracted-electrical integration across five passive sections and three temperatures; independent native, mask, electrical and fault audits pass. Both final 442-test source lanes and all three GUI probes pass; verified compact retention and GitHub delivery/merge feedback are complete. | Missing editor capability and four-model linkage are closed within the declared scope. Estimate rises to 65%, low confidence (55–75%); full family gates and all catalog statuses remain unchanged. |
| 2026-10-24 | Verified all seven desktop jobs and completed the defined MiM installed recipe at `65614924`. Added actual five-section mismatch-alias source acceptance: 45 native runs and 399-test feedback per host, independent audits and verified compact recovery. | Concrete installed and alias milestones completed; all family statuses remain partial. Estimate stays 60%, low confidence (50–70%). |
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
