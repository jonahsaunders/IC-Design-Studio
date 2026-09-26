# Executed reference compatibility and physical verification

The reference gates exercise actual Xschem, KLayout, Magic, Netgen and ngspice
processes. They retain commands, logs, inputs, fresh extracted netlists, DRC
coordinates, strict LVS reports and file hashes. A successful regression with
an intentionally defective design means the defect was detected; it never
means that design is clean. Missing engines, timeouts and incomplete reports
cannot produce a passing required check.

## Scope and reference designs

| Reference | Check | Required outcome |
|---|---|---|
| GF180 `5vfullv2-compatibility.sch` | Six analyses through independent Xschem and Studio capture/native/export/reimport paths | Waveforms and measurements agree within the recorded numerical tolerances |
| GF180 Banba physical reference | Studio and independent KLayout GDS/OASIS round trips, fresh full DRC and LVS | Geometry and interfaces preserved; exact known unfilled density findings; strict LVS passes |
| GF180 Banba filled candidate | Recreate fill, compare archived geometry, run three complete DRC decks and LVS | Zero DRC findings with the audited dummy-poly correction; strict LVS passes |
| LDFranck SKY130 overvoltage detector | Independent Xschem netlisting; native Magic; explicit flat conversion; Studio/KLayout GDS/OASIS; Magic save/reopen | Fresh full DRC has zero findings and strict LVS matches on each qualified route |
| Detector after Studio hierarchical export | Fresh full DRC and flat electrical comparison | Zero findings and strict LVS, while retaining the editing hierarchy |
| Raw hierarchical Magic detector stream | Diagnostic, retained separately | Currently fails: 288 DRC findings and an LVS mismatch in the tested tool/deck combination |
| SKY130 metal1 fixtures | Real full-deck width and spacing at 135, 140 and 145 nm | 135 nm fails the expected rule with nearby coordinates; 140/145 nm pass |
| Source desktop | Queue physical verification, edit, navigate, undo, rerun, missing engine | Pass, stale, failed, repaired pass and blocked states are visibly distinct |

The six-case GF180 schematic and the Banba physical layout are **separate
reference circuits**. These tests do not claim that the Banba layout implements
the `5vfullv2` schematic. Banba LVS uses its own independent reference circuit.
Its physical configuration is GF180 **B**, 4LM, MIM B 2fF, top metal 11K; the
bundled GF180 **D** simulation-model subset is not a physical-stack declaration.

The detector source is locked to LDFranck commit
`53cf579f63d34227af67f0189b49ee09185f1db5`. Original cells are checked against
[`overvoltage-lock.json`](../examples/open-projects/overvoltage-lock.json).
Its source gate also compares all 16 programmed trip codes to the independent
reference using the recorded HSA startup procedure.

## Deliberate defects and strictness

Detector controls alter actual geometry: narrow metal, removed contacts/vias,
shorted rails/signals, a widened resistor, a removed top-level pin and an extra
pin. DRC must locate the width defect. Strict LVS must reject the electrical
and interface defects. Resistor mutation is checked by region XOR before the
engine runs. No schematic parameter, net alias or property tolerance is
changed to make a comparison pass.

Banba controls remove poly fill, metal2 fill and vias. The core must reproduce
exactly `PL.8=64`, `M1.4=148`, `M2.4=102` (314 total). The unmodified density
deck on the filled candidate must still report `PL.8=64`. The corrected deck
must detect removed poly/metal2 fill, and strict LVS must detect removed vias.
The upstream DRC wrapper exits 1 for completed findings; acceptance requires
its completion markers and exact parsed findings, not just that exit code.

## Recorded format and process exceptions

- **SKY130 resistor extraction:** the existing checksummed correction restores
  the PCell's 0.16 µm contact-overlap convention and geometric fixed-width
  recognition. The installed PDK is untouched. See the original source,
  exact block and correction hashes in [Open projects](OPEN_PROJECTS.md).
- **GF180 density:** the existing bounded correction includes dummy poly in
  the density area. Both original and corrected decks are exercised; a clean
  result always identifies the correction used.
- **Magic input style and pins:** use the exact `sky130()` style. The shorthand
  `sky130` is ambiguous. Magic 8.3.600 can promote ordinary text to a port when
  a label rectangle precedes the text in a rewritten stream. This detector
  gate reads pin intent from the stream itself: datatype 16 is pin purpose,
  datatype 5 is non-pin label purpose on the declared SKY130 layers. Only
  explicitly non-pin labels are demoted, with a retained JSON contract and
  log. It never obtains pin membership from the schematic, adds missing pins,
  or removes pin-layer labels. Missing-pin and extra-pin controls test that
  boundary. Internal child aliases are resolved by flat electrical extraction;
  all top-level pins and device parameters remain subject to strict LVS.
- **Magic hierarchy conversion:** native source verification, raw Magic stream
  conversion and Studio's rewritten stream are distinct results. The raw
  hierarchical stream fails even though its Studio rewrite passes in this
  combination. Existing HVI conversion feedback is retained. The explicit
  **Flatten for verification** import option provides a separately qualified
  one-cell route; it leaves original source files intact.
- **OASIS text:** geometry, label strings, anchors, hierarchy, array transforms
  and database units are compared independently of Studio sidecars. Text size,
  orientation, font and alignment are not standard OASIS features. These losses
  are reported, not called lossless; GDS presentation remains strictly compared.
  See [KLayout's text documentation](https://www.klayout.org/klayout-pypi/overview/geometry/texts/).
- **Startup isolation:** import selects an explicit startup file and technology,
  so a source-folder `.magicrc` cannot override the PDK or stop the conversion.
  A real-engine regression verifies this with a deliberately hostile startup.

## Reproduce and inspect

The [physical workflow](../.github/workflows/physical-qualification.yml) builds
Magic **8.3.600** and Netgen **1.5.300** from the
[engine lock](../examples/physical-engine-lock.json), fetches the checksummed
SKY130 assets and runs the detector, boundaries and desktop gates. The
[reference workflow](../.github/workflows/reference-compatibility.yml) runs the
GF180 schematic and physical gates. Both run on `experimental` pushes and are
required by the draft-release workflow.

Linux commands, after preparing the locked source/PDK as in the physical workflow:

```sh
python scripts/verify_bandgap_compatibility.py --output build/bandgap-compatibility --xschem /usr/bin/xschem --ngspice /usr/bin/ngspice
python scripts/qualify_gf180_exchange.py --pv build/gf180-pv --klayout /usr/bin/klayout --out build/gf180-exchange
python scripts/qualify_reference_exchange.py --detector build/open-project-evidence --out build/detector-exchange --magic "$PWD/build/physical-engines/installed/bin/magic" --netgen "$PWD/build/physical-engines/installed/bin/netgen" --klayout /usr/bin/klayout
python scripts/qualify_drc_boundaries.py --technology build/qualification-pdk/sky130A/libs.tech/magic/sky130A.tech --out build/drc-boundaries --magic "$PWD/build/physical-engines/installed/bin/magic"
QT_QPA_PLATFORM=offscreen python tests/gui_physical_qualification.py --pdk build/physical-adapter/sky130A --out build/physical-desktop --magic "$PWD/build/physical-engines/installed/bin/magic" --netgen "$PWD/build/physical-engines/installed/bin/netgen" --ngspice /usr/bin/ngspice
```

The GF180 PV checkout must be clean at
`05e7b6adf19edf942969c1c9625f02fd87874f06`. Qualification output directories
must be new. Inspect `qualification.json`, `compatibility.md`, `manifest.json`
and the raw case folders in `reference-*` and `sky130-evidence-*` CI artifacts.
`status` describes required checks; `complete_scope` remains false while any
reported route is failed or blocked. Reports include the commit, working-tree
state, source hashes, platform and actual tool versions, so local modified-tree
evidence cannot be mistaken for an untouched release build.

## Unqualified combinations

Local reference runs used Xschem **3.4.4**, ngspice **42**, standalone KLayout
**0.30.9**, Python KLayout **0.30.5**, and the pinned physical engines above.
Windows source-desktop and Python tests run separately from the Linux physical
engines. Packaged Windows/Linux smoke tests remain separate CI checks.

Exploratory Xschem **3.4.8RC** emitted unresolved source-template values and
ngspice **46** did not reproduce the detector's required switching behavior.
Those combinations are not qualified. A newer executable is not silently
treated as equivalent to the recorded baseline.

Licensed Virtuoso/OpenAccess import, native Windows physical engines, GF180
distributed RC/fill coupling and foundry signoff remain unqualified. The test
matrix records those limits explicitly. DRC/LVS success does not establish
parasitic accuracy, reliability, all-device PDK coverage or fabrication signoff.
