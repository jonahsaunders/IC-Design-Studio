# IHP capacitor saved-testbench verification

The ordinary catalog `cap_cmim` saved-testbench path needs a separate physical
comparison reference and a checked capacitance export. The original simulation
netlist remains unchanged. These checks address application integration; they
do not qualify the complete capacitor family or establish physical calibration.

The November 7 [parallel-network extension](IHP_CMIM_PARALLEL.md) adds ordinary
integer multiplicity and explicit parallel units with the same ordered
electrodes. It checks each width/length/count group and the complete native
graph. The single-unit evidence and numerical limits recorded below retain
their original scope; they are not evidence for the later extension.

## Simulation and LVS references

The catalog emits an X instance with ordered electrodes, dimensions, multiplicity
and the simulation selector `mm_ok`. Magic's extracted physical instance has no
`mm_ok` property. Passing the simulation reference directly to Netgen therefore
fails even for matching geometry.

Saved-testbench verification uses the existing source-bound Magic reference
projection. It retains `schematic.spice` for schematic simulation and creates
`schematic-lvs.spice` only for LVS. The separate receipt identifies both files
and the locked symbol/model evidence. Dimensions, multiplicity and electrode
order remain meaningful comparison inputs. Unknown parameters, altered source
files and nonliteral geometry are rejected. The comparison is rederived after
Netgen, and both references and the receipt belong to the final integrity check.

## Preserving the parasitic network

The tested Magic hierarchical exporter incorrectly moves a capacitor's
top-plate-to-substrate capacitance onto the bottom plate. On the retained
7 × 7 micrometre example, the raw extraction contains these three edges:

| Connection | Raw capacitance |
| --- | ---: |
| Top plate to substrate | 944.474 aF |
| Bottom plate to substrate | 1382.71 aF |
| Top plate to bottom plate | 476.219 aF |

The original hierarchical export instead combines the first two terms at the
bottom plate. A successful simulator exit does not detect this topology error.

The guarded path retains that original export and requests a separate flat
export from the same native extraction. Before selecting it for simulation,
the application checks the raw capacitance graph, intrinsic device, ordered
interface, source dimensions and native serialization. A flat writer is not
assumed correct for every device: other native device representations have
separate limitations. The initial boundary is one ordinary, flat, two-terminal
IHP `cap_cmim` instance with `m=1` and the unmodified shipped package
configuration. Every positive extracted edge must be at least 1 aF: the pinned
writer cannot preserve smaller positive edges. Mixed devices, hierarchy, aliases
and other unsupported CMIM arrangements fail before post-layout simulation.
General arrays and distributed resistance retain their separate qualification gates.

## Substrate and numerical scope

The selected two-port layout has an internal floating substrate node. The
application does not rename it to ground, add a leakage resistor, or add a
hidden third port. Its linear AC response includes the series contribution of
both substrate capacitances as well as the direct electrode coupling.

The original native simulator logs contain floating-node convergence warnings
followed by transient operating-point recovery. Agreement with the explicitly
floating linear AC network does not establish a unique physical DC operating
point. An actual grounded substrate requires its intended physical connection.
Separately labelled diagnostic circuits with an added leakage path do not
replace the application's unchanged boundary condition.

Raw-to-export capacitance rounding and simulator error are checked separately.
Agreement with the written native graph is numerical integration evidence,
not measured device accuracy, a calibrated field solution, an operating-voltage
rating or a lifetime guarantee. The [family checklist](IHP_CMIM_REQUIREMENTS.md)
and [progress tracker](QUALIFICATION_PROGRESS.md) keep those requirements open.

## Recorded source acceptance

The [validation record](validation/ihp-cmim-saved-bench-2026-11-03.json) identifies
both completed native rotations, wrong-width/wiring controls, independent raw
network and AC readback, Windows/Linux regression results and compact recovery
archives. It also verifies a real Windows-to-WSL source dispatch with the same
staged inputs. That diagnostic invokes dispatch directly while retaining an
old setup receipt; it does not establish normal GUI readiness or installed
acceptance. The contemporaneous desktop candidate predated this source repair.

## Included model handoff

The [reviewed follow-up](validation/ihp-managed-physical-handoff-2026-11-03.json)
selects the matching included IHP models for physical saved-testbench
simulation. It preserves explicit model selections and the physical job
route; DRC/LVS-only jobs do not gain a simulation-model requirement.
Focused Windows and native Linux checks pass. The subsequent
[ordinary source acceptance](validation/ihp-cmim-managed-saved-bench-2026-11-04.json)
passes real setup and unconfigured GUI verification for the bounded example;
installed acceptance remains separate. The earlier failure and configured control
remain separate evidence. Electrical saved-testbench and characterization
actions still require their separately configured local tools and models.

The [boundary correction](validation/ihp-managed-handoff-boundary-2026-11-03.json)
requires a selected saved testbench before automatic IHP model lookup. Plain
asset transfers retain their original source-integrity checks without needing
an installed simulation runtime. Both hosted regression failures and the
subsequent focused correction checks are retained separately.

The ordinary acceptance binds all 470 application backend files and three
additional captured inputs to `995bbcac`. Both default and explicit-control
jobs pass all eight stages with exact model, layout and graph readback. A
separate native Windows rendering check shows readable results with ordinary
scrolling; it uses hidden real widgets rather than an interactive session.
The floating-substrate, explicit-path and finite AC limitations above remain.
