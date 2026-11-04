# Editable parallel SKY130 resistors

The LI and metal1–metal4 resistor editor now accepts integer multiplicity from
1 through 16. Each unit retains the selected width and length. Separate straight
resistors connect to two buses on their own conductor layer; the generator does
not represent the array by enlarging one resistor marker.

Set the resistor's `mult` parameter, then use **Generate linked PDK device** to
review and apply the footprint. The existing W/L range is 0.5–10 µm on a 5 nm
grid. The two exposed terminals stay at the original first-unit positions when
multiplicity changes. Regeneration preserves their identities, attached wires
and the retained first-unit shapes; reducing the count removes obsolete units.
One-unit geometry and its saved specification remain unchanged.

The array uses a 3 µm gap between units and two 0.4 µm buses contained within
the original unmarked terminal landings. These are the editor's construction
choices, not process operating limits. Native DRC and extracted LVS are still
required after edits.

## Qualification contract and current state

The [versioned contract](qualification/sky130-metal-resistor-parallel-v1.json)
fixes the acceptance selection before native execution: 280 clean layouts,
25 native physical/reference fault controls and 30 extracted-array electrical
contexts, each with DC and complex AC. Clean layouts cover every count at
2 × 5 µm in both orientations, plus selected dimension boundaries at counts
2, 3 and 16. Save/reopen and independent GDS/OASIS round trips must preserve
the actual masks and terminals. Extraction must contain the separate physical
resistors, with their exact models, widths, lengths and parallel connections.

The source Qt workflow passes all five models through 3 → 16 → 2 → 1,
including review/apply, attached wires, undo/redo, save/reopen and late layer
locks. All 280 native layouts and 25 intended fault outcomes pass. All thirty
actual-array contexts pass DC and complex AC against both the application
reference and the analytical response: sixty native simulator runs. The
independent full audit verifies 3,870 path samples, with maximum normalized
error 7.51 × 10⁻⁸ against the unchanged limit of one. Source and tool identities
remain unchanged throughout execution. The [execution record](validation/sky130-metal-parallel-2026-10-26.json)
includes independent recovery of all 15,103 full-run files and a passing raw
audit from the restored evidence. The 86.1 MB archive retains the failed pilots,
actual source versions, native/electrical results and independent controls.
The [final combined source regression](validation/sky130-metal-parallel-source-feedback-2026-10-26.json)
passes all six stages on Windows and Linux, with 550 tests per host and matching
1,386 source identities. Full Linux discovery passes 3,725 tests with 61
skips. The ordinary-user Windows junction and temporary-reader-lock prerequisites
also pass. These results remain separate from installed-package acceptance.

Forty exact serialized comparisons against the earlier single-unit generator
also pass across all five models, four sizes and two placements. This checks
saved specifications and generated identities as well as polygon coordinates.
The first two failed native pilots remain retained: they exposed stream-label
presentation handling in the qualification fixture and interpretation of
Netgen's combined parallel-device property results. Neither repair changes the
construction, comparison tolerance or frozen acceptance selection.

Electrical checks use the application's actual exported circuit, the unchanged
native array extraction and an analytical parallel-resistance reference. They
use the existing comparison tolerances at the typical passive section and
27 °C. They do not replace an array with repeated calls to a single-unit
extraction. DC/AC is the frozen electrical scope; array transient, noise,
matching, calibrated statistics, full operating limits and installed delivery
remain separate requirements. No device or chunk status is promoted by this
implementation.

Use fresh output directories and the exact locked tools, sources and PDKs
identified by the contract:

```sh
python scripts/qualify_sky130_metal_resistor_parallel.py --help
python scripts/audit_sky130_metal_resistor_parallel.py --help
python tests/gui_sky130_metal_resistor_parallel.py --out /path/to/new-qt-evidence
```
