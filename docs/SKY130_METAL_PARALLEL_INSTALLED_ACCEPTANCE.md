# Installed SKY130 physical parallel resistor workflow

This gate exercises the packaged application's physical parallel arrays for
the five public LI/M1–M4 resistor models. It supplements the existing straight
resistor, MiM and desktop release gates. It does not qualify complete device
families, operating limits, silicon behavior or foundry signoff.

The frozen [contract](qualification/sky130-metal-parallel-installed-v1.json)
requires 30 fresh layouts: all five models, physical counts 2, 3 and 16, and
rotations 0 and 90 degrees, at 2 × 5 µm per unit. Every positive case must be
exported by the actual application, checked with native DRC and strict LVS,
and round-tripped through both GDS and OASIS. The native extraction must retain
exactly the requested number of physical units and their two terminal nets.

Separate routed editing checks exercise counts 3, 16, 2 and 1 for each model.
The gate checks the actual preview, application, undo, redo and reopened file,
including both attached wires and stable terminal identities. A late layer
lock must block each model's edit. Five last-unit width defects, one DRC
defect, six fresh repairs and a missing-engine block give 43 queued requests
and 42 native executions. Passing an older result cannot satisfy a fresh job.

Electrical acceptance consumes the actual application netlist and actual
native extraction from every positive GUI case. Only the top-cell name is
normalized, with the original bytes and each replacement span retained. Each
complete array is instantiated once; the producer does not regenerate units
or multiply an already parallel array a second time. All 30 contexts run DC
and AC at TT, 27 °C using the pinned platform engine, for 60 native simulator
runs and 3,870 application/extracted/analytical path samples. Analytical
response, measured currents, Kirchhoff's current law, public coefficients,
the full sample grids and execution identities are checked independently.

The two platform profiles retain the previously reviewed ngspice 42 Linux and
ngspice 46 Windows executables. Original package files, staged model files,
runtime dependencies, actual inputs, execution logs, source hashes and raw
results are captured and checked before and after execution. A fresh raw
audit must agree with the saved audit; the aggregate then joins that audit
to the exact GUI execution and selected immutable Git commit.

The selected desktop workflow runs the new gate on both platforms. For Linux:

```text
python scripts/verify_frozen_metal_parallel.py --executable dist/ICDesignStudio/ICDesignStudio --physical-pdk build/physical-adapter/sky130A --expected-commit FULL_COMMIT_SHA --out build/frozen-metal-parallel-evidence
python scripts/qualify_installed_metal_parallel.py --gui-root build/frozen-metal-parallel-evidence --expected-commit FULL_COMMIT_SHA --out build/frozen-metal-parallel-electrical-evidence
python scripts/verify_installed_metal_parallel.py --gui build/frozen-metal-parallel-evidence --electrical build/frozen-metal-parallel-electrical-evidence --expected-commit FULL_COMMIT_SHA --out build/frozen-metal-parallel-workflow-evidence/acceptance.json
```

Windows uses the same checkers against the installed executable before
uninstallation. The Windows receipt and both diagnostic uploads retain the
new gate alongside every prior gate. Source pilots are explicitly marked;
they cannot produce installed acceptance. Daily feedback covers the bounded
contract and substitution checks, while complete Qt lifecycle discovery and
native physical execution remain required in exhaustive acceptance.

The [October 26 source rehearsal](validation/sky130-metal-parallel-installed-source-2026-10-26.json)
passes all 30 GUI/native arrays, 20 routed transitions and 60 electrical runs.
Independent readback rejects all 31 rehashed component corruptions. Both
582-test feedback lanes and complete 3,759-test Linux discovery pass. The
verified archive restores 4,233 GUI/electrical files at their original paths
and reproduces both independent audits. These are source results; fresh
packaged Windows/Linux execution of this additive gate remains pending.

The contract's selected geometry and TT electrical condition are finite.
Complete operating ranges, other physical classes, reliability/calibration
requirements and full-family acceptance remain separate chunk-7 work. The
existing [source-array milestone](SKY130_METAL_RESISTOR_PARALLEL.md) retains its
own original candidate and evidence; this new gate does not relabel it.
