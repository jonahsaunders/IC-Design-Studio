# IC Design Studio 0.22.0.dev25 — analog reference and release qualification

This source preview follows the [integrated analog workflow](ANALOG_CLOSURE.md)
merged into `experimental` at `46658f81b378743f39bbc10d4c83c5b8ceb583d1`.
Dev25 and its Windows follow-up were merged into `experimental` in PRs #34/#35;
PR #32 then merged the same tree into `main` at
`a88cfe1cfe20254638b7bd97ec9128e843578282`.
It retains saved extraction choices, checked process-device semantics, constrained
layout updates and durable verification campaigns. The digital implementation
workspace and offline eight-preset VGA Playground remain included.

## Reference diagnostics and repeated verification

The [reference workflow](ANALOG_REFERENCE_WORKFLOW.md) connects an editable
SKY130 two-stage amplifier with saved OP, AC-loop, noise and startup fixtures.
Noise integration, measured unity frequency, minimum phase margin and startup
settling can be enforced as saved measurements in schematic and extracted runs.
The reference has an external ideal bias current; it does not qualify a
self-starting bias generator or arbitrary feedback/load networks.

Statistical test plans use recorded seeds and explicit numeric parameter
distributions. A trial realization is reused across tests and PVT conditions;
per-condition and joint results retain unresolved cases and withhold confidence
intervals until the trials complete. Declared tolerances remain separate from a
validated PDK mismatch model. Physical worker hosts require their own acceptance.

Calibrated extraction now supports bounded reconciled physical hierarchy with
orthogonal placements and shared-master dimensions. It preserves route paths,
cross-instance coupling and source-object mappings in an immutable run clone.
Native SPICE scopes, unmatched placements, electrical arrays without explicit
instances and incompatible parameter overrides are rejected. Supported scope
and size limits are recorded in the [guide](ANALOG_REFERENCE_WORKFLOW.md).

Bounded SKY130 physical recipes add MiM capacitors, generic poly resistors,
contacted substrate/well guards and explicitly tied schematic MOS dummies. MiM
plate connectivity is mask-aware, and generated device identities support later
layout updates. The generic-poly catalog binding now emits its actual resistor
primitive; upstream model and symbol bytes remain unchanged.
Native **Layout → Generate** dialogs expose contacted guards and tied dummies;
the existing PDK-device action handles selected supported capacitors/resistors.
Standard MOS geometry supports total widths up to 30 µm for the reference's
output stage, within the documented finger, grid and multiplicity limits.

## Bounded Magic RC correction

Actual AC/admittance qualification exposed mixed attofarad/femtofarad units and
lost ground/mutual capacitance in the pinned Magic 8.3.600 `extresist` path.
The new normalizer retains raw extraction, actual resistors and device-pin
rewiring, then reconstructs the original capacitance using normalized area
weights. Nets without positive weights use the resistance node nearest their
original physical origin. Serialized values must conserve the full original-net
capacitance matrix, and the evidence records every mapping and fallback.
Full-precision parasitic-capacitor export also prevents sub-attofarad values
from being rounded to zero. Non-capacitor SPICE lines remain unchanged, and an
independent final export check compares the collapsed capacitance matrix.

This process-RC path supports flat, unaliased extraction and at most 50,000
generated capacitors, counting ground and mutual terms together. It is a lumped
approximation with explicit conservation, not a spatial capacitance solution or
field-solver qualification.
Supported devices are numeric interconnect R, MOS and MiM subcircuits. Native
primitive-C and model-backed R devices fail closed; the new poly-resistor recipe
retains its separate DRC/LVS and capacitance-only fixture scope.
Bounded physical hierarchy is supported by the separate calibrated mode.
See the [workflow guide](ANALOG_REFERENCE_WORKFLOW.md) for supported inputs,
retained files and reproduction.

## Exact release assets

Windows acceptance now selects the installer for the current application version,
records its SHA-256 before execution, and rejects a changed installer afterwards.
All three installed DPI probes must identify the same clean source commit and
version. Their reports are retained in the platform validation evidence.

Payload preparation and final assembly require that exact installer hash. Both
platforms must provide their expected desktop archive, corresponding source ZIP
and evidence ZIP. General desktop execution and VGA reports must match the
selected clean build. A successful report from another binary, or an incomplete
asset list, cannot qualify a draft.
Archive acceptance also compares the distribution's hash before extraction and
after both probes, rejecting a file replaced while the application was running.

## Qualification status

The [original process-RC run](validation/dev25/process-rc-evidence/retention.json)
is superseded diagnostic evidence. The [corrected run](validation/dev25/process-rc.json)
passed 76/76 cases with unchanged implementation: 30 independent-netlist
comparisons, 30 complete saved-bench physical flows, 12 geometry/connectivity
faults, three stale-evidence rejections and an independent two-length coupon
acceptance. Actual AC excitation checked all three-terminal capacitance-matrix
entries at 1 kHz. Scope remains the listed transistor corners/temperatures and
pinned extraction coefficients.
The [corrected retention manifest](validation/dev25/process-rc-final-evidence/retention.json)
identifies the candidate source separately from its precommit base revision;
[27 focused regressions](validation/dev25/process-rc-unit-tests.txt) retain their
own execution log.

The [two-stage amplifier qualification](validation/dev25/two-stage-opamp.json)
passed all **216 schematic/extracted case pairs (432 simulations)**: four saved
fixtures across 27 Cartesian conditions, before and after changing the matched
input-pair lengths from 1 to 1.1 µm. Device IDs and saved requirements stayed
unchanged. Both geometries passed full DRC with zero violations and unique LVS,
then produced 6,325 resistors and 2,839 corrected parasitic capacitors. Across
both phases, extracted gain was at least 78.146 dB, phase margin at least
55.763°, integrated input/output noise at most 190.010/196.456 µV over
10 Hz–10 MHz, and startup settling at most 19.153 µs. The
[guide](ANALOG_REFERENCE_WORKFLOW.md) separates the initial and updated ranges.
These results qualify the recorded reference, ideal external bias and pinned
process deck; they do not establish silicon correlation or spatial C accuracy.

The [aggregate source record](validation/analog-reference-qualification.json)
links each executed qualification and its source hashes. The precommit base is
not the candidate implementation identity. Hosted package acceptance remains
separate.

The [retained core run](validation/dev25/core-tests.json) completed **984 tests,
35 skipped**, with no failures. Focused actual-ngspice checks additionally passed
[16 RC tests](validation/dev25/rc-tests.txt) and
[four saved-bias tests](validation/dev25/saved-bias-tests.txt).
[Offscreen Qt reference evidence](validation/dev25/gui-reference.json) checks the
four diagnostic fixtures, unchanged limits, undo/redo and save/reopen. These
source checks do not establish packaged Windows/Linux acceptance.

The [physical-device record](validation/dev25/sky130-devices.json) passed 14/14
cases: ten good coupons with zero full-DRC violations and unique LVS matches,
and four deliberate dimension, connectivity or contact-spacing faults correctly
detected. Numerical fixtures checked passive values across the recorded sizes
and PVT conditions. MiM process-corner names share a deterministic capacitor
model; no manufacturing distribution or guard-isolation performance is claimed.
The [offscreen device-dialog check](validation/dev25/gui-sky130-devices.json) also
passed all four recorded checks.

The [desktop scale record](validation/dev25/desktop-scale.json) passed correctness
checks in six iterations across two workloads, with 20 measured stages per
iteration and unchanged source. Offscreen Qt 6.8.3 measured median schematic/
layout edits of 137/206 ms for a three-level, 16-fixture amplifier bank. A
synthetic 500-device, 10,000-shape project took 3.36 s to load, 1.70/1.74 s to
edit and 97 ms to pan; sampled process RSS peaked at 314.7 MiB. No latency
budget was configured. Large-edit latency remains work to do, and these are
not native consumer-display acceptance results.

The local statistical qualification executed 1,152 actual ngspice 42 cases with
four workers: 128 correlated divider trials across nine temperature/supply
conditions. It verified analytical ratios, abrupt coordinator termination,
four expired-lease retries, immutable inputs and stale-token rejection. All
cases completed; deliberately narrow requirements yielded 99 passing and 29
failing trials with zero unresolved. The pass fraction was 77.34%, with a 95%
Wilson interval of 69.36–83.74%. This is an ideal-circuit tolerance and scheduler
check. Actual two-host acceptance remains unexecuted; use the
[worker acceptance protocol](CAMPAIGN_WORKER_ACCEPTANCE.md).
The [retained workload record](validation/dev25/statistical-campaign.json) and
[36-case final-source smoke](validation/dev25/statistical-campaign-final-source.json)
identify the executed sources and their scope. The hosted statistical workflow
is a required sixth draft gate. It subsequently passed in the
[dev25 release run](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/35550664971);
these local records retain their original scope.

Dev25 has an unpublished, hosted-qualified draft at the main commit above.
All six release gates passed; consumer-machine acceptance and the signing
decision remain open. See the [acceptance handoff](DEV25_ACCEPTANCE_HANDOFF.md).
Later experimental source changes need fresh qualification. The earlier dev24 draft at
`0f83dead7a25090ad97e3e07648d86248bd4e661` contains different source and does not
qualify these changes. The [historical local analog validation](validation/analog-closure.json)
belongs to the preceding source increment. Consult [release status](RELEASE_STATUS.md)
and the new candidate's exact-commit Actions runs before using package claims.

Release preparation requires desktop/package, external interoperability, pinned
physical, digital, VGA and statistical campaign workflows on the selected commit. Source tests and
synthetic calibration fixtures do not establish process, desktop-package or
consumer-device qualification. Draft creation does not publish a release.

The manual gates remain [Windows 10/11](https://github.com/jonahsaunders/IC-Design-Studio/issues/8),
[Ubuntu desktop](https://github.com/jonahsaunders/IC-Design-Studio/issues/9),
[signing policy](https://github.com/jonahsaunders/IC-Design-Studio/issues/10) and
[physical LAN/VPN collaboration](https://github.com/jonahsaunders/IC-Design-Studio/issues/31).
Use [native acceptance](NATIVE_DESKTOP_ACCEPTANCE.md) on the exact candidate
packages and retain the source identity, package hashes and observations.
