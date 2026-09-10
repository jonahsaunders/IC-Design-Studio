# IC Design Studio 0.17.0 — Direct Xschem project exchange

This release opens independently created Xschem schematics as editable native
projects. The previous Studio-generated package importer remains available.

## Import a project

1. Choose **File → Import → Import Xschem schematic…** and select the top `.sch`.
2. Review the dependency table. It lists child schematics, symbols and model files.
3. If a file is missing, use **Add library folder…** to add the directory that
   contains its referenced path. For `devices/res.sym`, add the folder containing
   `devices`. Multiple directories are searched in the displayed order after the
   schematic's directory. Declarative `XSCHEM_LIBRARY_PATH` entries and standard
   installation locations are suggested when present.
4. Select **Review files** after changing paths. Read **Schematics** and **Review
   notes**, then select **Open reviewed project**.
5. Save the resulting native project with **Save as…**. Imports open as unsaved
   projects and do not overwrite source schematics.

The review does not run `xschemrc`, Tcl expressions, launcher actions or imported
control scripts. Every resolved file is fingerprinted; changing one after review
requires another review. Missing dependencies and unsupported electrical constructs
block opening instead of silently changing the circuit.

## What becomes editable

| Content | Current support |
|---|---|
| Geometry | Component locations, quarter-turn rotations, mirrors, wires, labels and supported symbol artwork |
| Connectivity | Endpoints, touching pins, T-junctions, explicit labels and disconnected named nets; bare interior wire crossings remain separate |
| Hierarchy | Child `.sch` files, custom `.sym` files, ordered scalar ports, numeric defaults and instance parameter overrides |
| Native devices | Resistors, capacitors, inductors, DC/AC voltage and current sources, supported sine/pulse sources, and explicitly declared level-1 MOS models |
| Process models | Existing linked and locked PDK catalog bindings; model sections must be declared by the technology adapter |
| Analysis | Supported `.op`, `.tran`, `.ac dec` and temperature statements; the last supported analysis becomes the initial native setup |
| Properties | Nested quoted attributes, pin order from complete `sim_pinnumber` metadata, named-pin netlisting templates, and unknown declarative attributes retained for export |
| Standard symbols | Passive primitives, ground/labels, port symbols, MOS templates with empty optional fields, and the recognized standard voltage-source current-probe template |

The standard voltage-source template is translated by a specific declarative
adapter. It does not enable general Tcl evaluation. The standard global `GND`
ground symbol maps to native net `0`.

Imported source/symbol text supplies its own name/value artwork, avoiding duplicate
native captions. Labels at terminals attach to those terminals, and labels on wires
attach to their wires, so native editing can preserve their electrical attachments.

Parameter expressions use the existing bounded native arithmetic interpreter.
Unsupported expressions remain a review error. Source AC magnitude defaults to
zero when it was not specified. Nonzero AC phase, extra sine options, independent
pulse edges outside the existing native source model, and arbitrary source
expressions require a compatible external workflow.

## Export back to Xschem

Use **File → Export → Export Xschem package…** and choose a new or empty directory.
For a directly imported project this exports its native edits while preserving the
resolved source files. The export contains:

- A top `.sch` and the imported child schematics.
- Referenced `.sym` files and resolved static model/include dependencies.
- Updated component values, parameter overrides, placements and wire topology.
- Original properties, unchanged symbol records and schematic graphics/code records.
- A preservation report, plus `studio-project.icproj` and `studio-exchange.json`.

Open the exported top schematic in Xschem and add the export directory to its
library search path. Paths inside the exported sources point to copied assets.
Changed native symbol artwork receives a separate symbol where needed, so editing
one instance does not unexpectedly alter other instances that shared its source
symbol. Native MOS model edits generate an explicit model card.

Keep both Studio metadata files beside the schematics when exchanging edits. On
reimport, their matching fingerprint enables restoration of stable device/cell
identities, physical views, specifications and saved native setups. External
copies of tagged components receive distinct identities. Incompatible interface or
physical-metadata changes require reconciliation. Reimport advances the native
revision; earlier simulation evidence is not relabeled as current.

The native simulation setup and original Xschem control blocks are separate.
Changing a Studio analysis setup does not rewrite arbitrary Xschem control text.
The original blocks are preserved in the exported schematics. A changed supported
source analysis is detected on reimport; otherwise saved native setup choices are
restored from the metadata. Explicit circuit-parameter and wiring edits are exported.

A linked PDK remains a separately managed technology dependency in Studio. Its
resolved source model files are copied for exchange, but its complete registration,
rule decks and installed process environment are not replaced by a schematic export.

## Example and checks

**File → Examples → Xschem amplifier project** opens the new dependency review.
The example is a common-source amplifier with a hierarchical gain stage, resistance
and width overrides, a load capacitor and a separate illustrative level-1 model.
Its files are independently authored Xschem input, not output of Studio's exporter.
`examples/xschem-amplifier/reference.cir` is an independent reference circuit.

The automated checks cover parameter/value edits, moves, terminal order, custom
symbols, native metadata restoration, missing and changed files, unsupported models,
library search paths, hierarchy recursion, crossings, and native GUI operation.
The Linux executable is checked with offscreen Qt at 100% and 200% scaling.

External ngspice comparisons use both original and edited amplifier cases, with
121 AC samples per case, comparing amplitude and phase against the independently
written circuit. This checks the illustrative model and supported exchange subset;
it does not establish arbitrary-library or process qualification. The evidence
archive records actual engine attempts, including any startup failures.

For this build, **246 core tests and 8 new GUI workflow checks passed**. The standalone Linux app also passed 26 checks at each of 100% and 200% scale. Both
original and edited ngspice comparisons passed. The edited exported project was
also netlisted by Xschem 3.4.4 and its ngspice result matched the reference. The
unedited Xschem process exited during startup in the relocated build-host
installation; that external check remains unresolved and the combined external
report is deliberately marked **partial**. This is not a claim of complete
destination-tool qualification.

The restricted build host also required a test-only temporary-file adapter so the
external tools could create temporary files in the writable workspace. That
adapter changes temporary-file locations, not circuit calculations, and is not
part of the shipped application. The evidence archive describes the environment.

On a desktop with the engines installed, the independent check can be repeated:

```sh
python scripts/verify_direct_xschem.py --output verification/xschem \
  --ngspice /path/to/ngspice --xschem /path/to/xschem
```

Use a new output directory. A relocated Xschem installation can additionally use
`--xschem-share /path/to/share/xschem`. The script supplies its own startup settings,
retains source/reference/native/exported results, and exits unsuccessfully if a
requested external comparison fails.

## Boundaries

- Vector instances, buses, non-ground global hierarchy nets, recursive hierarchy,
  scripted library selection, and arbitrary executable netlisting templates are
  not native import targets in this release.
- Model-based devices outside the existing locked PDK catalog and supported generic
  models require a new adapter. The tool never substitutes a teaching model for an
  unknown process device.
- The importer does not reconstruct arbitrary subcircuit implementations hidden
  entirely in external model files; use a supported PDK adapter or native SPICE
  component import for those implementations.
- Custom properties and unsupported artwork are retained for export; not all are
  rendered or editable in the native canvas. Complex simulation control programs
  are not converted into native run tables.
- New native hierarchy cells that were not part of the imported project use the
  existing native handoff workflow. Direct exchange currently retains the imported
  hierarchy and supports new primitive instances within it.
- Native design limits remain 100 cells, 500 flattened devices and 5,000 wires per
  cell. Import is bounded to 1,000 dependency files, 10 MB per file and 30 MB total.
- This release provides a Linux x86_64 executable and source. It is not a qualified
  Windows/macOS binary or a fabrication signoff flow.

Format references: [Xschem file format](https://xschem.sourceforge.io/stefan/xschem_man/developer_info.html)
and [symbol attributes](https://xschem.sourceforge.io/stefan/xschem_man/symbol_property_syntax.html).
The broader Studio workflows remain documented in [UPDATE_0.16.md](UPDATE_0.16.md).
