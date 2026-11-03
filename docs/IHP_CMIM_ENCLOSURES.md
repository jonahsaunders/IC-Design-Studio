# IHP CMIM enclosure observations

This finite source-mode experiment exercises complete 7 µm × 7 µm `cap_cmim` layouts at selected enclosure boundaries. It does not establish installed acceptance, electrical behavior, operating limits, or qualification of the device family. The layouts are imported physical constructions based on the pinned public sources, not a claim that the ordinary application generates these variants as a PCell.

The two unchanged public decks and the separately versioned supplemental metal-spacing check were run on each selected layout. An ordinary catalog capacitor supplied the captured simulation-format X reference; the application projected it to the physical C reference for strict LVS. The independent reader checks written GDS and OAS masks, extraction input, labels, raw capacitor geometry and ordered terminals, all three finding reports, and the reference projection.

| Main-deck rule and tested geometry | Rotations | Observed finding in main deck | Other decks | Strict LVS |
| --- | --- | --- | --- | --- |
| MIM.c: Metal5 enclosure 580 nm | 0°, 90° | one MIM.c | zero | pass |
| MIM.c: Metal5 enclosure 600 or 620 nm | 0°, 90° | zero | zero | pass |
| MIM.d: TopVia1 enclosure 340 nm | 0°, 90° | one MIM.d | zero | pass |
| MIM.d: TopVia1 enclosure 360 or 380 nm | 0°, 90° | zero | zero | pass |

The MIM.c variants preserve the original array of 25 Vmim cuts on layer 129/0. The MIM.d variants replace that array with one 420 nm TopVia1 cut on layer 125/0 and hold the TopMetal1 edge fixed, so the test separates the selected enclosure from the other contact checks. The pinned main-deck MIM.d rule uses TopVia1, not Vmim: these results do not establish a Vmim enclosure threshold. Magic can canonicalize the alternate contact during stream conversion, so the evidence for the 125/0 mask comes from the unchanged public KLayout route, not a Magic round trip.

Six separately audited controls test missing Vmim, missing TopVia1, a contact on the wrong layer, a cross-plate short, an incorrect reference width, and swapped electrodes. The first four complete unfiltered extraction and are stopped by the application's specific port guard; LVS is not run for them. The wrong-width and swapped-electrode controls reach strict LVS and fail on actual property and pin mismatches respectively. Raw findings, including additional findings for the wrong-layer and short controls, are retained rather than hidden.

The reusable source-mode runner is [qualify_ihp_cmim_enclosures.py](../scripts/qualify_ihp_cmim_enclosures.py); its full selection is checked independently by [check_ihp_cmim_enclosures.py](../scripts/check_ihp_cmim_enclosures.py). `--pilot` explicitly selects only one legal TopVia1 case and cannot satisfy the full reader. Run the producer with explicit paths to the existing Magic, Netgen and KLayout executables and a new output directory; pass that directory to the reader. The command requires the pinned public PDK sources, Python KLayout bindings (reviewed version 0.30.5), and Magic 8.3.617 or newer as required by the pinned technology. The reviewed native run used Magic 8.3.684, Netgen 1.5.300 and KLayout 0.30.5. Use a fresh output directory outside the checkout and explicit tool paths with no symbolic-link or junction components. The producer binds its selected launcher bytes and source contract, but does not by itself claim a complete runtime identity.

The producer was exercised on native Linux; the full independent reader passed
on Linux and Windows. A full run can be reproduced from the repository root:

```text
python scripts/qualify_ihp_cmim_enclosures.py --output /absolute/new-output --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout
python scripts/check_ihp_cmim_enclosures.py /absolute/new-output
```

The [validation record](validation/ihp-cmim-enclosures-2026-11-03.json) identifies the retained raw evidence, source recovery chain, independent reviews and replay results. See [IHP_CMIM_REQUIREMENTS.md](IHP_CMIM_REQUIREMENTS.md) for the remaining requirements.
