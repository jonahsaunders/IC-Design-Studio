# Bundled device corrections and reproducible qualification

New projects use bundled SKY130 revision `293106f92f3e1dc5`, GF180 C revision
`5f3017f16df69dbe`, GF180 D revision `836ecc491786bd41` and IHP revision
`1e24ec25b491028b`. These include the tested resistor/NPN and MIM corrections,
parallel-unit SKY130 varactors, capacitor terminal mappings, GF180 native-model
selection, IHP isolation/clamp bindings and fixed SKY130 20 V geometry. Saved projects retain their
registered revisions; migration remains explicit. Original
licenses, modification notices and source hashes are retained. These changes
and their selected tests do not complete device-family qualification.

The earlier [default integration record](validation/default-device-packages-2026-10-17.json)
passes 62 fresh electrical cases through normal project creation, plus nine
IHP isolation cases. Independent raw readback verifies 4,590 terminal vectors,
32 standard-MOS analyses and 740 deliberately faulted device instances. Both
hosts pass save/reopen/netlist/export checks for all 235 usable entries; the
20 unavailable entries are separately checked for expected rejection.

Thirty standard single-finger transistor layouts across GF180 C/D and IHP pass
native full DRC and strict LVS at five selected sizes, with all 90 deliberate
length, drain-contact and gate/drain-short faults detected. Twelve IHP MIM
layouts also pass; three physical faults and three spacing boundaries retain
their separate expected outcomes. These are specific device fixtures, not
qualification of every layout or operating condition.

The earlier 2,963-test regression runs each exposed one assertion requiring adjacent
width/length text even though named SPICE parameters are order-independent.
The corrected assertion and related default-package/migration tests pass all
18 focused checks on each host. Original failed full-run logs and explicit
skips remain recorded. Complete installed-runtime acceptance is still separate.

## Fixed geometry and bundled model inventory

The [fixed-geometry and inventory record](validation/fixed-geometry-and-model-inventory-2026-10-17.json)
adds a source-locked contract for all seven SKY130 20 V symbol views. Their
internal transistor/parasitic dimensions are constant. W/L arguments do not
scale that geometry, and out-of-bin values can prevent model selection.
The app accepts only the recorded values, makes those fields read-only and
excludes them from parameter searches. Parallel multiplicity remains editable.
Generic MOS kp/vto/lambda fields are also excluded from searches when a PDK
model makes them inactive. Saved projects retain their existing revisions.
These internal model values do not establish drawn-mask dimensions or reliability limits.

Both native Windows ngspice 42 and corrected Linux/WSL ngspice 47 pass 54
selected DC/AC cases: three corners and 0/27/85 C, with the previously declared
0–1.2 V gate sweep and independent terminal drives. Each host passes 3,132
terminal vectors, 36 within-bin dimension controls and 252 deliberately faulted
instances. Independent raw readback checks all 324 output files across both
hosts. Wider dimension controls retain their original model-selection failures.
This is interface qualification at those points, not the full 20 V operating envelope.

The complete bundled SPICE include closure contains 6,402 definition occurrences
and 52 alternate declarations in source symbols. The inventory preserves source
lines, library sections, internal scope, conditional branches and naming diagnostics.
Every usable catalog model is present in each selectable corner. Three named
SKY130 alternatives lack definitions in this closure; alternatives are not
enabled or qualified by inventory alone. The separate IHP Verilog-A inventory
finds nine declarations and accounts for all six referenced external types.
Both inventory reports are identical on Windows and Linux. Other upstream views
and process options remain outside this source-coverage claim.

```sh
python scripts/qualify_sky130_fixed_geometry.py --package icstudio/assets/pdks/sky130A --output /path/to/new-results --ngspice /path/to/ngspice
python scripts/inventory_device_models.py --output /path/to/new-model-inventory.json
python scripts/inventory_veriloga_models.py --output /path/to/new-veriloga-inventory.json
```

The latest Linux full regression discovers 2,979 tests and passes with 15 explicit
skips. The Windows full run discovers 2,976 tests: 2,903 pass, 36 skip and 37
encounter sandbox socket/junction restrictions. All 37 pass when rerun with
the required local access; three subsequently added Verilog-A inventory tests
also pass. Original failed runs remain failures in the evidence record.
The editor checks all 14 fixed fields and seven editable multipliers on each
host. All 235 usable catalog entries pass save/reopen/netlist/export checks;
20 unavailable entries retain their expected rejections. Desktop CI now runs
the fixed-field editor check and both model inventory checks.

The later [artifact-path correction](validation/artifact-path-portability-2026-10-17.json)
fixes the short/full Windows directory aliases that caused 15 failures in an
earlier Windows release build. Both hosts pass all 15 original failing cases.
The focused digital/export run discovers 45 tests per host: Windows passes 40
and skips five unavailable-engine checks; Linux passes 42 and skips three
Windows-only checks. Seven additional Windows alias/long-path checks pass.
The full regression runs above predate this path correction. Final-head CI and
installed desktop acceptance remain pending.

## Prepare and install

From this repository, with Python and the project dependencies installed:

```sh
python scripts/prepare_default_device_packages.py --output /path/to/new-default-packages
```

This reproduces all four current package manifests byte for byte. It verifies
the bundled assets and reconstructs exact earlier inputs from the retained
manifests in `icstudio/assets/qualification/device-base-v2`. Those inputs use
the unchanged original assets; no earlier result is reassigned to a new revision.

Earlier individual correction packages remain reproducible with their original
recipes:

```sh
python scripts/prepare_sky130_device_package.py --output /path/to/new-sky130-default
python scripts/prepare_ihp_mim_qualification.py --output /path/to/new-ihp-adapter
python scripts/prepare_sky130_resistor_qualification.py --output /path/to/new-sky130-adapter
python scripts/prepare_sky130_bipolar_qualification.py --output /path/to/new-sky130-bipolar-adapter
```

Each output directory must be new. The preparers verify every input asset and
the exact source package revision before writing an output. The SKY130 builders
can reconstruct the original package from retained, hashed source deltas; this
preserves the earlier comparison packages. The individual IHP MIM builder
reproduces its earlier revision; use the default-package builder above for the
current combined corrections. In the app's PDK
revision manager, choose **Install packageâ€¦**, select the generated
`package.json`, and select the new revision for a project. Review revision
migration before changing an existing project.

| Correction | Original revision | Output revision |
|---|---|---|
| Earlier SKY130 resistor/NPN package; existing corner selections retained | `b1f441fabee1ed85` | `2a8a8a7048ac324d` |
| IHP standard MIM physical checking | `3abac20fcb57e184` | `d03f47cdf46a85a0` |
| SKY130 resistor parallel factor | `b1f441fabee1ed85` | `b897a1bb4cffa3bc` |
| SKY130 resistor correction plus NPN corners | `b1f441fabee1ed85` | `23527d231481aae4` |

## IHP capacitor checking

The public Magic MIM connectivity calculation now copies its existing contact
and top-metal sets into fresh CIF planes before traversing them. This avoids
the observed interference with native DRC visitation state. The original
600 nm spacing limit, operands, device extraction and all other rules remain
unchanged. No violations are waived.

Six standard `cap_cmim` geometries at two orientations pass native full DRC and
strict LVS after GDS import and explicit port assignment. Assigning ports is
checked to preserve every mask. Missing contacts, a plate short and incorrect
width are detected. Independent mask calculations and native MIM.e findings
agree at 595, 600 and 605 nm; these boundary controls retain other spacing
findings and are not full-DRC-clean examples.

Reproduce with the pinned local Magic and Netgen runtime:

```sh
python scripts/qualify_ihp_mim_layout.py --output /path/to/new-results --magic /path/to/magic --netgen /path/to/netgen
```

The correction applies to this locked public deck. It does not qualify RF MIM,
all legal dimensions, every PDK device or complete-chip signoff.

## SKY130 resistor simulation

Seven public polysilicon resistor models did not propagate the parallel `M`
factor through nested calls in the tested ngspice runtimes. Five fixed-width
extra-high-resistance models lost the factor for their whole circuit; the two
generic high/extra-high models lost it in their parasitic capacitance.

The correction declares `M=1` and explicitly forwards `M` to each immediate
resistor or nested model call. Equations, fitted coefficients and statistical
`MULT` expressions are unchanged. Apache notices and original source provenance
are retained, and each changed file contains a modification notice.

Twenty SKY130 resistor entries pass selected complex admittance and fault tests
with the corrected package: two lengths, multiplicity 1/3, two biases, three
corner selections and 0/27/85 C. A separate audit compares corrected results
against untouched unit models, including three parallel unit responses.

```sh
python scripts/qualify_resistor_families.py --output /path/to/new-results --ngspice /path/to/ngspice --osdi /path/to/ihp-osdi --targets sky130A --sky130-adapter /path/to/new-sky130-adapter/package.json --workers 4
python scripts/check_resistor_unit_reference.py --batch /path/to/new-results --original-batch /path/to/original-results --output /path/to/new-reference-audit.json
```

The historical original batch uses the retained unmodified `b1f441fabee1ed85`
package and its archived runner source. Omitting `--sky130-adapter` now selects
the corrected bundled default and cannot reproduce that original failure.
Original parallel-scaling failures remain failures; their unit responses provide
the independent reference. The IHP OSDI
directory is an existing runner requirement even for this SKY130-only batch.

Full geometry/bias/reliability envelopes, mismatch and noise behavior, extracted
connectivity and layouts for these resistor families remain open. The included
SKY130 package separately fixes four metal-resistor SPICE prefixes and the two
default primitive diode bindings; those metadata fixes preserve all upstream
asset bytes.

## Bipolar device execution

The [bipolar record](validation/bipolar-families-2026-10-16.json) exercises all
29 bundled bipolar symbols at selected DC points. It compares collector, base,
emitter and substrate currents with independent model calls, checks turn-on and
electrical current conservation, and detects base/emitter shorts and
collector/emitter swaps. Five-terminal IHP HBT thermal ports are clamped to zero
temperature rise; their thermal behavior is not qualified by these tests.

The original SKY130 NPN failed because its active library never loaded required
corner parameters. The current default package loads the reviewed t/s/f inputs
inside its tt/ss/ff sections. Every other existing corner section retains its
original content; no additional NPN corner mapping is inferred or qualified. For reproducing the earlier narrower test, the bipolar preparer includes the original public Apache
sources and their exact parameters, without changing NPN model equations. It
also includes the resistor correction. This package explicitly maps NPN t/s/f
to nominal/ss/ff and supports the tt alias. Other corner selections are rejected;
mixed, mismatch and Monte Carlo mappings are not guessed.

```sh
python scripts/qualify_bipolar_families.py --output /path/to/new-results --ngspice /path/to/ngspice --osdi /path/to/ihp-osdi --targets sky130A --sky130-adapter /path/to/new-sky130-bipolar-adapter/package.json --workers 4
```

GF180 C/D uses the included packages and ngspice 42. The IHP sweep passes with a
separately built public ngspice 47 binary; three hot NPN cases fail with the
default ngspice 42 runtime. This is not a default-runtime upgrade. A strict
cross-version comparison also finds numerical differences in 12 of the 33
cases that completed in both versions. Those findings remain visible; engine
interchangeability and release integration are not claimed.

The tested 144 cases cover selected corners, temperatures, collector biases,
base sweeps and multiplicity/emitter-geometry inputs. Full envelopes, AC/noise,
RF, mismatch, physical layouts and extracted connectivity remain open.

See the [qualification plan](PDK_QUALIFICATION_PLAN.md) for the complete gate and
the [PDK guide](PDK_GUIDE.md) for revision management.

## Public simulator and diode regression

The Linux/WSL runtime recipe builds the SHA-256-locked public ngspice 47 source
and retains its source archive, copying terms, build logs and binary identity.
Its launcher locates code models relative to the installed directory, including
paths containing spaces. The generated startup defaults to one simulation thread;
users may override that setting. The original 2026-10-16 build leaves simulator
equations unchanged; the subsequent capacitor parser correction is described
below. The complete
runtime image and installed release workflows still require acceptance.

The [runtime record](validation/runtime-device-regression-2026-10-16.json)
retains the 432-case diagnostic-engine MOS sweep, 72 passive cases, primitive
diode compatibility and selected tests of the production-source binary. The
36-case GF180/IHP diode sweep adds 25 catalog entries, 990 terminal-current
vectors and 900 detected device faults. These are selected DC integration
conditions, not ESD ratings, full operating envelopes or measured-silicon accuracy.

```sh
python scripts/build_ngspice_runtime.py --output /path/to/new-runtime --jobs 4
python scripts/qualify_diode_families.py --output /path/to/new-diode-results --ngspice /path/to/new-runtime/installed/bin/icstudio-ngspice --osdi /path/to/ihp-osdi --workers 4
```

## IHP isolation-box interface

The public `isolbox` symbol uses the terminal name `sub!`. Catalog terminal
validation now accepts this punctuation while keeping model and parameter names
restricted. Fresh stock imports and the current default recognize the binding;
saved projects keep their exact revisions.

The [isolation-box record](validation/ihp-isolation-interface-2026-10-16.json)
tests a separate package with unchanged upstream assets and defaults. Its width
and length must each be strictly greater than 2.1 µm, because the public equations
subtract 2.1 µm from each inner dimension. This is a mathematical domain guard,
not a foundry minimum or complete geometry qualification. Changed model bytes
require a fresh review before the importer applies that guard.

```sh
python scripts/prepare_ihp_isolation_qualification.py --output /path/to/new-isolation-package
python scripts/qualify_diode_families.py --output /path/to/new-isolation-results --ngspice /path/to/new-runtime/installed/bin/icstudio-ngspice --osdi /path/to/ihp-osdi --isolation-only --workers 4
```

Install the prepared package using **Install package…** to use this explicit revision.
Nine corner/temperature cases pass independent terminal-current comparisons and
36 detected pin/geometry faults. Eleven focused tests pass on Windows and Linux,
including fresh import, save/reopen, Xschem exchange and invalid-dimension rejection.
The current default repeats all nine cases successfully. Add
`--historical-isolation` to reproduce the earlier separate package.
Physical extraction and full bias/geometry envelopes remain open requirements.

## Primitive source inventory

`scripts/reconcile_primitive_inventory.py` verifies the complete primitive
Xschem source views, including unavailable entries. It reconstructs every Git
tree object so a truncated or omitted directory entry cannot silently pass.
It streams the pinned SKY130 `common.tar.zst` without extracting its contents.

Use `zstandard==0.23.0` in the qualification Python environment. The input GitHub
recursive-tree JSON responses must use the exact tree identities in the runner's
`LOCKS` table, with `recursive=1`. The existing SKY130 archive must match the
bundled `UPSTREAM-LOCK.json` checksum.

```sh
python scripts/reconcile_primitive_inventory.py --ihp-tree /path/to/ihp-tree.json --gf180-tree /path/to/gf180-tree.json --sky130-common /path/to/common.tar.zst --output /path/to/new-inventory.json
```

The [record](validation/primitive-symbol-inventory-2026-10-16.json) retains identical
Windows/Linux reports for all 255 entries and enumerates other symbol-view
directories. Source identity does not establish model terminal semantics,
model-only device completeness, operating ranges or physical qualification.

## Capacitor families and explicit parallel varactors

The [capacitor record](validation/capacitor-families-2026-10-17.json) adds 37
catalog entries: four SKY130, thirteen each GF180 C/D and seven IHP. All 180
selected cases pass independent complex terminal-current comparisons at two
geometries, two biases, three corners and 0/27/85 C, over 100 Hz–10 MHz. Every
available terminal is driven separately. An independent raw-file readback
reproduces 12,888 vectors (335,088 samples), 1,332 parallel-device comparisons
and 5,328 detected wrong-size or disconnected-terminal instances.

These tests exposed a public ngspice 47 parser defect: nonlinear capacitor
multipliers were concatenated with `e9`, producing invalid scientific literals
and parameter expressions. The runtime builder now applies a source-hash-checked
formatting correction expressing the intended `m*1e9` gain. It retains the
original source, patch, upstream archive, copying terms and modification notice.
The corrected binary passes 21 analytical response vectors at three biases;
the original binary's failures are retained. PDK equations are unchanged.

The public SKY130 varactor `VM>1` behavior does not equal parallel copies of the
unit device. The earlier separate package defines positive `VM` as parallel
upstream `VM=1` devices, including their substrate parasitics. Its explicit
wrapper models and revision `32afdde0c2e14085` preserve all original upstream
files. The current default includes this explicit contract; existing saved
projects retain their original contract. The independent reference instantiates literal unit devices and does
not call the new wrapper.

```sh
python scripts/build_ngspice_runtime.py --output /path/to/new-runtime --jobs 4
python scripts/verify_ngspice_capacitors.py --ngspice /path/to/new-runtime/installed/bin/icstudio-ngspice --output /path/to/new-analytical-results
python scripts/qualify_capacitor_families.py --output /path/to/new-capacitor-results --ngspice /path/to/new-runtime/installed/bin/icstudio-ngspice --osdi /path/to/ihp-osdi --parallel-varactors --workers 4
```

The last command creates the explicit SKY130 package under its output directory;
use **Install package…** to select that revision. To prepare it separately, run
`python scripts/prepare_sky130_parallel_varactors.py --output /path/to/new-package`.

Application/reference matching uses 1e-6 relative and 1e-15 A absolute limits.
Parallel and analytical checks use the same relative limit with a 1e-14 A
floor for the simulator's unscaled numerical shunt and internal-conductance
cancellation. Earlier stricter failures and precision experiments are retained;
conductance below 1e-14 S is not resolved. Fault detection keeps the original
application/reference limits. The source models' individual corner and
frequency limitations still apply; a requested corner is not proof that a model
provides distinct corner equations. In particular, IHP `cap_cmomf` is a
low-frequency engineering estimate without silicon validation or characterized
corner/mismatch spread; `cap_cmomi` also uses nominal-only corner/mismatch
behavior. Their original model notices remain in the package and evidence.

Nine focused tests pass on each OS, including package immutability, save/reopen,
Xschem exchange and rejected parameter/response faults. Full operating ranges,
noise, statistical independence, physical extraction, RF-band and silicon
accuracy and installed-runtime acceptance remain
separate requirements. The complete passing and failed experiments are in a
verified 112 MB archive outside dated working folders.

## Four-terminal capacitor corrections

The [four-terminal record](validation/four-terminal-capacitors-2026-10-17.json)
adds the two remaining placeable capacitor entries: the default SKY130 fixed
VPP model and IHP SVaricap. The original SKY130 symbol assigns the substrate
connection to the M5 shield and vice versa. The original IHP symbol swaps the
model's two gate terminals; its asymmetric coupling network makes that swap
observable. All four original VPP terminal drives and both original SVaricap
gate drives fail the independently ordered reference. Those failures are retained.

Corrected packages preserve every upstream asset and are now included in the
defaults. Saved revisions remain unchanged. The SKY130 package maps model order
`c0 c1 b m5` to `c0 c1 sub top`, retains the parallel-unit varactor adapters,
and removes W/L controls that the fixed-layout model does not implement. Its
positive `mult` parameter retains the public model's statistical and subcircuit
multiplier semantics. The IHP package maps `G1 W G2 bn` to `g1 nw g2 body`,
retains the earlier isolation-box interface, and enforces source-declared
W/L/Nx boundaries. These bounds do not establish a complete operating envelope.

```sh
python scripts/qualify_four_terminal_capacitors.py --output /path/to/new-four-terminal-results --ngspice /path/to/new-runtime/installed/bin/icstudio-ngspice --osdi /path/to/ihp-osdi --correct-vpp --correct-svaricap --workers 4
```

The command produces `vpp-package` and `svaricap-package` inside the output
directory; select the intended revision using **Install package…**. The packages
can also be prepared separately with `prepare_sky130_vpp_binding.py` and
`prepare_ihp_svaricap_binding.py`, each taking `--output` with a new directory.

All 144 selected cases pass four independent terminal drives at two biases,
three requested corners and 0/27/85 C, over 100 Hz–10 MHz. Raw-file readback
reproduces 1,728 complex vectors and 864 detected multiplicity or driven-terminal
faults. Eight focused tests pass on each OS, including preserved package assets,
save/reopen, Xschem terminal identity and rejected geometry inputs. The comparison
limits remain 1e-6 relative and 1e-15 A absolute.

Together with the preceding batch, all 39 currently placeable capacitor catalog
entries have selected electrical integration evidence. Other fixed VPP variants,
complete operating ranges, statistical/RF accuracy and physical extraction
remain open. In particular, SVaricap `Nx` changes
model geometry and is not assumed to equal parallel independent devices.

## MOS variants and clamp connections

The [MOS variant record](validation/mos-variants-2026-10-17.json) covers all
86 currently placeable MOS/clamp catalog entries: 42 SKY130, 17 each GF180 C/D,
and 10 IHP. These are symbol views; several share the same model. All 324
selected cases pass independent DC and complex terminal-current comparisons
under three requested process selections and 0/27/85 C. Raw-file readback
reproduces 33,516 vectors and 1,100,376 samples. All 3,096 deliberately faulted
device instances are detected in 126 simulations. Nine additional IHP cases
detect disabled RF mode in every tested RF view, covering 72 device instances.
This establishes model selection and terminal integration through 1 GHz, not
RF model accuracy or ESD robustness.

The original GF180 native-threshold symbol incorrectly selects `nfet_06v0`.
The corrected package selects the existing `nfet_06v0_nvt` model. The IHP
`nmoscl_2` and `nmoscl_4` bindings now follow model order `VDD VSS`, also
declared by the symbols' simulation pin numbers. Both original defects fail
the independent reference. All upstream asset bytes are retained. Fresh
registration applies the exact-source-guarded GF180 correction and preserves
the symbol's parsed simulation pin order. The current defaults include these
corrections, while saved projects retain their existing identities.

```sh
python scripts/qualify_mos_variants.py --output /path/to/new-mos-results --ngspice /path/to/new-runtime/installed/bin/icstudio-ngspice --osdi /path/to/ihp-osdi --correct-bindings --workers 4
```

Use `--pilot` for the nominal 27 C run. Corrected packages are written below
the output directory; select them through **Install package…**. The IHP
package also retains the previously tested isolation-box and SVaricap bindings.
Twenty-six focused tests pass on both Windows and Linux, including source
preservation, corrected fresh imports, saved revisions and Xschem handoff.

The selected gate range is 0–1.2 V with 0.6 V drain bias and separate source,
body and isolated-substrate connections. AC tests drive every terminal
independently from 1 kHz to 1 GHz. Several SKY130 models provide discrete size
bins; the retained initial generic-size failures are not passes. The 20 V
models use fixed internal geometry, so their two tested instances vary
multiplicity rather than effective W/L. The newer fixed-geometry contract
described above now enforces that limitation. Named corner selections also do not imply
distinct corner models for every device. Full operating limits, statistical
behavior, physical layout/extraction and other selectable models remain open.
