# Selected resistor layouts on GF180 and IHP

The [execution record](validation/resistor-layouts-2026-10-17.json) describes
190 selected layouts with zero full native DRC violations and matching strict
LVS. An independent readback also checks the exact extracted model, body,
terminals and dimensions. All 475 negative controls are detected: 285 physical
opens/shorts and 190 wrong-model/wrong-width schematic references.

| Process | Models | Sampled W/L pairs in micrometres | Passing layouts |
| --- | --- | --- | ---: |
| IHP SG13G2 | `rsil`, `rppd`, `rhigh` | 0.5/0.5, 0.5/20, 20/0.5, 2/7, 7/2 | 30 |
| GF180MCU C | Eight models below | 1/1, 1/20, 20/1, 2/7, 7/2 | 80 |
| GF180MCU D | Eight models below | 1/1, 1/20, 20/1, 2/7, 7/2 | 80 |

The GF180 models are `npolyf_s`, `npolyf_u`, `ppolyf_s`, `ppolyf_u`, `nplus_u`,
`pplus_u`, `ppolyf_u_1k` and `ppolyf_u_1k_6p0`. Each sample is a straight,
single resistor with two terminals and a separately contacted body guard ring.
Both 0- and 90-degree orientations pass. These are sampled points, not a claim
that every intervening geometry or the complete device operating envelope passes.

## Reproduce and open a layout

Use the current local Magic and Netgen executables with new output directories:

```sh
python scripts/qualify_ihp_resistor_layouts.py --output /new/ihp-results --magic /path/to/magic --netgen /path/to/netgen --workers 4
python scripts/qualify_gf180_resistor_layouts.py --output /new/gf-results --magic /path/to/magic --netgen /path/to/netgen --workers 4
```

`--pilot` selects the 2/7 sample. GF180 also accepts `--targets gf180mcuC` or
`gf180mcuD`. The commands create editable `saved.icproj` files, native geometry,
exported GDS/OASIS, independent schematic references and the complete physical
verification reports. Open a saved project in Studio to inspect or edit it.
Reverify after edits; the recorded pass applies only to the captured geometry.

Every case saves/reopens the project, exports OASIS, rewrites it with independent
KLayout, imports it without a Studio sidecar and exports GDS. Polygon XOR checks
preserve every mask. Full text presentation is compared with the original GDS;
native OASIS comparison checks electrical labels and anchors because that format
does not natively carry GDS text presentation. No masks are changed by port
assignment or exchange.

## Generator settings and retained failures

IHP uses its bundled public Magic generators with `vias=0`, leaving all three
terminals on Metal1. The original optional via stacks fail Metal2 minimum area
at the 0.5-micrometre widths. That failed run is retained. The Metal1-only run
repeats the entire matrix; unused via stacks are not waived or counted as passing.

GF180 uses the public open-pdks generator at the same pinned commit as the
bundled C/D rule decks. Original source files, the build recipe, startup grid,
license and checksums are retained under
[`icstudio/assets/physical/gf180_resistors`](../icstudio/assets/physical/gf180_resistors/README.md).
The unmodified generator produces contact enclosure/spacing failures in the
recorded pilot. The separately recorded local invocation adds 0.005 micrometres
to lower-layer enclosure, uses 0.11 micrometres of Metal1 enclosure on both
axes, 0.20 micrometres of well surround, 1 micrometre of guard clearance and
80% contact coverage. It retains the original 0.23-micrometre contact tile that
emits 0.22-micrometre cuts, a 5 nm grid and a fixed placement seed. The exact
C/D metal-option flags come from the upstream build recipe.

All intermediate failed experiments remain in the archive. The final geometry
uses the original DRC, extraction and LVS decks. The model equations, package
revisions and upstream generator files are unchanged. Six original source and
license files retain Apache-2.0; the qualification recipes are GPL-3.0 project
code. This work does not require private rules or a remote signoff service.

## Limits

This batch covers local physical geometry, ports, dimensions, exchange and fault
detection. Eighteen focused control/exchange tests pass on Windows and Linux.
Native Magic/Netgen execution is Linux/WSL; native Windows or installed-desktop
acceptance is not inferred. Electrical noise, statistics, RF behavior, continuous
operating ranges, other resistor families, antenna/density, complete-chip and
foundry qualification remain separate requirements. Chunk 7 remains in progress.
