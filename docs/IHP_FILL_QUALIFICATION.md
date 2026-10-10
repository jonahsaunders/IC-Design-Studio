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
35,226 for UART and 35,177 for APB. A first quasistatic floating-fill reduction
passes extracted setup/hold, annotation and electrical checks at all three
captured library conditions, using the original netlists and constraints.
These are preliminary typical-interconnect results; independent finite-RC and
active-fill parasitic coverage have not yet been accepted.

| Reference | Lowest post-fill setup slack (ns) | Lowest post-fill hold slack (ns) |
|---|---:|---:|
| Counter | 47.845844 | 0.097172 |
| UART | 4.017923 | 0.184612 |
| APB | 15.429800 | 0.010337 |

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

## Remaining chunk 5 work

- Complete independent extraction-model and active-fill parasitic coverage checks.
- Accept post-fill timing and electrical limits for all three references under
  the original constraints and captured library conditions.
- Reconcile supplemental manual-rule coverage with the native deck.
- Integrate the accepted recipe into the production flow, bind final export
  evidence, and rerun affected production and package tests.

None of these results establishes full IHP, bipolar/RF or tapeout qualification.
