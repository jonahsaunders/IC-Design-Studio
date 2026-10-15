# SKY130 physical coverage: chunk 6 in progress

The [execution record](validation/sky130-physical-progress-2026-10-11.json)
captures the original counter, UART and APB final layouts. Chunk 6 remains open.
Zero geometry markers alone do not establish complete physical coverage.

The [boundary export correction](#boundary-export-correction) removes a prohibited
die-outline annotation from all three final streams without changing manufacturing
geometry. Actual application checks and macro exports pass on the corrected
streams, and Windows reproduces identical GDS bytes. This is a separate correction;
the earlier catalog is not silently rebound to the new file identities.

The [special-subject review](#special-device-subject-absence) records, on the original GDS files,
416 executed error records, 593 verified absent subjects, 90 explicit standard-cell
W/L exemptions, eight advisory records and 449 unreviewed records. The preceding
[local/HV review](#local-geometry-marked-hv-and-hugepad-correction) reopens the
unsupported hugePad exemption, leaving ten periphery execution reviews and one declared optional rule not required by the
ordinary bulk references. Those ten reviews, the missing pin-spacing
definition and remaining required catalog/density interpretation remain open.
The [final electrical checks](#final-filled-reference-electrical-checks)
now pass nominal extracted timing and sequential equivalence on all three exact
filled references. The [grid/window diagnostics](#grid-and-density-window-diagnostics)
retain their separate measurements and unresolved source semantics.

The [application antenna gate](#application-antenna-gate) now requires all 13
reviewed stages for newly prepared bundled HD platforms. This closes the gap
between the supplemental checker and Finish/export; it does not close the
remaining rule or density requirements. Exact desktop-package installation and
foundry delivery acceptance belong to original chunk 12; they are not additional
chunk 6 completion gates.

## Global metal maximum-width bounds

The [metal-width audit](validation/sky130-metal-width-audit-2026-10-15.json) and
[reconciled catalog](validation/sky130-metal-width-2026-10-15.json) resolve three
more records: **363 to 360 unresolved**. Records `r1340`–`r1342` require maximum
widths of 25 µm for met1/met2 and 6 µm for met3 beneath pad metal. Every complete
connected conductor in these references fits within a strip no wider than
2.1 µm, so any portion selected beneath a pad also satisfies the maximum.
This is a numerical sufficient bound; it does not infer a pad selector.

The checker unions drawn metal and native fill across the reachable hierarchy
before measuring. The authenticated native technology file establishes the
three fill purposes. A connected fragment or fill bridge cannot evade the
bound. Explicit mask/edit or alternate metal purposes prevent promotion.
Exact limits pass; larger bounding boxes, including thin L shapes and rings,
remain unresolved because the sufficient bound cannot decide their local width.
Finish and saved-result/export validation require the report and reject missing,
altered or stale evidence.

All **316 tests pass on each OS without skips**. The **32 retained controls**
include exact limits, one-nanometer excesses, fill unions, hierarchy and ambiguous
cases; their layout and report bytes agree across Windows and Linux. Three
fresh Linux application runs and Windows result/export replays pass. Manufacturing
geometry, checkpoints, netlists and SPEF remain unchanged.

Catalog reconciliation now authenticates the previous complete catalog, its
audit, all 85 source dependencies and exact reference GDS hashes, then freshly
executes the three new checks. The earlier 1,193 decisions remain explicitly
retained results. Three historical integration sources are preserved verbatim;
the current integration is separately tested. Changed source or layout hashes
prevent reuse. The six incremental catalogs agree across operating systems at
**441 executed, 657 absent, 90 explicit W/L exemptions, eight advisory and
360 unresolved records**. This batch does not claim a fresh rerun of every old
catalog checker or native electrical extraction.

The evidence archive preserves new sources, controls, application artifacts and
reproduction drivers. Its parent is the family/package archive, whose parent is
the independent delivery archive; hashes for both retained archives are checked.
Chunk 6 remains incomplete.

### Remaining chunk 6 work at this checkpoint

These are unresolved coverage records, not 360 measured layout violations.
The separate missing `x.20` pin-spacing limit and wider required density work
also remain in chunk 6. Counts do not measure engineering effort.

| Records | Group | Definition or context still needed |
| ---: | --- | --- |
| 1 | Local geometry | Resolve the generated hugePad selector and conflicting area wording. |
| 16 | Grid | Establish the eight `metop` purposes before binding their grid/angle rules. |
| 32 | Device recognition | Resolve remaining RF fixed-layout model mapping, Table H5 and selected-device geometry. |
| 34 | Core and implants | Establish generated-mask construction and exact enclosure targets. |
| 69 | Module boundaries | Establish `q0`/`q1` subjects and module enclosure/spacing context. |
| 135 | Frame, seal and scribe | Supply frame/alignment construction, generated-mask companions and remaining chip-boundary definitions. |
| 56 | Pads and vias | Establish ViaTop and remaining pad-family selectors. |
| 17 | Dummy diffusion | Establish the `fomDummyDRC` operand and its density/fill constraints. |

The pinned public source bundle names several of these inputs without providing
their construction. New numerical checks must be bound to verified definitions;
absence of a guessed raw layer cannot establish a generated target is absent.
The GDS table does publish dummy FOM on `22:23`; the unresolved issue is its
relationship to the generated `fomDummyDRC` target and native waffle data, not
the absence of a raw dummy-purpose number.

## Low-Vt RF family absence and package boundaries

The [family and package audit](validation/sky130-family-package-audit-2026-10-15.json)
and [complete corrected catalog](validation/sky130-family-package-2026-10-15.json)
resolve **43 additional records per reference**, reducing the unresolved count
from **406 to 363**. Finish and saved-result/export validation require both new
reports; missing, altered or stale reports are rejected.

The 35 `r645`–`r679` messages explicitly name `sky130rf_nlowvt` devices. F2a
requires drawn `lvtn` for the `nlowvt` transistor family, and the published GDS
table identifies `125:44` as the low-Vt NMOS device purpose. The absence proof
requires that drawing, every published CLVTNM mask/edit purpose and the low-Vt
identifier to be empty. Low-Vt or RF names in reachable cells or text on any
purpose also prevent an absence claim. A named RF cell missing its implant
therefore stays unresolved. This does not recognize or check numerical geometry
for present RF devices, replace the missing fixed-layout model map or Table H5,
or cover the remaining `pshort` RF records.

Three further records (`r1312`, `r1313`, `r1333`) explicitly target bondpads or
their openings. C3 defines bondPad from `pad:dg OUTSIDE areaid:ft`. All drawing,
mask, pin, label, center and pad-frame purposes and candidate intent must be
absent. Missing enclosing metal or seal geometry cannot waive a present pad.
Other pad-family predicates remain unresolved.

The five remaining drawn package crossings (`r1436`, `r1440`, `r1442`, `r1445`,
`r1446`) now have numerical implementations. The authenticated installed KLayout
map binds PMM `85:44`, PMM2 `77:20`, RDL `74:20`, UBM `127:21` and bump `127:22`.
The original map is retained with its existing source hash; these purposes are
not newly attributed to the published GDS table. Each merged target is checked
against each supplied module-cut polygon on `81:10`. Holes, hierarchy and
connected fragments are preserved; touching or overlapping module markers are
rejected. Full containment and edge contact pass; a 1 nm crossing fails. Missing
module markers do not establish complete-chip boundaries or package availability.

All **286 tests pass on each OS without skips**, and **29 retained examples**
agree byte for byte across Windows and Linux. Six full catalog replays agree
at **438 executed, 657 absent, 90 explicit W/L exemptions, eight advisory and
363 unresolved records**. All 43 new reference decisions are absences, not
numerical passes on present RF devices or package structures. Three actual
Linux application runs and Windows saved-result/export replays pass.
Manufacturing geometry, checkpoints, netlists and SPEF are unchanged. Native
extraction, timing and equivalence retain their previously authenticated scope.

The source-bound evidence archive has the independent delivery archive as its
only parent. Required intermediate catalogs, source files, the installed layer
map, tests, examples and reproduction drivers are preserved directly.
Chunk 6 remains incomplete.

## Seal origin and minimum width

The [seal audit](validation/sky130-seal-geometry-audit-2026-10-15.json) and
[complete corrected-reference replay](validation/sky130-seal-geometry-2026-10-15.json)
add mandatory `r379` / `x.19` and `r392` / `x.28` reports to Finish and
saved-result/export validation. The single connected seal marker must have its
lower-left corner at `(0,0)`. Every merged seal feature, including ring walls,
must satisfy the error catalog's **6 µm minimum width**. Exact equality passes;
a 1 nm deficiency fails. The manual's N/A value does not waive that finite limit.

The marker is `81:1`, established by both the published GDS table and C4
description. The other `areaid.sl` entry on `81:7` is a signal-pad well identifier,
not a seal. Geometry is merged across reachable cells before checking. A ring
centered at the origin fails: the source specifies its lower-left corner.
Disconnected and corner-touching markers leave origin interpretation unreviewed;
width still executes on every component. These checks do not infer complete
seal construction or the unresolved advanced-seal diffusion selector (`r390`).

All **265 focused tests pass per OS without skips**. Nineteen retained examples
agree byte for byte on Windows and Linux: threshold widths, one narrow wall,
positive/negative origin shifts, a centered ring, duplicate/fractured rings,
translated/reflected hierarchy, arrays, exact paths and the signal-pad alias.
Changed, missing, failed or stale rehashed evidence is rejected.

Counter, UART and APB have **no seal marker**, so these two reference decisions
are absent subjects, not passing complete-chip seals. All six complete-catalog
replays agree: **438 executed, 614 absent, 90 explicit W/L exemptions, eight
advisories and 406 unreviewed records** per reference. Three actual Linux
application runs and Windows saved-result/export replays pass. Manufacturing
geometry, checkpoints, netlists and SPEF are unchanged. This batch does not
rerun native extraction, timing or equivalence.

The new evidence archive has the independent delivery archive as its only
parent, with intermediate catalogs, current code, controls and reproduction
drivers stored directly. Chunk 6 remains incomplete.

## Global drawn-feature bounds for scribe restrictions

The [scribe-size audit](validation/sky130-scribe-bound-audit-2026-10-15.json) and
[complete corrected-reference replay](validation/sky130-scribe-bounds-2026-10-15.json)
add fourteen required numerical bounds to Finish and saved-result/export
validation. They bind `r1376`–`r1389`, the drawn-layer `scribe.5` restrictions on
10-by-10 µm features within 150 µm of a scribe junction.

All reachable geometry is flattened and touching/overlapping fragments are
merged across cell boundaries. Every resulting connected feature must have
at least one bounding-box side **strictly below 10 µm**. This stronger global
condition excludes a 10-by-10 µm feature at any position or orientation, so it
also excludes one near any junction. The fourteen layers are diffusion, poly,
local interconnect, metal1–metal5, local/metal contacts and via1–via4.

A box with both sides exactly 10 µm or larger is a candidate and remains
**unreviewed**. The checker does not claim that a large box proves a wide region:
thin L shapes and hollow rings also remain candidates. It does not infer a
junction from the block outline, frame markers or cell names. Fourteen companion
mask records `r1390`–`r1403` remain unresolved because their generated-mask inputs
are not established. Unsupported geometry fails closed.

All **248 focused tests** pass on Windows and Linux without skips. The **27
retained examples** agree byte for byte, including a 1 nm threshold boundary,
exact-threshold candidates on every layer, merged/overlapping/corner-touching
fragments, cross-cell features, reflected arrays, disconnected geometry, holes,
thin shapes, exact paths and permitted text. Missing, altered and stale rehashed
reports cannot bypass saved-result/export validation.

All fourteen bounds execute on **nonempty geometry** in counter, UART and APB.
The complete catalogs are replayed on both systems with identical reports:
**438 executed bindings, 612 absent subjects, 90 explicit standard-cell W/L
exemptions, eight advisories and 408 unreviewed records** per design. Eighteen
frame bounds still lack boundary context. Three fresh Linux application runs and
Windows saved-result/export replays pass; manufacturing geometry and electrical
artifacts are unchanged. Native extraction, nominal voltage, timing and
equivalence remain authenticated retained dependencies, not new electrical runs.

The archive uses the independent delivery archive as its only parent and stores
required intermediate catalogs and current source files directly. Remaining
generated-mask, RF, grid/purpose, module/frame/pad, pin-spacing and density work
stays in chunk 6. **Chunk 6 and complete process qualification remain incomplete.**

## Drawn-well enclosure and hole-spacing bounds

The [well-bound audit](validation/sky130-well-bound-audit-2026-10-15.json) and
[complete corrected-reference replay](validation/sky130-well-bounds-2026-10-15.json)
add three required numerical checks to Finish and saved-result/export validation:

- `r923` / `pwde.6`: expand all drawn PWDE by a 1 µm square and require the result
  inside both DNWELL and UHVI.
- `r924` / `pwbm.5`: require every pair of holes in the fully merged drawn PWBM
  to have at least 0.84 µm square-metric spacing. Find holes before UHVI selection;
  filling nested islands enlarges the checked hole conservatively.
- `r931` / `uhvi.3`: require all drawn PWBM inside UHVI without subtracting a
  LOWVTID exemption.

The pinned error catalog supplies the finite limits and GDS layer names. The
manual calls the drain-extended implant `pwdem`, supplies UHV selection context,
and lists N/A values; those values are not treated as waivers. Whole drawn
operands and square margins provide stronger, sufficient bounds. Exact equality
passes. Failure of a stronger bound stays **unreviewed**, not a claimed foundry
violation. Missing enclosing geometry never discharges a present target. These
checks do not establish missing device geometry or generated-mask equivalence.

All **230 focused tests** pass on Windows and Linux without skips. The **23
retained geometry examples** agree byte for byte, including all three nonempty
exact-limit checks, 1 nm enclosure/spacing failures, missing layers, holes,
nested islands, merged/open rings, arrays and exact paths. Changed-layout,
missing-report and altered-report controls reject unsupported acceptance.

Fresh complete catalog replays for counter, UART and APB agree byte for byte on
both systems. Each contains **424 executed bindings, 612 absent subjects, 90
explicit standard-cell W/L exemptions, eight advisories and 422 unreviewed
records**. The three new reference decisions are absent-operand; their nonempty
control results are separate. Eighteen frame bounds also execute and stay
unreviewed because these blocks have no frame/die-cut context.

Three fresh Linux application runs and Windows saved-result/export replays pass.
Every exported artifact is read back and authenticated. Manufacturing geometry,
checkpoints, netlists and SPEF remain unchanged; native extraction, nominal
voltage, timing and equivalence are authenticated retained dependencies, not new
electrical runs. Missing generated-mask recipes, RF selection, grid/purpose,
module/frame/pad context, pin-spacing and required density coverage remain open.
**Chunk 6 remains incomplete.**

## Drawn-layer frame-margin bounds

The [frame-bound audit](validation/sky130-frame-bound-audit-2026-10-15.json)
and [fresh reference measurements](validation/sky130-frame-bounds-2026-10-15.json)
add eighteen numerical sufficient-bound checks to Finish and saved-result/export
validation. They cover `nsm.3a` enclosure and `nsm.3b` spacing for diffusion, tap,
poly, local interconnect and metal1 through metal5. Published source bytes bind
each exact catalog record, its 3 µm margin and its drawn-layer purpose.

For enclosure, the complete target region expanded by a 3 µm square must fit
within the explicitly supplied frame marker on 81:12. For spacing, that expanded
region must have no positive-area intersection with the supplied die-cut marker
on 81:11. Exact equality passes. Holes, merged target fragments, reflected arrays
and exact Manhattan paths are preserved. Touching/overlapping boundary markers
and unsupported geometry are rejected, so merging cannot hide a boundary.

This is a conservative proof: the square expansion is at least as strict as a
Euclidean 3 µm margin, and no named-cell or blanking exception is applied. Failure
therefore means **unreviewed**, not an established foundry violation. A present
target with missing boundary context also remains unreviewed. The checker never
substitutes a block bounding box for the frame or die-cut geometry. Supplied
markers alone do not prove complete-chip context or a valid frame construction.

All **212 focused tests** pass without skips on Windows and Linux. The **36
retained controls** agree byte for byte across systems, including nonempty
positives for all eighteen checks, 1 nm margin failures for every drawn layer,
holes, disconnected frames, interior/overlapping die targets, conservative corner
cases and missing context. Stale rehashed layouts and missing/altered reports
are rejected. Three fresh application runs and Windows saved-result/export
replays pass; manufacturing geometry and retained electrical artifacts are unchanged.

The counter, UART and APB blocks have no frame or die-cut markers. **All eighteen
reference requirements remain unreviewed**, and this batch promotes no catalog
record. Retained complete-catalog counts stay at 424 executed, 609 absent, 90 W/L
exemptions, eight advisory and 425 unreviewed. This batch reruns the frame bounds
and application checks; the complete catalog remains the preceding source-bound
checkpoint at `327dfac`. Generated-mask and dummy-diffusion frame records, frame
completeness, other unresolved physical rules and chunk 6 remain open.

```sh
python -m scripts.sky130_frame_bound_review --check
python -m unittest tests.test_sky130_frame_bounds tests.test_sky130_application_rules -v
```

The reference command requires the retained corrected streams under workspace
outputs. The readback-verified evidence archive retains current sources, reports,
controls and application outputs; its only parent is the selected-target archive,
which in turn references the independent delivery archive. Use the preceding
checkpoint's source commit or archived files to reproduce its exact full report.

## Selected pad, inductor and implant targets

The [selected-target audit](validation/sky130-selected-target-audit-2026-10-15.json)
and [complete corrected catalog](validation/sky130-selected-targets-2026-10-15.json)
add a mandatory report covering sixteen selected targets to Finish and saved-result
and macro-export validation. All sixteen targets are absent on the three reference
layouts. These are explicit absence decisions, not numerical passes on nonempty
pad or implant geometry.

- Seven bond-pad records use the published C3 definition of `bondPad` as a subset
  of `pad:drawing`. The complete drawing, additional pad/pin/label/mask purposes
  and candidate cell names and labels must be empty.
- Seven inductor-pad records require empty inductor drawing, label and terminal
  purposes and no candidate names or labels. All three captured F2a inductor
  families require the drawn inductor identifier, including the row without a
  populated Used field; that field is not a waiver.
- `r1476` requires an empty intersection of all drawn poly and tap. This stronger
  condition proves that the published `Var_channel` and the selected well target
  are empty. Explicit masks and varactor-name/label hints also prevent absence.
- `r1493` requires empty HVI and additional voltage/mask/intent guards. An empty
  HVI region has no selected diffusion inside it. Missing enclosing implants or
  metal never waives a present target.

All raw shape types count on guard purposes. Poly/tap measurement preserves
holes and exact Manhattan paths and rejects unsupported geometry or transforms.
Saved-result validation independently recomputes the report from actual GDS;
editing the recorded GDS hash cannot rescue stale measurements.

The first APB replay exposed a false pad-name hint in the address labels
`paddr[0]` through `paddr[3]`. The generic `pad` token now requires a following
non-letter or the end of the name. Explicit pad compounds and `bond` retain
substring matching, with Unicode/whitespace normalization. Raw drawing and mask
guards are unchanged. The failed attempt, its checker and reports are retained;
new controls cover ordinary bus names, explicit pads and actual pad geometry
under an ordinary bus name.

All **194 focused tests** pass without skips on each OS. All **57 retained
controls** and all three complete catalog reports agree byte for byte across
Windows and Linux. Fresh application runs pass the six partial profiles, thirteen
antenna stages, OpenDB antenna/power checks and macro export. Windows reproduces
the corrected GDS and validates saved results and exported artifacts.
Manufacturing geometry, netlists, checkpoints and SPEF remain unchanged.

Each corrected full catalog now contains **424 executed bindings, 609 absent
subjects, 90 explicit standard-cell W/L exemptions, eight advisory records and
425 unreviewed records**. The pad/stack queue falls from 76 to 62 and the
core/implant queue from 36 to 34. Finish retains 218 explicitly bound current
catalog messages alongside its partial periphery ledger; the full reference
catalog command does not establish arbitrary-job signoff.

Nonempty target checks, ViaTop and other pad variants, hugePad and generated-mask
recipes, RF selection, grid/purpose interpretation, complete module/frame context,
pin spacing and required density remain open. Chunk 6 remains incomplete.

```sh
python -m scripts.sky130_selected_target_review --check
python -m unittest tests.test_sky130_selected_targets tests.test_sky130_application_rules -v
```

The command uses the retained corrected exports and native/voltage/library
dependencies under workspace outputs. Its archive includes current sources,
reports, controls, drivers and current application inputs, with an authenticated
reference to the preceding independent delivery archive. It does not require the
older application archive chain. The preceding complete replay below is bound
to commit `480b647`; use that commit or its archived sources for its exact report.

## Complete catalog replay on corrected exports

The [delivery replay audit](validation/sky130-delivery-catalog-audit-2026-10-15.json)
and [complete catalog](validation/sky130-delivery-catalog-2026-10-15.json) now
bind all 1,556 catalog records to the exact corrected counter, UART and APB
exports. Geometry, recursive subject measurements, physical connectivity,
standard-cell comparisons and source bindings are freshly executed. Earlier
catalog decisions are not transferred merely by replacing their GDS hashes.

Each corrected design has **424 executed bindings, 593 absent subjects, 90
explicit standard-cell W/L exemptions, eight advisory records and 441 unreviewed
records**. All eight forbidden-boundary records are executed on the corrected
streams. The original streams and their 449-unreviewed catalog remain preserved.
This supersedes the earlier separation between 202 current catalog messages and
the historical full catalog for these three reference exports.

Every export is reproduced byte for byte from its original GDS and independent
OpenDB pin/die inventory. Native extraction and nominal-voltage contracts are
explicitly retained dependencies: their files are authenticated, and fresh gate
censuses, trusted library geometry and voltage selectors must agree. No new
extraction, timing or electrical acceptance is claimed. The complete six-profile
application ledger and its unresolved requirements remain separate.

All six case/OS replays pass, and Windows/Linux report bytes match for each case.
Seventy-four focused tests pass without skips on each OS. Fault controls reject
missing or duplicated catalog records, changed source/evidence bytes, overlapping
decision stages, a missing boundary check, and promotion or waiver of an unresolved
requirement. The evidence archive retains the replay inputs, reports, tests and
drivers without depending on the preceding archive chain.

This is a reference qualification command; it does not install full-catalog
verification for arbitrary application jobs. A complete inventory is not complete
required-rule coverage. Generated masks, RF selection, grid/purpose semantics,
frame/pad and module context, pin spacing and required density remain open.
Chunk 6 remains incomplete.

```sh
python -m scripts.check_sky130_delivery_catalog --check
python -m unittest tests.test_sky130_delivery_catalog -v
```

The replay uses retained reference exports and native/voltage/library dependencies
under the workspace outputs directory. `--case counter`, `--case uart` and
`--case apb` support independent runs; give each run its own `--output` file.

## Special device-subject absence

The [audit](validation/sky130-special-subject-audit-2026-10-15.json) and
[reference measurements](validation/sky130-special-subjects-2026-10-15.json)
add a required `special_subjects` report to Finish and saved-result/export
validation. Seven records have conservative empty-subject proofs. Present
subjects or device-name/label hints keep their requirements unreviewed.

- `r396` and `r929`: an entirely empty UHVI region cannot be straddled by any
  selected geometry. Present UHVI requires a separate nonempty review.
- `r928`: the deep-well target is absent in both drawn and explicit mask data.
  Missing enclosing UHVI never waives a present deep well.
- `r1047`, `r1059` and `r1060`: RPM, URPM, CRPM and poly-resistor purposes are
  all empty, and no candidate precision-resistor names or labels are present.
- `r922`: the fully merged nwell has no holes; explicit nwell masks, extended-
  drain markers and candidate names/labels are also absent. This discharges the
  empty target under both published selector wordings.

All raw shape kinds count on guard purposes. Hole detection preserves touching
fragments and a 1 nm opening. Unsupported nwell geometry or transforms fail
explicitly. N/A source values are not used as waivers. The catalog calls the
precision-resistor enclosure `urpm.3` while the matching manual description uses
`rpm.3`; the catalog/manual `depmos.8` hole selectors also differ. These reports
do not resolve nonempty rule meanings or qualify UHV/resistor devices.

All 163 focused tests pass without skips on each OS. Twenty retained controls
and original/corrected reference measurements agree byte for byte across Windows
and Linux. Controls exercise every raw guard purpose, normalized labels, solid
nwell, explicit/fragmented holes and 1 nm open/closed rings. Missing/altered
reports and rehashed layouts with added subjects reject stale absence claims.
All three application runs and Windows export replays pass. Manufacturing
geometry, checkpoints, netlists and SPEF remain unchanged.

Original-stream totals become 416 executed, 593 absent, 90 W/L exemptions,
eight advisory and 449 unreviewed. The device-selection queue falls from 77 to
70. Corrected streams retain 202 explicit current catalog messages, separate
from the unchanged six-profile ledger. Historical full-catalog decisions retain
their original GDS identities. Required generated-mask, RF, grid/purpose,
frame/pad, pin-spacing and remaining density coverage stays open.

```sh
python -m scripts.sky130_special_subject_review --check
python -m unittest tests.test_sky130_special_subjects tests.test_sky130_application_rules -v
```

The review requires retained corrected streams under workspace outputs. The
preceding physical-device-root checkpoint is source-bound to commit `32b6d4b`;
use that commit or its archived sources for its exact report. The current audit
preserves application outputs, controls, tests and reproduction drivers.

## Physical device-root connectivity

The [audit](validation/sky130-device-root-audit-2026-10-15.json) and
[reference measurements](validation/sky130-device-roots-2026-10-15.json) add a
required `device_roots` report to Finish and saved-result/export validation.
Seven floating-net records (`s11`, `s16`, `s21`, `s26`, `s31`, `s36`, `s41`)
pass complete paths through every contact level to actual gate or diffusion/tap
geometry. Gate geometry is poly intersecting diffusion; source/drain/tap roots
exclude poly. Pin annotations, labels and standard-cell markers supply neither
endpoints nor connections. Every submitted conductor and root area is accounted
for in the extracted graph, including isolated contact-only components.

All 106 counter, 1,304 UART and 1,204 APB nets reach physical roots. The original
and corrected streams produce identical measurements, and Windows and Linux
produce identical reports. This is a stronger sufficient condition for these
reference blocks. A legal pin-only IP feedthrough can remain unreviewed here;
it is not automatically a foundry-rule violation. Unsupported capacitor, RDL,
cut/short edits and float/tie declarations also leave these records unreviewed.
The existing block connectivity profile remains required separately.

All 147 focused tests pass without skips on each OS. Sixteen retained controls
exercise real gate/diffusion/tap endpoints, each missing contact level, a 1 nm
gap, pin-only feedthroughs, pin annotations spanning separate wires or layers,
exception labels, unsupported capacitor markers and poly-short bridges. Controls
match byte for byte across systems. Missing/altered reports and rehashed layouts
with stale connectivity evidence fail validation. All three application runs and
Windows export replays pass; the delivered manufacturing geometry is unchanged.

Original-stream totals become 416 executed, 586 absent, 90 W/L exemptions,
eight advisory and 456 unreviewed. The connectivity queue falls from seven to
zero. Corrected streams retain 195 explicit current catalog messages, separate
from the unchanged six-profile ledger. Historical full-catalog decisions retain
their original GDS identities. This does not establish device/body LVS, chip I/O,
ESD, new extracted performance or complete physical signoff. Chunk 6 remains open.

```sh
python -m scripts.sky130_device_root_review --check
python -m unittest tests.test_sky130_device_roots tests.test_sky130_application_rules -v
```

The review requires retained corrected streams under workspace outputs. The
preceding conservative-bound checkpoint is source-bound to commit `fc30087`;
use that commit or its archived sources for its exact report. The current audit
preserves application outputs, controls, tests and reproduction drivers.

## Conservative geometry bounds and IP blockages

The [audit](validation/sky130-conservative-bound-audit-2026-10-15.json) and
[reference measurements](validation/sky130-conservative-bounds-2026-10-15.json)
add a required `conservative_bounds` report to Finish and saved-result/export
validation. Four catalog limits follow from passing broader checks: every merged
drawn NSDM/PSDM width is at least 380 nm (`r471`, `r487`), and every merged poly
spacing/notch is at least 210 nm, which also satisfies the 175/160 nm limits
(`r520`, `r521`). No opposite-parallel or core-gap exception is used.

These are sufficient conditions. A failed broad check keeps the narrower rule
**unreviewed**, rather than claiming a foundry-rule violation. In particular,
poly at 175 or 160 nm can require a valid exception that this report does not
establish. The existing application profile restrictions remain separate.
Holes, notches, touching fragments and hierarchical transforms are checked;
unsupported geometry fails explicitly. The generated-mask requirements remain
open: a bound on drawn geometry does not construct a compatible mask.

Eighteen IP blockage messages (`r1234`–`r1251`) are absent on these references.
The census counts every raw shape, including text and paths, on the published
block purposes 67:10 through 72:10. These are the IP integration blockage layers
identified by table C4b. Magic fill-exclusion layers are not substituted for them.
Present blockage data remains unreviewed because the derived routing operands
and hierarchy semantics are not implemented here.

All 128 focused tests pass without skips on each OS. Sixteen retained controls
and the original/corrected measurements match byte for byte across systems.
Controls include exact bounds, 1 nm failures, narrower candidate spacings,
holes, merged fragments, reflected arrays, all six blockage purposes and text.
Missing/altered reports and rehashed layouts with stale measurements fail current
validation. All three actual application runs and Windows export replays pass.
Manufacturing geometry, checkpoints, netlists and SPEF are unchanged.

Original-stream totals become 409 executed, 586 absent, 90 W/L exemptions,
eight advisory and 463 unreviewed. The core/generated-mask queue falls from 40
to 36, and the routing/boundary queue from 26 to eight. Corrected streams retain
188 explicit current catalog messages, separate from the unchanged six-profile
ledger. Historical full-catalog decisions retain their original GDS identities.
No new extraction, electrical qualification or complete physical signoff is
claimed. Chunk 6 remains incomplete.

```sh
python -m scripts.sky130_conservative_bound_review --check
python -m unittest tests.test_sky130_conservative_bounds tests.test_sky130_application_rules -v
```

The review requires the retained corrected streams under workspace outputs.
The preceding selected-device checkpoint is source-bound to commit `3100a18`;
use that commit or its archived sources for its exact report. The current audit
preserves application outputs, controls, tests and reproduction drivers.

## Selected devices and recommended rules

The [audit](validation/sky130-selected-device-audit-2026-10-15.json) and
[reference measurements](validation/sky130-selected-devices-2026-10-15.json)
add a required `selected_devices` report to Finish and saved-result/export
validation. Thirty-four VPP, pwell-resistor and PNP messages are absent only when
their published mandatory drawn purpose is empty and no reachable cell name or
label suggests that device. Present geometry, text or a candidate name keeps
the family requirements unreviewed. Renaming a marked device cannot hide it.

Two implant checks execute numerically: gates overlapping drawn tunm require
95 nm enclosure (`r453`), and every drawn hvntm region must be inside hvi
(`r1061`). Gates use the intersection of poly and diffusion. Partial overlaps,
holes and connected fragments are preserved. A SONOS name or label with missing
or incomplete gate selection remains unreviewed. Missing HVI with present HVNTM
fails. These checks do not qualify complete SONOS or high-voltage devices.

Eight catalog entries have an explicitly published `RR` (recommended) parent:
`s0`–`s6` and `s8`. They are recorded as advisory with execution not claimed.
They do not become numerical passes or waive required rules. Together with the
36 verified device/implant absences on both reference streams, this reduces the
original queue from 529 to 485. Current totals are 405 executed, 568 absent,
90 W/L exemptions, eight advisory and 485 unreviewed. Corrected streams retain
166 explicit current catalog messages, separate from the unchanged six-profile
ledger. Historical full-catalog decisions remain bound to the original GDS files.

All 115 focused tests pass without skips on each OS. Seventeen retained controls
agree byte for byte across Windows and Linux, including valid nonempty implants,
1 nm failures, holes, reflected arrays, missing marker context, all three device
families and Unicode labels. Missing or altered reports, implant failures and
rehashed layouts carrying stale measurements fail validation. All three actual
application runs and Windows export replays pass. Manufacturing geometry,
checkpoints, netlists and SPEF are unchanged; no new extraction or electrical
qualification is claimed. Required density and complete physical coverage remain
open, so chunk 6 is incomplete.

```sh
python -m scripts.sky130_selected_device_review --check
python -m unittest tests.test_sky130_selected_devices tests.test_sky130_application_rules -v
```

The review uses the retained corrected streams under workspace outputs. The
preceding boundary checkpoint is source-bound to commit `895a4f2`; use that
commit or its archived sources to reproduce its exact report. The current audit
retains application outputs, controls, tests and reproduction drivers.

## Module and seal interactions

The [audit](validation/sky130-boundary-interaction-audit-2026-10-15.json) and
[reference measurements](validation/sky130-boundary-interactions-2026-10-15.json)
add 44 numerical checks to Finish and saved-result/export validation. Thirty-five
published drawn-layer purposes are checked against each supplied module-cut
polygon on 81:10 (`scribe.7`). Diffusion must not straddle seal geometry on 81:1
(`x.23b`); tap, poly, local interconnect and metal1-metal5 must not overlap it
(`x.23c`). Five package-purpose scribe records remain unresolved.

Targets are merged connected regions; touching fragments cannot hide a crossing.
Boundary polygons preserve their holes and are checked independently. Duplicate,
touching or overlapping boundary markers are rejected rather than merged across
a possible module seam. Manhattan polygons and exact orthogonal paths are
supported. Unsupported transforms, fractional path outlines and unexpected
boundary data fail explicitly. Drawing/text purposes retain text without
counting it as geometry. Missing/changed reports, selected-rule failures and
rehashed layouts carrying stale measurements fail validation.

The three reference blocks have **no module-cut or seal markers**. Passing these
interaction checks proves no crossing or overlap with supplied boundaries; it
does not establish complete-chip boundaries, seal origin/width, enclosure or
spacing. Those obligations remain open. Of the 44 new records, 29 have nonempty
target geometry and 15 have absent targets. Original-stream totals become
405 executed, 532 absent, 90 W/L exemptions and 529 unreviewed. Corrected streams
retain 130 explicit current catalog messages, separately from the unchanged
six-profile periphery ledger. Historical full-catalog decisions stay bound to
their original GDS identities.

Ninety-eight focused tests pass without skips on each OS. Eleven retained controls
match byte for byte across Windows and Linux and include nonempty failures for
all 44 checks, 1 nm crossings/overlaps, exact touches, containment, holes, multiple
modules, reflected arrays and rejection of an ambiguous module seam. All three
actual application runs and Windows export replays pass. Manufacturing geometry,
checkpoints, netlists and SPEF are unchanged; this batch adds no extraction or
electrical qualification. Chunk 6 remains incomplete.

```sh
python -m scripts.sky130_boundary_interaction_review --check
python -m unittest tests.test_sky130_boundary_interactions tests.test_sky130_application_rules -v
```

The review uses the retained corrected streams under workspace outputs. The
preceding VPP checkpoint is source-bound to commit `f59d259`; reproduce its exact
report using that commit or archived sources. The current audit preserves all
new application outputs, controls, tests and reproduction drivers.

## Selected VPP geometry and density measurements

The [audit](validation/sky130-vpp-geometry-audit-2026-10-15.json) and
[reference measurements](validation/sky130-vpp-geometry-2026-10-15.json) integrate
four selected catalog checks into Finish and saved-result validation. The new
`vpp_geometry` report measures actual capacitor drawing 82:64: minimum width
1.43 µm (`r1145`), no straddling nwell or dnwell (`r1151`/`r1152`), and minimum
nwell enclosure 1.5 µm where capacitor overlaps nwell (`r1153`). A capacitor
outside nwell leaves the enclosure requirement `unreviewed`, rather than
forcing placement or inferring an exemption from a missing enclosing layer.
Unsupported transforms, non-Manhattan polygons, fractional path boundaries and
unexpected raw target data are rejected before conversion can conceal an error.
Drawing/text purposes retain labels without treating their text as conductor area.

The same report records clipped, unioned metal3/4/5 area and poly-intersect-diffusion
area per connected capacitor region. Integer comparisons preserve exact ordinary
limits of 0.25, 0.30, 0.40 and 0.87. These are **measurements only**. Unfinished
special-device selectors, their exceptions and full VPP density acceptance remain
unreviewed; ratios within ordinary limits cannot change that status. Other VPP
geometry and connectivity requirements remain separate.

Eighty-four focused tests pass on each OS. Eight retained nonempty controls agree
byte for byte across systems: a valid geometry example, 1 nm width and enclosure
failures, both well crossings, an unresolved outside-nwell example, exact density
limits, and ratios just outside those limits. Holes, hierarchical arrays, reflected
instances, multiple capacitor regions, path conversion, stale reports and altered
layout identities are also tested. These controls qualify the selected checks,
not a complete capacitor device or its electrical behavior.

All three actual application runs and Windows export replays pass. Missing VPP
reports, changed measurements and selected-rule failures are rejected. The exact
reference layouts contain no capacitor drawing, so their four new catalog entries
are recorded as absent subjects. Their original-stream counts are 376 executed,
517 absent, 90 W/L exemptions and 573 unreviewed; density/fill records fall from
40 to 36. Corrected streams retain 86 explicit current catalog messages, separate
from the unchanged six-profile periphery ledger. Full historical decisions remain
bound to original GDS identities. No layout geometry, extraction or timing changes
are claimed, and chunk 6 remains incomplete.

```sh
python -m scripts.sky130_vpp_review --check
python -m unittest tests.test_sky130_vpp tests.test_sky130_application_rules -v
```

The review requires the retained corrected reference streams under workspace
outputs; their hashes and evidence archive are recorded in the audit. The preceding
label checkpoint is source-bound to commit `eecbabf`; use that commit or archived
sources to reproduce its exact report. New runtime validation changes source hashes.

## Explicit label and raw-target subjects

The [audit](validation/sky130-label-subject-audit-2026-10-15.json) and
[fresh measurements](validation/sky130-label-subjects-2026-10-15.json) resolve 37
literal catalog messages whose targets are absent on both original and corrected
reference streams. These include 28 floating/tied-label messages, the conditional
diode label, the selected part-number-cell naming message, and seven messages
selecting actual low-tap-density, injection, prune, capacitor or pad purposes.

Finish records `catalog_labels` alongside the preceding 45-message
`catalog_context`. Label searches traverse all purposes and reachable hierarchy;
Unicode compatibility, case, whitespace and embedded-token variants conservatively
prevent false absence. Cell-name searches include the top and reachable cells.
Raw targets use their exact pinned published purposes, including pad drawing
76:20. No missing enclosing frame or module region is used as an exemption.
Present targets remain `unreviewed`, and their report says `review-required`.
This batch does not implement floating-net detection or the whole-chip part-number
requirement. Saved-result validation freshly measures the layout, rejecting
missing or altered reports and rehashed layouts carrying false absence claims.

All three actual application runs pass the existing six partial geometry profiles,
thirteen antenna stages, OpenDB checks and macro export. Windows revalidates the
saved results and exports and reproduces identical corrected GDS. Sixty-seven
focused tests pass without skips on each OS, including deliberately added labels,
raw targets, hierarchy, source changes and false absence claims. Fresh measurement
reports agree byte for byte across systems.

The original-stream catalog advances to 376 executed, 513 absent, 90 explicit
W/L exemptions and 577 unreviewed entries. Connectivity/label records fall from
46 to 14, module records from 73 to 69, and frame records from 201 to 200.
Corrected streams carry 82 explicit current catalog messages: 74 absent subjects
and eight executed boundary prohibitions. Full historical catalog decisions
remain bound to the original streams. The application periphery ledger remains
133 executed and 28 reviews. Manufacturing geometry and electrical artifacts are
unchanged; this batch claims no new extraction, timing or full signoff.

```sh
python -m scripts.sky130_label_subject_review --check
python -m unittest tests.test_sky130_catalog_labels tests.test_sky130_application_rules -v
```

The measurement review requires the retained corrected references under the
workspace outputs directory; the audit records their identities and archive.
Older rule reports missing `catalog_labels` require current Finish rechecking.
The following core-context checkpoint is historical: reproduce its source-bound
report with commit `c085aa4` or its archived sources. Current source-bound reports
include the additional label validation and therefore have different source hashes.

## Explicit core and implant context

The [audit](validation/sky130-core-context-audit-2026-10-15.json) and
[fresh measurements](validation/sky130-core-context-2026-10-15.json) resolve 37
literal catalog subjects on both the original and corrected reference streams.
Thirty-three messages explicitly select geometry inside `core` or `COREID`,
and one concerns unapproved cells containing the core marker. The published
`areaid.ce` purpose is the memory-core identifier at 81:2; ordinary digital
floorplans and standard-cell markers do not establish that selection. Complete
absence of raw geometry and text on 81:2 resolves these selected subjects only.

Three further messages concern the actual LDNTM implant at 11:44: its outside-core
prohibition and two requirements to enclose LDNTM in CLNTM. That target is absent.
Requirements to enclose other targets in core or a generated mask remain open;
neither a `.c` suffix nor an empty enclosing mask proves them inapplicable.

Finish now records these 37 subject decisions alongside the eight boundary
prohibitions in a separate 45-message `catalog_context` report. Present core or
LDNTM data stays `unreviewed`, with status `review-required`; this implements no
numerical memory-device rules or approval. Saved-result and export validation
require the report and freshly recount the actual layout. Missing context,
changed source bindings, omitted rows, altered counts and false absence claims
are rejected. Older rule reports need current Finish rechecking.

All three actual application runs pass their existing geometry profiles, thirteen
antenna stages, OpenDB checks and macro exports. Windows revalidates the saved
results and exports, reproducing identical corrected GDS. Fifty-five focused tests
pass without skips on each OS. Controls cover marker geometry and text, nested
arrays, distinct standard-cell/floorplan purposes, forbidden boundaries, stale
reports and rehashed layouts carrying false absence claims. Fresh measurement
reports agree byte for byte across systems.

The original-stream catalog advances to 376 executed, 476 absent, 90 explicit
W/L exemptions and 614 unreviewed entries. Its core/generated-mask batch falls
from 77 to 40. The corrected streams retain separate current evidence for the
45 explicit messages; the other historical catalog decisions are not silently
rebound. The application periphery ledger remains at 133 executed and 28 reviews.
Manufacturing geometry and electrical artifacts are unchanged from the preceding
boundary correction. No new extraction, timing or foundry acceptance is claimed.

```sh
python -m scripts.sky130_core_context_review --check
python -m unittest tests.test_sky130_catalog_context tests.test_sky130_application_rules -v
```

The full review uses the retained corrected reference streams under the workspace
outputs directory. Their identities and archive entries are recorded in the audit;
missing or changed streams fail rather than falling back to older layouts.

## Boundary export correction

The [consolidated audit](validation/sky130-boundary-export-2026-10-15.json)
records a real export defect: the captured DEF-reader configuration adds a
`prBoundary.boundary` box at the die outline, while catalog records `r1252` and
`s68` prohibit that purpose in delivered layouts. The other six literal records
`r1253`–`r1255` and `s69`–`s71` prohibit poly, diffusion and tap boundary purposes.

Current Finish removes only a single top-level rectangular outline exactly equal
to the die captured independently from OpenDB. Multiple, nested, mismatched,
nonrectangular or textual outline data is rejected. Other prohibited boundary
purposes are rejected, including text. The original stream is retained, and the
schema-2 pin-export report binds the correction to the source GDS, final GDS and
checkpoint. Saved-result validation and macro export independently repeat the
geometry comparison and reject missing or altered correction evidence. Historical
boundary-bearing streams and older pin reports need current Finish rechecking.

On counter, UART and APB, exactly one outline is removed and zero pin-metal area
is added. Every other manufacturing region and text annotation is preserved;
checkpoint, netlist, DEF and SPEF bytes are unchanged. All six existing partial
geometry profiles, thirteen antenna stages, OpenDB antenna/power-connectivity
checks and macro exports pass on the corrected streams. Optional isolation stays
`NOT_REQUESTED`. The application periphery ledger still has 133 executed rows and
28 execution reviews; this batch does not promote full physical coverage.

Thirty-five focused tests pass without skips on Windows and Linux. Windows also
reproduces all three corrected GDS files byte for byte from the original streams
and Linux-captured inventories, revalidates the saved results and exports their
macro bundles. Restoring the prohibited outline cannot bypass delivery checks by
removing the correction report. Unexpected manufacturing changes are rejected.

The earlier 1,556-record ledger remains bound to the original streams, at 376
executed, 439 absent, 90 explicit W/L exemptions and 651 unreviewed entries. These
eight boundary prohibitions are independently checked on the corrected streams;
no blanket transfer of prior decisions or reduction of that historical count is
claimed. Earlier nominal extraction/timing/equivalence evidence retains its
original scope. No new electrical rerun, installer or foundry acceptance is
claimed. The audit archive retains the real outputs and reproduction drivers.

```sh
python -m unittest tests.test_sky130_boundaries tests.test_sky130_pins tests.test_digital_macro -v
```

## Explicit grid catalog subjects

The [audit](validation/sky130-grid-catalog-audit-2026-10-15.json) and
[measurements](validation/sky130-grid-catalog-2026-10-15.json) resolve 105 exact
catalog subjects on the three unchanged filled layouts: 20 nonempty drawn-layer
vertex checks pass, and 85 subjects have no raw geometry or text. The 35 named
drawn-layer bindings use the explicit 0.005 µm grid in the captured assumptions
table. The public [assumptions](https://skywater-pdk.readthedocs.io/en/main/rules/assumptions.html)
and [periphery table](https://skywater-pdk.readthedocs.io/en/main/rules/periphery.html)
still disagree on units; this review records that discrepancy and does not
promote the broader `x.1a` or `x.1b` requirements.

The 70 mask/edit/package bindings reuse exact retained purpose mappings and
preserve whether each alias came from the published table or installed layer map.
They are resolved only by complete raw shape/text absence. Present data requires
further review even if it passes the diagnostic grid; no disputed mask/package
grid is selected for acceptance. Sixteen `metop1`–`metop8` grid/angle records
remain unreviewed because their operands are not established.

The raw diagnostic still reports **FAIL**: seven text anchors are off the
diagnostic grid, with two in counter, four in UART and one in APB. Those findings
retain their coordinates and cell names. All physical vertices pass. Accepting
the literal catalog vertex checks does not resolve the separate annotation scope
or change any GDS geometry or label position. Periphery and application ledger
counts remain unchanged; chunk 6 remains incomplete.

Twenty-two focused tests pass without skips on each OS, and the complete reports
are byte-identical. Controls exercise all 35 drawn bindings, all 70 absence-only
bindings, hidden/holed polygons, hierarchy/arrays, fractional transforms, path
outlines, text-only subjects and incomplete measurements. Every drawn binding
rejects a 1 nm shift; every present mask/edit/package operand prevents absence.
This review reuses unchanged application and electrical evidence and retains
its new results in a small archive referencing the preceding verified archive.

```sh
python -m scripts.sky130_grid_catalog_review --check
python -m unittest tests.test_sky130_grid_catalog tests.test_sky130_grid_density.GridTests -v
```

## Standard-cell width/length and dummy-poly review

The [audit](validation/sky130-standard-cell-wl-audit-2026-10-15.json) and
[measurements](validation/sky130-standard-cell-wl-2026-10-15.json) resolve 95
explicit catalog entries together on the unchanged filled references. Ninety
messages explicitly concern invalid device W/L under `poly.x.1`; these use the
published `poly.X.1` standard-cell exception and are recorded as
`standard-cell-wl-exempt`, separately from executed numerical checks. Five
`poly.x.1a` subjects are absent because no normalized `dummy_poly` text occurs
on any purpose. No Table H3 dummy-cell exception is used.

The captured job inputs authenticate the exact HD library. Every reachable cell
containing diffusion, poly or `areaid.sc` must be an unchanged library leaf;
all nonempty layer shapes and texts are compared, including device markers.
Each gate must lie within its own trusted cell marker. The transformed instance
gate union must equal the fresh final-layout gate union, and the weighted gate
count must match both that geometry and the retained native NFET/PFET census.
Counter has 2,240 gates in 17 distinct masters, UART 17,002 in 43, and APB 17,143
in 40. This does not trust a cell name or a user-added marker by itself.

This review interprets the `areaid.sc` W/L exception separately from the named
`scs8*decap*`/MRGA clause. It uses neither that named-cell exception nor pruned
devices, and establishes no missing MRGA numerical limits. All 60 RF fixed-layout
dimension records, invalid NFET/PFET recognition and the FGR-only restriction
remain unreviewed. Standard-cell W/L acceptance does not establish those distinct
requirements or qualify arbitrary user-created cells.

Twenty focused tests pass without skips on Windows and Linux. Controls reject
changed cells/markers, missing marker coverage, cross-instance gates, overlapping
instances, changed library bytes, stale native counts and unsupported geometry.
Nested rotations, mirrors and arrays preserve the correct counts. A dummy label
on any purpose reopens the five dummy records. The complete reports agree byte
for byte. The review reuses the authenticated native census and does not rerun
placement, extraction or the application checks, whose source and inputs are
unchanged. The audit retains the new evidence in a small archive referencing its
verified parent. Periphery and application ledger counts remain unchanged.

```sh
python -m scripts.sky130_standard_cell_wl_review --check
python -m unittest tests.test_sky130_standard_cell_wl tests.test_sky130_catalog_queue -v
```

Reproduction requires the retained `sky130-filled-electrical-v1` job inputs and
captured platform GDS in the workspace outputs directory; their identities and
archive entries are recorded by the audit. Missing or changed inputs fail closed.

## Local geometry, marked HV and hugePad correction

The [batched audit](validation/sky130-local-hv-audit-2026-10-15.json) and
[measurements](validation/sky130-local-hv-2026-10-15.json) resolve 29 literal
catalog records as absent on the unchanged counter, UART and APB layouts.
Thirteen concern local selected geometry; sixteen concern marked HV subjects
under the authenticated nominal reference voltage contract. This does not
qualify nonempty resistor, pad or HV circuits.

Fresh recursive measurements cover touching/overlapping diffusion and taps,
diffusion/poly/local-interconnect resistor purposes, both RPM and the separate
URPM layer, drawn pads, all five retained HV selectors and normalized HV labels.
An empty poly-resistor purpose alone is insufficient: both resistor implants
must also be absent. URPM records bind directly to their catalog text and
published layer purpose, without substituting the similarly named RPM rules.
Retained decisions are authenticated once rather than rerunning old extraction.

This review also finds an unsupported earlier `pad.3` exemption. C3 defines
`hugePad` using `pad.mk`, while the earlier witness measured only drawn `pad:dg`.
The manual describes maximum area, but catalog `r900` describes an invalid
minimum area. The mask construction and this wording conflict remain open.
The zero drawn-pad measurement is preserved; the periphery rule is reopened
as `execution-review-required`, and `r900` stays unreviewed.

Current Finish workers apply this correction. Saved-result validation and
macro export reject a missing correction or a restored absence claim. Older
results carrying the former exemption require rechecking under the current
policy; their historical source records remain intact. The actual application
checks and exports pass on all three unchanged references, retaining the pending
rule, with both invalid-claim controls rejected for each design.

Thirty-six focused tests pass without skips on each operating system, including
operand-presence controls, corner/edge contacts, hierarchy and arrays, raw text,
unsupported paths/transforms, incomplete voltage context, stale sources and
export tampering. Complete measurement reports are byte-identical across
Windows/Linux. Evidence is retained in the audit's readback-verified archive.
Earlier nominal timing/equivalence results keep their original scope; no new
placement, extraction, timing, installer or foundry acceptance is claimed.

The supplemental periphery ledger now has 135 executed rows, 280 absent,
77 upstream NA, 36 advisory, 61 other-backend, ten execution reviews, one
missing definition and one declared optional rule not required. The application's
six-profile ledger retains its separate scope of 133 executed rows and 28
execution reviews. Supplemental catalog decisions are not automatically promoted
into the application ledger. Full required physical coverage remains incomplete.

## Batched remaining work

The [catalog work queue](validation/sky130-catalog-work-queue-2026-10-15.json)
reconstructs the retained decisions for all three exact reference layouts and
assigned all 880 then-open records to one work batch. It authenticates
the retained checkpoints and their direct inputs, checks each intermediate
count, and rejects missing, overlapping or changed source records. It imports
no geometry engines and does not repeat extraction or historical geometry runs.
Six focused tests cover reconstruction, stale inputs, ambiguous assignments,
changed source identities and attempts to queue already resolved records.
The conservative-bound review above advances this baseline; its `remaining_original_batches`
retains every open record for the original streams. Current original-stream counts are:

| Work batch | Open catalog records |
| --- | ---: |
| Local geometry and resistor/pad selectors | 1 |
| Marked high-voltage geometry | 0 |
| Coordinate grids and layer aliases | 16 |
| Device identification and RF geometry | 77 |
| Core context and generated implant masks | 36 |
| Module cut and selected boundary rules | 69 |
| Frame, seal, scribe and alignment marks | 156 |
| Pads, package geometry and ViaTop | 76 |
| VPP, dummy diffusion and density | 17 |
| Connectivity, redundancy and chip labels | 7 |
| Routing blockages and boundary purposes | 8 |
| **Total** | **463** |

These are scheduling groups, not equally sized engineering tasks or completion
percentages. Every currently queued record remains `unreviewed`; grouping itself
adds no coverage decisions. The separate ten periphery reviews, missing `x.20` value,
and wider density/application obligations remain. No record moves to another
chunk merely because its batch mentions chip, pad or scribe context.
The eight boundary prohibitions have separate passing checks on the corrected
streams; they remain in this original-stream queue, whose outline-bearing inputs
are preserved. This distinction prevents acceptance from following only a renamed file.

Work proceeds through each batch's shared definitions and applicability,
implementation or exact evidence binding, passing and deliberately failing
controls, and checks on the three filled references. Source gaps are recorded
once and revisited when new information arrives. Existing results can be reused
only with matching inputs and scope. New checks still need integration into
Finish/export and consolidated Windows/Linux validation; a planning queue cannot
replace those gates. Run the inexpensive reconstruction with:

```text
python -m scripts.sky130_catalog_queue --check
```

## Application isolation gate

The [application isolation audit](validation/sky130-application-isolation-2026-10-14.json)
connects the reviewed `x.29` checker to Finish, saved-result validation and macro
export. Newly prepared bundled SKY130 HD platforms declare ordinary bulk mode.
The physical editor offers the platform setting, an explicit bulk override, or
required NMOS isolation. Changing the mode invalidates the saved Finish result.
An explicit override requires a platform carrying the authenticated checker.

Bulk mode retains the number and locations of NFET gates outside deep nwell as
`NOT_REQUESTED`; it does not claim a passing isolation check. Required mode
accepts only complete gate containment. Failed workers retain their measurements
and diagnostics. Export rejects missing policies, reports, raw worker results,
requests or captured checker resources, including removal of the entire claim.
The macro manifest retains the selected mode, result and measurements.

The audit exercises the actual application checker/export entry points on the
unchanged filled counter, UART and APB references, together with the six existing
geometry profiles, all thirteen antenna stages and OpenDB power connectivity.
The required-isolation control fails each bulk reference. Windows/Linux tests
also exercise a contained positive control, failed exports, resource changes,
relocation, setting persistence and the three reference geometries.

This closes the isolation integration gap. It does not discharge the nine
remaining periphery reviews, missing `x.20` definition, or outstanding required
catalog/density interpretation. Earlier nominal electrical evidence retains its
original scope; no new placement, extraction, timing or foundry acceptance is
claimed by this integration audit.

## Explicit reference isolation option

The [isolation audit](validation/sky130-isolation-options-audit-2026-10-14.json)
records `nfet_in_dnwell: false` in the new, explicit
[reference options](qualification/sky130-reference-rule-options.json). The three
existing HD references use ordinary bulk NMOS bodies tied to VSS; they do not
request a separate isolated-well domain. This choice applies to these exact
layout/checkpoint identities. It is not a default for arbitrary designs.

The published `x.29` requirement is conditional on this switch. Its C3 target is
`(poly AND diff) NOT nwell`. The checker measures complete target containment
in the merged drawn deep-nwell polygons in **both** modes. It invents no numeric
enclosure margin and does not substitute this check for well spacing, RF device
selection or electrical body connectivity.

| Reference | Measured NFET gates outside deep nwell | Declared bulk mode | Enabled isolation control |
|---|---:|---|---|
| Counter | 1,120 | NOT_REQUESTED | FAIL |
| UART | 8,500 | NOT_REQUESTED | FAIL |
| APB FIFO | 8,571 | NOT_REQUESTED | FAIL |

All 18,191 noncontained gates remain in the measurements. `NOT_REQUESTED` is
stored as `declared-option-not-required`, never as executed or absent. A missing
option, non-Boolean value or unsupported geometry fails validation. Explicitly
requesting isolation on these unchanged layouts fails; a synthetic contained
control passes. The command returns failure for an isolation violation and
rejects a missing mode without creating a report.

Both operating systems pass 18 tests without skips and reproduce identical
complete reference data. Actual command checks cover bulk, failing isolated,
passing isolated and missing-mode cases. Controls also cover partial enclosure,
well holes, joined well polygons, PMOS exclusion, transformed arrays, raw text,
straddling gates, invalid counts and altered source records. Reconstructing the
preceding 601-row ledger verifies every source identity and preserves every row
other than the explicit `x.29` decision.

```sh
python -m unittest tests.test_sky130_isolation_policy tests.test_sky130_isolation_review -v
python -m scripts.sky130_isolation_review --check
python -m scripts.sky130_isolation_policy --gds design.gds --mode isolated --output isolation.json
```

Use `--mode bulk` only for an explicitly declared ordinary-bulk design; its
successful command exit records a configuration, not a passing isolation rule.
The current ledger has 135 executed, 281 absent, 77 upstream NA, 36 advisory,
61 other-backend, one declared optional rule not required, nine execution
reviews and one missing definition. All catalog counts remain unchanged.
This historical standalone review leaves the six-profile ledger unchanged.
The [application isolation gate](#application-isolation-gate) now enforces the
selected option separately. Full physical coverage and chunk 6 remain incomplete.

## Nominal reference voltage contract

The [voltage-intent audit](validation/sky130-voltage-intent-audit-2026-10-14.json)
checks a new, explicit [reference contract](qualification/sky130-reference-voltage-contract.json):
ideal 1.8 V VDD, 0 V VSS, every external signal within those rails, and no declared
high-voltage supply nets. These are declared operating requirements for the
three fixed reference designs, not measured internal analog voltages.

The checker authenticates the final implementation, captured library and database
snapshot, native extraction and port inventory. Every physical port needs an
explicit range and matching net, direction and signal type. Every cell needs
captured library metadata or one of the five exact electrically empty fill/tap
masters from the locked CDL. Signal-pin domains and every supply/bias connection
must agree. The native MOS bodies must connect to their declared rails; unknown
models or missing extracted terminals fail the check.

| Reference | Physical ports | Cell instances | Supply/bias pins | Native MOS bodies |
|---|---:|---:|---:|---:|
| Counter | 8 | 3,330 | 12,660 | 2,240 |
| UART | 15 | 17,357 | 65,970 | 17,002 |
| APB FIFO | 30 | 17,189 | 65,298 | 17,143 |

Fresh recursive measurements find no raw HVI, HL, diffusion-HV, VHVI or UHVI
shapes and no `hv_bb`, `hv_lv` or `shv_nwell` labels. The published HV methodology
starts propagation from tagged diffusion. Together with the checked nominal
contract and the earlier complete drawn/native device census, this establishes
conditional absence for `hvnwell.11`, `hv.X.1` and `hv.X.4`. Any HV selector,
exception label, unsupported voltage range or changed source prevents that
decision. The checker does not implement propagation for a nonempty HV circuit.

Windows and Linux produce identical complete reports and pass all 21 tests
without skips. Controls cover incorrect supply/bias wiring, unsupported library
domains, missing or invalid port ranges, unknown native models/terminals,
different checkpoint identities, raw text in transformed arrays, nonempty HV
selectors, changed sources and unsupported geometry. The small verified archive
retains final sources, drivers, reports and earlier failed attempts; the original
large electrical/native captures are authenticated and reused.

```sh
python -m unittest tests.test_sky130_voltage_contract tests.test_sky130_voltage_intent -v
python -m scripts.sky130_voltage_intent_review --outputs /path/to/retained/outputs --electrical-manifest /path/to/retained/electrical/manifest.json --check
```

At this voltage-review checkpoint, the periphery ledger had 135 executed, 281 absent, 77 upstream NA,
36 advisory, 61 other-backend, ten execution-review and one definition-required
record. All 1,556 catalog dispositions remain unchanged. Generated implants,
RF selection, grid, frame/die geometry, `x.20` and the
remaining catalog/density interpretation remain open. This evidence establishes
neither transient overvoltage limits nor rail integrity, foundry latch-up/ERC,
general user-design coverage or full chunk 6 acceptance. Application policy is
unchanged.

## Selected catalog subjects

The [selected-subject audit](validation/sky130-selected-subjects-audit-2026-10-14.json)
resolves 63 explicit catalog records on each unchanged filled reference. It
reconstructs the preceding catalog evidence, checks its device-review link and
performs fresh raw-layer and Boolean measurements. No source row is removed and
no same-name rule inherits coverage automatically.

The selected records cover HVI/HL-derived geometry, varactor channels, optional
module-cut via sizes, slotted contacts, exact named-cell contact/LI variants,
photodiodes, RF-diode identifiers and three general selector checks. The entire
raw HVI and HL selectors are empty; this establishes absence of those geometric
subjects. Voltage intent is addressed separately by the conditional nominal
contract above. The varactor decision proves that all poly/tap
intersection is empty. Slotted-contact decisions require both no exact merged
0.19 by 2.0 micrometre contacts and no raw RPM. Named-cell decisions use the
published exact names and the single explicitly published trailing wildcard.

Both systems pass 11 tests without skips and produce identical complete data.
Controls cover every nonempty operand, raw text in transformed arrays, rejected
zero-width paths, hierarchical varactor intersections, merged slotted contacts,
all named-cell selectors, unsupported geometry, altered sources, invalid counts,
failed parents and removal of an unrelated catalog record.

```sh
python -m unittest tests.test_sky130_selected_subjects -v
python -m scripts.sky130_selected_subject_review --check
```

The catalog now contains 356 executed, 320 absent and 880 unreviewed records.
These entries are not 880 independent active block rules. All 601 periphery
rows and their dispositions remain unchanged: 13 execution reviews and the
undefined `x.20` numeric value are still open. No numeric execution on nonempty
special devices, fresh native extraction or application-policy change is
claimed. The archive preserves exact sources, drivers, reports and logs without
duplicating the committed reference-layout fixture.

## Device intent and created implant masks

The [device-intent audit](validation/sky130-device-intent-audit-2026-10-14.json)
checks every drawn MOS gate against the complete native device census from the
retained exact filled captures. It authenticates those native files against both
their capture manifests and the previously accepted circuit readback. No fresh
native extraction or geometry modification is claimed.

| Reference | Standard 1.8 V NMOS gates | High-Vt 1.8 V PMOS gates | Total matched gates |
|---|---:|---:|---:|
| Counter | 1,120 | 1,120 | 2,240 |
| UART | 8,500 | 8,502 | 17,002 |
| APB FIFO | 8,571 | 8,572 | 17,143 |

All 36,385 MOS gates are accounted for. Every PMOS gate is contained in HVTP,
no NMOS gate overlaps HVTP, and no gate straddles a well boundary. The APB native
census additionally retains its three diodes and two poly resistors. Unknown
device models or mismatched MOS counts prevent the review from passing.

The locked [F2a drawn-device table](qualification/sky130-device-tables/table-f2a-lvs.tsv)
marks HVTR illegal for both HD MOS types. The periphery table explicitly names
the low-Vt RF device in its HVTR section. This combination of device identity,
complete drawn-gate accounting and absent HVTR supplies the missing target
context for `hvtr.3` and catalog record `r426`. The F2a floating-gate HV varactor
requires drawn LVTN, HVI, tap and poly. No such model, either drawn selector, or
poly/tap intersection exists in these references, closing `licon.19`/`r759` for
these exact layouts. These are absence decisions, not numeric execution on
nonempty RF or varactor devices.

The same tables prevent a broader exemption: F2a marks the HD high-Vt PMOS LVTN
as CAD-created, and the [F2b mask table](qualification/sky130-device-tables/table-f2b-mask.tsv)
requires generated LVTNM and NCM. Consequently, `lvtn.4b` and `ncm.3` remain open
for their generated-mask construction and enclosure semantics. Empty drawn
layers cannot discharge those obligations. The tables are retained verbatim
with their license from upstream revision
`7198cf647113f56041e02abf3eb623692820c5e1`; the audit binds the exact relevant rows,
column meanings, legends and source hashes.

Windows and Linux produce identical complete reports, with 14 tests passing per
OS without skips. Controls cover substituted device models, missing/extra native
MOS counts, missing/misplaced HVTP, straddling gates, nonempty selectors, text in
hierarchy, changed sources, changed capture hashes and unsupported geometry.

```sh
python -m unittest tests.test_sky130_device_intent -v
python -m scripts.sky130_device_intent_review --captures-root /path/to/retained/outputs --check
```

The second command requires the original native captures, not fabricated census
summaries. The capture paths and hashes remain recorded in the report. This
review has 135 executed periphery requirements, 278 absent, 77 upstream NA,
36 advisory, 61 other backend, 13 execution reviews and one missing definition.
The application policy remains unchanged. In the preceding obligation table
below, `hvtr.3` and `licon.19` are now resolved only under this stronger review;
all other listed obligations remain open.

## ESD and fuse target review

The [fresh Windows/Linux audit](validation/sky130-esd-fuse-audit-2026-10-14.json)
measures the unchanged filled counter, UART and APB layouts using the committed,
authenticated fixture. Both platforms reproduce identical
[source-bound decisions](validation/sky130-esd-fuse-2026-10-14.json). The 13 tests
pass on each platform without skips. They include nonempty marker/target controls,
text and zero-width paths in transformed arrays, altered evidence identities,
invalid counts, changed sources and removal of unrelated ledger requirements.

`ncm.4` specifically selects P+ diffusion within `areaid.ed AND NOT areaid.de`.
The raw `areaid.ed` layer is empty in all three layouts, so its required target is
empty. This proof does not depend on missing NCM and does not discharge `ncm.3`.
`x.11` and exactly 32 fuse catalog records have no fuse/target subjects under
the captured C3 definitions. The published metal4 fuse purpose, independent
target, other installed fuse purposes and a conservative metal2 guard are all
empty. Adding any of them reopens every fuse decision. Catalog/manual numeric
discrepancies are retained: no nonempty fuse dimension is claimed verified.

All 601 periphery rows remain present: 135 executed, 276 absent, 77 upstream NA,
36 advisory, 61 other backend, 15 execution reviews and one missing definition.
All 1,556 catalog records remain present: 356 executed, 255 absent and 945
unreviewed. Catalog records include multiple manifestations of one rule and
chip-specific entries; 945 is not a count of independent active block rules.
The actual application's narrower six-profile policy is unchanged by this
qualification review.

Reproduce the target review with:

```sh
python -m unittest tests.test_sky130_esd_fuse -v
python -m scripts.sky130_esd_fuse_review --check
```

These commands verify this bounded review, not complete physical signoff.
The small durable archive retains both platform logs, source, drivers and
byte-checked reports. Its input GDS/manual fixture is already committed; the
archive does not duplicate the large native evidence bundles.

The current remaining periphery obligations are explicit. The device-intent
review resolves the earlier `hvtr.3`/`licon.19` rows, and the nominal voltage
contract conditionally resolves the three voltage rows for these references.
The explicit bulk option above resolves the `x.29` mode selection without
claiming that its nonempty NFET targets pass isolation:

| Obligation | Remaining work |
|---|---|
| `x.1a`, `x.1b` | Resolve published grid units/purpose interpretation and seven text-anchor diagnostic findings. Physical polygon vertices already pass the 5 nm diagnostic. |
| `dnwell.6`, `difftap.13`, `poly.16` | Establish the referenced RF fixed-layout model map and Table H5 selections. |
| `lvtn.4b`, `ncm.3` | Resolve generated-mask construction and enclosure semantics. Missing drawn enclosing layers are insufficient evidence. |
| `nsm.3a`, `nsm.3b` | Establish frame/die-cut context and applicable boundary geometry. |
| `x.20` | Obtain the omitted numeric same-layer pin-spacing definition for the `IP_block` mode. |

The remaining catalog entries also need explicit execution, applicability or
source-definition review, including the unfinished VPP density selector. None
of these obligations is converted to a pass by the absence proofs above.

## Final filled-reference electrical checks

The [electrical audit](validation/sky130-filled-electrical-2026-10-14.json)
uses the unchanged filled counter/UART v20 and APB v22 GDS and decap checkpoints.
Fresh application entry-point executions pass all six reviewed geometry profiles,
all 13 antenna stages, OpenDB antenna/power checks and macro export. The actual
checkpoint supplies a new netlist, DEF, LEF, database view and nominal OpenRCX
extraction. The exported bundles retain these exact inputs and check results.

The application then consumes each final finish result for timing and formal
equivalence. Timing uses the implementation's final SDC, the captured typical
library and the freshly extracted SPEF. Every connected driver has parasitics;
there are no setup, hold or electrical violations.

| Final filled reference | Setup margin (ns) | Hold margin (ns) | Sequential equivalence |
|---|---:|---:|---|
| Counter | 47.654427 | 0.291230 | Pass |
| UART | 3.353671 | 0.454787 | Pass |
| APB FIFO | 15.705125 | 0.280405 | Pass |

All original and final routed SPEFs match exactly after removing only the
timestamp line. The final netlists include the added decaps, and formal proofs
establish the original RTL behavior without adding reset assumptions. UART's
frame partition needs PDR after an inconclusive induction attempt. Both the
completed proof and the intermediate induction trace remain available.

Deliberate controls fail as required: a 1 ps clock produces negative setup
margin; removing a connected net's parasitics produces INCOMPLETE despite
positive timing margins; a mapped output inverter produces a formal failure
and trace. An earlier unmapped inverter control was rejected before proof and
is retained separately. Windows and Linux independently reparse the raw timing
and proof files, verify every exported artifact and reproduce all three passes
and three expected failures. All 14 new binding/report tests pass on both.

OpenRCX describes checkpoint routing; it does not extract the GDS-only floating
fill. The earlier exact native circuit-invariance result remains the separate
nominal evidence for that fill under ideal supplies. These checks establish
the bounded nominal electrical gate, not calibrated extraction, process/RC
corners, power integrity, automatic fill generation, a rebuilt installer or
complete chunk 6 acceptance. Existing production engine code is unchanged.

```sh
python -m scripts.check_sky130_filled_electrical --directory path/to/counter --case counter
python -m unittest tests.test_sky130_filled_electrical -v
```

## Waffle-drop density conditions

The [source-bound review](validation/sky130-waffle-density-2026-10-14.json)
resolves exactly `r1210`–`r1233` and `s44`–`s67`. Every listed metal-density
requirement first needs at least 30% waffle-drop coverage in a 700 µm window.
Fresh recursive measurements find all four relevant raw waffle-drop layers
empty on each exact filled reference. Their coverage is therefore zero in
every possible window, independently of origin or edge clipping. The required
IP conditions are retained and evaluated through this absence proof.

This does not substitute ordinary drawn-metal density for oxide density, execute
nonempty waffle-drop rules, or establish a complete-chip boundary. Seven tests
per operating system cover exact source/parent bindings, every inserted operand,
raw shape types in rotated arrays, malformed measurements and stale inputs.
Both complete reports match byte for byte. These 48 decisions extend the earlier
marker ledger; every other catalog record and all periphery states are preserved.

The `vpp_over_MOSCAP` density record remains unreviewed: its published C3 selector
contains unfinished cell-name definitions. That record is not included in the
empty waffle-drop proof. The [density audit](validation/sky130-waffle-density-audit-2026-10-14.json)
retains the tests and source identities. No nonempty density or process-wide
acceptance is claimed.

```sh
python -m scripts.sky130_waffle_density_review --check
python -m unittest tests.test_sky130_waffle_density -v
```

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

## Application antenna gate

The [application gate](../icstudio/digital_sky130_antenna.py) runs the unchanged,
checksum-locked [13-stage deck](../scripts/sky130_staged_antenna.drc) after the
reviewed geometry profiles. The [platform preparer](../scripts/prepare_sky130_antenna.py)
captures its policy and deck. The bundled-platform builder now attaches that
policy; a rebuilt runtime and installer still need delivery acceptance.

Finish requires the reviewed native KLayout version, every stage and its exact
numeric settings, matching raw report counts, and zero violations. Inputs,
checkpoint, engine, platform, top and deck are bound to the saved evidence.
Failures retain diagnostics. Exports retain the native report, metrics, deck,
invocation and checkpoint, and reject missing, changed or stripped evidence.
Historical platforms without this policy retain their earlier limited scope.

The [application audit](validation/sky130-application-antenna-2026-10-14.json)
records fresh native executions on the exact filled counter, UART and APB
references: all 39 stage executions pass. The independent 178-control fixture
produces all 90 expected faults and accepts all 88 passing controls; the
application correctly refuses that deliberately faulty fixture. Separate actual
Runner executions pass boundary-pin export, six geometry profiles, staged
antenna, default OpenDB antenna/power checks and macro export on the three
retained original routed designs. Both Windows and Linux validate the saved
native evidence and relocated export contents. These runs do not perform new
place/route, regenerate fill, or establish final filled timing or full-rule LVS.

The related 97-test suite passes on both operating systems: 95 run and two
Windows-specific tests skip on Linux; 90 run and seven Linux/symlink tests skip
on Windows. All 11 new antenna integration tests run on each system. Initial
Windows sandbox access and an overly long temporary fixture path caused test
harness failures; the retained successful rerun uses a shorter writable path.
The original failure logs remain available with the audit.

This is the captured five-metal HD MOS supplement. Other device/process options
and the published met5 description discrepancy remain explicit limitations.
The periphery and error-catalog coverage counts above are unchanged, and
`chunk_complete` and `qualified` remain false.

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

## Portable final-filled replay on Windows and Linux

The [final-filled replay](validation/sky130-filled-replay-2026-10-14.json)
now executes on the actual counter v20, UART v20 and APB v22 GDS files on
Windows and Linux. All three hashes match the original fill checkpoint.
Fresh applicability and all six supplemental geometry/connectivity profiles
reproduce their retained reports exactly. Reconciliation of the fresh reports
reproduces 135 executed periphery requirements, 356 executed error records
and 39 absent error operands per design. All 408 notch controls also reproduce.
The two operating systems produce identical complete replay JSON.

The [runner](../scripts/check_sky130_filled_replay.py) uses the committed
[13 MB fixture](../tests/fixtures/sky130-filled-references-v1.zip): three exact
filled GDS files, independent original OpenDB pin/die inventories and all 165
pinned source files plus their lock. Its 172 inputs are authenticated before
writing to a new temporary directory. Archive, manifest, individual file and
independent checkpoint hashes are checked. Missing, duplicate, changed or
unsafe members are rejected. The full 920 MB native evidence archive remains
preserved separately; it is no longer needed for this polygon replay.

Fresh final-filled diagnostics find zero off-grid physical vertices and seven
off-grid text anchors: two counter port labels, four labels in the UART's
`sky130_fd_sc_hd__a222oi_1` master and one APB port label. They are retained as
findings, without moving labels or changing geometry. The density report still
measures raw metal occupancy, has no full 700 µm windows on these block dies,
and remains `BLOCKED`. Neither the grid-unit discrepancy nor oxide-density
semantics is resolved by rerunning the correct inputs.

All 215 incoming tests passed on each OS. The Windows reproduction then exposed
a source-path separator defect in the geometry reconciliation report. Canonical
forward-slash paths fix that defect; only source identities changed in the
reproduced report, not its rule findings. All 28 focused portability, fixture
and reconciliation tests pass on each OS. The initial Windows failure, original
incoming source/report, passing Linux run and corrected runs are retained in the
[audit record](validation/sky130-filled-replay-audit-2026-10-14.json).

```sh
python -m scripts.check_sky130_filled_replay --check
python -m unittest tests.test_sky130_filled_replay tests.test_sky130_geometry_reconciliation -v
```

The replay deliberately exits **2** after saving/checking the report because
chunk 6 remains blocked. A successful reproduction is not a passing process
gate. These runs use the KLayout 0.30.5 Python library on Windows/Linux; they
do not assert fresh native Magic/Netgen/OpenROAD, installed-engine or installer
acceptance. The earlier native evidence retains its original scope.

## Recommended oxide-density window scope

The [source-dependency review](validation/sky130-density-scope-2026-10-14.json)
resolves eight periphery reviews without claiming new density execution.
Each `m1`–`m4.pd.2a/2b` row explicitly names its corresponding `.pd.1` parent;
each parent carries the published **RR** recommendation flag. The child rows
specify the measurement window and step of that recommendation. Their exact
CSV records, descriptions, flags, values and units are checked against captured
source bytes, together with the published RR definition.

The eight children now retain **advisory** status alongside their parents.
An `A` flag by itself never establishes advisory status. The separate required
`m1`–`m4.-` RC metal/waffle-drop algorithms and every other row are unchanged.
The blank step unit, undefined oxide construction and edge policy remain
explicit; the density diagnostic is still `BLOCKED`, not a pass. Five focused
source/tamper controls pass on each OS, and both reproduce the same review.

At this stage the periphery ledger had 135 executed requirements, 277 absent operands,
77 upstream NA, 36 advisory rows, 61 other-backend rows, **14 execution reviews**
and one missing definition (`x.20`). The 1,161 unreviewed error-catalog records
are unchanged. This source review follows the filled replay's earlier 22-review
baseline; it does not rewrite the recorded measurements.
The subsequent source corrections below reopen three of these absence decisions.

```sh
python -m scripts.sky130_density_rule_scope --check
python -m unittest tests.test_sky130_density_rule_scope -v
```

Remaining execution reviews cover grid units, metal-fuse applicability, optional
DNW configuration, RF/special-device selectors, NCM construction and independent
voltage intent. The missing numerical pin-spacing definition, remaining catalog
reconciliation, required density coverage and final timing/equivalence/application
acceptance still prevent completion of chunk 6.

## Application integration of reviewed geometry

The digital runtime builder now attaches `sky130-reviewed-geometry-v2` to its
SKY130 HD platform. Physical Finish runs the six reviewed drawn-mask profiles
after boundary-pin export. The platform captures 177 authenticated helper/manual
resources; no reference GDS is included in those runtime resources. A changed or
missing resource is rejected before helper code can execute. Failed checks keep
their diagnostics and cannot produce an accepted report.

The saved result and macro export retain the exact GDS/checkpoint identities,
all mandatory checks, the 601-row manual ledger and the captured source resources.
Missing profiles, altered check counts, changed execution bindings, incomplete
ledgers and removed policies are rejected. Exported artifacts remain verifiable
after relocation. The export explicitly says that SKY130 signoff is unqualified.
Historical platforms without the new policy retain their original limited scope.

The [application audit](validation/sky130-application-rules-2026-10-14.json)
distinguishes production entry-point runs on retained original routed checkpoints
from replay of the three exact filled candidates. It also retains a deliberately
invalid metal layout and unsuccessful test/comparison attempts. These checks do
not claim new synthesis/place/route, fill generation, complete native-deck
execution, extracted timing or a rebuilt desktop/runtime installer.

This first production policy retains the six-profile baseline: 133 executed
periphery requirements. The subsequent two geometry bindings and eight advisory
source reviews remain in the separate, more advanced qualification ledger above;
they are not silently promoted into runtime coverage. Full rule reconciliation,
required density, final filled-layout timing/equivalence and delivered application
acceptance still prevent completion of chunk 6.

```sh
python -m scripts.prepare_sky130_rule_checks --platform platform.json --output platform/sky130hd/verification --manifest reviewed-platform.json
python -m unittest tests.test_sky130_application_rules -v
```

## Corrected enclosure and boundary applicability

The [source correction](validation/sky130-scope-corrections-2026-10-14.json)
reopens three unsupported absence decisions. The published `hvtr.3` wording
requires enclosure of PFETs by HVTR without explicitly defining the selected
PFET subset. An absent HVTR layer cannot prove that the required target is
absent. Its device-selection interpretation remains open.

The `nsm.3a` and `nsm.3b` descriptions require frame enclosure and die-cut
spacing for drawn/mask geometry. Neither requirement depends on NSM being
present. Empty NSM measurements therefore cannot establish compliance. The
complete boundary geometry and stated exceptions still require review.

The corrected qualification ledger has **135 executed requirements, 274 absent
operands, 77 upstream NA, 36 advisory rows, 61 other-backend rows, 17 execution
reviews and one missing definition**. Error-catalog coverage is unchanged:
356 executed, 39 absent and 1,161 unreviewed. Earlier measurements and reports
are preserved; these three historical exclusions are superseded.

The application applies the same corrections after executing its six profiles.
Its separate baseline still has 133 executed bindings, with 27 execution reviews.
Version 2 of the policy rejects reports missing the correction or restoring the
old exclusions. A platform prepared with version 1 must be prepared and checked
again under the current policy before current-policy export; editing an old
report cannot substitute for that run.

The [correction audit](validation/sky130-scope-correction-audit-2026-10-14.json)
records 22 passing tests on each operating system, fresh application finish/export
checks on the original counter/UART/APB checkpoints, and filled-reference worker
replay on Windows and Linux. The three filled reports and rejected synthetic
layout report match byte for byte across systems. All six profiles remain
present, and the invalid layout retains diagnostics without an accepted ledger.
These runs do not establish full-rule coverage, final filled-layout timing,
a rebuilt delivery package or completion of chunk 6.

```sh
python -m scripts.sky130_scope_corrections --check
python -m unittest tests.test_sky130_scope_corrections tests.test_sky130_application_rules -v
```

## Nitride-seal error-record reconciliation

The [NSM reconciliation](validation/sky130-nsm-reconciliation-2026-10-14.json)
resolves the explicit block records `r950`–`r987` as **absent operands** on each
of the three exact filled references. The published C3 definition makes
`NSM_keepout` the union of `nsm.dg` and `nsm.mk`; the captured layer map binds
these to the drawn nitride seal at 61:20 and its mask at 22:0. Fresh recursive
measurements find both empty. Width, self-spacing, and spacing/no-overlap to
that empty union have no subject geometry. No non-empty seal is claimed tested.

The 38 exact IDs, descriptions and parent records are checked against source
bytes. The neighboring `nsm.3a`/`nsm.3b` frame/die-cut records and all chip-level
records retain their prior state. A shared name never extends this exclusion.
The report stores only the 38 decisions per design and references the full
preceding ledger by checksum, preserving all other records without duplicating
the historical report.

The [Windows/Linux audit](validation/sky130-nsm-review-2026-10-14.json) records
ten passing tests per OS, with identical complete reconciliation reports.
Controls insert boxes, polygons, paths, zero-width paths and texts in rotated
array instances on either operand; every inserted shape prevents absence.
Missing or invalid counts, stale input identities and changed sources also fail.

Current error-catalog coverage is **356 executed, 77 absent and 1,123 unreviewed**.
Periphery coverage is unchanged, including its 17 execution reviews and missing
`x.20` definition. This review does not rerun the six geometry profiles, full
native checks or final electrical acceptance, and does not change the application
runtime policy. Chunk 6 remains incomplete.

```sh
python -m scripts.sky130_nsm_reconciliation --check
python -m unittest tests.test_sky130_nsm_reconciliation -v
```

## Selected marker and well-hole records

The [marker review](validation/sky130-marker-reconciliation-2026-10-14.json)
adds 98 explicit absent-subject decisions on each unchanged filled reference.
The source-bound groups cover selected deep-well, LVTN, HVTR, HVI, RDL, RPM,
TUNM, HVNTM, VHVI, drain-extended and NCM records. Every ID has an exact parent
and an explicit empty-subject condition; names and table membership do not
automatically extend coverage.

The enclosed targets are checked independently of their enclosing layers.
The nwell-hole requirement uses holes of the merged nwell polygon union;
all three layouts have nwell geometry but no such holes. PAD must be absent
for its RDL enclosure decision. Both HVI and HVNTM must be empty for the
selected high-voltage implant decisions. The captured C3 definitions establish
which resistor and drain-extended/VHV subjects require their markers.
Operating-voltage intent is not inferred from missing voltage markers.

The RDL and CCU1M mask aliases come from the pinned installed layer map;
their provenance remains distinct from the published aliases. Unsupported
nwell paths and non-unit/non-orthogonal instance transforms are rejected before
hole measurement. Raw marker counts include every referenced shape, including
texts and paths.

One source disagreement remains explicit: error record `r415` gives 0.19 µm
for `lvtn.3b`, while its periphery table gives 0.235 µm. Empty LVTN has no spacing
subject under either value; no threshold is selected or claimed implemented.
Ambiguous gate-enclosure/extension and drain-extended catalog targets, neighboring
frame/die-cut records and all chip-level records retain their previous states.

The [audit](validation/sky130-marker-review-2026-10-14.json) records 12 passing
tests on Windows and Linux and identical complete reports. Controls cover every
required operand, raw shapes in rotated arrays, merged well holes, present
targets with empty enclosing layers, stale identities and altered sources.
Current error coverage is **356 executed, 175 absent and 1,025 unreviewed**.
The 17 periphery execution reviews and missing `x.20` definition remain open.
This does not establish non-empty device qualification, new native/full-profile
execution, final electrical acceptance or completion of chunk 6.

```sh
python -m scripts.sky130_marker_reconciliation --check
python -m unittest tests.test_sky130_marker_reconciliation -v
```
