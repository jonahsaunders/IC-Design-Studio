# IHP five-terminal thermal models

The three public `npn13G2_5t`, `npn13G2l_5t` and `npn13G2v_5t`
models expose temperature rise through their fifth terminal, `t`. This is a
thermal model connection, measured in kelvin of rise above the selected ambient
temperature. It is not an additional electrical pad on the physical transistor.
The bundled public model files and their licenses remain unchanged.

The inspector now distinguishes Collector, Base, Emitter, Substrate and
Temperature rise. Symbol text resolves the source's mixed-case `Nx` and `El`
placeholders from the live parameters. Unknown placeholders remain visible;
arbitrary cell ports retain their own names.

## Local tests

The [execution record](validation/ihp-thermal-2026-10-17.json) retains 66
independent comparisons, 2,970 vectors, 656,370 compared values and 220 detected
faulted instances across the nine-condition batch and two nominal regressions.
All 121 raw outputs are re-read. Windows backend DC/AC/transient matches its
same-engine references and verifies all 153 returned files. Sixteen focused
tests and source-desktop checks pass on each host. Successful and failed runs,
the distinct tested source versions and original model licenses are archived.

`scripts/qualify_ihp_thermal.py` exercises ten instances: emitter counts 1 and 4
for the standard family, and counts 1 and 4 with emitter lengths 1 and 2.5 Âµm
for each editable-length family. The supply is 1 V. Nine selected conditions
combine nominal/slow/fast model sections with 0, 27 and 85 Â°C. These are finite
integration points, not a continuous safe operating envelope.

For each condition, the runner compares every electrical-terminal current and
the thermal output against independently authored five-terminal model calls.
It also compares all four electrical currents with the corresponding public
four-terminal model, which retains its internal thermal network.

- DC: 34 base-voltage points from 0.45 through 0.78 V.
- AC: 21 complex-response points from 100 kHz through 1 GHz, at 0.75 V bias.
- Transient: a smooth 5 MHz heating cycle from 0.55 to 0.78 V for 600 ns.
- Fault controls: clamp temperature rise to zero, or change emitter count.

The checker requires complete finite waveforms, electrical current balance,
actual stimulus readback, positive temperature rise and a changing thermal
output. Raw-file audits independently re-read the comparisons and check rising
DC temperature, thermal lag between equal-voltage portions of a heating cycle,
and the reduced collector current with the thermal output clamped.

DC and AC comparisons use a relative tolerance of `1e-6`, with absolute
tolerances of `1e-12 A` and `1e-8 K`. Transient comparisons interpolate onto the
application time grid and use `2e-4` relative, `1e-8 A` and `1e-5 K` absolute.
These bounds compare two calls to the same model on the same engine; they are
not bounds on silicon-model accuracy or agreement between engine versions.

## Retained failures and limits

The first pulse experiment used mismatched source-edge durations. Correcting
that input did not resolve the next sharp-pulse experiment: the independently
authored decks used different adaptive steps around 2 ps transitions and failed
the declared waveform tolerances. Those runs remain failures. The smooth-cycle
test does not qualify picosecond pulse response.

A direct comparison between managed ngspice 42 and the separately built
ngspice 47 also exceeded the same-engine tolerance. Their results retain separate
engine identities and independent references; no cross-version equivalence is
claimed.

Source-desktop checks on Windows and Linux verify placement, actual inspector
edits, saved five-terminal connectivity and live parameter text. They are separate
from numerical-model tests and from final installed-desktop acceptance.

Measured thermal calibration, arbitrary external thermal networks, mutual
heating, sharp-edge behavior, full bias/geometry ranges, noise, statistical/RF
accuracy and final installed-release acceptance remain open. The four-terminal
physical evidence is described in [the bipolar layout guide](IHP_BIPOLAR_LAYOUT_QUALIFICATION.md).
Chunk 7 remains incomplete.
