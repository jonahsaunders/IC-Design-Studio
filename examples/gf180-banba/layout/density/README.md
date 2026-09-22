# Density-filled Banba candidate

[`banba-density.gds`](banba-density.gds) closes the original 314 density findings by adding real dummy COMP, poly and M1–M4 around the circuit. The footprint expands from **0.4827 to 3.6250 mm² (7.51×)**. Device placement, routing, recognition masks and circuit dimensions are unchanged, as checked by a layer-by-layer geometric XOR and strict LVS. This is a physical finishing output; continue editing the original `../banba-layout.icproj`, regenerate its core GDS, and rerun fill after edits. Do not import more than a million fill tiles into the native flattened editor.

The new **2052.1 × 1766.5 µm** boundary includes a 600 µm collar on all sides of the original envelope. Layer 63/0 explicitly defines that rectangle, including the empty 30 µm edge margin. This full area is the density denominator. Fill also occupies eligible gaps in the original envelope. No density threshold is lowered and no marker is waived.

## Results and deck correction

KLayout 0.28.16, the pinned upstream GF180 verification commit `05e7b6adf19edf942969c1c9625f02fd87874f06`, and variant B give:

| Check | Result |
| --- | --- |
| Geometry/off-grid DRC | 0 findings |
| Density, with the mask-accounting correction below | 0 findings |
| Antenna | 0 findings |
| Strict LVS | 103 devices, 56 nets, 3 pins matched |
| Original circuit masks | XOR is empty on every original mask |
| Independent fill geometry checks | Tile dimensions, grid, minimum spacing, keepouts and poly/COMP enclosure pass |

The upstream density deck reads poly only from **30/0**, although dummy poly is **30/4**. Metals already include their dummy datatype. `--include-dummy-poly` stages a separate copy of the pinned deck and changes exactly one declaration:

```diff
-poly2 = get_polygons(30, 0)
+poly2 = get_polygons(30, 0) + get_polygons(30, 4)
```

The PL.8 limit remains 14% and the entire boundary remains the denominator. The original checkout is untouched; original and corrected deck hashes are recorded in [`physical-verification.json`](physical-verification.json). The **unmodified upstream deck still reports 64 PL.8 markers** on the filled layout. The zero-density result is conditional on this explicit input-layer correction, not a claim that the unmodified deck passes or that the foundry approved the correction.

An independent KLayout region-area calculation on the written GDS gives:

| Physical mask, drawing + dummy | Coverage | Checked density limit |
| --- | ---: | ---: |
| COMP | 30.938% | 25–70% |
| Poly2 | 38.897% | ≥14% |
| M1 | 31.050% | ≥30% |
| M2 | 31.090% | ≥30% |
| M3 | 38.144% | ≥30% |
| M4 | 37.936% | ≥30% |

Fault injection exercises the actual density deck: removing dummy poly restores PL.8=64; removing M2 fill restores M2.4=102; the unfilled core still has PL.8=64, M1.4=148 and M2.4=102 even with corrected poly accounting. See [`negative-controls/summary.json`](negative-controls/summary.json).

## Fill construction

The generator follows the published [dummy COMP](https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_13_1.html), [dummy poly](https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_13_2.html) and [dummy metal](https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_13_3.html) patterns:

- COMP: 5 × 5 µm; enclosing poly: 5.6 × 5.6 µm. Both use 8 µm nominal pitch and a 1.6 µm stagger on both axes.
- M1–M4: 2 × 2 µm, 3.2 µm nominal pitch, 0.5 µm stagger on both axes; consecutive layers shift by 0.5 µm on both axes. No contacts or vias connect the fill.
- A conservative 20 µm keepout surrounds all original circuit shapes on all layers. Process exclusions, including MIM FuseTop, resistor recognition and dummy-exclusion markers, receive 30 µm. Adjacent-layer circuit keepouts apply to drawn circuit material; the dummy arrays retain the specified relative offsets.
- Only complete tiles are inserted, on the 5 nm grid. Compact hierarchy arrays keep the GDS about 1.2 MB. The saved geometry checks also verify minimum diagonal separations and 0.3 µm poly enclosure of each dummy COMP tile.

[`fill-validation.json`](fill-validation.json) records actual tile counts, area, input/output/generator hashes, writer version and the fill policy. This conservative collar is intentionally large; it is a workable candidate, not a minimum-area floorplan. Pad ring, scribe structures and chip integration still require their own checks.

## Extraction limits

Magic 8.3.684 reads the filled GDS and preserves the checked 103-device/terminal/dimension bijection. Its extracted circuit has the same 175 parasitic capacitors, summing to 2.366 pF. All **20 operating-point and 60 startup** cases pass the existing limits with ngspice 42, the pinned models and a 5 pF load. See [`capacitance-check.json`](capacitance-check.json) and [`simulation.json`](simulation.json).

**The pinned Magic technology does not extract dummy-fill capacitance.** Its fill-only `.ext` cells contain only substrate records; the archived files make this limitation visible. These runs check that circuit extraction and the existing electrical screening survive the finishing operation. They do **not** qualify fill coupling. A fill-aware parasitic extractor and the previously blocked distributed-RC flow are still needed for electrical signoff. `signoff` remains false.

## Reproduction

From the repository root, with normal dependencies plus `docopt` and `jinja2`, a clean checkout of the pinned GF180 PV commit, and KLayout 0.28.16:

```sh
python scripts/fill_gf180_banba.py --out /new/filled
python scripts/verify_gf180_banba_physical.py --drc-lvs-only \
  --gds /new/filled/banba-density.gds --include-dummy-poly \
  --pv /path/to/globalfoundries-pdk-libs-gf180mcu_fd_pv \
  --klayout /path/to/klayout --out /new/filled-checks
python -m unittest tests.test_gf180_banba_fill tests.test_gf180_banba_physical \
  tests.test_gf180_banba_layout -v
```

The first command uses KLayout's Python module (archived output: 0.30.5). The verification command returns 0 only if all three DRC reports and strict LVS pass. Omitting `--include-dummy-poly` reproduces the pinned deck's PL.8 findings. The default verifier without `--gds` still checks the unfilled core.

To attempt the full extraction flow, omit `--drc-lvs-only` and provide the `--open-pdks`, `--magic` and `--ngspice` paths documented in the parent README. Full verification deliberately remains nonzero pending RC qualification. The archived C-only rerun executed the same capacitance and simulation phases; it did not retry the already blocked RC phase.

The archive includes all three DRC reports, strict LVS database (gzip), schematic/reference netlists, extraction logs/netlist, electrical summary and density negative controls. [`manifest.json`](manifest.json) records their hashes. Decompress `comparison.lvsdb.gz` before opening it in KLayout. Raw transient waveforms and intermediate flattened extraction geometry are reproducible outputs and are not bundled here.
