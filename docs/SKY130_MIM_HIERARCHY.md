# Imported repeated-cell SKY130 MiM layouts

The [October 26 source milestone](validation/sky130-mim-hierarchy-2026-10-26.json)
verifies a selected repeated-cell class for both `cap_mim_m3_1` and
`cap_mim_m3_2`. Each layout reuses one existing 2 × 10 µm capacitor leaf twice,
with independent P1/N1/P2/N2 terminals. The second occurrence is rotated,
mirrored and translated 40 µm; the complete pair is tested at 0° and 90°.

Application import, save/reopen, GDS, OASIS and reimport preserve exactly two
cells, two child occurrences, all written masks and the ordered terminal
anchors. Native verification flattens only its private stream. All four clean
layouts pass full native DRC and strict LVS with exactly two correct unit
capacitors, their dimensions and four independent connections. Original EXT
files are retained; the checker derives electrode orientation independently
and verifies that normalization changes only the required W/L tokens.

Eight fresh native controls detect a merged reference terminal, missing
reference device, wrong second-device width and deleted physical occurrence.
Ten stream controls detect lost occurrences, mirrors, rotations, labels or
masks. Fourteen distinct rehashed evidence mutations are rejected; twelve
were also exercised on the initial one-model pilot. The separate checker
uses literal mask expectations and actual original extraction files.

Both 601-test source-feedback lanes and all six stages pass. The 19.92 MB
archive retains 2,969 logical files through 1,761 unique objects. Restoring
all 1,264 full-run files at their original paths reproduces the unchanged
independent audit. Original pilot checker failures remain retained separately;
the full selection uses the final captured checker and source identities.

Shared producer mask helpers now live in `scripts/qualification_geometry.py`.
Their function syntax trees match the previous definitions, the resistor
runner re-exports its existing names, and affected regression tests pass.
The independent reader retains a separate geometry implementation.

This closes the predefined imported repeated-cell connectivity and exchange
example under [the versioned contract](qualification/sky130-mim-hierarchy-v1.json).
It does not establish direct hierarchical Magic extraction, distributed RC,
other sizes or physical classes, complete operating limits, calibrated
statistics/reliability, or a new installed workflow. Existing
[MiM requirements and installed acceptance](SKY130_MIM_REQUIREMENTS.md) keep
their original boundaries; no device status or completion gate is promoted.

Reproduce with a fresh output directory and the recorded physical adapter:

```text
python scripts/qualify_sky130_mim_hierarchy.py --sky130 LOCKED_ADAPTER --magic MAGIC --netgen NETGEN --output NEW_EVIDENCE
python scripts/audit_sky130_mim_hierarchy.py --root NEW_EVIDENCE --reviewed-source REVIEWED_SOURCE
```
