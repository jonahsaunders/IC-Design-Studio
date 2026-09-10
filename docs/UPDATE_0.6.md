# IC Design Studio 0.6.0

Engineering release built from the supplied 0.5.0 source and PDK packages.

## What changed

### Project and PDK lifecycle

- **File → Duplicate project** creates an independent .icproj with a new project identity, the current in-memory design, and its PDK lock. The original remains open. The copy appears in Projects. Existing destination files are never overwritten. Internal object IDs remain consistent within the independent project; prior waivers are cleared.
- **Projects → Locate** reconnects a moved .icproj or .icstudio manifest. It checks the project identity before updating the workspace entry.
- **PDK manager → Locate** relocates an installed registration after checking every asset hash. **Tools → Relink project PDK folder** repairs the current project's stored asset path. Neither action substitutes a different model revision.
- **Tools → Migrate PDK revision** selects a registered revision of the same PDK, maps every used catalog entry, and previews the affected instances, models and changed defaults. The complete candidate validates before Apply. Identical GDS layer/datatype pairs are required for used layers. Apply is one undoable edit; the model corner resets to nominal. A changed project requires a fresh preview.
- **Design → Replace selected PDK device** previews compatible replacements. Instance IDs, named terminal nets, pin positions, rotation, MOS W/L and physical links remain attached. The preview identifies dropped overrides and changed defaults. A replacement must have the same kind and named terminals.
- Registration removal also checks existing projects recorded in the workspace. Recoverable project deletion, restore, root-cell selection and reference-safe cell deletion remain available.

Cross-process migration (for example SKY130 to GF180) is intentionally outside this adapter: equal terminal counts alone cannot establish process or mask equivalence. An upgraded design needs simulation and physical checks again.

### Reusable components

A component consists of a native cell's electrical schematic, its custom symbol, ordered terminals and parameter defaults.

1. Use **File → Import SPICE component** to select an explicit .subckt and copy its required subcircuits into the active project. Imported cells remain editable. Colliding cell names are renamed and object references are remapped; the original file name and hash are recorded.
2. Use **Design → Component properties** to set the name, terminal order and defaults. The selected cell schematic is the electrical implementation. Its symbol is edited through the Symbol document in the project tree.
3. Open `examples/reusable-divider.icproj` for a working example. Put expressions such as `{resistance * 2}` in primitive values. Place the component from **Devices → Custom cells**, then edit each instance's defaults in the Inspector or Instance parameters dialog.
4. Terminal reordering keeps connections. Changing the terminal set of an already instantiated component is blocked, as is removing a default with active instance overrides.

The SPICE importer now accepts parameterized .subckt declarations and X-instance overrides, including braced expressions containing spaces and nested native subcircuits. It also resolves supported primitive-prefix PDK instances against the linked catalog. Empty symbol-only cells can still be drawn and saved, but referenced empty cells produce an explicit error when simulated or netlisted.

SPICE import remains an explicit subset: R/C/L, supported independent sources, level-1 MOS model cards, supported PDK models, subcircuits and bounded arithmetic. Arbitrary behavioral sources, encrypted models, scripts and general vendor macro-model syntax are not silently converted. Use the existing external testbench action for original decks outside this subset. Parameterized native designs currently export to numerically resolved flattened SPICE; native projects retain their hierarchy and defaults.

Xschem packages preserve component terminal order and parameter overrides, including continued external edits to exported instance parameters. They preserve the supported catalog model identities. Derived PDK defaults remain live on unchanged round trips; externally changed derived values become explicit overrides. Hierarchical Xschem GUI netlisting and unrestricted third-party library round trips remain unqualified.

### PDK device coverage

| PDK | 0.5 placeable/indexed symbols | 0.6 placeable/indexed symbols |
| --- | ---: | ---: |
| SKY130A | 47 / 74 | 71 / 74 |
| GF180MCU C | 18 / 22 | 20 / 22 |
| IHP SG13G2 | 29 / 45 | 35 / 45 |

These counts describe catalog symbol entries, not separately qualified models. Unavailable entries remain visible with specific reasons. The libraries retain their upstream model content; adapters changed.

New adapters cover numeric netlist expressions, SKY130 finger-width variants, explicit terminals for upstream hidden-body connections, GF180 diode area/perimeter expressions, IHP body-connected resistors and varicap, the exact static PNP geometry template, and the IHP capacitor feed enumeration. Hidden body nets become visible terminals that must be connected explicitly. No Tcl is executed. The capacitor feed choices are derived from the upstream model's none=0, same=1, double=2 declaration.

GF180 now loads the bipolar, diode, resistor, MIM capacitor and MOS capacitor sections alongside the MOS section. ff/ss select corresponding family sections; fs/sf select mixed MOS with nominal other families.

IHP gains common slow/fast corner aliases. Each included library maps to its matching ss/ff section when present, otherwise its nominal section. Inspect the package manifest for the exact section combination; these aliases do not claim that every device family varies together.

### IHP OSDI simulation

**Tools → Simulation runtime** records explicitly selected compiled .osdi libraries, their hashes and their platform. The launcher verifies them before every native ngspice job, stages them beside the job with simple relative filenames, and inserts pre_osdi controls before circuit parsing. This handles job/profile paths containing spaces. A missing or modified library produces a setup error. Compilation and simulator compatibility remain separate checks: a file hash alone is not a simulation result.

Compile the six supplied IHP Verilog-A libraries on the target computer, pointing --pdk-root at the extracted companion archive’s ihp-sg13g2 folder:

```sh
python scripts/compile_ihp_osdi.py --pdk-root /path/ihp-sg13g2 --openvaf /path/openvaf --output /path/new-osdi-folder
```

Select the six resulting .osdi files in Simulation runtime, configure ngspice in Engine diagnostics, and choose ngspice in Analysis. Compiler logs, source dependency hashes and output hashes are retained in build.json.

The tested pairing is ngspice 42 with OpenVAF 23.5.0 producing OSDI 0.3. The newer OpenVAF-reloaded v24.0.2mob produces OSDI 0.4 and was correctly rejected by ngspice 42 during testing. OpenVAF 23.5.0 crashes on its optional `--target_cpu` argument, so the helper defaults to native compilation; `--generic-cpu` is available for compilers that support it. Rebuild on each target machine. Native binaries compiled on the test host are excluded from the portable PDK archive.

The OSDI configuration applies to Studio's native circuit simulation. Exported simulation.cir files contain the circuit and PDK model includes; an external simulator environment must configure its OSDI model loading. The explicit external-testbench action retains the original deck's own controls.

Sources used for the implementation: [OpenVAF model loading](https://openvaf.github.io/docs/getting-started/usage/), [ngspice manual](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf), and the IHP source at commit `5e6d592e4002946a4616f798c357f0f3c06cf3b6`. The source archive contains the compiler helper; the companion PDK archive contains the pinned Verilog-A sources and their source lock.

## Validation and delivery

- 95 core tests pass, including independent copies, identity-checked relocation, atomic migration/undo, terminal preservation, parameterized and nested subcircuits, external Xschem parameter edits and missing/changed/wrong-platform OSDI guards.
- All eight native Qt suites pass: smoke, wiring, labels, recovery, workflows, usability, project/PDK workspace, and the new lifecycle/component suite.
- The frozen Linux executable passes at 100% and 200% scale without development PYTHONPATH, LD_LIBRARY_PATH or LD_PRELOAD. Checks cover save/reopen from spaced paths, rotation/undo, a background transient with 501 samples, project duplication, imported component parameters and the runtime dialog.
- Real ngspice evidence includes the existing SKY130/GF180 mixed-model circuits and a four-model IHP circuit. All 51 additional checks pass: 12 SKY130, 12 GF180 and 27 IHP. The accompanying `pdk-cases/report.json` records each device, corner, result and nominal Xschem round trip. Six initial GF180 diode failures exposed the missing library sections; all twelve GF180 cases passed after that configuration was corrected.
- This restricted test host requires a temporary-file-location adapter for ngspice and locally extracted loader libraries. The adapter changes temporary storage only; it is not part of the application and is not needed for normal desktop installations. OSDI sources and ngspice models were not altered to make the tests pass.

The Linux build targets x86_64 with glibc 2.39 or newer. Extract the entire archive and run ICDesignStudio, keeping _internal beside it. Source is included. PDK installations and external EDA engines are configured separately.

The Windows workflow now includes the new lifecycle/component tests, PDK workspace tests, usability tests, automatic Inno Setup provisioning and the expanded installed-app probe. It runs on manual dispatch or relevant pull requests when this source is hosted in a repository. **No Windows runner was available for this delivery: there is no verified Windows executable or installer.** Read WINDOWS_RELEASE.md to run the build and retain installer evidence. No repository or CI run was published from this workspace.

## Remaining milestones

The next major milestone remains a custom transistor-level layout with Magic DRC, Netgen LVS, extraction and post-layout ngspice, followed by automated external edit/reimport fixtures. This release does not rerun the historical 0.4 SKY130 stock-cell DRC/LVS report or qualify the 0.5 Magic import adapter. KLayout-scale editing, PCells, routing, complete process libraries, unrestricted round trips and full xschem/KLayout parity remain future work.

## Code map

- lifecycle.py / lifecycle_ui.py: project copies and relocation, PDK migration/replacement previews, component and runtime actions.
- components.py / spice_import.py: reusable electrical cells, ordered terminals, parameterized imports and hierarchy.
- osdi.py / engines.py: model hash checks, per-job library staging and preloading.
- pdk_import.py / catalog.py: declarative PDK adapter expansion and emitted-parameter reconciliation.
- scripts/compile_ihp_osdi.py / verify_release_pdks.py: reproducible model compilation and real simulator regressions.
- tests/test_lifecycle.py / gui_lifecycle.py: new domain and desktop regressions.
