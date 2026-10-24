# SKY130 LI resistor requirement contract

The [versioned contract](qualification/sky130-li-contract-v1.json) records
the reviewed sources and remaining requirements for
`sky130_fd_pr/res_generic_li.sym`. It contains 24 hashed source references,
12 classified facts and 12 requirement rows. This completes the source-review
deliverable; it adds no native execution and does not qualify the device.

**The first linked pilot uses a 2 × 5 µm single LI resistor, the
actual extracted circuit and the five distinct passive sections.** Earlier
LI tests exercise nominal, ss and ff, but all three select the same typical
resistor parameters. They are useful alias checks, not low/high LI corner
coverage. The current library supplies:

| Section | `rl1`, ohm/square | `tol_li`, µm |
| --- | ---: | ---: |
| tt | 12.2 | 0 |
| ll | 10.31 | +0.014 |
| hh | 14.02 | −0.014 |
| hl | 14.8 | −0.020 |
| lh | 9.5 | +0.020 |

These are model coefficients. The contract binds each value to the exact
bundled file, package identity and source hash; they are not operating limits.
The public RSLI specification table gives nominal 12.8 and bounds 9.2–17.0
ohm/square. It does not supply the complete measurement conditions in the
reviewed section. Preserve the typical-model/table nominal difference without
declaring it a failed bound or substituting either value.

The [retained public rule table](qualification/sky130-li-sources-v1/p035-li_dotdash_dotdash.csv)
sets ordinary LI resistor width to at least 0.290 µm, with a separate
`areaid.ed` exception. Earlier 0.17 µm electrical fixtures therefore do not
establish ordinary physical legality. Rule li.2 also needs an explicit
interpretation: it limits contact-free LI length/width but prints a length
unit for the ratio and carries flag NC. A native DRC pass cannot silently
resolve that definition or waive an unchecked requirement.

The public documentation cautions against generic resistors for analog use.
LI is the first narrow integration milestone because the project already has
electrical, physical and interface evidence. It is not a proposed precision
analog resistor. **M1–M4 still need their own electrical contracts and evidence**;
the five-model physical batch does not inherit LI-only electrical results.

## Selectable linked pilot

Keep the existing physical package separate from the current simulation
package. Generate the legal 2 × 5 µm single resistor at 0° and 90°, preserve
its masks through save/reopen and GDS/OASIS exchange, then run full native DRC,
strict LVS and independent written-rule checks. Read model, terminals and
dimensions from the unmodified native extraction.

Compare three paths under the same stimulus and load: the application export,
the actual native extracted subcircuit, and a literal independent model call.
Start at nominal/27 C, then exercise tt/ll/hh/hl/lh with effective parameter
readback. The contract specifies DC, complex AC, transient and noise stimuli,
existing numerical tolerances, expected fault controls and required evidence
bindings. Noise must use the legal 2 × 5 µm device; the old noise fixture was
0.17 × 10 µm. These are selected integration stimuli, not new validity limits.

The new `scripts/qualify_sky130_li_linked.py` runner selects passive sections
and orientations explicitly. The default is `tt` and both orientations; all
five sections are a separate explicit selection. Every execution uses a fresh
output directory. No development reuse or release-cache path is enabled.

```sh
python scripts/qualify_sky130_li_linked.py \
  --sky130 /path/to/locked-physical-adapter \
  --magic /path/to/magic --netgen /path/to/netgen --ngspice /path/to/ngspice \
  --output /path/to/new-evidence \
  --sections tt ll hh hl lh --rotations 0 90 --workers 2
python scripts/audit_sky130_li_linked.py /path/to/new-evidence \
  --output /path/to/separate-audit.json
```

The extracted path includes the unmodified native file and calls its actual
subcircuit. The auditor independently reads the raw data, applied source,
current conservation, passive parameters, native dimensions, executed decks,
selected sections and original extraction paths. Negative controls alter
width, length, metal model, multiplicity, terminal connectivity and section.
Invalid or nonfinite results cannot count as a detected electrical fault.

These three circuit paths share the same public compact model. Their agreement
tests circuit export and extraction integration; it does not independently
calibrate resistance or noise against physical measurements. The source
contract's analytical/calibration and complete written-rule requirements remain
open. Installed Windows/Linux candidate acceptance remains a separate step.

The [October 23 linked acceptance record](validation/sky130-li-linked-2026-10-23.json)
passes all ten selected section/orientation cases: 80 comparisons, 180 raw
outputs and 60 detected electrical faults. The two layouts pass native full
DRC and strict LVS; five physical faults are detected. An independent auditor
checks 1,429 file bindings and rejects five deliberately altered evidence sets
even after their corresponding hashes are rebound. Windows and Linux focused
tests pass 17 checks each. A fresh nominal replay from the verified archive
also passes; the original failed pilots and auditor-format corrections remain
retained. This closes the selected `LI-PASSIVE-CORNERS` and
`LI-EXTRACTED-ELECTRICAL` execution examples, without promoting the family.

## Definitions still required

The contract retains open rows for complete geometry and temperature validity,
voltage/current/power and reliability limits, li.2 applicability, independent
sheet-resistance measurement conditions, frequency/noise accuracy and statistical
calibration. The immutable source contract retains its pre-execution rows;
the linked acceptance record supplies the selected passive-corner and extracted
electrical results separately. Supported physical classes and installed
acceptance remain open. Absence from the inspected files is not a claim that
no public definition exists elsewhere.

The source model's `tnom=30 C`, temperature coefficients and positive-parameter
checks cannot supply missing limits. Limits for precision poly resistors or
other routing layers cannot be applied to LI without evidence of applicability.

The source bundle retains the original Apache-2.0 license and exact public
revision; the project license does not replace it. Existing acceptance remains
in [sky130-li-metal-resistors-2026-10-17](validation/sky130-li-metal-resistors-2026-10-17.json).
No matrix status or completion gate changes. Chunk 7 remains approximately
60% complete, low confidence (50–70%).
