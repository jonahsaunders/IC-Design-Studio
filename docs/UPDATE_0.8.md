# IC Design Studio 0.8.0

This release adds saved testbenches, reusable physical hierarchy and a complete three-stage SKY130 ring oscillator workflow. Three schematic instances share one editable inverter layout. The selected saved fixture supplies the stimulus, loads, corner, temperature, startup, probes and measurements for both schematic and extracted-capacitance simulation.

## Start with the ring oscillator

1. Extract the entire companion PDKs-and-Evidence archive and open `ring-oscillator.icproj`. Keep it beside `sky130A` initially; its model path is relative. Save a working copy wherever you prefer.
2. Configure separately installed Magic, Netgen and ngspice in **Tools → Engine diagnostics & paths**. The executed tools are Magic 8.3.683, Netgen reporting 1.5.132, ngspice 42 and Xschem 3.4.4. The Linux app bundles Python, Qt and KLayout, while these external engines remain separate installations.
3. Select `ring_oscillator`, choose Layout, and open **View → Physical workflow**. The supplied layout is ready to verify. Its hierarchy tree contains X1, X2 and X3, all referring to `inverter`.
4. Choose **Check connections**, then **Run physical verification** with `ring_nominal` selected. The background worker retains its immutable project and testbench snapshot, generated decks, native Magic cells, scripts, logs and measurements.
5. A complete pass requires schematic measurements, zero full Magic DRC violations, a unique Netgen match without property errors, capacitor extraction and passing post-layout measurements. A blocked or failed stage prevents later stages from reporting success.
6. Use **Before layout** and **After layout** to inspect n1, n2 and out. The comparison displays oscillation frequency. **Evidence folder** opens the underlying run. Changing either the circuit or saved bench marks the report stale.

For a fresh design, install `sky130A/package.json` through **Tools → PDK manager**, link it to the project, and choose the **SKY130 ring oscillator** New project template or **File → New SKY130 ring oscillator**. **Generate layout…** previews the physical implementation. Applying the review is one undoable transaction.

The default circuit uses three inverters, each with WN=1 µm, WP=2 µm and L=0.15 µm. The fixture has a 1.8 V supply and 5 fF output load. Its 8 ns transient starts from explicit initial conditions and measures settled rising-edge periods from 2 to 8 ns. These startup conditions demonstrate simulation behavior; they do not prove silicon startup under noise, process mismatch or power ramp variation.

The current native workspace is described in [the interaction guide](UPDATE_0.15.md).

## Saved testbenches

Open **View → Saved testbenches**. New, Edit, Duplicate and Delete operate on saved definitions; edits and deletion can be undone. **Open fixture** exposes the source/load schematic. **Open circuit** navigates to the DUT physical view. A bench can run while another cell is active; the result remains associated with the correct fixture or DUT.

The native editor has three tabs:

- **Analysis and fixture:** choose a fixture, transient/OP/AC/DC analysis, model corner, temperature and relevant analysis settings. UIC starts a transient directly from its configured initial conditions.
- **Probes and startup:** choose observed fixture nets and optional initial voltages.
- **Measurements:** add frequency, inverting delay, voltage or range checks, observation windows, thresholds and limits. Frequency requires several complete settled cycles; a static output fails. Range checks every sampled value within the window. Voltage uses the last returned sample, or an explicit coordinate in the saved definition. AC voltage values are magnitudes.

Each fixture currently contains exactly one DUT X instance plus independent V/I sources and R/C/L loads. Put further circuit hierarchy inside that DUT. Ground uses net `0`. Multiple DUT instances in the fixture and DUT instance parameter overrides are rejected; use a concrete circuit cell. This is a bounded saved-bench model, not arbitrary behavioral SPICE editing. Existing external-deck execution remains available for broader simulator syntax.

**File → Export saved SPICE testbench…** writes one SPICE file containing the resolved native DUT, saved sources/loads and analysis. Its PDK includes retain local locked-model paths; keep those models available or update paths in the external tool. Native project save/reopen preserves the editable bench definition.

## Linked physical hierarchy and layout editing

Declare the electrical child ports and create its physical view. **Design → Assign cell layout port…** associates each port with a conductor coordinate and extraction label. **Place linked physical instance…** places an existing schematic X instance with position, right-angle rotation and optional mirror. One electrical instance maps to one physical placement. Shared geometry with different instance parameter values requires separate concrete cell variants.

Select an instance in either view to highlight its counterpart. **Enter selected physical cell** and **← Parent** navigate the reusable layout. Editing a child changes every placement that references it. Derived terminal positions follow whole-instance movement, rotation and mirroring. Routes in the parent remain at their drawn coordinates and need reconnecting when access locations change.

Layout commands now include:

- Numeric translation, right-angle rotation and mirroring about an explicit grid-aligned pivot.
- Keyboard movement of whole instances; duplication creates both a new electrical instance and its linked physical placement in one undoable operation.
- Manhattan path drawing, adjustable path width and snapping to nearby terminals, ports and vertices.
- A path-vertex table for exact edits and **Route linked terminals…** for bounded obstacle-aware routes between compatible endpoints.
- Existing searchable layers, visibility, solo, selection locks, layer reassignment, hierarchy depth, ruler and Boolean operations.

Complete generated-footprint selection moves that footprint's assigned device terminals with it. Partial geometry edits leave assigned terminals fixed. Named cell ports are explicit coordinates; use the port assignment action to update them when moving an entire cell's geometry. All geometry edits require connection review and actual verification.

Ring regeneration replaces the parent routes, placements and port labels while reusing its child layout. Inverter regeneration replaces all geometry and labels in that inverter cell, including manual edits. Device regeneration replaces the selected recorded footprint; rotated or mirrored footprints require deliberate rebuilding instead of an ambiguous axis-aligned replacement.

## Multi-finger SKY130 devices

The native generator supports the standard four-terminal `sky130_fd_pr__nfet_01v8` and `sky130_fd_pr__pfet_01v8`, direct W/L parameter emission, multiplicity one, and integer nf from 1 to 8. W is total channel width; each finger uses W/nf. Multi-finger devices share alternating source/drain diffusion and include explicit gate, source, drain and body access.

Total W must be 0.42–10 µm, L 0.15–10 µm, and W/nf at least 0.42 µm on the 5 nm grid. Cell/global parameter defaults are resolved before generation and recorded for stale-geometry checks. These are accepted input bounds, not exhaustive qualification of every size. Executed multi-finger cases and their exact dimensions are listed in the companion regression report. Other voltage/model variants need separate geometry adapters.

Netgen's pinned SKY130 setup merges compatible parallel MOS devices and compares resulting dimensions/connectivity. Its ignored properties include nf. Consequently, an LVS pass alone does not prove a particular finger topology. The generator tests count gates and check source records; independent extraction and simulation validate the executed geometry cases.

## Verification and interchange boundaries

The generalized physical flow targets the selected SKY130 DUT hierarchy. It numerically flattens the schematic reference to resolve parameters for LVS; the native project, physical placements, GDS and extracted subcircuits retain hierarchy. Both simulations use the same saved fixture, with only the DUT implementation substituted. Extraction includes capacitance, without distributed wire resistance. There is no claim of density/antenna closure, reliability analysis, complete timing closure or fabrication signoff.

| Tool / format | 0.8 verification |
| --- | --- |
| KLayout 0.30.5, GDSII/OASIS | Real database edits, shared-instance identity/transform round trips, reviewed parent geometry changes and full ring re-verification. This exercises the database API, not the interactive KLayout GUI. |
| Magic 8.3.683, `.mag` | Native parent and child cells saved, parent metal painted with Magic, hierarchy converted to GDS, reviewed and re-verified. Keep referenced child files beside the parent. |
| Xschem 3.4.4, `.sch`/`.sym` | Headless netlisting of the three-level hierarchy, ngspice oscillation, shared-child width editing and native reimport with cell references and nets retained. Import requires Studio-generated package metadata and known locked symbols. |
| ngspice 42, SPICE | Saved source/load fixture, model corners, startup and measurements drive native and extracted circuits. The existing native SPICE import subset and external-deck path remain available. |

**File → Review imported layout changes** previews GDSII/OASIS changes before applying them. Exported instance property 126 holds its Studio ID. Supported external edits that retain this property preserve the electrical link even when a placement moves. Without it, exact cell/transform matching can recover a placement; unmatched instances need explicit relinking. Changed polygons lose old device/net tags, while unchanged geometry retains identity. Imported changed port text updates the corresponding physical port coordinate. The source-link audit does not substitute for actual extraction of edited geometry.

SKY130A, GF180MCU C and IHP SG13G2 model/symbol packages are included unchanged from 0.7, with revisions `b19a81c06779a79d`, `a1610a6b160f44d6` and `4a83d130587a7404`. Their placeable/indexed catalog counts remain 71/74, 20/22 and 35/45. GF180/IHP native physical generators are still pending. IHP requires host-compatible OSDI builds selected in **Tools → Simulation runtime**; see the existing source build guide. Historical catalog evidence is retained separately and is not represented as a fresh 0.8 model qualification.

## Executed 0.8 checks

- The final standalone Linux executable passes native probes at 100% and 200% scaling with development Python/loader overrides removed, including saved-bench editing and persistence. It also completes the entire ring physical flow from the portable example using an output path containing spaces.
- 114 core regressions and ten native Qt interaction suites pass. The new coverage includes bench validation/persistence, shared physical links, transforms, multi-finger geometry, external placement identity and Magic port datatypes.
- The real desktop runs the complete ring physical flow from its fixture view, runs the saved electrical bench from the DUT view, opens post-layout waveforms, and marks both results stale after a bench edit.
- Actual ngspice OP, transient, AC and descending DC saved-bench cases reproduce analytic divider results.
- Eighteen hierarchical/interchange cases produce their expected outcomes: ten complete physical-flow passes, two Xschem netlisting/edit/simulation passes and six deliberate rejections.
- The negative cases cover parent DRC, an open ring connection, incorrect child channel length, inconsistent measurement limits, excessive measured frequency and absent oscillation. Layout faults cannot reach a passing post-layout result.

| Ring fixture | Schematic frequency | Extracted-capacitance frequency |
| --- | ---: | ---: |
| 1.8 V, nominal, 27 °C | 5.847 GHz | 3.757 GHz |
| 1.8 V, ss, 27 °C | 4.137 GHz | 2.668 GHz |
| 1.8 V, ff, 27 °C | 7.758 GHz | 4.979 GHz |
| 1.6 V, nominal, 85 °C | 4.689 GHz | 3.010 GHz |

The 2/3/4/8-finger cases use WN = 1/1.5/2/4 µm and WP = 2/3/4/8 µm respectively, with L = 0.15 µm. Each passes full DRC, unique LVS and extracted-capacitance simulation.

The companion archive's `EVIDENCE-0.8/hierarchy-regression.json` is the consolidated matrix. Original failures and successful targeted rechecks are both retained. One test initially confused invalid limits with a measured limit failure; both cases are now separately verified. The first Magic round trip exposed datatype-16 port labels; the importer was fixed and the complete Magic case rerun successfully. `EVIDENCE-0.6` and `EVIDENCE-0.7` preserve historical qualification separately.

Magic was built from upstream tag 8.3.683. Netgen was built from tag 1.5.133 and reports 1.5.132. This restricted host used local Tcl/loader paths and a temporary-file-location adapter for ngspice. The adapter affects storage only, is excluded from the executable and PDK packages, and is unnecessary on a conventional desktop. No engine algorithm or model was changed to force a passing result.

## Reproduce

Use new or empty output directories. Replace `python main.py` with the bundled executable for frozen-app commands.

```sh
python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen python tests/gui_hierarchy.py

python main.py --cli testbench /path/ring-oscillator.icproj \
  --testbench ring_nominal --output /path/new-bench \
  --ngspice /path/ngspice

python main.py --cli verify /path/ring-oscillator.icproj \
  --testbench ring_nominal --output /path/new-physical-run \
  --magic /path/magic --netgen /path/netgen --ngspice /path/ngspice

python scripts/verify_hierarchy.py --pdk /path/sky130A \
  --output /path/new-regressions --magic /path/magic \
  --netgen /path/netgen --ngspice /path/ngspice --xschem /path/xschem

python main.py --cli magic-import --source /path/edited.mag \
  --technology /path/sky130A/libs.tech/magic/sky130A.tech \
  --executable /path/magic --output /path/new-conversion
```

The optional verification-script `--xschem-workdir` supports relocated Xschem shared data. Conventional installations do not need it. Physical evidence retains absolute test-host paths for traceability; portable examples beside the PDK packages are the rerun entry points.

The Linux x86_64 bundle targets Ubuntu 24.04 / glibc 2.39 or newer and contains the complete source. The Windows pipeline includes the new tests and saved-bench probe, but **no Windows runner was available: there is no verified Windows binary or installer in this delivery**. Automatic Windows/WSL engine setup remains pending.

Development entry points: `testbenches.py`, `testbench_ui.py`, `physical_cells.py`, `hierarchical_flow.py`, `hierarchy_ui.py`, `ring_oscillator.py`, `sky130_fingers.py`, `tests/test_hierarchy.py` and the verification scripts above. Subsequent work should extend physical adapters to GF180/IHP, qualify more reusable circuit classes, improve routing/constraint editing, add distributed parasitic extraction, and execute the Windows release gates. Complete KLayout/Xschem feature parity remains a longer-term goal.

Primary references: the pinned SKY130 model/symbol and Netgen setup files, [Magic ext2spice commands](https://opencircuitdesign.com/magic/commandref/ext2spice.html), [SKY130 periphery rules](https://skywater-pdk.readthedocs.io/en/main/rules/periphery.html), and [KLayout database API](https://www.klayout.de/doc-qt5/code/class_Layout.html).
