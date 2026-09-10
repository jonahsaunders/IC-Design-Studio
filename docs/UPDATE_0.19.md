# IC Design Studio 0.19.0 — Native project migration

This release adds a one-time path from an Xschem project to an independently editable IC Design Studio project. Native simulation uses a new SPICE generator and the shared ngspice execution service. It does not read the archived Xschem records, call Xschem, or need the original schematic/model directories after successful migration.

## Start here

1. Extract the entire Windows package and launch `ICDesignStudio.exe`. Keep its `app` and `python` folders beside the launcher. Python, Qt and ngspice are included.
2. Choose **File → Import and migrate Xschem project…** and select the top `.sch` file. For a project already opened in an older release, use **File → Migrate current Xschem project…**.
3. Review the object/dependency table. Standard symbols and the included GF180 simulation models resolve automatically. For custom libraries, add their containing folders and review again.
4. Save the native `.icproj` under a new name. A readable migration report is saved beside it. The original project remains available for recovery.
5. Press **F5**. Follow the running cases in **Analysis → Program analyses** and select a case to view its waveforms. Existing X/Y markers and measurement tools remain available.

For the supplied GF180 project, the companion migration bundle already contains `5vfullv2-native.icproj`. Open that file directly. Its full saved program runs 144 cases and can take a substantial amount of time; the analysis panel preserves the original timeout and probes.

On Windows the source ZIP also includes ngspice and its startup file. Install Python 3.12 and `requirements.txt`, then run `python main.py`. On Linux/macOS, select a native ngspice executable in Analysis → Engine setup or set `ICSTUDIO_NGSPICE`.

## What changes after migration

| Area | Native project behavior |
| --- | --- |
| Devices | Explicit terminal order and electrical emission tokens replace source format evaluation. Model names, unit conventions and expression strings are preserved. |
| Editing | Native parameter and simulation-program editors support undo. Existing native definitions can be placed again from the device library. Ordinary components and hierarchical cells can also be added. |
| Hierarchy | Child cells, ports, parameter defaults and instance overrides are retained for the supported subset. |
| Connectivity | Persistent terminal and net IDs survive save/reopen, renaming and connected moves. Moves that accidentally alter terminal connectivity are rejected transactionally. Geometry still determines intentional connection edits. |
| Models | Resolved text model dependencies are embedded with checksums. Runs materialize portable relative model paths, avoiding the previous path-with-spaces failure. |
| Analyses | Editable ngspice programs retain loops, measurements and multiple analysis cases. A schematic with no analysis gets an explicit editable operating-point setup. |
| Portability | A migrated project can move to a different folder or machine without its original Xschem source directories. The ngspice executable must be available for that host platform. |
| Recovery | Original source records are archived in the project. The simulation job omits this archive; the native execution path does not use it. |
| Export | Native projects export a SPICE deck with their model files. Exporting edited native definitions back to Xschem is not implemented in this release. |

## Meaning of the migration report

**Complete** means all reviewed objects in the declared migration scope were converted and the candidate passed connectivity and generation checks. It does **not** mean the converter has independently verified simulation equivalence for every possible circuit.

**Fixed representation** identifies a visual representation that differs from the source. **Needs attention** identifies unsupported behavior or missing dependencies. Some visual limitations permit saving a clearly labeled draft; electrical ambiguities block conversion. Source recovery is never counted as implemented native behavior.

Arbitrary Tcl-driven symbols, special global-label behavior, vector bus expansion, some symbol control flags, and graph/action objects still need explicit translation. Scalar bus labels such as `data[0]` are supported. Third-party/custom symbols and model files must actually be supplied; an open-source schematic format cannot reconstruct an absent custom model. Included simulation libraries do not constitute a complete physical verification/signoff PDK.

## Executed validation

- 287 automated regressions passed on Linux, including real ngspice simulation after removing original files and the recovery archive. Coverage includes parameterized hierarchy, edited values, missing models, unsupported Tcl, model integrity, headers with model includes, identity persistence, connected movement and accidental-net-merge rejection.
- The supplied GF180 circuit's native netlist was compared with a previously generated independent Xschem reference: **67 schematic devices, three inline test-program devices, and 46 nets; no differences**. Comparison normalizes case, continuation lines, expression whitespace and explicit `m=1` against the verified model default. This comparator deliberately rejects hierarchical reference decks; hierarchy has a separate real simulation regression.
- Actual Qt GUI tests exercised the migration report, parameter edits/undo, repeated connected moves, save/reopen in a folder with spaces and Unicode, the real simulation worker, case tables and waveform switching. Both a hierarchical divider and the supplied GF180 circuit passed operating-point, transient and AC analyses. GF180 operating-point VREF was **1.195093286891953 V**.
- The companion migration bundle contains the separate full-program qualification record and reproducible reference comparison evidence.
- The Windows package is assembled from Windows runtimes and checked for PE architecture, included libraries and file hashes. **Native Windows execution has not been performed in this workspace.** Linux execution and static packaging checks do not establish a Windows runtime pass.

The Linux test host required a workspace-local temporary-file adapter because its usual system temporary directory is unavailable. The adapter only redirects ngspice temporary-file allocation, does not change its numerical engine, and is not shipped as an application runtime dependency. Qualification metadata records this condition.

## Reproduce the acceptance checks

Core regressions, with ngspice available:

```sh
python -m unittest discover -s tests -v
python tests/gui_native_migration.py --evidence acceptance
python tests/gui_native_migration.py --project 5vfullv2-native.icproj --full --evidence full-acceptance
```

To qualify the actual extracted Windows package in PowerShell:

```powershell
& '.\app\scripts\verify_portable_windows.ps1' -Package '.'
& '.\app\scripts\verify_portable_windows.ps1' -Package '.' -Project 'C:\Projects\5vfullv2-native.icproj' -Full
```

The script requires native Windows, uses the packaged interpreter and simulator, and saves screenshots and JSON evidence. CI definitions now include real GUI/native-migration checks; adding those definitions is not evidence that a remote CI run has occurred.

The migration command is also available for reproducible conversion:

```sh
python -m icstudio.native_migration top.sch --output migrated.icproj --library path/to/custom/library
```

It refuses to overwrite an existing output and returns a nonzero result for a migration that needs attention. Use IC Design Studio 0.19 or newer to edit the new native electrical definitions.
