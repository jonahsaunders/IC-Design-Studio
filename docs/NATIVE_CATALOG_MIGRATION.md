# Native catalog migration — experimental

Imported Xschem designs can now use Studio's editable PDK catalog devices while
retaining their captured model libraries, simulation programs, hierarchy and
symbol artwork. The project remains an independent `.icproj` document.
PDK devices continue to use ngspice; migration does not replace process models
with the built-in solver's generic models.

## Import and link missing files

1. Choose **File → Import and migrate Xschem project…** and select the top `.sch`.
2. Open **Missing files / dependencies**. Select a missing symbol or model and
   choose **Link selected file…**, or double-click its row. The reference's
   originating schematic appears below the table.
3. Select the actual local file. **Add library folder…** can resolve a whole
   library; selecting a file also makes its library folder available for siblings.
4. Review the updated dependency list. A link applies to the schematic that
   references it, allowing different files with the same name in different cells.
   Dynamic references such as `$CUSTOM_LIBRARY/device.sym` can be linked explicitly.
   Linking files never executes Xschem startup scripts.

The ordinary Xschem import review also supports per-file links and double-click
repair. Linked dependencies become embedded assets when migration is saved.
Changing an input file after review disables saving until **Review again** runs.

## Match native devices

1. In the migration dialog, choose a registered revision under **Target device
   library**. The File menu stays technology agnostic. The same catalog-driven
   matcher works with registered GF180, SKY130, IHP or future adapter packages;
   process names are not hard-coded in the matcher.
2. Review **Devices**. A unique model match is selected automatically. When a
   model has several symbols, the original symbol identity helps select its
   corresponding entry. Remaining ambiguities have a **Catalog match** selector.
3. Keep **Require all model devices to match** checked to prevent saving a
   partial catalog conversion. Uncheck it to save a migration draft that retains
   unmatched devices as editable native SPICE definitions.
4. Save to a new `.icproj` filename. A `.migration.json` report is written beside
   it. The original source remains intact.

For an already-open compatible or native project, choose **File → Migrate current
project to native…**. **Help → Native migration report…** shows the saved device
matches and the original interpretation warnings.

Matching checks the model name and instance prefix, emitted terminal order,
physical parameter units, arithmetic expressions and captured model-file hashes
against the selected package. It retains terminal identities, net names and IDs,
pin positions, control programs and explicit LVS formats. Dimension-dependent
area and perimeter expressions remain live when width or length changes. Symbol
text reflects the edited catalog parameters. Existing physical bindings that
need a terminal-role change require review before conversion.

Unresolved global parameter expressions, incompatible parameter sets or a
different model revision remain visible as unmatched; they are never silently
approximated. Numeric primitives and source waveforms retain their native SPICE
definitions. Executable-symbol metadata and other source warnings remain in the
report even when every model device matches. A successful conversion is not a
numerical-equivalence or foundry signoff result.

The saved model closure and catalog metadata support reopen, editing, SPICE
export and Xschem exchange without the original source folder or registered PDK
installation. Models outside that captured closure require another import and
review. Xschem exchange rejects changed PDK model files until a new migration is
reviewed; it accepts electrical parameter edits against unchanged models.

IHP needs an appropriate installed adapter and compatible ngspice/OSDI runtime.
This feature does not supply missing OSDI binaries or add arbitrary Tcl execution
or vector-bus conversion. Those existing runtime/import limits still apply.

## Command line

```sh
python -m icstudio.native_migration top.sch --output migrated.icproj \
  --pdk-manifest /path/to/package.json --registry /path/to/registry \
  --library /path/to/symbol-library
```

Optional `--links links.json` supplies reference-to-local-file mappings. A scoped
key is the absolute parent schematic filename followed by `::` and its reference.
Optional `--matches matches.json` maps `cell-name/device-name` to a catalog key.
`--allow-unmatched` permits a draft. A report is produced even if no candidate
can be saved. Exit code 2 means the review still needs attention.

## Bugs addressed in this update

| Issue | Result |
| --- | --- |
| Engine choice leaked between projects and was not saved | Generic projects restore their own saved choice; native/PDK projects show why ngspice is required. Saving also commits pending analysis settings. |
| Missing dynamic dependencies had no repairable row | They appear in the dependency table and accept explicit file links. |
| One filename link could override references in other schematics | Explicit links are scoped by originating schematic. |
| Pin-role conversion renamed automatic nets | Unchanged terminal groups retain their generated net names and stable identities. |
| Catalog devices took generic emission paths in native projects | Simulation and Xschem export emit the selected catalog model and correct units. |
| Catalog text could show stale dimensions | Artwork substitutions use current catalog parameters. |
| Include-path rewriting invalidated catalog proofs on round trips | Proofs follow verified, unchanged model files into the newly embedded paths. |
| Exchange review omitted catalog parameter edits | Catalog references, dimensions and model parameters participate in change reporting. |
| Windows label-drag acceptance used a font-dependent coordinate | The test drags from the actual rendered text bounds. |
| Linux release probe expected removed SKY130-specific wording | The probe checks the technology-agnostic physical workflow and prints failures to CI logs. |

Validation includes the full unit suite, dependency-linking and engine-persistence
GUI checks, the release probe from source, the bundled GF180 bandgap (60 model
devices) and SKY130 inverter (2 model devices), formula and LVS preservation,
source-free save/reopen and exchange, and rejection of changed model files.
Tests for other process identifiers exercise the common adapter contract; they
are not real IHP model or OSDI qualification. Native Windows execution, the frozen
desktop package and numerical before/after comparisons remain CI/runtime gates.
