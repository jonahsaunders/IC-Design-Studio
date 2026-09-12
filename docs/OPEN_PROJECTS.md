# Real open-project qualification — dev20

The overvoltage detector is a real third-party import regression, with independent circuit comparison, ngspice sweeps and actual Magic/Netgen execution. **Strict full-circuit LVS passes** with the recorded upstream resistor extraction correction. HSA simulation uses first-point voltage guesses, and a generated native testbench can run directly in Studio. Import, simulation and physical comparison retain separate evidence.

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
  --require-consistent \
  --magic "$PWD/build/physical-engines/installed/bin/magic" \
  --netgen "$PWD/build/physical-engines/installed/bin/netgen" \
  --ngspice /usr/bin/ngspice
```

Run from a source checkout with `requirements.txt` installed. The engine builder needs the development packages listed in [physical CI](../.github/workflows/physical-qualification.yml). Use a new output directory for each run. Paths to executables are explicit; substitute your installed ngspice path.

The command and physical CI require **strict layout/schematic LVS**, all 16 HSA trip-code comparisons and three negative controls. Without `--require-consistent`, import and design acceptance remain separately reported for diagnosis. `qualification.json` retains the source, technology correction and tool provenance; raw comparison reports are retained on failure.

## Open both views in Studio

1. Choose **File → Import and migrate Xschem project…** and open `xschem/sky130_vbl_ip__overvoltage.sch`. Local hierarchy symbols and bundled SKY130 primitive symbols are discovered together.
2. Inspect the migration report. Supported arrays become scalar native devices with explicit terminal labels. Source graphics outside the native subset remain archived and are listed as needing attention.
3. Choose **File → Import Magic layout…**, select the top `.mag`, the generated `technology/sky130A.tech` from the qualification output and the Magic executable. Save its imported project.
4. Reopen the schematic and choose **File → Attach layout to schematic…**. Select the imported project and review the matching cell names. Attachment is one undoable transaction and refuses to overwrite existing layout.
5. Select **Linked views** to inspect the schematic and layout together. Name matching associates cell views only. Device-level correspondence requires LVS evidence. At the top-level overview, the 53,883 expanded shapes exceed the detailed drawing budget: zoom in or select a child such as `level_shifter` to inspect physical geometry.

![Imported level shifter with its schematic and physical geometry in linked views](images/overvoltage-workspace.png)

The command-line workflow produces `overvoltage.icproj` with seven schematic cells, 38 layout cells and six exact-name attachments. `trans_gate_mux` and `trans_gate_m` remain distinct because their names differ. The original GDS bytes remain recoverable through **Tools → External tool exchange → Restore original layout file…**.

For a runnable circuit, open **`overvoltage-bench.icproj`** from the output directory. It includes the unchanged DUT hierarchy and both views, the complete model include closure, supplies, bias and load. Select `detector_dc_bench`, keep **DC startup → Use first-point voltage guesses** enabled in the Analysis panel, and press **F5**. The saved default is code 0. Set `Vbit0`–`Vbit3` to 0 or 1.8 V to select codes 0–15. Select `ovout` in the waveform viewer.

`overvoltage.icproj` remains the bare DUT for schematic/layout inspection; its ports need the separate bench supplies to simulate. The generated bench embeds its model files and survives relocation. No upstream schematic or layout file is edited.

## What is checked

| Check | Evidence and acceptance |
|---|---|
| Source provenance | Every file in the committed lock must match; source files are never edited |
| Native schematic | Full hierarchy and parameters compared with the checked-in schematic reference through Netgen |
| Native save/reopen | The persisted native project is the input to subsequent checks |
| Schematic exchange | Exported Xschem reimported and netlisted; electrical comparison must still pass |
| Layout exchange | Every cell/layer compared by region XOR; text presentation and hierarchy/array transforms must match without relying on Studio sidecars |
| Nominal function | All 16 trip codes swept from 3 to 6 V; imported and reference output traces compared, with low/high endpoints and increasing thresholds required |
| Physical consistency | Fresh, flattened extraction from copied native Magic cells compared with the imported schematic, including device properties and top-level pins |
| Negative controls | A disconnected enable, miswired child substrate pin and 14.10→13.94 µm resistor-length fault must each fail LVS |
| Desktop testbench | Saved/reopened native project executed through the app analysis engine in HSA mode |

The default emitted-deck comparison uses ngspice HSA compatibility, the bundled pinned SKY130 `tt` models, 27 °C, DVDD 1.8 V, VBG 1.2 V, 600 nA bias and a 1 MΩ load. This is a rising DC check, not the upstream CACE timing/hysteresis suite or a full PVT qualification. Trace tolerance is 0.1% relative with a 2 µV floor; the native and reference circuits must switch on the same 10 mV step. The executed 16-code run switches from 3.30 V at code 0 to 5.46 V at code 15. Engine diagnostics remain in each run folder.

### HSA convergence correction

ngspice 42's [DC sweep implementation](https://sourceforge.net/p/ngspice/ngspice/ci/ngspice-42/tree/src/spicelib/analysis/dctrcurv.c) restarts `CKTop` at every point in HSA mode. This detector repeatedly entered convergence stepping and previously exceeded the 120-second limit. Raising iteration limits did not resolve it.

The new optional DC startup setting independently solves **each circuit's own first sweep point**, in the selected compatibility mode and at the requested temperature. Its node voltages become `.nodeset` guesses for the full sweep. These guesses are released before the final solution; they are not voltage clamps or copied reference outputs. Existing user nodesets are preserved. No solver tolerance or timeout is relaxed. The setting is enabled in the generated bench and HSA qualification runs, and is saved with analysis settings.

Every run retains `dc-startup.cir`, its raw operating point and log, the generated `.nodeset` file, and the full sweep deck/raw/log. A missing, partial, nonfinite or wrong-start solution fails before the sweep. `--compatibility native` remains available for an independent default-SPICE comparison; it does not silently replace HSA.

### Legacy diode normalization

The checked-in SPICE reference uses `XD` diode calls with area/perimeter, while the supplied Xschem source selects `lvsdiode.sym`, whose format emits primitive `D` devices. The bundled model declares the legacy `1e12` area scale.

The project-specific test bridge converts the 17 locked reference declarations to the source's primitive form. For LVS only, it converts diode area to square microns. The pinned PDK setup excludes perimeter; its Magic `pj` equivalent is excluded by the recorded wrapper too. It preserves diode terminals and areas, every MOS/resistor parameter, and all circuit connections. It does not modify the general importer or substitute a different circuit. A changed declaration count fails the bridge rather than applying it to an unknown design.

### Resistor extraction and internal pin aliases

The old pinned technology measured the resistor body as 13.94 µm, while the schematic specified 14.10 µm; dummy resistors similarly measured 1.25 instead of 1.41 µm. The upstream SKY130 PCell generator subtracts **0.08 µm per end** when drawing these resistors. The corresponding extraction definition must restore **0.16 µm** to recover the model length.

The [committed correction lock](../examples/open-projects/sky130-resistor-extraction.json) backports the resistor block verbatim from [open_pdks `1689ac3`](https://github.com/RTimothyEdwards/open_pdks/blob/1689ac3f2dc763876eaf967227c7dfe831b031ae/sky130/magic/sky130.tech). It also recognizes fixed resistor widths geometrically, so legacy cells do not require later marker paint. The PCell geometry convention is recorded in [the same revision's generator](https://github.com/RTimothyEdwards/open_pdks/blob/1689ac3f2dc763876eaf967227c7dfe831b031ae/sky130/magic/sky130.tcl).

[`prepare_open_project_technology.py`](../scripts/prepare_open_project_technology.py) verifies the entire base deck checksum, the unique replaced block and the complete resulting deck checksum. It writes a separate technology deck with attribution and provenance. Unknown revisions are rejected. The installed PDK, original design geometry, schematic parameters, Netgen property tolerances and strict result parser remain unchanged. To prepare the correction independently:

```sh
python scripts/prepare_open_project_technology.py \
  --source build/qualification-pdk/sky130A/libs.tech/magic/sky130A.tech \
  --out build/detector-technology
```

The previous child-pin findings came from Magic's internal aliases: for example, `level_shifter` merges port `dvdd` with a well node labeled `M2`. The detector gate uses `ext2spice hierarchy off` to compare the complete physical circuit, resolving internal aliases while preserving all top-level pins, devices and connectivity. Native project and imported layout hierarchy remain available for editing. Strict Netgen reports must pass without pin-list alterations or property errors. The deliberate child-pin and resistor-length faults verify that this extraction strategy still rejects actual defects.

### Remaining scope limits

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
