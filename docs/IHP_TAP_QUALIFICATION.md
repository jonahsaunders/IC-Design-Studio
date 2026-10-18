# IHP tap models and sampled layouts

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

These electrical points establish schematic integration with the pinned public
model. They do not establish fabrication limits, a complete operating envelope,
latchup/ESD behavior or installed-release acceptance.

## Sampled physical acceptance

The separate [physical execution record](validation/ihp-tap-layouts-2026-10-18.json)
covers both tap models at the five rectangles listed above, rotated by 0 and
90 degrees: twenty layouts in total. Select the public IHP KLayout extraction
option for these checks. Full Magic DRC remains enabled; the default Magic LVS
extraction route is not qualified for taps by this result.

The comparison converts schematic width and length to the public extractor's
area and perimeter. It accepts the exact reviewed live resistance formula or
a literal resistance matching that formula. It rejects other expressions,
unresolved geometry, conflicting parameters and changed source models. Native
area, perimeter and terminal roles are preserved. Taps are excluded from generic
resistor terminal permutation and series/parallel reduction in the private
comparison setup. Original public source files are unchanged.

The initial physical probe correctly failed LVS because those representations
differed. Subsequent deliberately undersized contacts exposed a separate gap:
Magic accepted 80 nm cuts. The application now also checks written contact
layer 6/0 directly against the locked public `Cnt.a` minimum of 160 nm, retaining
the original native result and navigable error locations. This supplemental
check covers that minimum only; it does not establish complete process-rule
coverage. It does not alter the design masks.

All twenty layouts and two additional public A/P reference netlists pass.
All forty removed-contact/undersized-contact layouts and eight incorrect
terminal/model/area/perimeter references are rejected. An independent audit
checks 70 native netlists, 50 converted netlists and 540 exported layer
comparisons, including reopened GDS and OASIS. The fault audit verifies that
only the intended contact masks changed.

Both source desktop actions pass. Six Windows backend cases verify all 476
received files. Seven prior MOS/resistor/MIM/PNP cases pass on the default
package; three NPN cases pass on their separately qualified corrected package.
An initial NPN attempt using the default package failed native DRC and remains
retained. NPN acceptance is not transferred to that default package.

```sh
python scripts/qualify_ihp_tap_layouts.py --help
```

These are sampled source-application results. Continuous geometry and operating
ranges, latchup/ESD, default Magic tap extraction, default-package NPN integration,
remaining device families and installed-release acceptance remain open.
Chunk 7 remains incomplete.
