# SKY130 threshold-variant layouts

The layout generator now accepts the four-terminal ordinary and `_nf` views of
`nfet_01v8_lvt`, `pfet_01v8_lvt` and `pfet_01v8_hvt`. Select the device and use
the existing generated-layout review. Regeneration, undo/redo and project
save/reopen preserve the model and threshold implant. This is source support;
the exact installed release needs separate acceptance.

The generator draws LVTN on 125/44 or HVTP on 78/44 around the actual channels.
The implant encloses the channels by 180 nm. LVT PMOS retains 380 nm of NWell
outside the implant and requires at least 0.35 µm channel length. Other existing
generator bounds, total-width/per-finger conventions and parallel-copy semantics
remain in force. The standard NMOS/PMOS geometry path is unchanged.

The public rule tables and GDS layer map are retained unchanged, with their
Apache-2.0 license and exact source identities, in
[the source lock](qualification/sky130-threshold-sources-v1/source-lock.json).
They come from the existing pinned public SKY130 revision
`7198cf647113f56041e02abf3eb623692820c5e1`. Original Studio code uses the project
license. No private model or rule package is introduced.

## Verified cases

The [execution record](validation/sky130-threshold-layouts-2026-10-21.json)
contains these completed local checks:

| Check | Result |
| --- | --- |
| Three models, five configurations, four rotations | 60 layouts pass full native Magic DRC, the pinned public KLayout block DRC and strict Netgen comparison |
| Missing/wrong implant, drain/gate/body contact opens, reference width/length and crossed gate/body | All 120 native faults detected |
| Final runner pilot | Three layouts and 24 faults pass |
| Independent readback on Windows and Linux | All 60 graphs, 216 channels, 120 stream comparisons and 1,620 integrity bindings verified on each host |
| Windows staging and local native backend | Three parallel multifinger layouts pass; all three missing-implant controls fail as required; 144 returned files verified |
| Affected source regression suites | 30 tests pass on each host, including actual ngspice execution, with zero skips |
| Additional catalog/migration and existing layout suites | 32 tests pass on each host, with zero skips |
| Source desktop actions | All six views pass generation/review, undo/redo, resizing/regeneration and save/reopen on both hosts |

The five configurations per model are minimum-width single-finger geometry,
4 µm × 1 µm single-finger geometry, two 1 µm fingers, eight 0.42 µm fingers,
and three parallel copies of the two-finger device. Multifinger lengths are
0.5 µm. Minimum lengths are 0.15 µm for LVT NMOS/HVT PMOS and 0.35 µm for LVT
PMOS. `_nf` views specify width per finger; ordinary views specify total width.

The independent native reader requires the exact model, all four terminal roles,
channel length and summed width across fingers/copies. It rejects extra circuit
directives, duplicate or unknown parameters and nonfinite values. Its final
hardening was reapplied to all 60 saved native positives and covered by fresh
pilot execution and regression tests. The original full-batch runner is retained
with its execution-time hash; no result is reassigned to a different source.

The process width/readout adapter also recognizes these three explicit public
models. It still authenticates the locked model file and internal transistor
wiring. Six actual simulations per host confirm matching operating-point
readouts between ordinary and per-finger views at the selected condition.

A 33.7 MB deduplicated archive retains 1.19 GB of logical source and evidence
files, including the failed attempts. Every object hash is verified. Restoring
2,353 source/physical-input files reproduces the three final pilot layouts and
all 24 fault controls using the local engines.

The original GF180 acceptance also retains its exact tested versions of the
two changed application modules through an additional historical source
snapshot. The current application does not inherit that older execution claim.

## Reproduction and limits

Use the locked physical adapter prepared by `prepare_sky130_qualification.py`
and the pinned native engines:

```sh
python scripts/qualify_sky130_threshold_layouts.py --sky130 /path/to/physical-adapter/sky130A --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout --output /path/to/new-results --workers 2
python tests/gui_sky130_thresholds.py --out /path/to/new-desktop-results
```

`--pilot` selects the three minimum-size cases and every fault control. The
physical CI workflow repeats that pilot; desktop CI repeats all six source
editor checks. A configuration change is not a successful hosted run.

Earlier failed attempts remain recorded: the first qualifier omitted imported
layer mapping, the second used SI instead of the native SKY130 micrometre
reference units, and the third did not recognize Netgen's explicit top-level
pin-mismatch result. Initial desktop tests incorrectly accessed a deleted dialog
and assumed regeneration always opens a parameter form. Those test-harness
failures are retained alongside the corrected passes. The acceptance limits and
public rule decks were not relaxed.

This closes the stated generator/recognition batch for six symbol views.
Continuous geometry and operating envelopes, all other physical device classes,
reliability/statistical/RF accuracy, complete chips and installed-release
acceptance remain separate. Three-terminal symbol views are not covered by this
four-terminal layout recipe. The seven unavailable real-device bindings remain
unavailable, all 286 available catalog entries remain `partial`, and chunk 7
remains in progress.
