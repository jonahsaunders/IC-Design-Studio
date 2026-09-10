# IC Design Studio 0.7.0

This release connects the native schematic and layout workspaces to an executed custom SKY130 inverter flow. It includes editable device geometry, reviewed regeneration, connection guidance, full Magic DRC, extracted Netgen LVS, capacitance extraction, and before/after ngspice waveforms. It builds on the 0.6 project/PDK lifecycle and reusable component work.

## Start with the supplied inverter

1. Extract the entire companion **PDKs-and-Evidence** archive. Open its `custom-inverter.icproj`. Its PDK path is relative to the adjacent `sky130A` directory, so keep those together initially. Save a working copy at your preferred location.
2. Configure the separately installed **Magic**, **Netgen** and **ngspice** executables in **Tools → Engine diagnostics & paths**. The tested engines are Magic 8.3.683, Netgen reporting 1.5.132, and ngspice 42. The Linux application bundle includes Python, Qt and KLayout; it does not bundle these three external engines.
3. Select `custom_inverter` in the cell selector. The `testbench` cell contains the supply, stimulus and load. The inverter cell contains the two PDK transistors with four explicit terminals each.
4. Open **View → Physical workflow**. The supplied project already has generated layout. To change it, edit schematic W/L, then choose **Generate layout…** and review the replacement. Apply is one undoable edit. Whole-inverter regeneration replaces all geometry and labels in that generated cell, including manual edits.
5. Use **Check connections** to inspect the linked terminals. Dashed lines indicate disconnected groups of terminals belonging to the same schematic net. Selecting a device or its linked geometry cross-selects the corresponding objects in the other view.
6. Choose **Run physical verification**. The background job retains a project snapshot and runs seven stages in order. A failed or blocked stage prevents later stages from reporting success.
7. Use **Before layout** and **After layout** to open the saved waveforms. The workspace displays the mean delay comparison. **Evidence folder** opens the scripts, decks, logs, extracted circuits and report. Changing the design marks the saved result stale.

For a fresh design, install `sky130A/package.json` in **Tools → PDK manager**, then choose the **Custom SKY130 inverter** template in New project. With SKY130 already linked, **File → New custom SKY130 inverter** creates the same electrical starting point without geometry. Custom cell symbols remain editable through their Symbol document in the project tree or the Design symbol actions.

## Editable physical devices

**Design → Generate SKY130 device layout** creates a footprint for one selected schematic MOS at an explicit location. It draws actual SKY130 masks: diffusion, implant, well where required, gate, contacts and metal access, with a separate body tap and four assigned terminal locations. A subsequent invocation previews replacement of that footprint using current model, dimensions and nets. Existing routes remain at their coordinates and need checking after regeneration.

The inverter generator places a native NMOS and PMOS, ties each body to its source supply, and routes input/output and supply connections. The default layout contains 55 editable shapes and eight terminal assignments. It does not copy a standard-cell inverter or call an upstream PCell script.

Supported models are exactly `sky130_fd_pr__nfet_01v8` and `sky130_fd_pr__pfet_01v8`, with direct W/L emission, one finger and multiplicity one. W is accepted from 0.42 to 10 µm and L from 0.15 to 10 µm, on the 5 nm grid. This is an accepted input range, not exhaustive physical qualification of every size. Voltage variants, transformed-width symbol templates, multiple fingers and other PDKs need separate geometry adapters.

The linked-layout audit detects changes to the recorded schematic model, sizes, parameters or nets and identifies removed devices. Its records describe the source of the generated geometry. Manual polygon edits still require actual DRC and extracted LVS; a matching source record does not prove the edited geometry correct.

## Physical verification

| Stage | Required result |
| --- | --- |
| Preflight | Valid inverter, current source links, locked model assets and available tool paths; tool versions and hashes recorded |
| Schematic simulation | The native catalog devices switch correctly in ngspice |
| Magic DRC | Explicit `drc(full)` style, no ignored rules, zero reported violations |
| LVS extraction | Magic creates the extracted transistor netlist with the declared ports |
| Netgen LVS | Unique circuit match without property errors |
| Capacitance extraction | Magic emits an extracted deck with parasitic capacitors |
| Post-layout simulation | The extracted circuit switches correctly; before/after delay measured |

DRC findings include physical bounding boxes and appear in Checks. Clicking a finding zooms to its area. Netgen's detailed device, net and property comparisons remain in the evidence log.

Verification uses the selected model corner with a fixed 1.8 V supply, 5 fF output load, 20 ns input period and 62 ns transient. It creates this bench around the selected inverter; it does not use arbitrary stimulus settings from another cell. Delay is the mean over six 50% crossings. Extraction includes capacitance, without distributed interconnect resistance. Whole-chip density, antenna, reliability, timing closure and fabrication signoff are outside this fixture.

## PDK packages and runtime setup

The managed installer now includes and hashes Magic and Netgen assets under `libs.tech`, so an installed SKY130 package has the physical files the new workflow needs. PDK manager states which packages have native Studio geometry generators. Model and symbol content is unchanged from the supplied 0.6 packages; the physical asset locks and capability metadata change their revisions.

| PDK | Package revision | Placeable / indexed symbol entries | Native 0.7 geometry |
| --- | --- | ---: | --- |
| SKY130A | `b19a81c06779a79d` | 71 / 74 | Standard 1.8 V NMOS/PMOS and custom inverter |
| GF180MCU C | `a1610a6b160f44d6` | 20 / 22 | Pending |
| IHP SG13G2 | `4a83d130587a7404` | 35 / 45 | Pending |

Install the new revision and use **Tools → Migrate PDK revision** to preview an existing project's upgrade. Its old lock is not silently replaced. **Locate** and **Relink project PDK folder** remain available for moved folders. Projects can still be duplicated, deleted recoverably and restored through the Projects view.

For IHP, compile the provided Verilog-A sources using `scripts/compile_ihp_osdi.py`, then use **Tools → Simulation runtime → Load folder…** to select the generated `.osdi` files together. File selection remains available. Hash and host-platform checks run before simulation. The tested historical pairing is OpenVAF 23.5.0, OSDI 0.3 and ngspice 42; native model binaries must be built for the destination machine. The 0.6 model/corner reports are included as historical evidence and were not all rerun for 0.7.

## External edit compatibility

| Tool / format | Executed in 0.7 | Limits |
| --- | --- | --- |
| KLayout 0.30.5, GDSII/OASIS | Write OASIS, edit geometry with the real KLayout database, review/reimport, then pass full inverter flow | This exercises KLayout's database API, not its interactive GUI; mapped layers, supported transforms and declared database units are required |
| Magic 8.3.683, `.mag` | Save the checked native cell, load/paint/save in Magic, convert to GDS and review/reimport, then pass full inverter flow | Matching technology required; arbitrary Magic hierarchy and all technologies are not qualified |
| Xschem 3.4.4, `.sch`/`.sym` | Netlist exported hierarchy with real Xschem; simulate it in ngspice; edit MOS width and reimport; repeat with a parameterized divider | Studio-generated package metadata and unchanged locked symbols required; this is headless netlisting, not a full Xschem GUI qualification |
| ngspice 42, SPICE | Native schematic, Xschem-generated and Magic-extracted decks simulate with actual engines | Native SPICE import remains the documented subset; unrestricted behavioral/vendor syntax uses the external-deck path |

Use **File → Export GDSII / OASIS**, edit externally, then **File → Review imported layout changes**. The preview compares geometry and applies external text changes. Matched cell names, physical instances and arrays retain hierarchy. Identical polygons keep their native IDs and links; changed polygons lose device/net tags. Schematic devices and assigned terminal coordinates remain available for checking. Review is protected against applying to a design changed since preview.

For Magic, the native file is in a successful run's `drc` directory. After an external edit, convert it with the CLI command below, then review `imported.gds` against the original project. **File → Import Magic layout** remains available to open a separate imported layout project.

Use **File → Export Xschem package**, open the top `.sch` with its export folder in `XSCHEM_LIBRARY_PATH`, and use **File → Import edited Xschem package** to bring supported edits back. Real netlisting exposed and fixed missing electrical labels, incorrect primitive/subcircuit types, missing child schematic resolution, and parameter escaping. Exported native cells now have sibling `.sym`/`.sch` files, ordered interface ports and live instance parameters. The complete Studio simulator deck is `simulation.cir`; Xschem's own netlist contains connectivity and needs model includes and analysis configured in the external testbench.

## Executed validation

- 102 core tests pass, including generator limits, regeneration/undo, connectivity guidance, stale source detection, hierarchy-preserving layout edits and parameterized Xschem exchange.
- Nine native Qt suites pass. An additional desktop check runs all three real engines through the worker, opens the extracted waveform and confirms that a later design edit marks evidence stale.
- The frozen Linux executable passes eight checks at both 100% and 200% display scale with development Python and loader overrides removed. It also completes all seven real physical stages from the portable project using an output path containing spaces.
- Ten physical cases produce their expected outcomes: seven complete passes and three deliberate fault rejections.
- Nominal, slow and fast corners pass. Additional geometry cases use WN=WP=0.42 µm / L=0.155 µm and WN=1.5 µm, WP=3 µm / L=0.35 µm. KLayout and Magic edited geometries pass the full flow again.
- A 100 nm metal island fails DRC; a severed output connection passes DRC and fails LVS; changing physical channel length from 150 to 200 nm without changing the schematic fails the LVS property check. None reaches post-layout simulation.
- Actual Xschem netlisting and ngspice pass for the original inverter and a 1→1.5 µm NMOS width edit. A parameterized divider produces 0.60 V, then 0.45 V after changing its ratio from 2 to 3; native reimport retains these edits.

| Default inverter corner | Schematic mean delay | Extracted-capacitance mean delay |
| --- | ---: | ---: |
| nominal | 20.21 ps | 25.79 ps |
| ss | 26.40 ps | 34.57 ps |
| ff | 16.08 ps | 20.85 ps |

The companion archive's `EVIDENCE-0.7` contains `qualification/regression.json`, each case's report and engine files, `xschem-qualified/report.json`, desktop evidence and release probes. Failures under `reject-*` are intentional negative cases. Test-host absolute paths are retained in immutable logs; use the portable project and configured local tools to rerun. `EVIDENCE-0.6` retains the earlier release's model checks separately.

Magic was built from upstream tag 8.3.683. Netgen was built from tag 1.5.133, whose executable reports 1.5.132; evidence records the observed version. This restricted host used local Tcl/loader paths and a temporary-file-location adapter for ngspice. The adapter affects temporary storage, is excluded from the app and PDK packages, and is unnecessary on a conventional desktop installation. No model or engine algorithm was changed to force passing results.

## Reproduce from source

After installing source dependencies and configuring the external tools:

```sh
python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen python tests/gui_silicon.py

python main.py --cli silicon /path/custom-inverter.icproj \
  --cell custom_inverter --output /path/new-evidence \
  --magic /path/magic --netgen /path/netgen --ngspice /path/ngspice

python scripts/verify_silicon.py --pdk /path/sky130A \
  --output /path/new-regressions \
  --magic /path/magic --netgen /path/netgen --ngspice /path/ngspice

python scripts/verify_xschem_exchange.py \
  --project /path/custom-inverter.icproj --output /path/new-exchange \
  --xschem /path/xschem --ngspice /path/ngspice

python main.py --cli magic-import --source /path/edited.mag \
  --technology /path/sky130A/libs.tech/magic/sky130A.tech \
  --executable /path/magic --output /path/new-conversion
```

The optional `--xschem-workdir` supports a relocated Xschem shared directory. Conventional installations do not need it. Verification outputs must be new or empty directories.

## Delivery and continuation

The standalone Linux x86_64 build targets Ubuntu 24.04 / glibc 2.39 or newer. Keep `_internal` beside the executable. The full source is included. PDKs and external EDA tools are separate installations.

The source includes the updated Windows build/installer pipeline and physical-workspace probe. **No Windows runner was available, so this delivery has no verified Windows binary or installer.** Automatic WSL engine management is also pending. See `WINDOWS_RELEASE.md` for the prepared steps.

The next development work is broader transistor geometry (multiple fingers and process variants), configurable physical testbenches, GF180/IHP physical adapters, richer routing and hierarchy editing, and a real Windows qualification run. Full Xschem/KLayout feature parity and fabrication readiness remain longer-term goals.

New code: `sky130_layout.py` generates and audits geometry; `silicon_flow.py` runs independent engines; `silicon_ui.py` presents the workflow; `import_review.py` reconciles external hierarchy/geometry; `interchange.py` and `xschem_io.py` handle the tested Xschem exchange. The verification scripts and `test_silicon.py` / `gui_silicon.py` are the regression entry points.

Primary implementation references: [SKY130 rules](https://skywater-pdk.readthedocs.io/en/main/rules/periphery.html), [Magic DRC commands](https://opencircuitdesign.com/magic/commandref/drc.html), [Netgen source](https://github.com/RTimothyEdwards/netgen), [Xschem symbol properties](https://xschem.sourceforge.io/stefan/xschem_man/symbol_property_syntax.html), [KLayout database API](https://www.klayout.de/doc-qt5/code/class_Layout.html), and the pinned PDK assets in the companion archive.
