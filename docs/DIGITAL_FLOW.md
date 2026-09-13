# Integrated digital design

Open **Digital → New digital counter example** or **New UART regression example**.
The digital workspace is a dock in IC Design Studio. RTL, schematic symbols,
netlists, timing, physical implementation, waveforms and regression reports share
native cells, project revisions, undo, saving and the application's job queue.

## Stages and evidence

| Stage | Engine | Captured result |
|---|---|---|
| Simulation | Icarus or Verilator | Assertions/process outcome, VCD, four-state waveform index |
| Lint | Verilator | Source-linked diagnostics |
| Elaboration / generic synthesis | Yosys | Ports, hierarchy, generic netlist and source index |
| Mapped synthesis | Yosys + locked Liberty | Standard-cell netlist, JSON index, cell count and area |
| Timing | OpenSTA | Setup/hold paths, constraint checks, default-activity power estimate |
| Equivalence | EQY + matching Yosys plugins | RTL versus the captured mapped netlist; partition outcomes and counterexamples |
| Floorplan / place / clock tree / route | OpenROAD Flow Scripts | ODB checkpoints, DEF, physical netlist, placement/route preview and engine metrics |
| Finish / GDS | ORFS, OpenROAD/OpenRCX, KLayout | Final GDS and extracted SPEF in addition to checkpoint evidence |
| Regression | Saved Icarus/Verilator cases | Individual outcomes, retained failures, waveforms and optional Verilator line coverage |

Install the engines separately and set executable paths in **Tools**, or discover
them on PATH. Verilator also needs its C++ build dependencies. Physical execution
needs GNU make and a complete ORFS checkout. Use **Jobs folder** to choose a path
without spaces for Verilator, EQY and ORFS. Tool installation and remote execution
are not bundled; these engines run locally beneath the integrated desktop UI.

## A block from RTL to layout

1. Open an example or import sources. **Apply sources** creates an undoable edit;
   saving the project also applies the editor draft.
2. Select **Elaborate** or **Mapped synthesis**, run, then **Publish symbol**.
   The compiler's actual scalar and bus ports become native schematic terminals.
   Choose the cell selector or **New RTL cell** to maintain independent blocks.
3. Use **Platform** to capture `sky130hd` or `nangate45` from ORFS, or import an
   explicit manifest. **Constraints** generates an editable clock and I/O SDC.
   **Floorplan** controls die/core rectangles in micrometres, density and threads.
4. Run **Mapped synthesis**. Select that completed run and check **Use selected
   mapped run** before running **Timing** and **Equivalence**. Both consume its
   exact netlist. Without a selected upstream, each stage first maps current RTL.
5. Run **Floorplan**, then select its result for **Place**, and continue through
   **Clock tree**, **Route**, and **Finish / GDS**. Each run captures its own
   checkpoint. A compatible selected earlier physical stage is resumed in a new
   directory; changes to RTL, platform, physical inputs or flow prevent reuse.
6. Select the finish result and run **Timing** to use its SPEF and propagated
   clocks with the current SDC. **Attach routed GDS** brings the generated hierarchy
   into the selected native cell, retaining RTL and its symbol. Signal terminals
   are mapped through captured DEF/GDS layer information. Existing layout is not
   overwritten; use the normal layout review workflow to reconcile replacements.

The view table links RTL, symbol, schematic, layout and explicitly attached
netlist/physical/extracted views. Saved views show when their sources are stale.
Compiling a symbol with changed ports on an already wired block requires interface
reconciliation. Generated macro power terminals are recorded in `digital_layout`
metadata; add them through the native circuit-interface tools before supply
routing. The current automatic attachment mapping supports `.drawing` entries
in the platform's KLayout technology file; an unmapped signal terminal is an error.

## Technology locks and supported versions

The analog model subsets shipped with Studio are insufficient for digital physical
implementation. A digital platform captures full Liberty, LEF, GDS and supporting
files independently. Files and ORFS scripts are checksummed when imported/prepared,
verified again before execution, and copied into the run. A changed installation
requires an explicit re-import or newly prepared run. One merged Liberty file per
selected corner is currently supported for mapping.

The implementation CI pins:

- ORFS `eaba6576441bf7c1743ea56ecdb1904210ec02c2` and its SKY130 HD platform;
- OpenROAD `26Q2-1164-g08f67ee5ec` and OpenSTA 3.1.0 from its Ubuntu 24.04 package;
- OSS CAD Suite `2026-09-13` for Yosys and EQY with matching plugins;
- Ubuntu 24.04 Icarus, Verilator and KLayout packages for simulation/GDS conversion.

Download archive checksums live in `.github/workflows/digital.yml`. A newer ORFS
checkout may require newer OpenROAD APIs. The selected scripts are executed as
captured; the app does not patch them or quietly downgrade a failed stage.

A custom platform manifest sits beside its files:

```json
{
  "version": 1,
  "name": "myplatform",
  "revision": "reviewed-revision",
  "directory": ".",
  "corner": "tt",
  "corners": {"tt": ["cells.lib"]},
  "files": ["cells.lib", "tech.lef", "cells.lef", "cells.gds", "config.mk"]
}
```

Include every supporting file needed by the platform configuration. The maximum
capture is 1 GiB / 10,000 files. This is an explicit file lock, not a complete
lock of transitive operating-system/compiler libraries. Engine versions, selected
executable hashes, runner source hashes, input snapshots, commands, logs and
artifact checksums remain available in each run directory.

## Inspection and verification

Diagnostics open their source line. The netlist browser links retained Yosys
source attributes to RTL and selects matching physical instances. Timing paths
highlight their cells when the result includes an upstream physical preview.
Inserted/renamed objects with no retained source mapping are identified as such.
Double-click a waveform signal to find its RTL declaration; fallback text matches
are labeled as source searches. The comparison table shows run metrics and
compatible-platform deltas; absent metrics remain absent.

Timing **INCOMPLETE** includes missing clocks/I/O constraints or no analyzable
paths. **FAIL** means a reported path violates timing. Reports cover up to 50 paths
per group for setup and hold at the selected corner, with full textual evidence.
Pre-layout timing has no extracted wire parasitics. Default propagated-activity
power is an estimate, not a workload measurement. There is no multi-corner signoff
claim or automatic false/multicycle-path correctness proof.

EQY runs sequential SAT induction at depth 30 against the actual selected mapped
netlist. **PASS**, **FAIL**, **UNKNOWN** and engine **ERROR** stay distinct. A
strategy timeout/unproved partition cannot produce PASS. State/reset assumptions
and complex designs may need another strategy; counterexamples and proof logs
are retained for investigation. A failed proof does not silently become a
successful physical qualification.

**Test cases** saves named testbench tops, simulators, definitions and optional
Verilator line coverage. **Regression** runs all cases, retaining a failed case
while continuing the others. The UART example tests reset, start/data/stop bits
for three byte patterns, and return to idle. Coverage describes instrumented code;
it does not establish exhaustive functional verification. Saved RTL cases also
appear in verification plans alongside analog testbenches. An RTL test runs once,
not once per analog temperature or supply corner. This is shared test management;
coupled analog/digital transient simulation is not implemented. An RTL-only symbol
is rejected as an analog circuit model until it has a schematic implementation.

The physical preview displays cell outlines and signal-route centerlines, bounded
to 20,000 visible instances and 50,000 segments. Inspect GDS in the native layout
editor for shapes. Finishing ORFS is separate from foundry-qualified DRC/LVS,
antenna, EM/IR and fabrication signoff. Existing native verification tools remain
available, with their own supported process/model scope.

## Portable source format and waveforms

Each cell can own a `digital` object with `version: 1`. Older root-level digital
projects retain an explicit `digital_cell` binding when loaded. Files, roles,
compilation order, include directories, defines, test cases, waveform name,
timeout, constraints and technology locks participate in project revisions.
Imports embed copies; later external-file edits do not change the saved project.

```json
{
  "version": 1,
  "top": "counter",
  "testbench": "counter_tb",
  "include_dirs": ["."],
  "defines": {},
  "waveform": "wave.vcd",
  "timeout": 60,
  "files": [
    {"path": "counter.sv", "role": "rtl"},
    {"path": "counter_tb.sv", "role": "testbench"},
    {"path": "constraints.sdc", "role": "constraint"}
  ]
}
```

Put this import manifest beside its explicitly listed files. Roles are `rtl`,
`testbench`, `include`, `data`, and `constraint`. Include headers and memory text
files explicitly. Only literal relative include and `$readmemh`/`$readmemb` paths
are portable; conditional dependencies must also be present. Sources are bounded
to 128 UTF-8 files / 16 MiB. Captured HDL/Tcl scripts execute with the user's local
OS permissions, like Studio's other installed engines; capture is not a sandbox.

Testbenches must terminate, use `$fatal(1, "reason")` on mismatches, and emit VCD
with `$dumpfile`/`$dumpvars`. The viewer preserves integer ticks, vector widths,
aliases and X/Z values, with signal selection, cursor, zoom and radix controls.
Verilator's predominantly two-state behavior differs from Icarus. Language support
is engine-specific. The bit-vector VCD reader supports 32 MiB, 2,048 declarations,
4,096 bits per signal, 200,000 changes and 64 MiB decoded values. Real/string dumps
and FST are unsupported; reduce dump scope/duration for larger designs.

## CLI and validation

```sh
python main.py --cli digital example --output counter.icproj
python main.py --cli digital example --design uart --output uart.icproj
python main.py --cli digital run uart.icproj --stage regression --output runs/uart
python main.py --cli digital run counter.icproj --stage mapped --orfs /path/to/ORFS --orfs-platform sky130hd --output runs/mapped
python main.py --cli digital run counter.icproj --stage timing --orfs /path/to/ORFS --orfs-platform sky130hd --upstream runs/mapped --output runs/timing
python main.py --cli digital run counter.icproj --stage equivalence --orfs /path/to/ORFS --orfs-platform sky130hd --upstream runs/mapped --output runs/proof
python main.py --cli digital run counter.icproj --stage finish --orfs /path/to/ORFS --orfs-platform sky130hd --upstream runs/mapped --timeout 300 --output runs/finish
```

Use a fresh output directory. `--cell` selects a native cell ID, `--platform` imports
an explicit technology manifest, and repeatable `--tool NAME=/path/to/executable`
selects engines. The older `import` and `export` commands remain available; export
alone produces an unexecuted handoff bundle, not a completed implementation.

```sh
python -m unittest tests.test_digital tests.test_digital_implementation -v
QT_QPA_PLATFORM=offscreen python tests/gui_digital.py
ICSTUDIO_TEST_ORFS=/path/to/ORFS ICSTUDIO_TEST_PHYSICAL=1 python -m unittest tests.test_digital_implementation -v
ICSTUDIO_TEST_ORFS=/path/to/ORFS QT_QPA_PLATFORM=offscreen python tests/gui_digital_implementation.py
```

Optional engine tests skip without their dependencies. `ICSTUDIO_TEST_YOSYS`,
`ICSTUDIO_TEST_EQY`, `ICSTUDIO_TEST_STA` and other engine-name overrides select
specific test binaries. CI runs actual engines, mapped gate-fault detection,
constraint failures, all five physical stages, macro attachment and extracted
timing, in addition to desktop editing, source/physical probing and cancellation.
