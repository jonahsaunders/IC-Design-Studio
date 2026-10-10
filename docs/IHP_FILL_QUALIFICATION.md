# IHP fill qualification checkpoint

Chunk 5 remains in progress. The counter, UART and APB references have zero
findings from the pinned maximal native geometry deck after fill. Their original
mask geometry and 200/400 µm footprints are unchanged. The repository generator
reproduces the exact checked GDS bytes. This is experimental qualification work;
the desktop production flow does not yet use this recipe.

The [checkpoint](validation/ihp-fill-checkpoint-2026-10-10.json) binds the inputs,
native reports, source files, fault controls and retained evidence archive.
The [source lock](../examples/ihp-fill-source-lock.json) identifies the upstream
macros and rule deck. Every native rule group stays enabled. The supplemental
manual-rule checks now cover the original block scope. Complete-chip seal/scribe
rules and full 800 µm windows remain outside these 200/400 µm references.

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

The captured before/after timing runs pass setup, hold, annotation and electrical checks
at all three captured library conditions under the original constraints. Nine
deliberately added 1,000 pF output-load faults fail setup. These results use one
nominal interconnect model, not three qualified interconnect corners.

**These timing runs do not establish final fill acceptance.** Subsequent native
width coupons show that the nominal tables return the same resistance and
capacitance for minimum-width and wider rectangles of equal length and spacing.
The rules have only one populated width point per table; the extractor clamps
its lookup to that point. Some other extraction branches use physical area, so
this is not a claim that every width-dependent term is absent. The affected
tables do not cover the actual 1/3.5/5 µm fill widths. The geometry, LVS and
algebraic reduction checks retain their stated scope; the following slack values
are historical results from this incomplete model.

| Reference | Lowest post-fill setup slack (ns) | Lowest post-fill hold slack (ns) |
|---|---:|---:|
| Counter | 47.717495 | 0.111594 |
| UART | 2.944024 | 0.197290 |
| APB | 14.405060 | 0.064350 |

The original active-fill extraction has an explicit coverage gap. A native Magic control
imports and round-trips the full 3.4 µm square on purpose 22 but produces exactly
the absent-fill capacitance. An otherwise identical ordinary-active control
produces a new node and 527.932 aF mutual capacitance. Source inspection confirms
that the fill type is outside the deck's ordinary diffusion-capacitance aliases.
The absent active-fill response is therefore not evidence of zero physical
effect. The explicit electrical view and junction model below address this
missing response; complete performance acceptance and production integration
remain necessary before chunk 5 closure.

## Supplemental rules and full-fill capacitance

The [active-fill source lock](../examples/ihp-active-fill-source-lock.json) captures
the authoritative Rev. 0.4 layout-rule PDF, Magic technology files and native
ngspice models at the same IHP revision. The PDF supplies the supplemental
AFil.c/d/i/j and GFil.e limits. The checker also verifies fill exclusions and
rejects seal geometry and both current and historical boundary mappings. Rules
with no relevant geometry are recorded as not applicable. The native maximal
deck remains mandatory.

`ihp_fill_capacitance_input.py` creates a separate electrical extraction view.
It maps each rectangular filler onto its electrical drawing purpose, preserves
every other mask, verifies every checkpoint terminal against the actual metal,
and checks masks and labels again after writing the GDS. All six original/filled
views for the three blocks reproduce the natively extracted inputs. The final
delivery GDS retains the correct purpose-22 fill geometry.

The active-fill view is limited to uncontacted N+ active in ordinary PWell.
It rejects circuit contact, poly filler and process modifiers. Each active square
has its own floating node and the pinned `dantenna` model, with substrate/PWell
as anode, N+ active as cathode, and its actual 3.4 µm width and length. Its
nonlinear junction capacitance and series resistance remain explicit.

The native missing-terminal diagnostics are audited individually against actual
decap locations, both transistor dimensions and all four rail connections.
Original and filled layouts have the same 7,638/38,370/38,604 expected diagnostics
for counter/UART/APB. A warning outside those exact decap fingers is rejected.
This is not a general warning waiver.

The first raw `.ext` comparison differed from the hierarchical native SPICE
waveform by about 15.84 ps. Investigation found that the hierarchical exporter
incorrectly applies resistor Pi-capacitance redistribution to IHP MOS subcircuits:
the inverter control loses its 163.059 aF gate-to-substrate capacitor. That native
waveform is not an acceptable reference. Flat export preserves the original
capacitor graph and rejects the hierarchical-export control.

`check_ihp_flat_capacitance.py` checks every original capacitor against the flat
export, allowing only the captured native numeric serialization. It reports and
bounds tiny negative overlap-subtraction residues; meaningful negative values
fail. The exporter also preserves the original sub-aF values in a full-precision
capacitor file. `ihp_native_capacitance.py` reduces that checked graph, eliminates
only floating metal, retains every active-junction node, and verifies numerical
residual, symmetry and passivity. A fixed 1e-4 charge-row error budget bounds
sparsification; it is not a timing-error bound.

The first native-SPICE networks reproduced across Windows and Linux within
1e-7 aF per capacitor. That established numerical reproducibility only. A later
independent geometry check found that their isolated `.ext` export used Magic's
default grid instead of the layout's 5 nm grid. Junction areas were four times
the drawn area and perimeters were twice the drawn perimeter. Capacitor
redistribution also changed. All transistor waveforms and convergence results
using either faulty export are rejected as acceptance evidence, including the
earlier counter corner results and UART/APB functional results. Their archived files
remain available for diagnosis; their passing waveform audits do not override
this invalidation. The geometry, strict LVS and separate OpenRCX evidence do not
depend on that export.

`ihp_magic_export.py` now imports the electrical GDS, extracts and exports flat in
one native process, then checks the capacitor graph. Its independent inverter
control compares exported junction
and channel areas with the drawn masks. The corrected NMOS/PMOS junction areas
are 0.5032/0.7616 µm² and agree within 1e-5 µm²; the deliberate default-grid
export fails the same criterion. All six corrected exports pass capacitor and
individual-warning audits. Their reduced capacitor networks reproduce on Windows
and Linux within 3.64e-12 aF per capacitor. The focused suite has 70 passing tests
on each system, with no skipped tests.

The corrected lumped-capacitance counter passes 432 output-bit checks across
matched original/filled nominal, slow and fast conditions. The fast run starts
from a captured reset state; cold zero-charge power-up with the original 1 ns
supply ramp remains numerically unresolved. The corrected UART and APB baseline
waveforms pass 254 and 869 output-bit checks. These results use ideal supplies.
An initial 1e-4 reduction misses the fixed 1 ps convergence limit at 1.145 ps.
With a 1e-5 reduction budget and tighter matched integration settings, the full
and reduced counter agree within 0.034957 ps across the four checked output
edges. A deliberately shifted 2 ns waveform fails. This is a counter convergence
check, not calibration of the field model or every workload.

The [native-export checkpoint](validation/ihp-native-export-2026-10-10.json)
explicitly supersedes electrical acceptance from the earlier faulty exports.
The first distributed-RC attempts are also rejected. Magic expands imported
labels to conductor bounding boxes, which can produce duplicate resistance
endpoints and negative area weights. `ihp_magic_rc_points.py` places each exact
net label at a verified metal-pin point, retaining actual boundary terminals.
It never selects all labels in the bounding box: that would also move nearby
fill names. All six corrected captures preserve every original capacitor exactly.

The existing production normalizer then preserves the raw capacitance and
checks the full device parameters and resistance topology. The counter, UART
and APB captures retain 403, 5,108 and 4,485 resistors respectively, before and
after fill. Ideal supplies, native zero-resistance nodes and quasistatic floating
fill have explicit, recorded anchors; positive-resistance circuit nets cannot
be replaced with ideal nodes. The original native files remain available.

`ihp_distributed_capacitance.py` keeps the solver's existing matrix-size bound.
It eliminates floating metal in the original net matrix and restores the
same-net endpoint terms needed when voltages differ along a resistor network.
An independent calculation expands the counter to physical resistance endpoints
before eliminating metal. The serialized compact model agrees across 1,087,880
matrix entries, with maximum absolute error 9.32e-10 aF and the unchanged
1e-12 relative/absolute comparison criteria. Omitting the same-net correction
fails. Complete full-fill waveform acceptance and production integration remain
open; preparing a conserved RC model does not establish either result.

### Complete-waveform and floating-poly controls

The nominal counter's first matched full-RC captures pass all 144 output-bit
checks, with 31 matched output edges and a maximum change of 16.308678 ps.
This uses the 1e-5 charge-row model, ideal supplies and a 50 ns clock. With
tighter matched integration, the separate 1e-4 lumped-capacitance reduction
also meets the existing 1 ps convergence criterion, at 0.045343 ps. These
results do not complete the larger workload gate.

`check_ihp_waveform.py` rejects an aborted native transient even when ngspice
returns zero and writes a partial waveform. It checks channel identities,
finite ordered data, the complete requested interval and every expected bit.
The captured UART/APB full-RC startup failures are rejected by this guard;
their completed lumped baseline captures still pass.

`ihp_floating_poly.py` identifies 21/208/152 capacitor-only poly nodes in the
counter/UART/APB, in both original and filled layouts. Every native port,
device terminal and resistor endpoint is protected. Only a native poly node
with zero extracted resistance and one normalized endpoint can be selected.
The same passive reduction removes its floating voltage while preserving its
capacitive effect. An independent counter calculation that expands physical
resistance endpoints first agrees across 1,044,515 matrix entries within the
unchanged 1e-12 comparison criteria; omitting the same-net correction fails.
The focused suite now has 85 passing tests on each operating system.

The APB original-layout powered-reset probe now completes 100 ns and passes
44 output-bit checks. It is a bounded convergence probe, not the complete
1,610 ns workload. Larger matched captures, numerical convergence and
production integration remain open.

## Reproduce the geometry stage

Obtain the exact three macro files listed in the source lock and the pinned
maximal deck. With KLayout 0.30.5 and its Python package installed:

```text
python scripts/prepare_ihp_block_fill.py --gds original.gds --top counter --die-nm 0 0 200000 200000 --macros pinned-macros --deck sg13g2_maximal.lydrc --executable /path/to/klayout --output new-evidence-directory
```

The directory must be new. The command rejects changed sources, a resized die,
existing fill, unsupported chip boundaries and insufficient existing poly density.
A successful exit establishes only this native geometry result.

Run the supplemental rules against the same final GDS:

```text
python scripts/check_ihp_fill_rules.py --gds filled.gds --manual SG13G2_os_layout_rules.pdf --output supplemental.json
```

The manual must match the source lock. This checks block applicability explicitly;
it does not manufacture chip-window coverage for a smaller block.

Use `scripts/ihp_lvs_reference.py` to prepare a reference from the captured
OpenROAD CDL, standard-cell masters and `digital_lvs_engine.py` checkpoint export.
Keep its `aliases.json` with the native comparison inputs. After running the
pinned native LVS deck with the captured options, audit the comparison:

```text
python scripts/check_ihp_lvs.py report.lvsdb --aliases aliases.json --output audit.json
```

## Reproduce the electrical model stage

Run `scripts/check_ihp_rcx_widths.py rules represented.json --output widths.json`
before considering a represented fill model. It requires an exact nominal table
point for every observed fill width in every applicable metal table. It rejects
the single-width vendor model, missing tables and nonfinite or malformed widths.
Passing this inventory guard does not establish native response or field accuracy.

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

For the separate transistor-capacitance experiment, export the previously
verified electrical GDS view with its actual native layout grid:

```text
python scripts/ihp_magic_export.py --gds electrical-view.gds --top counter --technology pinned-magic/ihp-sg13g2.tech --executable /path/to/magic --output new-native-directory
```

Audit the saved extraction feedback and retain the original device records.
Do not export a detached `.ext` in an unverified default-grid session. With
NumPy 2.3.5 and SciPy 1.16.3 available:

```text
python scripts/ihp_native_capacitance.py --spice new-native-directory/capacitance-full-precision.spice --ground NET000001 --output new-capacitance-directory
```

Use the verified physical ground alias, not an assumed name. Replace only the
capacitors in the matched experimental circuit with the generated network, retain
every functional transistor and active-junction model, and run the independent
waveform comparison. A successful preparation is not electrical acceptance.

## Remaining chunk 5 work

- Complete the filled UART/APB transistor comparisons and the full-fill electrical
  acceptance, including the unresolved cold-start numerical case.
- Bind the accepted full-fill capacitance and resistance model to the timing
  checks; finish review of the OpenRCX model's fill-width scope.
- Integrate the accepted recipe into the production flow, bind final export
  evidence, and rerun affected production and package tests.

None of these results establishes full IHP, bipolar/RF or tapeout qualification.

## Latest waveform and numerical diagnostics

The [width and waveform checkpoint](validation/ihp-width-waveform-progress-2026-10-10.json)
preserves the new completed comparison, rejected width model and numerical
diagnostics separately from any continuing run.

The completed capacitance-only APB pair passes 1,738 output-bit checks across
the complete 1,610 ns stimulus. All 90 output transitions have matching
directions; the largest observed timing change is 77.0093 ps. This is a measured
comparison, not a numerical convergence or distributed-resistance acceptance.
The filled UART capacitance run exhausted its 7,200-second runtime budget before
completing. Its replacement uses identical inputs and numerical settings with
a longer wall-clock budget. Neither an expired run nor a partially saved waveform
is accepted.

`scripts/ihp_transformer_capacitance.py` is a research alternative for representing
the same conserved capacitance matrix with reciprocal ideal port transforms.
It retains physical wire resistors and active-fill junctions. Matrix tests and
a small native linear fixture agree, but its initial complete-circuit and
powered-reset probes failed numerically. It is not an accepted performance model
and does not alter the desktop flow. No physical resistor was collapsed and no
leakage shunt was added to make those failed runs pass.

## Calibration geometry and material checks

The [calibration checkpoint](validation/ihp-calibration-progress-2026-10-10.json)
records further experimental model corrections. Chunk 5 remains incomplete.

`scripts/ihp_calibration_geometry.py` requires every reference wire's native
metal, area and perimeter to match its intended rectangle exactly. This rejects
the extra metal painted by DEF measurement ports and rejects rounding of
off-grid reference patterns. Independent GDS cells retain each calibration
pattern's relative geometry. The two-width pilot produces byte-identical rules
to the monolithic extraction while reducing native extraction from 862 seconds
to about 3 seconds. This isolation is only for reference patterns; circuit
coupling is not discarded.

Native import audits also caught two mirrored SPEF records being treated as
distinct capacitors. Both records must identify the same terminal pair. The
corrected import conserves every reference ground capacitor, mutual capacitor
and rectangular wire resistance within the stated native storage precision.

`scripts/ihp_rcx_material.py` binds the seven nominal sheet resistances to the
pinned Magic extraction source, rejects other corners or revisions, and reads
back every applied layer value. Native extraction must explicitly use
`-lef_res`; wider calibration tables alone do not enable width-scaled wire
resistance. Routing resistance overrides are replaced by the audited nominal
material values for this experiment. This does not calibrate via resistance or
other process corners.

All 52 absent/nearby controls now pass their absolute resistance and basic
capacitance-response checks across the minimum, doubled-minimum and actual
1/3.5/5 µm fill widths. Every applicable width table contains the actual widths.
Complete width blocks are ordered numerically without changing any tabulated
value or its metal/context. These checks still do not accept the model: the
separate 5% nominal capacitance consistency gate remains unresolved. Native
timing must be repeated with an accepted model before fill closure.

A denser, two-width spacing pilot retains 355,710 reference wires after rejecting
whole off-grid patterns before extraction. All retained rectangles and imported
values pass their audits. At 20 µm length, 20 of 28 independent controls pass the
5% consistency limit; the eight remaining failures are ground capacitance on
TopMetal1 and TopMetal2. All 28 controls pass at 200 µm length. This supports
investigating finite wire-end capacitance, and does not justify accepting short
fill rectangles or raising the tolerance. The actual-width model still needs
that correction and a complete repeated comparison.

Install the independent reference solvers with
`python -m pip install -r requirements-qualification.txt` before running the IHP
qualification tests. The desktop packaging workflow installs those pinned test
dependencies explicitly. The current 108-test IHP suite passes on Windows and
Linux with no skipped cases; packaging and full release acceptance remain
separate checks.
