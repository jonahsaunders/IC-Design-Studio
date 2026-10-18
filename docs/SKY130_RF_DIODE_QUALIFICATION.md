# SKY130 RF diode runtime and sampled electrical qualification

The [execution record](validation/sky130-rf-runtime-2026-10-18.json) covers two
public RF diode candidates, `rf_diode_ps2nw` and `rf_diode_pw2dn`. Chunk 7 remains
in progress. Neither candidate is promoted into the default library, and no
physical, full operating-envelope or measured-silicon qualification is claimed.

## Public sources and explicit correction

Four public Apache-2.0 model originals, their license and exact upstream
identities are retained under `icstudio/assets/qualification/sky130-rf`.
The [source lock](../icstudio/assets/qualification/sky130-rf/source-lock.json)
contains portable paths and hashes. The candidate builder preserves all original
assets in the current SKY130 package. It adds separate derivative wrappers that
pass `PJ={perim}` to the perimeter branch, whose public wrapper omitted it.
No fitted parameter, primitive model equation or process corner is replaced.

Both devices use an explicit two-terminal `X` call: `d0` maps to the public `c0`
anode, and `d1` to the `c1` cathode. Positive rectangular W/L are in micrometres.
Area is W×L and perimeter is 2×(W+L); direct overrides of these computed values
are rejected. These dimensions do not establish a physical layout recipe.

## Automatic runtime requirement

The application recognizes these explicit RF subcircuit calls in graphical
decks, captured native circuits, saved programs and explicit testbenches. Before
execution it runs a separate analytical level-3 diode circuit using the actual
selected engine. The checks cover OP, DC, repeated AC and explicit AREA/PJ/M
alterations. A passing result must also use the unscaled AREA/PJ convention.
The user's circuit, model bytes and analysis order remain unchanged.

Each invocation keeps its probe inputs, raw results, engine identity and
acceptance report. It reruns the check rather than relying on a cached version
number. Actual ngspice 42 controls are rejected through all three execution
routes on Windows and Linux. The verified Windows 46 runtime and corrected
Linux 47 runtime pass. This recognition applies to explicit known RF calls;
it is not a recursive certification of arbitrary renamed subcircuits hidden
inside third-party external libraries.

## Executed checks

Each host executes 360 independent branch cases: two models, three corners,
five area/perimeter pairs and three temperatures (−40, 27 and 125 °C), with
one correct model and three intentional faults per combination. All 90 valid
cases match analytical complex admittance at 71 frequencies from 1 kHz to
10 GHz, before and after a DC analysis. All 270 missing-perimeter, wrong-area
and wrong-resistance cases are rejected. The tolerance is 10⁻¹⁸ A plus 10⁻⁶ of
the expected current; it is unchanged from the earlier nominal-temperature
review. Temperature conventions follow the public model definitions and
[ngspice's implementation](https://github.com/imr/ngspice/blob/ngspice-46/src/spicelib/devices/dio/diotemp.c).

The application qualifier separately checks save/reopen and export/reimport
for both entries, six device geometries against independent explicit calls,
and twelve polarity/width faults per host. Both hosts build the identical
portable candidate. Saved-program checks preserve OP→AC→DC→AC order and compare
the resulting currents with independently executed application references.
All automatic runtime checks and actual incompatible-engine controls pass.

## Reproduce locally

Use the verified native engine appropriate to the host. Each output directory
must be new; existing results are retained.

```text
python scripts/prepare_sky130_rf_qualification.py --output build/rf-candidate
python scripts/qualify_sky130_rf_branches.py --ngspice ENGINE --output build/rf-branches
python scripts/qualify_sky130_rf_application.py --ngspice ENGINE --package build/rf-candidate --output build/rf-application
python scripts/qualify_sky130_rf_programs.py --application build/rf-application --ngspice ENGINE --reject-ngspice INCOMPATIBLE_ENGINE --output build/rf-programs
```

The last command intentionally requires an incompatible engine as a negative
control. Windows CI runs the branch and application checks with the bundled
engine and retains their outputs. Local passing results do not imply that a
pending hosted run or a packaged-release acceptance has passed.

## Remaining work

The RF marker, well topology, contacts and strict extracted connectivity still
need a qualified physical route. Bias-dependent capacitance, transient/noise,
statistical behavior, geometry boundaries and a documented supported operating
envelope need further checks. The default catalog still has seven unavailable
real model entries and nine utility entries. Other required device families and
installed-release acceptance also remain part of chunk 7.
