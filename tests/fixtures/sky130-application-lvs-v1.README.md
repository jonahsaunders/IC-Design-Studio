# Actual application LVS evidence

`sky130-application-lvs-v1.zip` is a partial capture of a real filled counter
Finish run and one deliberate removed-gate fault. It tests the portable saved
comparison validator; it is not a complete job or process qualification record.
`fixture.json` binds the original input/result and capture driver identities.
`data.json` records every retained artifact hash. The failure control is an
actual native comparison database, not a fabricated PASS/FAIL response.

SKY130 HD cells, CDL and independent diode references retain Apache-2.0 terms.
The extraction source by laurentc2 retains BSD-2-Clause terms. The original
checker, license and source lock are included with the checked artifacts;
Studio adapters, drivers and reference design remain GPL-3.0-or-later. The
archive also retains the project license and third-party notices. See
[the application execution record](../../docs/validation/sky130-application-lvs-2026-10-16.json)
for the fresh flow, fault and export evidence.

Run `python -m unittest tests.test_sky130_application_lvs` with the normal project
dependencies. These tests reopen the native comparison graph and recompute
reference/label transformations without requiring an OpenROAD executable.
