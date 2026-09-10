# Current verification — 0.8.0

114 core tests, ten Qt suites, four actual-ngspice saved-analysis cases and eighteen hierarchical/interchange cases produce their expected outcomes. The ring oscillator also passes from the native desktop and final standalone executable. The final frozen app passes 100% and 200% scaling probes with development overrides removed. The consolidated evidence and exact limits are described in [UPDATE_0.8.md](UPDATE_0.8.md). Windows execution remains unverified.

# Verification report — 0.4.0

- 76 core regressions pass, including new label/ground topology, recovery corruption, atomic-write failures, competing saves, result identity and process-tree cleanup coverage.
- Native Qt suites pass: manual wiring/mnemonics, direct labels/ground/net inspection, reliability lifecycle, core smoke, usability and existing study/physical/symbol workflows. Compact and full-width dark workspaces were visually checked.
- The actual SKY130 reference passes all eight stages with ngspice 42, Magic 8.3.683, Netgen 1.5.133 and KLayout 0.30.5. DRC = 0, unique native-schematic LVS match, 14 parasitic capacitors, correct pre/post transient response. See SKY130_REFERENCE.md.
- Windows installer and installed-app verification scripts are included but have not run on Windows here. No Windows binary or signing qualification is claimed.
- The packaged Linux executable passes native startup, dark appearance at 100% and 200% scaling, save/reopen, rotation/undo and a 501-sample background simulation. Its full eight-stage SKY130 flow also passes. JSON reports are included in the separate reference evidence archive.

## Previous 0.3.1 verification

# Verification report — 0.3.1 manual schematic editing

61 core tests passed. `tests/test_wiring.py` covers electrical topology, placed geometry, persistence, deletion/undo, explicit labels, legacy migration, branch-preserving movement and bounded Xschem edits. `tests/gui_wiring.py` exercised real native mouse/key events and inspected full/compact dark screenshots. Native usability, interface, dark-mode/job-state and 0.3 workflow checks passed during this update. A complete manually wired RLC/current-source example ran in the built-in engine and actual ngspice 42 (563 transient samples). The ngspice run used the same test-only temporary-file adaptation described below; it is excluded from release archives.

The final PyInstaller Linux build passed headless native startup (exit 0) and simulation of its bundled manual-wiring example (501 finite samples, vin/vout traces) without the development Python environment. The source ZIP was checked for integrity and excludes native platform binaries. Windows execution, installers, foundry qualification and general platform compatibility are not established by these tests.

---

# Verification report — 0.3.0 workflow expansion

50 core tests passed. Existing native interaction, usability and dark-default/job-state checks passed. New native workflow tests exercised study-form submission, per-case waveforms, physical connectivity and missing-conductor errors, capacitance estimates and post-layout workers, instance arrays and edits, vector symbol editing, study cancellation without a partial aggregate, and saved-run recovery. Actual ngspice 42 runs checked analytic resistor noise, checksummed model binding, four voltage/temperature cases and external-deck simulation. Dark screenshots were inspected. The rebuilt standalone Linux executable passed startup, a three-case study, and post-layout estimate simulation without the development Python environment.

`tests/test_workflows.py`, `tests/gui_workflows.py` and `tests/engine_workflows.py` contain the new regressions. The real-engine test on this restricted host used the previously documented test-only tmpfile redirect; it is not shipped as application behavior. Magic profile tests use a fixture runner; no actual Magic/foundry extraction or Windows execution was performed.

The old tests below are historical records. This update does not establish the blueprint’s complete professional-release gates.

---

# Verification report — 0.2.2 component symbols

The existing `tests/gui_usability.py` passed after the drawing changes, including placement preview/cancellation, click placement, selection, dragging, actual pin wiring, and an RC analysis worker run. Native screenshots were visually reviewed for all three updated components at 0°, 90°, 180°, and 270° in dark and light themes, including selected outlines. The native workspace and device browser were reviewed at 1440×900.

The rebuilt standalone Linux executable passed offscreen startup and clean exit without the development Python environment.

The symbol and icon changes affect drawing only. The terminal locations, hit targets, project model, and solver are unchanged. Checks used native Qt with the offscreen platform on the Linux build host; physical-display and Windows rendering remain unverified. Earlier test records below are historical.

---

# Verification report — 0.2.1 dark-default and Windows loader update

31 core tests passed (24 existing and seven native-loader/fallback regressions). The native dark-default/preference/job-state smoke check and cancellation check passed. A dark screenshot was inspected. The rebuilt Linux executable passed offscreen startup and frozen RC simulation. See UPDATE_0.2.1.md for the exact wrong-platform regression, Python-fallback evidence, and Windows validation boundary. Earlier test records below are historical.

---

# Verification report — 0.2.0 interface update

Executed 7 September 2026 on the same Ubuntu 24.04 x86_64 host described below.

- All 24 numerical, model, geometry, interchange, and engine-parser tests passed.
- Existing native GUI integration passed after the workspace redesign: property transactions, undo/redo, connection editing, component operations, background simulation, staleness, geometry/DRC, keyboard nudge, themes, and recovery.
- New `tests/gui_usability.py` passed with real Qt mouse/key events: cancellable placement preview and click placement; inline invalid-draft handling; valid-draft commit on selection change; rubber-band selection; move preview and commit; two-pin wiring; analysis validation and a completed worker run; micrometre geometry fields; fully hidden layer persistence; source-field visibility; command-palette keyboard navigation; camera memory; focus/restore controls; compact layouts.
- Worker cancellation passed without publishing a result.
- Light/dark screenshots and 1440×900 / 1100×760 layouts were inspected. Compact toolbar clipping and canvas reframing defects found during this review were corrected.
- The rebuilt standalone Linux executable passed offscreen startup/exit and frozen CLI RC simulation. Qt's SVG image and icon plugins were explicitly staged and confirmed loaded, so dropdown and checkbox assets render in the binary as well as the source application. Future builds include the QtSvg packaging hook.

These checks are headless native Qt checks. They do not establish X11/Wayland, Windows, physical high-DPI, screen-reader, or professional-user acceptance. No new PDK/tool qualification is claimed. The prior engine-comparison results below are historical evidence from 0.1.0; the simulation engine was not changed in this interface update.

---

# Verification report — 0.1.0

Executed 7 September 2026 on an Ubuntu 24.04 x86_64 build host with glibc 2.39, Python 3.12.13, PySide6/Qt 6.8.3, KLayout 0.30.5, and the compiled C++20 solver. These are engineering-preview tests, not the blueprint's full release-gate certification.

## Core and native interface

- **24 automated tests passed**: atomic-save failure preservation, Unicode/spaced project paths, schema rejection, invalid transaction rollback, undo/redo, hierarchy recursion rejection, case-portability checks, geometry coordinate checks, plugin command validation, pivoted solve and Python fallback, analytical OP/AC/transient/noise circuits, MOS rail behavior, singular circuits, invalid sweeps, Boolean holes, GDSII/OASIS XOR comparisons, changed-file sidecar rejection, width/spacing/grid violations, handoff preservation reporting, real/complex ngspice raw parsing, and literal Tcl path quoting.
- **Native Qt integration passed**: property changes, undo/redo, pin connections, add/move/duplicate/delete, background simulation, result staleness after edits, Boolean editing, DRC, keyboard nudge, both themes, and recovery snapshot presence. This used Qt's offscreen platform and real application widgets/controllers; no browser was involved.
- **Cancellation test passed**: a running worker terminated, and its cancellation did not publish a completed result.
- The light/dark desktop captures were inspected for layout and drawing defects. This does not qualify a physical display, touch device, high-DPI configuration, or screen reader.

## Real ngspice comparison

The actual Ubuntu ngspice 42 executable ran exported generic decks. The app parsed its raw results and compared output voltages to the built-in engine using linear interpolation at the built-in sample coordinates.

| Fixture | Analysis | Maximum absolute difference | Allowed tolerance | Result |
|---|---|---:|---:|---|
| RC low-pass | Transient | 0.0352942 V | 0.04 V | Pass |
| RC low-pass | AC magnitude | 0.00001491 V | 0.001 V | Pass |
| RC low-pass | Operating point | 0 V | 0.001 V | Pass |
| CMOS inverter | DC sweep | 0.00091122 V | 0.015 V | Pass |

The transient difference includes different pulse-edge and integration behavior: the built-in solver uses fixed-step backward Euler and ideal pulse transitions, while ngspice uses adaptive stepping and a short finite edge. These tolerances cover these fixtures only; they are not a general equivalence claim.

The restricted host has no `/tmp` or `/proc` view. A test-only `tmpfile()` adapter redirected ngspice's temporary files into the permitted test directory. It did not modify the circuit, engine executable, or solver. Missing `/proc` statistics produced diagnostic warnings but did not prevent the analyses. This adaptation is not part of the shipped application and is unnecessary on a normal Linux desktop.

## Packaged application

The final Linux directory bundle passed:

- Frozen application startup and clean exit using Qt's offscreen platform, without the development Python environment.
- Frozen CLI RC simulation and valid result JSON.
- Frozen background-worker entry point, streamed progress, and complete result JSON.
- Frozen handoff export including the KLayout-dependent GDSII/OASIS files.
- Dynamic dependency inspection of the XCB platform plugin with no unresolved libraries after runtime staging.

This is not an X11/Wayland interactive-session test. The bundle targets the Ubuntu 24.04 x86_64 baseline. It has not been run on a Windows machine, an older Linux distribution, an ARM machine, or a physical high-DPI screen.

## Unverified gates

Windows binaries/installers, signed updates, managed WSL, Magic/Netgen destination regressions, Xschem GUI round trips, PDK/model qualification, complete DRC/LVS, parasitic extraction, post-layout simulation, performance targets, full crash/recovery campaigns, accessibility certification, licensing review, and external user pilots remain incomplete. Read RELEASE_STATUS.md for the complete capability boundary.
