# Real open-project qualification — dev19

The overvoltage detector is a real third-party import regression, with independent circuit comparison, ngspice sweeps and actual Magic/Netgen execution. Its current **layout-versus-schematic result needs attention**. Import success and electrical/physical consistency are reported separately.

## Reproduce the overvoltage project

Source: [LDFranck/sky130_vbl_ip__overvoltage](https://github.com/LDFranck/sky130_vbl_ip__overvoltage), commit `53cf579f63d34227af67f0189b49ee09185f1db5`, Apache-2.0. The [source lock](../examples/open-projects/overvoltage-lock.json) verifies 67 source, reference and license files. The original repository is downloaded explicitly; it is not bundled with Studio or silently updated.

```sh
git clone https://github.com/LDFranck/sky130_vbl_ip__overvoltage build/overvoltage-source
git -C build/overvoltage-source checkout --detach 53cf579f63d34227af67f0189b49ee09185f1db5
python scripts/build_physical_engines.py --output build/physical-engines
python scripts/fetch_sky130_reference.py --physical-only --output build/qualification-pdk
python scripts/qualify_open_project.py \
  --source build/overvoltage-source \
  --pdk build/qualification-pdk/sky130A \
  --out build/overvoltage-evidence \
  --compatibility native \
  --magic "$PWD/build/physical-engines/installed/bin/magic" \
  --netgen "$PWD/build/physical-engines/installed/bin/netgen" \
  --ngspice /usr/bin/ngspice
```

Run from a source checkout with `requirements.txt` installed. The engine builder needs the development packages listed in [physical CI](../.github/workflows/physical-qualification.yml). Use a new output directory for each run. Paths to executables are explicit; substitute your installed ngspice path.

The command returns success only when the import regressions pass. Add **`--require-consistent`** to require full layout/schematic LVS as well. On the current pinned design that stricter gate fails. `qualification.json` always distinguishes `import_regression` from the overall design `status`; raw comparison reports are retained on failure.

## Open both views in Studio

1. Choose **File → Import and migrate Xschem project…** and open `xschem/sky130_vbl_ip__overvoltage.sch`. Local hierarchy symbols and bundled SKY130 primitive symbols are discovered together.
2. Inspect the migration report. Supported arrays become scalar native devices with explicit terminal labels. Source graphics outside the native subset remain archived and are listed as needing attention.
3. Choose **File → Import Magic layout…**, select the top `.mag`, the matching `sky130A.tech` and the Magic executable. Save its imported project.
4. Reopen the schematic and choose **File → Attach layout to schematic…**. Select the imported project and review the matching cell names. Attachment is one undoable transaction and refuses to overwrite existing layout.
5. Select **Linked views** to inspect the schematic and layout together. Name matching associates cell views only. Device-level correspondence requires LVS evidence. At the top-level overview, the 53,883 expanded shapes exceed the detailed drawing budget: zoom in or select a child such as `level_shifter` to inspect physical geometry.

![Imported level shifter with its schematic and physical geometry in linked views](images/overvoltage-workspace.png)

The command-line workflow produces `overvoltage.icproj` with seven schematic cells, 38 layout cells and six exact-name attachments. `trans_gate_mux` and `trans_gate_m` remain distinct because their names differ. The original GDS bytes remain recoverable through **Tools → External tool exchange → Restore original layout file…**.

The imported top is a DUT, not a complete testbench: it has no voltage sources or embedded model deck. The qualification script supplies and records its testbenches explicitly. Do not expect pressing F5 on the bare DUT to reproduce the sweep.

## What is checked

| Check | Evidence and acceptance |
|---|---|
| Source provenance | Every file in the committed lock must match; source files are never edited |
| Native schematic | Full hierarchy and parameters compared with the checked-in schematic reference through Netgen |
| Native save/reopen | The persisted native project is the input to subsequent checks |
| Schematic exchange | Exported Xschem reimported and netlisted; electrical comparison must still pass |
| Layout exchange | Every cell/layer compared by region XOR; text presentation and hierarchy/array transforms must match without relying on Studio sidecars |
| Nominal function | All 16 trip codes swept from 3 to 6 V; imported and reference output traces compared, with low/high endpoints and increasing thresholds required |
| Physical consistency | Fresh extraction from copied native Magic cells compared with the imported schematic; raw findings retained |
| Negative control | An intentional disconnected enable must be detected by LVS |

The emitted-deck comparison uses ngspice default SPICE compatibility (`--compatibility native`), the bundled pinned SKY130 `tt` models, 27 °C, DVDD 1.8 V, VBG 1.2 V, 600 nA bias and a 1 MΩ load. This is a rising DC check, not the upstream CACE timing/hysteresis suite or a full PVT qualification. Trace tolerance is 0.1% relative with a 2 µV floor; the native and reference circuits must switch on the same 10 mV step. The executed 16-code run switches from 3.30 V at code 0 to 5.46 V at code 15. Engine diagnostics remain in each run folder.

**App-default simulation remains unqualified for this legacy source.** Studio normally selects HSA compatibility. An explicit `--compatibility hsa` attempt exceeded the 120-second per-run limit with repeated convergence stepping. Default-mode emitted-deck agreement is not evidence that the bare DUT works with F5 or that HSA has passed. Keep that compatibility issue open alongside full-layout LVS.

### Legacy diode normalization

The checked-in SPICE reference uses `XD` diode calls with area/perimeter, while the supplied Xschem source selects `lvsdiode.sym`, whose format emits primitive `D` devices. The bundled model declares the legacy `1e12` area scale.

The project-specific test bridge converts the 17 locked reference declarations to the source's primitive form. For LVS only, it converts diode area to square microns. The pinned PDK setup excludes perimeter; its Magic `pj` equivalent is excluded by the recorded wrapper too. It preserves diode terminals and areas, every MOS/resistor parameter, and all circuit connections. It does not modify the general importer or substitute a different circuit. A changed declaration count fails the bridge rather than applying it to an unknown design.

### Physical findings still open

A direct comparison of the current imported schematic and fresh native-Magic extraction does not pass full LVS even after that normalization. The reports identify discrepancies involving substrate/pin correspondence and the level-shifter/top hierarchy. A separate fixed-width diagnostic makes the model's implicit 1.41 µm width explicit and uses the generic resistor class documented by the pinned Magic technology. All terminals, lengths, multiplicities, comparison tolerances and pin checks remain unchanged. Netgen then reports matching topology with **property errors**: resistor lengths are 14.10 versus 13.94 µm and dummy lengths 1.41 versus 1.25 µm. That diagnostic does not replace strict LVS. Review the upstream design's intended process revision, resistor extraction definitions and child pin correspondence before making physical or schematic edits; increasing tolerances would conceal the finding.

Magic's GDS conversion also reports two HVI parent/child disagreements in `voltage_divider`. `feedback.txt`, the conversion log and the project's retained import report expose them. The successful GDS/native/GDS geometry test establishes that Studio preserves the converted geometry; it does not certify the source-to-GDS conversion or remove those warnings.

## Import behavior added in dev19

- A reachable child schematic can introduce the PDK family even when the root contains only local block symbols.
- A single ascending/descending `[start:end]` range expands to at most 128 scalar instances. Scalar nets broadcast; vector terminal counts must match. Repetition, stride, concatenation, and incompatible widths remain explicit errors.
- Native names use `M5__0`, `M5__1`, etc.; collisions are rejected. Net names keep their scalar indices and declared range order.
- Extra array members are placed in a labeled bank away from the original wiring. The original drawing remains in the migration archive.
- Imported diagonal segments retain endpoint/junction connectivity. Interior crossings stay separate unless explicitly joined. The normal drawing tool continues to create Manhattan wires.
- GDS text size, font and alignment survive import/export and external review.
- Saved layer preferences remember their known layer set, so newly attached layers appear after reopening while deliberately hidden layers stay hidden.
- Magic import audits the complete local child tree and rejects missing children before conversion.

## Other reproducible projects

The included [GF180 bandgap](BANDGAP_COMPATIBILITY.md) supplies a second open-PDK project, with startup, a six-case compatibility circuit and the original 144-analysis source. Its tests compare captured/native/exported execution paths. The [analog qualification](PROFESSIONAL_WORKFLOWS.md) includes current-mirror, differential-pair and amplifier fixtures, and the [physical gate](QUALIFICATION_0.22.md) exercises deliberate opens, shorts/dimensional faults and DRC violations.

See [release status](RELEASE_STATUS.md) for this update's executed checks and the remaining hardware acceptance. Do not infer support for every device or construct in an arbitrary PDK from these bounded fixtures.
