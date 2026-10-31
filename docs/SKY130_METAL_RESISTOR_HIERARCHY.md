# Repeated SKY130 resistor cells

The October 26 source integration milestone verifies that importing, saving,
reopening and exchanging a layout preserves two independent resistors sharing
one child cell. It covers LI and M1–M4 using one 2 × 5 µm straight child per
model. The second instance is rotated 90°, mirrored and translated 40 µm;
the complete pair is checked at 0° and 90°.

The ten clean layouts retain exactly two cells, two child references and four
distinct top-level terminals, A1/B1/A2/B2. GDS and OASIS readback checks the
actual transforms and written mask polygons. Native verification flattens its
private copy, removes child-local labels and preserves all masks and top-level
ports. Every clean layout passes full native DRC and strict LVS with exactly
two correct model instances, W = 2 µm and L = 5 µm, on independent nets.

Twenty native fault controls detect a merged reference terminal, a missing
reference instance, an incorrect width on only the second resistor and an
actual conductor joining the two A terminals. Twenty-five modified stream
files also detect lost instances, mirrors, rotations, terminal names or masks.
The independent checker reads original artifacts without importing the
producer or regenerating a positive extraction. Twelve rehashed evidence
corruptions are rejected.

The initial physical bridge clipped a marker and was correctly rejected for
changing the extracted dimensions. Its repaired path avoids both resistor
bodies; the failed attempt remains retained. A subsequent checker-only repair
recognizes two observed Netgen width-fault conclusions, while still requiring
the exact selected model, width mismatch and property-error context. Generic
pin-matching failures do not count as width-fault evidence. Five actual logs
pass and fifteen invalid log edits are rejected. The later checker has its own
identity; original executed sources and native results remain unchanged.

The compact 8.14 MB archive contains 3,862 logical files through 1,606 distinct
objects. Complete readback and independent checking of 1,743 restored full-run
files pass without rerunning Magic or Netgen. The separate physical adapter
remains locked to its original revision and retained dependency archive.

This closes the selected imported repeated-cell connectivity and exchange
gap. It does not qualify parameterized arrays, snakes, new contact/via classes,
electrical hierarchy response, full device limits or installed delivery. The
existing straight-resistor editor and electrical contracts retain their own
scope. The separate [parallel-array milestone](SKY130_METAL_RESISTOR_PARALLEL.md)
covers the newly supported bounded array construction. All device statuses and
the chunk-7 completion gate remain unchanged.

See the [execution record](validation/sky130-metal-hierarchy-2026-10-26.json).
For reproduction, use fresh output directories and the exact locked physical
adapter recorded there:

```sh
python scripts/qualify_sky130_metal_resistor_hierarchy.py --help
python scripts/audit_sky130_metal_resistor_hierarchy.py --help
```
