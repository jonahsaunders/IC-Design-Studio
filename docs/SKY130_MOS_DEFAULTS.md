# SKY130 MOS starting dimensions

Seven short MOS symbols previously started with W = 1 µm and L = 0.15 µm,
outside the selected public models' geometry bins. Actual execution of all
42 available MOS defaults reproduced seven model-selection failures and
35 successful cases. Fresh placement now uses the dimensions below, taken
from each model's ordinary public symbol.

| Short symbol | Initial W, µm | Initial L, µm |
| --- | ---: | ---: |
| `nfet3_03v3_nvt` | 1 | 0.5 |
| `nfet3_05v0_nvt` | 1 | 0.9 |
| `nfet3_g5v0d10v5` | 1 | 0.5 |
| `nfet3_g5v0d16v0` | 5 | 0.7 |
| `pfet3_01v8_lvt` | 1 | 0.35 |
| `pfet3_g5v0d10v5` | 1 | 0.5 |
| `pfet3_g5v0d16v0` | 5 | 0.66 |

The correction checks the catalog binding, the locked source identities and
the actual short-symbol, ordinary-symbol and model-file bytes. Customized
bindings and unreviewed source revisions retain their own defaults. A reviewed
source that is missing or changed requires package repair. The helper affects
new instances only: saved, reopened, imported and deliberately edited dimensions
keep their values. These symbols retain the application's explicit drain, gate,
source and body terminals.

The bundled SKY130 package remains revision `1901822ae8f81ae1`, with manifest
SHA-256 `42cafd2b1407783d361cfbb276abe3ba9e97b2c06a716af6c9069c8426852413`.
No model coefficients, symbol source bytes, package metadata or upstream license
notices change. The implementation introduces no private or newly copied PDK
resources. It uses the public sources already retained by the project.

## Executed checks

The [execution record](validation/sky130-mos-defaults-2026-10-22.json) binds the
results to the tested sources. Windows ngspice 46 and local Linux ngspice 47 each
pass 14 cases for all 42 available MOS defaults:

- Nine DC cases: nominal, slow and fast process selections at 0, 27 and 85 °C,
  sweeping the gate from 0 to 1.2 V. Separate voltage sources expose each terminal.
- Five nominal 27 °C AC cases, driving drain, gate, source, body and the isolated
  20 V device's substrate separately, over 31 points from 1 kHz to 1 GHz. Devices
  without a substrate terminal have zero applied AC drive in that fifth case.
- Two deliberately wrong DC circuits per condition: doubled multiplicity and
  gate tied to source. Every affected device must differ from the independent
  reference after successful engine execution.

Each host completes 588 valid device comparisons and detects 756 faulty device
instances. Independent raw-file readback checks 46 files, 1,932 model calls,
2,366 terminal vectors and 88,556 current samples per host. It verifies terminal
voltages, signed/complex currents, current conservation, geometry, model names,
multiplicity and the declared fault outcomes. The reference circuit uses literal
model calls and geometry values; it does not use the application's emitter or
device constructor. The tolerance remains 1e-12 A absolute plus 1e-6 relative.

All 67 distinct affected tests pass on each host. The initial runs skipped three
engine-dependent tests; separate runs with the real simulator enabled pass all
three. Tests confirm that only the seven intended defaults change, altered proof
sources are rejected, and new/original/custom dimensions survive save/reopen and
Xschem export/import. Each host also passes seven source Qt editor workflows:
placement, rotation, duplicate, undo/redo, property editing and save/reopen.
These editor checks use an offscreen display and do not establish frozen-package
or manual consumer-desktop acceptance.

## Reproduction and scope

```sh
python -m unittest tests.test_sky130_mos_defaults -v
python scripts/qualify_sky130_mos_defaults.py --ngspice /path/to/ngspice --output /path/to/new-results --workers 2
QT_QPA_PLATFORM=offscreen python tests/gui_sky130_defaults.py --out /path/to/new-editor-results
```

Add `--pilot` for one nominal 27 °C DC case and its two fault controls. The
repository's physical workflow runs that pilot with its pinned simulator, and
desktop builds run the editor check. Hosted results must be assessed for the
exact new commit; earlier successful builds do not qualify this application.

The original seven failures and final raw results are retained in a verified,
deduplicated archive. Restored-source pilot execution must pass before redundant
generated files are removed. The before-fix diagnostic uses a different bias
fixture, so it proves the original model-selection failures, not waveform
equivalence to the final independent comparisons.

This fixes starting dimensions and verifies the specified integration cases.
It does not establish continuous geometry, voltage or temperature envelopes,
ESD ratings, reliability, statistical or RF accuracy, additional physical
generation, complete-chip signoff or complete upstream PDK coverage. In
particular, successful 16 V electrical defaults do not supply a qualified 16 V
layout generator. The seven unavailable real-device bindings are separate from
these seven corrected symbols. All device statuses remain partial and chunk 7
remains open under its existing completion gate.
