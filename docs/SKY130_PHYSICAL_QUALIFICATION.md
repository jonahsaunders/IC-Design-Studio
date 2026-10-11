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

Reconcile the full required rule inventory and antenna applicability beyond
the selected profile and complete density. Rerun the strict connectivity and
electrical checks after a valid fill solution is established. Integrate the
complete gate into the application and verify its delivered Windows/Linux
paths. The current standalone diagnostics do not yet provide that gate.

The durable evidence archive contains 707 files, including rejected attempts,
and was read back completely against its manifest. A second 527-file archive
preserves the antenna diagnosis and stage controls with complete readback.
The third archive preserves 722 files covering connectivity, controls and the
unaccepted native fill pilot, also with complete readback.
Their identities are recorded in the respective execution records. Chunk 5's
original acceptance record remains unchanged; its historical source binding
is now explicit as described above.
