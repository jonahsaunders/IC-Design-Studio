# IHP CMIM parallel saved-testbench graph

The ordinary saved-testbench capacitance flow now accepts flat parallel
`cap_cmim` catalog units with the same ordered top and bottom electrodes.
Previously it rejected an ordinary `m=2` device before extraction, even though
the physical multiplicity flow already supported the corresponding two units.
The [2026-11-07 record](validation/ihp-cmim-parallel-2026-11-07.json) retains the
reproduction, final source identities and bounded native results.

The checker regenerates each ordinary device's source declaration and binds its
instance name, dimensions, multiplicity, mismatch flag and terminal order to the
captured schematic. It compares an exact width/length/count multiset against
every raw intrinsic device and both native exports. It rejects duplicate raw
locations (including alternate numeric spellings), duplicate instance names,
missing or extra devices, changed dimensions, reversed electrodes and unknown
records. Equal area does not substitute for equal width and length. Integer
multiplicity represents a physical count in this checker; it introduces no
new model-validity or operating limit.

The complete raw capacitance graph must agree with the selected flat native
export. The older hierarchical writer still assigns top-to-substrate
capacitance to the bottom electrode. Its original output is retained alongside
the corrected native export. Single-unit schema 1 fields and values remain
unchanged; parallel evidence uses schema 2 and an explicit list
of intrinsic dimension/count groups.

The final native experiment used the existing complete contacted two-unit
7 × 7 µm masks, an ordinary `m=2` source and two explicit `m=1` sources, at 0° and
90°. All four saved-bench runs passed Magic DRC, Netgen LVS, graph comparison,
ngspice post-layout simulation and final integrity checks. Incorrect source
counts of one and three, and an incorrect source width, failed native LVS and
did not proceed to capacitance extraction. The independent reader verified
836 evidence files, both intrinsic units, all three capacitance edges and twelve
actual complex AC samples. The maximum relative current error against the
independently solved finite linear circuit was `8.056106524566877e-9`.

These are nominal-corner, 27 °C, finite 100 kHz–1 MHz source integration results.
Internal `SUB` remains floating, and the native singular-matrix/stepping warnings
are retained. No ground, leakage path or substitute operating point was added.
The work establishes neither a unique physical DC operating point nor calibrated
parasitic capacitance. General hierarchy, aliasing, mixed devices, arbitrary
layout arrays, contact/enclosure coverage, operating limits, statistical
validation and installed parallel acceptance remain outside this evidence.
The [full requirements](IHP_CMIM_REQUIREMENTS.md) and existing device gate remain
unchanged; the historical [single-unit evidence](IHP_CMIM_SAVED_BENCH.md) keeps its
original scope.

Reproduce from a verified source snapshot on native Linux storage with the
pinned runtime on `PATH`:

```text
python scripts/qualify_ihp_cmim_parallel.py --output /var/tmp/new-cmim-parallel-evidence
python -m unittest tests.test_ihp_cmim_capacitance tests.test_ihp_cmim_parallel
```

The producer uses a fresh output directory and preserves the original project,
schematic, all native outputs and file hashes. The independent reader checks the
complete evidence inventory, recorded application/helper identities, pinned PDK
semantic identity and package bytes, actual project-to-source agreement and raw
native results. The small native regression fixture retains its source identity
and applicable Apache-2.0 notice; no new upstream model or generator body is
imported.
