# IHP fill qualification checkpoint

Chunk 5 remains in progress. The counter, UART and APB references have zero
findings from the pinned maximal native geometry deck after fill. Their original
mask geometry and 200/400 µm footprints are unchanged. The repository generator
reproduces the exact checked GDS bytes. This is experimental qualification work;
the desktop production flow does not yet use this recipe.

The [checkpoint](validation/ihp-fill-checkpoint-2026-10-10.json) binds the inputs,
native reports, source files, fault controls and retained evidence archive.
The [source lock](../examples/ihp-fill-source-lock.json) identifies the upstream
macros and rule deck. Every native rule group stays enabled. Unimplemented manual
rules and complete-chip seal/scribe rules still need coverage review.

## Fill and circuit preservation

The fill recipe uses the original block footprint as its scope, with the upstream
active and metal exclusions. Ordinary metal spacing uses the upstream adjustable
1.5 µm setting. Existing circuit poly already exceeds the pinned 15% minimum;
the recipe adds no poly gates. The earlier combined active/poly pattern created
492/1,032/1,032 extra floating MOS devices and was rejected by the connectivity
checks, despite its zero geometry findings. Those failed attempts are retained.

Before and after fill, native four-terminal device comparisons cover all standard
cells, physical decoupling cells and boundary ports. Parallel fingers are combined
using the native option; general simplification and device/circuit purging remain
disabled. The native floating-net option removes unconnected wire nets. It cannot
replace the mandatory independent port audit described below.

The upstream SPICE reader strips brackets from element connections but leaves them
in subcircuit headers. That can disconnect bus ports and still produce a native
graph match. The reference adapter now verifies every exported cell terminal
against OpenDB, then creates a reversible, collision-free naming map. It also
captures boundary net aliases and individual intentionally unconnected terminals.
A comparison-only GDS copy receives matching port labels; every physical mask is
verified unchanged. The original deliverable retains its original labels.

Every graph-paired port must retain its identity and every expected port must be
present. Real short, clock-pin-open, swapped-output and wrong-PMOS-body controls
are rejected. The clock-open and swapped-output examples demonstrate why the
native “match” message alone is insufficient. Windows and Linux reproduce the
same six valid comparison audits and four rejected controls.

Native OpenRCX represents every added metal rectangle: 8,951 for counter,
35,226 for UART and 35,177 for APB. The later
[coupling-model checkpoint](validation/ihp-coupling-model-2026-10-10.json)
supersedes the first checkpoint's electrical-model results. Positive controls
found that the original ORFS model reports zero nearby floating-metal coupling
on Metal1–Metal5. Its preliminary timing passes cannot establish fill acceptance.

The official nominal Magic-derived OpenRCX model from the same pinned IHP release
passes nearby/absent/far controls on all seven metals. Its
[source lock](../examples/ihp-fill-rcx-source-lock.json) retains all four vendor
candidates; only the nominal replacement has been exercised here. The new
qualification guard rejects the original model's failed controls.

The replacement produces observable signal/fill coupling in all three blocks.
Some connected floating components exceed the existing 256-node dense-solver
budget. The experimental sparse solver checks its residual, symmetry and
passivity and rejects components beyond its fixed 1,024-node bound. An independent
NumPy calculation checks the exported capacitance matrix and the full two-node
fill resistance model at 25 frequencies from 100 kHz to 50 GHz. Maximum errors
relative to the added admittance matrix are 7.57e-6, 3.67e-6 and 4.88e-6, below
the predetermined 1e-4 tolerance. Deliberately enlarged fill resistance fails
that tolerance in all three cases. This validates the captured matrix and sampled
band; it does not calibrate the extraction field model or fill widths.

Matched before/after timing passes setup, hold, annotation and electrical checks
at all three captured library conditions under the original constraints. Nine
deliberately added 1,000 pF output-load faults fail setup. These results use one
nominal interconnect model, not three qualified interconnect corners.

| Reference | Lowest post-fill setup slack (ns) | Lowest post-fill hold slack (ns) |
|---|---:|---:|
| Counter | 47.717495 | 0.111594 |
| UART | 2.944024 | 0.197290 |
| APB | 14.405060 | 0.064350 |

Active-fill parasitics remain an explicit coverage gap. A native Magic control
imports and round-trips the full 3.4 µm square on purpose 22 but produces exactly
the absent-fill capacitance. An otherwise identical ordinary-active control
produces a new node and 527.932 aF mutual capacitance. Source inspection confirms
that the fill type is outside the deck's ordinary diffusion-capacitance aliases.
The absent active-fill response is therefore not evidence of zero physical
effect. It must be resolved before chunk 5 closure.

## Reproduce the geometry stage

Obtain the exact three macro files listed in the source lock and the pinned
maximal deck. With KLayout 0.30.5 and its Python package installed:

```text
python scripts/prepare_ihp_block_fill.py --gds original.gds --top counter --die-nm 0 0 200000 200000 --macros pinned-macros --deck sg13g2_maximal.lydrc --executable /path/to/klayout --output new-evidence-directory
```

The directory must be new. The command rejects changed sources, a resized die,
existing fill, unsupported chip boundaries and insufficient existing poly density.
A successful exit establishes only this native geometry result.

Use `scripts/ihp_lvs_reference.py` to prepare a reference from the captured
OpenROAD CDL, standard-cell masters and `digital_lvs_engine.py` checkpoint export.
Keep its `aliases.json` with the native comparison inputs. After running the
pinned native LVS deck with the captured options, audit the comparison:

```text
python scripts/check_ihp_lvs.py report.lvsdb --aliases aliases.json --output audit.json
```

## Reproduce the electrical model stage

On the retained native control capture, run `scripts/check_ihp_fill_coupling.py`
with the capture directory and `--output audit.json`. It exits unsuccessfully
when any metal lacks its nearby response or a far/absent control differs.
Successful controls establish response coverage, not field accuracy.

For a captured, explicitly represented floating-metal extraction:

```text
python scripts/ihp_fill_spef.py --source parasitics.spef --represented represented.json --output new-model-directory
```

This exports `timing.spef` and `reduction.json`, preserving the extracted signal
terminals and resistances. Independent model checks, native timing and coverage
review remain mandatory. The experimental scripts do not yet change desktop
production behavior.

## Remaining chunk 5 work

- Resolve active-fill parasitic coverage and review the model's fill-width scope.
- Bind the final accepted full-fill model to timing and electrical acceptance.
- Reconcile supplemental manual-rule coverage with the native deck.
- Integrate the accepted recipe into the production flow, bind final export
  evidence, and rerun affected production and package tests.

None of these results establishes full IHP, bipolar/RF or tapeout qualification.
