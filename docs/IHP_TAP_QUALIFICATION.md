# IHP tap schematic models

The bundled IHP revision `c0a32344f73be40d` enables the public `ntap1` and
`ptap1` two-terminal symbols. The previously bundled symbols used a Tcl
resistance expression and a starred alternative LVS attribute that the
declarative importer rejected. Only the two exact reviewed symbol hashes are
adapted in memory. No Tcl runs, and every original symbol, model, license and
notice stays byte-identical. Saved projects retain their registered revision;
the exact previous manifest is retained for reproducible reconstruction.

The source is the Apache-2.0
[IHP PDK revision 5e6d592](https://github.com/IHP-GmbH/IHP-Open-PDK/tree/5e6d592e4002946a4616f798c357f0f3c06cf3b6/ihp-sg13g2).
The existing GPL-3.0 application license is unchanged. Attribution and exact
source hashes are in `icstudio/ihp_taps.py` and the bundled source files.

## Editing and simulation

Both symbols have terminals `p` and `m`. Width and length are positive values
in metres; engineering suffixes such as `2u` are accepted. Resistance remains
calculated from these dimensions and cannot be independently overridden:

```
R = 1 / (w*l / 9.8e-10 + 2*(w+l) / 9.8e-4)
```

This is the public symbol's parallel area/perimeter resistance formula. The
SPICE model uses the supplied resistance; its W/L parameters do not recalculate
it internally. The inspector shows the live resolved value, and save/reopen
preserves that dependency. The selected ngspice export writes the resolved
numeric resistance; native symbol exchange retains the formula.

The two public electrical models are identical in this source revision.
Numerical comparisons therefore cannot distinguish their names. The acceptance
runner separately checks each emitted model identity and pin order.

## Recorded local acceptance

The [execution record](validation/ihp-taps-2026-10-18.json) separates the
final-source nine-condition ngspice 47 batch from the managed ngspice 42 nominal
regression. They total 50 independent analysis comparisons, 320 output vectors,
66,020 compared values and 200 detected faulty device instances. Independent
raw readback verifies all 120 output files, including analytical DC division,
complex RC response and Johnson noise. The normal Windows backend route passes
five analysis comparisons and verifies all 255 received files. Source editor
checks pass on Windows and Linux; these are not installed-release results.

Each condition contains both models at five W/L pairs, in micrometres:
`(.78,.78)`, `(.78,5)`, `(5,.78)`, `(2,2)` and `(10,10)`. Nominal, slow and fast
model sections are tested at 0, 27 and 85 degrees Celsius. Complete locked
includes and their compiled IHP model dependencies remain loaded.

- DC: -10 through +10 mV, 1 mV steps, with a 1 kilohm load.
- AC: 100 Hz through 10 MHz, five points per decade, with a 1 pF load.
- Transient: 600 ns of a smooth 5 MHz drive, compared with an independent deck.
- Noise: both model families at their default geometry over the AC frequencies.
- Fault controls: 20% width error and disconnected input, detected for all ten
  devices in every condition.

The numerical comparator has explicit finite-value, sweep-completeness, phase
and nonzero-response checks. Original unsuccessful editor probes remain in
the evidence archive; they exposed test-harness assumptions about manifest
serialization, deferred Qt widgets and numeric SPICE export. The editor's
computed-parameter commit behavior was corrected before accepted runs.

```sh
python scripts/prepare_ihp_taps.py --output /path/to/new-package
python scripts/qualify_ihp_taps.py --package icstudio/assets/pdks/ihp-sg13g2 --output /path/to/new-results --ngspice /path/to/ngspice --osdi /path/to/ihp-osdi
python tests/gui_ihp_taps.py --out /path/to/new-editor-evidence
```

These points establish schematic integration with the pinned public model.
They do not establish fabrication limits, a complete operating envelope,
tap-layout extraction, latchup/ESD behavior or installed-release acceptance.
In particular the public Magic `ngspice(lvs)` style has distinct tap-recognition
semantics; the default layout route has not been qualified for these devices.
Chunk 7 remains incomplete.
