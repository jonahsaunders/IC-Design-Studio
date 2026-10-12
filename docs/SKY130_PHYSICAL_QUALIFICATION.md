# SKY130 physical coverage: chunk 6 in progress

The [execution record](validation/sky130-physical-progress-2026-10-11.json)
captures the original counter, UART and APB final layouts. Chunk 6 remains open.
Zero geometry markers alone do not establish complete physical coverage.

| Check on the original final GDS | Counter | UART | APB |
|---|---|---|---|
| ORFS KLayout, FEOL/BEOL/off-grid enabled | 0 markers | 0 markers | 0 markers |
| Volare KLayout, all five optional groups enabled | 0 markers | 0 markers | 0 markers |
| Magic full geometry, no ignored rules | 0 markers | 0 markers | 0 markers |
| Supplemental poly antenna | Pass | Pass | Pass |
| Native Magic antenna | No findings | No findings | Three contact-stage findings |
| Supplemental all 13 antenna etch stages | Pass | Pass | Pass |
| Strict transistor/body/supply/port LVS | Match | Match | Match |

Both complete geometry engines reject injected poly-width and Metal1-width
faults on a copy of the original counter. These controls prove the selected
rules execute; they do not prove every published rule is implemented.

## Antenna coverage and the resolved contact discrepancy

The native checker accepts an isolated poly wire whose antenna ratio exceeds
the published limit. The new [poly check](../scripts/sky130_poly_antenna.drc)
executes the published 0.180 micrometre sidewall thickness and maximum ratio 50.
It accepts the legal coupon, rejects the oversized coupon, and distinguishes
5 nm below, exactly at, and 5 nm above the boundary. All three reference layouts
pass this supplemental check. Upper metals cannot supply protection during
poly etch and are deliberately absent from this stage's connectivity model.

The native local-interconnect control does reject its deliberate fault. This
does not validate every other etch stage or the native contact-area calculation.

The [subsequent antenna record](validation/sky130-antenna-progress-2026-10-11.json)
corrects the initial attribution: Magic's three APB findings occur at **via4**,
whose lower conductor is Metal4. The earlier via3 measurements addressed a
different etch stage and remain preserved as historical diagnostics. Each
affected net has one 0.64 square micrometre via4 cut and 0.213 square micrometres
of connected gate. Independent native measurements give 3.00469483568075,
below the limit of 6 before diode credit.

Source inspection and an isolated logging build expose two contact-counting
defects in Magic 8.3.684. Array calculations mix internal tile dimensions with
CIF contact dimensions. Separately, each fragment created by overlapping
contacts is counted as at least one full cut. Six exact via3 controls and four
exact via4 controls reproduce four incorrect native classifications: two
missed 16-cut via3 faults, one missed four-cut via4 fault, and one false failure
on a single stacked via4 cut. The latter reproduces APB's reported 801.252
normalized ratio despite its physical ratio being below 6. Original GDS files
and native failed results are preserved; no production engine was replaced.

The new [staged checker](../scripts/sky130_staged_antenna.drc) uses the published
Table Ig profile, matching the captured five-metal technology's 1.2 micrometre
top metal. It measures actual polygon union area or sidewall perimeter and
adds connectivity only as each of the 13 etch stages is reached. Diode area,
the one-time diode bonus, and substrate-short exemption follow the published
definitions. The via4 and Metal5 table descriptions contain copied lower-layer
names; the explicit rule identifiers and thicknesses govern this profile.
This interpretation does not qualify other stacks or device classes.

All three unchanged reference GDS files pass every stage. The checker also
classifies all ten exact-cut controls correctly. The independent
[fixture generator](../scripts/sky130_antenna_controls.py) adds 178 rectangular
controls: 5 nm below, at and above each boundary, diode credit, substrate
shorts, future-layer and disconnected protection, connected gate aggregation,
unconnected metal, and a single bonus shared by multiple diodes. These isolate
antenna arithmetic and connectivity; they are not geometry-legal test chips.
The exact rational oracle expects 90 failures and 88 passes. The
[report auditor](../scripts/check_sky130_antenna_controls.py) matches every
native marker location, gate area, etched area, diode area and ratio on both
Windows and Linux. Twenty-four evidence-rejection and inventory tests pass on
each OS. Native execution here uses Linux KLayout 0.30.5; Windows readback is
not a fresh Windows engine or consumer-installer qualification.

The diagnostic APB log contains 4,000 complete contact records and three
interleaved records that are not claimed reconstructed. Its raw log, build
patch, exact source identities and controlled reproductions are retained.
The earlier all-stage v1 record carried incorrect via4-only metadata; the
source-controlled deck's v3 runs provide the accepted all-stage evidence.

## Density and rule inventory

Density is now measured over each original declared die rectangle: 200 by
200 micrometres for counter and 400 by 400 for UART/APB. Initial measurements
used the cell's smaller bounding box; those captures are retained as rejected
measurements. Neither version establishes density acceptance. The published
manual and installed deck have different density descriptions; applicable
windows, mask interpretation, fill requirements and thresholds still need
explicit reconciliation.

The first native waffle-fill counter pilot passes both full geometry engines,
but remains below the installed density helper's minimums for active material,
local interconnect and Metal5: 14.39%, 26.99% and 32.50%, versus 33%, 35% and 45%.
These are helper screening limits; the complete manual interpretation is still
open. The candidate and its raw reports are retained as unaccepted evidence.

The [rule inventory](qualification/sky130-rule-inventory.json) preserves all
601 periphery rows from 50 published tables at upstream revision
`7198cf647113f56041e02abf3eb623692820c5e1`. Its source lock covers 165 rule
documents, including antenna, assumptions and connectivity. Each periphery row
retains its value, flags, description, source identity and candidate deck
locations. Commented code remains visible. Text matches are search aids and
cannot promote a row to passing coverage. Every row remains explicitly
unreviewed until applicability and execution evidence have been reconciled.
The first source capture selected CSV/RST documents. The subsequent pin-export
record captures all seven referenced layer/extraction TSV files at the same
upstream revision, with verified Git blob identities. Their interpretation
remains part of the rule review.

The separate [error catalog inventory](qualification/sky130-error-rule-inventory.json)
retains all 1,556 published error records. Periphery tables alone omit named
dummy-fill, core and chip rules. In particular, the error catalog includes
`fomdmy` width, spacing, implant and well constraints. Exact-name links are
navigation aids; neither inventory establishes execution or applicability.

Sources are the [published periphery rules](https://skywater-pdk.readthedocs.io/en/main/rules/periphery.html)
and [antenna rules](https://skywater-pdk.readthedocs.io/en/main/rules/antenna.html),
captured at the immutable revision above. Manual content is copyright the
SkyWater PDK Authors and contributors, under [Apache-2.0](../licenses/Apache-2.0.txt).
Volare KLayout deck excerpts retain their GPLv3 terms, provided by this
repository's [license](../LICENSE). Magic technology excerpts retain their
upstream Apache-2.0 terms. Exact source files and notices are in the evidence
archive.

## Strict original-layout connectivity

The [connectivity record](validation/sky130-connectivity-progress-2026-10-11.json)
binds all three original GDS files to native four-terminal transistor comparison.
Counter, UART and APB match 204, 2,580 and 2,224 combined transistors respectively,
with all 8, 15 and 30 declared boundary ports accounted for. This covers the
selected HD standard-cell circuits, not every SKY130 device family.

The [reference adapter](../scripts/sky130_lvs_reference.py) verifies every
instance and terminal against the captured implementation database, including
fillers and body pins, before using the independently supplied master CDL.
It fixes CRLF port parsing and standalone CDL separators without removing
terminals. The [native reader](../scripts/sky130_cdl_reader.rb) implements only
explicit symbolic short connections; ordinary resistors retain their values.
The pinned CDL's micrometre dimensions use an explicit numeric scale.

The layout comparison uses drawn conductors and physical contacts. Substrate
and well connections use KLayout's [soft connection checks](https://www.klayout.de/doc/manual/lvs_connect.html)
to reject missing metal supply wiring. No global supply ties, implicit
connections or equivalent-pin declarations are introduced. Each top pin
annotation must overlap exactly one metal island; its label is attached within
that overlap on a comparison copy whose masks are verified unchanged. Pin
markers never become conductors. The original pin-extent problem is addressed
by the independently captured boundary-pin export described below.

The [port auditor](../scripts/check_sky130_lvs.py) requires graph-paired names
and full boundary coverage. APB's `pready` and `VDD` are physically tied, as
specified by the independently flattened CDL tie cell. Their paired name group
preserves both declared ports; missing, permuted or unexpected names fail.

Eleven native counter controls include two valid cases and nine rejected faults:
signal open/short, supply short, substrate/well contact opens, port swap/removal,
device-width change and incorrect device body. Seven separate native reader
controls verify short semantics, preserved resistor values, transistor dimensions
and rejection of unsupported cards. Windows and Linux independently re-create
the reference inputs and adapted GDS, re-read the reports and produce the same
audit digest. Seventeen focused rejection tests pass on each OS without skips.
Native engine execution remains Linux KLayout 0.30.5.

Earlier parser, scale and label failures remain in the archive. In particular,
an initial flattened control retained an unwanted substrate label and failed
its valid cases; it is not accepted as successful fault coverage. The corrected
batch runs the repository's exact source and passes every control.

## Boundary-pin export

The [pin-export record](validation/sky130-pin-progress-2026-10-11.json) closes
6 counter, 13 UART and 28 APB `x.5` findings. The DEF stream contained pin
annotations extending past the end of routed metal. The application now
captures the actual boundary-pin boxes independently from OpenDB and exports
their missing metal. It rejects absent routes, disconnected islands, mismatched
annotations, changed source files and undeclared mask changes. Every original
annotation and non-pin mask is preserved.

All three corrected exports pass both complete enabled native geometry decks,
strict transistor/body/port comparison, all 13 selected antenna stages and the
additional all-layer pin-containment check. Virtual substrate pin containment
uses the manual's complement-of-nwell definition. The actual Runner, saved-job
validator and macro exporter preserve the source GDS, independent inventory,
capture worker, checkpoint and report. These runs use the existing routed
checkpoints; they are not fresh place-and-route or installer tests.

Windows and Linux reconstruct identical corrected GDS files and audit the native
reports and macro archives. All 34 focused pin/connectivity tests pass on both
OSes without skips. The portable records retain the exact executed source
hashes. A deduplicated archive outside dated folders preserves 561 evidence
files in 410 unique blobs and passed complete byte-for-byte readback.

The new SKY130 hooks change shared application files. Chunk 5's original IHP
record remains bound to the exact previously tested source, now explicitly
retained in its [historical source snapshot](validation/ihp-fill-tested-source-2026-10-11/manifest.json).
That snapshot does not imply a new IHP native run with the current application.

## Fill diagnostics

The [additional fill auditor](../scripts/sky130_fill_geometry.py) checks
fill-to-fill spacing and area omitted by some native deck expressions. Its
selected conservative block profile also checks dummy diffusion dimensions,
implant/well exclusions, grid, unchanged circuit geometry and the original
die extent. Native `PASS` alone is insufficient: an experimental candidate
contained sub-minimum metal3/metal4 fill even though both native decks passed.
Boundary and deliberate-fault tests verify the extra checker. This checker is
one part of the required gate, not a complete rule or density acceptance claim.

## Remaining gate

The [fill progress record](validation/sky130-fill-progress-2026-10-11.json)
binds the final counter/UART v20 and APB v22 candidates. Their original
200/400 micrometre dies are unchanged. All three pass both enabled native
geometry decks, all 13 selected antenna stages, supplemental fill/pin checks
and the unchanged eight-layer density screen. Native Magic density measurements
agree with independent polygon-area calculations. This remains a screen,
not complete foundry density qualification.

Added fill and same-footprint rail decaps stay outside a 9 micrometre circuit
clearance. Windows and Linux independently reconstruct the selected decap
placements and verify every drawn mask within that clearance. Nonconducting
body-pin annotation changes are explicitly recorded. Every original circuit
device record, non-supply capacitor pair and original-node resistance value
is unchanged in the final native extraction: 1,194 counter, 18,580 UART and
18,300 APB capacitor pairs. All new devices have the required rail-only decap
connections; every native missing-terminal message identifies one of those
devices and its expected supply. The check uses exact rational arithmetic,
rejecting even arbitrarily small injected capacitance changes.

This is nominal native circuit invariance with ideal supplies. It does not
establish distributed RC timing, supply integrity or extractor calibration.
The earlier dense-fill counter changed circuit capacitance and remains a
retained failed candidate; it is not used for an unchanged-model handoff.

The original CDL's `diode_2` cell was empty, so the earlier transistor comparison
did not test APB's three antenna diodes. The
[diode adapter](../scripts/sky130_diode_lvs.py) now uses an
[independent pinned library model](https://github.com/fossi-foundation/skywater-pdk-libs-sky130_fd_sc_hd/blob/9cb2d7cb8ed4619094263614039a61b6b2d22a88/cells/diode/sky130_fd_sc_hd__diode_2.spice).
Every polygon layer of that library cell matches the installed GDS. Its
independent reference area and perimeter agree with its own source layout.
All three final designs pass the expanded diode/transistor/body/port comparison.
Native APB controls reject a missing diode, open cathode, reversed polarity,
wrong area and wrong perimeter. The initial adapter accepted the area fault;
the corrected deck explicitly enables both dimension comparisons and its
successful controls supersede that failed attempt.

Windows and Linux produce identical physical, circuit and diode readback
records. The recorded regression suite runs 128 tests per OS, with six Windows and
five Linux tool-configuration skips; six additional diode tests pass per OS
without skips. All 32 newly added implant, applicability, invariance and diode
tests pass without skips. Native verification execution remains Linux.
The new durable archive preserves 1,959 files in 1,399 unique blobs, including
raw native captures and rejected recipes. Its 920 MB compressed contents passed
complete hash-verified readback outside the dated workspace folders.

The [raw implant checker](../scripts/sky130_raw_feol.py) supplements native
engines with drawn-mask doping, width, spacing, area, hole and HVTP enclosure
checks. The [implant execution batch](validation/sky130-rule-execution-2026-10-11.json)
also closes the selected low-voltage implant enclosure and butting-edge checks.
It removes only actual coincident portions when applying 0.125 micrometre
enclosure, requires zero enclosure on those butting portions and applies
0.130 micrometre spacing to opposite-doping non-butting edges. Partial butting
cannot exempt a whole edge. All 41 checks and profile guards pass on each
final layout; all 19 geometry/binding tests pass on Windows and Linux without
skips. The [execution ledger](../scripts/sky130_rule_execution.py) binds 18
published requirements to these actual checks and rejects missing checks,
missing guards, failed profiles and mismatched layouts. Manual merging is
conditionally clear because no subminimum implant spacing remains.

The [low-voltage geometry batch](validation/sky130-low-voltage-2026-10-11.json)
adds 43 reviewed requirements for wells, diffusion, gate dimensions, NPC and
local contacts. All three final layouts pass with identical Windows/Linux
ledgers; all 46 implant, geometry and binding tests pass without skips.
Channel width is measured across the diffusion ends of each gate, independently
of its orientation. Partial standard-cell markers, gate terminations, bent
gates, missing well/tap/source contacts, unsupported process selectors and
missing companion implant checks are rejected. Boundary tests distinguish
concave diffusion corners from convex ones and reject even a five-nanometre
enclosure, spacing or size error. The earlier exploratory corner-sign check is
retained but superseded. No submitted geometry or rule threshold changed.

The [interconnect batch](validation/sky130-interconnect-2026-10-11.json)
adds another 56 requirements for metal width/spacing/area/holes, exact square
contacts and conductor enclosure. Physical metal checks combine routed metal
and fill, while only drawn conductors can establish contact enclosure.
All three final layouts pass with identical Windows/Linux ledgers and all
62 combined geometry/binding tests pass without skips. Adjacent enclosure
uses the actual deficient portions at each cut corner, following the pinned
reference deck algorithm. The APB library's T-shaped `nor4b_2` contact passes;
an injected five-nanometre corner fault fails in every orientation. The first
checker promoted partial deficiencies to whole sides and incorrectly rejected
that contact. Its source and report are retained as a rejected checker.
The correction changes no layout or physical threshold. Huge-metal spacing
and other unbound requirements remain open.

The [applicability review](../scripts/sky130_block_applicability.py)
retains all 601 periphery source rows. The
[additional applicability batch](validation/sky130-manual-progress-2026-10-11.json)
establishes 101 further explicit absence proofs per final design:
207 rows now have measured absent operands,
77 explicitly say NA, 27 are advisory, 61 belong to the other backend,
117 have reviewed execution bindings, 111 still require execution review and
one needs a source definition.
An absent operand is a block-specific finding, not a passing device test.
Both operating systems produce the same updated review and pass all 12
applicability rejection tests without skips. The high-voltage well checks
include both HVI and the separate thin-oxide high-voltage well identifier;
rules requiring voltage declarations or ambiguous enclosure targets stay open.

Chunk 6 still requires complete per-rule/error-catalog reconciliation,
remaining device/layer semantics and density/window/oxide applicability.
The published `x.20` IP-block pin-spacing rule has no numeric
value or unit; no threshold is invented. Final bound timing and equivalence,
application integration and delivered Windows/Linux execution also remain.
The retained standalone checks do not yet provide the complete gate.

The durable evidence archive contains 707 files, including rejected attempts,
and was read back completely against its manifest. A second 527-file archive
preserves the antenna diagnosis and stage controls with complete readback.
The third archive preserves 722 files covering connectivity, controls and the
unaccepted native fill pilot, also with complete readback.
Their identities are recorded in the respective execution records. Chunk 5's
original acceptance record remains unchanged; its historical source binding
is now explicit as described above.
