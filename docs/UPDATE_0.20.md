# IC Design Studio 0.20.0 — Connected native workflows

This release connects native electrical definitions to the graphical analysis, variation, layout mapping and Xschem exchange workflows. It uses small circuits for acceptance; the long supplied GF180 simulation was not rerun.

## Install and start

For Windows, extract the complete Windows-x64 ZIP and run **ICDesignStudio.exe**. Python, Qt, KLayout's Python libraries, ngspice, standard Xschem symbols and GF180 simulation models are included. The KLayout desktop executable is a separate installation, needed only to execute external DRC scripts.

For source, install Python 3.12 and `requirements.txt`, then run `python main.py`. Windows source archives include the ngspice runtime. Linux/macOS need a native ngspice installation or an executable selected in **Analysis → Engine setup**. Existing `.icproj` files open directly; save upgrades under a new filename if retaining an older application alongside this release.

## Try the fast examples

- **File → Examples → Native divider and studies**: a 1 V divider with two 1 kΩ resistors. Operating point returns 0.5 V. It includes an Output specification for sensitivity and search.
- **File → Examples → Native RC and extracted comparison**: a small pulsed RC circuit with mapped device geometry, a routed output and explicitly illustrative interconnect coefficients. Run its transient, then **Analysis → Post-layout → Distributed RC and specification comparison → Extract and compare**.

## Graphical native analyses

The Inspector now offers operating point, transient, DC sweep, AC response and noise for native projects. These run the active cell using its native electrical definitions and embedded model assets. Choose a source for DC/noise, an output net for noise, and a temperature for any graphical analysis. AC/noise frequency density is points per decade.

**Native simulation program** remains available and preserves the saved loops, alterations and measurements. A graphical analysis excludes those control commands and previous analysis/output directives; it retains the circuit and model declarations outside the control blocks. A circuit that relies on `alter`, `let`, model loading or other control-program setup must keep using its saved program or move the required configuration into its electrical definitions. A child cell selected alone still needs an appropriate stimulus fixture.

The model-corner selector lists only section names found in every directly referenced embedded `.lib` file. **nominal** keeps the originally saved sections. Selecting another entry changes those top-level library section selections. This is not automatic inference of arbitrary PDK corner conventions or validation of all nested library combinations.

Operating-point voltage/current readouts use actual returned vectors. Native top-level primitive MOS devices also request `id`, `gm`, `vgs`, `vds` and `vdsat`. Internal devices inside arbitrary model subcircuits are not guessed.

## Variation, sensitivity and parameter search

Open **Analysis → Variation cases**. Each case has a separate immutable input, status, result and log. Existing resume/retry and specification evaluation apply.

| Target | Meaning |
| --- | --- |
| `R1.native.value` | A migrated resistor's numeric value |
| `X1.native.r` | A numeric native hierarchical instance parameter |
| `V1.native.dc_level` | DC level of a numeric DC/AC source, preserving its AC excitation |
| `MN1.native.w` | A native numeric width, in the original model's units |
| `R1.value` | An ordinary native primitive's value |

Numeric targets are listed in study dialogs. Expressions and compound waveform source strings remain editable in device properties; they are not silently treated as scalar sweep values. PVT supports numeric DC supplies, temperature and declared corners. Tolerance runs use explicit distributions and a repeatable seed; they are not substitutes for foundry statistical models.

**Sensitivity** creates a nominal case and positive/negative perturbations for each selected target. It reports central differences and normalized sensitivity when the nominal output is nonzero. Finite step size, nonlinear behavior and numerical noise affect the estimate.

**Bounded parameter search** evaluates a sampled parameter interval against a saved scalar specification. Choose target/minimize/maximize, bounds and sample count. All saved requirements must pass for a candidate to be eligible. The best sampled point can be applied with undo after every case has a valid measurement, provided the design has not changed. This is a sampled search, not a global or adaptive optimizer. The underlying case generator supports up to three explicit axes; the desktop dialog currently exposes one axis.

Use the divider to search `R1.native.value` from 1000 to 3000 with 3 samples and an Output target of 0.25 V. The 3000 Ω candidate returns 0.25 V. Sensitivity around 1000 Ω gives approximately −0.5 normalized sensitivity.

## Native device geometry mappings

Select a native leaf device and use **Layout → Native device geometry mapping** or the placement assistant. Choose an R, C, NMOS or PMOS recipe; explicitly map each geometry terminal to an electrical pin and select the parameter names and unit multipliers. A width stored as a micrometre number needs `1u` to convert to metres. Resistor/capacitor values use SI units after the multiplier.

Use **Place / regenerate** to generate geometry. Regeneration preserves role-based shape/pin IDs and translated placement. Changed native definitions, parameters, nets or mappings mark existing footprints stale. The mapping retains the original electrical model.

Geometry uses the active technology's declared recipes. Generic MOS geometry remains illustrative. A parameter mapping does not establish process-recognized device equivalence, include every model parameter, or qualify a PDK. Process-specific recipes, model correspondence and extraction still require validation. Distributed RC comparison retains its existing flat Manhattan-interconnect scope.

## Native Xschem exchange

Export a native project using the existing Xschem export command and an empty folder. The package includes `.sch` hierarchy, `.sym` artwork and declarative formats, model assets, programs, an exchange report, and matching native metadata.

In Xschem, add that folder to `XSCHEM_LIBRARY_PATH` and use it as the netlist/simulation directory so relative `models/` paths resolve. In Studio, open the exported top `.sch` to review changes. The **Changes** tab shows electrical parameters, nets, placement, orientation and program edits. Export metadata restores native device/cell identities, physical views, requirements and saved setups. Do not mix metadata from different exports.

Copied instances receive new identities. Deleting a device with linked geometry, or changing its terminal interface while linked physical pins exist, requires reconciliation in Studio. Files changed after review invalidate acceptance. Model changes are captured and checksummed again. Do not expect physical geometry to regenerate automatically after an external electrical edit.

Supported exchange covers declarative native device tokens, scalar ordered pins, hierarchy, parameters, placements, wires/labels, artwork, model assets and ngspice programs. Arbitrary Tcl behavior, full vector-bus semantics, every third-party macro and all source-format constructs remain outside the contract. Round-trip tests establish the tested subset, not universal numerical equivalence with every Xschem project.

## KLayout verification

**Verify → Open KLayout findings** loads `.lyrdb` report databases with cell names, hierarchical rule categories and geometric values. Double-click a finding to switch to its cell and select overlapping native geometry. Imported external reports are evidence from their source; loading one does not establish that it matches the current design.

**Verify → Run KLayout rule script** queues a self-contained Ruby `.drc` script through an installed KLayout executable. The script receives `$input` (exported GDS), `$top` and `$report` (required `.lyrdb` output). The run retains its script, exact command arguments, log, report and hashes for engine, script, design and GDS. A demonstration width script is in `examples/klayout/teaching-widths.drc`; use the layer numbers of your own technology. Relative helper scripts and external rule dependencies are not automatically packaged by this single-script workflow.

Zero findings means that the chosen script reported none. It does not establish full DRC coverage or foundry signoff. This release does not add a complete KLayout LVS/device-extraction framework.

## Validation and remaining scope

Core regression and actual Qt-worker acceptance use tiny divider/hierarchy/RC fixtures, including paths with spaces and Unicode. The graphical GUI acceptance runs 11 actual ngspice jobs across the five analyses, sensitivity and search; it also exercises apply/undo, geometry mapping and reviewed Xschem exchange. The long user-supplied simulation is intentionally excluded.

The Windows package receives archive/manifest/native-binary dependency checks. Native Windows execution is not available in the build environment; do not interpret the Linux GUI tests as Windows qualification. `scripts/verify_portable_windows.ps1` runs the small migration and graphical-workflow acceptance gates on a Windows machine. CI also includes both gates.

KLayout report parsing is tested against a real KLayout-generated report database. External KLayout desktop rule-script execution remains a destination-machine qualification step. No claim of qualified process extraction, full RF periodic/harmonic analyses, a mixed-signal co-simulation scheduler, unrestricted large-design capacity or complete PDK coverage is made by this release. Existing bounded case, geometry, hierarchy and waveform limits remain in place.
