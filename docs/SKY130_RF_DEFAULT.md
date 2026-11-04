# Default SKY130 RF n-well diode binding

New SKY130 projects use revision `b26f7f28e659ddc1`. The source-listed
`rf_diode_ps2nw` choice now has a usable two-terminal simulation binding. This
removes one missing default binding; it does not complete RF device qualification
or chunk 7. The default catalog has 287 available partial entries, six unavailable
real-device bindings and nine utilities.

The [execution record](validation/sky130-rf-default-2026-10-23.json) records the
checks and their source identities. The previous
[RF candidate evidence](SKY130_RF_DIODE_QUALIFICATION.md) keeps its original
package, source and sampled scope.

## Model and project behavior

The binding preserves the Apache-2.0 public model originals and license. A
separate, identified derivative adds the missing `PJ={perim}` argument to the
perimeter branch, exactly as in the previously tested candidate. No fitted
coefficient, primitive equation or corner is changed. The application's
integration remains under the project's GPL-3.0-or-later license.

`d0` is the anode and `d1` the cathode. Positive rectangular W/L are entered in
micrometres; the application derives area W×L and perimeter 2×(W+L). Direct area,
perimeter or multiplicity overrides are rejected. The automatic engine check
still runs before every simulation and rejects incompatible AREA/PJ/history
behavior. These sampled electrical dimensions are not physical validity or safe
operating ratings.

The new version adds assets and changes only this catalog binding and its model
include. Older assets and the previous manifest remain recoverable. Saved
projects retain their registered versions; there is no automatic migration.
The original two-model candidate can still be rebuilt byte-identically.

The `rf_diode_pw2dn` candidate remains unavailable in the default. Its additional
substrate/isolation behavior needs an electrical model; the existing three-terminal
geometry checks do not supply one.

## Executed integration checks

Fresh default-project installation is exercised with three geometries, nominal/
slow/fast corners and −40/27/125 °C. On each host, all eighteen independent DC/AC
comparisons pass, all 54 wrong-polarity or wrong-width instances are detected,
and all 54 automatic runtime proofs pass. Independent raw readback checks 54
native files and 1,512 current samples per host; Windows and Linux values match.
Saved OP→AC→DC→AC programs pass, and incompatible engines are rejected through
graphical, saved-program and external-deck routes.

All 302 catalog entries undergo save/reopen/export/import checks on both hosts:
287 available entries pass and fifteen unavailable/utility entries retain their
expected rejection. Final-source pilots and full-suite outcomes are recorded
separately in the execution record. Both hosted workflows now require the new
default integration check and retain its output.

```text
python scripts/qualify_sky130_rf_default.py --ngspice ENGINE --output build/rf-default
python scripts/qualify_sky130_rf_programs.py --application build/rf-default/application --ngspice ENGINE --reject-ngspice INCOMPATIBLE_ENGINE --output build/rf-default-programs
```

## Public capacitor regression found during acceptance

The hosted public-layout job exposed a regression in the new MiM orientation
adapter. It rejected a symmetric four-sided contact surround in the comparator
and collinear end contacts in the amplifier. The correction recognizes end
contacts touching the plate's end lines. A complete surround symmetric about
both plate axes explicitly retains native global X/Y dimensions: it has no unique
contact direction from which to infer a PCell orientation.

Asymmetric surrounds, missing contacts, ambiguous corners, wrong native sizes
and shared bottom electrodes remain rejected. The surround exception does not
qualify its distributed resistance or parasitic model. Strict native DRC/LVS and
the original reference dimensions remain unchanged.

All thirteen affected hosted physical routes replay locally with the expected
results. The original amplifier capacitor-polarity defect remains a required
LVS failure; its explicit corrected reference passes. Both narrow-metal and
wrong-device-width controls are detected. The original hosted failure archive
is retained. This is local reproduction and repair, not a fresh hosted pass.

Full operating envelopes, statistical and measured RF accuracy, substrate
parasitics, remaining models and final installed-release acceptance remain open.
