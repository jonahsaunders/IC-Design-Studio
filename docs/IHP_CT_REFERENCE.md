# Finite IHP center-tapped reference

This adds a three-port reference reader and an independently checked passive
circuit for one published IHP SG13G2 example. It does **not** provide the required
parameterized `inductor3` catalog binding or electrical qualification.

The original [lumpedmodel example](https://github.com/VolkerMuehlhaus/lumpedmodel/tree/e92d2f0a8c7dbf057ae6fb382894dccfa1fb6320/inductor_fit/examples)
is documented upstream as a Palace simulation of a two-turn inductor, with
82.29 µm outer diameter and 4 µm width/spacing. The retained source has 82
frequencies from 10 MHz to 60 GHz and a fitted passive R/L/C/K circuit. Geometry
is a statement in the upstream README; the fixture does not contain authenticated
GDS, the original Palace input or a converged mesh reproduction.

## Source and redistribution

`tests/fixtures/ihp-ct-reference-v1/SOURCE.json` records the commit, original
paths, Git blob IDs, SHA256 values and sizes of all six original files. They are
unmodified apart from local filenames. The source repository supplies GPL
version 3; its full original `LICENSE` and the upstream README are retained,
with attribution and limits in `NOTICES.txt`. Preserve those files when
redistributing this fixture. The separate upstream fitter identifies
Copyright (C) 2026 Volker Muehlhaus and GPL-3.0-or-later; its identity is recorded,
but its implementation is neither copied nor executed here. This fixture does
not relicense the authored reader or unrelated project files.

## Terminal and response semantics

The upstream model declares exactly `p1 p2 ct`. Its substrate branches connect
to global SPICE node `0`. The common return is not an independently excited
fourth body terminal and cannot establish the catalog `LA/LC/LB/B` contract
(where `LC` is the center tap).

`icstudio.three_port_reference.touchstone3` retains all nine complex entries
of an explicit-header, full three-port Touchstone 1.x S file. Supported formats
are RI, MA and DB, with a common positive real reference impedance. Three-port
data uses row order S11, S12, S13, S21, S22, S23, S31, S32, S33, consistent with
the [IBIS Touchstone specification](https://www.ibis.org/touchstone_ver2.1/touchstone_ver2_1.pdf).
Version 2 keywords, partial matrices and nonfinite or incomplete populations
are rejected. The existing one-/two-port importer is separate.

`matrices` converts the full S matrix to Y or Z. `center_tap_impedances` requires
explicit zero-based coil-end and center-tap indices and reports these separate
experiments:

* Differential currents +1 A and −1 A, with center-tap current zero.
* Differential currents +1 A and −1 A, with center-tap voltage zero.
* Balanced end voltages +0.5 V and −0.5 V, with center-tap voltage zero.
* Center-tap excitation with both coil ends grounded.
* Each coil end separately excited with the other ports grounded.

Current-balanced and voltage-balanced experiments differ for an asymmetric
network. Tests use an independently specified asymmetric resistor network with
analytical answers and a nonsymmetric S matrix to catch port transposition.

## Reproduce the finite check

Run the focused suite with the project's Python environment:

```text
python -m unittest discover -s tests -p test_ihp_ct_reference.py -v
```

Use a new output directory. The source-only mode checks the locked originals,
independent Touchstone arithmetic, full mutual-inductance modified nodal
analysis, sampled passivity and reciprocal circuit response:

```text
python scripts/audit_ihp_ct_reference.py --output work/ct-source
```

The native mode executes the retained circuit with three independent AC
voltage excitations. It captures all nine Y entries at all 82 original
frequencies, compares them with independent MNA and converts the result to S.
The engine identity, exact decks, original model bytes, raw logs, tables and
integrity inventory remain in the output:

```text
python scripts/audit_ihp_ct_reference.py --output work/ct-native --ngspice PATH_TO_NGSPICE
python scripts/audit_ihp_ct_reference.py --output work/ct-readback --readback work/ct-native
```

Readback checks require the same authored audit/reader source identities. The
readback mode reports verified native evidence without claiming a fresh run.
It verifies raw files and semantic excitation, current sign, frequency and
circuit responses. It does not authenticate arbitrary third-party execution
claims solely from a self-authored hash manifest.

## Limits and remaining binding inputs

The differences between the rounded printed circuit and full-precision fitted
S data, and between that fit and the original simulated data, are reported as
descriptive errors. They are not calibration uncertainty or an invented
physical acceptance threshold. The frequency grid is not a voltage, current,
temperature, reliability or statistical operating envelope.

Closing the required catalog binding still needs licensed, authoritative
terminal/geometry/parameter semantics, including the independently characterized
body terminal or an explicitly supported restriction of its use; parameterized
behavior rather than this one fixed geometry; physical/extracted matching to
authenticated layout and solver inputs; calibration and uncertainty; and
documented operating/reliability applicability. This reference establishes none
of those missing inputs and does not promote the device matrix or close chunk 7.
