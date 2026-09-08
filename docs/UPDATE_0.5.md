# IC Design Studio 0.5.0 — Project and PDK workspaces

This update continues the native PySide6 desktop application from the supplied 0.4.0 handover. It is an engineering release, not a claim of Altium, Xschem or KLayout feature parity.

## Start here

1. Open **Projects** in the Project sidebar, or **File → Projects**. Open, create, forget, delete, and restore projects here. **Project settings** edits the name, root cell and linked PDK.
2. Open **Tools → PDK manager**. Select **Install package** and choose `package.json` inside one of the supplied PDK folders, or **Add folder** for an existing supported installation. Select an installed revision and **Link to project**.
3. Open **Devices** (P), choose a category and search a model. Select **Place component**, then click the canvas. R and Shift+R rotate. Every placed PDK device retains its own model identity; selecting another variant does not alter previously placed devices.
4. Use **Analysis → ngspice** for linked models; configure its executable under **Tools → Engine diagnostics & paths**. Select the PDK model corner in the Analysis panel. The generic solver refuses to substitute teaching models for PDK devices.
5. Every cell in the Project tree now exposes **Schematic**, **Layout** and **Symbol**. Select Symbol to open its editor. **Design → New custom symbol** creates a reusable cell; **Edit selected symbol** edits the selected device's local artwork or its referenced cell symbol.

## Project structure and deletion

A `.icproj` remains a readable JSON design. Folder projects retain the existing atomic `project.icstudio` manifest and content-addressed cell snapshots. The project index is a separate local workspace inventory; forgetting a project only removes its index entry.

Delete is recoverable: the selected project file is renamed beside its original location and recorded in the local project inventory. **Projects → Restore** restores it, provided another file has not taken its old name. Folder-project deletion moves only its manifest; snapshots, other files and PDK installations remain. Current unsaved edits are saved before deletion. File-hash checks prevent deleting a project modified by another session. This is application recovery, not the operating system recycle bin.

Cell rename and delete appear in Design and the tree context menu. Deleting the root, last cell, or a cell still referenced by schematic/physical instances is blocked. Valid cell deletion is undoable.

## PDK coverage in this release

| Supplied adapter/assets | Indexed primitive symbols | Placeable symbols | Evidence in 0.5.0 |
| --- | ---: | ---: | --- |
| SKY130A, pinned supplied Volare revision | 74 | 47 | Four distinct MOS models in one circuit; actual ngspice OP; native and Xschem round trips |
| GF180MCU C, Volare e6f9c8876da77220403014b116761b0b2d79aab4 | 22 | 18 | Four distinct MOS models in one circuit; actual ngspice OP; native and Xschem round trips |
| IHP SG13G2, upstream commit 5e6d592e4002946a4616f798c357f0f3c06cf3b6 | 45 | 29 | Placement, model-parameter validation, deck generation and Xschem round trips; OSDI simulation not run |

Counts refer to symbol entries, including alternative symbols, not unique qualified devices. Unavailable entries remain searchable with their specific reason. The catalog does not expose internal binned model cards as independent placeable devices. These are selected primitive/model assets; whole digital standard-cell libraries, every PDK variant, foundry PCells and verification decks are not all bundled or qualified.

PDK registration detects local `sky130A/B`, stock GF180MCU variants and `ihp-sg13g2` folder structures. It discovers recursive ngspice include dependencies, checksums assets, reads KLayout layer maps and parses declarative Xschem metadata. Exact coverage depends on the selected installed revision. Tcl, Python and dynamic symbol scripts are never executed by catalog import. Unsupported formats remain unavailable rather than producing guessed decks.

Dimensions are explicit: native MOS W/L are physical values; SKY130's supplied symbols use micron-valued model parameters, while the supplied GF180 and IHP symbols use physical values such as `0.28u`. Parameter formulas support bounded arithmetic and selected numeric functions. Unsupported strings or expressions fail visibly. Simulation evidence covers nominal operating points for the named devices, not all listed devices, corners, transient behavior or physical qualification.

IHP requires compiled OSDI models and a suitably configured simulator. The native launcher deliberately reports this missing integration. IHP decks can be exported for a separately configured ngspice environment; Studio does not yet configure or launch those compiled models. Asset discovery is not simulation qualification.

Every device reference contains PDK ID, catalog revision and device ID. Catalog revisions incorporate the files and parsed technology metadata. Older kind-based reference projects still load. An incompatible project/PDK switch is rejected; layout aliases can map only through identical GDS layer/datatype pairs. Changing device model families requires explicitly replacing devices. Removing a PDK registration retains its assets, but projects using app-installed assets must be relinked before those assets are moved into the registration archive.

## Symbol workspace

Dedicated editor window: select/move artwork, line, rectangle, ellipse, text, delete, undo/redo, wheel zoom, fit, and an exact pin-position table. Existing pin names must match the device/cell interface. Static `.sym` artwork and native JSON symbols can be imported/exported. Curves are represented by line segments on import/export; Xschem script behavior is not reproduced. Port names are entered when creating a cell; arbitrary external symbol-to-model binding still requires a supported PDK adapter.

## Layout workspace

Layer search by name or GDS number, all/none/solo visibility, selection locks, move selection to layer, fit selection, hierarchy browser and display depth. GDS/OASIS imports retain native cell hierarchy, orthogonal rotations, mirrors, array vectors and layout text. Source coordinates must fit the existing 1 nm database grid. Non-unit magnification/nonorthogonal instance transforms are rejected with an actionable message. The native model still has its previous design-size and coordinate limits.

The geometry engine remains KLayout 0.30.5. This update is the first step toward a KLayout-style editing environment. Technology PCells, advanced selection modes, editing inside hierarchy, comprehensive marker/ruler systems, large-design performance and full KLayout feature parity remain open.

## Interoperability

| Tool | Import | Export | Important boundary |
| --- | --- | --- | --- |
| KLayout | GDSII/OASIS with hierarchy and text; existing reviewed geometry update path | GDSII/OASIS, `.lyp`, editable Studio sidecars | 1 nm, orthogonal unit-scale instance transforms; PCells remain geometry |
| Magic | **File → Import Magic layout** invokes installed Magic and the selected `.tech`, then reads converted GDS | Existing **Tools → Convert GDS through Magic** | Requires real compatible Magic and matching technology; new import adapter has not been qualified by an actual Magic run in this environment |
| Xschem | Studio package edit round trip; static symbol import in editor | `.sch`/`.sym` package with model identity, pin order, model parameters and a complete simulation deck | Arbitrary third-party schematic libraries, script execution, mirrored schematic instances and unrestricted external netlisting remain incomplete |
| ngspice | New bounded editable SPICE importer; existing external testbench and raw-result workflows | Locked PDK/generic decks, including distinct models per instance | Editable import rejects unsupported statements rather than dropping their behavior; IHP OSDI launcher remains open |

The new SPICE importer supports R/C/L, independent sources, level-1 MOS cards, explicit subcircuits and supported PDK X instances. It reconstructs schematic positions from connectivity; SPICE contains no original drawing geometry. Use the external testbench workflow for richer decks that cannot yet be represented natively.

## Verification and boundaries

All 86 core tests and seven native Qt integration suites passed. The Linux bundle passed startup, dark workspace, save/reopen, rotation/undo and a background simulation at 100% and 200% display scale. The release includes the logs, PDK mixed-model evidence and screenshots. The previous 0.4.0 eight-stage SKY130 standard-cell report remains historical evidence; this update does not claim a new complete DRC/LVS/extraction run. The source and Linux bundle are tested in the available Linux environment. There is no verified Windows executable, Windows installation result or macOS qualification.

## Code map for the next update

- `project_manager.py`: project index, recoverable deletion and safe cell removal.
- `project_ui.py`: project settings/manager, installed PDK UI, catalog placement and symbol access.
- `catalog.py`: per-instance identities, model binding, safe numeric parameters and technology linking.
- `pdk_import.py`, `pdks.py`: stock-folder adapters and immutable installed package management.
- `symbol_io.py`, `symbol_editor.py`: static interchange and vector editing.
- `layout_import.py`, `layout_ui.py`: hierarchy-preserving reads and layer/hierarchy UI.
- `spice_import.py`: bounded editable netlist import.
- Existing model/history/wiring/export/worker modules continue to own their original responsibilities. New code uses their validation/history transactions.

Next priorities: expand scripted/three-terminal device adapters and full standard-cell catalogs; add IHP OSDI launch/worker management; qualify Magic import and new custom-layout DRC/LVS; add explicit replace-device/model mapping; finish the Windows build/install gate; then extend layout editing, schematic hierarchy/buses and scalability with named compatibility fixtures.

## Upstream references

- SKY130 device documentation: https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html
- GF180 model documentation: https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/HV/HV_2_6.html
- IHP technology libraries: https://ihp-open-pdk-docs.readthedocs.io/en/latest/contents/technology_libraries/index.html
- IHP upstream source: https://github.com/IHP-GmbH/IHP-Open-PDK/tree/5e6d592e4002946a4616f798c357f0f3c06cf3b6
- KLayout layer selection/hierarchy: https://klayout.de/doc/manual/selecting.html and https://klayout.de/doc/manual/cell.html

Upstream licenses/notices and package checksums accompany the supplied assets.
