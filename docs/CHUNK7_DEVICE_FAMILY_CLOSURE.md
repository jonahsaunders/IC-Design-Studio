# Chunk 7: close one device family at a time

**October 30 current source checkpoint:** `f633d2c` adds the reviewed
two-terminal SKY130 pw2dn binding and corrected Linux simulator. The current
inventory is 289 partial entries, four unavailable bindings and nine utilities.
The earlier accepted inventory remains 287 partial / six unavailable / nine
utilities; full frozen acceptance of the current candidate is running.
The [current tracker](QUALIFICATION_PROGRESS.md) and
[combined source evidence](validation/chunk7-combined-pw2dn-feedback-2026-10-30.json)
separate these scopes. None of these binding changes qualifies a full family.

The October 30 [IHP CMIM source checklist](IHP_CMIM_REQUIREMENTS.md) now pins
the available process-control and physical-rule definitions and identifies the
remaining applicability gaps. The [existing MIM.g checker boundary](IHP_MIM_G_BOUNDARY.md)
is independently verified at below/equal/above-limit mask areas, with its failed
producer and separate recovered readback preserved. The new
[capacitor-only model controls](IHP_CAPACITOR_MODEL_SECTIONS.md) pass combined
source feedback on both hosts. These are finite source milestones; complete
device classes, operating envelopes and exact installed behavior remain open.

The October 28 [IHP resistor editor follow-through](IHP_RESISTOR_EDITOR.md) adds
finite linked Metal1/Metal2 access for three resistor models, reviewed source
LVS projection and an independent installed gate. Its original 60-case source
GUI proof and scientific 60-layout/165-control archive remain separately
identified. Final combined source and fresh frozen acceptance are pending.

October 28 follow-through adds a source-defined MOS voltage screen, full finite
metal hierarchy electrical evidence, an explicitly derived MiM fixture replay,
and a new optional ESD desktop acceptance path. The
[combined source checkpoint](validation/chunk7-final-integration-2026-10-28.json)
passes 795 tests and all six feedback stages on both hosts. The
[progress tracker](QUALIFICATION_PROGRESS.md) distinguishes their source results
from pending exact installed acceptance. None promotes a complete device family.

Execution update: October 26, 2026. The
[editable resistor and linked M1–M4 milestone](SKY130_METAL_RESISTOR_EDITOR.md)
is followed by the selected
[imported repeated-cell class](SKY130_METAL_RESISTOR_HIERARCHY.md), based on
`e3fa0cc` plus the separately retained qualification sources. Both independent
native readback and restored evidence checks pass. The separate
[physical parallel-array milestone](SKY130_METAL_RESISTOR_PARALLEL.md) now passes
its complete 280-layout, 25-fault and thirty-context DC/AC source selection.
It adds editable counts 1–16 for all five models, with attached-route and
single-unit compatibility checks. The older `e3fa0cc` Linux installed straight-resistor result passes; its Windows
job timed out after the installed step and provides no retained Windows raw
artifact. Exact `53c17aa7` Linux installed parallel-array acceptance and offline
component readback pass; the corresponding Windows run remains separate. Both MiM constructions also complete the
selected [imported repeated-cell source class](SKY130_MIM_HIERARCHY.md), with
four native clean layouts, eight native controls, ten stream controls and
restored independent readback. Full remaining class/envelope requirements remain.
The [linked MiM hierarchy electrical record](validation/sky130-mim-hierarchy-electrical-2026-10-26.json) completes a separate selected whole-network source experiment on those same four archived layouts: forty AC runs per host, all five passive sections, independent terminal excitations and fixed analytical limits. Its conditioned ±2⁻¹⁶V common-mode selection passes; the original larger-offset selection remains failed/unqualified. No full family, installed or arbitrary common-mode/geometry envelope is inferred.
The original planning baseline `43a04bb` and the
[sampled IHP high-voltage MOS acceptance](IHP_HV_MOS_LAYOUTS.md) retain their
historical scope. New results are linked explicitly below. The authoritative
[matrix](qualification/pdk-matrix.json) at that historical checkpoint contained
287 partial device entries, six unavailable real-device bindings and nine
utilities, with source baseline `43a04bb`. The current source inventory is
listed at the top of this document. Historical records retain their own sources and
package revisions.

A separate [optional ESD package](SKY130_ESD_NVT_BINDING.md) now provides the
explicit upstream-corrected binding and passes selected electrical integration
on both hosts. That record retains its original six-unavailable default scope;
the current source promotion and pending installed acceptance are recorded above.

The existing chunk gate is unchanged: every supported device must pass its
terminal, parameter, model, operating-envelope, layout and extracted-connectivity
requirements; unavailable required devices remain blockers. No family can be
declared complete merely by rerunning its current sample list. In particular,
the matrix's `device-simulation` requirement calls for a reviewed operating
envelope **before** execution. The present batch count is not that envelope.

## First closure candidate and immediate deliverables

Start with **SKY130 local-interconnect generic resistor `res_generic_li.sym`**
as the first narrow submilestone, then extend the completed method separately
to M1–M4. **The selected M1–M4 linkage is now complete:** its separate
contract tests actual extraction against application export and analytical
references across five passive sections and three temperatures. The native
editor now supports all five straight resistor types. Full family closure is a conditional
engineering priority, not a claim that its remaining limits are available.
The LI model has a simple two-terminal primitive, a corrected public binding,
native physical extraction, independent electrical references and analytical
RC/noise checks. It avoids the missing bindings and additional model types of
the RF, ESD, coil and thermal families. See the
[existing LI/metal evidence](SKY130_METAL_RESISTOR_QUALIFICATION.md).

The first [LI source contract](SKY130_LI_REQUIREMENTS.md) is now recorded with
open requirements. It identified missing distinct passive-corner coverage:
nominal/ss/ff all select the typical resistor parameters. The
[linked 2 × 5 µm pilot](validation/sky130-li-linked-2026-10-23.json) now passes
tt/ll/hh/hl/lh at 27 C and both orientations, including the actual native
extraction. This closes the selected linking example; operating-envelope,
physical-class and installed requirements remain. Generic-resistor
documentation also cautions against analog use; the LI submilestone is an
integration target, not a precision analog recommendation. No new gate is
created or existing gate reduced by this prioritization.

**Source deliverable completed: a reviewed LI requirement contract.**
Keep every row below tied to an exact public file/revision/hash,
the numerical or semantic requirement, and its existing or missing test. A
model coefficient, a simulation that converges, or a chosen test temperature
cannot establish a physical validity limit. Preserve an explicit unresolved
entry if public evidence does not supply it. Retain upstream license notices.

| Requirement | Existing evidence | Next action and exit condition |
| --- | --- | --- |
| Binding and interfaces | Source-checked `res_generic_li` → `res_generic_l1`; save/reopen and catalog exchange. | Bind every supported alias and imported/native view to the same reviewed contract. Verify current and saved package identities separately. No implicit migration. |
| Geometry and physical classes | Straight single resistors, six selected sizes, two rotations per LI/M1–M4 model; full native DRC/LVS and stream exchange. | Reconcile public marker rules, generator rules, extraction dimensions, grid, contact class, multiplicity and any snake/array views with the declared support. Identify each uncovered class explicitly. Verify boundary and interior cases for each supported class. |
| Operating conditions | LI DC, AC, transient and noise at selected conditions. | Establish source-backed geometry, temperature, voltage/current or power restrictions and actual corner mappings. Specify required observables and tolerances before new runs; record any missing reliability/statistical applicability rather than marking it passed. |
| Extracted electrical behavior | LI retains its linked 2 × 5 µm example. M1–M4 now have separate three-geometry, two-rotation, five-section, three-temperature DC/AC/transient coverage and selected noise, with all 24 native inputs byte-matched to editor extractions. | Extend only to source-backed required boundaries and supported classes. Shared-model agreement does not establish calibrated resistance/noise accuracy. |
| Installed acceptance | Both source desktops and historical tests. | On one frozen integration candidate, install exact Windows/Linux deliverables, perform place/edit/save/reopen/export/native verification, and run the required electrical cases. Record desktop/runtime/package hashes and actual received artifacts. Source tests do not satisfy this row. |

The smallest useful linked acceptance example is the existing legal **2 × 5 µm,
single LI resistor**, at 0° and 90°, with its two terminals, native full DRC,
strict LVS, exact extracted dimensions and independent DC/AC/transient/noise
references. Add the existing ordinary-rule **0.29 × 0.29 µm** physical control,
then the contract's remaining boundaries and classes. The earlier **0.17 µm**
electrical samples do not establish ordinary-layout legality: the public
special-context exception has not been applied to those layouts.

The **source requirement contract** and **selected linked physical/electrical
example** are now recorded, with source blockers explicitly retained. Family
closure requires all applicable contract rows,
all supported geometry classes and installed acceptance, with no unresolved
required row. Closing LI would not automatically close the four metal models:
the current LI electrical runner only exercises `res_generic_l1`.

If the source review cannot establish a required LI limit, record the precise
missing definition and continue an independently actionable family. Do not keep
adding LI samples and call that progress toward resolving the missing definition.

## Ordered work after the initial contract

| Priority | Family and target | Concrete next milestone | What still prevents family closure |
| --- | --- | --- | --- |
| 1 | SKY130 LI, then M1–M4 generic resistors | Five native editor recipes and the separate M1–M4 linked source-integration milestone are complete. Reconcile required geometry/envelope limits and qualify the exact installed recipe next. | Full applicable envelope/class reconciliation and exact installed acceptance. Metal layout evidence does not inherit LI electrical coverage. |
| 2 | SKY130 first and second MiM | [Versioned two-device contract](SKY130_MIM_REQUIREMENTS.md), twenty-context passive-section example and sixty-context selected ±5 V integration checks with actual DC readback are recorded. Selected imported two-occurrence whole-network electrical linkage now passes under its explicit conditioned-common-mode contract. Retain its original larger-offset numerical limitation, reconcile the remaining supported physical classes and source-defined boundaries, retain the completed October 24 installed recipe and qualify added classes separately. | Source-backed operating/statistical/reliability applicability, unsupported physical classes and acceptance beyond the completed selected installed recipe. Fractional electrical multiplicity does not imply fractional physical copies. |
| 3 | IHP 1.2 V and 3.3 V MOS, separate standard and RF views | Reconcile the sampled standard LV/HV geometry acceptance with the full model envelopes, then join extracted electrical checks. | HV sampled native geometry passes; unsampled classes and complete envelopes remain open. Public model measurements at 27 C do not establish complete temperature validity. Standard geometry cannot stand in for RF geometry even where compact model names overlap. |
| 4 | GF180 C and D standard 3.3 V MOS | Resolve the two retained fast-corner specification discrepancies and the incomplete threshold-extraction definition; consolidate finger/multiplicity coverage against the contract. | Literal published current bounds still differ from direct public-model results. Geometry batches and source/reference agreement cannot override those mismatches. C/D physical stacks remain separate. |
| 5 | IHP straight resistors and taps; GF180 C/D straight resistor families | Join each model's electrical envelope to its existing physical classes and native extraction. For taps include the exact computed-resistance binding and independent body/port check. | Selected geometry/temperature points, body handling, optional via classes, model-specific operating limits and installed acceptance. A disabled optional via stack is not a passed via class. |
| 6 | Remaining capacitors/varactors, junction diodes and bipolar families across all targets | Produce one contract per model/class, starting with families that already have native DRC/LVS and independent electrical evidence. Close their uncovered boundary/context rows. | Separate body/isolation/thermal terminals, nonlinear bias, applicable statistical/RF/reliability behavior, public limits and installed acceptance. Selected BJT thermal responses do not calibrate a thermal network. |
| Separate discovery queue | IHP coils/pads, SKY130 unavailable ESD/VPP/RF binding and other upstream process/tool views | Resolve exact model/source availability and semantic view equivalence; attach one evidence-backed resolution to each missing input. | The six required bindings below and the broader upstream semantic inventory. More successful execution on a substitute cannot resolve a missing identity. |

This order builds on sampled HV implementation acceptance while making the next
family's closure contract a separate, small piece of work. It does not require
waiting for the six unavailable bindings before closing an independently
complete available family. Chunk 7 as a whole still requires those blockers.

Relevant retained records are the
[MiM binding guide](SKY130_MIM_MULTIPLICITY.md),
[first-MiM correction](SKY130_FIRST_MIM_LAYOUT.md),
[second-MiM orientation](SKY130_MIM_ORIENTATION.md),
[MOS shared-finger guide](MOS_FINGER_LAYOUTS.md),
[GF180 specification result](GF180_MOS_SPECIFICATIONS.md),
[resistor geometry guide](RESISTOR_LAYOUT_QUALIFICATION.md),
[diode geometry guide](DIODE_LAYOUT_QUALIFICATION.md) and
[device adapter guide](DEVICE_ADAPTER_QUALIFICATION.md).
Use the latest execution record for each specific assertion; documentation
links to earlier batches do not transfer a pass to today's source revision.

## Keep three different blocker types separate

| Blocker type | Examples at this checkpoint | Useful next work |
| --- | --- | --- |
| Application or qualification defect | Missing required physical classes; incomplete extracted-versus-schematic electrical linkage; missing selectable case scheduling in older suites. | Reproduce the specific failure, fix code, retain the failing input, verify the affected case and meaningful fault controls, then run the affected regression set. |
| Source/model definition or discrepancy | Unspecified complete temperature/SOA definitions; missing models; GF180 ff currents disagree with literal published limits even for independent direct calls. | Pin and reconcile public sources, versions, units and extraction equations. Keep an unresolved requirement if evidence is insufficient. Do not invent a limit, round a failure into a pass, or reclassify a model discrepancy as an app fix. |
| Acceptance execution | Required installed workflow not yet run for the exact candidate; upstream tool-view enumeration has no semantic execution evidence. | Freeze inputs and run the defined acceptance once; retain complete success/failure evidence. An old installer, source-desktop pass or queued CI job does not satisfy it. |

The earlier accepted checkpoint has the following six unavailable real-device
bindings. They are exact catalog entries, not six arbitrary test cases. Current
source candidates resolve the first two electrical bindings; their complete
operating envelopes and exact installed workflows remain separately required.
The other four remain unavailable in the current source inventory.

| Target | Required catalog entry | Input that must be resolved |
| --- | --- | --- |
| SKY130 | `sky130_fd_pr/nfet_g5v0d10v5_nvt_esd.sym` | The matching electrical model is absent from the selected library closure. |
| SKY130 | `sky130_fd_pr/diode__sky130_fd_pr__model__parasitic__rf_diode_pw2dn.sym` | Default matching electrical definition is absent. Existing isolation geometry/candidate work does not establish the complete required electrical binding. |
| SKY130 | `sky130_fd_pr/vpp_cap__sky130_fd_pr__cap_vpp_11p3x11p8_l1m1m2m3m4_shieldm5.sym` | Exact fixed-layout model is absent. A differently sized VPP or different underlying device is not equivalent. |
| IHP | `sg13g2_pr/bondpad.sym` | Matching usable electrical model is absent. The public empty placeholder rechecked during the active HV investigation is not an electrical qualification. |
| IHP | `sg13g2_pr/inductor.sym` | Catalog electrical binding remains absent. Existing geometry and selected EM/measured-coil results retain their own identities. |
| IHP | `sg13g2_pr/inductor3.sym` | Matching three-terminal electrical binding remains absent; two-terminal coil results cannot supply the missing terminal behavior. |

Nine utility entries have separately declared non-electrical behavior; do not
count them as missing physical models or silently drop them from interface checks.
Pinned-file enumeration also does not prove that all upstream models, process
options and tool views have been semantically reconciled.

## Smallest safe selectable/resumable pilot

Pilot on `scripts/qualify_sky130_metal_resistor_layouts.py`, **one LI 2 × 5 µm
case**. It already supports `--models l1 --pilot --workers 1`, creates a stable
`l1-w2-l5` case folder, and keeps both orientations plus all five fault controls
inside `case()`. Resume that complete unit; do not reuse an individual successful
DRC step while its associated extraction, exchange or faults are incomplete.
Do not couple this pilot to the actively changing HV generator.

The shared `regions`, `same_masks` and `rotated` functions now live in
`scripts/qualification_geometry.py`. Their function syntax trees are identical
to the original IHP definitions; the IHP module re-exports the historical names,
and SKY130 imports the process-neutral module directly. Existing IHP/SKY130
mask, port, rotation and fault-mutation regression tests pass. This removes
cross-process runner coupling without claiming extra qualification coverage.

The [opt-in development pilot](SKY130_LI_DEVELOPMENT_REUSE.md) implements one
complete LI case; default and release paths remain fresh. Use a new immutable
run directory for every invocation. The development interface adds
`--development --select l1-w2-l5 --resume-from /existing/complete-run`. Unknown,
duplicate or empty selections must fail before tools launch. The selection list
and full required case list must both appear in the report; a selected run must
never report complete-family or release acceptance.

A reusable case key must include at least:

- Schema and suite identity, case parameters, orientations, all faults, fixture
  content, expected outcomes and numerical acceptance thresholds.
- Exact runner, auditor, application and helper hashes. Begin conservatively
  with the existing complete Python source closure plus the auditor; narrowing
  it requires a reviewed transitive-dependency manifest. Commit ID alone is
  insufficient for a dirty checkout, and hashing only the top-level runner
  misses imported behavior.
- Complete verified simulation/physical PDK manifests and assets, include
  sections, generated configuration, native DRC/LVS/extraction rule closure,
  generator scripts and source/limit locks. Simulation and physical package
  identities may differ and must both be retained when used.
- Executable and loaded runtime/library identities, Python/package versions,
  operating system/architecture, effective tool options and relevant environment
  values, random seeds and solver settings. Do not reuse across operating
  systems or tool binaries merely because version strings match.

Persist a terminal case record only after its outputs and file manifest are
complete. Reuse is allowed only after verifying all input identities and output
hashes **and rerunning the independent case audit against the original raw
outputs**. Missing evidence, mismatched inputs, generic launch failures,
truncated reports and interrupted cases are cache misses. A successful process
exit without required output is not an accepted case. Failed attempts remain
immutable historical evidence; do not rewrite them into successful reruns.

The new report should reference the original run ID, case ID, manifest hash,
source commit, dirty-source hashes and execution time. It should add a separate
reuse-validation timestamp and audit outcome. Never relabel old native output
as newly executed evidence or substitute today's source identity. Publish an
aggregate only after checking exact selected coverage, no duplicate cases,
all required faults, and unchanged inputs before/after execution. Reuse does
not alter `qualified: false` or `chunk_complete: false` in this development run.

Minimum controls for the cache pilot are: two identical invocations reuse the
complete case; one changed helper, threshold, tool binary, PDK asset or case
parameter forces fresh execution; missing/corrupted output forces fresh
execution; interrupted publication cannot become a hit; changed evidence with
updated file hashes still fails the semantic audit when geometry/model/ports
are wrong; a failed fault control cannot be cached as accepted; and reuse
preserves the original source/run identity. Test an unrelated documentation
edit separately so conservative code hashing does not cause avoidable misses.

**Release and exhaustive acceptance remain fresh.** Those entry points must
reject development reuse and run the complete required selection on the exact
frozen candidate. A development aggregate helps find regressions quickly; it
does not satisfy merge compatibility or installed release gates by itself.

## Reporting progress without counting samples as completion

For every family batch, report which contract row changed from missing to
specified, failed to passed, or unexecuted to accepted; name the still-open
rows and the exact evidence identity. Record native execution time separately
from environment preparation, queueing, reused audit time and repair work.
Measure time to first actionable failure and time to close a contract row.

The current estimate is in the [progress tracker](QUALIFICATION_PROGRESS.md).
The October 25 milestone delivers missing native editing for five device types
and closes four models’ selected extracted-electrical integration. Complete
family qualification still needs all applicable contract rows, six missing
bindings and exact installed workflows. Revise the estimate for delivered
capability and resolved requirements, not for the number of samples or tests.
