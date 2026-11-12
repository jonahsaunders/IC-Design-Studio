# IHP L2n0 measured reference

`tests/fixtures/ihp-l2n0-reference-v1` retains eight unmodified files from
[IHP Open PDK revision 9439837](https://github.com/IHP-GmbH/IHP-Open-PDK/tree/943983786b04351feb20e33e8d3d76c0e0d87cce/ihp-sg13g2/libs.tech/openems/testcase/SG13_Octagon_L2n0):
two measured two-port responses, their upstream one-port exports, the original
and simplified layouts, the upstream guide and Apache-2.0 license. `SOURCE.json`
binds original paths, byte counts, Git blob identities and SHA-256 hashes.
The guide is renamed `UPSTREAM.md`; all file contents and notices are unchanged.
The [EM Reference Suite](https://github.com/milanofthe/em-reference-suite/tree/0885e604e9af168e3a44e81626b3b127362787d9/cases/ihp_sg13g2_l2n0)
provided the discovery lead; these files were retrieved directly from IHP.

This adds a two-turn measurement reference alongside the existing four-turn
L6n2 reference. It does not supply the missing parameterized `inductor` or
`inductor3` catalog binding. No new solver run, measurement uncertainty,
operating envelope or full-device acceptance is claimed.

Run the source and arithmetic audit, optionally including application import,
save/reopen and both GDS/OASIS exports:

```sh
python scripts/audit_ihp_l2n0_reference.py --output new-audit.json --exchange-output new-exchange
python -m unittest tests.test_ihp_l2n0_reference tests.test_ihp_measured_reference tests.test_ci_feedback -v
```

Use new output paths. The audit verifies the source manifest before and after
execution. It compares the application parser with independent complex matrix
conversion, reads each original layout with KLayout, and checks every exported
mask and label independently. Regression controls reject changed measurements,
a missing license, rebinding altered files to a new manifest, phase-only parser
errors and a removed via. Fast feedback binds all nine fixture files and runs
the new controls without reducing its existing selection or deadlines.

Each two-port measurement has 201 frequencies from 100 MHz to approximately
50 GHz. Derived differential metrics from the raw data are:

| Die | R at 1 GHz (ohm) | L at 1 GHz (nH) | Peak Q | First self-resonance (GHz) |
| --- | ---: | ---: | ---: | ---: |
| x2y7 | 1.6134 | 1.6743 | 23.518 | 25.565 |
| x5y8 | 1.5944 | 1.6719 | 23.112 | 25.417 |

Peak Q is the largest positive inductive sample below the first resonance,
near 9.052 GHz. Resistance and inductance use linear interpolation of complex
impedance; resonance interpolates the first positive-to-negative imaginary
impedance crossing. These are descriptive observations, not acceptance limits
or a statistical characterization from two dies.

Keep these limitations visible:

- The upstream one-port exports use a different frequency grid. Their maximum
  complex-impedance differences from linear interpolation of the two-port data
  are about 43.7% and 33.9%, respectively, over their common band. This comparison
  has no established equivalence tolerance and includes resonance interpolation.
  Both raw forms remain available; the audit does not silently replace either.
- The original layout has 144 TopVia2 polygons; the simplified view has four.
  Both are preserved and exchanged separately. A solver must explicitly justify
  any via simplification and its effective conductivity.
- The single-ended ground reference, measured die substrate/backside conditions,
  de-embedding standards, uncertainty budget and full temperature/geometry
  applicability are not established by this reference import.

Source/import acceptance remains separate from fresh field-solver reproduction,
installed acceptance and full chunk-7 qualification. The catalog and matrix
statuses are unchanged.

The [November 7 validation record](validation/ihp-l2n0-reference-2026-11-07.json)
retains both complete audits and raw exchanges. All 30 affected tests pass on
Windows (one existing directory-symlink skip) and native Linux (no skips).
All 7,019 snapshot files remain unchanged during each run. Source execution
takes 8.406 seconds on Windows and 2.301 seconds on Linux, excluding preparation.
