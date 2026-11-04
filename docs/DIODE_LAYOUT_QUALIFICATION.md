# Selected IHP and GF180 diode layouts

The [execution record](validation/diode-layouts-2026-10-17.json) records 100
sampled layouts with zero full native DRC violations, matching strict LVS and
independent readback of polarity, model and exact dimensions. All 300 negative
controls are detected: 150 physical opens/shorts and 150 reversed-polarity,
wrong-width and wrong-model schematic references. These are local device checks;
chunk 7 remains in progress.

| Process | Models | Passing layouts |
| --- | --- | ---: |
| IHP SG13G2 | `dantenna`, `dpantenna` | 20 |
| GF180MCU C | `diode_nd2ps_03v3`, `diode_pd2nw_03v3`, `diode_nd2ps_06v0`, `diode_pd2nw_06v0` | 40 |
| GF180MCU D | Same four junction families | 40 |

Each family uses W/L pairs 0.45/0.45, 0.45/20, 20/0.45, 2/7 and 7/2 micrometres,
with 0- and 90-degree rotations. Every device has one central junction conductor
and a separate contacted guard ring. Anode/cathode assignment follows junction
doping: the centre is the cathode for an n-diode and the anode for a p-diode.
The reference is created independently of the extracted netlist.

## Reproduce

```sh
python scripts/qualify_diode_layouts.py --output /new/diode-results --magic /path/to/magic --netgen /path/to/netgen --workers 4
```

Use `--pilot` for the 2/7 sample, or `--targets ihp-sg13g2`, `gf180mcuC` or
`gf180mcuD` to select a profile. Each case produces an editable `saved.icproj`,
original generator script/GDS, independent reference and native verification
reports. Save/reopen, GDS/OASIS export, independent KLayout rewrite and import
without a Studio sidecar preserve every mask and electrical label. GDS text
presentation is checked against the original GDS; native OASIS does not carry
that presentation and is compared for geometry, strings and anchors.

## Extraction correction

Magic 8.3.684's flat SPICE writer emits device perimeter with a factor of
`1e-12` instead of `1e-6`. A 2 by 7 micrometre GF180 diode therefore produced
`pj=18p` instead of `pj=18u`. The pinned Netgen setup ignores `pj`, so ordinary
LVS alone missed this. The independent dimensional audit rejected it.

The layout-only verification flow now uses Magic's hierarchical writer on its
already flattened private input. The native writer produces the correct value;
no extracted numbers, PDK decks or model equations are rewritten. The original
application project and hierarchy remain intact. The affected upstream code is
in [the flat writer](https://github.com/RTimothyEdwards/magic/blob/master/ext2spice/ext2spice.c)
and [the hierarchical writer](https://github.com/RTimothyEdwards/magic/blob/master/ext2spice/ext2hier.c).
The retained local native run establishes behavior for the actual runtime.
Other extraction profiles already use the hierarchical writer by default.

The earlier GF180 production-gate source is preserved in a separate historical
snapshot. Its acceptance is not reassigned to the modified application. Fresh
checks cover 14 representative MOS, resistor and MIM layouts across all four
profiles after this change. The 29 focused regressions pass on Windows and Linux.

## Generator settings

IHP uses its pinned public generator, `vias=0`, and the 5 nm grid documented in
its `.magicrc`. The former 10 nm grid rounded 0.45 micrometre dimensions to 0.46;
that failed run is retained. Both public diode equations depend on area and
perimeter, so rotation preserves electrical geometry. The independent physical
reference swaps W/L at 90 degrees to match their x/y extraction convention.

GF180 uses the Apache-2.0 [pinned open-pdks source](../icstudio/assets/physical/gf180_resistors/README.md).
The named local invocation sets 0.50 micrometres of junction-to-guard spacing,
0.075 micrometres of guard diffusion enclosure, 0.11 micrometres of metal
enclosure, a 0.25 micrometre guard contact tile and 80% contact coverage. The
optional outer guard is off; the contacted junction guard remains. It uses the
upstream 5 nm startup grid and a fixed seed. Original and intermediate failing
contact-enclosure variants are retained. Final DRC, extraction and LVS use
unchanged public decks.

## Limits

This batch does not qualify other diode families, ESD/breakdown ratings,
continuous geometry or bias ranges, noise/statistics, RF, complete-chip
antenna/density, or fabrication. Native execution is Linux/WSL; native Windows
and installed-desktop acceptance remain separate. Other device families and
required unavailable models still prevent completion of chunk 7.
