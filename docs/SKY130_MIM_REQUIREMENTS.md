# SKY130 MiM capacitor requirement contracts

The [versioned contract](qualification/sky130-mim-contract-v1.json) consolidates
both `cap_mim_m3_1` and `cap_mim_m3_2`. It binds 41 source records, nine classified
facts and twelve remaining requirements. It is a source-review deliverable;
the planned experiment remains unexecuted in this immutable contract. Neither
device is promoted and the chunk-7 gate is unchanged.

The [October 24 installed acceptance](validation/sky130-mim-installed-acceptance-2026-10-24.json)
now completes the selected configured workflow at exact candidate `65614924`:
the actual Windows installation and Linux frozen application pass current and
historical binding lifecycle, four fresh native layouts, public geometry checks
and sixty electrical contexts per host. The shipped simulation package and
engines run with the separately locked physical PDK adapter. Complete retained
diagnostics and independent raw readback support this bounded result. The
immutable contract remains a historical planning record; the full family,
complete physical classes, operating limits and statistical/reliability scope
remain open. The installed electrical selection has mismatch disabled; actual
`_mm` alias integration is covered by the separate source experiment below,
while empirical statistical calibration remains unresolved.

## Current requirement disposition

The twelve original requirements retain their original definitions. Later
records close the predefined passive-section example, the selected bias-boundary
example, and the installed workflow recipe. They leave the remaining family
requirements open; the immutable planning contract is not rewritten.

| Original requirement | Current disposition |
| --- | --- |
| `MIM-INTERFACE` | Selected installed lifecycle passes; complete import/invalid-input coverage remains partial. |
| `MIM-PASSIVE-CORNERS` | Predefined twenty-context example completed, with later installed repetition. |
| `MIM-BIAS-BOUNDARIES` | Predefined signed-bias example completed. Leakage, breakdown and lifetime are separate. |
| `MIM-ELECTRICAL-GEOMETRY` | Full electrical validity/accuracy domain remains undefined. PCell bounds are not a substitute. |
| `MIM-TEMPERATURE` | MiM-specific validity/accuracy limits remain unresolved. |
| `MIM-RELIABILITY` | Duty, time, temperature and electrical-stress applicability remain unresolved. |
| `MIM-SPEC-ACCURACY` | Published limits still need measurement-condition and topology mapping. |
| `MIM-STATISTICS` | Selected actual alias execution completed; empirical distributions/correlations, process/layout dependence and reliability calibration remain open. |
| `MIM-PHYSICAL-CLASSES` | Selected isolated rectangles and parallel examples pass; stacked/shared/dummy/imported/hierarchical classes remain partial. |
| `MIM-WRITTEN-RULES` | Legacy stack terminology and missing numerical/context definitions remain unresolved. |
| `MIM-EXTRACTED-RC` | Selected mask-derived lumped-model integration passes; distributed/substrate/top-sheet accuracy and direct hierarchy remain open. |
| `MIM-INSTALLED` | Original configured Windows/Linux recipe completed at `65614924`; no added family-wide prerequisite. |

## Actual mismatch-library sections

The [October 24 alias execution](validation/sky130-mim-mismatch-aliases-2026-10-24.json)
closes the selected `_mm` execution gap under a separate
[predefined contract](qualification/sky130-mim-mismatch-aliases-v1.json).
Both capacitor models select `tt_mm`, `ll_mm`, `hh_mm`, `hl_mm` and `lh_mm`
through the existing application library interface, without manually overriding
statistical switches. The corresponding base sections supply deterministic
references. Each host passes 45 native runs, with independent readback of
1,080 device-frequency observations and 20 detected control conditions.

The fixed example uses 2×10 µm geometry, 27 °C, zero DC bias, unit AC stimulus,
three frequencies, multipliers one/four, a fixed seed and four replicas per
model. Application/literal mapping and the paired multiplicity law pass the
predefined tolerances. Wrong-section, disabled-mismatch, incorrect `mf` and
actually omitted simulator `m` controls are detected. Sixteen rehashed evidence
controls reject changed summaries, decks, results, runtime assets, source
provenance, coverage and scope claims; fifteen are offline-auditor checks and
one is the separate comparison with the reviewed source snapshot.

Windows uses the existing ngspice 46 and Linux the existing reviewed ngspice 42.
Each host independently passes the paired law; equality of random draws across
engine versions is not required. Four replicas do not establish a distribution,
correlation or silicon calibration. The application, public models and package
revisions are unchanged. This source experiment adds no installed or physical
coverage to the separate exact-candidate acceptance.

## Earlier bounded acceptance

The later [passive-section execution record](validation/sky130-mim-passive-corners-2026-10-23.json)
closes the predefined twenty-context example below. Both constructions pass
fresh native extraction at two orientations, followed by all five distinct
passive sections. The independent audit verifies four layouts, twelve physical
faults, 120 electrical faults and 320 AC samples from forty raw files. Its
seventeen rehashed evidence controls reject changed model sources, substituted
native paths, false summaries, incomplete bindings and unrelated physical
failures. This leaves the immutable contract's historical planning status intact;
the new record supplies the subsequent bounded result.

A later independent review added exact native startup, DRC, extraction and LVS
input checks. Five deliberately altered execution scripts/setup paths accepted
by the earlier checker now reject. The original data still passes complete
Windows/Linux readback, and the archived-source replay passes the stricter
checker. These checker changes and their 23 focused tests are retained separately
from the unchanged native producer and original audit. No native rerun is claimed
for an audit-only change.

**The source review identified missing genuine passive-corner coverage.**
The earlier nominal, ss and ff batches all select the same typical resistor and
capacitor coefficients. Their different MOS sections and selected temperatures
do not establish the distinct `ll`, `hh`, `hl` and `lh` MiM conditions.

## What the retained evidence already establishes

| Record | Bounded result | Remaining distinction |
| --- | --- | --- |
| [Capacitor families, October 17](validation/capacitor-families-2026-10-17.json) | Explicit terminal probes, selected complex admittance, parallel scaling and faults; MiM examples use 2×2 and 7×7 µm at ±0.5 V. | Historical package and second-MiM `vm` mapping; not the later mismatch correction or full voltage domain. |
| [Second-MiM layouts, October 22](validation/sky130-mim2-layouts-2026-10-22.json) | 28 selected square layouts and 35 controls; extracted capacitance checks at three selected conditions. | Original square-only scope and original package retained. |
| [MiM binding, October 22](validation/sky130-mim-binding-2026-10-22.json) | Corrected second-model `mf`/simulator `m` mapping; seeded paired mismatch scaling at four shapes and multipliers 0.5, 1, 4 and 16. | Shared-model integration; no measured distribution, correlation or lifetime calibration. |
| [Second-MiM orientation, October 23](validation/sky130-mim-orientation-2026-10-23.json) | Rectangles preserve mask-derived W/L through rotations and mirrors; 64 layouts, 47 controls and 24 electrical conditions. | Selected geometry and zero-bias public-model equivalence, not measured RF accuracy. |
| [First-MiM correction, October 23](validation/sky130-first-mim-2026-10-23.json) | Corresponding first-plate orientation and contact-edge defects corrected; both-family regression and separated mixed-family layouts checked. | Does not qualify stacked overlap, shared electrodes, distributed RC or installed deliverables. |

Every record retains its original code and package identity. The current
simulation package is `b26f7f28e659ddc1`; the physical adapter is separately
locked to revision `9a491f0ebd51a0aa`. The contract records both underlying
model/symbol hashes and the exact public technology/PCell identities. Earlier
results are not silently relabeled as current-package acceptance.

## Source definitions and their limits

The [public MiM section](qualification/sky130-mos-bias-sources-v1/device-details.rst)
defines model-validity voltage as `|Vc0 − Vc1| = 0–5 V` and describes CAPM above
metal3 and CAP2M above metal4. Its listed cell/model identifiers differ from the
shipped two-terminal wrapper names. The construction correspondence supports a
bounded family mapping, which must be recorded explicitly before adding linked
±5 V boundary checks. That wording does not establish leakage, breakdown or
lifetime qualification. The shipped wrappers themselves contain no voltage-
dependent capacitor or leakage term.

The [electrical table](qualification/sky130-mim-sources-v1/cap_mim-table0.rst)
lists the same values for both constructions:

| Quantity | Nominal | Lower / upper specification | Unit |
| --- | ---: | ---: | --- |
| Area capacitance | 2 | 1.8 / 2.2 | fF/µm² |
| Perimeter capacitance | 0.19 | 0.11 / 0.27 | fF/µm |
| Top-plate sheet resistance | 5.8 | 4.8 / 6.8 | Ω/square |

The table does not supply the complete measurement conditions or mapping to
stress corners. In particular, the model's extreme area/perimeter coefficients
extend beyond these tabulated values. This is an unresolved specification/model
mapping, not grounds to replace coefficients or declare a measurement failure.
The wrappers model bottom-metal and contact resistance; the table's top-plate
sheet resistance is not a substitute for either. Documentation mentions
bottom-to-substrate parasitics, while these two-pin wrappers have no explicit
substrate terminal. Complete parasitic and RF accuracy remain unqualified.

The public PCell defaults/checks bound W and L to 2–30 µm and label the drawn
capacitor routines as work in progress. These are generator bounds. The
application uses the same dimension bounds, a 5 nm grid and 1–16 integer
parallel copies; first MiM additionally limits aspect ratio to 5:1. Second MiM
has no equivalent ratio test. Footprint budgets and exact binding/layer guards
can reject otherwise in-range inputs. None of these checks supplies a complete
electrical geometry-validity envelope. Positive fractional electrical `mf`
does not represent a fractional physical copy.

The retained [public periphery table](qualification/sky130-mim-sources-v1/periphery-rules.rst)
contains N/A values for capm geometry rules and uses legacy met2/via2 wording.
Its named area, aspect and context restrictions still require reconciliation
with the pinned executable technology's metal3/metal4 constructions. Native DRC
success cannot resolve an unspecified or unimplemented written rule.

## Predefined next acceptance example

Use one **2×10 µm, multiplicity-one rectangle of each MiM construction**, at
0° and 90°. This is the previously exercised asymmetric layout and makes swapped
W/L observable in series resistance. Generate and verify fresh native geometry,
then retain its original/corrected extraction and masks. Compare application
export, the actual extracted file, a literal model call and independently
calculated series RC in all five sections: twenty selected contexts.

| Section | Area coefficient, fF/µm² | Perimeter coefficient, fF/µm | Metal tolerance, nm |
| --- | ---: | ---: | ---: |
| tt | 2 | 0.19 | 0 |
| ll | 1.778 | 0.03 | +45.5 |
| hh | 2.231 | 0.35 | −45.5 |
| hl | 1.778 | 0.03 | −65 |
| lh | 2.231 | 0.35 | +65 |

These are source-fixed coefficients, not validity bounds. The contract also
records each section's metal/contact resistance, the common −25 nm dimension
offset, exact include names and native parameter units.

Set temperature and reference temperature explicitly to 27 °C, DC differential
bias to zero, AC normalization to one and both statistical switches to zero.
Use the existing eight frequencies from 1 kHz to 10 GHz. Save actual applied
voltages and effective coefficient probes. At this chosen reference temperature,
the model gives `C = camimc·wc·lc + 2·cpmimc·(wc+lc)` and
`R = rmN·lc/wc + rcviaN·pitch²/(wc·lc)`, where the effective dimensions include
the recorded offset/tolerance and the contact pitches are 0.56/0.73 µm for
first/second MiM. Compare complex admittance, reconstructed resistance and
capacitance at relative tolerance 10⁻⁶. This checks implementation of the
published equations; it does not validate those equations against silicon.

Keep the existing physical faults, require swapped W/L to change resistance
by more than 5%, and detect other electrical mutations against the ordinary
comparison tolerance. In particular, a wrong MiM model need not change the
total response by 5% in every section. A wrong section must fail coefficient
readback or numerical comparison. An independent audit must reject a rehashed
manual substitute for the actual extracted path. Preserve all failures and
exact selected coverage. Closing this example only closes the selected
`MIM-PASSIVE-CORNERS` execution gap.

## Selected voltage-boundary follow-up

The subsequent [construction source map](qualification/sky130-mim-bias-source-map-v1.json)
verifies twelve pinned source hashes and four retained native inputs. Native
mask/extraction mappings, public PCells, wrapper coefficients and terminal
bindings consistently connect first MiM to CAPM over metal3 and second MiM to
CAP2M over metal4. This supports an explicitly inferred mapping for selected
−5/0/+5 V differential model-integration checks. It does not supply an upstream
legacy-name alias table or establish equivalence of omitted substrate parasitics.

The [subsequent execution record](validation/sky130-mim-bias-boundaries-2026-10-23.json)
passes sixty contexts: both constructions, two orientations,
five passive sections and three signed DC biases at 27 °C. It requires separate
actual operating-point readback for both terminals and source current, alongside
the existing eight-frequency independent RC comparison. AC agreement alone
cannot detect omitted or wrong DC bias in these voltage-independent models.
The source map defined thresholds and deliberate missing/reversed/incorrect
bias controls before execution. Four historical physical inputs were restored
and strictly re-audited with their original identities; all new electrical
execution was fresh. The strengthened independent checker verifies sixty
operating points, 480 AC samples, 180 bias faults, five domain rejections and
forty comparisons against zero-bias response. Twenty-nine rehashed evidence
mutations are rejected, including a same-bias output from a different
orientation. Unique execution/case/analysis/control titles bind each raw file
to its deck. This detects output substitution, not fully forged raw content.
The source map remains an unchanged pre-execution record; the later execution
record closes this selected example without promoting either device.

## Square-electrode dispatch correction

The [subsequent shape regression](validation/sky130-mim-physical-scope-2026-10-23.json)
fixes a dispatch defect: a square bounding box could conceal an L-shaped or
holed capacitor electrode. Every electrode is now checked for rectangular
shape before native extraction begins, including later electrodes and the
other MiM construction. Genuine squares retain their existing native path;
the nonsquare normalizer's size and grid bounds are not applied as new physical
validity limits for that path.

Both 2×2 µm constructions and a separated first-plate square with a rotated
second-plate 2×10 µm rectangle pass fresh native DRC, strict LVS, public KLayout
checks and direct extracted model/terminal/dimension checks. Four malformed
written-layout controls reject before engine execution. Nineteen focused tests
pass on each host, independent readback verifies the retained native evidence,
and archived sources reproduce the mixed case. This repairs the shape bypass;
it does not close the complete `MIM-PHYSICAL-CLASSES` requirement or qualify
arbitrary imported geometry.

## Staged Windows engine preflight

The [Windows engine preflight](validation/sky130-mim-windows-preflight-2026-10-23.json)
passes 546 capacitor-multiplier comparisons and four linked MiM contexts using
the exact staged ngspice 46 binary. Both models at 0° and tt pass 0/+5 V actual
operating-point readback and 32 AC samples, with ten detected bias faults and
five declared-domain rejections. Independent review binds the source to
`c61eeaa`, verifies unchanged models/runtime and checks the selected historical
native extraction under its original identity. This supports bringing up the
installed probe with this engine; it is source/staged-engine integration and
does not close `MIM-INSTALLED`. Other corners, −5 V and 90° are outside this
selected Windows preflight.

The [Linux native-runtime preflight](validation/sky130-mim-linux-runtime-preflight-2026-10-23.json)
also passes all 546 analytical multiplier comparisons on the already available
Ubuntu ngspice 42 binary. The desktop workflow selects this runtime separately
from the corrected ngspice 47 managed payload. The known failure in unpatched
47 therefore does not justify replacing 42 for this scope. This check uses
the local system binary, not a frozen desktop, and does not exercise a PDK or
the sixty-context linked MiM requirement.

## Installed editor and native-layout subgate in development

The built-in `--mim-acceptance` probe and separate
`scripts/verify_frozen_mim.py` checker are implemented for both release
platforms. The checker requires the selected clean commit, the actual frozen
executable, the locked physical adapter, the bundled current simulation
package and managed engines. The bounded scope is both 2×10 µm
capacitors at 0/90 degrees, actual editor placement/edit/save/reopen and layout
generation, preserved historical parameter mapping, native verification and
failure/repair/stale-evidence controls. The
[source bring-up record](validation/sky130-mim-installed-probe-source-2026-10-23.json)
passes four GUI/native cases and three saved binding states, with seven queued
jobs and six actual native executions. Independent readback verifies the raw
scripts, geometry, extraction and DRC/LVS results, rejects ten rehashed evidence
corruptions and confirms that the installed checker rejects the source report.

Windows runs this inside the existing per-user installation before uninstall;
Linux runs it against the frozen application before archive assembly. Both
platforms then require public KLayout checks on the four exact GUI exports and
a narrow-metal control, followed by all sixty predefined electrical contexts
through the discovered shipped simulator. An independent electrical auditor
checks raw operating points, AC samples, faulty-bias controls and model/runtime
identity. `scripts/verify_installed_mim.py` binds these results to one selected
candidate, the original GUI jobs and unchanged evidence inventories. The public
and electrical pilots remain explicitly source-only; they cannot satisfy that
installed aggregate. Release evidence archives retain every subgate.

The [public source pilot](validation/sky130-mim-installed-public-drc-source-2026-10-23.json)
passes all four exact exports and the declared narrow-metal fault under the
255-category deck. The [electrical source pilot](validation/sky130-mim-installed-electrical-source-2026-10-23.json)
passes all sixty contexts on the actual local ngspice 42, with sixty operating
points, 480 AC samples and 180 detected bias faults. Independent readback rejects
ten public-output and thirteen electrical-output corruptions. These are
development checks against fresh GUI inputs, with exact engine identities and
recoverable evidence; they do not describe a frozen installation.

This source bring-up was a historical preparation step, superseded by the
October 24 installed acceptance above. The original `MIM-INSTALLED` recipe is
now completed for that exact candidate. All-class physical coverage, silicon
accuracy, reliability and complete family qualification remain separate gates.

## Work still needed for family closure

The contract separates local execution from missing source definitions:

- **Local:** the selected passive-section and mapped ±5 V linked examples and
  the defined installed Windows/Linux recipe are completed. Remaining work
  includes supported physical-class reconciliation, broader import coverage
  and full extracted behavior.
- **Source or calibration:** complete electrical W/L and temperature validity;
  measurement conditions for the tabulated limits; statistical correlations and
  calibration; ripple, leakage, field, self-heating and lifetime applicability;
  complete written-rule and parasitic-model mapping.
- **Unsupported or separately qualified classes:** stacked/shared electrodes,
  PCell dummy/contact-coverage variations, arbitrary imported geometry, direct
  hierarchical native extraction and distributed RC. Existing separated mixed
  capacitors do not establish these classes.

All copied documentation remains unmodified under its original Apache-2.0
license and pinned public revision. No private resource is required for the
planned passive-section example. Chunk 7 remains approximately **60% complete**,
with low confidence (50–70%); this contract does not increase that estimate.
