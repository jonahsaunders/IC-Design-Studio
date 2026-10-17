# Standard MOS boundary checks

The runner exercises eight standard transistor views across SKY130A, GF180MCU
C/D and IHP SG13G2. It samples independently driven gate, drain and body
voltages at multiple geometries, temperatures and the three generic process
corners. Each result compares all four terminal currents with a separately
written SPICE instance and checks charge conservation. Re-reading the simulator
files verifies the saved comparisons. Both deliberate terminal swaps and wrong
parallel multiplicity must produce a measurable mismatch for every device.

The [2026-10-17 acceptance record](validation/mos-boundaries-2026-10-17.json)
contains 216 passing Linux/WSL cases across all four packages and 162 passing
native Windows cases for SKY130/GF180 C/D. Together they check 16,848 device
comparisons, 67,392 terminal-current vectors and 2,763,072 samples, with all
33,696 deliberately faulted device instances detected. A separate audit
recomputes the comparisons from all 1,512 raw simulator files. Seventeen
focused regression tests pass on each host. The 24-case Linux pilot and the
aborted first Windows launch are retained separately; neither counts toward
the 378 completed cases.

The source facts and selected test points have different scopes:

| Target | Published source facts used | Additional selected points |
|---|---|---|
| SKY130A | N/P gate and drain model limits of 1.95 V in magnitude; asymmetric forward-body and reverse-body limits; five sizes from the union of N/P characterization tables | 0, 27 and 85 C; the union of sizes is tested on both polarities |
| GF180 C/D | All 16 measured width/length pairs in the 3.3 V table, including 0.22 micrometre width and 10 micrometre length; characterization at -40, 25 and 125 C | Gate/drain sweeps through nominal 3.3 V; reverse-body bias through 0.3 V |
| IHP | Width 0.15–10 micrometres, length 0.13–10 micrometres, maximum drain-source voltage 1.5 V, measurement at 27 C | Gate through nominal 1.2 V, reverse-body bias through 0.3 V, and 0/85 C |

These are sampled application/model integration checks. They do not establish
continuous-range accuracy, reliability ratings, silicon calibration or physical
layout acceptance. Model geometry bounds do not automatically permit those
dimensions in the application's layout generator. Mixed, statistical and
device-specific process corners remain separate work.

The source snapshots retain their original Apache-2.0 licenses and are listed
with exact revisions and hashes in
[sources.json](qualification/mos-boundary-sources-v1/sources.json). The IHP
source remains the package's hash-locked `cornerMOSlv.lib` header. The runner
rejects changed documentation or model sources before execution.

Run from the repository root, choosing a new output directory:

```sh
python scripts/qualify_mos_boundaries.py --output /path/to/new-results --ngspice /path/to/ngspice --osdi /path/to/ihp-osdi --workers 4
```

`--pilot` runs only the nominal corner at 27 C and is recorded as a pilot. It
cannot stand in for the complete batch. `--targets` can select individual
packages. Native Windows without IHP OSDI libraries can select `sky130A
gf180mcuC gf180mcuD`; the complete IHP batch uses the local Linux/WSL engine.
The respective ngspice 42 and corrected ngspice 47 results are separate
acceptances, not proof that the engines are interchangeable.

The runner preserves projects, circuit decks, model inputs, raw vectors,
source identities and per-case fault results. Completed evidence can be stored
in a verified content-addressed archive to avoid retaining repeated model
copies. A source, model, executable or operating-condition change requires
review of the affected checks.
