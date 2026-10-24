# Windows simulation and SKY130 RF candidate checks

The Windows runtime is pinned to the unmodified official **ngspice 46 console
distribution**. The previous version 42 changes explicit diode geometry across
repeated analyses: a successful operating point can be followed by incorrect
DC/AC results. This was reproduced with independent diode equations and retained
as a failing control. Inserting `reset` would change users' control programs;
the application instead replaces the bundled executable and preserves those
programs and their PDK model equations.

The [execution record](validation/windows-simulation-and-rf-2026-10-18.json)
identifies the exact tested source, engines, successful checks, failed diagnostic
attempts, platform skips and retained evidence. It does not complete chunk 7,
qualify every simulator feature, or establish installed-release acceptance.

## Source and redistribution

The [official Windows archive](https://sourceforge.net/projects/ngspice/files/ng-spice-rework/old-releases/46/ngspice-46_64.7z/download)
has SHA-256 `7ed713cd8d401db724ffe99087c3122bf05a9cfa99de02c6eeed44ee44785a33`.
Its console executable has SHA-256
`86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453`.
The stager checks the archive before extraction and records all installed file
hashes. Original COPYING terms remain included; third-party components keep
their upstream licenses. Historical evidence retains the version 42 identity.
No private model package or remote signoff service is used.

## Independent runtime checks

`scripts/verify_ngspice_diode_sequences.py` checks a fully specified level-3
diode model with independent analytical current/admittance calculations:

- Operating point and a five-point forward DC sweep.
- Six sixteen-point AC sweeps, including repeated analyses after OP and DC.
- Independent AREA, PJ and M changes, with both single and parallel devices.
- Complete axes, terminal stimulus, finite samples and current signs.

Every current must agree within `1e-18 A + 1e-6 × |expected|`. Thermal voltage
uses the constants declared in the
[engine source](https://github.com/imr/ngspice/blob/ngspice-46/src/include/ngspice/const.h);
substituting the newer exact SI constants produces a measurable 2.6 ppm
difference at 0.2 V. The first diagnostic using those different constants is
retained as a failed checker attempt. Fault tests reject collapsed geometry,
missing multiplicity/sidewall response, stale results after alteration,
nonfinite data, truncated sweeps and incorrect stimuli.

The existing nonlinear-capacitor checker independently verifies literal,
scientific, parameter and expression multipliers, nested instances and charge
syntax at three biases. Windows 46 passes both checkers; corrected Linux 47
passes the same diode sequence. Windows 42 fails the diode sequence. The
Windows build runs both checkers before packaging and retains their outputs.

```sh
python scripts/verify_ngspice_diode_sequences.py --ngspice /path/to/ngspice --output /path/to/new-diode-check
python scripts/verify_ngspice_capacitors.py --ngspice /path/to/ngspice --output /path/to/new-capacitor-check
```

## Separate RF candidate

The two public SKY130 RF diode wrappers contain an area branch and a perimeter
branch, but omit the perimeter argument on the latter. An explicit candidate
preserves all four Apache-2.0 originals and adds `PJ={perim}` only to the two
derivative perimeter branches. Its application bindings use subcircuit calls
with area/perimeter computed from positive rectangular width and length.

Independent zero-bias branch admittance agrees for both models, three process
corners and five area/perimeter pairs on Windows 46 and corrected Linux 47.
All 90 missing-perimeter, wrong-area and wrong-series-resistance cases per host
are rejected. Repeating AC after DC preserves the result. Independent readback
compares 85,200 complex values across hosts and verifies the raw-file hashes.

Both application paths also pass save/reopen and two rotated export round trips
for the two candidate entries, plus six-device nominal DC/AC comparisons and
twelve deliberately faulty device instances per host. These results validate
the explicit candidate's selected interfaces and equations. They do not prove
measured RF accuracy, physical layout/extraction, full bias/temperature/geometry
ranges or safe execution with older simulators. The candidate is not promoted
to the default catalog; seven real model entries therefore remain unavailable.

## Repository regressions

The GF180 high-voltage action now belongs to **Verify → Physical verification**.
The earlier omission from the menu map put it directly in a general menu and
failed hosted interoperability checks. Both actual source desktops pass the
repaired menu test and retain working GF180 verification actions.

A separate real Windows installation check exposed long PDK asset paths. The
registry uses extended paths for filesystem operations while preserving normal
portable paths in package metadata and simulation decks. Real long-path tests
cover installation, reopening, model staging, tamper rejection, recoverable
removal and failed-copy cleanup; escaping the package remains rejected. This
requires no Windows configuration change or administrator privileges. The
record distinguishes the full runtime regression from subsequent focused
validation of this path repair.
