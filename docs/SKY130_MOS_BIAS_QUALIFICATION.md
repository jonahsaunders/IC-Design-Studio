# SKY130 MOS voltage-boundary checks

The [October 21 record](validation/sky130-mos-bias-2026-10-21.json) covers
**33 existing symbol views and 11 public core-MOS models**. It extends the
earlier selected-bias checks to the published gate, drain and body voltage
endpoints. Chunk 7 remains incomplete: these are sampled integration results,
not complete device, reliability, SOA or manufacturing qualification.

## Tested conditions

The complete local Linux batch passes 60 cases: gate, conducting drain, body,
and gate-off extended-drain sweeps at five process selections (`nominal`,
`ss`, `ff`, `sf`, `fs`) and 0/27/85 C. The temperatures are selected test points;
the source does not establish them as the complete temperature-validity range.
Each sweep has 41 coordinates, two existing geometry/finger/multiplicity
points per symbol and two complementary bias contexts.

The 11 models include standard/low-threshold 1.8 V NMOS, standard/low/high-
threshold 1.8 V PMOS, 3.3/5 V native NMOS, and the 5 V gate devices with
10.5 V and 16 V drain variants. The 16 V models are exercised separately at
zero gate voltage. Their conducting drain limits are 11 V for NMOS and 10 V
for PMOS. The public documentation also conditions those models on separate
safe-operating-area limits; this batch does not establish that additional SOA.

The full batch compares 6,300 device instances against independently written
model calls and detects 12,600 instances with deliberately doubled multiplicity
or exchanged gate/drain connections. The final nominal/27 C four-case pilot
passes on both Windows and Linux. Fifteen affected tests pass on each host.

## Independent checks and retained evidence

Application decks use the product's catalog creation and SPICE exporter.
The independent reference writes model names, terminal order and geometry
equations directly. A linear controlled-source fixture drives application
decks; separate behavioral voltage sources drive the references. The checker
reads the actual terminal voltages at every coordinate, checks finite terminal
currents and reference current conservation, and compares currents using
1e-6 relative plus 1e-12 A absolute tolerance. Both faults must be detected on
every tested instance. Fault circuits may intentionally exceed valid bias;
they are rejection controls, not extra valid operating points.

`input.icproj` preserves the catalog-device fixture. The exported `input.cir`
also contains the explicit sweep-scaling sources and is the executable testbench.
This batch tests exported bindings; it does not assert that the saved schematic
alone contains the complete stimulus or establish installed-desktop acceptance.

Independent Windows and Linux audits recompute the final full/pilot results
from 272 raw files: 7,140 valid device comparisons and 14,280 faulted instances.
They verify the complete declared condition matrix and numeric limits against
the original public documentation. The initial runner cited the wrong line
range for the NMOS extended-drain paragraph; its numeric limits were correct.
The final runner corrects only that citation. Both versions and the explicit
byte comparison are retained, and final pilots use the corrected runner.

The original source and [source lock](qualification/sky130-mos-bias-sources-v1/source-lock.json)
are retained under their original Apache-2.0 license. Numerical acceptance
thresholds are unchanged. The validation record identifies the deduplicated
archive, independent audits and restored-source replay.

## Reproduction

Use the locked simulator and package revision identified by the validation
record. Run from the repository root with a new output directory:

```sh
python -m unittest tests.test_sky130_mos_bias tests.test_mos_variants tests.test_mos_boundaries -v
python scripts/qualify_sky130_mos_bias.py --ngspice /path/to/ngspice --output /path/to/new-results --workers 4
```

Add `--pilot` for the four nominal/27 C cases. The regular Linux physical and
Windows desktop workflows run that pilot and retain its evidence. A pilot is
not the complete five-corner matrix; newly configured CI remains pending until
its own run succeeds.

## Remaining scope

Complete geometry/temperature ranges, independent silicon accuracy, continuous
operating limits, SOA/reliability and broader physical/extracted-connectivity
coverage remain open. This batch does not cover the separate ESD or 20 V
models, resolve the seven unavailable real-device catalog bindings, or complete
GF180/IHP device qualification. All existing partial device statuses remain
partial in the [qualification matrix](qualification/pdk-matrix.json).
