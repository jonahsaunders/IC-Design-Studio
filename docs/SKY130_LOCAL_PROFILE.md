# SKY130 public-check baseline v1

Chunk 6 qualifies a generic SKY130 workflow against an explicit, versioned suite
of public checks, with local verification and export.
Tiny Tapeout is inspiration and a public reference; its shuttle interface is
not an export requirement. This 2026-10-16 profile replaces the previous
catalog-wide interpretation of chunk 6. It does not qualify every SKY130 device,
the complete chip, manufacturing masks, or foundry signoff.

## Approved completion gate

On 2026-10-16 the user approved completion against the public-check baseline,
with unresolved process requirements explicitly excluded from its qualification
claim. This replaces the earlier requirement to resolve every applicable rule
before completing chunk 6. It does not change those rules into passes.

The baseline is `sky130a-hd-public-checks-v1`. Valid reference layouts must pass
the included local checks, deliberate faults must be detected, and Studio must
export the exact checked artifacts and source identities. Missing or failed
included checks cannot produce a baseline pass. The
[completion record](validation/sky130-public-baseline-2026-10-16.json) binds the
implementation, reference runs, controls and cross-platform exports.

The export manifest reports `public-checks-passed` when every included check
passes with full density windows. It reports `surrounding-layout-required` for
a checked small block with no full windows, and `incomplete` when checks are
missing. Historical jobs do not automatically acquire a baseline pass.
`foundry_signoff` and `complete_rule_coverage` remain false in every case.

Excluded from this baseline are the unresolved x.20 pin-spacing limit and
periphery applicability, generated-mask definitions, the historical 302 open
catalog records, final-mask/metal-5 density and clipped-window acceptance,
seal/frame/scribe and complete-chip checks, other device families, electrical
qualification and installer/release acceptance. These remain visible obligations
for broader support. The native deck's built-in cell filters remain explicit.

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
| Scope | Versioned included checks, source identities and explicit exclusions | Complete for the public-check baseline; complete process-rule applicability remains excluded |
| Local verification | Public native DRC, supplemental transistor geometry, 13 antenna stages, power connectivity, strict LVS and public density checks | Complete for the retained reference scope; both captured HD libraries have separate reference/fault evidence |
| References and faults | Counter/UART/APB and nonempty transistor controls; deliberate faults rejected | Native, implant, fill-mapping, spacing, density and LVS fault controls pass their expected outcomes; native implant gap remains explicit |
| Density | Meaningful full windows on final fill, with explicit treatment of small blocks | Filled 840 µm reference passes nine windows under both public profiles; smaller blocks retain their surrounding-layout obligation |
| Application | Normal execution and portable export with no missing-check baseline success | Complete for the public-check reference gate; installer requalification remains separate |

The completion review also corrects two older manual-ledger exclusions:
missing frame/module identifiers cannot discharge enclosure requirements.
New Finish reports keep those rows unresolved, and export rejects a restored
false exemption even if its report hash is recomputed. Older reports without
this review need a new Finish before export. Original measured geometry and
historical evidence files are preserved.

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

## Mandatory density gate

The [application density execution record](validation/sky130-density-gate-2026-10-16.json)
closes a fill-setting bypass: every newly prepared SKY130 HD Finish job checks
both retained public growth profiles, whether metal fill is enabled or disabled.
A failed full window saves the measurements and stops Finish. Export recomputes
the measurements from the actual final GDS and independently captured bounds;
missing evidence, changed source files and altered passing reports are rejected.
The original Tiny Tapeout checker, Apache license and source lock accompany
every new result and export.

This is a mandatory project policy for the named public profiles. It does not
supply the remaining foundry applicability or final-mask definitions. A small
block still reports `surrounding-layout-required`; completing implementation
does not confer density acceptance on a block without full windows. Historical
jobs retain their original evidence and are not silently upgraded.

## Mandatory application connectivity

The [application LVS execution record](validation/sky130-application-lvs-2026-10-16.json)
extends those reference controls into normal Finish. Every newly prepared
SKY130 HD Finish job now captures a fresh independent OpenDB/CDL reference and
compares it with the final GDS. Device dimensions, body connections, antenna
diodes and every boundary port must agree. Unknown CDL or extraction revisions
fail explicitly. The two supported captured library revisions are tested
separately; this does not qualify every cell or device family.

Port-name encoding operates on a mask-identical copy, with labels placed on
existing metal. Pin annotations cannot create conductors. The comparison adds
no global supply ties, port equivalences or device blackboxes. A missing or
failed comparison prevents Finish from succeeding. Export requires the exact
checked GDS, database, independent reference, native comparison database,
comparison settings, tool identities and source licenses. Saved-result replay
reconstructs the reference and label adaptation and reads the native comparison
graph instead of trusting a saved PASS field. Historical jobs retain their
original evidence and gain no automatic connectivity claim.

The source review identifies the extraction rules as the BSD-2-Clause
`laurentc2/SKY130_for_KLayout` source with mechanical interface substitutions in
ORFS. The adapter verifies that relationship and retains the original source
and license. Independent diode GDS/SPICE views retain their Apache-2.0 terms.
No private or Cadence-licensed checker is incorporated.

The final connectivity-focused suite collects 220 tests on each OS: Windows
passes 212 with eight OS-specific skips, and Linux passes 215 with five. The
platform-specific skipped cases execute on the other OS. Six fresh Linux
Finish runs cover counter, UART and APB on both captured library revisions;
all six deliberate physical faults are rejected. Six Windows exports reopen
relocated native evidence, verify every exported artifact/notice hash and
reject a changed native comparison database.

The earlier fill-focused suite collects 162 tests per OS: Windows passes 154 with eight
OS-specific skips, and Linux passes 157 with five OS-specific skips. The skipped
platform-specific cases execute on the other OS. Three Windows exports reopen
relocated evidence, verify every exported artifact/notice hash and reject a
changed fill inventory. Native OpenROAD LEF readback preserves every fill
obstruction and the expected pins in all four fresh application references.

This work establishes the stated public-window and reference connectivity results.
Complete process applicability, final-mask density and complete-chip boundary
policies are excluded from baseline v1. Routed OpenRCX SPEF is retained;
floating-fill coupling has not been qualified. Broader device and electrical
qualification keep their separate gates.

Public Tiny Tapeout and ChipFoundry decks already retained by the project are
reference implementations. Their original licenses remain in force. Reuse is
limited to process checks that apply to the declared design context. Shuttle
submission checks are not generic SKY130 rules. Existing Studio checks,
including the contact-coverage regression, remain in force.

## Broader obligations

The historical 302 unresolved catalog records remain unchanged. They are not
automatically waived, relabeled absent, or counted as passing. Applicability
decisions need evidence. They are excluded from the bounded public-check
qualification rather than discharged. Frame/scribe and complete-chip
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
