# PDK qualification in twelve chunks

**2026-10-16 approved completion boundary:** chunk 6 follows the
[SKY130 local qualification profile](SKY130_LOCAL_PROFILE.md).
Exports and verification are generic SKY130; Tiny Tapeout is a source of
inspiration, not the required target.
Work now prioritizes a complete local design workflow,
physical fault detection, meaningful density context and application export.
The catalog-wide source reviews below are historical evidence; the 302 unresolved
records remain visible and do not become passes through this scope change.
The user approved qualifying the explicit public-check baseline while excluding
unresolved process requirements from that claim. The
[bounded completion record](validation/sky130-public-baseline-2026-10-16.json)
completes chunk 6 on that basis; it does not establish full foundry signoff.

The target is analog and digital design on SKY130, GF180MCU C/D and IHP SG13G2.
No target is currently qualified for complete-chip tapeout. Work proceeds in the
order below; a passing small reference design keeps its original scope.

All qualification checks must execute locally. A shuttle or foundry service
running the missing checks does not satisfy this requirement. Public technical
clarifications can inform local implementations; the project's GPL license and
third-party attribution requirements remain unchanged.

The [local unblocking review](validation/sky130-local-unblock-2026-10-15.json)
identifies 33 unresolved records linked to explicitly frame-only rules. Their
applicability needs a verified layout context before any disposition can change.
The review also prepares an unsent request for public pin-spacing, context and
operand definitions. All 302 records remain unresolved; this is a concrete source
and applicability route, not a new acceptance result or a reduced completion gate.

The [machine-readable matrix](qualification/pdk-matrix.json) is the coverage
record. It includes 125 process/workflow requirements and all 302 bundled catalog
entries, including utilities and unavailable devices. Every requirement points to
a defined fixture, procedure, expected result, operating conditions, remaining
automation work and status. Each device has separate interface, simulation and
physical tests. These are test contracts; many are not executable yet.

The matrix also records the exact package revisions, source-lock hashes, model
include sections, device terminal/parameter mappings, digital libraries, metal
options and current digital operating points. It does **not** equate this bundled
subset with the complete upstream PDK. Upstream completeness and the remaining
device-specific operating envelopes are explicit open requirements.

## Current checkpoint: chunks 1â€“6 have completed their declared reference gates

Chunk 6 is complete as `sky130a-hd-public-checks-v1`: public native DRC,
supplemental geometry, thirteen antenna stages, strict device/body/port LVS,
public density windows, independent fill checks and generic portable export.
Fresh counter/UART/APB runs and Windows revalidation exercise the application.
The filled 840 Âµm counter passes nine full windows; smaller UART/APB blocks
explicitly require surrounding layout. Missing checks never inherit a pass.

The versioned export carries its exact source identities and exclusions. The
302 unresolved historical catalog records, missing x.20 definition, generated
mask coverage, complete-chip boundaries and electrical/installer qualification
remain unresolved. This is the narrower completion standard approved by the
user, not a claim that those requirements have been solved.

## Chunk 7: device execution is in progress

The [IHP isolation physical record](validation/ihp-isolation-physical-2026-10-21.json)
adds 20 isolation-box layouts and eight isolated-transistor/tap layouts, with
all 80 deliberately introduced faults detected. Twelve contact-enclosure
boundary checks produce the required four below-limit failures and eight
at/above-limit passes. The implementation preserves all three isolation
terminals, connects the physical NWell ring and retains internal tap recognition.
Both existing tap paths also pass their selected regression cases and twelve
fault controls. Eighty affected tests pass on each host, and five Windows-to-local-
Linux runs verify 885 returned files. Independent audits and archive replay
bind these results to their source. See the [scope and reproduction guide](IHP_ISOLATION_PHYSICAL.md).
Complete device envelopes, missing model bindings, broader physical coverage
and final installed-release acceptance remain required; chunk 7 is incomplete.

### Earlier RF isolation checkpoint

The [RF isolation record](validation/sky130-rf-isolation-2026-10-21.json)
adds explicit anode/cathode/substrate connectivity for a bounded SKY130 RF
p-well layout. Each host passes 24 legal layouts, detects all 186 deliberate
faults and checks twelve below/at/above-minimum n-well openings. Independent
readback verifies 156 native netlists, 1,056 stream-layer comparisons and 3,480
artifact bindings across both hosts. The affected 90-test suite passes on each
system; both source desktop actions and three Windows/native handoffs pass.

The three retained records describe planar geometry, not electrical simulation
models. Complete isolation behavior, missing default device bindings, full
operating envelopes, broader geometry/semantic coverage and exact final
installed-release acceptance remain required. This closes the tested physical
connectivity gap without changing any device's qualification status. Chunk 7
remains in progress.

### Earlier measured-coil and release-input checkpoint

The [measured-coil and release-input record](validation/ihp-measured-coil-2026-10-21.json)
completes fresh 1/2 µm reproduction of the public IHP L6n2 fixture. All four
native excitations reach −60 dB; independent raw-wave arithmetic and archive
restore/replay pass on both hosts. Full-band measured errors remain explicit in
the [reference guide](IHP_MEASURED_COIL_REFERENCE.md). This is one geometry and
stackup, not a general inductor-model accuracy qualification.

Runtime caching now identifies all 537 staged build inputs, including previously
omitted PDK preparation/model files. Both hosts verify identical staging and
pass 48 focused packaging/runtime tests. Multiplicity validation also follows
the emitted SPICE `m` parameter, preventing an `mf` alias from exporting zero or
negative multiplicity. All 286 available defaults still validate; 788 valid
exports remain byte-identical and four earlier rejections remain unchanged on
each host. The final full source suites pass 3,248 tests per host, with 63
Windows and 56 Linux skips. Documentation/evidence registration follows those
source snapshots; no executable code is changed afterward.

The retained protected Ubuntu release passes its frozen digital/physical checks
on older commit `ae5a7a1`; it is historical evidence, not acceptance of this new
source. Seven nonutility catalog entries still lack qualified default bindings.
Complete device operating envelopes, broader physical/extracted geometry,
semantic upstream/process-option coverage and exact final installed-release
acceptance remain required. Chunk 7 is still in progress.

### Earlier mixed-context checkpoint

The [latest mixed-context and EM record](validation/ihp-mixed-context-2026-10-21.json)
closes the large mixed-varactor blocker for the tested layouts. All 24 positive
layouts and 27 full-flow faults pass. The [context implementation](IHP_MIXED_CONTEXT.md)
retains both complete public decks and the native NPN supplement, with independent
physical-stream preservation, 72 native controls and five actual Windows backend
handoffs. Invalid native technology files can no longer pass either application
or standalone qualification entry points merely by printing a zero count.

Both IHP substrate profiles now pass the unchanged numerical criteria at
0.8/0.56 µm mesh sizes: maximum resistance changes are 1.91% and 1.93%, and
maximum impedance changes remain below 0.98%. Independent Windows/Linux raw
readback agrees, sampled passivity passes, and saved characterizations reopen
as current. This establishes numerical convergence for those fixtures only.
Pinned GPL-3.0 measured IHP coil data, its GDS, and published openEMS/Palace
comparisons are retained; their independent parser audit passes on both hosts.
Fresh simulation against that measurement remains a separate accuracy gate.

The final source suites discover 3,224 tests each and pass, with 63 Windows and
55 Linux platform skips. Original failed runs and exact historical GF180 source
blobs are retained. The verified evidence archive contains 34,943 path bindings;
restored native diagnostics reproduce their expected outcomes on both hosts.
Full device envelopes, remaining models, broader physical coverage and exact
installed-release acceptance still keep chunk 7 open.

### Earlier October 21 checkpoint

The [completed EM refinement and import diagnostics](validation/ihp-em-refinement-2026-10-21.json)
retain finished native runs and independent Windows/Linux readback. Both IHP
substrate options reach their energy targets and pass sampled passivity, but
the 1 µm refinements still differ by about 5.37% in resistance, above the
unchanged 5% limit. They remain rejected. The separate synthetic PML/domain
experiment passes numerical convergence and passivity; it is not a production
driver change or IHP accuracy result. The audit now checks actual native probe
coordinates, with deliberate position, unit and duplicate-header faults.

The original 5 µm synthetic CI domain fails the new passivity gate in the actual
hosted Linux run. The corrected 50 µm execution fixture passes with the unchanged
production driver and reopens as current on both systems; the original fixture
remains a rejected control. This retains the single-mesh CI scope and all
acceptance limits. A separate full two-mesh run of the same production-driver
fixture passes at 3.71% Z, 4.94% R and maximum scattering gain 0.98288, with
matching independent readback and current saved results on both systems.
Native execution of the repaired fixture on hosted Linux and
exact desktop-package acceptance remain separate gates. The full hosted IHP
pipeline passes on `552e3ce`, including its varactor, NPN and mixed-layout checks.
Thirty focused tests pass on each OS after the probe-audit addition; the preceding
complete suites pass 3,208 tests with explicit platform skips. Further large
mixed-varactor diagnostics still leave 39–58 native regions and are not promoted.
Required model availability, full operating envelopes, broader physical/extracted
coverage and installed-release qualification keep chunk 7 open.

The [full-network acceptance audit](validation/openems-passivity-2026-10-21.json)
supersedes the earlier synthetic result. Although its meshes agree within 1.40%
in impedance and 1.95% in resistance, the final two-port response implies gain
for some incident-wave combinations. Windows and Linux now reject attachment;
the historical characterization stays saved but stale. The new sampled
passivity check supplements the unchanged 5% mesh gate and applies to quick
previews too. No values are clipped or fitted. The
[synthetic study](validation/openems-mesh-study-2026-10-21.json) retains its exact
historical evidence and does not qualify any device. Separately, the full
[hosted IHP geometry pipeline](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/39613802857)
passes on commit `7cb7016`, including its NPN, top-via and mixed-layout checks.
Newer-source hosted acceptance retains its separate gate.

The [measured-wave correction](validation/ihp-em-waves-2026-10-21.json) resolves
the apparent negative IHP resistance in the earlier solver experiment. Native
probe files show incoming waves at the unpowered port; the driver now retains
both incident columns and solves the complete wave system. Independent voltage/
current matrix readback confirms positive resistance. The 280 µm run still fails
the unchanged mesh gate (4.80% Z and 7.73% R); the stopped 180 µm refinement remains
incomplete. Legacy structured openEMS characterizations now show as stale while
their evidence is preserved. This corrects the prior diagnosis, without promoting
any device or completing chunk 7.

The [native IHP EM follow-up](validation/ihp-em-native-rejection-2026-10-21.json)
records the historical rejected characterization, not a device pass. Its
negative-resistance interpretation is superseded above. The 280 µm two-mesh run
reaches its energy targets but fails impedance/resistance agreement; independent
matrix calculations also show negative coarse resistance for both substrate
options. The remaining 180 µm refinement was stopped once the unchanged
acceptance gate was shown to be impossible. An early rejection now avoids these
futile refinements in the editor and qualification command, preserving the
original mesh and final limits. The earlier complete-suite results below retain
their tested source; the follow-up records focused checks of the new guard.

The [October 21 IHP profile and mixed-layout record](validation/ihp-em-mixed-2026-10-21.json)
adds the pinned public top-metal material profiles for 280 and 180 µm bulk
substrates. Both source desktops verify review, apply, undo/redo and save/reopen.
Two top-via fixtures pass both complete public geometry decks; all five specific
via faults are detected. The actual generated solver-coil geometry also passes.
These are source, geometry and interface results, not calibrated EM accuracy or
replacements for the unavailable IHP compact inductor models.

Twelve mixed NPN/small-varactor layouts pass full native DRC and strict LVS,
with all twenty-one faults detected. Windows independently verifies the twelve
exchanges and twenty-four native/comparison netlists. A separate large Nx10
varactor combination retains 58 full native well-rule findings. Both complete
source regression suites pass 3,198 discovered tests with platform skips.
Historical GF180 source bindings preserve the exact previously tested Git blobs.
The earlier head has seven successful hosted PR checks and one IHP timeout;
the new timeout allowance retains all checks and adds via/mixed regressions.
New-head hosted acceptance, full operating envelopes, remaining models and
installed-release qualification remain open. Chunk 7 is not complete.

The [upstream file and tool-view inventory](UPSTREAM_VIEW_INVENTORY.md)
now enumerates 13,203 entries across the named IHP/GF180 repositories and
SKY130 common/primitive archives, including all five IHP submodules and explicit
non-target SKY130B entries. Every Git tree and archive identity is checked;
actual package bytes determine matches. Both hosts produce identical reports
and pass fifteen source-integrity tests. Device/process-option interpretation,
other source archives and execution qualification remain separate open work.

The new IHP public geometry action is now placed in the physical verification
submenu. This fixes the hosted interoperability failure caused by its earlier
top-level placement. Both the unchanged interoperability check and IHP action
check pass on Windows and Linux; subsequent hosted release acceptance is pending.

The [public IHP geometry record](validation/ihp-public-geometry-2026-10-20.json)
adds eighty passing varactor layouts across both public geometries and all Nx1–10
rotations, with all sixty-four faults detected. Thirty-six NPN layouts and
ninety-nine faults also pass. Both unmodified public geometry decks run locally;
separate written-oxide and full native NPN checks catch demonstrated omissions.
All original masks and annotations are retained. Independent readback checks
232 native/comparison netlists; eleven Windows handoffs verify 1,978 received
files. The archive restores and replays nine native success/failure controls.

The final full Windows suite discovers 3,175 tests and passes with
63 explicit platform skips; sixty-one focused Linux tests pass.
The prior commit's hosted checks pass except Windows frozen digital setup,
which reached the fourth process profile before its one-hour deadline. This
change retains every check and allows ninety minutes; new hosted acceptance
remains pending. Full device envelopes, remaining unavailable models, mixed
layouts and installed-release acceptance still prevent chunk 7 completion.

The [contacted-varactor record](validation/ihp-varactor-contacts-2026-10-19.json)
adds forty full-DRC/strict-LVS passes and twenty-eight detected faults for the
explicitly contacted small IHP geometries. A source-checked private correction
measures complete poly/varactor contacts using the unchanged 160 nm limit.
The coupon adds actual well/substrate ties while retaining every original drawn area,
gate and pin. Independent readback covers eighty netlists and four hundred
export layer pairs; six Windows backend cases verify 720 received files.
Eight earlier bipolar/tap/coil cases pass. The original Nx10 tie findings and
large-geometry well findings remain failed. Larger geometries, full operating
envelopes, other outstanding devices and installed-release acceptance remain
open; chunk 7 is not complete.

The full Windows suite passes 3,167 discovered tests with 63 platform skips;
the final verifier/backend checks pass another 37 tests. Linux discovers 3,168
tests with 55 skips: the source-copy run has one missing-Git-context error, and
that identical test passes from the real checkout. The compact evidence archive
restores and replays six native success/failure controls. The earlier detector
repair, coil/selected-varactor CI and release-tool checks pass at `e81d12d`;
hosted acceptance of the new contact/tie changes remains pending.

The [varactor and detector record](validation/ihp-varactor-and-detector-2026-10-19.json)
adds four-terminal IHP varactor comparison and prevents recognition annotations
from shorting separate devices. In that original run forty rotated cases passed
strict LVS, sixteen also passed full DRC, and twelve deliberate faults were
detected. Twenty-four smaller-layout rotations and the larger geometry had DRC findings;
see the [physical scope](IHP_VARACTOR_QUALIFICATION.md). The detector now runs
independent selector-code comparisons in two processes: all 32 waveforms match
the previous sequential run exactly, and the saved desktop bench passes. Hosted
acceptance, full device coverage and installed-release qualification remain open.
Chunk 7 is not complete.

The [IHP coil physical record](validation/ihp-inductor-physical-2026-10-19.json)
adds both public coil interfaces without inventing electrical models. Eight
rotated layouts pass full native DRC/LVS and all 28 deliberate faults are
detected, including a turn short missed by public extraction alone. Independent
readback covers 44 native/comparison netlists and 156 export layer pairs. Sixty-one
focused tests and both source editor checks pass per host, nine Windows backend
cases verify 486 received files, and six prior native device cases pass. The
compact archive restores and replays successfully. Electrical coil models,
complete operating envelopes, other outstanding families and installed-release
acceptance remain open; chunk 7 is not complete. See the
[physical interface scope](IHP_INDUCTOR_QUALIFICATION.md).

The [RF transient record](validation/sky130-rf-transient-2026-10-19.json) adds
independent nonlinear reverse-pulse integration and native timestep convergence.
Each host passes 180 valid simulations across 90 conditions and detects all 270
model faults. Both full local suites pass 3,135 discovered tests with explicit
platform skips; the ten new RF tests pass separately. Fresh hosted inverter,
public-layout and interoperability checks pass at `e912509`; remaining hosted
and installed-release acceptance are tracked separately. These results extend
the public candidates' tested scope; they do not complete chunk 7.

The [October 19 RF and CI record](validation/chunk7-ci-rf-bias-2026-10-19.json)
adds reverse-bias DC, complex admittance and noise checks for both public RF
candidates. Each host passes 90 valid cases and rejects 270 model faults across
three corners, three temperatures, five geometries and seven bias visits.
Independent readback verifies 15,120 raw files and cross-host agreement. The
record also repairs the RF menu mapping, Windows path-identity assertions and
the handling of Magic's exact repeated-boundary warning. The affected physical
CI jobs now select a pinned simulator with measured diode behavior. Remaining
physical families, operating envelopes, unavailable models and installed-release
acceptance still prevent chunk 7 completion; the default catalog is unchanged.

The [RF n-well physical record](validation/sky130-rf-nwell-layout-2026-10-18.json)
closes the earlier prototype gap for one rectangular ps2nw junction. Twenty-four
rotated layouts pass native public DRC, written-contact proof, unfiltered device
extraction and strict polarity/geometry comparison; all 102 faults are rejected.
Independent readback verifies all native dimensions and 648 mask comparisons.
Both source desktops, eight Windows backend cases, 107 regressions per host and
archive restoration/replay pass. RF p-well, complete operating envelopes, remaining
models and installed-release acceptance remain open. No default device is promoted;
chunk 7 is still incomplete.

The [RF include follow-up](validation/sky130-rf-includes-2026-10-18.json) closes
the nested-library runtime-detection gap. Both hosts reproduce explicit-call
currents through two wrapper routes and reject incompatible engines before
circuit execution. Affected 146-test suites pass with platform skips; archive
recovery reproduces both circuits and twelve guard tests. The separate RF
n-well layout prototype remains an unaccepted investigation. No default device
is promoted and chunk 7 remains incomplete.

The [public RF runtime record](validation/sky130-rf-runtime-2026-10-18.json) adds
automatic simulator rejection and reproducible public candidates for two SKY130
RF diodes. Each host passes 90 valid and 270 deliberately faulty thermal/corner/
geometry cases. Independent readback verifies 1,440 raw files and identical
51,120 current samples across hosts. Portable application and preserved-program
checks pass, including actual incompatible-engine rejection on all three routes.
The [RF guide](SKY130_RF_DIODE_QUALIFICATION.md) keeps physical extraction, wider
operating envelopes and default promotion explicitly open. Chunk 7 is incomplete.

The [Windows runtime and RF candidate record](validation/windows-simulation-and-rf-2026-10-18.json)
replaces the reproduced repeated-diode-analysis defect with the verified official
Windows ngspice 46 runtime. All executed checks in the 3,107-test Windows suite
pass; subsequent focused tests cover the real long-path PDK installation fix.
Both source desktops pass the GF180 menu repair. Separate public RF derivatives
pass independent branch calculations and selected application checks on both
hosts, but remain outside the default catalog pending runtime enforcement and
physical/envelope qualification. The [guide](WINDOWS_SIMULATION_QUALIFICATION.md)
records the exact boundaries. Chunk 7 remains in progress.

The latest [physical integration record](validation/gf180-high-voltage-layouts-2026-10-18.json)
also records the repaired IHP tap editor check. Hosted Linux failed because it
asserted the pre-NPN default revision; the same failure is reproduced locally.
The corrected check verifies the current source-locked default and passes on
Windows and Linux without relaxing any placement, resistance or saved-project
assertions. Hosted acceptance of this correction remains pending.

The [GF180 high-voltage physical record](validation/gf180-high-voltage-layouts-2026-10-18.json)
adds a local verification route that preserves asymmetric drain/source identity
and rejects broken body wiring. Forty layouts and all 182 fault controls pass;
independent raw-mask/netlist audits, sixteen prior-device regressions, both source
editors and eight actual Windows backend cases pass. Both full suites pass all
executed tests out of 3,100 discovered, with explicit platform skips. A verified
archive restore repeats native success and failure cases. The
[guide](GF180_HIGH_VOLTAGE_QUALIFICATION.md) identifies every local public-rule
correction and its limits. The earlier default IHP NPN integration gap is also
closed by its [record](validation/ihp-npn-default-2026-10-18.json). Seven real model
entries remain unavailable; broader family/envelope and installed-release gates
still prevent completion of chunk 7.


The [IHP tap-layout record](validation/ihp-tap-layouts-2026-10-18.json) closes
the earlier sampled tap LVS gap with source-checked public area/perimeter
conversion and strict terminal roles. Twenty layouts and two public-format
references pass, and all forty physical and eight reference faults are detected.
The controls exposed native false passes for undersized contacts; the application
now checks their written masks against the locked 160 nm public minimum as well
as retaining full native DRC. Independent netlist and mask audits, both source
desktop actions and six actual Windows backend cases pass. Seven other device
layouts and three NPN layouts also pass with their separately recorded package
identities. Complete ranges, default-package NPN integration, remaining families
and installed-release acceptance remain open.

The [GF180 high-voltage record](validation/gf180-high-voltage-2026-10-18.json)
restores a public library already identified by the original source lock.
Both asymmetric 10 V devices now have explicit four-terminal bindings in C/D,
documented geometry limits and single-finger enforcement. The full Linux batch
passes 160 DC/AC comparisons and 2,240 device faults; native Windows nominal
checks add eight comparisons and 112 faults. Independent raw readback verifies
all 504 files. The [guide](GF180_HIGH_VOLTAGE_QUALIFICATION.md) explains the
public model's M behavior and remaining physical, transient/noise, range and
installed-release requirements. The current catalog has 286 usable entries;
availability does not establish complete device qualification.

The [CI repair record](validation/ci-repair-2026-10-18.json) reproduces and fixes
the historical SKY130 package mismatch that stopped all nine hosted physical
stages and Linux packaged acceptance. The unchanged locked packages rebuild
exactly on both hosts; 68 fast CI tests per host and real inverter, boundary and
bipolar checks pass locally. All nine hosted physical stages and the dependent
detector desktop check and Linux release job now pass at commit `957055a`.
The Windows release job exposed one encoding-sensitive test fixture: its
default CP1252 write was incompatible with the application's UTF-8 netlist
reader. That failure is reproduced locally; explicit UTF-8 fixture writes
pass all four real saved-bias checks with Windows UTF-8 mode disabled. An early
hosted regression now exercises that configuration. Completed hosted acceptance
of the repaired Windows release remains pending. The earlier Windows runner
disconnection is not attributed to either repair. These results do not complete
chunk 7.

The [IHP tap record](validation/ihp-taps-2026-10-18.json) enables both public
tap symbols while preserving their source bytes and saved package revisions.
The editor keeps resistance calculated from width and length. Fifty independent
electrical comparisons pass; all 200 faulty device instances are detected and
120 raw outputs independently audited. Both source editors and the Windows
backend route pass. The original tap layout probe passed full DRC but failed
strict LVS; that failure is retained alongside the subsequent physical record
above. The [tap guide](IHP_TAP_QUALIFICATION.md) records both sets of tested points
and the remaining limits.

The [IHP thermal record](validation/ihp-thermal-2026-10-17.json) adds nine
selected conditions for all three five-terminal NPN families, with separate
final-source and managed-engine nominal regressions. All 66 independent
comparisons and 220 fault controls pass; 121 raw outputs are audited. Windows
source staging verifies 153 returned files, and both source desktops and 16
focused tests per host pass. The [thermal guide](IHP_THERMAL_QUALIFICATION.md)
records the corrected terminal labels and live symbol parameters, along with
retained sharp-edge and cross-engine comparison failures. Complete operating
ranges, remaining devices and final installed acceptance remain open.

The [SKY130 resistor record](validation/sky130-li-metal-resistors-2026-10-17.json)
resolves the unavailable LI binding using the existing documented model. The new
default retains all original assets and saved-project revisions. Both hosts pass
72 electrical analysis comparisons and detect 864 faulted instances; independent
raw readback also verifies analytical RC and noise behavior. Five LI/metal families
pass 60 native layouts and all 150 faults, with 210 extracted netlists audited.
Source-desktop checks, 31 focused and 29 package/matrix tests per host pass. The
[resistor guide](SKY130_METAL_RESISTOR_QUALIFICATION.md) separates electrical test
points from legal physical geometry and records the retained failures. Complete
operating ranges, other required devices and installed acceptance remain open.

The [IHP NPN-layout record](validation/ihp-npn-layouts-2026-10-17.json) adds
36 layouts across all three four-terminal NPN families, with all 99 deliberate
faults detected. Exact emitter/count audits, 54 independent rule-geometry checks,
31 focused tests per host, PNP regressions and staged-backend receipt pass.
The separately versioned package corrects disconnected-component traversal;
the optional extractor preserves orientation and emitter count. Five-terminal
thermal behavior, continuous operating envelopes, other device-family coverage,
unavailable required models and installed acceptance remain open.

The [IHP bipolar-layout record](validation/ihp-bipolar-layouts-2026-10-17.json)
adds ten sampled PNP layouts and 35 detected physical/reference faults. An
explicit public KLayout extraction option resolves the larger-PNP recognition
gap while retaining full Magic DRC and strict Netgen comparison. Unfiltered
native output, exact geometry, every mask and the desktop/backend route are
checked; empty circuits cannot pass. The [bipolar guide](IHP_BIPOLAR_LAYOUT_QUALIFICATION.md)
records the separate source license, retained failures and remaining NPN/HBT,
operating-envelope, other-family and installed-release requirements.

The [diode-layout record](validation/diode-layouts-2026-10-17.json) adds 100
native full-DRC/strict-LVS layouts for two IHP and four GF180 diode families on
each C/D variant. All 300 intentional faults are detected, and an independent
audit checks 400 extracted netlists and all mask changes. The application now
uses the native writer that preserves correct diode perimeter units. Fourteen
representative MOS/resistor/MIM layouts and 29 focused tests per host pass after
that change. The [diode guide](DIODE_LAYOUT_QUALIFICATION.md) records exact
settings and retained failures. Wider operating ranges, other device families,
statistical/RF behavior and installed acceptance still prevent chunk 7 completion.

The [resistor-layout record](validation/resistor-layouts-2026-10-17.json)
adds 190 selected native full-DRC/strict-LVS layouts: three IHP resistor families
and eight families on each GF180 C/D variant, at five W/L pairs and two rotations.
All 475 physical/reference fault controls are detected. Independent readback
checks every mask, exact extracted model/body/terminals/dimensions and all fault
changes. The [layout guide](RESISTOR_LAYOUT_QUALIFICATION.md) documents the public
generator settings, retained original failures and exact scope. Broader device
families, operating envelopes, statistical/RF behavior and installed acceptance
remain open; these samples do not complete chunk 7.

The [alternate-model record](validation/alternate-models-2026-10-17.json)
accounts for all 52 choices declared by bundled source symbols: five existing
defaults, 44 added usable views and three explicit missing-model entries. The
accepted 170 cases pass independent terminal comparisons and detect all 10,128
faulted instances. All 680 raw files are independently re-read; 48 focused tests
pass on each host. New defaults reproduce exactly and preserve saved revisions.
The [model-choice guide](ALTERNATE_MODEL_QUALIFICATION.md) records the selected
conditions and the corrected simulator-dependent diode area behavior. Broader
upstream models, operating envelopes, physical/extracted connectivity,
statistical/RF behavior and installed-release acceptance remain open.

The latest [physical MOS boundary record](validation/mos-physical-boundaries-2026-10-17.json)
adds 72 layouts across GF180 C/D and IHP, each passing native full DRC and strict
LVS at the recorded published geometry points. All 504 deliberate size, contact
and short faults are detected. The generators now support narrow contact
landings and lengths through 10 micrometres. A regression correction preserves
body-tap shape identity when resizing between narrow and wide devices; save/reopen
checks cover that transition. All 72 focused tests pass on both hosts. The
[boundary guide](MOS_BOUNDARY_QUALIFICATION.md) records the exact scope; other
device-family layouts, alternate models, full operating envelopes, statistical/RF
coverage and installed-runtime acceptance still prevent chunk 7 completion.

The earlier [standard MOS boundary record](validation/mos-boundaries-2026-10-17.json)
adds 378 passing condition cases across Windows and Linux/WSL for eight standard
MOS views in SKY130A, GF180 C/D and IHP. It checks 67,392 terminal-current vectors
and detects all 33,696 deliberately faulted device instances. Independent raw
readback verifies all 1,512 simulator output files. Seventeen focused regression
tests pass on each host. The [boundary guide](MOS_BOUNDARY_QUALIFICATION.md)
distinguishes published limits and characterization points from selected biases
and temperatures. The exact sources, decks and raw outputs are retained in a
verified 159 MB archive. This expands sampled electrical coverage; complete
operating envelopes, other variants, statistical/RF behavior, broader physical
connectivity and final installed-runtime acceptance remain open.

The earlier [fixed-geometry and model inventory record](validation/fixed-geometry-and-model-inventory-2026-10-17.json)
closes the editable SKY130 20 V geometry defect for all seven views. Both hosts
pass 54 selected electrical cases and 252 deliberate device faults, and the
editor prevents ineffective geometry edits. The bundled source inventory now
accounts for 6,402 SPICE definition occurrences, 52 alternate declarations and
nine IHP Verilog-A declarations covering all six referenced external types.
All 235 usable catalog interfaces pass on both hosts. The final Linux full
suite discovers 2,979 tests and passes with 15 skips; the Windows run's 37 sandbox-blocked
tests all pass with local access restored, while its original failed outcome
and 36 skips remain recorded. Three additional inventory tests pass separately.
Complete operating envelopes, alternate-model adapters and execution, broader
physical/extracted connectivity, full upstream coverage and exact installed
release acceptance still prevent completion of chunk 7.

The subsequent [artifact-path correction](validation/artifact-path-portability-2026-10-17.json)
resolves inconsistent Windows short/full directory names in verification-file
capture. All 15 failures from the earlier Windows release build pass on both
hosts. Focused workflow/export regressions pass 40 tests on Windows (five
unavailable-engine skips) and 42 on Linux (three Windows-only skips), with
seven additional Windows alias/long-path checks passing. The full-suite results
above predate this correction; final-head CI and installer acceptance remain open.

The earlier [default-package integration](validation/default-device-packages-2026-10-17.json)
puts the reviewed capacitor, MOS and isolation corrections into new SKY130,
GF180 C/D and IHP projects while preserving saved revisions. All 62 fresh
electrical cases and nine isolation cases pass, with 740 deliberately faulted
device instances detected. All 235 usable catalog entries pass save/reopen,
netlist and export checks on both hosts; the 20 unavailable entries are
separately checked for expected rejection. Thirty standard GF180/IHP transistor
layouts and twelve IHP MIM layouts pass native full DRC and strict LVS, with
93 physical faults detected. Both 2,963-test regression runs exposed one
ordering-sensitive test assertion; the corrected test and related cases pass
18 focused checks per host. Original full-run failures and skips remain recorded.
Complete operating envelopes, broader physical coverage, alternate models and
installed-runtime acceptance still prevent completion of chunk 7.

The latest [MOS variant batch](validation/mos-variants-2026-10-17.json) covers
all 86 placeable MOS/clamp catalog views, including hidden-body, native-threshold,
high-voltage, isolated and RF variants. Its 324 selected condition cases pass
33,516 independently re-read terminal vectors (1,100,376 samples), with all
3,096 deliberately faulted instances detected. Nine additional IHP RF cases
detect disabled RF mode in 72 instances. Source-backed corrections fix the
GF180 native-model selection and IHP clamp supply order; new registrations
apply those fixes, and explicit packages preserve the original asset bytes.
Twenty-six focused tests pass on each host. The broader operating envelopes,
physical coverage, complete operating envelopes and installed-runtime acceptance
remain required. The newer source inventory and defaults are recorded above.

The [completed MOS sweeps](validation/standard-mos-sweeps-2026-10-16.json)
add 432 cases across six selected geometries, three process corners and
0/27/85 C for the eight standard NMOS/PMOS entries. All 1,728 independent
DC/AC/transient/noise comparisons pass, as do 432 Xschem round trips; all
432 deliberately wrong-width simulations are detected. Another 36 corner
and temperature cases exercise separate drain and body biases: 2,592 terminal
current vectors agree with independently written decks, and all 108 pin-swap,
body-connection and wrong-model controls are detected. Four new comparator
fault tests pass on Windows and Linux.

Fresh execution of the bounded SKY130 recipes passes 20 legal layouts and
five deliberate physical faults, including finger/multiplicity cases. Ten
resistor/capacitor layouts pass schematic/extracted/independent admittance
comparisons under three selected conditions each. Every raw run, model input
and source identity is retained in a verified 176 MB content-addressed archive.
These results validate application integration using the same public models;
they do not establish accuracy against measured silicon or a complete model
operating envelope. Results retain their original package revisions.

The [passive-device record](validation/standard-passives-2026-10-16.json)
adds 16 resistor/MIM catalog entries across the four process variants. All
72 selected corner/temperature/bias cases pass: 1,728 complex admittance
vectors over 100 Hzâ€“10 MHz, with 3,456 deliberately faulted device instances
detected in 144 isolated fault simulations. A separate audit proves three-copy
parallel scaling for 1,728 application/reference pairs. These are selected
AC integration tests, not complete device operating ranges or measured-silicon
validation.

The pilot exposed a GF180 catalog integration defect: legacy MIM symbols called
models absent from the active corner selection. Newly registered and bundled
C/D packages now also select the existing `cap_mim` section. All upstream
asset bytes and catalog mappings remain unchanged. The new package revisions
are `a6aa4319ebe9cbc9` (C) and `b2daff2da0a120b4` (D); fresh MOS regression
comparisons pass under those revisions. Historical GF180 fill evidence retains
its exact earlier importer source and does not become a new physical acceptance
run. All 53 focused regression tests pass on Windows and native Linux.

The [device-correction record](validation/device-corrections-2026-10-16.json)
extends resistor execution to 53 catalog entries. Combining the passing GF180
C/D and IHP runs with a separately versioned SKY130 correction gives 72 passing
condition cases, 3,816 complex response vectors and 7,632 detected device faults.
Seven SKY130 polysilicon models needed explicit propagation of their parallel
factor through nested calls. A separate 2,880-vector audit proves corrected
results agree with the untouched single-device models and their three-copy
responses. A corrected ngspice 47 pilot also passes; the complete sweep uses
the pinned ngspice 42 runtime. Noise, mismatch and full operating envelopes
remain open.

The included SKY130 metadata now correctly emits four metal resistors as `R`
devices and two default primitive diodes as `D` devices, retaining every upstream
asset byte. Nine diode corner/temperature cases pass independent DC comparison
and polarity/area fault detection. All 255 catalog interface checks pass on
Windows and Linux, with 21 explicitly unavailable entries still unavailable.
Seventy-eight focused regression tests pass on each host, and fresh standard
SKY130 NMOS/PMOS regressions pass under the new metadata revision.

The IHP `cap_cmim` failure is resolved for the tested layouts with a separate
versioned correction to the public Magic deck. Fresh temporary CIF planes avoid
the observed connectivity-traversal interference; the rule and 600 nm limit are
unchanged. Twelve layouts pass full native DRC and strict LVS, three physical
faults are detected, and native/independent spacing checks agree at 595/600/605
nm. The boundary controls retain unrelated DRC findings and are not declared
fully clean. The initial failures and diagnostic variants remain archived.

The [bipolar record](validation/bipolar-families-2026-10-16.json) adds all 29
bundled bipolar symbols at 144 selected DC condition cases, with 3,744 terminal
current vectors, current-conservation checks and 2,052 detected device faults.
The SKY130 package requires exact public NPN corner definitions missing from
its original include closure. The IHP sweep uses a separately built ngspice 47
binary; three hot NPN cases fail with the default ngspice 42 runtime. A strict
cross-version audit retains numerical differences in 12 other cases. These are
engine-specific integration results, not interchangeable-runtime or complete
device qualification. Five additional focused tests pass on both hosts.

The [default-package integration](validation/default-device-packages-2026-10-16.json)
now includes the tested corrections in fresh SKY130 and IHP projects. The new
SKY130 package retains all original corner selections and adds NPN t/s/f only
inside tt/ss/ff. Its 36 bipolar and 18 resistor cases pass. The exact previously
tested IHP package passes 12 full-DRC/strict-LVS layouts, six physical controls
and 36 candidate-runtime bipolar cases. All 255 Linux catalog checks and 25
focused tests per host pass; two Windows MOS cases pass eight analyses and
two deliberate width faults. Original package reconstruction and saved-project
revision retention are tested. The initial missing-library source snapshot and
missing Windows engine invocation remain recorded failures.

The [runtime regression](validation/runtime-device-regression-2026-10-16.json)
adds a public ngspice 47 build recipe, relocated model-loading tests and selected
production-binary MOS, diode and bipolar regressions. All 432 standard-MOS cases
pass the diagnostic build, as do 72 passive cases. Twenty-five additional diode
entries pass 36 corner/temperature cases, 990 terminal-current vectors and 900
deliberate device faults. The complete runtime image and installed release
acceptance remain open; the local Docker startup failure is recorded.

The [IHP isolation-box record](validation/ihp-isolation-interface-2026-10-16.json)
adds a separate package and fresh-import support for the public `sub!` terminal.
Mathematical domain guards reject nonpositive inner model dimensions without
claiming foundry geometry limits. Nine DC cases pass 54 terminal-current vectors,
5,454 samples and 36 deliberate faults. The existing 25-entry diode suite still
passes, and eleven focused tests pass on each host. This record predates promotion of the isolation
entry into the current defaults; its wider qualification limits remain open.

The [GF180 bandgap connectivity record](validation/gf180-bandgap-connectivity-2026-10-16.json)
passes all twelve required physical exchange and fault-control checks for the
declared four-metal/MIM-B reference. Strict native LVS is paired with an
independent written-metal graph covering 293 device terminals, three ports and
64 body contacts. This detects opens that substrate joins alone can hide.
The filled candidate passes full public DRC/antenna/density and connectivity;
the original unfilled core retains its expected density failures. Missing fills,
removed vias, individual ground/contact opens and a power short are rejected.
Distributed RC, fill coupling, other physical stacks and full device coverage
remain unqualified.

The [primitive source inventory](validation/primitive-symbol-inventory-2026-10-16.json)
reconciles all 255 catalog entries with their complete pinned primitive-symbol
views: 74 SKY130A, 68 each GF180 C/D and 45 IHP. No symbols are missing, added or
changed. Every Git directory object is reconstructed against the pinned root
identity; the complete SKY130 source archive is hash-verified and streamed.
Windows and Linux produce identical reports and pass four omission/tampering
regression tests each. This closes primitive-symbol source coverage only;
model-only devices, other tool views and process options remain separate work.

The [capacitor-family record](validation/capacitor-families-2026-10-17.json)
adds 37 catalog entries at 180 selected terminal-drive, bias, corner and
temperature cases. Independent raw readback verifies 12,888 complex response
vectors, 1,332 parallel-device comparisons and 5,328 detected device faults.
A source-authenticated ngspice capacitor-parser correction passes analytical
checks; a separate SKY130 package defines parallel unit varactors explicitly.
Original models, default packages and failed experiments remain preserved.
These results do not qualify full operating envelopes, RF or silicon accuracy,
remaining physical layouts, or the complete installed runtime.

The [four-terminal capacitor record](validation/four-terminal-capacitors-2026-10-17.json)
adds 144 cases for the default SKY130 VPP and IHP SVaricap. It detects and
corrects swapped substrate/shield and gate connections in separate explicit
packages, then independently re-reads 1,728 complex vectors and 864 detected
device faults. All 39 currently placeable capacitor catalog entries now have
selected electrical integration checks. Full ranges, other model variants,
physical/extracted behavior and default promotion remain open.

The [release regression record](validation/chunk7-release-regressions-2026-10-17.json)
retains passing full application suites on Windows and Linux: 2,954 discovered
tests on each host, with 36 and 31 explicit skips respectively. The corrected
simulator also passes eight standard-MOS cases, 32 independent analyses and
eight deliberate width faults. Earlier environment failures and GitHub desktop
diagnostics are retained. These source tests do not replace complete image,
installer or optional-engine acceptance.

The [adapter instructions](DEVICE_ADAPTER_QUALIFICATION.md) reproduce current and
earlier packages. Full simulator release integration, upstream completeness,
operating envelopes, remaining device families and physical coverage remain
chunk-7 work. Chunk 7 remains open.

### Earlier initial checkpoint

The [initial MOS and catalog record](validation/standard-mos-initial-2026-10-16.json)
retains fresh local execution without completing the device-family gate. All
255 bundled entries are exercised independently on Windows and Linux: the 234
placeable entries preserve model identity, terminals and parameters through
save/reopen and Studio Xschem exchange at two orientations. The 21 unavailable
entries reject placement with their recorded reasons. Malformed parameters and
missing/wrong-revision models are rejected. These tests compare with the locked
catalog; independent upstream interface reconciliation is still required.

The eight standard NMOS/PMOS entries across SKY130, GF180 C/D and IHP pass
32 independent nominal DC, AC, transient and noise comparisons, including AC
phase, plus eight deliberately wrong-width simulations. Forty generated legal
layouts pass native full DRC and strict LVS against independently written
device calls. All 120 wrong-length, drain-open and gate/drain-short controls
fail native connectivity or size checks. The corrected length control measures
poly/diffusion overlap; the initial SKY130 contact-pad selection failure is
preserved in the archive. Thirteen focused fault/comparison tests pass on each
host. No application or upstream PDK source was changed for this checkpoint.

The [test-envelope review](qualification/standard-mos-test-envelope-v1.json)
separates published model facts from selected test points and application layout
bounds. Complete bias, temperature, reliability, geometry and process-corner
coverage remains open, as do the other device families. SKY130 simulation and
physical adapters retain their distinct source revisions. The 432-case sweep
is now recorded separately above; the initial record remains unchanged.
Chunks 8â€“12 remain pending and retain their original gates.

## Earlier checkpoints under the previous completion standard

The following entries retain the status and scope of their original executions.

The [mandatory density gate](validation/sky130-density-gate-2026-10-16.json)
checks every new SKY130 HD Finish independently of the fill-generation setting.
Failed full windows stop Finish and retain their measurements. Export remeasures
the final layout and refuses missing or altered evidence. Small blocks remain
explicitly dependent on surrounding layout. This closes an application bypass;
it does not resolve missing process definitions or complete chunk 6.

The [application connectivity integration](validation/sky130-application-lvs-2026-10-16.json)
makes strict transistor, diode, body and port LVS mandatory for newly prepared
SKY130 HD Finish jobs and binds the evidence to portable exports. Both reviewed
library revisions are tested independently. Physical fault and altered-evidence
controls prevent missing or failed connectivity from becoming a success. The
extraction source and diode resources retain their BSD and Apache terms.
The remaining applicability, pin-spacing and density definitions still prevent
a complete chunk-6 claim.

The [generic fill and connectivity execution](validation/sky130-generic-density-2026-10-16.json)
adds local metal fill to normal Finish, independent database/GDS agreement,
fill-aware LEF obstructions and portable evidence. A fresh 840 Âµm reference with
381,362 fill rectangles passes nine full windows under each public oxide-density
profile. Its unfilled control fails both profiles. Strict MOS/diode/body/port LVS
passes on the exact filled large layout and rejects a removed-diode fault;
custom NMOS/PMOS controls also pass native full DRC/LVS and reject width faults.
Small macros retain an explicit surrounding-layout requirement. Complete profile
applicability, final-mask/boundary density and fill coupling are not qualified;
the historical 302 catalog records retain their status. Chunk 6 is still partial.

The [generic native integration](validation/sky130-generic-native-2026-10-16.json)
adds the pinned public geometry deck to normal Finish and preserves its exact
evidence in macro export. Three reference layouts and a fresh counter Finish
pass. Twelve controls cover process metal, contacts, grid, width and nonempty
NMOS/PMOS geometry; Studio's independent implant checks detect two faults missed
by the public native deck. Density context and full profile applicability still
need qualification. The 302 unresolved historical catalog records are unchanged.

The preceding [public oxide-density audit](validation/sky130-oxide-audit-2026-10-15.json)
adds two explicitly identified Apache-licensed public density profiles, exact
integer-area measurements and inclusive 700/70 um windows. All 411 tests per OS,
27 identical control layouts/reports, three fresh application runs and Windows
exports pass. Independent upstream runs expose endpoint omissions and boundary
area discrepancies, retained and explained by rectangle arithmetic. APB has
21/10 clipped-window findings under the two profiles; counter/UART have zero.
All three blocks are smaller than 700 um, so none obtains full-window acceptance.
**The catalog remains at 302 unresolved records and chunk 6 remains open.**
Only resources compatible with the project's GPL license are incorporated.

The preceding [public alignment audit](validation/sky130-alignment-audit-2026-10-15.json)
adds nonempty integrity checks for all 31 mask purposes at the four corners of
the exact public seal template. All 394 tests per OS, 146 identical control
layouts/reports, three Linux application runs and Windows export replays pass.
It also detects 5 nm gaps in a retained output of the public seal generator.
**The catalog remains at 302 unresolved records.** The public alignment shapes
are now retained, but all 56 associated records still need authoritative
final-mask and complete-chip/scribe placement policy. The reference blocks do
not supply that context. No requirement is waived and chunk 6 remains open.

The preceding [dummy-FOM partner audit](validation/sky130-dummy-partner-audit-2026-10-15.json)
resolves **five additional binary records: 307 to 302 unresolved** through
independently defined empty seal, fuse and die-cut operands. It does not
construct dummy FOM or waive enclosure. All 378 tests per OS, 19 controls, six
incremental catalogs, three Linux application runs and Windows exports pass.
Current counts are **441 executed, 715 absent, 90 W/L exemptions, eight advisory
and 302 unresolved**. The [source dependencies](validation/sky130-source-dependencies-2026-10-15.json)
map every remaining record into 17 groups and retain pin-spacing and density
as independent obligations. No private foundry package is available. Missing
definitions remain open; full chunk 6 completion cannot be claimed from the
current source set.

The preceding [die-cut and density audit](validation/sky130-diecut-density-audit-2026-10-15.json)
resolves **18 additional spacing records: 325 to 307 unresolved**, through an
empty published die-cut operand. Enclosure remains open. The new density kernel
evaluates all six required waffle-drop predicates per metal on explicit full
windows, with 72 nonempty threshold controls. It does not qualify window/cell
policy or generated final-mask operands; required density remains incomplete.
All 365 tests per OS, 86 controls, six incremental catalogs, three application
runs and Windows exports pass. Counts at that checkpoint were **441 executed, 710 absent,
90 explicit W/L exemptions, eight advisory and 307 unresolved**. Test cases and
numerical observations do not count as additional completed reference records.

The preceding [module-operand audit](validation/sky130-module-operand-audit-2026-10-15.json)
resolves **35 additional records: 360 to 325 unresolved**. Thirty-four spacing
and one overlap requirement have an independently bound, empty module operand.
The unknown other operands are not inferred, and enclosure companions remain
open. All 330 tests per OS, 14 new cross-system controls, six incremental
catalogs, three application runs and Windows exports pass. Counts at that checkpoint were
**441 executed, 692 absent, 90 explicit W/L exemptions, eight advisory and 325
unresolved**. Together with the preceding three numerical width bounds, this
resolves 38 records from the 363-record checkpoint. Required density, pin spacing,
generated operands and remaining device/chip context keep chunk 6 incomplete.

The preceding [metal-width audit](validation/sky130-metal-width-audit-2026-10-15.json)
resolves **three additional numerical records: 363 to 360 unresolved**. Stronger
global bounds on merged drawn-plus-fill metal prove the three under-pad maximum
widths. Failed sufficient bounds and alternate purposes remain unresolved.
All 316 tests per OS, 32 cross-system controls, three application runs and Windows
exports pass. Six incremental catalogs authenticate unchanged prior evidence and
freshly execute the new checks; they do not rerun every previous catalog checker.
Counts at that checkpoint were **441 executed, 657 absent, 90 explicit W/L exemptions, eight
advisory and 360 unresolved**. The [remaining-work table](SKY130_PHYSICAL_QUALIFICATION.md#remaining-chunk-6-work-at-this-checkpoint)
keeps required definitions, context, pin spacing and density work in chunk 6.

The preceding [family and package audit](validation/sky130-family-package-audit-2026-10-15.json)
resolves **43 additional records per corrected reference: 406 to 363 unresolved**.
Thirty-five low-Vt RF and three explicit bondpad targets are absent under required
drawing, mask/edit and intent guards. Five package-layer module-crossing checks
are implemented from the authenticated installed layer map; their reference
targets are also absent. These are 43 absence decisions, not 43 numerical passes
on present devices. All 286 tests per OS, 29 retained examples, six complete
catalog replays, three application runs and Windows exports pass. Counts at that checkpoint
were **438 executed, 657 absent, 90 explicit W/L exemptions, eight advisory and
363 unresolved**. Remaining RF selectors, generated masks, grid purposes,
module/frame/pad context, pin spacing and required density keep chunk 6 open.

The preceding [seal geometry audit](validation/sky130-seal-geometry-audit-2026-10-15.json)
requires the drawn seal's lower-left corner at the origin and its minimum width
of 6 Âµm. Nonempty rings, 1 nm failures, hierarchy and ambiguous markers are
tested. All 265 tests per OS, 19 cross-system examples, six full-catalog replays,
three application runs and Windows exports pass. Reference seal targets are
absent; no complete-chip seal qualification is claimed. Current counts are
**438 executed, 614 absent, 90 explicit W/L exemptions, eight advisory and 406
unresolved records**. The [remaining-work table](SKY130_PHYSICAL_QUALIFICATION.md#remaining-chunk-6-work-at-this-checkpoint)
keeps source and boundary dependencies explicit. Chunk 6 remains incomplete.

The preceding [scribe-size audit](validation/sky130-scribe-bound-audit-2026-10-15.json)
executes fourteen global size bounds on nonempty drawn-layer geometry. Every
merged feature has a bounding-box side below 10 Âµm, excluding the restricted
10-by-10 Âµm feature anywhere without inventing junction locations. Larger
candidates remain unresolved. All 248 tests per OS, 27 cross-system examples,
six full catalog replays, three application runs and Windows exports pass.
Complete corrected catalogs now have **438 executed, 612 absent, 90 explicit
W/L exemptions, eight advisory and 408 unresolved records** per reference.
The fourteen mask companions and missing frame/junction context stay open,
alongside the other generated-mask, RF, grid, pad, pin-spacing and density work.
Chunk 6 remains incomplete; no PDK is qualified for complete-chip tapeout.

The preceding [well-bound audit](validation/sky130-well-bound-audit-2026-10-15.json)
implements three numerical checks for drawn PWDE enclosure, PWBM hole spacing
and PWBM enclosure. Exact limits, 1 nm failures, nested holes, missing enclosures
and hierarchy are tested. All 230 tests per OS, 23 cross-system geometry examples,
six full catalog replays, three application runs and Windows exports pass.
The three reference targets are absent, reducing the complete corrected catalog
from 425 to **422 unresolved records**. Its other counts are 424 executed, 612
absent, 90 explicit W/L exemptions and eight advisory records. The eighteen frame
bounds still require missing chip-boundary context. Generated-mask, RF, grid,
module/frame/pad, pin-spacing and required density work remains; chunk 6 is
incomplete and no PDK is qualified for complete-chip tapeout.

The preceding [frame-bound audit](validation/sky130-frame-bound-audit-2026-10-15.json)
implements eighteen numerical sufficient bounds for drawn-layer frame enclosure
and die-cut spacing. Exact 3 Âµm margins and 1 nm failures are tested on all nine
layers. Missing context and failed conservative bounds remain unreviewed; no
blanking or named-cell exemption is inferred. All 212 tests per OS, 36 cross-system
controls, fresh frame measurements, three application runs and Windows exports
pass. The reference blocks lack frame/die-cut markers, so all eighteen requirements
stay unreviewed and the retained full catalog remains at 425 unresolved records.
This advances nonempty checker implementation without promoting unsupported
reference coverage. Chunk 6 remains incomplete.

The preceding [selected-target audit](validation/sky130-selected-target-audit-2026-10-15.json)
adds a required report for sixteen pad, inductor and implant targets to Finish
and saved-result/export validation. All sixteen are conservatively absent in
the references; nonempty requirements remain unreviewed. The corrected complete
catalog contains 424 executed bindings, 609 absent subjects, 90 W/L exemptions,
eight advisory and 425 unreviewed records. All six catalog replays, 194 tests
per OS, 57 cross-system controls, three application runs and Windows exports
pass. A pad-name false positive on APB address labels was fixed with retained
positive/negative controls; raw geometry guards are unchanged. Nonempty pad,
generated-mask, RF, grid/purpose, module/frame, pin-spacing and required density
coverage remains open. Chunk 6 is incomplete.

The preceding [corrected-export catalog replay](validation/sky130-delivery-catalog-audit-2026-10-15.json)
rebuilds every reviewed decision on the actual delivered counter, UART and APB
layouts. Each complete 1,556-record catalog contains 424 executed bindings, 593
absent subjects, 90 W/L exemptions, eight advisories and 441 unreviewed records.
All six Windows/Linux case replays pass with identical report bytes, and 74 tests
pass per OS. Export bytes are independently reproduced; retained native extraction
and nominal-voltage dependencies are authenticated and explicitly identified.
This reference command does not add full-catalog acceptance for arbitrary jobs.
Generated masks, RF selectors, grid/purpose, module/frame/pad context, pin spacing
and density remain unresolved. Chunk 6 is incomplete.

The preceding [special-subject audit](validation/sky130-special-subject-audit-2026-10-15.json)
resolves seven explicit UHV, deep-well, precision-resistor and nwell-hole records
through conservative subject absence. Raw masks/markers and device-name/label
hints prevent unsupported absence claims. A missing enclosing UHVI never waives
a present deep well. Nonempty selector differences and N/A values stay unresolved.
The new report is mandatory in Finish and saved-result/export validation.
All 163 focused tests pass per OS; twenty controls and fresh measurements agree
exactly. All three application runs and Windows exports pass. Original counts
are 416 executed, 593 absent, 90 W/L exemptions, eight advisory and 449 unreviewed.
Corrected streams retain 202 explicit catalog messages. Generated-mask, RF,
grid/purpose, frame/pad, pin-spacing and remaining density coverage stays open.
Chunk 6 is incomplete.

The preceding [physical-device-root audit](validation/sky130-device-root-audit-2026-10-15.json)
closes seven floating-net records. All 2,614 reference nets reach actual gate or
diffusion/tap geometry through the complete contact graph, without pin endpoints,
labels or standard-cell exemptions. Unrooted wires and unsupported selectors
stay unreviewed; a legal IP feedthrough is not automatically a foundry violation.
The new report is mandatory in Finish and saved-result/export validation.
All 147 focused tests pass per OS; sixteen controls and fresh reference
measurements agree exactly. All three application runs and Windows exports pass.
Original counts are 416 executed, 586 absent, 90 W/L exemptions, eight advisory
and 456 unreviewed. Corrected streams retain 195 explicit catalog messages.
Generated-mask, RF, grid/purpose, frame/pad, pin-spacing and remaining density
coverage stays open. Chunk 6 is incomplete.

The preceding [conservative-bound audit](validation/sky130-conservative-bound-audit-2026-10-15.json)
proves four catalog limits with stronger all-geometry width/spacing checks and
verifies eighteen explicit IP blockage subjects are absent. Failed sufficient
bounds and present blockages stay unreviewed. The new report is mandatory in
Finish and saved-result/export validation. All 128 focused tests pass per OS;
sixteen controls and fresh reference measurements agree exactly. All three
application runs and Windows export replays pass. Original counts are 409
executed, 586 absent, 90 W/L exemptions, eight advisory and 463 unreviewed.
Corrected streams retain 188 explicit catalog messages. Generated-mask, RF,
grid/purpose, frame/pad, pin-spacing and remaining density coverage stays open.
Chunk 6 is incomplete.

The preceding [selected-device audit](validation/sky130-selected-device-audit-2026-10-15.json)
adds 36 required device/implant records to Finish and saved-result validation.
Two checks execute numerical implant geometry; 34 family obligations require
both empty mandatory drawn purposes and no device-name/label hints to establish
absence. Present VPP, pwell-resistor and PNP candidates stay unreviewed. Eight
explicitly recommended source records are advisory, never numerical passes.
All 115 focused tests pass per OS; 17 retained controls and fresh reference
measurements agree exactly. All three application runs and Windows exports pass.
The original catalog now has 405 executed, 568 absent, 90 W/L exemptions, eight
advisory and 485 unreviewed records. Corrected streams retain 166 explicit
catalog messages. Required density, generated-mask, RF, grid/purpose, frame/pad
and pin-spacing coverage remains open. Chunk 6 is incomplete.

The preceding [boundary interaction audit](validation/sky130-boundary-interaction-audit-2026-10-15.json)
integrates 44 module-crossing and seal-overlap checks into Finish and saved-result
validation. Ninety-eight focused tests pass per OS; eleven retained controls
exercise nonempty failures for every selected check and match exactly across
systems. All three application runs and Windows export replays pass. The original
catalog has 405 executed, 532 absent, 90 W/L exemptions and 529 unreviewed records;
corrected streams retain 130 explicit catalog messages. The reference blocks have
no module-cut or seal markers. These interaction checks do not establish complete
chip boundaries or waive enclosure/spacing. Chunk 6 remains incomplete.

The preceding [VPP geometry audit](validation/sky130-vpp-geometry-audit-2026-10-15.json)
integrates numerical capacitor width, well-straddling and selected nwell-enclosure
checks into Finish and saved-result validation. Outside-nwell enclosure context
stays unreviewed. Eight nonempty controls, including 1 nm failures and exact density
boundaries, agree across both OSes; 84 focused tests pass on each system. All three
actual application runs and Windows exports pass. The references have no capacitor
targets; that original catalog checkpoint has 376 executed, 517 absent, 90 W/L exemptions
and 573 unreviewed records. Corrected streams retain 86 explicit catalog messages.
Density ratios remain measurements only, and chunk 6 remains incomplete.

The preceding [label-subject audit](validation/sky130-label-subject-audit-2026-10-15.json)
resolves 37 explicit label, named-cell and raw-target messages on both original
and corrected SKY130 references. The original-stream catalog now has 376 executed
bindings, 513 absent subjects, 90 W/L exemptions and 577 unreviewed entries.
Current Finish/export retains these 37 messages alongside the preceding 45-message
core/boundary context. Present targets stay unreviewed; this census does not
implement their numerical or connectivity checks. All three actual application
runs and Windows exports pass, 67 focused tests pass on each OS, and fresh
measurement reports agree exactly. Chunk 6 remains incomplete.

The preceding [core-context audit](validation/sky130-core-context-audit-2026-10-15.json)
resolves 37 explicit selected subjects on both original and corrected SKY130
references. That original-stream checkpoint has 376 executed bindings, 476 absent
subjects, 90 W/L exemptions and 614 unreviewed entries. Current Finish/export
separately validates a 45-message catalog context: those 37 subjects plus eight
boundary prohibitions. Present core/implant data stays unreviewed; numerical
memory-device checks and approval are not implied. All three actual application
checks and Windows export replays pass. Fifty-five tests pass on each OS, and
fresh measurement reports agree exactly. Chunk 6 remains incomplete.

The preceding [boundary export audit](validation/sky130-boundary-export-2026-10-15.json)
fixes a prohibited die-outline annotation in all three SKY130 output streams.
Only the single top-level box matching independent OpenDB die geometry is removed;
unexpected boundary data is rejected and all manufacturing geometry is preserved.
The six partial geometry profiles, thirteen antenna stages, OpenDB checks and
macro export pass on each corrected design. Thirty-five tests pass on each OS;
Windows reproduces identical corrected GDS and validates the exported bundles.
Eight literal boundary prohibitions are checked on those new streams. Earlier
catalog decisions retain their original file identities, and chunk 6 stays open.

The preceding [grid catalog audit](validation/sky130-grid-catalog-audit-2026-10-15.json)
resolves 105 exact vertex subjects: 20 nonempty drawn-layer checks pass the
published 5 nm drawn grid, and 85 subjects contain no raw shapes or texts.
The catalog now retains 376 executed bindings, 439 absent subjects, 90 explicit
standard-cell W/L exemptions and 651 unreviewed records. Twenty-two focused tests
pass on each OS without skips; the complete reports agree byte for byte.
Sixteen metop grid/angle aliases, the broader periphery unit/purpose semantics
and all seven text-anchor findings remain open. The complete grid diagnostic
retains FAIL; the periphery and application ledgers are unchanged.

The preceding [standard-cell audit](validation/sky130-standard-cell-wl-audit-2026-10-15.json)
binds 90 explicit W/L exceptions to the authenticated HD library and fresh
instance-level geometry on the three filled references. Five dummy-poly subjects
are absent. That checkpoint contains 356 executed bindings, 354 absent subjects,
90 explicit standard-cell W/L exemptions and 756 unreviewed entries. Twenty
focused tests pass on each OS without skips, and the complete reports agree.
RF recognition and all 60 RF fixed-layout dimension records remain open; the
exception does not establish their requirements or missing MRGA numeric limits.
The supplemental and application periphery ledgers remain unchanged. Chunk 6
is incomplete.

The preceding [local/HV audit](validation/sky130-local-hv-audit-2026-10-15.json)
resolves 29 explicit catalog subjects as absent on the exact three nominal
filled references. Coverage at that checkpoint was 356 executed, 349 absent and 851 unreviewed
catalog records. It also reopens the unsupported `pad.3` exemption: C3 uses a
mask-derived hugePad subject, while the earlier witness measured drawn pads.
The supplemental periphery ledger has ten execution reviews plus the undefined
`x.20` threshold. Current Finish/export retain that pending rule and reject
missing corrections or restored absence claims. All three application checks
and exports succeed, 36 focused tests pass without skips on each OS, and
Windows/Linux measurement reports agree exactly. These remain bounded
reference results; chunk 6 is incomplete.

The [batched SKY130 work queue](SKY130_PHYSICAL_QUALIFICATION.md#batched-remaining-work)
originally grouped 880 records into eleven shared work batches; the latest
review retains the remaining 463 original-stream IDs by batch. Its inexpensive reconstruction
authenticates existing results without repeating old geometry/extraction work.
Grouping alone never accepts a rule or assigns it to a later chunk.

The preceding [application isolation audit](validation/sky130-application-isolation-2026-10-14.json)
integrates explicit `x.29` selection into physical settings, Finish and macro
export. Bulk results retain noncontained gate measurements as `NOT_REQUESTED`;
required mode blocks acceptance when containment fails. Missing or changed
evidence blocks export. This closes an application integration gap, while the
nine periphery reviews, undefined `x.20` threshold and outstanding required
catalog/density interpretations keep chunk 6 open.

The preceding [SKY130 isolation audit](validation/sky130-isolation-options-audit-2026-10-14.json)
records an explicit ordinary-bulk choice for optional `x.29`. It retains all
18,191 NFET gates outside deep nwell as measurements and shows that enabling
isolation fails all three reference layouts. The declared result is
`NOT_REQUESTED`, never a passing check or absent-target claim. Eighteen tests
and actual passing/failing/missing-mode command controls succeed on both systems;
complete reference reports agree. Nine periphery execution reviews and the
undefined `x.20` value remain. The six-profile application ledger is unchanged;
the new isolation gate preserves its separate scope.

The preceding [SKY130 voltage-intent audit](validation/sky130-voltage-intent-audit-2026-10-14.json)
checks explicit nominal 0â€“1.8 V reference contracts against every physical port,
captured library domain, 143,928 cell supply/bias pins and all 36,385 native MOS
bodies. Fresh HV-selector/label measurements and the pinned source methodology
conditionally discharge `hvnwell.11`, `hv.X.1` and `hv.X.4` for these exact
references. Both systems pass 21 tests without skips and reproduce identical
reports. That checkpoint left ten periphery execution reviews and the undefined `x.20` value;
the catalog counts below are unchanged. Transient reliability, arbitrary HV
circuits and foundry ERC are outside this nominal contract.

The preceding [SKY130 selected-subject audit](validation/sky130-selected-subjects-audit-2026-10-14.json)
resolves 63 explicit catalog records with fresh raw/derived measurements. Eleven
tests pass on each OS, complete reports agree, and the preceding evidence is
reconstructed. The catalog now has 356 executed, 320 absent and 880 unreviewed
records. Generated-mask and complete-chip obligations remain open.

The preceding [device-intent audit](validation/sky130-device-intent-audit-2026-10-14.json)
matches all 36,385 drawn MOS gates to the native census of the unchanged filled
layouts. Published device tables supply the missing context for the HVTR and
HV-varactor target decisions while preserving generated LVTNM/NCM obligations.
Fourteen tests pass on each OS and complete reports agree. The periphery ledger
at that checkpoint had 13 execution reviews plus the undefined `x.20` threshold; the error
catalog at that checkpoint had 356 executed, 257 absent and 943 unreviewed records. The full list of
remaining periphery obligations is in the [SKY130 guide](SKY130_PHYSICAL_QUALIFICATION.md#explicit-reference-isolation-option).
These are separate ledgers, not independent counts to add together.

The final filled references already pass the recorded application physical
checks/export, nominal routed extracted timing and RTL equivalence. Chunk 6
still requires complete required physical coverage. Exact installer and foundry
delivery acceptance remain in original chunk 12; no delivery prerequisite has
been added to chunk 6. The checkpoints below retain their historical scope.

Chunks 1â€“5 now have their defined planning/reference acceptance. The final
[IHP fill gate](IHP_FILL_QUALIFICATION.md) binds counter, UART and APB to zero
native markers, passing supplemental block rules, strict device/port LVS,
unchanged nominal circuit capacitance and local fields, final-netlist formal
proofs and three-library-condition extracted timing. The actual application
fill, timing and macro-export paths pass. Native abstract readback confirms
all fill is represented, and Windows/Linux evidence audits agree exactly.

The final recipe keeps fill 9 micrometres clear of the circuit. This preserves
the original nominal electrical model and supersedes the earlier coupled-fill
waveform experiments. No unfinished transient is counted as passing; the
1 ps convergence limit remains unchanged. Independent extraction calibration,
additional corners, complete-chip checks and foundry acceptance remain in their
original later chunks. Chunk 6 is now in progress.

The [SKY130 physical coverage batch](SKY130_PHYSICAL_QUALIFICATION.md) runs all
three original final layouts through full enabled geometry in both engines,
with deliberate FEOL/BEOL faults detected. All 13 selected antenna etch stages
pass on the unchanged references, with 178 boundary/connectivity controls and
ten exact contact-array controls. APB's false via4 findings and missed native
array faults are traced to contact-unit and fragment-counting errors. The
three original layouts now also pass strict transistor/body/supply/port LVS,
with deliberate connection, device and port faults rejected. Independent
OpenDB pin export now also resolves all 47 original pin-containment findings;
the corrected layouts pass both full native decks, strict LVS and all selected
antenna stages through the actual export paths. Windows/Linux reconstruction
agrees exactly, with 34 focused tests per OS and complete durable readback.
The rule ledger now also retains the 1,556-record published error catalog and
the previously missing layer TSV sources. The final remote-fill candidates
now pass both native geometry decks, the selected antenna checks and the
unchanged density screen. Exact nominal circuit capacitance, device records
and node resistance are preserved on all three designs, with identical
Windows/Linux audits. An independently referenced diode check closes the
empty-CDL omission and rejects five native diode faults. The
[fill progress record](validation/sky130-fill-progress-2026-10-11.json) retains
these results and failed attempts. Chunk 6 remains open for complete rule
reconciliation, density interpretation, final timing/equivalence and the
combined application gate.

The subsequent [low-voltage](validation/sky130-low-voltage-2026-10-11.json)
and [interconnect](validation/sky130-interconnect-2026-10-11.json) batches add
99 explicit rule bindings. All three final layouts pass on Windows and Linux,
with identical ledgers and 62 combined geometry/binding tests passing without
skips. The periphery ledger retains all 601 rows: 117 executed requirements,
207 measured absent operands, 77 upstream NA, 27 advisory, 61 other backend,
111 requiring execution review and one missing a published definition.
The later [wide-metal batch](validation/sky130-wide-metal-2026-10-11.json) and
[context](validation/sky130-context-review-2026-10-11.json)/
[butting](validation/sky130-butting-review-2026-10-11.json) reviews reduce the
open periphery count to 70. That checkpoint has 125 execution bindings,
239 measured absent operands, 77 upstream NA, 28 advisory, 61 other backend
and one missing source definition. All 92 combined tests pass per OS without
skips; both operating systems reproduce the same final-layout ledger.
The subsequent [global](validation/sky130-global-review-2026-10-11.json),
[mask](validation/sky130-mask-review-2026-10-11.json) and
[complete connectivity](validation/sky130-floating-review-2026-10-11.json)
batches reduce the open periphery review count to 24. That checkpoint has
133 execution bindings, 277 measured absent operands, 77 upstream NA,
28 advisory, 61 other backend and one missing source definition. All 123
combined tests pass per OS without skips, with identical final-layout ledgers.
The complete graph detects floating networks that the bundled local
contact-neighbor check can miss. Exact source records preserve duplicate
rule-name distinctions, and independent voltage-tagging obligations stay open.
Neither these checks nor the earlier native passes complete chunk 6.

The initial [error-catalog reconciliation](validation/sky130-error-reconciliation-2026-10-14.json)
binds 82 of the 1,556 published error records for each retained final
layout: 61 to executed geometry/connectivity checks and 21 to measured absence
of floating/tie exception labels. Its other 1,474 records remain unreviewed,
including chip-level records with the same rule names. This is a new audit of
the committed evidence, not a fresh final-GDS or Windows execution. The 24
open periphery execution rows and the missing `x.20` definition are unchanged.
The [reproduction command and fault controls](SKY130_PHYSICAL_QUALIFICATION.md#explicit-error-catalog-reconciliation)
make the distinction between catalog coverage and periphery coverage explicit.

The [grid/window diagnostic batch](validation/sky130-grid-density-2026-10-14.json)
adds raw grid checks and exact Manhattan metal-occupancy measurements on
700 micrometre windows with 70 micrometre steps. The recovered CI exports
have different hashes from all three locked filled references. Their physical
boundaries pass the grid profile, while seven text anchors are off grid.
Their 200/400 micrometre dies have no full 700 micrometre windows. Clipped
measurements are retained, but neither those measurements nor metal occupancy
are asserted to pass the published oxide-density requirements. The existing
24 open execution rows, missing pin-spacing definition, final filled-layout
timing/equivalence and combined application gate remain open. The
[reproduction instructions](SKY130_PHYSICAL_QUALIFICATION.md#grid-and-density-window-diagnostics)
identify the exact missing filled-reference archive needed to continue.

The subsequent [geometry reconciliation](validation/sky130-geometry-reconciliation-2026-10-14.json)
adds 313 explicit error-record bindings and closes two periphery execution
reviews: the general angle obligation and intra-polygon notches. Each retained
filled layout now has 356 executed error bindings, 39 measured absent operands
and 1,161 unreviewed error records. The periphery ledger now has 135 executed
requirements and 22 execution reviews still open, alongside the missing
`x.20` definition. All other periphery dispositions are unchanged. Its 408
fresh notch controls cover 34 operands, three boundary gaps and four rotations.
All 74 `s`-series records and ambiguous device-dependent entries stay open.

The [reference replay](validation/sky130-reference-replay-2026-10-14.json)
establishes that the recovered CI GDS files and independent OpenDB inventories
match the original **pin-corrected, unfilled** checkpoint exactly. Fresh calls
to the application's pin exporter reproduce all three reference GDS files byte
for byte, followed by 18 passing geometry/connectivity profile runs on Linux.
These runs do not replace the later filled-layout, native-engine, timing,
Windows or combined application acceptance. The
[updated reproduction instructions](SKY130_PHYSICAL_QUALIFICATION.md#geometry-catalog-and-notch-reconciliation)
separate retained filled-layout reconciliation from fresh unfilled execution.

The IHP reference acceptance retains its original source in an explicit
historical snapshot of shared files changed by the SKY130 export hooks. It
does not assert a new IHP native run with those hooks.

The subsequent [portable filled replay](validation/sky130-filled-replay-audit-2026-10-14.json)
recovers the exact final counter/UART/APB inputs in a committed 13 MB fixture.
Fresh applicability and all six supplemental profiles reproduce their original
results on Windows and Linux; both systems produce identical complete replay
JSON. The incoming 215-test batch passes on each OS, followed by 28 focused
fixture/reconciliation checks. A Windows path-spelling defect is fixed and its
failed attempt retained. Physical vertices pass the grid diagnostic, while
seven text anchors remain off grid. Raw metal-window measurements remain blocked
for oxide-density acceptance. This is fresh polygon execution, not a new native
runtime or installer qualification.

The [density scope review](validation/sky130-density-scope-2026-10-14.json)
then resolves eight window/step rows as parameters of their explicitly named
RR recommendations. Five focused controls pass per OS. Required RC metal-fill
algorithms are unchanged, and no unexecuted density recommendation becomes a
pass. The latest periphery ledger retains 135 executed requirements and now has
14 execution reviews, 36 advisory rows and the separate missing `x.20` definition.
The 1,161 open error records and remaining source, density, timing/equivalence
and combined application gates still leave chunk 6 incomplete.

The [application rule integration](validation/sky130-application-rules-2026-10-14.json)
adds the six reviewed geometry profiles to prepared SKY130 HD Finish jobs and
macro export. The exact helper/manual inputs, all checks and the 601-row ledger
are retained and validated; missing reports or removed policies cannot pass
export. Production entry points are exercised on the original counter/UART/APB
routed checkpoints, with separate replay of the exact filled candidates and an
invalid-layout control. This closes a bounded integration gap, not the complete
chunk: the runtime policy has 133 executed periphery bindings, while the later
135-binding qualification review remains separate. Complete rule coverage,
required density, final filled-layout timing/equivalence and a rebuilt delivered
runtime still require acceptance.

The chunk 4 GF180 record retains its original source and scope. The eight shared
modules changed for IHP have exact historical source snapshots; this preserves
past acceptance without asserting a new GF180 production run on the new source.

## Completed chunk 4 reference gate

Chunks 1â€“4 now have their defined planning/reference acceptance. The
[full density closure](validation/gf180-fill-closure-2026-10-09.json) binds the
original six GF180 C/D counter, UART and APB production exports to both native
and supplemental checks. All native main, antenna and density counts are zero.
Each export passes 108 supplemental checks, final transistor/supply connectivity,
formal equivalence and three library-condition timing/electrical checks after
fill. Windows and Linux reproduce the same fill and boundary reports.

The user authorized selection of a reference floorplan. It keeps each original
die/core footprint and declares 40 Âµm streets immediately outside all four die
edges. The manual's stricter 26 Âµm scribe clearance removes the margin COMP
candidates; a continuous geometric proof finds no legal 5 Âµm COMP square in
the remaining interior. Six deliberately added margin arrays fail that boundary
rule. Exclusion-edge rows and vendor-memory rules have no operands in these
six layouts. Density denominators, RTL and constraints remain unchanged.

The pinned metal-fill procedure requires 200 Âµm windows at 100 Âµm steps and
a total-die density threshold. All full windows and additional clipped windows
are retained. It supplies no separate numeric local-window acceptance limit;
unknown foundry limits are not asserted passed. The new record resolves the
earlier premature native-only completion by binding this manual coverage.

Digital function is supported by final extracted device/supply connectivity,
formal equivalence, unchanged circuit masks and extracted timing. The separate
full Magic-RC transient experiments are unfinished and are not counted as
passing waveforms. Chunk 4's original gate did not require full-chip transistor
transients. Full-device, extraction-corner, complete-chip and foundry acceptance
remain in their original later chunks. No complete PDK is tapeout qualified.

## Sequence and gates

| Chunk | Achievable batches | Completion gate |
|---|---|---|
| 1. Qualification matrix | Inventory bundled inputs; enumerate tests and missing upstream coverage; validate identities and completeness. | Every requirement has a test, expected result and status. Missing coverage is visible. This planning gate is defined; process execution is not qualified. |
| 2. Toolchain | Compatible KLayout CLI; hosted OpenROAD result; clean Linux install; clean Windows/WSL install; native rule coupons and fault controls. | Exact fresh runtimes execute every required valid/invalid case correctly. |
| 3. GF180 geometry | Integrate via pitch; integrate tap spacing; counter; UART; APB. Establish a separate matched D platform. | Production-flow geometry, antenna, extracted timing and equivalence pass without changing the original design constraints. |
| 4. GF180 density | Resolve active/poly fill; resolve each metal layer; check exclusions; rerun all post-fill checks. | Filled production references pass required density/geometry, connectivity, extraction, timing and equivalence. Experimental counter results retain their narrower scope. |
| 5. IHP geometry/fill | Resolve the twelve observed findings, grouped by rule; recheck counter; UART; APB. | Complete final-layout rules, connectivity and extracted performance pass. |
| 6. SKY130 public checks | Version the public baseline and exclusions; execute local native/supplemental geometry, antenna, strict final-GDS LVS, density, fill checks, fault controls and generic export. | The approved `sky130a-hd-public-checks-v1` reference gate passes; full-window and small-block outcomes remain distinct. Unresolved process rules and foundry signoff are explicitly excluded. |
| 7. Devices | Reconcile upstream inventory; MOS; resistors; capacitors; diodes; bipolar; remaining devices. Treat IHP RF separately. | Every supported device passes terminal/parameter/model, operating-envelope, layout and extracted-connectivity tests. Unsupported required devices remain blockers. |
| 8. Extraction/corners | Wire coupons; vias; device parasitics; coupling/fill; independent RC corners; complete required PVT/RC pairs. | Independent references agree within frozen, source-backed tolerances and injected faults fail. |
| 9. Analog blocks | Mirror; differential pair; amplifier; reference; oscillator; noise/statistics; separate IHP bipolar and RF batches. | Schematic and extracted results meet numerical specifications fixed before execution, across declared conditions. |
| 10. Digital/mixed signal | Select larger controller; functional coverage; clock/reset review; physical/timing closure; analog/digital integration. | Functional, equivalence, all-mode timing/electrical and final-layout checks pass. |
| 11. Complete chips | Assemble chip; electrical-rule review; ESD/latch-up review; EM/IR review; I/O/package review. | Every required chip-level check passes on final geometry and the actual package/modes. |
| 12. Delivery/tapeout | Exact Windows package; exact Ubuntu package; independent handoff reproduction; submission preparation; external acceptance. | Consumer workflows pass and the required foundry/shuttle acceptance covers the precise submitted design, revisions and waivers. |

## Locked starting scope

| Analog target | Bundle revision | Indexed / placeable | Physical option and present digital coverage |
|---|---|---|---|
| SKY130 A | `2a8a8a7048ac324d` | 74 / 71 | Local interconnect plus five metals; HD digital library; 3 library by 3 RC conditions. |
| GF180 C | `627ca682d68e1e92` | 68 / 64 | Five metals, 0.9 micrometre top metal, MIM, HRPOLY1K; digital 9-track 5 V, 5LM_1TM/9K; 3 library by 1 RC condition. |
| GF180 D | `7dd87219f1333dbb` | 68 / 64 | Five metals, 1.1 micrometre top metal, MIM, HRPOLY1K; separate `gf180d` 9-track 5 V / 5LM / 11K production references; both installed-runtime reference gates passed. |
| IHP SG13G2 | `d03f47cdf46a85a0` | 45 / 35 | Five ordinary and two top metals; SG13G2 digital cells; 3 library by 1 RC condition. MOS, bipolar and RF qualification remain distinct. |

All digital profiles start from ORFS
`eaba6576441bf7c1743ea56ecdb1904210ec02c2`. SKY130's prepared digital profile
uses the additional checksum-locked Volare assets listed in the matrix.
GF180 primitive models and physical decks have separate source locks; the
matrix retains both. Do not infer that matching analog device names establish
matching digital views or matching metal stacks.

Current digital library points are:

| Target | Typical | Slow | Fast |
|---|---|---|---|
| SKY130 HD | 1.80 V, 25 C | 1.60 V, 100 C | 1.95 V, -40 C |
| GF180 C digital | 5.00 V, 25 C | 4.50 V, 125 C | 5.50 V, -40 C |
| IHP digital | 1.20 V, 25 C | 1.08 V, 125 C | 1.32 V, -40 C |

These are selected library conditions, not the valid operating envelopes for
all analog devices. IHP's generic slow/fast aliases leave some HBT, capacitor and
resistor sections at nominal; the exact include mappings are in the inventory.
Their actual best/worst and statistical sections need their own tests.

## Using the record

Run the coverage check from the repository root:

```sh
python scripts/check_pdk_qualification.py
```

The release documentation check also invokes it. It verifies all bundled asset
hashes, exact device coverage, required process/workflow rows, test contracts,
referenced runner paths and the hashes of historical evidence records. Its
success is named `matrix_consistent`; process qualification remains
`unqualified`. Missing evidence and unsupported devices cannot become passes.

Current execution statuses are `not_run`, `partial`, `failed`,
`needs_definition`, `unsupported` and `passed_reference`. A `partial` row identifies
prior limited evidence without claiming the complete test passed. Schema 4 retains
the chunk 2 toolchain references, which require the complete,
hash-bound [acceptance record](validation/toolchain-2026-10-07.json). It requires
both operating systems, valid/fault controls and every required hosted step on
the recorded source. It separately binds the [chunk 3 acceptance record](validation/gf180-geometry-2026-10-07.json)
to current production evidence, both operating systems, actual rule/fault controls,
all required timing conditions and the captured C/D technologies. Device rows,
density and later chunks cannot inherit either pass. Schema 4 independently binds
the six-reference density record, two OS audits, exact source/runtime identities,
installed acceptance and preserved evidence. Chunks 5â€“12 need their own reviewed
acceptance schema and records;
preserve previous failures rather than merely changing a status string.

## Historical execution checkpoints

The entries below preserve what was known at each earlier checkpoint, including
failures and then-open work. The current checkpoint above and the matrix govern
today's status; historical JSON evidence remains unchanged.

Chunks 1 and 2 are complete within these boundaries. On the corrected application
backend, each installed runtime passed 26 digital checks, 15 timing pairs, three
audited exports, seven tool controls, sixteen process-rule controls and nine
digital physical controls. Required hosted implementation steps passed on
`7feca0695f586ff84c8d2111b528076891a50e77`. The record retains the initial
antenna-diode coverage failure and its correction.

Chunk 3 is complete within its reference scope. The [production GF180-C batch](validation/gf180-production-geometry-2026-10-07.json)
passes main geometry, antenna, extracted timing and equivalence on counter, UART
and APB with unchanged RTL/constraints and PDK sources. The application generates
and captures the two corrected recipes. The separate [matched D batch](validation/gf180d-production-geometry-2026-10-07.json)
now also passes these reference gates, with the actual 11K technology and
extraction selection independently audited. The updated runtime includes all
four digital profiles. Each Linux and Windows installation passed 34 digital
checks, 18 timing pairs, four audited exports, seven tool controls, 16 process-rule
controls and 12 digital physical controls. Independent full-deck audits on each
OS's C/D counters pass main geometry and antenna while retaining density failures.
The [installed C/D UART/APB batch](validation/gf180-cd-installed-workloads-2026-10-07.json)
also passes geometry, antenna, all 12 library-corner timing checks and equivalence
on application source `1989dbf`, with unchanged design constraints. The installed
Windows catalog also passes selection, C/D save/reopen, corner reset and undo.
Its initial report-writer failure is retained; the corrected checker completed
the entire workflow and produced a source/runtime-bound report.

Windows setup failed twice with WSL service connection errors before the third,
unmodified full setup passed. Both failures are retained. Eight read-only
idle/startup cases, two full integrity checks and six saved-job dispatch trials
passed, but no root cause or reliability fix is established. Public-release
startup reliability remains open.

Hosted run `37652837883` passed on source
`1989dbf`; independent input, source and artifact audits passed 28 counter stages,
64 UART/APB stages across four profiles and 16 additional SKY130 corner stages.
The SKY130 export audit retains three numerically distinct interconnect
extractions and all 18 library/interconnect timing pairs. Hosted-upload omissions
were restored only by exact hash in a separate audit copy; original downloads
remain unchanged. Desktop build run `37652838673` passed all five jobs on the same
application source; exact consumer-package acceptance remains chunk 12 work.
The acceptance checker passed the full 1,444-test suite (63 skips); the subsequent
GUI report-only correction passed the actual installed-catalog workflow again.
Full density checks still report 555, 5,796 and 4,416 markers for each variant respectively;
these remain chunk 4 failures. No process or complete chip is qualified for tapeout.

Chunk 4 has started with a [native density baseline](validation/gf180-density-baseline-2026-10-07.json).
The 555 counter markers span seven failed whole-layout rule labels, not 555
independent windows: PL.8 (104), M1.4 (139), M2.4 (161), M3.4 (137), M4.4 (8),
M5.4 (3) and MT.3 (3). In the selected 5LM stack, M5.4 and MT.3 both measure
Metal5. The pinned deck compares poly coverage against 14% and each metal against
30%; its marker counts emit existing polygons and do not measure the coverage
deficit. All four OS/variant counter reports agree. The next batch must reconcile
the complete foundry dummy-fill requirements and measure actual coverage before
adding legal fill. The original extent, constraints and failed reports remain fixed.

The next [fill diagnostics](validation/gf180-fill-diagnostics-2026-10-07.json)
retain an independently audited native C counter experiment using the supplied
capacitive filler cells. Six implementation/proof/timing stages pass; native
main geometry and antenna remain clean. The poly-density finding is removed,
but all five metals still fail. Over the original declared 200 by 200 micrometre
die, COMP is 30.46% and poly is 22.82%. Metal coverage is 21.44%, 0.88%, 0.44%,
11.93% and 5.36%, respectively. The native deck uses the smaller occupied-geometry
extent, so its percentages are different; empty die margins must stay in the
independent density denominator. The higher remaining native marker count
(4,387) reflects additional metal polygons, not a measured coverage deficit.

Seven native coupons establish specific coverage gaps: entirely absent material
can yield zero density markers, and wrong-size dummy COMP, poly and metal are
not distinguished from the size controls by the pinned deck. The
[supplemental checker](../scripts/check_gf180_fill.py) detects absent material,
measures the declared footprint, includes dummy poly in total coverage, and
checks dummy sizes, grid, spacing, poly/COMP enclosure and selected circuit
clearances. Its written-GDS results agree on Windows and Linux. The
[manual source lock](../examples/gf180-fill-manual-lock.json) pins the governing
fill tables; the licensed source copies are retained in the diagnostic archive.

This checker intentionally cannot approve full fill qualification: local
density, well/marking/edge exclusions, pattern offsets, adjacent-layer rules,
final-layout LVS and post-fill extraction remain open. Its command returns 1
for failed checks and 2 for a passing subset with incomplete coverage. For a
captured C counter, use the original project's die coordinates:

```sh
python scripts/check_gf180_fill.py --gds final.gds --top counter --variant C --bounds 0 0 200 200 --output fill-report.json
```

Four connected power-mesh experiments are also retained as failures: three
failed detailed placement and one failed power-channel repair. They do
not change the production recipe. They motivated the placement diagnosis below.
Every accepted method must still complete the post-fill checks on C/D counter,
UART and APB references. C's capacitive-filler experiment does not qualify D.

The [filled-counter connectivity record](validation/gf180-filled-connectivity-2026-10-07.json)
captures the subsequent independent audit. A coarser Metal2 power mesh leaves
the placement channels required by the actual pin-access rules. Two new mesh
trials pass the six implementation/proof/timing stages, main geometry and
antenna checks without changing RTL, timing constraints, die or core. The final
GDS prototype adds 911 Metal1 dummy squares and carries the original declared
die boundary into stream-out. It has zero native main, antenna and density
findings. Over that unchanged die, COMP/poly coverage is 30.42%/22.79%; Metal1
through Metal5 coverage is 30.84%, 34.91%, 30.19%, 32.64% and 30.83%.

Independent foundry CDL views match all 18 used cell layouts exactly. The
reference includes 801 placed cells and 4,184 transistors, including capacitive
fillers; its available terminals were checked against the implementation
database. Explicit bulk bindings follow the captured power-grid intent. A
verification copy removes repeated child-cell text labels while preserving all
physical masks and all eight chip-level pin labels.

The unchanged LVS deck can report a matching graph while retaining an unresolved
ground `must-connect` warning. The application now preserves extraction findings
in the cross-probe table and rejects a clean-match verdict for warnings, errors
or unclassified extraction messages. The older retained Banba comparison also
contains this warning and is now a negative regression; its historical graph
match does not establish strict connectivity acceptance.

A separately captured diagnostic disables name-based joins, requires chip-top
connectivity and models substrate taps with soft global connections. It matches
the counter's devices and eight pins with no extraction findings. Its 1,965
net-match warnings concern interchangeable internal capacitive-filler nodes.
However, an actual isolated ground pad still escapes that comparison. An
independent metal-only network check therefore verifies every chip pin and all
1,602 cell power terminals. Windows and native-runtime connectivity measurements
agree. Together the two checks accept the valid reference and reject a ground
open, signal short and missing substrate contacts. The individual false pass and
failed diagnostic attempts remain retained.

These results do not complete chunk 4. The GDS prototype and diagnostic deck need
production integration and complete fill-rule coverage. The recorded timing
precedes the final Metal1 dummy fill; extraction and timing must run on the
actual filled geometry. C/D counter, UART and APB still require complete accepted
production runs on both operating systems.

Native extraction of matched before/after geometries retains all 4,184 device
records and eight chip ports. The fill adds 911 floating conductors. An independent
capacitance-matrix audit preserves the full floating network, checks its numerical
solution and measures increased loads on all six signal ports. These measurements
hold the other retained nodes fixed; they are not a timing result. The native
resistance files contain 35,706 resistor records in each case, but production RC
assembly rejects a negative supply-network capacitance weight. Six much smaller
negative capacitance roundoff residues are retained separately; only explicitly
recorded diagnostic copies normalize those residues. The production floating
reducer also rejects this 911-node component at its 256-node budget. These open
integration issues and the failed extraction attempts remain in the same record;
neither the parser nor the acceptance gates were weakened.

The subsequent [RC extraction candidate](GF180_RC_EXTRACTION_CANDIDATE.md)
corrects misplaced device connection points and includes the earlier repairs
for device connections across planes and conductors without a driver. Matched
native counter runs extract every network, preserve 4,184 devices and eight
ports, and contain no negative resistance-node weights. The 18 used cell
controls also preserve their device inventories. This is an explicit additional
engine candidate; the installed runtime is not replaced or newly qualified.
The full circuit exceeds the original pairwise capacitance expansion budget.
The [compact export integration](validation/gf180-compact-export-2026-10-07.json)
now preserves the same area-weighted equations with 24,459 before-fill and 26,281
filled capacitors, including intrinsic capacitance at its original substrate
anchor. Both stay below the unchanged 50,000-capacitor default. Final exports
preserve all 4,184 device parameter records, eight ports, and 46,757/47,668
resistors, respectively. The full floating network is retained. Independent
small-circuit native frequency, transient and corrupted-coefficient controls
pass for the production generator.

The initial integration record is not chunk 4 acceptance. Its full-counter
exports used the previously audited diagnostic roundoff copies; raw parsing
remains strict. All original design constraints and numerical/size guards
remain in force.

The [shielding and fill follow-up](validation/gf180-shielding-fill-candidate-2026-10-08.json)
records two additional explicit engine candidates. Contact-material shielding
and floating-point triangle-resistance corrections allow both counter layouts
to extract and export from untouched inputs, preserving all devices, ports and
floating fill conductors. The later polygon candidate carries actual diagonal
regions through each shielding plane. Twenty independent diagonal controls
pass against inside/outside Manhattan bounds refined to the native grid, while
twenty rectangular and twenty contact controls retain their results. The exact
strip-integration function also passes 126 independently integrated numerical
cases. The two full counters retain identical original capacitance records and
the same resistance graphs after accounting for internal node names.

These are bounded geometry and arithmetic results, not calibrated extraction
accuracy. Printed resistance-node capacitance weights still vary slightly
between extractions. The separately enabled corner model retains four diagonal
failures, and direct-overlap diagonal coverage remains open. The default engine
and installed application runtime are unchanged. Full-counter transient and
post-fill timing acceptance are still pending. The subsequent
[current-sum integration](validation/gf180-current-sum-integration-2026-10-08.json)
replaces long voltage-source chains with internally terminated current sums and
isolated output buffers. Its strict parser rejects physical leakage, unbuffered
loads and malformed dependencies. Native SPARSE/KLU frequency and floating-pair
transient controls pass, and injected coefficient/leakage faults are detected.
Full before/filled exports reproduce the tested prototype on Windows and Linux
without changing any physical resistor, capacitor, device or port. The complete
counter simulation and post-fill timing still need their own acceptance.

The supplemental fill checker now verifies both sides of well boundaries and
the documented marking-layer exclusions, including contained dummy polygons
that a spacing check alone misses. Its operands are checked against the selected
C/D layer map. Fourteen written-GDS tests pass on each operating system,
including exact-limit, 5 nm short, hole and diagonal-boundary controls. Both
systems produce the same 87-check report for the filled C counter with no
failures in the implemented subset. Local density, drawing patterns, adjacent
layers, embedded-memory marker aliases and complete boundary/scribe scope
remain explicit gaps. The report still returns `qualified: false`.

The [density and adjacent-layer follow-up](validation/gf180-fill-coverage-2026-10-08.json)
binds additional rule definitions to the same pinned manual revision. Global
metal density now requires strictly more than 30%, as Mn.4 and MT.3 specify;
exactly 30% is rejected. COMP and poly retain their inclusive minimum limits.
Integer doubled areas preserve half-database-unit polygon areas at the boundary.
Adjacent-layer checks require 1 micrometre clearance and no overlap with the
union of circuit and dummy material, including Poly2 below Metal1. This is a
conservative interpretation satisfying both the table's general layer wording
and the diagram's dummy-metal labels.

Twenty written-GDS controls pass on each operating system, including exact
thresholds, 5 nm spacing faults, contained and diagonal geometry, shifted window
origins, partial edges and an independent rectangle-union density oracle. The
unchanged filled C counter passes all 96 implemented checks on both OSes under
each C/D layer map, with identical reports. Replaying C geometry with D's operand
map does not qualify a production D design. Each actual checker returns exit 2
for incomplete coverage.

The checker also measures 200 by 200 micrometre windows at 100 micrometre steps
anchored to the declared die. It reports full windows separately from clipped
edge measurements and does not invent local acceptance limits. The counter's
one full window per metal agrees with its global density. Two clipped Metal1
regions measure 29.55% and 28.67%; they remain measurements without a foundry
edge-window verdict. Local/edge acceptance, empty-field COMP coverage, drawing
patterns, memory-marker scope and boundary/scribe requirements remain open.

Complete fill rules, actual post-fill circuit behavior and timing, then
production C/D counter, UART and APB acceptance on both operating systems are
required before chunk 5.

The [capacitance-precision candidate](validation/gf180-capacitance-precision-2026-10-08.json)
addresses the observed full-counter weight repeatability failure. Double totals
and distribution arithmetic pass 24 native order/scale/mode controls; the older
engine passes six. Three extractions of each geometry, including a fresh pinned
source build, now preserve every printed weight under unique node matching.
The raw capacitance terms, resistor graph and device parameters are unchanged.
Both production exports reproduce byte for byte on Windows and Linux. This is
bounded candidate evidence; it does not promote the default engine or complete
chunk 4. The earlier frozen-circuit transient attempt ended on its wall-time
guard before finishing. Its unchanged retry uses a CPU-work limit and a separate
longer wall guard; no complete transient or post-fill timing pass is recorded.

Before each batch, freeze its exact inputs, numerical limits and negative
controls. After the batch, preserve commands, versions, input/output hashes,
native reports, measurements and failures. A new device/model/geometry/tool
revision requires appropriate requalification. A numerical agreement threshold
is not a circuit-performance specification; both must be declared where relevant.

The [exclusion-rule controls](validation/gf180-exclusion-controls-2026-10-08.json)
add separate NDMY/PMNDMY minimum-width checks, NDMY spacing and rectangular
area/side limits. Unsupported vendor implant layers MCELL_FEOL_MK (11/17) and
YMTP_MK (86/17) now produce explicit coverage failures; neither inherits the
supported MTPMARK (122/5) checks. Large nonrectangular NDMY regions remain a
blocking interpretation gap, and any exclusion marker requires a separate
DE.1 design justification. Twenty-four written-GDS tests pass on each OS.
The unchanged C counter passes 103 implemented checks under both C/D maps,
with byte-identical OS reports and actual incomplete-coverage exit code 2.

The [native exclusion runner](../scripts/qualify_gf180_exclusion_rules.py)
executes the unchanged pinned DE rule file on 23 diagnostic layouts and compares
each outcome with the supplemental checker under both C/D maps. It reproduces
seven differences: two narrow markers hidden by the native cross-layer union,
three rectangles flagged by the native area rule despite satisfying the manual
limits, and two unsupported memory-layer cases rejected by supplemental coverage.
The memory cases do not audit the complete native memory rules. Native DE.3
emits all edges at or above 15,000 square micrometres, including the exact limit
and the permitted 80-micrometre short-side rectangles. These disagreements are
retained; the native deck is unchanged and no acceptance waiver is inferred.

The same checkpoint retains a terminal numerical failure in the earlier
filled full-counter simulation: ngspice reports a timestep-too-small error at
2 picoseconds on a distributed VDD node, despite exiting with code zero. The
functional checker correctly rejects that result. Exact-build instruction
samples locate much of the observed CPU work in KLU matrix refactorization;
sampled floating-point operands do not establish a subnormal-arithmetic cause.
Both short startup solver trials on the newer precision circuit exhaust their
fixed CPU-work limits without reaching the observation point. No full-counter
electrical or timing acceptance is established by these diagnostics.

The later [simulator-ordering investigation](validation/gf180-simulator-ordering-2026-10-08.json)
finds a bounded startup improvement without changing the extracted circuit.
An isolated ngspice 42 build passes the production RC controls and frozen
device-only counter with either AMD or COLAMD ordering. On the identical filled
RC circuit, COLAMD completes the 100 ps startup observation in about 30 seconds;
AMD reaches its 240-second CPU limit before that point. Rejected current-return
and row-scaling alternatives remain in the evidence. Full 900 ns before/filled
COLAMD runs have started with the original circuit, models, numerical limits and
component budgets. Startup alone is not functional or timing acceptance; the
default engine and installed application remain unchanged.

The complete upstream inventory, general analog/RF numerical specifications,
representative full-chip designs, package choices and foundry/shuttle acceptance
target remain open. They have tests and blocking conditions in the matrix;
no guessed limits or synthetic acceptance evidence fill those gaps.

The [drawing-pattern controls](validation/gf180-fill-patterns-2026-10-08.json)
check a declared alternating staggered array against the actual written GDS.
The [source lock](../examples/gf180-fill-pattern-lock.json) includes the pinned
manual tables and diagrams. COMP uses 5 micrometre squares on an 8 micrometre
pitch with 1.6 micrometre offsets; matching poly uses 5.6 micrometre squares
on the same pitch. Metal uses 2 micrometre squares, a 3.2 micrometre pitch and
0.5 micrometre offsets. These are the chosen generation recipe, not an
enumeration of all legal patterns. The drawing space is checked through the
placement recipe; the separate Euclidean DRC limits remain unchanged.

Thirty-six written-GDS tests pass on each OS, including legal diagonal gaps,
cropped arrays, negative indices, shifted origins, hierarchy, rotation and
reflection. Missing stagger, wrong pitch, 5 nm phase errors and undeclared
dummy layers are rejected. The checker also detects reuse of an entire array
on adjacent metals even when different sites were removed on each layer.
Accepting the full DM.9 offset relationship remains open when both adjacent
layers contain dummy material.

The subsequent [adjacent-metal recipe](GF180_FILL_PATTERNS.md) recognizes an
exact 0.5 micrometre translation along either axis of the complete declared
staggered arrays. All four phases must agree after translation, and both written
arrays must first pass their own pattern checks. Replicas still fail; diagonal
or other nonreplicated relationships remain explicitly unqualified by this
selected recipe. Written controls cover both C/D maps, every adjacent pair,
cropped arrays, rotations/reflections and 5 nm offset faults. Replaying all six
retained filled production references leaves their 104 implemented checks
unchanged. These references use only Metal1 dummy fill and do not themselves
qualify adjacent-layer patterns or complete fill coverage.

The unchanged C counter's 911 Metal1 squares match the
[declared recipe](../examples/gf180-counter-fill-pattern.json) and pass all 104
implemented checks under both C/D maps on both OSes. A retained GDS with one
square shifted 5 nm still passes the earlier 103 checks but fails the new
drawing-pattern check. Corresponding Windows/Linux reports are byte-identical.
The CLI returns 2 for the reference and 1 for the fault; neither is qualified.
C geometry under a D map still does not establish a production D result.

For this reference, add the recipe to the existing inspection command:

```sh
python scripts/check_gf180_fill.py --gds filled.gds --top counter --bounds 0 0 200 200 --variant C --pattern-plan examples/gf180-counter-fill-pattern.json --output new-pattern-report.json
```

Omitting the recipe keeps drawing coverage explicitly open. Membership allows
sites removed for blockages and therefore does not establish empty-field
coverage. Local/edge acceptance, complete boundary/scribe scope, exclusion-edge
rows, full post-fill circuit behavior/timing and production C/D acceptance
remain required before chunk 5.

The [COMP placement-space analysis](validation/gf180-comp-space-2026-10-08.json)
examines all possible 5 micrometre square origins within the declared rectangle.
It uses a conservative subset of the forbidden origins from the circuit COMP
and poly clearances. An empty complement proves that no legal square fits;
a nonempty complement cannot approve a placement. This avoids relying on a
sampled placement grid or treating a square-corner keepout as a Euclidean rule.
Exact-limit sites retain a numerical margin, and line/point origin domains and
non-Manhattan material remain explicitly unqualified.

The original captured implementation declares a 200 by 200 micrometre die and
the core from (20, 20) to (180, 180). The counter has no legal additional COMP
square anywhere inside that core under DCF.4/5 alone. Possible origins remain
around the die margins. The optional `--core-bounds 20 20 180 180` reports the
core separately; it never replaces the die, changes the density denominator,
or clears the complete DCF.1a requirement. Both OSes produce identical reports
under the C/D maps, and all 44 written-GDS fill controls pass, including an
independent rectangle-distance oracle, exact-limit corridors, holes, rotations
and incomplete geometry cases. This reference remains a C design.

The [boundary source lock](../examples/gf180-boundary-manual-lock.json) captures
the scribe/guard-ring chapter and uncoded-rule appendix at the same manual
revision. DCF.7a is 26 micrometres in the main fill table and 8 micrometres in
the appendix. Enforcing 26 would satisfy both stated minima, but no scribe or
frame geometry is declared for this counter and it has no GUARD_RING_MK
geometry. The implementation footprint cannot supply those missing chip-level
facts. Boundary acceptance and the manual discrepancy remain explicit; no
scribe dimensions, packaging choice or waiver is inferred.

The [earlier unfilled full-RC control](validation/gf180-unfilled-functional-2026-10-08.json)
has now completed 900 ns with 12,609 finite, ordered waveform points. An
independent audit verifies the frozen circuit/models/stimulus, all 18 clock
edges and all 18 functional samples using interpolation at the original sample
times. This covers the earlier current-sum export before the precision change.
Its paired filled run failed numerically; the newer precision/COLAMD runs have
their own acceptance. This result does not establish post-fill timing or PVT
coverage.

The [declared-boundary checks](validation/gf180-fill-boundaries-2026-10-08.json)
add DCF.7a/b/c/d and DPF.7 clearances using an explicit, source-bound floorplan.
The [boundary format](GF180_FILL_BOUNDARIES.md) identifies prime die, scribe,
frame, frame-cell and SLM test regions. Fill crossing or missing its declared
region fails coverage. Frame-cell non-ET exceptions must be explicit, and
dummy poly outside prime die is rejected. The checker enforces the main
table's 26 micrometre DCF.7a distance while retaining the appendix's conflicting
8 micrometre value. Source identity alone does not establish complete-chip
floorplan correctness, guard-ring connectivity or reticle/package acceptance.

Eleven additional written-GDS tests cover exact limits, 5 nm faults, all four
edges, diagonal distances, a scribe polygon with a hole, recursive rotations,
unclassified/crossing polygons and stale or changing source identities. The
counter's original GDS and density denominator are unchanged. It has no boundary
declaration, so the checker reports `missing_boundary_plan`; no chip-level
geometry is invented and chunk 4 remains incomplete.

The [six-reference density candidate batch](validation/gf180-density-production-2026-10-08.json)
now reproduces the coarse-Metal2 power mesh, capacitive filler cells and
perimeter Metal1 dummy recipe through the production APIs on the actual C and D
platforms. Counter, UART and APB each pass all three native rule groups, with
zero geometry, antenna or density findings. Counter uses 911 Metal1 dummy
squares; UART uses 2,123; APB uses 2,119. The original RTL, timing constraints,
die/core dimensions and selected mapping corners are preserved. Independent
audits check the actual C 9K and D 11K technology selections, including D's
explicit extraction rules, every retained artifact and all other written masks.

All six candidates pass mapped/physical equivalence, detect the injected
register fault and pass three library timing conditions before the final
floating Metal1 fill. Those 18 timing results do not establish post-fill
timing. Linux runs the six implementations and full native rule decks; Windows
replays the exact written GDS through the supplemental checker. All 104
implemented supplemental checks pass for each design on both systems. Their
decoded reports agree; the only serialization difference is integer versus
floating-point spelling of the declared bounds in API and CLI reports.

The initial launcher failed before implementation because it omitted the cell
ID. A later launcher accidentally reset UART's slow mapping corner to typical;
the independent audit rejects that C result. The matching incorrect D trial was
intentionally stopped, with its exact process identities and artifacts retained.
Corrected C/D UART runs preserve the original slow mapping and pass their audits.
The successful and rejected native files are retained in separate hashed archives.

These are explicitly staged candidate profiles, not new application defaults or
fresh Windows production acceptance. Complete fill coverage and block/chip
boundary scope, post-fill connectivity/extraction for the larger references,
post-fill function/timing, accepted engine integration and installed-runtime
acceptance remain required. The precision/COLAMD counter simulations have now completed the nominal
functional gate described below; this geometry batch alone did not establish it.
Chunk 4 remains incomplete.

The [six-layout power-connectivity audit](validation/gf180-cd-filled-power-2026-10-08.json)
now binds every placed cell to the original database by master, orientation and
position. All 16,592 placements agree, and every used cell's physical masks match
the independent GDS at the pinned foundry-library revision. The audit covers 48
cell types and all 33,184 VDD/VSS cell terminals across the actual C/D references.
Windows verifies that each terminal reaches its declared top-level power net and
that the top ports remain distinct. Captured preview power anchors can lie on a
different rail from the GDS label; their physical connectivity is checked rather
than requiring the annotation coordinates to be identical.

For each design, written-GDS controls isolate VDD, isolate VSS and bridge two
signal ports. All 18 metal faults are rejected. Six unchanged controls pass.
A separate substrate-contact removal leaves the metal network connected in all
six designs, explicitly demonstrating that metal continuity alone cannot approve
substrate/device connectivity. Each fault retains its exact changed masks and
all other masks are independently checked for equality. Original filled layouts
and their design constraints remain unchanged.

The [six-reference native circuit audit](validation/gf180-six-filled-lvs-2026-10-08.json)
now completes the C/D counter, UART and APB layout comparisons. Each stock-deck
device graph matches, while the top-level VSS must-connect warning still blocks
strict acceptance. Each experimental substrate-aware comparison matches with no
extraction warning. Independent Windows readback confirms all 98,524 device
pairs and 106 top-level pins, with a bijective net mapping and every device
terminal checked against that mapping. The six prepared verification layouts
preserve every physical mask of their exact density candidates.

The UART references preserve three intentionally unused clock-load outputs.
Their ambiguous internal net matches include two nodes in one OAI31 cell per
layout, as well as filler-cell nodes. The independent terminal audit confirms
the complete graph mapping, including those nodes. An initial audit incorrectly
assumed every ambiguity belonged to a filler cell; that rejected attempt is
retained. Counter and APB ambiguities are confined to filler-cell internal nets.

The foundry antenna CDL uses positional diode area/perimeter values that the
stock reader rejects. A strict adapter converts those two reviewed diode models
to explicit A/P/M syntax without changing nodes, polarity, values or
multiplicity. Unsupported records fail. The stock reader also treats diode
dimensions as secondary comparison parameters, allowing dimension faults to
pass. A separately retained diagnostic guard makes both dimensions mandatory.
Independent database readback confirms all four diodes in each APB layout have
the expected polarity, 0.2034 square micrometre area and 1.85 micrometre perimeter,
with both dimensions enabled in the experimental comparison.

Fifteen focused tests pass on each OS; sixteen actual native Ruby controls
reproduce the original parser rejection and silent dimension-fault passes, then
verify that the guarded comparison rejects the faults. The full application
suite passes 1,527 tests with 62 skips. One Linux test launch failed before
execution with a WSL connection error; the direct-entry retry passes, and the
failed launch remains retained. Source libraries and the original rule deck
are unchanged.

The [completed connectivity fault audit](validation/gf180-connectivity-controls-2026-10-09.json)
now covers all six actual C/D counter, UART and APB layouts: six positive controls
pass and thirty injected faults are detected. Each layout includes isolated
VDD/VSS pads, a signal short and removed substrate contacts. Both APBs additionally
reject diode area, perimeter and polarity faults. LVS alone misses isolated power
pads; metal continuity alone misses substrate faults. Both checks are required.

Independent readback reconstructs every written-mask or reference-netlist fault,
recomputes metal connectivity, and reads the native comparison databases directly.
The positive controls preserve 394,080 device terminals and 197,048 primary
parameters. The original two APB substrate tests reported incomplete wiring, then
their harness tried to open a database that extraction had not produced. Fresh
source-locked repeats each reproduce the specific soft-connection rejection in
about 22 seconds. The original harness errors remain retained; generic tool
failures are not accepted as fault detection. An initial audit's overly broad
historical batch-snapshot comparison is also retained; the corrected audit binds
the selected completed case and each artifact directly.

The verified archive retains 919 logical files using 652 unique content objects,
including original failures, native databases, geometry, reference inputs, deck,
engine and independent audit. It is stored outside the dated build folders.
These results complete the experimental fault-control batch. The stock-deck
substrate warning, accepted production substrate/diode integration, larger-reference
post-fill function/timing, complete fill scope and installed production acceptance
remain open. Chunk 4 is incomplete.

The [source-controlled LVS recipe preparer](GF180_LVS_RECIPE.md) authenticates
32 upstream files and stages the two reviewed substrate/diode corrections in a
new directory. It preserves the source checkout and records every file hash.
Prepared rules still require strict native comparison and independent metal
continuity; preparation does not promote a project or installed runtime to
accepted status.

The [paired full-RC waveform audit](validation/gf180-filled-functional-2026-10-08.json)
now confirms both complete 900 nanosecond precision-candidate counter runs under
the isolated COLAMD engine. The original stimulus, models, 0.2 nanosecond maximum
step and numerical limits are unchanged. The unfilled waveform has 12,606 finite,
ordered points; the filled waveform has 12,610. An independent audit confirms
all 18 clock edges and all 18 original functional sample times by interpolation.
It also checks 5,931 recorded points in the settled intervals of each waveform,
including the counter wraparound. Both retain the original logic thresholds.

Observed maximum clock-to-output transitions are approximately 2.33 nanoseconds
in each run. These nominal measurements do not establish static timing across
all paths or operating conditions. The frozen output-delay constraint allocates
time relative to the capture clock; it is not a one-nanosecond clock-to-output
deadline. The exact engine binary is rechecked after completion. The 25-member
archive retains both full waveforms, circuits, model files, logs and source
records. This establishes the nominal before/filled counter functional control;
larger-reference electrical checks, required timing conditions and production
engine acceptance remain open.

The [six-reference extraction attempt](validation/gf180-larger-rc-gaps-2026-10-08.json)
runs the locked precision engine on the actual C/D layouts with each variant's
bundled technology. Both counter pairs complete extraction and export. The
fresh C counter decks have different internal node numbering; an independent
unique-node correspondence confirms every raw resistance record, printed
distribution weight, device-terminal incidence and raw capacitance record
against the simulated model. Byte equality is not claimed, and D does not
inherit the C waveform result.

At that checkpoint both UARTs stopped at the existing model-size bounds. The
measured C UART needed 130,773 compact capacitors and 430,791 controlled sources;
the API then allowed at most 100,000 capacitors and 250,000 controlled sources,
with 50,000 capacitors requested by default. Both APBs stopped because the RC exporter did not support
their four native diode records. The extracted APB inventory retains 22,486 MOS
devices plus four diodes with explicit area/perimeter. No electrical elements
are dropped, no limit is relaxed and no failed case is treated as accepted.
The 114-member archive preserves all six native attempts and their exact inputs.
Those retained failures motivated the following export changes.

The [native diode RC controls](validation/gf180-native-rc-diodes-2026-10-08.json)
exercise the foundry antenna cell physically abutted to its substrate/well tap
under both C and D technologies. Native diode polarity, area and perimeter are
preserved through normalization, export, topology contraction and island
analysis. All 28 native-export faults are rejected, including changed geometry,
multiplicity, polarity, model, missing devices and invalid endpoints. Both
133-point nominal DC sweeps match an independently assembled circuit, and
ngspice reads back the expected area and perimeter for every diode. The model's
IKK warning remains in the evidence; these controls do not qualify high-injection
behavior, other device families or full PDK signoff. The 891-member archive also
retains the earlier failed control attempts.

Larger models can request explicit capacitor and auxiliary-source allocations.
Defaults remain 50,000 capacitors and 250,000 sources; supported allocation
ceilings are 250,000 and 1,000,000 respectively. The selected source allocation
is retained and enforced through finalization, contraction and island analysis.
Counts are checked before output mutation. This does not discard elements,
change the electrical equations or promise simulator capacity. The current
larger-reference run explicitly requests 200,000 capacitors and 600,000 sources
and measures peak memory. Native SPICE continuation records are also supported
without changing port order, device parameters or line formatting.

The [anchored compact-RC checkpoint](validation/gf180-affine-rc-2026-10-09.json)
now retains all eight C/D UART/APB before/filled exports. UART preserves 22,588
devices; APB preserves 22,490, including its four diodes. The original all-node
audit exposed a common-mode residual. Correcting its independent oracle and
using 60-digit arithmetic confirmed a separate roundoff defect in the saved
helper coefficients. That failed evidence is retained.

The corrected exporter represents each weighted sum as its largest-weight input
plus weighted differences from that input. This preserves zero capacitor voltage
when all physical nodes move together, without adding sources or changing limits.
The parser verifies each affine anchor, both helper layers and isolated buffers;
the conservation audit handles differential controls with compensated sums.
Both earlier encodings remain authenticated and usable.

All eight authenticated native extractions have been reprocessed; normalized
Magic inputs remain byte-identical, and devices, wire resistors, ports and model
element counts are preserved. Independent checks pass all 32 voltage-pattern
trials across 196,958 to 201,502 physical nodes per export at the original
1e-10 relative / 1e-10 aF absolute limits. Every common-mode current and energy
residual is exactly zero in this evaluator. Windows SPARSE and Linux SPARSE/KLU
each pass the native full-matrix AC, common-mode, fault and floating-node transient
controls; production transient differences are below 0.931 microvolt against
the expanded reference, within the existing 2 microvolt bound. The 1,548-test
Windows suite passes with 62 skips, and 54 focused RC tests pass on each OS.

The deduplicated evidence archive is stored outside dated build folders and
verified by reading every unique object. This establishes bounded numerical and
export correctness, not calibrated extraction or full-layout transistor-level
behavior. Larger-reference post-fill function/timing, complete fill-rule coverage,
production connectivity acceptance and installation acceptance remain open.
Chunk 4 is incomplete.

Fresh execution of the source-controlled LVS recipe now passes all eight
counter/APB controls. Independent readback verifies 213,376 positive device
terminals and 106,696 primary parameters. The original APB timeout remains
retained; completed counter controls were reused in the continuation. Source,
native results and the independent audit are preserved in a verified 20 MB
archive outside dated build folders. This establishes recipe reproducibility,
not installed combined acceptance or complete chunk 4 qualification.

The [written-metal continuity module](GF180_METAL_CONTINUITY.md) now derives
every placed-cell supply from independent library GDS and the captured OpenDB,
and checks the complete port set and its physical anchors. On each OS, six
actual layouts and thirty retained physical controls reproduce the independently
audited results, covering 16,592 placements and 33,184 supply terminals. A source
command authenticates database/preview hashes against the finished job and
preserves diagnostics. Automatic finished-job dispatch and combined LVS
acceptance still need integration and fresh installed-runtime verification.

The [final-layout reference exporter](GF180_REFERENCE_EXPORT.md) now generates
and retains the independent transistor reference in configured GF180 finish
jobs. Six actual C/D OpenDB exports match the earlier audited references exactly,
covering 16,592 instances and 98,524 devices; Windows readback reconstructs all
six saved results. Reference artifacts and their source CDL survive macro export
without implying an LVS pass. The full Windows suite passes 1,600 tests with 62
skips, and 74 focused checks pass on each OS. Bundling these inputs and combining
strict native LVS with written-metal acceptance remain open.

The [C APB nominal device audit](validation/gf180-device-c-apb-2026-10-09.json)
independently checks all 63 frozen assertions (147 output bits) over 57,534
waveform points, at 5 V / 25 C with the original 20 ns physical clock and 10 fF
output loads. All assertions pass; 1,035,612 measured input samples agree with
the frozen stimulus within the declared 1 microvolt bound. Sampled-output
substitutions fail all 147 corresponding comparisons. This establishes the
device-only baseline for that design, not post-fill behavior or all-path timing.
The other C/D full-program baselines and before/filled RC checks retain their
separate execution and acceptance requirements. Chunk 4 remains incomplete.

The first [complete APB before/filled RC attempt](validation/gf180-apb-startup-2026-10-09.json)
failed before producing usable waveforms under a 6 GiB per-process address-space
guard. Both runs preserved all devices, extracted resistors and capacitance
elements and used the identical frozen test deck. The simulator returned zero
despite its aborted transient; the checker correctly rejected both results.
An isolated build adding only a failure-status print reproduced the before-case
failure as `KLU_OUT_OF_MEMORY` (-2), with no numerical rank result. The generic
singular-matrix message therefore does not establish a connectivity defect.
The filled case has its own retained startup failure; its exact internal status
has not been independently diagnosed. Resource-capacity investigation and both
complete functional waveforms remain required. Original failures, the unchanged
inputs' archive dependencies and the exact diagnostic binary are retained.

The [combined GF180 finish integration](GF180_FINISH_CONNECTIVITY.md) now requires
both strict native device/substrate comparison and complete written-metal
acceptance for configured profiles. All six retained filled layouts pass;
the deliberately disconnected C-counter VDD port is rejected even though its
native device graph matches. Current-source Windows and Linux saved-result
reconstruction agrees byte for byte on all seven cases. The full independent
229-cell source preparation and two fresh C/D counter implementations with
audited macro exports have separate retained checkpoints. Default runtime
bundling, installed acceptance, full before/filled electrical timing and
complete fill-rule coverage remain open; chunk 4 is not complete.

The subsequent [runtime-input integration](GF180_RUNTIME_INPUTS.md) enables
complete GF180 connectivity preparation in new runtime builds. A real cold-cache
download and network-disabled Linux reconstruction produce the same C/D profiles
as the verified configured counter flows. This closes the default builder
integration gap; actual newly built image and installed acceptance remain separate.
The new image has subsequently built successfully and passed an independent
audit of all 54,396 locked files in its exact exported archive. Fresh installed
execution retains its own acceptance gate.

The [fresh Linux installation](validation/gf180-installed-linux-2026-10-09.json)
then passes 34 digital checks, all 18 declared timing pairs and seven native
tool controls. Independent readback verifies 1,391 artifact bindings and
reconstructs the saved results. The actual installed engine accepts the C/D
counter positives and rejects four deliberate physical faults: one VDD-port
open and one signal short per stack. Both VDD opens disconnect 790 supply
terminals even though native device comparison matches. Complete evidence is
archived outside dated folders. The subsequent
[fresh Windows installation](validation/gf180-installed-windows-2026-10-09.json)
passes the same 34 digital checks, 18 timing pairs and seven native tool
controls, with 1,391 independently verified artifact bindings. Its separate
C/D native controls likewise accept both valid counters and reject all four
physical faults. Exact desktop-package acceptance remains separate; these
unfilled counter checks cannot close the post-fill electrical, timing or
complete fill-coverage gates.

The [installed macro audit](validation/gf180-installed-macros-2026-10-09.json)
checks exports from all four fresh installed C/D counter jobs. Windows reopens
each complete job and reproduces its 102 native macro members byte for byte,
including the manifest, all 94 artifacts, the constraint and six source notices.
Independent audits retain all 80 required reference/connectivity artifacts and
bind the exports to the archived original job inputs and results. No post-fill
or complete process acceptance is inherited from this portability check.

The [C UART audit](validation/gf180-device-c-uart-2026-10-09.json) and
[D UART/APB audits](validation/gf180-device-d-nominal-2026-10-09.json) complete
the four larger nominal device-only baselines together with the earlier C APB
result. Every frozen assertion passes and the inputs agree with the declared
stimulus. These baselines have no wire RC and cannot establish post-fill timing.

The subsequent [C APB full-RC supervisor failure](validation/gf180-apb-supervision-2026-10-09.json)
is retained separately from the earlier allocation failure. Its runner killed
the simulation after a progress-file replacement failed on the mounted Windows
drive; it produced no complete waveform. The repaired supervisor keeps its
authoritative progress on the native filesystem and treats the Windows copy as
best-effort. Permission-failure controls pass, while the unchanged complete RC
program still requires a finished waveform and independent acceptance.

The [post-fill timing batch](GF180_POSTFILL_TIMING.md) now passes all 18 filled
reference cases on the separate C/D typical interconnect models and three
captured library conditions. Both OS audits reproduce 78 native outcomes,
including 42 rejected capacitance, missing-clock and missing-antenna controls.
The application now retains antenna input loads in physical netlists and
rejects missing or partial parasitic annotation, unresolved load diagnostics
and stale reports from a previous scenario. Both corrected APB netlists pass
fresh equivalence proofs; other netlists remain byte-identical. The permanent,
verified archive retains successful and rejected experiments. This is bounded
reference timing acceptance; full fill integration and coverage, independent
full-RC programs and subsequent process/package gates remain open.

See [release targets](PUBLIC_RELEASE_TARGETS.md),
[digital qualification](DIGITAL_PLATFORM_QUALIFICATION.md),
[bundled PDK scope](PDK_GUIDE.md) and
[release gates](RELEASING.md) for the existing evidence boundaries.
