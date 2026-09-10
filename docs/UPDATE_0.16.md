# IC Design Studio 0.16.0 — design goals and verification

This release connects reusable specifications, waveform calculation, individual variation cases, schematic readouts, constrained placement and extracted comparisons. It retains Xschem package exchange, the visible schematic/layout grids, configurable windows and direct wire editing from the previous release. Application text uses original feature names and names only open-source EDA tools.

## Find the right workspace

The Results panel now has four short workspace tabs: **Simulation**, **Waveforms**, **Physical** and **Checks**. A second row shows only the pages in that workspace. The existing commands remain searchable with **Ctrl+K**. Float, dock or resize the Results panel through **Window → Configure windows**.

- **Analysis → Design specifications** opens saved output requirements.
- **Analysis → Variation cases** opens the case scheduler and distribution view.
- **Analysis → Waveform calculator** opens derived, stacked waveform panels.
- **Layout → Placement and constraints** opens the schematic device checklist and analog constraints.
- **Analysis → Post-layout → Distributed RC and specification comparison** opens extracted comparisons.
- **File → Import → Import edited Xschem package** reviews an edited package. Ctrl+K can find this command if the File submenu is collapsed.

## Reusable specifications

Choose a cell or saved testbench in **Specifications**, then select **Edit requirements**. Add rows with a name, expression, optional minimum/maximum, and base unit. At least one limit is required. **Save requirements** stores them in the project and closes the editor so results remain prominent. Saving uses the normal Undo/Redo history.

New workers evaluate the exact definitions in their saved input. PASS includes equality; the margin is the smaller distance to the active limits. Negative margins fail. A missing signal, invalid expression, complex output without an explicit magnitude/phase conversion, unit mismatch, unavailable crossing or out-of-range coordinate produces ERROR, never PASS. A completed simulation can still fail its requirements.

**Evaluate selected run** previews the current editor definitions on historical data. It does not rewrite the saved run evidence. **Export results** writes a CSV. A testbench's own specification list takes precedence over its fixture cell's list.

| Requirement | Expression | Unit |
|---|---|---|
| Final output | `final(V("vout"))` | V |
| Differential gain | `final(abs((V("outp")-V("outn"))/(V("inp")-V("inn"))))` | 1 |
| Peak source power magnitude | `max(abs(V("vin")*I("V1")))` | W |
| Output at 25 µs | `at(V("vout"),25e-6)` | V |
| First rising threshold crossing | `crossing(V("vout"),0.9,1)` | s |
| First falling threshold crossing | `crossing(V("vout"),0.9,-1)` | s |
| Settling to 1.8 V within 20 mV | `settling(V("vout"),1.8,0.02)` | s |
| Integrated output | `final(integ(V("vout")))` | V*s |
| Downward unity-gain crossing | `crossing(db20(V("out")/V("in")),0,-1)` | Hz |

Limits accept suffixes such as `10k`, `25u` and `20f`. Expression constants use ordinary decimal/scientific notation, such as `25e-6`. Expression evaluation uses a bounded syntax tree, without Python evaluation, imports, attribute access or file access.

## Waveform calculator and markers

Each calculator row defines one named panel. **Calculate / plot** evaluates every row against the selected saved result. **Save plot layout** retains the definitions with the active cell; reopen the calculator on another run to reuse them. Panels keep their own units and Y ranges. Linked X zoom/pan applies only to panels with the same sampled axis.

Supported functions are `V`, `I`, `trace`, `abs`, `real`, `imag`, `phase`, `db20`, `unwrap`, `sqrt`, `sin`, `cos`, `exp`, `log`, `deriv`, `integ`, `fft`, `min`, `max`, `mean`, `rms`, `pp`, `final`, `at`, `crossing`, `settling` and `clip`. AC arithmetic reconstructs complex values from saved magnitude and phase. `phase` returns radians; `db20` returns decibels. `mean` and `rms` are sample statistics. `integ` uses trapezoidal integration on the saved X coordinates; `deriv` uses adjacent-sample differences. `clip(signal,start,stop)` selects a sampled interval.

FFT requires at least four uniformly spaced time samples. It uses a Hann window, coherent-amplitude correction, zero padding to the next power of two and a single-sided amplitude spectrum including DC. Adaptive samples are rejected explicitly. FFT frequency plots use a linear axis so DC remains visible. Expressions support up to 200,000 samples and 12 saved panels.

Every panel includes the existing exact X, Y and X/Y markers. Drag markers or type their coordinates in **Markers**; choose interpolation or nearest sample. X/Y checks compare the trace value at X against a chosen Y limit. Markers are saved by waveform identity. Wheel zooms X, Shift+wheel zooms Y, Ctrl+wheel zooms both, middle drag pans and F fits.

## Individual corners and statistical cases

Choose **Current cell · Inspector analysis** or a saved testbench as the study source. Create a parameter sweep, PVT matrix or component tolerance study. PVT requires a DC voltage-source target and model corners declared by the technology. Component tolerances accept comma-separated targets, a shared relative sigma, normal/uniform distribution, trial count and repeatable seed.

The matrix review appears before launch. Uncheck unwanted cases or double-click a row to edit its parameter values and temperature. **Run enabled cases** creates one immutable job per case. Parallelism uses the existing 1–8 worker setting. Each row shows its condition, job state, selected specification, value, margin and verdict. Select a specification to inspect its distribution and worst margin. The displayed pass fraction uses all planned cases as its denominator; incomplete and errored cases cannot inflate it.

Double-click a completed case to open its saved requirement results and waveform. This turns off Follow latest. **Stop this study** stops only that group. **Resume / retry missing** reuses validated completed jobs and queues cancelled, interrupted, absent or failed cases. It never overwrites an earlier attempt. Manifests and results survive reopening the project. The history loader retains up to 2,000 recent run records; results beyond that window are still on disk but may need a new attempt when resuming an older group.

Studies record the implementation hash and, for ngspice, the executable checksum. Replay is blocked if these change; create a new study to use a different implementation. PDK include locking remains enforced by the existing simulation exporters. Limits are 500 cases per study. The teaching solver retains its 80-unknown limit and requires 27 °C for MOS circuits; model-bound designs and MOS temperature studies require ngspice.

**Model mismatch** is available only when the linked technology declares a statistical profile with reviewed evidence and numeric parameter mappings. The profile uses the same deterministic case planner. No process distribution, mismatch coefficient, correlation or qualification is inferred. Native statistical-model syntax outside these explicit parameter mappings remains an external model integration task.

## Schematic readouts

Enable **Show operating-point values on schematic** on the Specifications page. Readouts follow the selected run or case and identify stale data. Saved node voltages, source/passive branch currents and available MOS device values appear alongside the schematic.

The teaching solver exposes its own square-law current, gm, region and headroom, including its stated model limitations. ngspice OP runs request gm, drain current, VGS, VDS and VDSAT for supported primitive MOS instances. Headroom is computed only when VDS and VDSAT are actually returned. Subcircuit model internals are not guessed, and unavailable quantities are omitted. Current sign follows the engine's declared terminal direction.

## Placement, constraints and parametric devices

**Placement & rules** lists every physical device, its placement state and missing terminals. Select a row to select the schematic instance. **Place / regenerate** uses its value or W/L and creates linked geometry and physical terminals. Hierarchical instances use their child-cell layout ports. Model-bound MOS instances use the existing supported process recipes.

New declared-rule recipes cover resistors, capacitors, MOS footprints, contact arrays and guard rings. The generic teaching process supplies explicitly illustrative rules. Other technologies must provide `pcell_rules` with layer mappings, dimensions and calibrated coefficients, or use an existing process MOS recipe. Resistor geometry uses sheet resistance; capacitor geometry uses area density. Realized dimensions/values and coefficient provenance stay in the saved recipe.

Regeneration preserves the electrical device ID, stable shape roles and terminal IDs, including an ordinarily translated footprint. It does not change the schematic value. Changed parameters, deleted/reshaped generated geometry and changed generator rules are reported by background checks. A rotated/reshaped anchor requires review before regeneration.

| Constraint | What it checks or arranges |
|---|---|
| Symmetry | Two footprint centers about an explicit X or Y axis; arrangement holds the first device fixed. |
| Matching | Electrical parameters, model identity, geometry and orientation. |
| Common centroid | Centroids of explicit groups of unit devices; automatic ABBA placement supports two equal groups with an even number of members. |
| Guard coverage | Protected footprint bounds inside the assigned generated ring opening. |

These are explicit geometric constraints. The tool does not infer device matching physics, automatically split an electrical transistor into unit instances, optimize all analog constraints simultaneously or prove substrate isolation. The teaching ring is illustrative geometry. Existing routes stay in place during constrained placement; remaining connections identify what must be rerouted.

## Live rules and routing

Background checks run on an immutable revision snapshot after geometry changes. They check declared width/spacing/grid rules, cut enclosures, analog constraints, generator provenance and physical terminal connectivity. Stale results are discarded. Click a finding to locate the geometry or affected net. Dashed guides update remaining connections.

While drawing a path/rectangle or placing a via, local previews show a clear or blocked outline and the specific rule. **Prevent routes and vias that violate preview checks** rejects an invalid path before committing it and retains the path for correction. Via placement checks both conductor pads and the cut. An explicitly labeled path cannot touch a differently labeled conductor. The existing obstacle-aware Manhattan router and route-layer transitions remain available.

Large schematic overviews batch wire strokes and simplify symbols when labels would be too small to read. Full detail returns when zooming in; hit targets and electrical geometry remain unchanged.

Local previews use a spatial index and a bounded neighborhood. Dense regions ask for background checks rather than monopolizing interaction. This feedback uses declared geometry rules; run the full process rule deck separately. Rectangles can still be committed for constructive editing even when they temporarily violate a rule. Protection can be turned off explicitly in the assistant.

## Distributed RC and before/after verification

Declare layer sheet resistance, ground area/edge capacitance and same-layer parallel coupling in **RC coefficients**. The default form values are labeled illustrative estimates. Supply calibrated values and their source for engineering use.

**Extract and compare** requires a flat physical cell with resolved terminal connectivity and Manhattan conducting paths. It subdivides routes, preserves branches and terminal locations, inserts distributed resistance, distributes ground capacitance and estimates coupling between nearby parallel routes on the same layer. Coupling scales the declared 1 µm-gap coefficient inversely with edge gap. Rectangular/polygon pads are ideal conductors; generated device geometry is not reinterpreted as an extracted device. Overlapping route centerlines are rejected rather than double-counted.

The exported network contains component values, terminal remapping, coefficient and design hashes, section settings and qualification scope. Original net names identify the chosen physical anchor, preferably a declared layout port. Internal nodes are named explicitly. Stale extraction cannot be applied to another revision.

The comparison worker simulates the schematic and RC network with the same analysis and saved requirements. The table shows both values, their delta, and each verdict. **Before / after waveforms** overlays the saved data. **Export extracted network** writes the full JSON network. The teaching solver and document device limits still apply; increase section length or use the process extractor when needed.

This estimator is not a field solver. It does not provide cross-layer coupling, arbitrary hierarchy extraction or process device recognition. The existing Magic/Netgen process workflow and its click-to-locate DRC/LVS mismatch browser remain available for supported external decks. No new foundry or fabrication qualification is claimed.

## Xschem exchange review

The review shows added/removed devices and changed names, positions, rotations, values, parameters and nets, alongside wire-path replacements. Unsupported records and blocking errors remain visible even when import is unavailable. An import is applied only after review and only if package files still match the reviewed checksums.

Native specifications, plot definitions, device IDs and physical metadata remain in the package metadata. Changed or missing symbols, unknown symbols, conflicting net labels, changed ports and unsupported source constructs require reconciliation. Opaque graphics are retained as metadata. External schematic control/netlist text is not executed or imported as a simulation setup. This remains round-trip editing of Studio-generated packages; it is not an arbitrary-library Xschem importer.

## Examples and verification

Open the new examples directly through **File → Examples**.

- `distributed-rc-specifications.icproj`: connected teaching geometry, saved output requirement, distributed RC extraction and before/after simulation.
- `differential-amplifier-goals.icproj`: differential AC expressions and matched input-pair teaching footprints. The physical design is intentionally unfinished; the checklist and guides expose remaining work. The teaching MOS model has no device capacitance, so this example does not establish realistic bandwidth.
- `common-centroid-resistors.icproj`: four explicit unit resistors with matching and ABBA centroid constraints. Routing remains to be completed.

The release evidence archive records unit, native GUI, wire/marker regression, scheduler lifecycle, capture performance and standalone executable probes. GUI checks use offscreen Qt, real local worker processes and deterministic fixtures. Physical displays, fresh operating systems, human usability sessions and foundry model/extraction qualification were not performed. An attempted ngspice 42 execution in this restricted build environment could not initialize its temporary files; the new OP-vector parser is covered by fixtures, not a successful external-engine run here.

Technical references: [Xschem waveform graphs](https://xschem.sourceforge.io/stefan/xschem_man/graphs.html), [Xschem operating-point data](https://xschem.sourceforge.io/stefan/xschem_man/tutorial_ngspice_backannotation.html), [KLayout geometry API](https://www.klayout.de/doc/programming/geometry_api.html), [ngspice documentation](https://ngspice.sourceforge.io/docs.html).
