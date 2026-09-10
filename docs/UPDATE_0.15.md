# IC Design Studio 0.15.0 — simulation and direct editing

This update retains visible schematic/layout grids, the configurable Window menu and Xschem exchange. The application and its guides use original feature names and name only open-source EDA tools. The third keyboard preset is now **Classic analog**; existing saved bindings migrate when that legacy preset is selected.

## Analysis workspace

Open **Analysis → Simulation Explorer** (Ctrl+Shift+A) or **Window → Simulation Explorer**. The first level of Analysis contains setup, run and stop commands. Testbenches, Studies, Post-layout, Waveforms and Engine setup each have a single submenu.

1. Choose an analysis and engine in **Inspector → Analysis**. Only fields relevant to that analysis appear.
2. Click **Add current setup** in Simulation Explorer. Repeat for other analyses or settings. Rename setups to describe the intended test. The plan is saved inside the project and supports Undo/Redo.
3. Enable the setups to run and choose **Run enabled** (Ctrl+F5). F5 still runs the current Inspector settings.
4. Set **Parallel jobs** from 1 to 8. Each job uses an independent local worker and immutable input snapshot. Additional jobs queue until a slot becomes free. All enabled setups are validated before any job in a batch starts.
5. Follow status, progress, elapsed time, engine and input revision in the run table. Select a row and enable **Show log** for its messages. Select multiple rows to stop those jobs. **Stop all simulations** also cancels queued work.
6. Double-click a completed run or use **Open waveforms**. This disables **Follow latest**, so later completions preserve the waveform you chose. Enable Follow latest when you want results to advance automatically.
7. **Rerun snapshot** repeats the saved circuit and settings. **Clear finished** clears table rows for this session; it does not delete the saved jobs. Reopening the project restores up to 100 recent run records. Interrupted or cancelled jobs cannot replay as complete results.

External command-line conversion jobs remain exclusive. Built-in analyses, ngspice analyses, saved testbench jobs and existing study workflows use the simulation scheduler. Study cases retain their existing detailed tables; a study is one scheduled worker. External tools still require installation, the appropriate model files and any required technology setup.

The Results panel can be resized, floated or docked using its title bar and **Window → Configure windows**. The Simulation workspace preset opens the explorer. Narrow panels scroll to retain access to every control.

## Waveforms and measurements

The Waveforms toolbar offers **Inspect**, **X cursor**, **Y limit** and **X/Y check**. Choose a trace and a pass condition, then click the plot. Drag a line to adjust its coordinate. Drag the intersection of an X/Y check to adjust both coordinates. Grabbing one of its lines changes only that coordinate.

| Tool | Measurement | Pass condition |
|---|---|---|
| X cursor | Trace value at the selected X coordinate | Readout only |
| Y limit | Maximum or minimum across every saved sample of the trace | Entire trace at or below / at or above the limit |
| X/Y check | Trace value at X, compared with the horizontal Y limit | Value at or below / at or above the limit |

**Markers…** opens an exact-coordinate editor. Enter values in the explicitly labeled base units; `25u` means 25 microseconds in an X field labeled seconds. Plot tick labels may use scaled units such as milliseconds. PASS includes equality. Missing traces and out-of-range X positions display a non-passing status instead of inventing a value. Y checks include samples outside the zoomed view and show the number of threshold crossings/touches.

By default, a marker interpolates between saved samples. Frequency plots interpolate along logarithmic X, matching the drawn trace. **Nearest sample** instead reads the closest saved sample. This is a numerical readout of the available data; interpolation does not add simulation accuracy or prove behavior between samples.

Markers retain their coordinates when trace visibility changes. They are saved locally per result and restore when that result is reopened on the same installation. **Export CSV** includes coordinates, units, sample mode, measurement and PASS/FAIL. Markers do not alter the circuit or the immutable simulation result.

- Wheel: zoom X around the pointer. Shift+wheel: zoom Y. Ctrl+wheel: zoom both.
- Middle drag: pan. **Fit plot**, F or double-click in Inspect: restore full data bounds.
- Delete: remove the selected marker. Esc: cancel a marker drag and return to Inspect.
- Inspect retains the original click/right-click A/B sample readouts. Multiple X markers also show ΔX and ΔY.

## Wire movement

Dragging a wire segment slides its existing corners. It no longer copies the previous corners into a growing sequence of bends. Free endpoints move freely; connected pins remain attached; branch leads stretch instead of creating a new branch on every drag. Component movements update terminal leads together, including a group moving both ends of the same wire. Necessary connections at stationary pins and junctions remain present.

The preview uses the same reshape operation as the committed edit. Each release commits one undoable transaction. Repeated drag/return operations, off-grid pins, shared terminals and branches have regression coverage. **Move** retains its explicit detach behavior; **Stretch** preserves attached wires. Ordinary device dragging preserves terminal connections. Xschem shortcut and exchange workflows remain available.

## Compatibility information

**Help → Compatibility matrix** now opens a searchable native table directly from bundled data. It works offline and does not depend on a document path or an external viewer. The table covers Xschem, ngspice, KLayout, Magic, Netgen, OpenVAF and the built-in application, with the scope and limits of each supported path.

## Verification scope

The release includes numerical/topology tests, native mouse/keyboard tests, actual local-worker concurrency/cancellation tests, Xschem package exchange regressions and standalone executable probes at 100% and 200% scaling. See the accompanying verification archive for the executed results.

These are offscreen Qt checks on the Linux build host. Physical desktop hardware, human usability sessions and external engine/PDK requalification were not performed for this update. The application remains an engineering preview, with the earlier fabrication and qualification limits unchanged.
