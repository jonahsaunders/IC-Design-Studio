# SKY130 local qualification profile

Chunk 6 targets a generic SKY130 workflow with local verification and export.
Tiny Tapeout is inspiration and a public reference; its shuttle interface is
not an export requirement. This 2026-10-16 profile replaces the previous
catalog-wide interpretation of chunk 6. It does not qualify every SKY130 device,
the complete chip, manufacturing masks, or foundry signoff.

## Completion gate

Every applicable physical requirement for the declared profile must be accounted
for. Valid reference layouts must pass locally, deliberate physical faults must
be detected, and Studio must retain and export the exact checked artifacts.
Missing or failed required checks prevent a verified result. Source revisions,
tool versions, upstream exclusions and unsupported features remain explicit.

Initial target: SKY130A HD digital blocks and 1.8 V NMOS/PMOS layout controls.
Top names, dimensions and interfaces are design inputs. The process's permitted
metal stack is independent of any shuttle's reserved layers. No Tiny Tapeout
tile size, tt_um_ naming, GPIO interface or metal-5 prohibition is imposed.
Counter, UART and APB examples exercise the
digital path. Custom transistor geometry and connectivity controls exercise
the physical path; complete device-family and analog-performance qualification
remain in chunks 7–9. Exact PDK/tool identities must accompany each execution.

## Work and acceptance evidence

| Batch | Required outcome | Status |
| --- | --- | --- |
| Scope | Pinned sources and an applicability record for every required profile check | Native source/options pinned; complete applicability record remains open |
| Local verification | Generic SKY130 native DRC, transistor geometry, antenna and connectivity; separate density and LVS evidence | Fresh filled counter/UART/APB Finish passes; strict reference LVS and custom MOS controls pass; full profile acceptance remains open |
| References and faults | Counter/UART/APB and nonempty transistor controls; deliberate faults rejected | Native, implant, fill-mapping, spacing, density and LVS fault controls pass their expected outcomes; native implant gap remains explicit |
| Density | Declared surrounding geometry and boundary policy; meaningful full-window checks on final fill | Local fill generation and independent stream checks implemented; 840 µm reference passes nine full windows under both public profiles; complete density applicability remains open |
| Application | Normal application execution and export, repeatable on Windows/Linux, with no missing-check success | Four filled Linux Finish runs and three Windows export/readback runs pass; installer requalification remains separate |

## Generic integration evidence

The [2026-10-16 execution record](validation/sky130-generic-native-2026-10-16.json)
records three fresh native runs on the retained counter/UART/APB layouts and a
fresh counter run from RTL through the normal application Finish/export path.
Each native run emits all 255 expected categories with zero markers. The category
inventory detects incomplete output; it is not a count of all foundry requirements.
The native deck, its GPLv3 license, command, logs and measurements are bound to
the exact final GDS and retained in the generic macro export.

The 12 controls cover valid metal-1/metal-5 shapes, off-grid and minimum-width
faults, covered/uncovered contacts inside and outside a core marker, and valid
1.8 V NMOS/PMOS devices with corresponding missing-implant faults. The native
deck misses both removed-implant faults. Studio's existing raw-mask checker
detects them as `n/psd.9.n` and `n/psd.9.p`. Both results are preserved; a native
zero-marker result cannot substitute for the other mandatory checks.

Reproduce the geometry controls in a source environment with the project Python
dependencies and a Ruby-enabled KLayout 0.30.5 executable:

```sh
python scripts/qualify_sky130_native.py --klayout /path/to/klayout --output /new/evidence/folder
```

The script preserves expected native misses and the independent implant results;
it does not treat those controls as full device or electrical qualification.

## Filled layouts and connectivity evidence

The [generic fill execution record](validation/sky130-generic-density-2026-10-16.json)
adds optional local metal fill to normal Finish. Select **Generate SKY130 metal
density fill** in Physical settings, or set `physical.sky130_fill` to `true`.
The selected SKY130 HD platform must contain the reviewed physical checkers and
the captured stream technology. Other technology revisions fail explicitly until
their mapping is reviewed.

OpenROAD generates the fill. An independent reader compares every final GDS fill
rectangle against the implementation database and checks its size, grid, bounds,
spacing and clearance from circuit metal on all five layers. The generated
technology retains the original drawing maps and supplies explicit fill maps;
the original technology and both recipes are retained. The macro LEF includes
the fill as routing obstructions, and export binds the checked GDS, database,
LEF, rules and reports. Missing or changed evidence prevents export.

The 840 by 840 µm counter contains 381,362 fill rectangles. All nine full
700 by 700 µm windows, sampled every 70 µm, pass both retained public 80% metal
growth profiles on metals 1–4. The unfilled reference fails 36 full-window
measurements per profile despite a clean native geometry report. A wrong stream
mapping also escapes native DRC but is rejected by the new database/stream check.
These controls establish why neither native DRC nor the presence of a fill option
is sufficient density evidence. Metal 5 is checked for fill geometry; the public
oxide profiles do not establish a metal-5 density requirement.

Clipped edge observations remain diagnostics and are retained, including their
findings. A smaller macro has zero full windows and is exported with
`surrounding-layout-required`, never a density acceptance claim. Its eventual
assembly needs new checks on the combined layout and declared context.

The exact filled counter, UART and APB references also pass fresh strict
transistor, diode, body and port LVS comparisons against independently captured
database/CDL references. Removing diode diffusion from counter/APB or flip-flop
polysilicon from UART makes comparison fail. Separate custom
1.8 V NMOS/PMOS controls pass native full DRC and extraction/LVS; changing their
reference widths is rejected. These are retained qualification runs, not an
automatic LVS pass conferred on every application export.

The final focused suite collects 162 tests per OS: Windows passes 154 with eight
OS-specific skips, and Linux passes 157 with five OS-specific skips. The skipped
platform-specific cases execute on the other OS. Three Windows exports reopen
relocated evidence, verify every exported artifact/notice hash and reject a
changed fill inventory. Native OpenROAD LEF readback preserves every fill
obstruction and the expected pins in all four fresh application references.

This work establishes the stated public-window and reference connectivity results.
It does not close complete profile applicability, final-mask density or all
boundary policies. Routed OpenRCX SPEF is retained; floating-fill coupling has
not been qualified. Broader device and electrical qualification keep their
separate gates. Chunk 6 remains open while an applicable requirement lacks proof.

Public Tiny Tapeout and ChipFoundry decks already retained by the project are
reference implementations. Their original licenses remain in force. Reuse is
limited to process checks that apply to the declared design context. Shuttle
submission checks are not generic SKY130 rules. Existing Studio checks,
including the contact-coverage regression, remain in force.

## Broader obligations

The historical 302 unresolved catalog records remain unchanged. They are not
automatically waived, relabeled absent, or counted as passing. Applicability
decisions need evidence. Any unresolved requirement that applies to the supported
profile still blocks that profile's qualification. Frame/scribe and complete-chip
obligations remain recorded for chunk 11; unrestricted signoff remains unqualified.

Native DRC alone does not cover density, antenna, LVS, or electrical
performance completely. Those requirements have separate tests and reports.
All checks in this profile execute locally, and all incorporated resources must
comply with [the contribution license policy](../CONTRIBUTING.md).

## References

- [Local hardening and simulation](https://tinytapeout.com/guides/local-hardening/)
- [Analog layout and interface requirements](https://tinytapeout.com/specs/analog/)
- [Pinned precheck source](https://github.com/TinyTapeout/tt-support-tools/tree/01d5d2814fa9dd61e9d211e0b235a4a592a9316a/precheck)
- [Earlier physical evidence](SKY130_PHYSICAL_QUALIFICATION.md)
- [Twelve-chunk qualification plan](PDK_QUALIFICATION_PLAN.md)
