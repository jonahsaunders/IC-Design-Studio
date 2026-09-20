# Analog references and extracted verification

Use one saved circuit, its saved testbenches and unchanged requirements to
compare schematic and extracted behavior. The [integrated workflow](ANALOG_CLOSURE.md)
provides revision tracking, constrained layout updates and durable campaigns;
dev25 extends the supported references, diagnostics and hierarchical extraction.

## Start from a linked process

Link the complete, matching SKY130A process in PDK manager. Simulation model
subsets alone do not supply Magic extraction or Netgen setup files. Preserve the
package lock and configure the actual Magic, Netgen and ngspice executables.

Choose **File → New SKY130 two-stage op-amp** to create an editable reference
using the linked technology. The equivalent source API uses the PDK from a
project you have already configured:

```python
from icstudio.model import load_project, save_project
from icstudio.two_stage_opamp import reference

configured = load_project("linked-sky130-project.icproj")
project, dut_cell_id, bench_id = reference(configured["pdk"])
save_project(project, "two-stage-opamp.icproj")
```

This reference requires the supported SKY130 1.8 V NMOS/PMOS models and the
`sky130_fd_pr__cap_mim_m3_1` compensation-capacitor model. Its bias input uses an
external ideal reference current; startup results do not qualify a bias-reference
generator.
The [portable editable example](../examples/sky130_two_stage_opamp.icproj)
contains the four fixtures and 27-condition plan. It starts with bundled
simulation models; link the complete process before physical extraction.
The supplied fixture uses 0.9 V input bias, an external 5 µA current reference,
a 1 pF output load and two explicit parallel 30 × 30 µm MiM compensation
capacitors. Changed bias, load or compensation needs a fresh comparison.
The final reference's M6 output device uses six 5 µm fingers, for total W 30 µm
and L 0.5 µm; the saved layout must match that finger configuration.

## Keep the electrical checks with the fixture

The reference supplies separate OP, AC, noise and transient-startup benches.
Each bench owns its sources, probes, model corner, temperature, diagnostic
definition and measurement limits. Changing the active plot does not change the
saved fixture. Run the selected bench through the analog workspace and inspect
its retained measurements and waveform.
The fixture editor's **Diagnostics** tab selects noise integration, return ratio,
startup or operating-point inspection; **Measurements** saves the corresponding
limits.
The [captured loop-fixture editor](validation/dev25/images/opamp_ac-diagnostics.png)
shows the saved return net, injection net and convention.

| Bench | Saved measurements and interpretation |
|---|---|
| Operating point | Output bias, supply current and static-power requirement. |
| AC loop fixture | Gain, measured unity-gain frequency and minimum phase margin over the sampled unity crossings. A missing crossing is a failed measurement. |
| Noise | Integrated input/output RMS noise over the saved frequency band, using the fixture's named voltage source and output. |
| Startup | Supply ramp, final output and time after which the output stays inside the saved band through the final observation window. |

The AC fixture holds the DC operating point with a large feedback inductor and
uses a shunt capacitor to approximate an open loop over the measurement band.
Its saved diagnostic states the return-ratio convention. It is a defined
engineering fixture; phase-margin results are not a general guarantee for every
closed-loop load or feedback network.

The same diagnostic definitions travel into extracted testbench decks. Retain
failed measurements, missing crossings and failed startup cases rather than
removing them from the comparison. Source execution does not qualify physical
geometry: perform the process flow below for the actual edited layout.

Choose **Design → Generate two-stage op-amp layout…** for the reference's bounded
physical recipe. Review the generated geometry and use the schematic-driven
update flow after resizing supported devices. The source equivalent is
`generate_layout(project, dut_cell_id, replace=False)` from
`icstudio.two_stage_opamp`; replacement is explicit. A generated layout remains
unqualified until the required process and electrical gates pass on that layout.

## Generate bounded process devices

The SKY130 recipes retain the catalog device, its terminal order and its actual
process model. Device regeneration uses the existing physical footprint and ECO
identities. Dimensions use the 5 nm grid; passive catalog W/L values are emitted
in micrometres.

For a selected supported passive, use **Layout → Generate → Generate PDK device
layout…**. The same menu provides **Generate contacted SKY130 guard…** and
**Add tied SKY130 MOS dummy…**. Review the preview and connections, then apply
the generated geometry through the normal undoable edit flow.

| Recipe | Supported dimensions and electrical meaning |
|---|---|
| MiM `cap_mim_m3_1` | W/L 2–30 µm, aspect ratio at most 5:1 and multiplicity one. Place explicit parallel capacitors when more area is needed. The top and bottom plates remain separate electrical terminals. |
| `res_generic_po` | W 0.5–10 µm, L 1.65–100 µm and multiplicity one. The model is emitted as the catalog's SPICE R primitive, with its W/L and terminal order. |
| Contacted guard | P+ substrate or N+ well ring, 0.8–5 µm thickness, at least a 2 µm opening and at most 500 µm overall. A qualified tie uses an existing metal1 conductor carrying the chosen reference net. |
| MOS dummy | An explicit schematic NMOS or PMOS with D/G/S/B tied to one named reference net. Generated straps survive supported dimension updates. |

The supported standard 1.8 V MOS recipe accepts total W 0.42–30 µm, L 0.15–10 µm,
1–8 fingers and multiplicity one. Each finger must retain at least 0.42 µm width
on the 5 nm grid. The 30 µm bound accommodates the reference's output device;
it does not qualify arbitrary dimensions or placements without their own checks.

The source APIs in `icstudio.sky130_devices` are
`install(project, cell_id, device_id, x=0, y=0)`,
`install_guard(project, cell_id, spec, net, tie=None, members=())` and
`install_dummy(project, cell_id, name, kind, tie_net, w='1u', l='1u', x=0, y=0)`.
Review the connections and retain DRC, LVS and electrical results for the exact
generated instance. A guard without a verified reference tie is incomplete;
decorative fill cannot replace an electrical dummy.

Legacy imported generic-poly resistor catalogs that emit an X wrapper must be
reindexed against the corrected catalog mapping before using this recipe. The
dev25 package metadata fixes this binding without changing the upstream model
or symbol bytes. Preserve the new package lock with any regenerated project.

The [retained physical-device qualification](validation/dev25/sky130-devices.json)
passed all 14 acceptance cases with pinned Magic/Netgen and actual ngspice:
ten good coupons had zero full-DRC violations and unique LVS matches, while
four deliberate dimension, connectivity and contact-spacing faults were detected.
The nominal 30 × 30 µm MiM measured 1.81978225 pF in its numerical fixture;
the 1 × 20 µm poly resistor measured 961.4288179 Ω. These are process-model
results for the recorded coupons. SS/FF names share the deterministic MiM
model; this does not establish a capacitor distribution, manufacturing accuracy
or guard-ring isolation performance. [Offscreen Qt evidence](validation/dev25/gui-sky130-devices.json)
retains the four dialog/preview/edit checks.
The poly-resistor recipe has independent DRC/LVS and capacitance-only fixture
evidence. Model-backed resistor primitives are outside the normalized process-RC
path described below.

## Select the physical model explicitly

Open the saved fixture's **Physical extraction** tab. Keep the choice with the
project and select **Compare schematic and post-layout** in its verification
plan when both implementations are required.

| Choice | Supported scope |
|---|---|
| Process capacitance | Locked Magic capacitance extraction followed by the saved electrical fixture. |
| Process distributed RC | Flat, unaliased Magic resistance extraction with conservative reconstruction of the original capacitance matrix. The flow fails when output lacks the required distributed resistance or supported mapping. |
| Calibrated interconnect RC | Checked coupon coefficients for a named corner, Manhattan route paths, ideal pads/vias and bounded same-layer parallel coupling. This is an interconnect model, not measured-silicon qualification. |

For calibrated RC, section length and coupling search distance are saved in
integer nanometres. An omitted RC corner follows the saved model corner; an
explicit RC corner selects its calibration independently. Changing temperature
does not invent new interconnect coefficients.

The process run retains preflight, schematic simulation, full DRC, LVS extraction
and comparison, selected parasitic extraction, post-layout simulation and final
integrity checks. Every required stage must pass. Provenance names the input
revision, model/extraction configuration, actual tools, locked process files,
netlists and waveform hashes. A late change to evidence fails the run even if
the earlier simulations passed.

### Preserve capacitance on the Magic resistance graph

Actual AC and admittance checks exposed a capacitance-redistribution defect in
the pinned Magic 8.3.600 `extresist` path: it mixes attofarad and femtofarad values
and loses original ground and mutual-capacitance contributions when splitting
nets. The process-RC flow now keeps the extracted resistor graph and device-pin
rewiring, and reconstructs capacitance from the original `.ext` records before
SPICE export.

The normalization retains untouched `top.raw.ext` and `top.raw.res.ext` files,
the corrected `top.ext`/`top.res.ext`, the raw SPICE export `raw-export.spice`,
the final `extracted.spice`, and `rc-normalization.json`. The report
records source/output hashes, implementation identity, units, scales, node
mapping, weights, fallback choices and conservation checks. These files are
included in the saved flow's final integrity boundary.

Original ground capacitance is distributed using normalized positive
`extresist` node weights. Original mutual capacitance uses the product of the
two endpoint weight sets. These are area-based lumped weights; the raw
redistributed capacitance magnitudes are discarded. If a net has no positive
weights, its original capacitance is assigned to the resistance node nearest
the original node's physical origin, and that fallback is recorded.

After serialization, the helper checks the full nodal capacitance matrix
(the Maxwell matrix) collapsed back to the original nets, including diagonal
ground/coupling totals and mutual terms. The exporter also rounds capacitances
below 1 aF to zero, so the finalization step reconstructs parasitic C lines at
17 significant digits. It preserves non-capacitor lines byte for byte, checks
the exact named resistor-edge multiset and independently collapses the final
SPICE capacitance matrix for comparison against the original extraction.
Conservation of this matrix does not
determine the physical locations of capacitance or guarantee the distributed
network's behavior at every frequency. The approximation needs its own saved
AC, noise and transient comparisons; it is not a field-solver result or signoff.

This correction accepts only flat, unaliased, complete extraction with intact
ports, one explicit zero-capacitance substrate reference and unambiguous
connected resistance groups. It rejects hierarchical/alias records, inconsistent
units or mappings, and expansion beyond 50,000 generated capacitors, counting
ground and mutual terms together. Physical hierarchy in distributed extraction
remains limited to the separate bounded calibrated mode described below.

The supported normalized process-RC scope is numeric interconnect resistors,
MOS devices and the catalog's MiM subcircuit devices. Native primitive capacitor
devices and model-backed resistor devices are rejected: their electrical devices
cannot be treated as generated parasitics. The separately qualified poly-resistor
physical recipe therefore remains limited to its capacitance-only process fixture.

The [original process-RC evidence](validation/dev25/process-rc-evidence/retention.json)
is explicitly superseded diagnostic evidence. The
[corrected process-RC run](validation/dev25/process-rc.json) passed 76/76 cases
with unchanged implementation during execution: 30 independent-netlist
comparisons, 30 complete saved-bench physical flows, 12 deliberate geometry/
connectivity faults, three stale-evidence rejections and one independent coupon
acceptance containing both wire lengths.
The [corrected evidence manifest](validation/dev25/process-rc-final-evidence/retention.json)
binds the executed candidate implementation and selected raw/results files.
Its precommit base revision is not the candidate implementation identity;
the recorded file manifest and hashes identify the executed code.

For the 100/200 µm metal1 coupon pair, the additional 100 µm produced 12.5 Ω and
10.692 fF. Actual ngspice AC excitation at 1 kHz checked every entry of each
three-terminal capacitance matrix, including signed mutual terms; maximum error
against the recorded reference matrix was 9.47 × 10⁻³⁰ F. This confirms numerical
conservation for the stated deck/coupon and probe, not physical spatial accuracy.

The nominal 27 °C current-mirror OP case retained 15 interconnect resistors and
20 parasitic capacitors, passed all eight flow stages, and kept its requirements:

| Measurement | Schematic | Corrected process RC |
|---|---|---|
| Output current | 51.1916 µA | 50.8059 µA |
| Bias voltage | 0.766026 V | 0.779360 V |

The [final two-stage amplifier record](validation/dev25/two-stage-opamp.json)
passed **216 schematic/extracted case pairs (432 simulations)**. Each of two
geometries ran four saved OP/AC/noise/startup fixtures at all 27 Cartesian
combinations of nominal/SS/FF, 0/27/85 °C and 1.62/1.8/1.98 V. The second
geometry changes the matched M1/M2 lengths from 1 to 1.1 µm; device IDs and
all saved requirements remain unchanged. Both geometries passed full DRC with
zero violations, unique LVS and corrected extraction with 6,325 resistors and
2,839 parasitic capacitors. Implementation integrity passed with no changed
files during the qualification.

The following ranges are **extracted** results across the 27 conditions for
each geometry; schematic ranges remain in the record:

| Measurement | Initial geometry | After matched-pair length update |
|---|---|---|
| Gain | 78.146–82.770 dB | 78.205–82.789 dB |
| Phase margin | 55.763–58.393° | 56.146–58.829° |
| Unity-gain frequency | 3.492–4.807 MHz | 3.445–4.728 MHz |
| Maximum integrated input noise, 10 Hz–10 MHz | 188.815 µV RMS | 190.010 µV RMS |
| Maximum integrated output noise, 10 Hz–10 MHz | 196.456 µV RMS | 195.363 µV RMS |
| Maximum startup settling | 19.139 µs | 19.153 µs |

Across both schematic and extracted phases, supply-current magnitude was
27.979–35.864 µA and static power was 45.326–71.011 µW. These are results for
the saved ideal 5 µA external bias, load and measurement fixtures. Corrected
area-weighted C over the Magic resistance network is still a lumped
approximation; this record does not qualify spatial field-solver accuracy or
foundry signoff. The [aggregate source record](validation/analog-reference-qualification.json)
links this and the other local qualifications, with their separate source
identities and remaining hosted/native acceptance.

For a source qualification checkout with the required compiler/Tcl/Tk development
dependencies and ngspice installed, recreate the pinned process assets and
engines using the same scripts as CI:

```sh
python scripts/build_physical_engines.py --output build/physical-engines
python scripts/fetch_sky130_reference.py --physical-only --output build/qualification-pdk
python scripts/prepare_sky130_qualification.py --input build/qualification-pdk/sky130A --output build/physical-adapter/sky130A
python scripts/qualify_analog_process.py --extraction rc --pdk build/physical-adapter/sky130A --out build/analog-rc-evidence --magic "$PWD/build/physical-engines/installed/bin/magic" --netgen "$PWD/build/physical-engines/installed/bin/netgen" --ngspice /usr/bin/ngspice
```

Use the actual ngspice path on your host and a fresh evidence directory. The RC
command covers the mirror, differential pair and five-transistor amplifier;
nominal/SS/FF at 27 °C and nominal at 0/85 °C; saved OP/DC fixtures; and deliberate
physical/evidence faults. `--circuits current_mirror --conditions nominal:27`
selects a smaller explicitly recorded scope. The straight-metal1 coupon checks
the locked extraction deck's reference coefficients; it is not measured-silicon
or field-solver calibration.
These conditions select transistor model corners and temperatures. Resistance
and capacitance use the pinned extraction deck's coefficients; this does not
qualify independent parasitic process corners or measured-silicon accuracy.

To check the larger two-stage reference with all 27 saved PVT combinations,
unchanged OP/AC/noise/startup limits and an actual layout update, use:

```sh
python scripts/qualify_two_stage_opamp.py --pdk build/physical-adapter/sky130A --output build/two-stage-opamp-evidence --extraction rc --full-pvt --workers 4 --magic "$PWD/build/physical-engines/installed/bin/magic" --netgen "$PWD/build/physical-engines/installed/bin/netgen" --ngspice /usr/bin/ngspice
```

Each before/after geometry receives its own DRC/LVS/extraction. Its immutable
extracted DUT is reused across the saved electrical fixtures and conditions,
with retained netlist/result hashes. This does not claim a new physical
extraction at every voltage/temperature.

## Use supported physical hierarchy

Calibrated extraction accepts linked schematic and physical instances with
orthogonal rotations/reflections and complete mapped ports and terminals. The
run clone resolves the selected hierarchy without editing the original shared
masters. Route paths survive the transform, allowing interconnect resistance
and bounded coupling across instance boundaries.

An instance's parameter values must match its shared physical master. Create a
concrete cell variant when dimensions differ. Every schematic instance needs one
matching physical placement; instantiate electrical arrays explicitly. Native
SPICE program/parameter scopes and unsupported native devices remain outside
calibrated extraction. Review their support in the applicable process flow;
normalized process RC still requires flat, unaliased input. Recursive/deep
calibrated hierarchies, more than 3,000 primitive devices or
100,000 shapes are rejected. The extracted network retains the 2,000-section
limit; increase section length or use a process extractor for larger networks.

The extraction record maps generated devices and shapes back to their source
cells and instance paths. Reapply only to the original matching revision.
Changes to hierarchy, geometry, calibration or process locks require a new run.

## Run repeatable statistical campaigns

In **Verification test plans → Edit plan → Statistical verification…**, select
independent component tolerances, correlated component tolerances or a validated
PDK mismatch model. Choose the parameter cell, trial count and repeatable seed,
then enter the numeric targets, sigma basis and distribution. Correlated normal
targets can share a named factor with a loading between -1 and 1; uniform
variations remain independent.

For the amplifier reference, this source configuration samples declared input
pair widths. It is an engineering tolerance study, not a foundry mismatch model:

```python
plan = project["test_plans"][0]
plan["statistics"] = {
    "kind": "correlated",
    "cell": dut_cell_id,
    "count": 64,
    "seed": 20260920,
    "variations": [
        {"target": "M1.params.w", "relative_sigma": 0.03,
         "distribution": "normal", "group": "input_pair", "rho": 0.7},
        {"target": "M2.params.w", "relative_sigma": 0.03,
         "distribution": "normal", "group": "input_pair", "rho": 0.4},
    ],
}
save_project(project, "two-stage-opamp-statistics.icproj")
```

`rho` is a shared-factor loading. In this example the induced pair correlation is
0.7 × 0.4 = 0.28. Each seeded trial realization is reused across every selected
test and operating condition; PVT cases are not additional independent samples.
The full four-bench, 27-condition reference with 64 trials produces 6,912 cases,
within the 10,000-case campaign limit. Interactive runs remain limited to 200.
Use fewer conditions/trials for an initial check.

Sampling W/L does not regenerate physical geometry. Rebuild and qualify matching
physical variants before claiming extracted statistical results. A validated PDK
mismatch selection requires recorded model evidence and explicit numeric
parameter mappings; selecting it does not invent a manufacturing distribution.

Create a campaign through the plan window, or use the same saved project in the
source CLI:

```sh
python main.py --cli campaign create two-stage-opamp-statistics.icproj --plan "Two-stage op-amp PVT requirements" --output runs/opamp-statistics
python main.py --cli campaign run runs/opamp-statistics --workers 4 --trust-project
python main.py --cli campaign statistics runs/opamp-statistics
python main.py --cli campaign export runs/opamp-statistics --output runs/opamp-statistics.csv
```

The campaign's **Statistical results…** view reports each PVT condition and the
joint result across all conditions. A trial passes only when every selected test
passes. Missing runs, simulator errors and incomplete measurements remain
unresolved. The pass fraction and 95% Wilson interval are withheld until all
trials resolve; the report still shows bounds from the unresolved outcomes.
Independent-trial intervals do not turn user-declared tolerances into foundry
manufacturing-yield evidence.
The [captured statistical results](validation/dev25/images/statistical-results.png)
show the resolved local workload, including deliberately failing trials.

Campaign input and result identities, worker leases, pause/resume and retries
use the existing durable runner. Separate worker hosts must use matching
source/tools, identical mounted paths and a separately qualified filesystem.
One-host multiprocess execution does not qualify NFS or two-host locking.
Use the [campaign worker acceptance protocol](CAMPAIGN_WORKER_ACCEPTANCE.md) to
capture an actual two-host filesystem and crash-recovery check.

The executed local scheduler reference used ngspice 42 and four workers for
1,152 resistor-divider cases: 128 correlated trials × three temperatures × three
supplies. All cases completed after an abrupt coordinator termination and four
lease retries, preserving the original inputs and rejecting a stale publication
token. The maximum error against the analytical divider ratio was
2.21 × 10⁻¹². Deliberately narrow requirements produced 99 passing and 29 failing
trials, with none unresolved: 77.34% passing, 95% Wilson interval 69.36–83.74%.
This records numerical classification and scheduler behavior for the stated
ideal circuit and user-declared tolerances.
The [retained workload report](validation/dev25/statistical-campaign.json)
records 120.17 seconds of execution (9.59 cases/s) and approximately 103.5 MiB
sampled coordinator-plus-descendant resident memory. These measurements are
specific to this host and circuit; shared memory pages may be counted more than
once. A [final-source smoke](validation/dev25/statistical-campaign-final-source.json)
rechecked 36 cases after additional input guards.

## Measured desktop editing scope

The [retained desktop workload](validation/dev25/desktop-scale.json) ran both
projects three times, measuring 20 stages per iteration with unchanged source.
All checks for selection, view movement, schematic/layout editing, exact
undo/redo, save/reopen and queued recovery passed. The backend was offscreen
Qt 6.8.3 on the recorded Linux host; live layout checks were disabled.

| Workload | Median load | Median schematic edit | Median layout edit | Median pan | Sampled peak RSS |
|---|---|---|---|---|---|
| Three hierarchy levels, 16 reused amplifier fixtures | 232 ms | 137 ms | 206 ms | 46 ms | 203.5 MiB |
| Synthetic 500-device, 10,000-shape project | 3.36 s | 1.70 s | 1.74 s | 97 ms | 314.7 MiB |

Edit timings include the full Studio refresh and synchronous widget repaint.
RSS covers the whole current process, sampled every 20 ms, and can miss brief
allocation peaks. The hierarchical fixture uses generic display geometry; the
large fixture is synthetic. Their screenshots retain the
[hierarchical schematic](validation/dev25/images/scale-hierarchical-analog-schematic.png),
[hierarchical layout](validation/dev25/images/scale-hierarchical-analog-layout.png),
[large schematic](validation/dev25/images/scale-synthetic-large-schematic.png) and
[large layout](validation/dev25/images/scale-synthetic-large-layout.png).

No latency or memory acceptance budget was configured. The passing status
establishes the recorded correctness checks; the approximately 1.7-second large
edit remains a responsiveness gap. Native display/GPU presentation latency,
assistive technology, consumer machines, circuit simulation and process
qualification remain outside this measurement.

To repeat this offscreen source workload with a fresh output directory:

```sh
QT_QPA_PLATFORM=offscreen python tests/gui_analog_scale.py --out build/desktop-scale-check --iterations 3 --display-class offscreen
```

The optional `--max-stage-ms` and `--max-rss-mib` arguments enforce declared
limits. Choose and record those limits before treating a future run as latency
or memory acceptance.

## Qualification and release boundaries

Current source evidence is recorded separately from packaged desktop results.
See [dev25 notes](UPDATE_0.22_DEV25.md), [release status](RELEASE_STATUS.md) and
[release acceptance](RELEASE_FOLLOWUPS.md). Earlier drafts qualify only their own
commits and assets. Consumer machines, actual speakers/displays, physical LAN/VPN
collaboration and separate campaign-worker hosts require their own observations.
The [local engine environment](validation/dev25/local-environment.json) records
the actual executable hashes, wrappers and this host's temporary-file adaptation.
Those host details are part of reproducing the local evidence, not a change to
the application's simulator behavior.
