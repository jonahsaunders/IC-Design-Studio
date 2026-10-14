# SKY130 physical coverage: chunk 6 in progress

The [execution record](validation/sky130-physical-progress-2026-10-11.json)
captures the original counter, UART and APB final layouts. Chunk 6 remains open.
Zero geometry markers alone do not establish complete physical coverage.

The latest [grid/window diagnostics](#grid-and-density-window-diagnostics)
preserve fresh CI-layout measurements and the remaining completion blockers.

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
The correction changes no layout or physical threshold.

The [wide-metal batch](validation/sky130-wide-metal-2026-10-11.json) adds
the eight large-metal and nearby attached-feature requirements for the
selected Manhattan profile. All three layouts pass the complete companion
checks and produce identical Windows/Linux ledgers; 91 combined tests pass
per OS without skips. The final blocks contain no m1–m4 regions both wider
and longer than 3 micrometres. Separate non-empty controls exercise the strict
3 micrometre boundary, notches, drawn/fill proximity and near/far portions of
attached wires. Clipped error edges prevent a short wide section from
reclassifying an entire long wire. Other geometry profiles remain separate.

The [additional context review](validation/sky130-context-review-2026-10-11.json)
establishes 28 further absence decisions using exact photo-device operands,
module-only via options, named-cell exceptions and other explicit selectors.
The published floating-label rule `x.17` is retained as advisory because its
description explicitly excludes it from the tapeout gate; required floating
connectivity `x.22` stayed open at that checkpoint. Both low-voltage checkers now reject the
published UHVI selector 74/22, and gate classification explicitly requires
opposite diffusion ends. These are additional guards, not new exceptions.

The [butting-operand audit](validation/sky130-butting-review-2026-10-11.json)
finds no diffusion/tap interaction in any final block and records four further
requirements as absent operands. The proof rejects full/partial shared edges,
corner touches and invalid overlaps; it does not claim non-empty butting
device qualification. All 92 current applicability/geometry/binding tests
pass per OS without skips, and both final ledgers match. Six additional
published diagrams are captured at the same pinned revision for continued
definition review; the diagrams alone do not close a requirement.

The [global geometry review](validation/sky130-global-review-2026-10-11.json)
adds the three distinct orthogonal-angle records, the remaining-layer
45-degree requirement and complete pin-polygon containment. Exact source
record identities prevent the repeated `x.2` names from absorbing an NA row.
Every unmerged polygon edge is checked, including holes, hidden internal
edges, hierarchy and fill. The 442-purpose map combines the published GDS
table, installed layer map and explicitly documented native fill/outline
purposes. Unknown polygon purposes fail. Pwell and isolated pwell use the
published C3 definitions; fill cannot establish pin containment.

That review also establishes 27 measured absent-operand decisions for TUNM
and specifically marked HV/VHV targets. The published GDS table supplies
TUNM 80/20 and diff.hv 65/8. Independent operating-voltage tagging obligations
remain open; the absence of a drawn marker does not establish those obligations.

The [mask/context review](validation/sky130-mask-review-2026-10-11.json)
adds executable maskAdd/maskDrop core containment and restricted mask-data
placement checks, with no special placement exemptions invoked. Native fill
and waffleDrop overrides remain distinct purposes. Eleven further absence
decisions measure pad/RDL operands, cpmm exception context, condiode labels
and gates outside standard-cell identifiers. The explicit `poly.X.1` standard-cell
exception applies only because every gate is wholly contained; a straddling
gate is refused. This does not qualify analog-device W/Ls.

The [complete connectivity review](validation/sky130-floating-review-2026-10-11.json)
now executes `x.22` through all contact levels. All 106 counter, 1,304 UART and
1,204 APB components reach a gate, diffusion/tap or top-level metal pin.
No floating/tie labels or standard-cell exemptions are used. The controls
reject a disconnected metal/via stack that passes a mere neighbor-contact
test, removal of any contact level, wrong-layer pins and annotation bridges.
All submitted conductor/root area must appear in the extracted components.
Two APB poly-short annotations are wholly inside already continuous poly;
they add neither conductor nor roots. An annotation extending outside poly
or bridging a gap fails. The first unsupported-annotation profile and its
rejected results remain preserved. All 123 combined tests pass per OS without
skips and the final ledgers match exactly.

The new archives passed complete readback and remain outside dated folders.
The global/mask records also reference a verified supplement containing their
exact execution and layer-map construction drivers. These checks use KLayout
0.30.5's polygon library on both operating systems; they do not assert fresh
Windows standalone-engine or installer qualification.

The [applicability review](../scripts/sky130_block_applicability.py)
retains all 601 periphery source rows. The
[additional applicability batch](validation/sky130-manual-progress-2026-10-11.json)
establishes 101 further explicit absence proofs per final design:
277 rows now have measured absent operands,
77 explicitly say NA, 28 are advisory, 61 belong to the other backend,
133 have reviewed execution bindings, 24 still require execution review and
one needs a source definition.
An absent operand is a block-specific finding, not a passing device test.
Both operating systems produce the same updated review. The high-voltage well checks
include both HVI and the separate thin-oxide high-voltage well identifier;
rules requiring voltage declarations or ambiguous enclosure targets stay open.

Chunk 6 still requires complete per-rule/error-catalog reconciliation,
remaining device/layer semantics and density/window/oxide applicability.
The published `x.20` IP-block pin-spacing rule has no numeric
value or unit; no threshold is invented. Final bound timing and equivalence,
application integration and delivered Windows/Linux execution also remain.
The retained standalone checks do not yet provide the complete gate.

## Explicit error-catalog reconciliation

The initial [2026-10-14 reconciliation](validation/sky130-error-reconciliation-2026-10-14.json)
retains all 1,556 error IDs in source order for counter, UART and APB. It binds
82 records to the existing final-layout evidence: 46 angle checks, eight pin
containment checks, seven complete-conductor connectivity checks and 21 absent
floating/tie label operands. The remaining 1,474 records are explicitly
unreviewed. Error IDs and periphery rows are separate counts; this does not
reduce the 24 remaining periphery execution reviews.

The [reconciler](../scripts/sky130_error_reconciliation.py) uses literal error
IDs, descriptions, layer purposes and source-record identities. It checks
all six companion profiles, every mandatory guard, their source hashes,
the exact GDS/top identities and extraction-area accounting. A same-name match
cannot establish coverage. The `s`-series chip records do not inherit the
`r`-series block results. Label absence is recorded as absence, not a passing
test of non-empty exception handling. Octagonal subset checks on diffusion,
tap, poly and contacts cite the actual stronger orthogonal checks; the general
`x.3a` check alone excludes those layers.

Reproduce the committed report with the pinned `klayout==0.30.5` dependency:

```sh
python -m scripts.sky130_error_reconciliation --check
python -m unittest tests.test_sky130_error_reconciliation -v
```

The [regressions](../tests/test_sky130_error_reconciliation.py) inject a
one-nanometre slope error for every selected angle record, uncovered and
wrong-layer pins, a disconnected metal/via stack and every supported
floating/tie exception label. They also reject missing or duplicate checks,
boolean/float violation counts, changed source records, stale layouts,
inconsistent extraction areas and unsupported coverage promotion.

This batch audits the hash-bound reports already committed in the
[connectivity checkpoint](validation/sky130-floating-review-2026-10-11.json).
It verifies the retained Linux and Windows audit identities without claiming
to execute either historical run again. New fault controls run locally on
Linux. The original final GDS archive is not present in this workspace; fresh
final-layout and delivered Windows execution remain separate work. No prior
checker, native result or acceptance snapshot was changed.

The durable evidence archive contains 707 files, including rejected attempts,
and was read back completely against its manifest. A second 527-file archive
preserves the antenna diagnosis and stage controls with complete readback.
The third archive preserves 722 files covering connectivity, controls and the
unaccepted native fill pilot, also with complete readback.
Their identities are recorded in the respective execution records. Chunk 5's
original acceptance record remains unchanged; its historical source binding
is now explicit as described above.

## Grid and density-window diagnostics

The [2026-10-14 record](validation/sky130-grid-density-2026-10-14.json) executes
new diagnostics on the counter, UART and APB exports recovered from CI run
`38190866879`, artifact `11722609690` (`digital-implementation-evidence`). The
archive SHA-256 is
`4ec0edefcd132a2373c52a3030a58462788a0deabf386a4bece5238026186492`.
Every GDS differs from its locked filled-reference identity. These results
cannot be substituted for final filled-layout execution.

| CI layout | Physical grid errors | Off-grid text anchors | Full 700 µm windows | Additional clipped windows |
|---|---:|---:|---:|---:|
| Counter | 0 | 2 | 0 | 9 |
| UART | 0 | 4 | 0 | 36 |
| APB | 0 | 1 | 0 | 36 |

The [grid checker](../scripts/sky130_grid_geometry.py) checks unmerged polygon
vertices, holes, exact orthogonal path outlines, hierarchy/array placement and
text anchors. It rejects unknown purposes, empty geometry, non-unit or
non-orthogonal instance transforms, odd-width/diagonal/round paths and unsupported
shapes before integer rounding can conceal an error. It uses the assumptions
table's 0.005 µm drawn grid and explicit 1 nm mask/package purposes. It does
not silently correct the periphery table's inconsistent `mm` units, infer
unreviewed mask aliases or invoke seal exceptions. Text findings retain their
cell names and coordinates separately from physical boundaries; no geometry
or annotations were changed.

The [window checker](../scripts/sky130_density_windows.py) unions drawn metal
with its own fill purpose before measuring area. It requires explicit die
bounds, preserves metal outside those bounds as a finding, and keeps every
full and clipped window distinct. The diagnostic lattice starts at the die's
lower-left; that origin and the 70 µm step are explicit conventions because
the `.pd.2b` source leaves its unit blank. Non-Manhattan metal is refused before
window clipping can round an intersection. Raw metal occupancy is not the
published MM1–MM4 oxide-pattern-density metric. The source does not establish
the full oxide operand construction or edge policy needed for acceptance.
Every density report therefore remains `BLOCKED`; a small block cannot pass
because it contains no full windows. The standalone density CLI exits 2.

The [captured source bundle](qualification/sky130-grid-density-sources.json)
retains eight exact upstream files, including their license, URLs and hashes.
Each run verifies them against the existing pinned manual inventory. The
[regression controls](../tests/test_sky130_grid_density.py) cover every known
ordinary purpose and explicit fine-grid purpose, hidden/holed polygons,
hierarchy and arrays, path-edge rounding, changed source bytes, 700/70 µm
boundary conditions, overlap accounting, clipped denominators and the refusal
to return density acceptance. These controls ran on Linux with KLayout 0.30.5;
no new Windows qualification is asserted.

Download the named CI artifact and reproduce the saved record:

```sh
python -m scripts.check_sky130_grid_density --artifact /path/to/digital-implementation-evidence.zip --check
python -m unittest tests.test_sky130_grid_density -v
```

The first command's successful exit means exact diagnostic reproduction, not
chunk acceptance. The record retains all 25 open periphery rows for each
reference, the 1,474 unreviewed error records, density interpretation gaps and
the final timing/equivalence/application gates. The required filled-reference
archive remains:

```text
C:\Users\jonah\Documents\Codex\IC-Design-Studio-evidence\sky130-fill-progress-2026-10-11-v1\evidence.tar.gz
SHA-256: ccef87b3fdbd89009e33449fc1be84eb4e3899ada61163ae99007eef3b6307e0
Bytes: 920448744
```

Its identity comes from the retained checkpoint; the archive has not been
recovered here. Restoring it enables checks on the correct final geometry,
but does not itself resolve the missing `x.20` limit, oxide-density definition,
remaining rule reviews or unexecuted combined acceptance gate.

## Geometry catalog and notch reconciliation

The subsequent [geometry reconciliation](validation/sky130-geometry-reconciliation-2026-10-14.json)
extends the initial catalog audit with 313 literal error-ID bindings. The
[reconciler](../scripts/sky130_geometry_reconciliation.py) binds each record
to its exact periphery parent, checker identity and actual check. The source
catalog's canonical content hash protects every reviewed description and
threshold. Existing checker sources and historical reports remain unchanged.

| Coverage per retained filled reference | Previous | Current |
| --- | ---: | ---: |
| Executed error records | 61 | 356 |
| Absent error operands | 21 | 39 |
| Unreviewed error records | 1,474 | 1,161 |
| Executed periphery requirements | 133 | 135 |
| Periphery execution reviews still open | 24 | 22 |
| Missing periphery definitions | 1 | 1 |

The 184 geometry bindings cover selected well, implant, diffusion, gate,
local-interconnect, metal and contact records. Eighteen of these establish
**absent ring operands** under the exact-square contact guards; they do not
claim execution of non-empty ring rules. Another 129 records bind documented
mask and mask-edit purposes to the actual angle/containment checks. Explicit
aliases distinguish mask from drawing purposes. Ambiguous FOM wording,
unmapped metop aliases, RF/device-dependent records and all 74 `s`-series
records remain unreviewed.

Two global periphery obligations gain execution bindings. The general
`x.3` angle heading is covered by its numeric child `x.3a` and the stronger
orthogonal subset checks, including the conservative seal treatment. For
`x.6`, 408 fresh controls prove that all same-layer spacing operations in the
selected profiles include intra-polygon notches: 34 operands, gaps one
nanometre below/at/above the limit, and four rotations. Each coupon is a
single connected U polygon. All 136 undersized gaps are detected and all
272 at/above-limit gaps pass their target spacing check. Contact-shaped U
coupons intentionally violate the exact-square profile and establish only
the individual spacing operation, not legal contact layouts.

The [regressions](../tests/test_sky130_geometry_reconciliation.py) reject
failure of every newly bound check, missing parent evidence, stale identities,
duplicate or incomplete checks and changed source thresholds. They also
exercise all 65 mask-purpose angle mappings, actual allowed-area containment,
the 17 mask-edit core restrictions, all six ring-absence guards, and disabled
or incomplete notch controls. With KLayout 0.30.5:

```sh
python -m scripts.sky130_geometry_reconciliation --check
python -m unittest tests.test_sky130_geometry_reconciliation -v
```

The new catalog counts audit the retained filled-layout evidence; only the
controls execute fresh geometry here. The 22 remaining periphery reviews
cover unresolved grid units, metal-fuse operands, special device and voltage
semantics, and oxide-density windows. The absent `x.20` numeric definition
remains a separate blocker. No native summary count supplies missing coverage.

## Exact pin-corrected reference replay

The [replay record](validation/sky130-reference-replay-2026-10-14.json)
identifies the recovered CI exports more precisely: all three GDS hashes and
all three independent OpenDB inventory hashes match the
[original pin checkpoint](validation/sky130-pin-progress-2026-10-11.json).
They are the earlier unfilled outputs, not the later filled references.

The [replay runner](../scripts/check_sky130_reference_replay.py) verifies the
complete CI archive hash, the original checkpoint/source identities and each
inventory/GDS binding. It calls the actual application pin exporter and its
independent mask/text readback. Each regenerated GDS must match the original
reference **byte for byte**. The CI source-GDS hashes differ from the earlier
capture and are retained separately; no source-byte equivalence is asserted.

All six supplemental profiles then execute on each regenerated GDS: raw
implant, low-voltage geometry, interconnect, wide-metal, global geometry and
complete conductor connectivity. All 18 runs pass with every expected check
present and zero violations. These are fresh Linux/KLayout 0.30.5 runs. The
[replay regressions](../tests/test_sky130_reference_replay.py) reject stale or
incomplete profiles, invalid count types, missing conductor area and ambiguous
archive members.

The combined inventory, applicability, geometry, connectivity, reconciliation,
grid/window, replay and pin-export test batch passes all 215 tests without
skips. The release documentation/matrix check also passes; its process
qualification status remains `unqualified`.

```sh
python -m scripts.check_sky130_reference_replay --artifact /path/to/digital-implementation-evidence.zip --check
python -m unittest tests.test_sky130_reference_replay -v
```

The runner does not execute place/route or recapture OpenDB intent. Native
Magic/Netgen/OpenROAD are unavailable in this workspace; the available CI
runtime payload exceeds the connector's 512 MiB download limit. Final
filled-layout timing/equivalence, native replay, delivered Windows execution
and the combined application gate remain open. Chunk 6 is still incomplete.
