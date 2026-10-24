# IHP bipolar layout verification

The [execution record](validation/ihp-bipolar-layouts-2026-10-17.json) adds
ten sampled `pnpMPA` layouts with zero full Magic DRC findings, public KLayout
extraction and strict Netgen LVS. All 35 deliberate faults are detected.
This closes the sampled PNP extraction gap; chunk 7 remains in progress.

The subsequent [NPN record](validation/ihp-npn-layouts-2026-10-17.json) adds
36 passing layouts across `npn13G2`, `npn13G2l` and `npn13G2v`, with all 99
physical/reference faults detected. Independent audits check 135 native circuits,
90 comparison circuits, 45 rejected missing interfaces and all mask changes.
Fifty-four geometry comparisons reproduce the corrected rule's seed, connected
components and illegal mask exactly, including the native square-offset metric
at diagonal edges. This is finite physical coverage, not full bipolar signoff.

| Model | Emitter width/length (µm), emitter count |
| --- | --- |
| npn13G2 | 0.07/0.9, counts 2, 5, 8, 10 |
| npn13G2l | 0.07/1, count 1; 0.07/2.5, count 1; 0.07/2, count 3 |
| npn13G2v | 0.12/1, count 2; 0.12/5, count 4 |

Each passes at 0, 90, 180 and 270 degrees. These four-terminal layouts do not
qualify the separate five-terminal thermal models or all generator settings.

## Use and reproduce

For an IHP project, choose **Verify → Physical verification → Verify IHP layout
with KLayout extraction…** and select a self-contained schematic reference.
The ordinary DRC/LVS action continues to use Magic extraction. Both routes
retain the exact project, original GDS, reference, source identities and logs.
The included Linux/WSL backend transfers and verifies the additional rule bundle.

```sh
python scripts/qualify_ihp_pnp_layouts.py --output /new/pnp-results --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout --workers 4
```

The five W/L pairs are 2/0.7, 2/5, 10/0.7, 2/7 and 7/2 micrometres.
Each passes at 0 and 90 degrees, with save/reopen and independent GDS/OASIS
exchange preserving every mask and electrical annotation. The reference uses
collector/base/emitter order and independently calculated emitter area/perimeter.
Negative controls remove contacts from each terminal, short collector/emitter,
reverse the reference polarity, or alter reference area or perimeter by 20%.
The short also crosses the base ring; it is not claimed as an isolated two-net
short. Independent readback checks all 45 native and 45 comparison netlists,
all mask changes, extracted geometry and fault locations.

## Why a second extraction route is needed

The bundled public Magic input deck recognizes PNP devices through a small
deep-nwell heuristic. Larger sampled shapes disappear from its extracted
circuit even when DRC passes. The original failing runs remain in the evidence.
This does not justify changing the expected schematic or suppressing a check.

The additional [public IHP runset](https://github.com/IHP-GmbH/IHP-Open-PDK/tree/5e6d592e4002946a4616f798c357f0f3c06cf3b6/ihp-sg13g2/libs.tech/klayout/tech/lvs)
recognizes PNP emitter, base and collector from the process masks. Studio retains
its unmodified files, original copyright headers, Apache-2.0 license and exact
hash inventory [with the bundle](../icstudio/assets/physical/ihp_klayout_lvs/README.md).
The project's adapter remains GPL-3.0 code. No private source or remote checking
service is used.

Studio explicitly disables comparison alignment, simplification, combining,
purging and implicit net connections during extraction. An early exploratory
run of the upstream comparison emitted a match after dropping unmatched NPN
circuitry. That result is retained as a failure, not acceptance. Studio checks
the unfiltered extracted circuit, rejects empty output and missing interfaces,
then requires strict Netgen device/property/port matching.

Recorded interoperability conversions are required. The private engine
input duplicates IHP datatype-2 pin text onto datatype 25, which the public
KLayout runset reads. Original pin text, coordinates, masks and user exports
remain intact. The native BJT `Q` instance prefix becomes `X` for the same public
IHP subcircuit model, terminal order and parameter text expected by Netgen.
No extracted number is adjusted. Unknown BJT interfaces and duplicate converted
instance names are rejected; raw output is always retained.

The pinned writer's unnamed L/V devices use a numeric instance prefix because
its prefix table uses uppercase model suffixes. Studio accepts only that exact
known fallback interface and records its conversion to `X`. The single flat
top declaration can be reordered to the schematic's port order only when both
have identical, unique port names. Device nodes and all net names remain intact.

Each run now copies the source bundle into its evidence directory and explicitly
identifies a local NPN extraction correction. The public recognition rules use
the short and long sides of emitter rectangles, but the original writer measured
global X/Y dimensions. The private correction measures physical short/long sides
at every rotation and rejects nonrectangular or unequal emitters in one device.
It leaves PNP geometry, device recognition, terminal connectivity and emitter
count unchanged. A separately recorded private Netgen setup retains emitter
count (`Nx`); the public setup otherwise discards it. Original files, copyright
notices and licenses remain preserved, with local modifications clearly marked.

## Default NPN rule entry point

New IHP projects select package `cfb96b74cf33877e`, whose explicit Magic
entry point is `libs.tech/magic/icstudio-ihp-sg13g2.tech`. It selects the
previously reviewed NPN correction in a separately named CIF output file.
The 160 earlier assets, simulation bindings and their original licenses are
unchanged. The new package adds only that entry point, the corrected rule file
and provenance. Existing saved projects retain their registered revision.

```sh
python scripts/prepare_ihp_npn_default.py --output /new/ihp-default-package
python scripts/qualify_ihp_npn_layouts.py --package /new/ihp-default-package --output /new/npn-results --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout --workers 2
```

The first command reproduces the bundled package byte for byte. The second
verifies that exact package, checks all locked assets and requires its identity
to remain unchanged throughout the run. Omitting `--package` still reproduces
the historical, separate qualification package through the retained recipe;
historical evidence is not relabeled as current-default evidence.

The NPN correction addresses Magic's
first-intersecting-tile behavior: a broad seed can miss a separate collector.
Intersecting that seed with the original active set first gives each component
its own search. All original rule operands, distances and the final illegal-mask
calculation are retained. Independent connected-component and Boolean geometry
audits check the result; unrelated diffusion and well islands must still fail.

The unmodified reference GDS/CDL and Apache-2.0 license are retained under
`icstudio/assets/physical/ihp_bipolars`. Local fixtures add metal and contacts
inside the existing substrate guard. Every original device mask is preserved.

The [default integration record](validation/ihp-npn-default-2026-10-18.json)
covers nine public NPN geometries in all four rotations: 36 passing layouts
and 99 detected physical/reference faults. Independent readback checks 135
native netlists, 90 converted comparison netlists, 2,160 layer comparisons and
the exact rule entry point in all 135 runs. User exports preserve all original
text anchors. Only the private checker input removes noninterface labels;
all 345 removals across this batch agree with the recorded transformation.

The same default passes ten PNP layouts and 35 fault controls, twenty tap
layouts plus two public-format checks and 48 fault controls, and ten
representative MOS, resistor, MIM and bipolar regressions. Both source editor
actions pass. Nine Windows staged backend cases accept all three valid NPN
families and reject one open collector and one wrong-width reference per
family, returning 714 hash-verified files. These checks close the default
NPN rule-selection gap; they do not establish installed-executable acceptance.

## Validation and remaining work

Forty focused regression tests pass on Windows and Linux. The source desktop
action is exercised on both hosts; a captured choice executes through a staged
local backend and its returned evidence is verified. Fourteen representative
default-route MOS, resistor and MIM layouts pass across SKY130, GF180 C/D and IHP.
These are source/runtime checks, not acceptance of the previously installed
desktop executable. Earlier digital production-gate source bytes remain
preserved separately and retain their original scope.

The subsequent NPN changes pass 31 focused tests on each host. Four PNP layouts
and fourteen deliberate faults pass regression; the existing PNP runner separately
passes its two-layout/seven-fault case. A saved desktop selection executes a
three-emitter NPN through the staged source backend, which returns and verifies
80 evidence files, including the private recipe and comparison setup. The
19.7 MB archive retains accepted and failed runs, source files and licenses;
1,200 files were restored and verified before redundant temporary runs were
removed. This does not establish installed-executable acceptance.

The original NPN generator failures remain historical evidence. The public
reference-cell route resolves selected physical cases, while continuous geometry
and operating ranges, thermal/RF/statistical behavior, complete-chip rules and
manufacturing signoff remain unqualified. Other device families and installed
release acceptance continue to block completion of chunk 7.
