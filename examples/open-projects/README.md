# External open-design references

This directory stores source locks and bounded compatibility contracts. It does
not bundle the third-party design repositories or a ready-made detector project.

## SKY130 voltage monitor

The programmable overvoltage detector comes from
[LDFranck/sky130_vbl_ip__overvoltage](https://github.com/LDFranck/sky130_vbl_ip__overvoltage)
at the Apache-2.0 revision pinned in [`overvoltage-lock.json`](overvoltage-lock.json).
Follow the [import and qualification walkthrough](../../docs/OPEN_PROJECTS.md)
to fetch that source, prepare its locked physical technology and run
`scripts/qualify_open_project.py`.

The output provides two native projects:

| Project | Purpose |
| --- | --- |
| `overvoltage.icproj` | Inspect the imported DUT schematic and layout in **Linked views**. Its external ports need a fixture before simulation. |
| `overvoltage-bench.icproj` | Run the complete detector fixture. Select `detector_dc_bench`, retain **DC startup → Use first-point voltage guesses**, and press **F5**. |

In the bench, set `Vbit0`–`Vbit3` to 0 or 1.8 V for codes 0–15, then inspect
`ovout`. The recorded nominal rising 3–6 V sweep produced trip thresholds
from **3.30 V at code 0 to 5.46 V at code 15**, with TT models, 27 °C,
DVDD 1.8 V, VBG 1.2 V, 600 nA bias and a 1 MΩ load. Those conditions do not
establish falling hysteresis, full PVT or extracted-RC performance.

Strict native-source LVS and the later supported exchange routes have separate
evidence. Read the [reference compatibility matrix](../../docs/REFERENCE_COMPATIBILITY.md)
for fresh DRC/LVS routes, deliberate defects, the raw hierarchical Magic-stream
failure and the explicitly recorded resistor-extraction correction. Generate
the project on a host with the required Linux tools, then open its portable
`.icproj` in the Windows or Linux desktop.

## Other public designs

[`public-layouts-lock.json`](public-layouts-lock.json) pins independently authored
inverter, comparator, common-mode generator and amplifier references. The
[public-design qualification guide](../../docs/PUBLIC_DESIGN_COMPATIBILITY.md)
lists the exact expected passes and intentional failures and reproduces their
DRC/LVS checks. Passing that regression means defects were detected where
expected; it does not mean every imported design is clean.

For bandgap examples, use the [supplied GF180 5 V simulation](../gf180-bandgap/README.md)
or the separate [native Banba design sequence](../gf180-banba/README.md).
