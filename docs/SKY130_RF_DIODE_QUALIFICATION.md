# SKY130 RF diode runtime and sampled electrical qualification

The [execution record](validation/sky130-rf-runtime-2026-10-18.json) covers two
public RF diode candidates, `rf_diode_ps2nw` and `rf_diode_pw2dn`. Chunk 7 remains
in progress. Neither candidate is promoted into the default library. The
subsequent n-well physical checks below cover selected isolated layouts; no
complete RF family, full operating-envelope or measured-silicon qualification
is claimed.

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
are rejected. Electrical dimensions alone do not establish physical validity.

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
Linux 47 runtime pass. Recognition includes known RF calls behind external
wrappers. It does not certify arbitrary renamed third-party model definitions.

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

The [included-library follow-up](validation/sky130-rf-includes-2026-10-18.json)
also checks calls hidden behind nested wrappers and selected `.lib` sections.
Both hosts reproduce the explicit-call currents and reject the incompatible
engine before running the circuit. Original circuit and library bytes remain
unchanged. Inspection records the dependency hashes and uses the external
deck's actual working directory. If a dependency cannot be inspected, the same
runtime proof is required; absence of a recognized call is insufficient.
This conservative check does not certify renamed model definitions, execute
conditional expressions, or establish physical validity.

## Reproduce locally

Use the verified native engine appropriate to the host. Each output directory
must be new; existing results are retained.

```text
python scripts/prepare_sky130_rf_qualification.py --output build/rf-candidate
python scripts/qualify_sky130_rf_branches.py --ngspice ENGINE --output build/rf-branches
python scripts/qualify_sky130_rf_bias.py --ngspice ENGINE --output build/rf-bias
python scripts/qualify_sky130_rf_transient.py --ngspice ENGINE --output build/rf-transient
python scripts/qualify_sky130_rf_application.py --ngspice ENGINE --package build/rf-candidate --output build/rf-application
python scripts/qualify_sky130_rf_programs.py --application build/rf-application --ngspice ENGINE --reject-ngspice INCOMPATIBLE_ENGINE --output build/rf-programs
python scripts/qualify_sky130_rf_includes.py --application build/rf-application --ngspice ENGINE --reject-ngspice INCOMPATIBLE_ENGINE --output build/rf-includes
```

The last command intentionally requires an incompatible engine as a negative
control. Windows CI runs the branch and application checks with the bundled
engine and retains their outputs. Local passing results do not imply that a
pending hosted run or a packaged-release acceptance has passed.

## Remaining work

The RF p-well/deep-n-well topology, its additional substrate junction and full
RF layout coverage remain open. Transient, noise and bias coverage
beyond the sampled checks below, statistical behavior, geometry boundaries and
a documented supported operating envelope need further checks. The default catalog still has seven unavailable
real model entries and nine utility entries. Other required device families and
installed-release acceptance also remain part of chunk 7.

## Sampled reverse-bias current, admittance and noise

The [October 19 execution record](validation/chunk7-ci-rf-bias-2026-10-19.json)
adds an independent nonlinear branch solution. Each host tests both RF models,
three corners, five rectangular area/perimeter pairs and −40, 27 and 125 °C.
Every circuit visits 0, −0.05, −0.1, −0.5, −1 and −5 V junction bias, then returns
to zero without resetting. OP current, complex AC admittance and current-noise
density are checked at 91 frequencies from 10 Hz to 10 GHz. The anode is grounded
and the cathode is driven. These are test points, not published safe voltage or
frequency ratings.

The oracle solves the series resistor/junction equations by bisection, including
temperature-dependent leakage, depletion capacitance and barrier potential.
It propagates each branch's shot noise and resistor thermal noise independently.
The implementation follows the retained public model facts and the simulator's
[diode equations](https://github.com/imr/ngspice/blob/ebdaf58ec76a06ffaac7e0f138360dd1cf5ee4b6/src/spicelib/devices/dio/dioload.c),
[temperature conventions](https://github.com/imr/ngspice/blob/ebdaf58ec76a06ffaac7e0f138360dd1cf5ee4b6/src/spicelib/devices/dio/diotemp.c)
and [noise implementation](https://github.com/imr/ngspice/blob/ebdaf58ec76a06ffaac7e0f138360dd1cf5ee4b6/src/spicelib/devices/dio/dionoise.c).
No fitted model coefficient is changed in a valid case.

Each host passes 90 valid cases and rejects 270 missing-perimeter, doubled-barrier
and doubled-leakage controls. A fault must produce complete, finite results with
the correct stimulus before its numerical mismatch counts as detection. Fault
detection applies to the complete seven-bias sequence; a capacitance fault need
not alter DC current. Acceptance uses 10⁻⁶ relative tolerance with a 10⁻¹⁸ A
current floor and a 10⁻²⁴ A/√Hz noise floor.

Independent raw-file readback verifies 15,120 hashes, 461,160 plot points per host
and 3,913,560 scalar components across Windows 46 and Linux 47. The largest
cross-host relative difference is below 9.8×10⁻¹⁶. An earlier anode-driven pilot
is retained: two tiny reverse-current comparisons exceeded the current floor
because subtracting nearly equal resistor-node voltages lost precision. The
grounded-anode circuit passes the unchanged tolerance. This does not qualify
arbitrary common-mode voltage placement or measured RF/noise accuracy.

## Sampled nonlinear reverse pulses

The [transient record](validation/sky130-rf-transient-2026-10-19.json) checks a
grounded anode with the cathode ramping from 1 V to 1.5 V and back to 1 V.
Both public RF candidates run across the same three corners, three temperatures
and five geometries. Pulse timing follows each circuit's calculated RC constants;
it is not a published device speed rating.

An independent fourth-order Runge–Kutta calculation evolves both junction
voltages using the public voltage-dependent capacitance, leakage and series
resistance. Halving its integration step must change the result by less than
one hundredth of the acceptance budget. Native Gear integration uses two maximum
timesteps, each independently compared at all 833 output points. Both runs must
agree with the oracle and with each other. The current budget is 10⁻⁴ relative
plus 10⁻¹² A absolute; time axes and applied voltage are also checked.

Each host passes 90 conditions at both native refinements (180 valid simulations)
and rejects 270 missing-perimeter, doubled-capacitance and doubled-perimeter-
resistance controls. Complete finite waveforms are required before a fault can
count as detected. Independent readback verifies 900 raw files and 374,850 points
per host; the largest cross-host current difference consumes less than 0.41%
of the comparison budget. The largest valid error consumes less than 55%.

The retained exploratory runs include overly strict solver settings that stalled
and a coarser setting that missed the unchanged accuracy threshold. The accepted
settings pass the independent calculation and timestep refinement. This evidence
qualifies only the tested reverse pulses, not arbitrary solver settings, forward
switching, breakdown, statistical behavior or silicon accuracy. Default catalog
promotion and complete chunk-7 acceptance remain open.

## Bounded n-well physical verification

The [physical execution record](validation/sky130-rf-nwell-layout-2026-10-18.json)
supersedes the earlier unaccepted n-well prototype for its tested scope. The
desktop action **Verify → Physical verification → Verify SKY130 RF n-well diode…** accepts one
rectangular `ps2nw` junction with a continuous contacted substrate ring. It
requires a linked physical SKY130A package and an explicit two-terminal
schematic. An example reference for a 2 × 2 µm junction is:

```spice
.subckt rf_coupon A K
XD A K sky130_fd_pr__model__parasitic__rf_diode_ps2nw area=4 perim=8
.ends rf_coupon
```

The RF marker remains in every exported stream. It must exactly match the
rectangular n-well, implementing the applicable published
[RF marker rules](https://skywater-pdk.readthedocs.io/en/main/rules/periphery.html#rfdiode).
Unknown device masks, additional junctions and unsupported geometry are rejected.
The existing pinned GPL public deck runs all enabled block FEOL, BEOL and grid
groups; its category inventory and source bytes are checked. Complete-chip,
antenna, density and parasitic verification remain separate.

Before device extraction, a separate audit joins only LI, mcon and metal1.
Every tap component must have actual licon contacts reaching exactly its named
metal terminal. Labels, implants, wells and common substrate cannot repair an
open wire in this audit. Missing contacts, disconnected sections, floating metal
and shorts fail. Only after this proof may native device extraction connect the
physical body domains. No native devices are filtered, combined or aligned to
the reference. Native A/K terminals and measured area/perimeter must also agree
with independent metal/mask measurements.

For this single-device topology the final comparator checks the entire flat
graph, exact model, terminal polarity, area and perimeter. It accepts no extra
elements, directives or parameters. Native SI geometry is converted explicitly
to the public RF model's µm²/µm interface; no fitted model values are changed.
This bounded comparison does not substitute for general multi-device LVS.

Six widths/lengths—2×2, 4×2, 2×4, 1×4, 4×4 and 10×10 µm—pass four rotations each.
All 24 layouts survive save/reopen, GDS/OASIS interchange, native DRC and strict
extraction. All 102 deliberate physical/reference faults are rejected. These are
sampled layouts, not a validated continuous geometry or electrical envelope.
Windows backend and both source desktop checks have separately recorded scope;
packaged installation acceptance remains open.

```text
python scripts/qualify_sky130_rf_layouts.py --sky130 LOCKED_PHYSICAL_PACKAGE --klayout KLAYOUT --output build/rf-layouts
```

The qualifier retains every successful and failed report. The default verifier
continues to reject RF markers it cannot preserve; choosing the RF action does
not enable unsupported devices in the default simulation catalog.
