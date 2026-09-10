# IC Design Studio 0.18 — Xschem projects

For the simulation startup fixes and the source download with Windows ngspice included, see [the 0.18.1 patch guide](UPDATE_0.18.1.md).

Open a `.sch` file directly from **File → Open project**. Standard Xschem symbols and the public GF180MCU primitive simulation library are included in the desktop packages. A complete import opens immediately; dependency review appears when a custom file needs attention.

## Opening your GF180 schematic

On Windows, extract the entire portable package and double-click **ICDesignStudio.exe**. Keep the `app` and `python` folders beside it. Python, Qt, KLayout and the ngspice console runtime are included. You can also drop a `.sch` or `.icproj` file onto the executable.

Choose your schematic in File → Open project. The importer recognizes GF180 symbols and relocated model paths such as `/foss/pdks/gf180mcuD/libs.tech/ngspice/`. It uses project-local files and explicit library folders first, then the included library. Common GF180 environment-variable paths are resolved without running configuration scripts. Imported schematics, symbols and model bytes are retained in the saved `.icproj`, so reopening it does not depend on the original installation.

Missing custom symbols appear as labelled placeholders. The project remains openable for inspection and editing; simulation waits for the actual missing files. Pin positions and model definitions are never invented.

## Editing

The schematic remains editable: select, move, stretch, rotate, mirror, wire, label, duplicate and undo using the existing capture tools. Imported symbol artwork stays visible when zoomed out. The Inspector provides **Edit Xschem properties** for dimensions, model names and other source properties. Values remain SPICE expressions rather than being converted to teaching-model parameters.

**Component** opens a searchable Xschem/GF180 symbol browser for an imported project. It also accepts a custom `.sym` file. Use the net-label and ground tools for labels. Hierarchical components enter through schematic import so their child schematics can be collected with them.

## Running the simulation program

Press **F5** or **Run**. The Analysis Inspector shows the preserved ngspice program, the waveform probes to retain and the maximum runtime. Edit the program there or from Analysis → Edit Xschem simulation program.

The simulator executes the program's analysis commands, loops, resets, parameter changes, measurements and file outputs. Program variables use ngspice's canonical identifier case. Known directory-creation/listing commands are handled by the application, and the original output directory is relocated into the run's own folder. Unrecognized operating-system commands require an explicit external workflow; they are not silently ignored.

**Analysis → Xschem analyses** lists each captured operating-point, DC, transient or AC analysis, including loop conditions. Completed cases can be opened while subsequent analyses run. **Simulation Explorer** retains the outer job, its input snapshot, log and lifecycle; multiple saved programs can use the existing run queue. Stop controls cancel the worker and its simulator process.

Waveform probes use expressions such as `v(vref) v(avdd) v(v1) v(v2) i(vdd)`. They select the additional waveform files retained by Studio; the program's own `save`, `meas` and `wrdata` commands remain in the program. Raw files retain every saved sample. Use the waveform selector to switch cases and the waveform calculator for derived expressions.

Use **X** for a coordinate readout, **Y** for a whole-trace limit, and **X/Y** for a trace-at-X threshold test. Enter exact coordinates with engineering suffixes, or drag markers on the plot. Equality passes; positions outside the trace are labelled out of range. AC interpolation follows the logarithmic frequency axis.

**Open output files** opens the run folder containing original and executable netlists, copied models, the library lock, engine log, case index, raw waveforms and the program's output files. A completed program is not a claim that the circuit meets its design specifications. Simulator or measurement diagnostics produce **Needs review**.

## Export and reimport

File → Export Xschem package writes schematics and their source assets together. Geometry and property edits are included. Native project/cell/component identities, specifications and associated native views are restored when the matching metadata pair accompanies a reimport. Edits to the native metadata are detected. A known older voltage-source template is expanded declaratively during export so it also netlists in newer Xschem versions.

File → Export SPICE deck exports the circuit and its model files into a new folder. The circuit retains the original device parameters and simulation program. It does not use the built-in teaching solver.

## Included libraries and boundaries

The exact source paths, revisions and SHA-256 hashes are recorded in `icstudio/assets/exchange/index.json`. The GF180 primitive library is pinned to commit `4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c`. It includes the 5 V MOS devices and PNP/resistor symbols referenced by the supplied bandgap schematic. Library repairs retrieve this exact public revision into the user's application data folder. Normal import is offline.

This release covers scalar terminals, declarative SPICE symbol formats, supported schematic hierarchy and ngspice control analyses. Arbitrary Tcl netlisting programs, vector buses, generated symbols, custom private libraries and operating-system scripts are not universally interchangeable. Those projects can require their actual source dependencies or an external Xschem workflow. The included GF180 assets cover schematic capture and simulation; physical extraction rules and foundry signoff remain separate.

## Validation

The supplied bandgap schematic opens with 68 editable components (67 electrical components and one simulation program), 380 wire segments and 88 placed labels. Its referenced symbols and models resolve offline. A comparison against an actual Xschem-generated netlist matches all 67 electrical components and all 46 connected nets, including device parameters. Save/export/reimport tests preserve native identities and specifications.

Automated checks cover the existing native features, new import/path/metadata cases, binary waveform parsing, the real ngspice worker, analysis-table navigation, property editing/undo and exact X/Y PASS/FAIL checks. See the accompanying validation report for the full characterization and packaged-runtime results.

The Windows package is assembled from official Windows CPython, Qt/PySide6, KLayout and ngspice distributions with a relocatable native launcher. Windows execution has not been qualified on a Windows machine in this environment. Static package checks do not replace that test. The package includes the same `--release-test OUTPUT_FOLDER` desktop test entry point for checking it on Windows. Linux runtime tests are reported separately.

## Building

Source requirements are pinned in `requirements.txt`. `scripts/package.py` builds for its host platform and can include a platform-matching ngspice binary through `ICSTUDIO_BUNDLED_NGSPICE`. `scripts/assemble_windows.py` assembles the portable Windows package from the official embeddable Python archive, matching Windows wheels and the ngspice console distribution. Its runtime manifest records the exact input and output hashes. No external repository is published by these scripts.
