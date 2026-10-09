# PDK qualification in twelve chunks

The target is analog and digital design on SKY130, GF180MCU C/D and IHP SG13G2.
No target is currently qualified for complete-chip tapeout. Work proceeds in the
order below; a passing small reference design keeps its original scope.

The [machine-readable matrix](qualification/pdk-matrix.json) is the coverage
record. It includes 125 process/workflow requirements and all 255 bundled catalog
entries, including utilities and unavailable devices. Every requirement points to
a defined fixture, procedure, expected result, operating conditions, remaining
automation work and status. Each device has separate interface, simulation and
physical tests. These are test contracts; many are not executable yet.

The matrix also records the exact package revisions, source-lock hashes, model
include sections, device terminal/parameter mappings, digital libraries, metal
options and current digital operating points. It does **not** equate this bundled
subset with the complete upstream PDK. Upstream completeness and the remaining
device-specific operating envelopes are explicit open requirements.

## Sequence and gates

| Chunk | Achievable batches | Completion gate |
|---|---|---|
| 1. Qualification matrix | Inventory bundled inputs; enumerate tests and missing upstream coverage; validate identities and completeness. | Every requirement has a test, expected result and status. Missing coverage is visible. This planning gate is defined; process execution is not qualified. |
| 2. Toolchain | Compatible KLayout CLI; hosted OpenROAD result; clean Linux install; clean Windows/WSL install; native rule coupons and fault controls. | Exact fresh runtimes execute every required valid/invalid case correctly. |
| 3. GF180 geometry | Integrate via pitch; integrate tap spacing; counter; UART; APB. Establish a separate matched D platform. | Production-flow geometry, antenna, extracted timing and equivalence pass without changing the original design constraints. |
| 4. GF180 density | Resolve active/poly fill; resolve each metal layer; check exclusions; rerun all post-fill checks. | Filled production references pass required density/geometry, connectivity, extraction, timing and equivalence. Experimental counter results retain their narrower scope. |
| 5. IHP geometry/fill | Resolve the twelve observed findings, grouped by rule; recheck counter; UART; APB. | Complete final-layout rules, connectivity and extracted performance pass. |
| 6. SKY130 rules | Reconcile rule inventory; enable FEOL; check density/antenna; final-GDS LVS; negative controls. | Every required rule group executes; no silently disabled coverage or unexplained violations. |
| 7. Devices | Reconcile upstream inventory; MOS; resistors; capacitors; diodes; bipolar; remaining devices. Treat IHP RF separately. | Every supported device passes terminal/parameter/model, operating-envelope, layout and extracted-connectivity tests. Unsupported required devices remain blockers. |
| 8. Extraction/corners | Wire coupons; vias; device parasitics; coupling/fill; independent RC corners; complete required PVT/RC pairs. | Independent references agree within frozen, source-backed tolerances and injected faults fail. |
| 9. Analog blocks | Mirror; differential pair; amplifier; reference; oscillator; noise/statistics; separate IHP bipolar and RF batches. | Schematic and extracted results meet numerical specifications fixed before execution, across declared conditions. |
| 10. Digital/mixed signal | Select larger controller; functional coverage; clock/reset review; physical/timing closure; analog/digital integration. | Functional, equivalence, all-mode timing/electrical and final-layout checks pass. |
| 11. Complete chips | Assemble chip; electrical-rule review; ESD/latch-up review; EM/IR review; I/O/package review. | Every required chip-level check passes on final geometry and the actual package/modes. |
| 12. Delivery/tapeout | Exact Windows package; exact Ubuntu package; independent handoff reproduction; submission preparation; external acceptance. | Consumer workflows pass and the required foundry/shuttle acceptance covers the precise submitted design, revisions and waivers. |

## Locked starting scope

| Analog target | Bundle revision | Indexed / placeable | Physical option and present digital coverage |
|---|---|---|---|
| SKY130 A | `24bc6d0bfd6a0224` | 74 / 71 | Local interconnect plus five metals; HD digital library; 3 library by 3 RC conditions. |
| GF180 C | `627ca682d68e1e92` | 68 / 64 | Five metals, 0.9 micrometre top metal, MIM, HRPOLY1K; digital 9-track 5 V, 5LM_1TM/9K; 3 library by 1 RC condition. |
| GF180 D | `7dd87219f1333dbb` | 68 / 64 | Five metals, 1.1 micrometre top metal, MIM, HRPOLY1K; separate `gf180d` 9-track 5 V / 5LM / 11K production references; both installed-runtime reference gates passed. |
| IHP SG13G2 | `3abac20fcb57e184` | 45 / 35 | Five ordinary and two top metals; SG13G2 digital cells; 3 library by 1 RC condition. MOS, bipolar and RF qualification remain distinct. |

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
prior limited evidence without claiming the complete test passed. Schema 3 retains
the chunk 2 toolchain references, which require the complete,
hash-bound [acceptance record](validation/toolchain-2026-10-07.json). It requires
both operating systems, valid/fault controls and every required hosted step on
the recorded source. It separately binds the [chunk 3 acceptance record](validation/gf180-geometry-2026-10-07.json)
to current production evidence, both operating systems, actual rule/fault controls,
all required timing conditions and the captured C/D technologies. Device rows,
density and later chunks cannot inherit either pass. Later completed gates need
their own reviewed acceptance schema and records;
preserve previous failures rather than merely changing a status string.

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

See [release targets](PUBLIC_RELEASE_TARGETS.md),
[digital qualification](DIGITAL_PLATFORM_QUALIFICATION.md),
[bundled PDK scope](PDK_GUIDE.md) and
[release gates](RELEASING.md) for the existing evidence boundaries.
