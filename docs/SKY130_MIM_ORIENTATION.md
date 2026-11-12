# Rectangular SKY130 second-MiM extraction

The later [first-MiM correction](SKY130_FIRST_MIM_LAYOUT.md) extends the shared
adapter to the first plate and tests both families together. This guide's
original second-plate acceptance retains the exact sources recorded below.

The experimental application now supports rectangular metal4/cap2m/metal5 MiM
recipes within the existing 2–30 µm, 5 nm grid and 1–16 parallel-unit bounds.
The public Magic extractor reports width and length along the global coordinate
axes. Rotating a rectangle therefore swapped the model parameters, although the
physical capacitor was unchanged. This matters because the public model uses
`rm4 * lc / wc` for its bottom-plate series resistance.

The correction reads the written GDS, independently of schematic parameters,
labels and generator annotations. The pinned public `sky130::cap_device` draws W
toward the external bottom contact and L perpendicular to it. The application
uses that physical contact direction, matches each native device location and
size to exactly one electrode, and changes only the native W/L tokens where
necessary. Native connectivity, model selection and other parameters are retained.
A fresh Magic process exports the corrected records without extracting them again.

The source convention is bound to the existing public physical adapter:

| Input | SHA-256 |
| --- | --- |
| `sky130A.tech` | `5ee53b96094fe144145bf1216627672747366ec9bef9f2f848304a9a0c77427e` |
| `sky130A.tcl` | `48d2111c3246cbbed88bca5cf479dd8edc4ce4629d5241cca4102368765da69a` |

The [pinned public asset lock](../examples/sky130-reference-assets.json) identifies
the source release. No private rules or model package is used, and upstream files
and their notices are unchanged. This is original application integration under
the existing project license.

The correction rejects changed technology/PCell inputs, missing or ambiguous
bottom contacts, shared bottom electrodes, unsupported shapes or dimensions,
unrecognized native coordinate scales, hierarchical native extraction records,
missing/duplicate devices, and disagreement between native dimensions and masks.
The shared Magic entry point applies this guard to flat extraction routes.
Distributed RC involving these rectangles remains explicitly blocked until its
separate normalization interaction is qualified. Hierarchical designs can use the
ordinary layout-verification flow, which first creates a private flattened stream.
Direct hierarchical Magic workspace extraction is not covered by this adapter.

## Recorded checks

The [validation record](validation/sky130-mim-orientation-2026-10-23.json) binds
sources, engines, raw outputs, independent audits and archive identity.

- Eight selected sizes/counts pass 64 rotations and mirrors, translated away from
  the origin: 2×10, 10×2, 3.005×5.005, 2×30 and 30×2 µm; three and sixteen
  parallel 2×10 units; and a 2×2 square control.
- All 64 layouts pass native full DRC, strict native LVS and the pinned public
  KLayout DRC configuration. GDS/OASIS/reimport comparisons preserve geometry.
- All 47 physical/reference faults are detected. A missing bottom contact on a
  rectangle is rejected by the written-mask guard after successful native
  extraction; this is recorded separately from native LVS rejection.
- Linux and Windows each pass 24 electrical conditions with eight AC samples
  from 1 kHz through 10 GHz. Schematic, extracted and literal independent model
  calls agree in complex admittance and reconstructed series resistance. All 21
  asymmetric width/length controls are detected through series resistance.
- The independent audit reconstructs the expected orientation from bottom-metal
  extension, checks unchanged native connectivity, reads raw responses directly,
  and validates 1,200 integrity bindings. Four corruptions are rejected, including
  changed dimensions with recomputed checksums.
- Windows staging/receipt passes a mirrored, rotated three-unit design and two
  disconnected-contact controls. Both source desktops pass creation, review,
  undo/redo, square and rectangular regeneration, and save/reopen.

These are public-model equivalence checks. The high-frequency stimulus does not
establish measured RF accuracy. The earlier square-only acceptance remains
historical and unchanged. Full operating, reliability, statistical, arbitrary
layout and installed-release acceptance remain separate; this batch does not
complete chunk 7 or promote a partial device.

## Reproduction

With the pinned physical adapter and configured local engines, run:

```sh
python scripts/qualify_sky130_mim_orientation.py --sky130 /path/to/adapter \
  --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout \
  --ngspice /path/to/ngspice --output /path/to/new-evidence
python scripts/audit_sky130_mim_orientation.py --root /path/to/new-evidence \
  --output /path/to/new-evidence/audit.json
```

`--pilot` runs the first asymmetric case at 0° and 90°, one electrical condition
and all six faults. The complete audit intentionally requires the full eight-case
batch. CI now runs that full batch and audit, preserving the existing square and
mismatch checks.
