# GF180 asymmetric high-voltage model integration

GF180 C revision `b661a751abfc662a` and D revision `2f92b1f05da58bd7`
enable `nfet_10v0_asym` and `pfet_10v0_asym`. Their source file,
`models/ngspice/smbb000149.spice`, was already identified by the original
upstream lock but omitted from the bundled model include closure. The added
file matches that recorded SHA-256 exactly:
`8a8d44d5f13d4a097e86fab598e97e82bb726af1cc01eb6d500739766dfd9363`.

The public source is from the
[pinned GlobalFoundries PDK](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/tree/4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c).
Its Apache-2.0 notice is retained. No upstream model coefficients, symbols,
licenses or existing assets are changed. The project's GPL-3.0 license remains
unchanged. Exact earlier package manifests remain available for reconstructing
historical qualification inputs and opening saved projects.

## Binding and declared limits

Both models have distinct drain, gate, source and bulk terminals. Drain and
source are asymmetric and cannot be treated as interchangeable. The source
symbol's area and perimeter formulas remain live functions of width.

The importer accepts the public typical, FF, SS, FS and SF sections, with
`nominal` aliasing typical. It retains the existing `design.ngspice` and
low-voltage/passive include sections. Internal model-definition and statistical
sections are not exposed as interchangeable process corners.

The [published recommended ranges](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/HV/HV_2_3.html)
are W = 4–50 micrometres, L = 0.6–20 micrometres and M = 1–100. The adapter
enforces these ranges and fixes NF to 1 because the
[public model overview](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/HV/HV_1_2.html)
does not support finger scaling. These model ranges do not establish legal
physical dimensions or safe reliability limits.

M retains the public subcircuit's exact behavior: its core MOS uses M, while
the external drift resistors and capacitances do not uniformly scale with it.
The M=2 and M=100 comparisons therefore verify agreement with that public
subcircuit, not equivalence to two or one hundred complete parallel devices.
Use explicit separate instances when that complete parallel topology is needed.

## Local evidence

The [execution record](validation/gf180-high-voltage-2026-10-18.json) covers
both packages, both polarities, five corners, four temperatures and two drain
biases. The 80 cases pass 160 independent DC/AC comparisons: 8,960 terminal
vectors and 344,960 values. All 2,240 deliberately faulty instances are
detected. A separate parser audits all 480 raw outputs and verifies current
conservation at every accepted sample.

The actual Windows simulator additionally passes both drain biases at nominal
25 degrees Celsius for C and D: eight comparisons and 112 faulty instances.
Combined independent readback covers 504 raw files, 168 comparisons, 9,408
vectors and 362,208 values. The maximum observed terminal-current conservation
residual is approximately `3.27e-13 A`. Windows and Linux source editors pass
placement, limit feedback, parameter editing and saved-revision checks.

- W/L pairs, in micrometres: `(4,0.6)`, `(4,20)`, `(50,0.6)`, `(50,20)` and
  `(25,0.6)` at M=1, plus `(25,0.6)` at M=2 and M=100.
- Temperature: -40, 25, 125 and 175 degrees Celsius, following the temperatures
  described in the [model extraction documentation](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/HV/HV_2_1.html).
- DC: gate bias magnitude 0–5 V, 0.1 V steps; drain bias magnitude 5 or 10 V;
  0.2 V reverse bulk bias. The PMOS gate sweep runs -5 through 0 V.
- AC: 100 Hz–10 MHz, five points per decade, comparing complex current at all
  four terminals with independent per-terminal excitation.
- Fault controls: wrong width within the accepted range, and exchanged drain
  and source connections. Every device must show an actual response mismatch;
  simulator failure is not accepted as successful fault detection.

Independent decks call the original subcircuits directly and use their junction
geometry defaults; the application follows the separately imported symbol
formulas. Runtime output completeness, nonfinite values, missing phases and
unexercised drain responses are checked explicitly.

The final full suites discover 3,071 tests each and pass: 3,040 executed on
Linux with 31 skips, and 3,032 on Windows with 39 skips. All four source-editor
checks pass; visual review confirmed the corrected device labels. Earlier
ordering and historical-evidence failures remain recorded. The 151 MB evidence
archive verifies every stored object, and a restore check verifies both model
packages, the source and one complete case, then passes seven restored tests.

```sh
python scripts/prepare_gf180_hv.py --input icstudio/assets/pdks/gf180mcuD --output /path/to/new-package
python scripts/qualify_gf180_hv.py --package /path/to/new-package --output /path/to/new-results --ngspice /path/to/ngspice
python tests/gui_gf180_hv.py --target gf180mcuD --out /path/to/new-editor-check
```

These tests establish selected schematic integration with the pinned public
model. Physical extraction, transient/noise coverage, complete operating limits,
statistical/RF accuracy and installed-release acceptance remain open. The public
[model limitations](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/HV/HV_2_2.html)
also distinguish statistical targets from silicon verification. Chunk 7 remains
in progress.
