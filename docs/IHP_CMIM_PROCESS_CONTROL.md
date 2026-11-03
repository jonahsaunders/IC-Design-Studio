# IHP capacitor process-control comparison

This bounded experiment establishes the selected capacitor's electrode mapping
and compares the pinned nominal `cap_cmim` model with published process-control
definitions. It reports model limitations; it does not establish measured
calibration, safe operating ratings, reliability, or full-family qualification.

Independent readback of the retained layout, labels, native extraction and strict
LVS maps `c0`/`PLUS`/`C1` to TopMetal1 and `c1`/`MINUS`/`C2` to Metal5. This mapping
uses actual masks and source definitions, rather than the model's stale Metal3
comment. It is a replay of the selected archived physical evidence, not a fresh
physical extraction for every electrical point.

Fourteen new native ngspice-42 jobs measure capacitance from the complex current
and applied AC voltage, using `Im(Y)/(2πf)`. Four additional jobs deliberately
alter the driven electrode, frequency, temperature or geometry. Independent
raw readback checks the complete allowed circuit and control sequence, operating
point, frequency, stimulus orientation, temperature and model identity. Added
passives, parameter overrides and extra control commands are rejected even when
the reported file hashes are recomputed. Native failures from earlier attempts
are retained separately.

| Source condition | Implemented comparison | Result and limit |
| --- | --- | --- |
| A.ah | 300 K, 1 MHz, top plate grounded, lower plate at −10/−5/0/+5/+10 V | The model ratio is 1 at all points. Published targets predict 1.00076 at −10 V and 1.00024 at +10 V, giving model-minus-target differences of −760 and −240 ppm. The source supplies no acceptance tolerance. |
| A.ad | Zero bias, 1 MHz; −40/0/26.85/27/75/125 °C, normalized at 300 K | Largest selected target residual is approximately 0.0587 ppm. Native model TNOM is 27 °C, distinct from the 26.85 °C measurement reference. Target agreement is not a calibrated operating-range claim. |
| A.k/A.l | Zero bias, 100 kHz; selected 7 × 7, 10 × 10 and 7 × 14 µm rectangles | Direct total-capacitance/area and /perimeter observations are reported. A separate model-only decomposition gives 1.5 fF/µm² and 40 aF/µm. Missing monitor dimensions, de-embedding and measurement temperature prevent an exact physical-monitor comparison. |

The small real-current component is also retained, but this experiment makes no
conductance-accuracy claim. Reversing the drive can expose cancellation in that
tiny component; the independently checked capacitance observable uses the
imaginary component. Statistical sections, parasitic extraction, broader
geometries, installed execution and continuous validity/reliability remain open.

The runner and separate reader use the licensed source ledger already retained
in [the applicability checklist](IHP_CMIM_REQUIREMENTS.md). Reproduction uses the [included public evidence subset](qualification/ihp-cmim-plate-evidence-v1/README.md),
75,922 bytes, containing twelve unchanged historical native files and both
applicable licenses. The source contract pins the ZIP and provenance manifest;
physical, model and raw-output checks remain mandatory. The complete original
15 MB archive is no longer required for the default commands. The subset's
parent digest is provenance; reading this subset does not verify omitted parent
contents or perform a fresh physical extraction.

Use native Linux ngspice and Python with KLayout bindings (reviewed version
0.30.5) for archived-mask readback. The output must be a new directory outside
the checkout with an existing parent. For a direct installation, launcher and
native-binary paths must be the same; the alternative is the exact supported
managed wrapper. Run from the repository root:

```text
python scripts/qualify_ihp_cmim_process_control.py --out /absolute/new-output --ngspice NATIVE_LAUNCHER --native-binary ACTUAL_NGSPICE_BINARY
python scripts/check_ihp_cmim_process_control.py --evidence /absolute/new-output
```

The optional `--physical-archive` accepts either the exact bundled subset or the
original `repair-native-review.zip`, SHA-256
`495ee8b7771c8df0f00c8b4b994e48d4dbcf18a8734a1b25cb9c8b423136e6a7`,
retained under `IC-Design-Studio-evidence/ihp-cmim-catalog-reference-2026-11-02-v1`
with the [original catalog-reference record](validation/ihp-cmim-catalog-reference-2026-11-02.json).
Arbitrary or repacked archives are rejected. The recorded archive identity
always distinguishes the public subset from that complete historical archive.

The [validation record](validation/ihp-cmim-process-control-2026-11-03.json)
binds native results, independent readback and the compact recovery archive.

The [public reproduction record](validation/ihp-cmim-public-reproduction-2026-11-03.json)
verifies the default producer and independent raw readback on Linux, portable
Windows replay, and changed/missing/repacked evidence rejection. It preserves
the original comparison result and its limitations.

The original model coefficients are unchanged. Qualification requires resolving
the voltage-dependence discrepancy and the missing applicability/calibration
inputs, rather than adjusting the published target to fit this model.
