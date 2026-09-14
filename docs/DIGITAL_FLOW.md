# Integrated digital design

Open **Digital → New digital counter example**, **New UART regression example**, or
**New APB FIFO peripheral**. Digital design occupies the main document workspace. RTL, schematic symbols,
netlists, timing, physical implementation, waveforms and regression reports share
native cells, project revisions, undo, saving and the application's job queue.

![Digital source and waveform workspace](images/digital-workspace.png)

See [workspace commands and design decisions](DIGITAL_WORKSPACE.md) for the pane
layout, target runs, constraints, language server, indexed waveforms and macro export.

## Stages and evidence

| Stage | Engine | Captured result |
|---|---|---|
| Simulation | Icarus or Verilator | Assertions/process outcome, VCD, four-state waveform index |
| Lint | Verilator | Source-linked diagnostics |
| Elaboration / generic synthesis | Yosys | Ports, hierarchy, generic netlist and source index |
| Mapped synthesis | Yosys + locked Liberty | Standard-cell netlist, JSON index, cell count and area |
| Timing | OpenSTA | Setup/hold paths, constraint checks, default-activity power estimate |
| Equivalence | EQY, Yosys, SBY and Bitwuzla | RTL versus the captured mapped netlist; partition outcomes and counterexamples |
| Floorplan / place / clock tree / route | OpenROAD Flow Scripts | ODB checkpoints, DEF, physical netlist, placement/route preview and engine metrics |
| Finish / GDS | ORFS, OpenROAD/OpenRCX, KLayout | Final GDS and extracted SPEF in addition to checkpoint evidence |
| Regression | Saved Icarus/Verilator cases | Individual outcomes, retained failures, waveforms and optional Verilator line coverage |

## Included tools and first setup

Release builds include the digital engines, their C++ compiler/build dependencies,
Python, Tcl, shared libraries, a compatible ORFS revision and full SKY130 HD files.
**Tools → Set up and verify** installs them under your user profile without PATH
edits or individual tool downloads. Setup runs automatically on first ordinary
launch, and the Windows installer also attempts setup before launching Studio.
Allow several minutes and several GB of disk space. **Ready** requires successful
Icarus simulation, UART regression with Verilator coverage, mapped synthesis,
equivalence, timing, GDS/SPEF generation and extracted timing. Logs and results stay
in the setup evidence directory. An installation failure never produces Ready.

Linux x64 uses a private native runtime with an Ubuntu 24.04 / glibc 2.39 baseline.
Windows x64 uses an app-owned WSL 2 distribution. If WSL is unavailable, **Enable
Windows Linux support** invokes Windows' administrator prompt; Windows may require
a reboot. Reopen Studio and retry setup afterward. The engines and platform are
already included; users do not install a Linux distribution or set Linux paths.
Setup does not replace or unregister other WSL distributions. User-installed
runtimes and setup evidence survive an application uninstall.

New digital projects receive the included SKY130 HD lock after setup succeeds.
Existing platform selections and custom executable settings are preserved.
**Custom tool paths** selects an external toolchain when any override is set;
remaining tools then resolve from PATH. A source checkout without a built runtime
continues to support this manual configuration. Custom Verilator needs a C++
compiler and make, and custom physical runs need ORFS. Use a jobs path without
spaces for those custom workflows. Managed jobs use private temporary Linux paths
and copy their captured results back, including when the Windows jobs folder has
spaces. Cancellation targets the job's process tree, not the entire distribution.

Release builders run `python scripts/build_digital_runtime.py` on Linux with
Docker, then `python scripts/qualify_digital_runtime.py` on each target OS. Users
do not need Docker. `scripts/package.py` refuses a missing, damaged or unqualified
payload. `ICSTUDIO_DIGITAL_PAYLOAD` and `ICSTUDIO_DIGITAL_STATE` let development/CI
use isolated package and installation directories.
Headless installs can use `ICDesignStudio --cli digital setup`; readiness is
available as JSON with `ICDesignStudio --cli digital status`.

## A block from RTL to layout

1. Open an example or import sources. **Apply sources** creates an undoable edit;
   saving the project also applies the editor draft.
2. Select **Elaborate** or **Mapped synthesis**, run, then **Publish symbol**.
   The compiler's actual scalar and bus ports become native schematic terminals.
   Choose the cell selector or **New RTL cell** to maintain independent blocks.
3. Use the included SKY130 HD platform, or use **Platform** to capture another
   `sky130hd` / `nangate45` ORFS revision or an explicit manifest.
   **Constraints** generates an editable clock and I/O SDC.
   **Floorplan** controls die/core rectangles in micrometres, density and threads.
4. Choose **Run to placement**, **Run to routing**, or **Run to GDS**. The durable
   target plan maps RTL, builds each required physical stage, then runs timing.
   **Verify block** runs lint, simulation/regression, mapping, equivalence and timing.
   A failed or incomplete check stops the plan. Resume rechecks the captured inputs
   and artifacts; a new target captures current edits.
5. Compatible results are reused automatically. **Run stage** also selects a
   compatible upstream netlist/checkpoint. **Pin selected upstream run** gives
   explicit control for an experiment. Raw SDC edits invalidate timing/physical
   results; generated clock/I/O intent also drives the synthesis budget.
6. Select the finish result and **More → Attach implemented macro** to bring its
   generated hierarchy into the native cell, retaining RTL and its symbol.
   **More → Export implemented macro** writes GDS, abstract LEF, netlist, SDC,
   SPEF and terminal/provenance metadata. The bundle does not contain a
   characterized macro Liberty model. DRC/LVS are separate checks.

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
- OSS CAD Suite `2026-09-13` for Yosys, EQY with matching plugins, SBY and Bitwuzla;
- The included package uses OSS CAD Suite's Icarus and Verilator, and Ubuntu
  24.04 KLayout/compiler packages; the separate implementation CI also tests
  Ubuntu's Icarus and Verilator.

Download archive checksums live in `packaging/digital/Dockerfile` and
`.github/workflows/digital.yml`. The generated package manifest records the
exported image/archive identity, exact installed package versions and a file lock.
Base OS package updates are captured and must pass the release acceptance again;
the Docker recipe alone is not a bit-for-bit reproducible OS package lock.
Licenses and package copyright files are retained in the runtime alongside source
locations. A newer ORFS
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
capture is 1 GiB / 10,000 files. Custom installations lock the selected files,
without capturing all transitive operating-system/compiler libraries. The managed
runtime additionally checks its included files before dispatch. Engine versions, selected
executable hashes, runner source hashes, input snapshots, commands, logs and
artifact checksums remain available in each run directory.

## Inspection and verification

Run diagnostics open their captured source revision in a read-only pane.
Live language-server diagnostics open the working copy. The netlist browser links retained Yosys
source attributes to RTL and selects matching physical instances. Timing paths
remain visible above a linked physical view and highlight their cells when the
result includes an upstream physical preview.
Inserted/renamed objects with no retained source mapping are identified as such.
Double-click an EQY partition to inspect its retained counterexample. A failed
regression case can also open its waveform up to the assertion failure.
Double-click a waveform signal to find its RTL declaration; fallback text matches
are labeled as source searches. The comparison table shows run metrics and
deltas only for matching constraints, technology, synthesis settings, corners,
parasitic mode and engine context; absent metrics remain absent.

Timing **INCOMPLETE** includes missing clocks/I/O constraints or no analyzable
paths. **FAIL** means a reported path or electrical slew/capacitance/fanout check violates constraints. Reports cover up to 50 paths
per group for setup and hold at each selected library corner, with full textual
evidence, total negative slack and per-corner reports.
Pre-layout timing has no extracted wire parasitics. Default propagated-activity
power is an estimate, not a workload measurement. There is no multi-corner signoff
claim or automatic false/multicycle-path correctness proof.

EQY runs SBY/Bitwuzla induction at depth 30 with explicit undefined-state propagation
against the actual selected mapped netlist. Use its four proof executables from
the same toolchain `bin` directory; companions are discovered beside Yosys when
absent from PATH. **PASS**, **FAIL**, **UNKNOWN** and engine **ERROR** stay distinct. A
strategy timeout/unproved partition cannot produce PASS. State/reset assumptions
and complex designs may need another strategy; counterexamples and proof logs
are retained for investigation. A failed proof does not silently become a
successful physical qualification.

**Test cases** saves named testbench tops, simulators, definitions and optional
Verilator line coverage. **Regression** runs all cases, retaining a failed case
while continuing the others. The APB example tests bus setup/access, FIFO ordering/full/empty/wraparound,
invalid accesses, reset and interrupt masking. The UART example tests reset, start/data/stop bits
for three byte patterns, and return to idle. Coverage describes instrumented code;
it does not establish exhaustive functional verification. Saved RTL cases also
appear in verification plans alongside analog testbenches. An RTL test runs once,
not once per analog temperature or supply corner. This is shared test management;
coupled analog/digital transient simulation is not implemented. An RTL-only symbol
is rejected as an analog circuit model until it has a schematic implementation.

The physical preview uses indexed cell outlines and batched signal-route
centerlines, retaining all instances and routes within the captured preview limits. Inspect GDS in the native layout
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
is engine-specific. Large bit-vector VCDs use a paged SQLite index with limits of
2 GiB, 100,000 declarations, 4,096 bits per signal and 20 million changes. Small
traces retain the bounded JSON representation. Real/string dumps and FST remain
unsupported; reduce dump scope/duration above these limits.

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
