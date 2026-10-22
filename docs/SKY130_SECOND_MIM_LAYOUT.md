# SKY130 second-plate MiM layout

The editor can generate a bounded square layout for `cap_mim_m3_2`, using
metal4, cap2m and metal5. The capacitor has distinct top (`c0`) and bottom
(`c1`) electrodes, 800 nm via4 cuts, and connected physical parallel copies.
The original layout batch preserves its exact catalog and model revision.
The later [multiplicity correction](SKY130_MIM_MULTIPLICITY.md) changes the
default parameter mapping in a new revision while preserving saved projects.

The recipe accepts equal W/L from 2 to 30 µm on the 5 nm grid, with integer
parallel multiplicity from 1 to 16. These are implementation bounds, not a
claim that every size/count combination has been qualified. The upstream
electrical default of 1 µm remains unchanged; choose supported dimensions
before generating this physical recipe.

The [execution record](validation/sky130-mim2-layouts-2026-10-22.json) records:

| Check | Verified result |
| --- | --- |
| Full native Magic DRC, strict Netgen LVS and public KLayout block DRC | 28 layouts pass: seven configurations, four rotations |
| Missing dielectric, open top/bottom contacts, wrong reference width/count | All 35 controls detected |
| Schematic/extracted/independent capacitance at 1 kHz | 21 comparisons pass at nominal/27 C, ss/0 C and ff/85 C |
| Independent raw-file, native-netlist and mask audits | Both hosts verify 96 physical capacitor instances, 56 stream comparisons and 504 integrity bindings |
| Source tests and editor | 32 distinct targeted tests per host; generation/review, undo/redo, resizing and save/reopen pass |
| Windows staging and local native verification | Valid three-copy layout passes; disconnected top contact fails as intended; 48 returned files verified |

The seven missing-dielectric controls collapse the two native ports into one.
They correctly stop at the extracted-interface check; their later LVS and
integrity stages are explicitly unrun. The independent audit re-reads those
shorts and the missing masks. They are not counted as successful LVS runs.

The first prototype's standalone metal5 landing failed the minimum-area rule.
It now uses a 2 × 2 µm landing. The original failure is retained. Source rules
and layer identities come from the existing pinned physical adapter's
`sky130A.tech` and `sky130A.tcl`; upstream licenses and asset bytes are retained.

## Rectangular rotation remains unresolved

The attempted 2 × 10, 10 × 2 and 3.005 × 5.005 µm rectangles pass at zero
degrees, then fail strict dimension comparison at 90 degrees: the native
extractor exchanges W and L. The public model's series resistance depends on
L/W, so dimension interchange cannot simply be waived. The new recipe rejects
rectangles before changing the design. The failed layouts, raw native output
and property-error reports remain in the evidence archive.

This limitation also prevents claiming complete second-MiM geometry coverage.
No extracted dimensions, comparison tolerances or upstream rules were rewritten.
The original source symbol emits `VM=MF`, while the public model declares `mf`.
The later [multiplicity batch](SKY130_MIM_MULTIPLICITY.md) corrects that mapping
and verifies selected native mismatch scaling. The original deterministic
layout checks retain their historical scope; full statistical qualification
remains separate.

## Reproduce

Use the adapter prepared by `prepare_sky130_qualification.py` and local engines:

```sh
python scripts/qualify_sky130_mim2.py --sky130 /path/to/adapter --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout --ngspice /path/to/ngspice --output /path/to/new-results
python scripts/audit_sky130_mim2.py --root /path/to/new-results --output /path/to/audit.json
python tests/gui_sky130_mim2.py --out /path/to/new-editor-results
```

`--pilot` runs the 2 µm square, one electrical condition and five faults. CI
includes that pilot and the source editor workflow. Configuring CI does not
establish a completed hosted or installed-release result.

This batch adds usable physical support within the stated bounds. Complete
operating/statistical ranges, rectangular geometry, other device families,
seven unavailable required bindings and final installed acceptance remain open.
Chunk 7 and complete-chip tapeout qualification remain incomplete.
