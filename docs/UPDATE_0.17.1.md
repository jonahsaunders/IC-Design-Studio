# IC Design Studio 0.17.1 — Xschem dependency repair

This is a source update to the import workflow. It does not add a new device
model adapter or convert arbitrary ngspice control programs into native setups.
The underlying exchange format and supported circuits are described in
[UPDATE_0.17.md](UPDATE_0.17.md).

## Why the reported schematic cannot open

The schematic references external files; a `.sch` alone does not contain its
symbol definitions or process models. The initial dialog listed 12 missing
symbols. Inspection also found two absolute model references and a substantial
embedded ngspice control program. The previous dialog hid those dependencies
until its code symbol was located.

| Missing group | Files referenced by the reported project |
|---|---|
| Standard Xschem symbols | `lab_wire.sym`, `vsource.sym`, `gnd.sym`, `devices/code_shown.sym` |
| Process symbols under `symbols/` | `pnp_05p00x05p00.sym`, `nfet_03v3.sym`, `pfet_03v3.sym`, `nfet_05v0.sym`, `pfet_05v0.sym`, `ppolyf_u_2k.sym`, `nwell.sym`, `pplus_u.sym` |
| Process model entry points | `/foss/pdks/gf180mcuD/libs.tech/ngspice/design.ngspice` and `/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice` |

The model library is requested with `typical`, `bjt_typical` and `res_typical`
sections. The script contains loops, parameter changes, measurements and other
commands outside the native import subset. It also adds testbench devices in
the code block. These require further compatibility work with the exact models
and symbols used by the project. Resolving paths alone does not make this design
importable. Its process models must not be replaced with generic MOS or resistor
approximations to make the review pass.

## Repair missing paths

1. Choose **File → Import → Import Xschem schematic…**.
2. Use **Add library folder…** to select your Xschem installation directory,
   `xschem_library`, or its `devices` directory. Familiar subdirectories are
   added automatically, so bare and `devices/` references can both resolve.
3. Add the project or process-library directory that contains `symbols/`.
   Alternatively, select one missing row and click **Locate selected file…**.
   Choosing `symbols/nfet_03v3.sym` also supplies the enclosing library root,
   allowing other matching files in that directory to resolve.
4. For an absolute `/foss/...` model path from another installation, use
   **Locate selected file…** to select the corresponding local model file.
   Static includes inside that model may expose further dependencies.
5. Read **Review notes** for model and simulation limitations. Use
   **Copy diagnostic report** to collect dependencies, search folders and errors.

In 0.17.0, the immediate workaround for standard symbols is to add both the
`xschem_library` directory and `xschem_library/devices`. For process references
beginning `symbols/`, add the directory containing `symbols/`. This follows
[Xschem's documented library lookup](https://xschem.sourceforge.io/stefan/xschem_man/tutorial_xschem_libraries.html).
The old version cannot relocate absolute model paths through this dialog.

The updated importer discovers declarative `XSCHEM_LIBRARY_PATH` and
`XSCHEM_SHAREDIR` entries, installations next to an Xschem executable on PATH,
common installation folders and an explicitly configured `PDK_ROOT` plus `PDK`.
It remembers folders selected in the dialog. Explicit search order is retained;
automatically derived directories follow those entries. It does not run
`xschemrc`, imported scripts or Xschem itself to discover paths.

Explicit file locations apply to matching references within this review. They
take precedence over search results. Selecting an unavailable file keeps that
dependency unresolved. On successful native import, the resolved source bytes
and reference mappings are retained for export; exported model paths point to
the copied assets. File changes after review still require another review.

## Apply this source update

Extract the complete source archive into a new directory. From its
`IC-Design-Studio` folder, using Python 3.12:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

If running from an existing Python environment containing the requirements,
start the new source with `python main.py`. Source files do not update an
already packaged executable; that application must be rebuilt. This update
does not include a Windows installer or a new Linux binary.

## Validation and remaining input

254 core tests and 11 native Qt workflow checks passed. Added coverage includes
mixed symbol references, installation folders with spaces, Windows environment
discovery, explicit precedence, relocation and portable export of an absolute
model reference, stale files, early code dependencies, the Locate action,
copying diagnostics and remembered folders. Windows discovery tests simulate
the environment; no Windows application execution is claimed.

The reported schematic was reviewed directly. With no supplied libraries, the
new dialog exposes 12 missing symbols and two missing model entry points at
once, plus the control-program limitation. Supplying the available standard
Xschem library resolved all four standard symbols. Eight process symbols and
the two model entry points remain missing. No electrical qualification of this
GF180MCUD design has been performed.

Further work needs the exact `symbols/` library, the referenced GF180MCUD model
files and their includes, and the project's `xschemrc` for inspecting path
configuration. The submitted circuit itself is not bundled into this source
release. Model and script compatibility must be addressed after those assets
are available.
