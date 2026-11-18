# Features to add

This is the feature-by-feature target for IC Design Studio, from design entry
through tapeout and silicon bring-up. The inventory covers capabilities
documented by commercial and open-source EDA projects and the engineering
requirements needed to use them together. The source links by domain define
the comparison scope. Extend the inventory as new flows, standards, and
public vendor documentation surface.

## How to use this inventory

The identifiers are stable references for issues, tests, and qualification
evidence. Each item is a target capability. For a specific item, verify
Studio’s behavior and classify it as missing, partial, integrated, or
qualified for a named use. Existing capabilities belong in the inventory
because parity includes their edge cases, interoperability, usability,
performance, and supported process scope.

For implementation, record the user workflow, native or external engine,
applicable process and platforms, representative input, expected result,
and evidence. Check the normal desktop workflow and the automation path.
Use negative controls wherever an erroneous success could affect tapeout.
Qualify each process, variant, analysis and tool build independently.
Compare the same design and requirements before reporting parity or a win.

Start with the existing SKY130A/HD UART and the named submission profile
selected under [AGENTS.md](AGENTS.md#tapeout-first). Pull only the entries
required by that profile into its critical path. Carry the analog reference
work in parallel where possible, then expand to mixed-signal and separately
qualified GF180MCU C/D and IHP SG13G2 paths. Integrate proven engines and
documented formats when they shorten delivery. For the release boundary and
implementation order, see the [acceptance targets](docs/PUBLIC_RELEASE_TARGETS.md)
and [qualification tracker](docs/QUALIFICATION_PROGRESS.md).

| Area | Feature groups |
| --- | --- |
| Design foundation | [Project and workspace](#project-and-workspace), [PDKs and process data](#pdks-and-process-data), [Schematic capture](#schematic-capture), [Libraries and reusable IP](#libraries-and-reusable-ip) |
| Custom implementation | [Custom layout](#custom-layout), [Routing and layout constraints](#routing-and-layout-constraints), [Analog simulation](#analog-simulation), [Experiments and optimization](#experiments-and-optimization), [Waveforms and results](#waveforms-and-results) |
| Analog and system verification | [Behavioral and mixed-signal](#behavioral-and-mixed-signal), [RF and microwave](#rf-and-microwave), [Extraction and back-annotation](#extraction-and-back-annotation), [Physical verification](#physical-verification), [Reliability and manufacturability](#reliability-and-manufacturability) |
| Digital design and implementation | [Architecture and RTL](#architecture-and-rtl), [Digital simulation and verification](#digital-simulation-and-verification), [Static and formal verification](#static-and-formal-verification), [Synthesis](#synthesis), [Physical implementation](#physical-implementation), [Timing signoff](#timing-signoff), [Power integrity](#power-integrity), [Design for test](#design-for-test), [Cell and memory characterization](#cell-and-memory-characterization) |
| Delivery and product quality | [Tapeout and handoff](#tapeout-and-handoff), [Exchange and interoperability](#exchange-and-interoperability), [Collaboration and version control](#collaboration-and-version-control), [Automation and infrastructure](#automation-and-infrastructure), [Desktop experience and accessibility](#desktop-experience-and-accessibility), [Learning and support](#learning-and-support), [Functional safety and design assurance](#functional-safety-and-design-assurance) |
| Extended flows | [Electromagnetics and multiphysics](#electromagnetics-and-multiphysics), [Packages, chiplets and boards](#packages-chiplets-and-boards), [Photonics and special processes](#photonics-and-special-processes), [FPGA, prototyping and emulation](#fpga-prototyping-and-emulation), [Fabrication and TCAD](#fabrication-and-tcad), [Laboratory and silicon lifecycle](#laboratory-and-silicon-lifecycle) |
| Engineering productivity | [Specialized generators and systems](#specialized-generators-and-systems), [Engineering intelligence and decision support](#engineering-intelligence-and-decision-support) |

## Studio starting points

Use these documented starting points when assessing existing features. Each
row covers the scenario named in its evidence, so audit the complete scope
of an inventory item before closing it.

| Related entries | Existing starting point and evidence |
| --- | --- |
| PRJ-01, PRJ-10–13 | Project files and folders, recovery, project management, and save/reopen controls. [Project Hub](docs/PROJECT_HUB.md) · [Design recovery](docs/RELIABLE_DESIGN_WORKFLOWS.md) |
| PDK-01, PDK-04, PDK-17, PDK-22 | Search and switch installed PDKs, preview model changes, and save cross-process schematic copies. Physical migration across processes requires a new layout. [PDK switching](docs/PDK_GUIDE.md#switch-the-open-project) |
| SCH-02–10, LAY-02–14, RTE-05 | Native wiring and buses, layout editing, linked views, physical instances, and via previews. [User guide](docs/USER_GUIDE.md) · [Native vectors](docs/NATIVE_VECTORS.md) · [Layout commands](docs/DRAWING_0.22.md) · [Vias](docs/LAYOUT_VIAS.md) |
| SIM-02–06, EXP-01–05, WAV-06 | Named analysis setups, solver-backed runs, studies, and saved waveform comparison. [Analog workspace](docs/ANALOG_WORKSPACE.md) · [Simulation controls](docs/USER_GUIDE.md#simulation) |
| PEX-02, PEX-04, PHY-02, PHY-07 | Real extraction, DRC, and LVS on selected reference fixtures such as the pinned inverter. [SKY130 inverter](docs/SKY130_REFERENCE.md) · [Process RC and hierarchy](docs/ANALOG_IMPLEMENTATION_EXTENSIONS.md) · [Public layouts](docs/PUBLIC_DESIGN_COMPATIBILITY.md) |
| RTL-02, VER-01, FRM-11, IMP-01, STA-06 | RTL editing, functional simulation, mapping/implementation, timing, and selected equivalence cases. [Digital workspace](docs/DIGITAL_WORKSPACE.md) · [RTL-to-GDS](docs/DIGITAL_FLOW.md) · [Platform evidence](docs/DIGITAL_PLATFORM_QUALIFICATION.md) |
| AMS-05–07, EM-01, EM-10 | A clocked SAR example and a separate bounded field-solver workflow. [SAR co-simulation](docs/MIXED_SIGNAL_SAR.md) · [Electromagnetic analysis](docs/OPENEMS.md) |
| COL-01–13, COL-16–19 | Local versions and branches, reviewed merges, in-app GitHub PRs, and scoped live editing. [GitHub review workflow](docs/USER_GUIDE.md#github-pull-requests-in-studio) · [Live collaboration](docs/LIVE_COLLABORATION.md) · [Recorded verification](docs/QUALIFICATION_PROGRESS.md) |
| EDU-01–08, AUT-15–18 | Student Hub lessons, evidence and progress, plus scoped release checks. Includes spec-driven TIA and op-amp projects with schematic and post-layout checkpoints. [Student Hub](docs/STUDENT_HUB.md) · [Analog projects](docs/STUDENT_ANALOG_PROJECTS.md) · [Release gates](docs/RELEASING.md) |
| EDU-01–08 | Guided layout tradeoffs, hand-plotted LC filters with simulated Bode traces, and interactive Ahuja compensation. [Layout lesson](docs/STUDENT_LAYOUT_DECISIONS.md) · [Bode lesson](docs/STUDENT_LC_BODE.md) · [Ahuja lesson](docs/STUDENT_AHUJA.md) |
| EDU-01–08 | Miller zero and phase-margin study, measured SKY130 bias and cascode lab, and four bandgap lessons with topology-specific temperature experiments. [Miller](docs/STUDENT_MILLER.md) · [Bias and cascode](docs/STUDENT_BIAS_CASCODE.md) · [Bandgaps](docs/STUDENT_BANDGAPS.md) |
| EDU-01–08 | Four editable GF180 bandgap labs with ratio trim, two-rate startup across process and temperature, layout, and Magic capacitance-extracted comparison. [Bandgap labs](docs/STUDENT_BANDGAPS.md) |
| EDU-01–08 | Ten interview labs with editable test circuits, measured comparisons, and whiteboard follow-ups. [Analog interview labs](docs/STUDENT_INTERVIEW_LABS.md) |

## Project and workspace

References for library and project workflows. [Cadence Virtuoso Studio](https://www.cadence.com/en_US/home/tools/custom-ic-analog-rf-design/virtuoso-studio.html) · [Xschem schematic editor](https://xschem.sourceforge.io/stefan/xschem_man/creating_schematic.html) · [Studio Project Hub](docs/PROJECT_HUB.md)

- **PRJ-01.** Create standalone files and directory projects with a portable manifest.
- **PRJ-02.** Start from a blank project, process template, reference circuit, or imported design.
- **PRJ-03.** Organize design libraries, cells, named views, and project dependencies.
- **PRJ-04.** Resolve schematic, symbol, layout, abstract, RTL, behavioral, and extracted views for each instance.
- **PRJ-05.** Switch view bindings by configuration for simulation, verification, and implementation.
- **PRJ-06.** Store stable identity for designs, instances, nets, shapes, and ports across edits.
- **PRJ-07.** Open multiple projects and documents with separate editor state and active contexts.
- **PRJ-08.** Browse hierarchy, search globally, follow references, and locate definitions and uses.
- **PRJ-09.** Manage read-only and editable libraries, external IP, and linked local copies.
- **PRJ-10.** Track modified files, external changes, Save As, rename, move, duplicate, and archive.
- **PRJ-11.** Save atomically, recover after interruption, and inspect or restore prior saved versions.
- **PRJ-12.** Validate schema versions, upgrade old documents, and preserve recoverable source data.
- **PRJ-13.** Package portable projects with missing-dependency diagnostics and relinking.
- **PRJ-14.** Separate working files, generated reports, cached objects, and verified release artifacts.
- **PRJ-15.** Report project units, process, variant, branch, revision, and status at point of use.
- **PRJ-16.** Detect incomplete libraries, unresolvable links, circular hierarchy, and conflicting definitions.

## PDKs and process data

References for process scope and import. [Studio PDK guide](docs/PDK_GUIDE.md) · [SKY130 open PDK](https://github.com/google/skywater-pdk) · [GF180MCU open PDK](https://github.com/google/gf180mcu-pdk) · [IHP open PDK](https://github.com/IHP-GmbH/IHP-Open-PDK)

- **PDK-01.** Install, discover, verify, update, and uninstall versioned PDKs.
- **PDK-02.** Pin process release, variant, stack, library, tool, and required deck hashes per project.
- **PDK-03.** Support independent SKY130A, GF180MCU C, GF180MCU D, and IHP SG13G2 profiles.
- **PDK-04.** Load licensed process assets from authorized local or on-premises installations.
- **PDK-05.** Map layer and purpose names to stream numbers, drawing styles, and editor visibility.
- **PDK-06.** Represent manufacturing grids, minimum geometry, layer stacks, and routing direction.
- **PDK-07.** Load via definitions, via arrays, permitted stacks, and cut-class restrictions.
- **PDK-08.** Bind schematic symbols, parameterized layouts, extracted names, and simulator models.
- **PDK-09.** Define terminal order, bulk connections, default values, units, and multiplicity semantics.
- **PDK-10.** Define voltage, temperature, dimensions, model bins, and valid operating envelopes.
- **PDK-11.** Distinguish global process, device mismatch, library timing, and interconnect corners.
- **PDK-12.** Attach accepted DRC, LVS, ERC, antenna, density, EM/IR, and extraction runsets.
- **PDK-13.** Provide standard-cell, I/O, macro, memory, filler, tap, decap, and seal-ring libraries.
- **PDK-14.** Reconcile Liberty, LEF, stream, netlist, symbol, and behavioral views.
- **PDK-15.** Track SPICE, Verilog-A, compiled OSDI, and device-model compatibility by engine.
- **PDK-16.** Check cross-view dimensions, polarity, device names, pin order, and parameter ranges.
- **PDK-17.** Preview process or stack migration with model, rule, layer, and topology differences.
- **PDK-18.** Support multiple PDKs within a system with explicit die and library namespaces.
- **PDK-19.** Surface supported subsets, unsupported options, missing collateral, and independent process evidence.
- **PDK-20.** Build custom process descriptions with explicit rule coverage and a validation fixture.
- **PDK-21.** Preserve source licenses, permitted redistribution, local overrides, and package provenance.
- **PDK-22.** Compare two PDK revisions and identify affected devices, rules, views, and saved runs.

## Schematic capture

References. [Virtuoso Layout Suite and schematic integration](https://www.cadence.com/en_US/home/resources/datasheets/virtuoso-layout-suite-ds.html) · [Xschem component properties](https://xschem.sourceforge.io/stefan/xschem_man/component_property_syntax.html) · [Xschem netlisting](https://xschem.sourceforge.io/stefan/xschem_man/netlisting.html)

- **SCH-01.** Place, group-select, move, stretch, duplicate, rotate, mirror, and align components.
- **SCH-02.** Wire orthogonal or free-angle paths with bend control, snapping, and explicit junctions.
- **SCH-03.** Distinguish crossing wires, intentional junctions, and floating or no-connect pins.
- **SCH-04.** Move devices while retaining intentional connectivity and labeled nets.
- **SCH-05.** Create local, hierarchical, global, power, and ground nets with explicit scope.
- **SCH-06.** Edit vector buses, ordered slices, concatenations, bundles, and differential pairs.
- **SCH-07.** Create hierarchical subschematics from selections and navigate up or down in context.
- **SCH-08.** Generate symbols from ports and edit graphics, pin placement, labels, and display attributes.
- **SCH-09.** Manage pin direction, electrical type, order, function, default tie, and connect-by-name rules.
- **SCH-10.** Create repeated instances, arrays, parameterized cells, and reusable schematic blocks.
- **SCH-11.** Edit instance, cell, design, borrowed, and inherited parameter values with units.
- **SCH-12.** Support expressions, on-canvas value display, and parameter sweeps tied to stable IDs.
- **SCH-13.** Edit properties in bulk and review reference, model, or parameter replacements before committing.
- **SCH-14.** Cross-probe from a schematic net or device into layout, simulation, or physical findings.
- **SCH-15.** Highlight complete nets across sheets, hierarchy, aliases, and buses.
- **SCH-16.** Trace power paths and identify power domains, ground references, and unconnected terminals.
- **SCH-17.** Run electrical rule checks for pin conflicts, floating inputs, shorts, and domain mismatches.
- **SCH-18.** Place sources, meters, test points, stimulus blocks, and simulator control directives.
- **SCH-19.** Maintain testbench and device-under-test interfaces through hierarchy changes.
- **SCH-20.** Generate hierarchical and flattened netlists with model binding, units, and source maps.
- **SCH-21.** Read and review differences between two schematics by net, device, parameter, or interface.
- **SCH-22.** Create annotations, tables, drawing frames, page references, and documentation views.
- **SCH-23.** Print or export scalable schematics with consistent symbols, fonts, and legibility.
- **SCH-24.** Locate a netlist, simulator, or checker diagnostic at its originating schematic object.

## Libraries and reusable IP

References. [Synopsys design and IP portfolio](https://www.synopsys.com/products.html) · [Cadence product catalog](https://www.cadence.com/en_US/home/tools/tools-a-z.html) · [Xschem symbol properties](https://xschem.sourceforge.io/stefan/xschem_man/symbol_property_syntax.html)

- **LIB-01.** Search, filter, preview, favorite, and place devices by function, process, and availability.
- **LIB-02.** Browse symbols, schematic, layout, abstract, model, and documentation together.
- **LIB-03.** Author parameterized library cells with editable, validated parameters and default recipes.
- **LIB-04.** Provide process MOS, bipolar, diode, resistor, capacitor, inductor, varactor, and substrate devices.
- **LIB-05.** Provide high-voltage, RF, isolated, ESD, and special-purpose devices where qualified.
- **LIB-06.** Package reuse-ready references, current mirrors, amplifiers, comparators, converters, PLLs, and regulators.
- **LIB-07.** Manage standard cells, macros, pad libraries, and mixed-signal IP abstracts.
- **LIB-08.** Package digital building blocks with RTL, register maps, verification, constraints, and physical models.
- **LIB-09.** Generate and validate interface variants, parameter ranges, and naming conventions.
- **LIB-10.** Replace a symbol or device with a compatible alternative while preserving links and parameters.
- **LIB-11.** Review an update against previous pin, footprint, model, and timing contracts.
- **LIB-12.** Distribute and install versioned libraries with dependency and license metadata.
- **LIB-13.** Bind local aliases to upstream model, catalog, and device identities.
- **LIB-14.** Generate physical cells deterministically and retain their recipe and override history.
- **LIB-15.** Support reusable generator scripts and verified parameter presets.
- **LIB-16.** Check that a reused block’s schematic, physical boundary, pin names, and abstracts agree.
- **LIB-17.** Search by admissible supply, frequency, class, PPA, or interface requirements.
- **LIB-18.** Track owner, origin, verification state, revision, licensing, and known integration constraints.

## Custom layout

References. [Cadence Virtuoso Layout Suite](https://www.cadence.com/en_US/home/resources/datasheets/virtuoso-layout-suite-ds.html) · [KLayout manual](https://www.klayout.de/doc/manual/index.html) · [Magic source and tools](https://github.com/RTimothyEdwards/magic)

- **LAY-01.** Draw rectangles, polygons, wires, paths, circles, arcs, and curved approximations.
- **LAY-02.** Edit polygon vertices, stretch edges, change widths, and preserve holes.
- **LAY-03.** Snap to manufacturing grid, tracks, pins, vertices, edges, and reference points.
- **LAY-04.** Select by geometry, net, type, layer, interaction area, hierarchy, or connectivity.
- **LAY-05.** Configure layer visibility, selection, lock, drawing purpose, and display styles.
- **LAY-06.** Apply union, intersection, subtraction, XOR, sizing, clipping, and polygon cleanup.
- **LAY-07.** Move, rotate, mirror, copy, align, distribute, and array by reference.
- **LAY-08.** Create and edit cell instances, arrays, and variants in hierarchy.
- **LAY-09.** Enter edit-in-place, set display depth, flatten selectively, and preserve hierarchy on export.
- **LAY-10.** Generate, update, and detach parameterized physical cells with preserved overrides.
- **LAY-11.** Place devices directly from schematic connectivity and expose unplaced or unbound items.
- **LAY-12.** Cross-probe instance, terminal, net, and violation across schematic and layout.
- **LAY-13.** Create electrical ports, labels, pin polygons, and physical terminal shapes.
- **LAY-14.** Define boundary shapes, keepouts, blockages, routing obstructions, and placement regions.
- **LAY-15.** Build common-centroid, interdigitated, mirrored, and matched arrays with dummies.
- **LAY-16.** Support fingering, series and parallel multiplicities, abutment, and diffusion sharing.
- **LAY-17.** Generate guard rings, taps, shielding, wells, deep wells, and isolation structures.
- **LAY-18.** Generate spiral, transformer, passive, high-voltage, diode, and ESD geometries by profile.
- **LAY-19.** Guide power-grid and substrate connectivity through actual layer and contact rules.
- **LAY-20.** Overlay two layouts and review XOR markers by cell, layer, and coordinate.
- **LAY-21.** Measure distance, width, area, perimeter, enclosure, spacing, and route length.
- **LAY-22.** View large hierarchies efficiently with incremental rendering and indexed selection.
- **LAY-23.** Inspect physical stacks in a scale-accurate 3D view and export diagrams.
- **LAY-24.** Export and independently read back layer purposes, labels, transforms, arrays, and pins.
- **LAY-25.** Handle partial edits and merges without changing geometry outside the reviewed scope.

## Routing and layout constraints

References. [Cadence layout automation](https://www.cadence.com/en_US/home/resources/datasheets/virtuoso-layout-suite-ds.html) · [Magic](https://github.com/RTimothyEdwards/magic) · [Studio vias](docs/LAYOUT_VIAS.md)

- **RTE-01.** Route interactively by point, terminal, or net with a committed preview.
- **RTE-02.** Guide width, spacing, bend, jog, end-of-line, and grid rules while drawing.
- **RTE-03.** Avoid obstacles and support push-and-shove routing with explicit affected geometry.
- **RTE-04.** Select valid via types, cut arrays, stack limits, enclosure, and redundant contacts.
- **RTE-05.** Propose automatic via insertion at compatible overlaps with preview and validation.
- **RTE-06.** Preserve pin access, track alignment, and connectivity while stretching or rerouting.
- **RTE-07.** Route differential pairs with coupled spacing, symmetry, and length constraints.
- **RTE-08.** Match signal lengths, tune target delay, and report physical and electrical mismatch.
- **RTE-09.** Route wide power nets, current straps, rings, shields, and ground returns.
- **RTE-10.** Apply routing layers, widths, nondefault rules, allowed vias, and high-voltage clearance by net class.
- **RTE-11.** Bind constraints to nets, instances, pairs, symmetry groups, and regions.
- **RTE-12.** Guide matched placement, orientation, abutment, proximity, and shielding constraints.
- **RTE-13.** Plan analog and digital route channels, crossings, and return paths at block level.
- **RTE-14.** Estimate congestion and route resources before physically blocking the floorplan.
- **RTE-15.** Identify stale or newly violated constraints as schematic, layout, or PDK changes.
- **RTE-16.** Review unresolved terminals and incomplete nets with a jump to the missing segment.
- **RTE-17.** Repair opens, shorts, spacing, or vias through scoped previews and undoable edits.
- **RTE-18.** Report cross-domain nets, proximity violations, and routing exceptions with an exportable rationale.

## Analog simulation

References. [Cadence ADE Suite](https://www.cadence.com/en_US/home/resources/datasheets/virtuoso-ade-suite-ds.html) · [ngspice manual](https://ngspice.sourceforge.io/docs.html) · [Sandia Xyce](https://xyce.sandia.gov/about-xyce/) · [Analog Devices LTspice](https://www.analog.com/en/resources/design-tools-and-calculators/ltspice-simulator.html)

- **SIM-01.** Run named, repeatable analyses with a pinned simulator, netlist, model files, and environment.
- **SIM-02.** Calculate DC operating points and inspect currents, regions, power, and small-signal device quantities.
- **SIM-03.** Sweep sources, device parameters, temperature, load, geometry, and design variables.
- **SIM-04.** Run linear AC analysis for magnitude, phase, impedance, transfer, and gain.
- **SIM-05.** Run transient analysis with configurable timestep, initial conditions, sources, and stop criteria.
- **SIM-06.** Run small-signal noise analysis and integrate noise over specified frequency bands.
- **SIM-07.** Report output-referred and input-referred noise with per-source contribution.
- **SIM-08.** Calculate transfer function, poles and zeros, sensitivity, and diagnostic derivatives.
- **SIM-09.** Measure loop gain, stability margins, return ratio, and startup behavior.
- **SIM-10.** Measure distortion with FFT, THD, SINAD, SFDR, and windowing controls.
- **SIM-11.** Calculate group delay, settling, slew, jitter, propagation delay, and rise/fall time.
- **SIM-12.** Support behavioral sources, arbitrary waveforms, file stimulus, and controlled sources.
- **SIM-13.** Load BSIM, bipolar, passive, and specialized device models with verified parameter handling.
- **SIM-14.** Support hierarchical and extracted decks, model includes, sections, and scoped parameters.
- **SIM-15.** Import and run compatible SPICE decks with explicit dialect diagnostics.
- **SIM-16.** Support chained analyses, batch scripting, measurements, and captured simulation programs.
- **SIM-17.** Preserve node and instance identities between results and schematic or layout.
- **SIM-18.** Report convergence, singularities, undefined devices, missed timesteps, and numerical tolerance issues.
- **SIM-19.** Expose initialization, numerical method, integration, homotopy, and convergence controls.
- **SIM-20.** Run long jobs with progress, cancellation, interruption recovery, and bounded time or storage.
- **SIM-21.** Support scalable multi-core, distributed or accelerated engines through validated adapters.
- **SIM-22.** Compare independent simulators within declared numeric tolerances for shared fixtures.
- **SIM-23.** Reproduce archived analyses with the exact inputs or explain which dependency changed.
- **SIM-24.** Capture simulation effort, accuracy, and memory tradeoffs without hiding unmet specifications.
- **SIM-25.** Tie every pass or fail to the measured condition, limit, uncertainty, and source revision.

## Experiments and optimization

References. [Cadence ADE Suite](https://www.cadence.com/en_US/home/resources/datasheets/virtuoso-ade-suite-ds.html) · [Synopsys design and signoff portfolio](https://www.synopsys.com/implementation-and-signoff.html) · [Studio analog optimizer](docs/ANALOG_OPTIMIZER.md)

- **EXP-01.** Save and share testbenches, probes, analyses, variables, measurements, and expected limits.
- **EXP-02.** Configure per-test and global inputs, overrides, and conditional test selection.
- **EXP-03.** Run one highlighted case or batch a selected, inspectable simulation plan.
- **EXP-04.** Define cross-products or explicit lists of PVT, RC, model, and load conditions.
- **EXP-05.** Run deterministic Monte Carlo with process and mismatch effects, seeds, distributions, and correlations.
- **EXP-06.** Fit distributions and report confidence intervals, convergence, and sampling error.
- **EXP-07.** Estimate yield with declared assumptions and confidence over the sampled space.
- **EXP-08.** Evaluate worst-case corners, sensitivity, and rare failures with recorded search methods.
- **EXP-09.** Compare candidate revisions by specification, condition, and measured margin.
- **EXP-10.** Tag regressions, waived failures, pending runs, and stale artifacts distinctly.
- **EXP-11.** Optimize sizes, bias, geometry, or topology against explicit multi-objective constraints.
- **EXP-12.** Produce Pareto fronts with preserved metrics, candidates, and tradeoff explanations.
- **EXP-13.** Provide gm/Id, current density, intrinsic gain, capacitance, and device characterization curves.
- **EXP-14.** Generate and validate lookup tables for device dimensions, bias, process, and operating regime.
- **EXP-15.** Support constrained tuning, parameter bounds, quantization, and process-aware substitutions.
- **EXP-16.** Review, compare, and apply a chosen candidate as an undoable design edit.
- **EXP-17.** Compare schematic and extracted results with the same stimuli, limits, and numerical tolerances.
- **EXP-18.** Run distributed experiments with stable task identity, caching, retry, and resumable runs.
- **EXP-19.** Generate characterization dashboards and export reviewable results with exact run provenance.
- **EXP-20.** Support statistical model fitting and compare fits to independent validation data.

## Waveforms and results

References. [Cadence ADE Suite](https://www.cadence.com/en_US/home/resources/datasheets/virtuoso-ade-suite-ds.html) · [Analog Devices LTspice](https://www.analog.com/en/resources/design-tools-and-calculators/ltspice-simulator.html) · [Studio user guide](docs/USER_GUIDE.md#simulation)

- **WAV-01.** Plot analog, digital, event, vector, complex, and sampled signals with units.
- **WAV-02.** Search, group, hide, color, rename, and reorder traces by net or hierarchy.
- **WAV-03.** Pan, zoom, fit, and share axes across linked plots.
- **WAV-04.** Switch linear, log, decibel, polar, Smith, and complex-plane views where applicable.
- **WAV-05.** Measure cursors, deltas, extrema, RMS, slope, duty, frequencies, and thresholds.
- **WAV-06.** Compare any compatible runs and display engine, settings, and design revision for each.
- **WAV-07.** Difference, ratio, normalize, resample, and align compatible traces with stated interpolation.
- **WAV-08.** Run expression-based measurements and save reusable formulas with inputs and units.
- **WAV-09.** View time, frequency, eye diagrams, and jitter or noise distributions from the same data.
- **WAV-10.** Display sweep families, corner envelopes, histograms, correlations, and pass/fail limits.
- **WAV-11.** Preserve samples and reveal decimation or interpolation of plotted traces.
- **WAV-12.** Support very large analog and digital captures with indexed loading.
- **WAV-13.** Cross-probe a trace into the schematic, layout, RTL, or timing path.
- **WAV-14.** Read simulations from documented RAW, CSV, VCD, FST, and other selected formats.
- **WAV-15.** Export numerical results and publication-ready plots with units and provenance.
- **WAV-16.** Persist plot layouts, cursors, measurements, and comparisons with the run.
- **WAV-17.** Explain failed or cancelled runs and make engine diagnostics and inputs inspectable.
- **WAV-18.** Expose accessible frame labels, trace tables, keyboard measurements, and distinguishable line styles.

## Behavioral and mixed-signal

References. [Accellera standards](https://accellera.org/downloads/standards) · [Accellera UVM-MS](https://www.accellera.org/activities/working-groups/uvm-ms/uvm-ms-faq) · [Cadence product catalog](https://www.cadence.com/en_US/home/tools/tools-a-z.html) · [Studio SAR co-simulation](docs/MIXED_SIGNAL_SAR.md)

- **AMS-01.** Author, validate, and compile supported Verilog-A and Verilog-AMS models.
- **AMS-02.** Support real-number models, wreal semantics, and SystemVerilog real-valued interfaces where supported.
- **AMS-03.** Bind analog, behavioral, digital, transistor-level, and extracted instances in one hierarchy.
- **AMS-04.** Define disciplines, natures, units, resolution, terminals, and compatible connections.
- **AMS-05.** Insert and inspect logic-to-electrical and electrical-to-logic connect modules.
- **AMS-06.** Configure thresholds, hysteresis, slew, impedance, sample timing, and level translation.
- **AMS-07.** Coordinate solver events with HDL clocks and expose accepted timesteps and synchronization points.
- **AMS-08.** Define causality, convergence, event ordering, rollback, and interpolation at solver boundaries.
- **AMS-09.** Simulate unequal time scales, asynchronous crossings, startup, and power gating.
- **AMS-10.** Propagate X/Z and ambiguous threshold crossings through explicit bridge policy.
- **AMS-11.** Cross-trigger analog and digital waveform debugging with a shared time base.
- **AMS-12.** Apply assertions and scoreboards to analog thresholds, digital states, and mixed events.
- **AMS-13.** Simulate mixed-signal interfaces with extracted layout, package, and jitter models.
- **AMS-14.** Support ADC/DAC metrics, code histograms, INL/DNL, ENOB, clipping, and missing codes.
- **AMS-15.** Verify timing, settling, calibration, and error recovery for mixed-signal control loops.
- **AMS-16.** Compare behavioral and transistor implementations over declared operating conditions.
- **AMS-17.** Exchange selected models, stimuli, tolerances, and results with supported external simulators.
- **AMS-18.** Debug interface mismatch, event drift, solver failure, and analog-to-digital conversion errors.
- **AMS-19.** Reproduce a complete mixed-signal regression from a portable test plan and dependency lock.

## RF and microwave

References. [Keysight RF Suite](https://www.keysight.com/us/en/products/design-engineering-software/electronic-design-automation/rf-suite.html) · [Keysight GoldenGate](https://www.keysight.com/my/en/products/software/pathwave-design-software/pathwave-rfic-design-software.html) · [ngspice analyses](https://ngspice.sourceforge.io/docs.html) · [Qucs-S simulator backends](https://qucs-s-help.readthedocs.io/en/latest/overview/choosing-a-sim-backend.html)

- **RF-01.** Capture port impedances, reference planes, transmission lines, RF grounds, and bias tees.
- **RF-02.** Plot one-port and multiport S, Y, Z, ABCD, and mixed-mode parameters.
- **RF-03.** Import and export Touchstone data with known units, port order, and impedance.
- **RF-04.** Renormalize, cascade, terminate, and de-embed network models.
- **RF-05.** Compare passivity, reciprocity, causality, and interpolation of measured or extracted models.
- **RF-06.** Use Smith charts, impedance matching, stability circles, and noise or gain contours.
- **RF-07.** Measure noise figure, gain compression, IP2/IP3, linearity, and intermodulation distortion.
- **RF-08.** Run load-pull and source-pull sweeps with power, efficiency, and impedance contours.
- **RF-09.** Solve driven and autonomous periodic steady state.
- **RF-10.** Run single-tone and multi-tone harmonic balance with harmonic and mixing controls.
- **RF-11.** Run periodic AC, transfer, noise, and conversion analyses.
- **RF-12.** Analyze oscillation startup, frequency, phase noise, jitter, and injection locking.
- **RF-13.** Run envelope and modulated-signal simulation for long or widely separated time scales.
- **RF-14.** Measure conversion gain, image rejection, sidebands, and mixer feedthrough.
- **RF-15.** Calculate EVM, ACPR, spectral masks, and swept-band modulation metrics.
- **RF-16.** Synthesize matching networks, filters, couplers, and transmission-line geometries.
- **RF-17.** Generate and characterize inductors, transformers, baluns, varactors, and differential structures.
- **RF-18.** Compare circuit, extracted, and field-solver results at named ports and reference planes.
- **RF-19.** Track model applicability across frequency, swing, bias, temperature, and substrate conditions.
- **RF-20.** Sweep RF design targets by process corner, variability, matching, and stability margin.
- **RF-21.** Measure crosstalk, isolation, feedthrough, impedance imbalance, and return losses.
- **RF-22.** Include RF package interconnect, substrate coupling, and de-embedded test structures.

## Extraction and back-annotation

References. [Synopsys StarRC and signoff](https://www.synopsys.com/implementation-and-signoff.html) · [Cadence extraction products](https://www.cadence.com/en_US/home/tools/tools-a-z.html) · [OpenROAD extraction flow](https://openroad-flow-scripts.readthedocs.io/en/latest/mainREADME.html) · [Studio process RC](docs/ANALOG_IMPLEMENTATION_EXTENSIONS.md)

- **PEX-01.** Bind extraction to the exact streamed or saved layout, process stack, deck, and engine.
- **PEX-02.** Extract layout devices with terminal order, body ties, dimensions, pins, and instance identity.
- **PEX-03.** Extract sheet, contact, and via resistance, including relevant distributed resistance.
- **PEX-04.** Extract ground, fringe, overlap, substrate, and cross-net coupling capacitance.
- **PEX-05.** Extract inductance, mutual coupling, skin effect, and frequency-dependent losses where required.
- **PEX-06.** Support explicit nominal, minimum, and maximum interconnect corners independent of model PVT.
- **PEX-07.** Preserve hierarchy, arrays, labels, net aliases, and port binding.
- **PEX-08.** Flatten only chosen scope with a retained mapping to the original design.
- **PEX-09.** Extract full blocks, dedicated nets, or changed regions with explicit completeness.
- **PEX-10.** Support model-order reduction with controls and measured error across the intended bandwidth.
- **PEX-11.** Export SPEF, SPF/DSPF, extracted SPICE, and supported simulator netlist views.
- **PEX-12.** Bind extracted models to testbench DUTs and mapped digital implementation.
- **PEX-13.** Locate extracted devices and parasitics in schematic and layout through stable cross-reference.
- **PEX-14.** Account for effects of fill, shielding, via arrays, and neighboring structures.
- **PEX-15.** Compare schematic and extracted waveforms, timing, margins, and design specifications.
- **PEX-16.** Calibrate extractors against test structures, accepted decks, and independent references.
- **PEX-17.** Detect injected parasitic faults, missing layers, stale artifacts, and unsupported devices.
- **PEX-18.** Track extraction temperature, process assumptions, approximation scope, and runtime.
- **PEX-19.** Reproduce and compare extraction from identical inputs and verify retained reports.

## Physical verification

References. [KLayout DRC](https://klayout.de/doc/manual/drc.html) · [KLayout LVS](https://www.klayout.de/doc/manual/lvs_overview.html) · [Netgen](https://github.com/RTimothyEdwards/netgen) · [Cadence physical signoff](https://www.cadence.com/en_US/home/solutions/advanced-node-solutions/digital-advanced-node.html) · [Synopsys IC Validator portfolio](https://www.synopsys.com/implementation-and-signoff.html)

- **PHY-01.** Run interactive local DRC on changed geometry for fast editing feedback.
- **PHY-02.** Run approved full-block and full-chip DRC decks on the final streamed geometry.
- **PHY-03.** Check width, spacing, enclosure, overlap, extension, area, and manufacturing grid.
- **PHY-04.** Check notch, minimum hole, end-of-line, cut class, and multi-pattern interactions where applicable.
- **PHY-05.** Check device recognition, layer purpose, illegal combinations, and required process markers.
- **PHY-06.** Cross-check pin placement, label syntax, top cell, hierarchy, and interfaces.
- **PHY-07.** Extract and compare hierarchical schematic and physical netlists with LVS.
- **PHY-08.** Report opens, shorts, permutations, unmatched nets and devices, and parameter discrepancies.
- **PHY-09.** Handle device reductions and legal source/drain permutations with inspectable definitions.
- **PHY-10.** Compare pin directions, top-level interfaces, and power or bulk assignments.
- **PHY-11.** Support independent schematic and layout source selection and preserve exact inputs.
- **PHY-12.** Manage LVS black boxes and interface contracts with evidence for their boundaries.
- **PHY-13.** Run process-specific antenna checks on real connected layers and terminal areas.
- **PHY-14.** Run local and global density checks with true process windows and exclusions.
- **PHY-15.** Generate, review, and recheck metal fill with hierarchy and electrical context.
- **PHY-16.** Maintain physical and electrical compatibility after dummy-fill insertion.
- **PHY-17.** Run power/ground continuity, tap, well, isolation, and substrate checks.
- **PHY-18.** Run voltage-aware ERC, pad-domain, ESD path, and latch-up checks where required.
- **PHY-19.** Display interactive violation markers with layer, rule, explanation, and exact location.
- **PHY-20.** Filter, group, assign, compare, and export findings across runs and design revisions.
- **PHY-21.** Scope waivers by rule, geometry, design hash, rationale, approval, and expiry.
- **PHY-22.** Run fault controls that guarantee deliberate opens, shorts, parameter errors, and missing reports are detected.
- **PHY-23.** Reject stale, incomplete, contradictory, or nonmatching verification evidence.
- **PHY-24.** Run hierarchical, incremental, tiled, or parallel checks with equivalence to the required final check.
- **PHY-25.** Import external result databases and cross-probe into an independently read stream.
- **PHY-26.** Evaluate deck/rule enablement and show required checks that could not run.

## Reliability and manufacturability

References. [Siemens Calibre PERC and 3DPERC](https://eda.sw.siemens.com/en-US/ic/calibre-design/reliability-verification/perc) · [Cadence signoff and design for manufacturing](https://www.cadence.com/en_US/home/solutions/advanced-node-solutions/digital-advanced-node.html) · [Synopsys reliability portfolio](https://www.synopsys.com/implementation-and-signoff.html)

- **REL-01.** Check device operating limits for DC and transient voltage, current, and temperature.
- **REL-02.** Check terminal voltage relationships and oxide limits across startup, power states, and faults.
- **REL-03.** Verify electrical paths, resistance, clamps, and discharge topology for ESD protection.
- **REL-04.** Check latch-up proximity, body ties, tap placement, guard rings, and isolation.
- **REL-05.** Calculate interconnect current density, via stress, and electromigration over worst conditions.
- **REL-06.** Model reliability changes from BTI, hot-carrier effects, and dielectric breakdown where supported.
- **REL-07.** Report lifetime assumptions, workload duty cycle, acceleration models, and bounds.
- **REL-08.** Check analog self-heating, thermal runaway, and temperature-sensitive parameter shifts.
- **REL-09.** Check supply sequencing, reverse current, level-shifter and isolation use, and domain crossings.
- **REL-10.** Identify electrical overstress and buses or interfaces exposed to illegal states.
- **REL-11.** Run reliability-specific fault controls and retain failing conditions with paths and geometry.
- **REL-12.** Detect process-specific hotspots, layout patterns, restricted patterns, and coloring conflicts.
- **REL-13.** Analyze critical area, systematic pattern/yield hazards, and manufacturability ranking.
- **REL-14.** Repair recommended spacing, via redundancy, and pattern hazards with a reviewed preview.
- **REL-15.** Account for CMP, density gradients, fill-induced variation, and local layout effects.
- **REL-16.** Check redundant vias, missing stitch points, return paths, and yield-critical intersections.
- **REL-17.** Review waivers with owner, evidence, expiry, accepted target, and potential consequence.
- **REL-18.** Correlate signoff failures with measured defects or field return evidence when available.
- **REL-19.** Track reliability requirements by foundry, product class, qualification, and exact package context.

## Architecture and RTL

References. [Accellera standards](https://accellera.org/downloads/standards) · [Surelog and UHDM](https://github.com/chipsalliance/Surelog) · [Synopsys chip design](https://www.synopsys.com/implementation-and-signoff.html) · [Cadence Stratus and verification catalog](https://www.cadence.com/en_US/home/tools/tools-a-z.html)

- **RTL-01.** Define system requirements, interfaces, budgets, clocks, resets, and design boundaries.
- **RTL-02.** Author and browse Verilog and SystemVerilog with syntax coloring and diagnostics.
- **RTL-03.** Support VHDL and mixed HDL designs through verified tool adapters.
- **RTL-04.** Preprocess defines, include files, packages, and language-specific build order.
- **RTL-05.** Elaborate parameterized modules, packages, interface instances, and generated hierarchy.
- **RTL-06.** Jump from nets, instances, types, and diagnostics to declarations and uses.
- **RTL-07.** Support completion, rename preview, search, formatting, and per-language editor settings.
- **RTL-08.** Manage multiple source sets, top modules, test tops, generated sources, and dependency locks.
- **RTL-09.** Generate readable hierarchy, block diagrams, schematics, and interface documentation.
- **RTL-10.** Define buses, memory maps, interrupts, resets, address decode, and protocol bindings.
- **RTL-11.** Generate consistent RTL, firmware headers, documentation, and tests from register definitions.
- **RTL-12.** Import and emit supported SystemRDL and IP-XACT views.
- **RTL-13.** Assemble reusable SoC blocks, bus fabrics, interconnect, timers, memories, and bridges.
- **RTL-14.** Verify interface compatibility and clock/reset domain intent at block boundaries.
- **RTL-15.** Configure compute, traffic, memory, and bandwidth estimates at architecture level.
- **RTL-16.** Simulate transaction-level workloads through SystemC/TLM or compatible frameworks.
- **RTL-17.** Integrate HLS from C, C++, or supported models with traceable generated RTL and constraints.
- **RTL-18.** Generate formal and simulation wrappers for protocols and external devices.
- **RTL-19.** Track configurable variants, supported data widths, and generated design provenance.
- **RTL-20.** Cross-probe edited RTL across design hierarchy, elaboration, simulation, synthesis, and timing.
- **RTL-21.** Manage power-intent and clock-domain metadata alongside design source.

## Digital simulation and verification

References. [Synopsys VCS](https://www.synopsys.com/verification/simulation/vcs.html) · [Synopsys Verdi](https://www.synopsys.com/verification/debug/verdi.html) · [Verilator](https://verilator.org/guide/latest/overview.html) · [cocotb](https://docs.cocotb.org/en/v1.9.0/simulator_support.html) · [Accellera UVM](https://accellera.org/downloads/standards/uvm)

- **VER-01.** Compile and simulate RTL, behavioral, and gate-level designs with pinned engines.
- **VER-02.** Support four-state and two-state simulations with explicit X/Z semantics.
- **VER-03.** Run self-checking testbenches and capture compile, elaboration, and simulation logs.
- **VER-04.** Support cocotb, native HDL testbenches, VPI, or documented equivalent interfaces.
- **VER-05.** Support SystemVerilog UVM sequences, agents, drivers, monitors, and scoreboards.
- **VER-06.** Select deterministic seeds, constrained-random modes, and randomized stimulus.
- **VER-07.** Use directed tests, reference scoreboards, property assertions, and protocol verification IP.
- **VER-08.** Track code coverage of lines, branches, toggles, FSMs, and expressions where supported.
- **VER-09.** Track functional coverage, coverpoints, crosses, assertions, and waived bins.
- **VER-10.** Merge coverage only for compatible design and tool versions and export coverage data.
- **VER-11.** Create verification plans that trace requirements to tests, coverage, and results.
- **VER-12.** Debug by source line, breakpoint, timestamp, assertion, signal driver, or transaction.
- **VER-13.** View and cross-probe VCD/FST waveforms, packed values, unknowns, and details of transitions.
- **VER-14.** Search waveform patterns and compare failing traces against passing revisions.
- **VER-15.** Replay failures with command, seed, data, environment, and retained output.
- **VER-16.** Run gate-level simulations with SDF back-annotation and timing-check reporting.
- **VER-17.** Support low-power simulation for domain transitions, isolation, and state retention.
- **VER-18.** Run event-oriented or cycle-accurate simulation with stated speed and fidelity characteristics.
- **VER-19.** Build regression suites with parallel jobs, reruns, flake tracking, and reproducibility.
- **VER-20.** Surface assertion and expected-output causes instead of relying on exit status alone.
- **VER-21.** Support portable stimulus or equivalent scenario generation for multi-block verification.
- **VER-22.** Inject faults for resilience and recovery testing under explicit targets and assumptions.
- **VER-23.** Track design, coverage, and requirement closure across block and system-level tests.

## Static and formal verification

References. [Synopsys VC Formal](https://www.synopsys.com/verification/static-and-formal-verification/vc-formal.html) · [Siemens Questa formal](https://eda.sw.siemens.com/en-US/ic/questa/formal-verification/) · [YosysHQ tools](https://yosyshq.readthedocs.io/en/latest/tools.html) · [EQY](https://yosyshq.readthedocs.io/projects/eqy/en/stable/quickstart.html)

- **FRM-01.** Lint hierarchy, syntax, synthesis compatibility, and coding conventions.
- **FRM-02.** Detect width truncation, sign extension, incomplete cases, unintended latches, and inferred loops.
- **FRM-03.** Run early clock-domain crossing checks for clocks, synchronizers, and reconvergent signals.
- **FRM-04.** Run reset-domain crossing checks for reset behavior, release order, and synchronizers.
- **FRM-05.** Validate constraints and identify unsynchronized paths without an explicit disposition.
- **FRM-06.** Check structural low-power rules, isolation, retention, level shifting, and domain connectivity.
- **FRM-07.** Support bounded model checking with limits, counterexamples, and coverage.
- **FRM-08.** Support inductive proof and unbounded property checking through appropriate engines.
- **FRM-09.** Track assumptions, assertions, covers, proof status, or inconclusive results.
- **FRM-10.** Report vacuous proofs, contradictory assumptions, or unreachable scenarios.
- **FRM-11.** Check combinational and sequential equivalence between RTL and mapped netlists.
- **FRM-12.** Compare equivalence after retiming, memory mapping, parameter changes, or physical ECOs.
- **FRM-13.** Run equivalence partitions and review unmatched cut points and compared scope.
- **FRM-14.** Prove memory control, protocol stability, arithmetic properties, and register access behavior.
- **FRM-15.** Check information flow, access controls, and isolation invariants for supported models.
- **FRM-16.** Check deadlock, livelock, fairness, and liveness with explicit semantics.
- **FRM-17.** Display counterexamples as waveforms and cross-probe implicated RTL or constraints.
- **FRM-18.** Retain proof version, engine, bounds, assumptions, artifacts, and reproducibility.
- **FRM-19.** Record justified waivers and show outstanding obligations per revision.

## Synthesis

References. [Synopsys digital implementation](https://www.synopsys.com/implementation-and-signoff.html) · [YosysHQ tools](https://yosyshq.readthedocs.io/en/latest/tools.html) · [OpenROAD Flow synthesis](https://openroad-flow-scripts.readthedocs.io/en/latest/mainREADME.html)

- **SYN-01.** Elaborate, synthesize, and technology-map supported RTL to the chosen standard-cell library.
- **SYN-02.** Manage constraints, operating modes, top selection, source manifests, and safe overrides.
- **SYN-03.** Configure allowed libraries, dont-use lists, black boxes, and hard macros.
- **SYN-04.** Infer and map memories, registers, arithmetic, muxes, DSP, and supported specialized cells.
- **SYN-05.** Optimize logic through constant propagation, sharing, balancing, and dead-code removal.
- **SYN-06.** Configure hierarchy preservation, flattening, incremental reuse, and design partitions.
- **SYN-07.** Support clock gating, latch mapping, enable handling, and explicit clock structures.
- **SYN-08.** Optimize area, delay, power, fanout, and testability with agreed constraints.
- **SYN-09.** Support retiming, resource optimization, and optional physical information during synthesis.
- **SYN-10.** Emit a mapped netlist, effective SDC, constraints report, and source-to-instance map.
- **SYN-11.** Report cell counts, area, inferred blocks, unresolved modules, and clock characteristics.
- **SYN-12.** Diagnose unsupported code, unbound cells, unused logic, and unconstrained timing groups.
- **SYN-13.** Cross-probe synthesized cells and nets into their originating RTL.
- **SYN-14.** Inspect hierarchy, logic cones, fan-in/fan-out, and mapped schematic views.
- **SYN-15.** Check netlist formal equivalence and interface preservation.
- **SYN-16.** Compare mapping candidates by target, constraints, area, timing, and power.
- **SYN-17.** Reuse stage outputs for incremental edits with complete input identity.
- **SYN-18.** Export technology-specific cell mappings, technology-independent netlists, and reports.
- **SYN-19.** Track tool-specific optimizations, unsupported constraints, and deterministic build settings.

## Physical implementation

References. [Cadence digital implementation](https://www.cadence.com/en_US/home/solutions/advanced-node-solutions/digital-advanced-node.html) · [OpenROAD Flow](https://openroad-flow-scripts.readthedocs.io/en/latest/mainREADME.html) · [LibreLane flow steps](https://librelane.readthedocs.io/en/latest/reference/step_config_vars.html)

- **IMP-01.** Select the implementation platform, technology, standard cells, macros, and run stages.
- **IMP-02.** Define die/core area, aspect ratio, utilization, rows, sites, and tracks.
- **IMP-03.** Plan and place I/O pins, pads, bumps, and interface keepouts.
- **IMP-04.** Place macros with legal orientations, halos, channels, guides, and obstructions.
- **IMP-05.** Support hierarchical block planning, partition pins, abstracts, and top-level assembly.
- **IMP-06.** Insert tap, endcap, well tie, filler, tie, decap, and spare cells consistently.
- **IMP-07.** Generate and verify power grids with rails, rings, stripes, straps, and connections.
- **IMP-08.** Run global placement with timing, routability, and density objectives.
- **IMP-09.** Legalize placement and report rule violations, density issues, and congestion.
- **IMP-10.** Run clock-tree synthesis for clock groups, gates, related clocks, skew, and latency.
- **IMP-11.** Repair timing, fanout, transition, capacitance, and electrical design-rule violations.
- **IMP-12.** Run global routing with per-layer demand, overflow, guides, and congestion displays.
- **IMP-13.** Run detailed routing with via legality, pin access, spacing, and use of routing tracks.
- **IMP-14.** Repair antenna violations with allowed changes and recheck the physical netlist.
- **IMP-15.** Add fill as required and re-extract final timing and noise.
- **IMP-16.** Preserve placement, wire and via geometry, pad routes, power connectivity, and hierarchy on stream-out.
- **IMP-17.** View checkpoints, compare placement and routing candidates, and inspect problematic regions.
- **IMP-18.** Cross-probe a timing path, cell, net, or route from RTL to mapped and routed views.
- **IMP-19.** Support incremental physical and functional ECOs with explicit affected geometry and rerun scope.
- **IMP-20.** Reuse clean implementation stages with compatible inputs and restart from validated checkpoints.
- **IMP-21.** Report area, utilization, congestion, wire length, via count, skew, power, and closure.
- **IMP-22.** Export and cross-check Verilog, DEF, LEF abstract, parasitics, constraints, and final stream.
- **IMP-23.** Verify abstract accuracy and readiness of the block for top-level integration.

## Timing signoff

References. [Cadence Tempus and digital signoff](https://www.cadence.com/en_US/home/solutions/advanced-node-solutions/digital-advanced-node.html) · [Synopsys signoff portfolio](https://www.synopsys.com/implementation-and-signoff.html) · [OpenSTA](https://github.com/The-OpenROAD-Project/OpenSTA) · [LibreLane timing corners](https://librelane.readthedocs.io/en/stable/usage/timing_corners.html)

- **STA-01.** Import Liberty, mapped netlists, SDC, parasitics, and operating modes.
- **STA-02.** Define primary, generated, virtual, and propagated clocks.
- **STA-03.** Set clock uncertainty, latency, skew, waveform, and source assumptions.
- **STA-04.** Model input/output delays, loads, driving strength, and time units.
- **STA-05.** Review false paths, multi-cycle paths, disabled arcs, and exceptions.
- **STA-06.** Verify setup and hold timing for each required view, path group, and corner.
- **STA-07.** Report WNS, TNS, failing endpoints, slack distributions, and worst paths.
- **STA-08.** Detect unconstrained endpoints, inactive clocks, missing paths, and undefined timing cases.
- **STA-09.** Run recovery/removal, pulse width, gating, asynchronous, and latch checks where required.
- **STA-10.** Report slew, capacitance, fanout, noise, signal integrity, and timing-rule violations.
- **STA-11.** Analyze multi-mode and multi-corner cases with separate library and RC dimensions.
- **STA-12.** Apply OCV, AOCV/POCV or library variation models where required and qualified.
- **STA-13.** Apply common path pessimism removal and expose graph/path-based assumptions.
- **STA-14.** Analyze coupling-induced delay shifts, crosstalk, and noise with final extraction.
- **STA-15.** Use propagated post-CTS and post-route clocks and check against ideal-clock baselines.
- **STA-16.** Compare pre-layout, routed, extracted, and ECO timing through bound artifacts.
- **STA-17.** Cross-probe path stages and slack into the schematic, hierarchy, or physical route.
- **STA-18.** Review the most effective corrective changes and preserve timing across all required modes.
- **STA-19.** Emit annotated path reports, human-readable summaries, and machine-readable status.
- **STA-20.** Export SDF and compare gate-level timing simulations to the signoff inputs.
- **STA-21.** Identify missing or contradictory summaries and reject incomplete signoff.
- **STA-22.** Use MCMM coverage reports and fault controls for violations, unconstrained paths, and missing corners.

## Power integrity

References. [Cadence Voltus and signoff](https://www.cadence.com/en_US/home/solutions/advanced-node-solutions/digital-advanced-node.html) · [OpenROAD IR drop](https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/psm) · [Ansys SIwave and HFSS](https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v251/en/Subsystems/HFSS3DLayout/Content/3DLayout/SIwaveSolutionsinHFSS3DLayout.htm)

- **PWR-01.** Define supplies, power domains, voltage areas, ground references, and operating states.
- **PWR-02.** Import, edit, validate, and export selected UPF or CPF power intent.
- **PWR-03.** Support retention, isolation, power switches, level shifters, and always-on connectivity.
- **PWR-04.** Track power-up, power-down, brownout, and reset sequencing requirements.
- **PWR-05.** Calculate static leakage, internal power, switching power, and energy by hierarchy.
- **PWR-06.** Estimate vectorless activity and report assumptions and uncertainty.
- **PWR-07.** Annotate activity from VCD/SAIF and record workload, time window, and unmatched signals.
- **PWR-08.** Compare estimated RTL, mapped, extracted, and measured power at matched conditions.
- **PWR-09.** Map power grid topology and trace from supply, pads, or bumps to the loads.
- **PWR-10.** Analyze static IR drop against required operating and package conditions.
- **PWR-11.** Analyze transient or dynamic IR drop and peak current across workload windows.
- **PWR-12.** Check current density and electromigration for metal, vias, contacts, and straps.
- **PWR-13.** Map power hot spots, voltage droop, and reliability markers onto the layout.
- **PWR-14.** Support voltage-aware timing or circuit simulation where droop affects closure.
- **PWR-15.** Calculate PDN impedance, resonance, decoupling, and step response.
- **PWR-16.** Use coupled package, die, board, and supply models with explicit boundaries.
- **PWR-17.** Evaluate simultaneous switching, ground bounce, and supply noise.
- **PWR-18.** Estimate die thermal conditions and feedback between power and temperature.
- **PWR-19.** Compare grid edits, reinforcement, decoupling, and placement changes before applying.
- **PWR-20.** Recheck affected power states and verify signoff against actual final connectivity.
- **PWR-21.** Report power and IR results by mode, corner, workload, rail, and requirement.
- **PWR-22.** Verify coverage of high-current paths, disconnected sources, and missing or inconsistent models.

## Design for test

References. [Cadence Modus DFT](https://www.cadence.com/en_US/home/resources/datasheets/cadence-modus-dft-software-solution-ds.html) · [Siemens Tessent](https://www.siemens.com/en-us/products/ic/tessent/) · [Synopsys test and design portfolio](https://www.synopsys.com/implementation-and-signoff.html) · [Accellera standards catalog](https://accellera.org/downloads/standards)

- **DFT-01.** Define manufacturing test strategy, test modes, clocks, resets, and external interfaces.
- **DFT-02.** Run testability checks for clocks, asynchronous controls, feedback, and unobservable logic.
- **DFT-03.** Insert scan cells and chains with domain, phase, lock-up, and test-clock constraints.
- **DFT-04.** Reorder scan chains for physical routing and verify chain connectivity.
- **DFT-05.** Configure scan compression, decompression, compaction, and X handling.
- **DFT-06.** Support boundary scan and JTAG TAP, chain descriptions, and connectivity checks.
- **DFT-07.** Support embedded-instrument access and documented descriptions for supported flows.
- **DFT-08.** Generate stuck-at fault patterns and fault coverage reports.
- **DFT-09.** Generate transition/delay patterns with launch, capture, and clock constraints.
- **DFT-10.** Support bridging, path-delay, cell-aware, and other applicable fault models.
- **DFT-11.** Run fault simulation, identify untested faults, and justify coverage exclusions.
- **DFT-12.** Integrate logic BIST and report signature, coverage, and test runtime.
- **DFT-13.** Integrate memory BIST across multiple memories and supported algorithms.
- **DFT-14.** Support memory redundancy analysis, repair information, and built-in self-repair.
- **DFT-15.** Verify cross-domain and low-power test states and clocking.
- **DFT-16.** Estimate test power, toggle activity, peak current, and pattern volume.
- **DFT-17.** Simulate scan and test patterns with functional and gate-level netlists.
- **DFT-18.** Export supported tester formats and retain pin, timing, vector, and mode definitions.
- **DFT-19.** Provide test mode constraints and STA closure for scan, capture, and at-speed clocks.
- **DFT-20.** Preserve design equivalence with documented test-mode assumptions.
- **DFT-21.** Support hierarchical and multi-die test planning with reviewed access paths.
- **DFT-22.** Diagnose scan failures and feed candidate defects back to net, cell, and coordinates.
- **DFT-23.** Track defect coverage, test time, pattern limits, and manufacturing acceptance by revision.
- **DFT-24.** Qualify analog and mixed-signal observation, calibration, and BIST where required.

## Cell and memory characterization

References. [Cadence characterization and signoff](https://www.cadence.com/en_US/home/solutions/advanced-node-solutions/digital-advanced-node.html) · [Synopsys PrimeLib and simulation](https://www.synopsys.com/implementation-and-signoff.html) · [OpenRAM](https://github.com/VLSIDA/OpenRAM)

- **CHR-01.** Define characterization stimuli, transition/load grids, PVT corners, and extraction views.
- **CHR-02.** Discover combinational functions, sequential behavior, drive strengths, and pin roles.
- **CHR-03.** Generate and validate timing arcs, conditional expressions, and pin-sense mappings.
- **CHR-04.** Measure cell delay, transition, setup, hold, pulse width, recovery, and removal.
- **CHR-05.** Measure input capacitance, output drive, internal power, leakage, and dynamic energy.
- **CHR-06.** Characterize state-dependent conditions, multi-input switching, and noise behavior.
- **CHR-07.** Generate table-based Liberty and supported waveform/current-source models.
- **CHR-08.** Generate variation data and validate statistical assumptions and units.
- **CHR-09.** Validate interpolation, extrapolation, monotonic behavior, and constraint consistency.
- **CHR-10.** Compare generated timing against independent raw simulation over representative points.
- **CHR-11.** Export model, netlist, abstract, stream, and functional model with matching pin definitions.
- **CHR-12.** Recharacterize affected cells and corners incrementally against exact model identity.
- **CHR-13.** Generate SRAM instances using validated options for word size, depth, ports, and banking.
- **CHR-14.** Export memory RTL, SPICE, Liberty, LEF, GDS, and integration metadata.
- **CHR-15.** Characterize memory read/write timing, retention, leakage, and access power.
- **CHR-16.** Check memory bistability, write margin, read margin, and low-voltage limits.
- **CHR-17.** Verify memory behavior, multi-port collisions, and macro interface constraints.
- **CHR-18.** Compile ROM or register-file macros with verified initialization and views.
- **CHR-19.** Support hardened custom macro characterization and port mapping.
- **CHR-20.** Compare library revisions and identify impacted timing, power, and implementation candidates.
- **CHR-21.** Document model quality, bounds, supported options, and reproducible characterization evidence.

## Tapeout and handoff

References. [Tiny Tapeout local hardening](https://tinytapeout.com/guides/local-hardening/) · [Tiny Tapeout submission requirements](https://tinytapeout.com/specs/) · [Studio acceptance targets](docs/PUBLIC_RELEASE_TARGETS.md) · [Studio release verification](docs/RELEASING.md)

### Verified first handoff scope

The [Tiny Tapeout SKY 26e source handoff](docs/TINY_TAPEOUT_HANDOFF.md) covers
the SKY130A HD UART on one tile. See the [qualification log](docs/QUALIFICATION_PROGRESS.md#tiny-tapeout-sky-26e-uart-source-handoff)
for the source revision and replay results.

| Feature IDs | Verified for the UART source package | Remaining for physical handoff |
| --- | --- | --- |
| TAP-01–04, TAP-14 | Named profile and pinned tool references. The official checker accepted the metadata and wrapper ports and generated the 161 × 111.52 µm tile configuration. Source simulation verified pin behavior, reset, and enable. | Verify effective tools, libraries, clock timing, pin geometry, layers, and power on the final layout. |
| TAP-15–17, TAP-19–20 | Reproducible ZIP with source and configuration hashes. The verifier rejected a missing file, a changed file, and an invalid path. | Bind final geometry, netlists, decks, reports, and their provenance. Add comparison against current design revisions. |
| TAP-22 | The desktop and CLI export the source and the official workflow to harden it and run downstream checks. | Run the workflow on the exact candidate, review the physical result, and submit through Tiny Tapeout. |

Next on this path are hardening and final stream verification (TAP-07–12),
then installed-app replay and external acceptance (TAP-21, TAP-23–24).

- **TAP-01.** Select a named foundry or shuttle profile for the exact process and submission type.
- **TAP-02.** Verify the current accepted PDK, metal stack, libraries, tools, decks, and runset options.
- **TAP-03.** Check template or wrapper identity, design class, die boundary, origin, and dimensions.
- **TAP-04.** Check clock, reset, pin positions, directions, names, allowed layers, and power conventions.
- **TAP-05.** Check pad frame, seal-ring, scribe and keepout requirements where the submission owns them.
- **TAP-06.** Check package, bump, I/O, external wiring, and process-specific interface requirements.
- **TAP-07.** Assemble complete top-level hierarchy and detect missing, duplicate, or renamed referenced cells.
- **TAP-08.** Generate final GDSII or OASIS with accepted stream format, units, coordinates, and layer maps.
- **TAP-09.** Round-trip final stream through an independent reader and verify ports, hierarchy, and geometry.
- **TAP-10.** Run accepted downstream preflight on the exact stream with its recorded source and deck bindings.
- **TAP-11.** Attach DRC, LVS, extraction, antenna, density, ERC, and required process reliability results.
- **TAP-12.** Attach final functional checks, equivalence, signoff timing, power, and extracted analog results.
- **TAP-13.** Include waived items and their approval, scope, rule identity, and exact design reference.
- **TAP-14.** Verify configuration, constraints, netlists, parasitics, and required corporate or shuttle metadata.
- **TAP-15.** Include a manifest of sources, tools, decks, engines, settings, and cryptographic checksums.
- **TAP-16.** Define handoff dependencies, permitted content, delivered files, and missing/excluded artifacts.
- **TAP-17.** Produce a reproducible package with an inspectable report and separately retained raw evidence.
- **TAP-18.** Compare package revisions and identify which checks require rerun after a change.
- **TAP-19.** Detect stale, incomplete, mismatched, corrupted, or partially written handoffs.
- **TAP-20.** Review package integrity on clean hosts using documented verification commands.
- **TAP-21.** Run installed Windows and Ubuntu source-to-handoff paths at the qualified revisions.
- **TAP-22.** Run export, upload, or accepted downstream handoff through the documented submission interface.
- **TAP-23.** Track submission receipt, external rejection and diagnostics, resubmission, and final disposition.
- **TAP-24.** Record acceptance by exact process, collateral revision, submission identity, and design hash.
- **TAP-25.** Retain the final design and package for late ECOs, review, and repeat submissions.
- **TAP-26.** Link silicon test results and lessons back to the tapeout design and simulation expectations.

## Exchange and interoperability

References. [Si2 LEF/DEF](https://si2.org/lef-def-downloads/) · [Accellera standards](https://accellera.org/downloads/standards) · [IBIS Open Forum specifications](https://ibis.org/specs/) · [Xschem netlisting](https://xschem.sourceforge.io/stefan/xschem_man/netlisting.html) · [Studio exchange guide](docs/INTEROPERABILITY.md)

- **INT-01.** Import and export GDSII and OASIS with explicit layer, unit, hierarchy, label, and property mapping.
- **INT-02.** Import, inspect, modify, and export compatible Magic and KLayout layout representations.
- **INT-03.** Round-trip Xschem schematic hierarchy, symbols, libraries, includes, and supported simulation setup.
- **INT-04.** Exchange documented SPICE, CDL, extracted netlists, and supported simulator dialects.
- **INT-05.** Exchange Verilog, SystemVerilog, VHDL, structural netlists, and supported behavioral models.
- **INT-06.** Exchange Liberty models with corner, units, timing/power metadata, and validation.
- **INT-07.** Exchange LEF/DEF technology, floorplan, placement, pins, routes, and obstructions.
- **INT-08.** Exchange OpenDB or equivalent implementation checkpoints through versioned adapters.
- **INT-09.** Import and export SDC, selected UPF/CPF constructs, and operating mode metadata.
- **INT-10.** Exchange SPEF, DSPF, SPF, extracted netlists, and canonical node mappings.
- **INT-11.** Exchange SDF timing, SAIF activity, VCD/FST traces, and simulator-specific outputs where documented.
- **INT-12.** Exchange IP-XACT, SystemRDL, register definitions, and machine-readable interface views.
- **INT-13.** Exchange Touchstone, IBIS/IBIS-AMI, and model metadata for signal integrity flows.
- **INT-14.** Import and export KLayout report databases and supported third-party marker formats.
- **INT-15.** Exchange package, board and mechanical views through documented formats and adapters.
- **INT-16.** Support OpenAccess exchange or bridges with authorized SDKs and compatible libraries.
- **INT-17.** Support licensed tool adapters or documented bridges for Cadence, Synopsys, and Siemens workflows.
- **INT-18.** Preserve cross-view names, orientation, pin order, process IDs, and electrical dimensions.
- **INT-19.** Preview migrations, report known loss or unsupported constructs, and retain original source.
- **INT-20.** Compare imported and exported artifacts using independent parsers and test fixtures.
- **INT-21.** Support safe reversible reconciliation after edits in different tools.
- **INT-22.** Support resolved library roots and manifest-driven relative dependency paths.
- **INT-23.** Prevent unsafe type coercion, malformed scope, silent geometry changes, and inherited model confusion.
- **INT-24.** Keep fingerprinted compatibility profiles by format revision, external tool build, and process variant.
- **INT-25.** Provide a portable evidence sidecar for annotations or semantics unavailable in the destination format.
- **INT-26.** Export documentation and images using PDF, SVG, PNG, CSV, and readable reports.

## Collaboration and version control

References. [GitHub pull requests](https://docs.github.com/en/rest/pulls/pulls) · [GitHub reviews](https://docs.github.com/en/rest/pulls/reviews) · [Studio live collaboration](docs/LIVE_COLLABORATION.md) · [Studio version history and GitHub workflow](docs/USER_GUIDE.md#github-pull-requests-in-studio)

- **COL-01.** Create named versions with notes and browse durable project history.
- **COL-02.** Compare working or archived versions by schematic, net, parameter, layout, and simulation impact.
- **COL-03.** Restore an earlier version while preserving the current design and its recovery path.
- **COL-04.** Create, switch, rename, and track local branches with explicit treatment of pending edits.
- **COL-05.** Fetch and publish remote branches using established credentials and normal Git safety checks.
- **COL-06.** Review three-way schematic, layout, and settings differences before merging.
- **COL-07.** Resolve conflicts per object, field, or region and validate the resulting design.
- **COL-08.** Reject stale merge reviews or unexpected remote tips and preserve work on failed updates.
- **COL-09.** Create draft or ready GitHub pull requests in the app as supported by repository policy.
- **COL-10.** Browse open, closed, and merged pull requests with reviews, diffs, and checks.
- **COL-11.** Add general and line-specific reviews, threaded comments, and resolved discussions.
- **COL-12.** Approve or request changes and bind reviews and merges to the exact reviewed revisions.
- **COL-13.** Merge or queue a pull request through the allowed methods and retain the outcome.
- **COL-14.** Handle protected branches, stale heads, repository access, and signing requirements.
- **COL-15.** Attach design evidence and semantic changes for schematic/layout review.
- **COL-16.** Share checkpoints, annotations, and discussions attached to exact objects and evidence.
- **COL-17.** Show active editors, attribution, scope ownership, and offline or reconnect status.
- **COL-18.** Claim cells, layers, or regions and reconcile overlapping work with reviewed conflicts.
- **COL-19.** Support live edits, permissions, host operations, and resilient client recovery.
- **COL-20.** Audit changes, reviews, approvals, release evidence, and external submission identity.
- **COL-21.** Set per-project permissions for viewer, editor, reviewer, and administrator where hosted.
- **COL-22.** Preserve large design artifacts and their checksums while allowing offline edit and later sync.

## Automation and infrastructure

References. [Synopsys flow automation](https://www.synopsys.com/implementation-and-signoff/lynxnxt-automation-system/flow.html) · [LibreLane custom flows](https://librelane.readthedocs.io/en/latest/usage/writing_custom_flows.html) · [Studio fast feedback](docs/CI_FEEDBACK.md)

- **AUT-01.** Provide headless commands for capture validation, simulation, checks, implementation, and export.
- **AUT-02.** Provide documented Python and Tcl interfaces for supported data, queries, and edits.
- **AUT-03.** Support plugins with versioned capabilities, declared inputs, and controlled effects.
- **AUT-04.** Parameterize flows using manifests, templates, defaults, and explicit overrides.
- **AUT-05.** Compose jobs with dependencies, optional steps, checkpoints, and inspectable execution plans.
- **AUT-06.** Run jobs locally, on managed Linux or WSL, on farm schedulers, or in approved compute environments.
- **AUT-07.** Allocate CPUs, RAM, GPUs, process count, disk, and time budgets.
- **AUT-08.** Run independent cases concurrently while respecting shared resources and licenses.
- **AUT-09.** Run and compare pinned toolchains through containers or other reproducible environments.
- **AUT-10.** Cache and verify outputs by source, dependency, tool, deck, settings, and platform identity.
- **AUT-11.** Expose progress, queue state, cancellation, retries, worker health, and actionable errors.
- **AUT-12.** Resume interrupted runs from validated checkpoints and prevent duplicate publication.
- **AUT-13.** Surface tool availability, licensed feature availability, and local tool configuration.
- **AUT-14.** Support commercial license servers, queue reservations, and graceful handling of shortages where integrated.
- **AUT-15.** Offer structured logs, exit codes, reports, and evidence bundles for CI.
- **AUT-16.** Run focused developer checks and full release acceptance with immutable candidate provenance.
- **AUT-17.** Reuse authenticated and verified build inputs across development, CI, and packaging.
- **AUT-18.** Verify installers, updates, dependencies, executable signatures, and rollback paths.
- **AUT-19.** Keep audit records and reproducible environment descriptions across policy and tool changes.
- **AUT-20.** Keep telemetry configurable and minimize collection of private design or credential data.
- **AUT-21.** Support organizational access, protected asset storage, and approved data locality when hosted.
- **AUT-22.** Manage artifact retention, storage limits, remote coordination, and reliable locking.
- **AUT-23.** Detect malformed or untrusted inputs and keep profiles, logs, and secrets out of released artifacts.
- **AUT-24.** Measure time to first useful failure, testable installer, first waveform, verified layout, and exact handoff.
- **AUT-25.** Benchmark clean and incremental runs with cache state, hardware, queue delay, and comparable outputs.
- **AUT-26.** Capture successful real-engine commands and replay fixtures so failures can be reproduced independently.

## Desktop experience and accessibility

References. [Apple design principles](https://developer.apple.com/design/human-interface-guidelines/design-principles/) · [Apple accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility) · [Apple undo and redo](https://developer.apple.com/design/human-interface-guidelines/undo-and-redo) · [Studio desktop responsiveness](docs/DESKTOP_RESPONSIVENESS.md)

- **UX-01.** Use recognizable documents, tabs, menus, inspectors, property controls, and toolbars.
- **UX-02.** Make common operations available through menu, keyboard, pointer, and command search.
- **UX-03.** Keep layout and schematic tool modes visible and provide predictable cancellation and feedback.
- **UX-04.** Show visible focus, accessible names, logical tab order, and keyboard-only operation.
- **UX-05.** Support screen-reader access to project tree, selected objects, forms, results, and status.
- **UX-06.** Support text scaling and high-DPI displays with no clipped important controls or labels.
- **UX-07.** Support light, dark, and system appearance with readable contrast.
- **UX-08.** Convey state through text, ordering, icons, or line shapes in addition to color.
- **UX-09.** Use scoped dialogs and explicit confirmation for consequential publication, replacement, or merge.
- **UX-10.** Provide transaction-based undo/redo, current action context, and safe previews before applying.
- **UX-11.** Support modern pointer and trackpad gestures, editable shortcuts, and customary platform shortcuts.
- **UX-12.** Support multiple monitors, saved layouts, floating panels, compact workspaces, and restore defaults.
- **UX-13.** Keep long solver, import, and network work responsive with progress and accessible errors.
- **UX-14.** Jump from an actionable error to the offending field, object, path, or report.
- **UX-15.** Preserve edited input and selection when operations time out, fail, or conflict.
- **UX-16.** Preserve text, localization, Unicode paths, different decimal settings, and right-to-left layout as applicable.
- **UX-17.** Support offline use for local editing, bundled help, examples, and applicable engines.
- **UX-18.** Provide signed or reviewable installs and portable packages on qualified desktop platforms.
- **UX-19.** Measure interaction responsiveness on large native designs and actual consumer screens.
- **UX-20.** Test focus, scaling, input, and accessibility on every advertised desktop target.
- **UX-21.** Make project, engine, PDK, rule, branch, and handoff status visible where decisions are made.

## Learning and support

References. [Studio Student Hub](docs/STUDENT_HUB.md) · [Studio example library](docs/FEATURE_TOUR.md#example-library) · [Tiny Tapeout HDL resources](https://tinytapeout.com/hdl/)

- **EDU-01.** Provide guided paths from a first waveform through layout, verification, and tapeout preparation.
- **EDU-02.** Provide editable templates, worked examples, and repeatable reference circuits.
- **EDU-03.** Explain concept and task distinctions across generic, public PDK, and qualified process work.
- **EDU-04.** Search all learning paths and expose available prerequisites, progress, and next steps.
- **EDU-05.** Provide checkpoints that evaluate saved projects, actual measured results, and user actions.
- **EDU-06.** Provide meaningful lab faults that teach debugging of opens, shorts, wrong bias, and timing failures.
- **EDU-07.** Allow repeated attempts and preserve progress, notes, and reflection across sessions.
- **EDU-08.** Support recovery, moved project relinking, and export of portfolio evidence.
- **EDU-09.** Support instructor-selected assignments, offline course packs, and reproducible graded checks.
- **EDU-10.** Teach analog, digital, mixed-signal, physical verification, reliability, and real submission workflows.
- **EDU-11.** Explain model, solver, and process limitations in context with links to current references.
- **EDU-12.** Provide command help, shortcuts, searchable documentation, and versioned release notes.
- **EDU-13.** Provide onboarding diagnostics and a practical troubleshooting path for PDKs and engines.
- **EDU-14.** Provide accessible keyboard, text-scaling, light/dark, and assistive use of tutorials and plots.
- **EDU-15.** Provide exportable certification or completion evidence tied to the specific course path and checks.
- **EDU-16.** Let users switch between learning and professional project views without losing document context.

## Electromagnetics and multiphysics

References. [openEMS introduction](https://docs.openems.de/en/latest/intro.html) · [Keysight RF Suite](https://www.keysight.com/us/en/products/design-engineering-software/electronic-design-automation/rf-suite.html) · [Ansys HFSS and SIwave](https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v251/en/Subsystems/HFSS3DLayout/Content/3DLayout/SIwaveSolutionsinHFSS3DLayout.htm) · [Studio field-solver workflow](docs/OPENEMS.md)

- **EM-01.** Construct 2D, 2.5D, and 3D structures from exact process or package stackup and geometry.
- **EM-02.** Define dielectric, conductor, substrate, permeability, conductivity, and anisotropic material data.
- **EM-03.** Model conductor thickness, roughness, skin effect, and frequency-dependent losses.
- **EM-04.** Set finite-element, integral-equation, or finite-difference solver options as supported.
- **EM-05.** Define lumped, waveguide, differential, and localized ports with reference planes.
- **EM-06.** Assign excitations, sources, boundary conditions, open boundaries, and symmetry.
- **EM-07.** Generate and inspect meshes, adaptive refinement, and convergence criteria.
- **EM-08.** Run frequency sweeps, broadband extraction, and time-domain excitation.
- **EM-09.** Visualize field vectors, power, surface current, magnetic flux, and spatial slices.
- **EM-10.** Compute inductance, mutual coupling, Q, resonance, loss, and substrate coupling.
- **EM-11.** Calculate line impedance, propagation, crosstalk, reflections, and via discontinuities.
- **EM-12.** Analyze radiation, antenna gain, directivity, pattern, and near/far fields when needed.
- **EM-13.** Export S-parameters or passive fitted models with defined units and reference planes.
- **EM-14.** Compare 2D, 2.5D, and full-wave results against measurements or analytical references.
- **EM-15.** Couple field-solver responses to circuit and system simulations.
- **EM-16.** Calculate steady-state and transient temperatures, heat flow, and thermal impedance.
- **EM-17.** Compare thermal and electrical iterations under coupled power and material changes.
- **EM-18.** Integrate mechanical stress, thermal expansion, and warpage where package requirements need them.
- **EM-19.** Quantify sensitivity to mesh, model domain, boundary conditions, ports, and material uncertainty.
- **EM-20.** Tie EM and thermal artifacts to exact geometry, stackup, solver, conditions, and applied scope.

## Packages, chiplets and boards

References. [Cadence Virtuoso System Design Platform](https://www.cadence.com/content/dam/cadence-www/global/en_US/documents/tools/ic-package-design-analysis/virtuoso-system-design-platform-ds.pdf) · [Synopsys 3DIC portfolio](https://www.synopsys.com/implementation-and-signoff.html) · [UCIe specifications](https://www.uciexpress.org/specifications) · [KiCad PCB Editor](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html) · [Altium ECAD–MCAD integration](https://www.altium.com/documentation/altium-codesigner/direct-ecad-mcad-design)

- **PKG-01.** Create a system model linking dies, packages, boards, connectors, and power sources.
- **PKG-02.** Track die orientation, stack order, bump maps, and pin-to-terminal assignments.
- **PKG-03.** Plan wire bonds, flip-chip bumps, microbumps, TSVs, hybrid bonds, and RDL where needed.
- **PKG-04.** Route interposers, substrates, package redistribution, and die-to-die links with constraints.
- **PKG-05.** Check bump pitch, wire-bond clearances, substrate layers, fabrication limits, and stack alignment.
- **PKG-06.** Extract package and interposer power, signal, and return-path parasitics.
- **PKG-07.** Assemble multiple die netlists and perform system LVS or equivalent connectivity checks.
- **PKG-08.** Validate die-to-die protocols, link budgets, channel models, and power interfaces.
- **PKG-09.** Support UCIe or other selected interface profiles with explicit package and PDK conditions.
- **PKG-10.** Simulate SI/PI across die, substrate, socket, board, and external connectors.
- **PKG-11.** Analyze eye opening, timing skew, jitter, crosstalk, return loss, and PDN impedance.
- **PKG-12.** Model package thermal behavior, warpage, mechanical limits, and assembly tolerances.
- **PKG-13.** Maintain package outline, placement, pins, footprint, assembly, and exchange metadata.
- **PKG-14.** Export verified chip symbols and package footprints for PCB layout.
- **PKG-15.** Support PCB stackups, net classes, controlled impedance, pours, and return path rules.
- **PKG-16.** Integrate PCB routing, differential pairs, length matching, and board-specific DRC.
- **PKG-17.** Create a board or test-fixture netlist and validate it against the packaged IC.
- **PKG-18.** Exchange board geometry and connector placement with mechanical CAD.
- **PKG-19.** Generate or integrate a BOM, assembly drawing, and component placement output.
- **PKG-20.** Export fabrication data through Gerber, drill, IPC-2581, ODB++ or approved equivalents where supported.
- **PKG-21.** Check package and board physical constraints with 3D inspection and assembly review.
- **PKG-22.** Support panelization or downstream manufacturing handoff through a verified adapter.
- **PKG-23.** Maintain per-die, package, and board revision identities and cross-domain change review.
- **PKG-24.** Coordinate package, silicon, and board requirements with affected pinout and verification results.

## Photonics and special processes

References. [GDSFactory PDK components](https://gdsfactory.github.io/gdsfactory/notebooks/08_pdk/) · [GDSFactory routing](https://gdsfactory.github.io/gdsfactory/api_routing/) · [Meep](https://meep.readthedocs.io/en/stable/) · [Cadence custom and photonics portfolio](https://www.cadence.com/en_US/home/tools/tools-a-z.html)

- **PHO-01.** Model optical ports by wavelength, polarization, mode, direction, and cross section.
- **PHO-02.** Bind photonic PDK components to electrical and optical schematic, layout, and simulation models.
- **PHO-03.** Generate waveguides, tapers, bends, splitters, combiners, crossings, and converters.
- **PHO-04.** Route optical waveguides with bend radius, optical length, layer, and loss constraints.
- **PHO-05.** Generate grating couplers, edge couplers, fiber arrays, and associated optical test ports.
- **PHO-06.** Integrate modulators, detectors, lasers, rings, filters, interferometers, and phase shifters.
- **PHO-07.** Simulate propagation, dispersion, phase, coupling, loss, reflection, and optical transfer functions.
- **PHO-08.** Support eigenmode analysis, frequency-domain and time-domain electromagnetic simulation.
- **PHO-09.** Fit compact or scattering models to field simulation or measured data.
- **PHO-10.** Simulate optical and electrical networks with shared stimuli and explicit boundary conditions.
- **PHO-11.** Cover thermal tuning, heaters, stress, and electrical control of optical characteristics.
- **PHO-12.** Evaluate optical process corners, layout sensitivities, losses, and fabrication tolerances.
- **PHO-13.** Check optical connectivity and compare intended topology with extracted waveguide networks.
- **PHO-14.** Check photonic spacing, bend radius, transition, keepout, density, and process rules.
- **PHO-15.** Export photonic stream data, optical models, port maps, and package interfaces.
- **PHO-16.** Integrate verified adjoint or inverse-design workflows with geometric and fabrication constraints.
- **PHO-17.** Support specialized high-voltage and wide-bandgap device profiles with validated model/deck adapters.
- **PHO-18.** Integrate MEMS mechanical/electrical transducers with explicit units and multi-domain model bindings.
- **PHO-19.** Integrate superconducting, quantum RF, or cryogenic layout and simulation profiles where qualified.
- **PHO-20.** Verify special-process and optical flows with independently reviewed fixtures and calibration data.

## FPGA, prototyping and emulation

References. [OpenFPGA supported tools](https://openfpga.readthedocs.io/en/stable/) · [Verilator simulation](https://verilator.org/guide/latest/simulating.html) · [Synopsys verification portfolio](https://www.synopsys.com/verification.html) · [Cadence prototyping and emulation catalog](https://www.cadence.com/en_US/home/tools/tools-a-z.html)

- **FPG-01.** Select FPGA family, board, hardware platform, constraints, and supported backends.
- **FPG-02.** Support open FPGA synthesis, placement, routing, and bitstream flows through adapters.
- **FPG-03.** Support licensed FPGA toolchains through documented integrations where available.
- **FPG-04.** Track board clocks, pins, reset, voltage banks, and device resource constraints.
- **FPG-05.** Map resources to LUTs, flip-flops, DSP, BRAM, PLL, and supported hard IP.
- **FPG-06.** Report resource utilization, timing, congestion, build identity, and bitstream compatibility.
- **FPG-07.** Use hardware constraints and model substitutions to prototype an ASIC design.
- **FPG-08.** Generate or bind board interfaces, clock models, memories, and external peripheral stubs.
- **FPG-09.** Program supported development boards and verify the expected image.
- **FPG-10.** Provide on-chip logic analyzer probes, triggers, trace buffers, and timestamp correlation.
- **FPG-11.** Support host software and virtual devices for before-silicon integration.
- **FPG-12.** Integrate execution and deterministic data exchange between host simulation and hardware.
- **FPG-13.** Partition a design across one or more prototyping or emulation devices.
- **FPG-14.** Handle clock conversion, communication boundaries, and timing/performance differences.
- **FPG-15.** Run scenarios against emulated systems and capture repeatable debug evidence.
- **FPG-16.** Compare FPGA, emulator, RTL, and silicon results with known fidelity limits.
- **FPG-17.** Support firmware load, UART, trace, interactive control, and regression through supported harnesses.
- **FPG-18.** Preserve board and tool configuration, constraints, bitstream, firmware identity, and test results.
- **FPG-19.** Support architecture exploration for FPGA fabrics or embedded fabric integration where needed.
- **FPG-20.** Qualify prototype workflows independently from ASIC timing and silicon signoff.

## Fabrication and TCAD

References. [Silvaco Victory Process](https://silvaco.com/products/manufacturing/tcad/victory-process/) · [Silvaco Victory Device](https://silvaco.com/products/manufacturing/tcad/victory-device/) · [Cadence manufacturing signoff overview](https://www.cadence.com/en_US/home/solutions/advanced-node-solutions/digital-advanced-node.html)

- **FAB-01.** Model process stack and geometry in a versioned technology simulation definition.
- **FAB-02.** Describe deposition, etch, lithography, implant, diffusion, and anneal through a supported TCAD adapter.
- **FAB-03.** Set boundary conditions, material models, doping profiles, and mesh refinement.
- **FAB-04.** Simulate 2D/3D device behavior with process-dependent geometry and doping.
- **FAB-05.** Model electrostatic, transport, breakdown, self-heating, and optical effects where applicable.
- **FAB-06.** Export I–V, C–V, charge, field, and geometry measurements from device simulations.
- **FAB-07.** Fit compact models to measured or TCAD device data with independent validation curves.
- **FAB-08.** Track fitted model bounds, uncertainties, calibration data, and source correspondence.
- **FAB-09.** Compare alternative process assumptions and models through design-technology co-optimization.
- **FAB-10.** Analyze lithography patterns, process windows, coloring, and printability through accepted decks.
- **FAB-11.** Exchange mask data or coordinate with authorized mask preparation and OPC workflows.
- **FAB-12.** Check reticle alignment, die placement, scribe information, and mask layer assignments when required.
- **FAB-13.** Analyze CMP and density-related process effects with appropriate process models.
- **FAB-14.** Maintain process monitor, dummy, metrology, and calibration structures with their required interfaces.
- **FAB-15.** Identify manufacturing hotspots and correlate them with design and model variants.
- **FAB-16.** Report pre-correction and post-correction geometry and account for approved output differences.
- **FAB-17.** Simulate fabrication variation and explore visual and electrical sensitivity to process windows.
- **FAB-18.** Track reticle, wafer process variant, foundry feedback, and manufacturing artifact identity.
- **FAB-19.** Keep protected process data and licensed outputs in authorized tool and storage environments.
- **FAB-20.** Reproduce a process or model study with the applicable technology release and calibration evidence.

## Laboratory and silicon lifecycle

References. [Cadence Modus test and diagnosis](https://www.cadence.com/en_US/home/tools/digital-design-and-signoff/test-automation/modus-test.html) · [Synopsys chip design and lifecycle portfolio](https://www.synopsys.com/implementation-and-signoff.html) · [NI wafer probe testing](https://www.ni.com/en/solutions/semiconductor/case-studies/pxi-based-automated-wafer-probe-tester.html) · [Tiny Tapeout chip and board guidance](https://tinytapeout.com/specs/)

- **LAB-01.** Define a bring-up plan with pad, power, reset, clock, debug, and measurement expectations.
- **LAB-02.** Bind packaging, board revision, pin map, tester configuration, and silicon specimen.
- **LAB-03.** Communicate with supported instruments through documented interfaces.
- **LAB-04.** Control voltage/current sources, oscilloscopes, multimeters, signal sources, logic analyzers, and network analyzers.
- **LAB-05.** Define calibration, reference planes, measurement range, sample window, and triggering.
- **LAB-06.** Run characterization sweeps of process lot, supply, temperature, load, and conditions.
- **LAB-07.** Automate measurement setup, repeatable run plans, and time-series capture.
- **LAB-08.** Retain instrument settings, firmware, environmental data, and uncertainty.
- **LAB-09.** Read production data such as supported STDF traces, binning, and wafer-level measurements.
- **LAB-10.** Plot wafer maps, yield by bin, trends, distributions, and correlations.
- **LAB-11.** Compare measured behavior with schematic, extracted, and statistical simulation.
- **LAB-12.** Attribute discrepancies to package, fixtures, process, model, silicon, or measurement conditions.
- **LAB-13.** Record known-good settings, characterization bounds, and regression margins.
- **LAB-14.** Debug failing chips using scan results, embedded traces, probe points, and mapped design identity.
- **LAB-15.** Cross-probe manufacturing or tester failure candidates into cells, nets, and final geometry.
- **LAB-16.** Support characterization, wafer sort, package test, and final test handoffs through adapters.
- **LAB-17.** Track test-program versions, passing limits, pattern sets, and compatibility with die and package revisions.
- **LAB-18.** Track reliability qualification and accelerated test results by exact conditions and design.
- **LAB-19.** Support process variation monitors, ring oscillators, temperature or voltage sensors, and telemetry.
- **LAB-20.** Compare yield, reliability, and fault trends after design or process revisions.
- **LAB-21.** Capture failure analysis, corrective ECOs, and post-fix measurement evidence.
- **LAB-22.** Preserve laboratory notebooks, raw measurements, expected results, and review disposition.
- **LAB-23.** Export reproducible characterization reports and archive datasets with reuse permissions.

## Specialized generators and systems

References. [Cadence reusable design IP and HLS catalog](https://www.cadence.com/en_US/home/tools/tools-a-z.html) · [GDSFactory component and routing API](https://gdsfactory.github.io/gdsfactory/api/) · [OpenRAM](https://github.com/VLSIDA/OpenRAM) · [Studio example selection](docs/INDEX.md#find-a-complete-example)

- **GEN-01.** Generate or configure reusable CMOS logic blocks with schematic, layout, symbol, and validation views.
- **GEN-02.** Generate standard-cell candidates with defined rails, tracks, pin access, and characterization inputs.
- **GEN-03.** Generate bias networks, references, current mirrors, differential pairs, and amplifier stages.
- **GEN-04.** Generate configurable passive filters, RC banks, mixed-signal trim arrays, and DAC ladders.
- **GEN-05.** Generate analog test structures, Kelvin contacts, extractable combs, arrays, and matched passive replicas.
- **GEN-06.** Generate power-management reference topologies for LDOs, regulators, and monitored rails.
- **GEN-07.** Generate clock and timing blocks such as ring oscillators, delay lines, dividers, and PLL subblocks.
- **GEN-08.** Generate interface macros, comparators, level shifters, and configurable I/O wrappers.
- **GEN-09.** Generate pad frames, bump maps, tap patterns, guard structures, and package-aware interfaces.
- **GEN-10.** Support parameterized digital FIFOs, synchronizers, counters, timers, and interrupt controllers.
- **GEN-11.** Integrate reference CPU, accelerator, DSP, and interconnect IP with known licensing and validation.
- **GEN-12.** Generate configurable SoC fabrics, address decoders, register maps, and compatible firmware headers.
- **GEN-13.** Integrate reusable interface controllers and PHY abstractions with requirements and verification assets.
- **GEN-14.** Compose multiple IP blocks and check handshake, clock, reset, address, and power interactions.
- **GEN-15.** Compile reusable design generators with deterministic parameters, versions, and integration constraints.
- **GEN-16.** Produce consistent schematic, RTL, symbol, layout, verification, and export views from generation where applicable.
- **GEN-17.** Update a generated block and preview changes to interfaces, geometry, connections, and dependent tests.
- **GEN-18.** Validate realistic layouts and simulated electrical behavior for declared generated configurations.

## Engineering intelligence and decision support

References. [Cadence custom and digital product catalog](https://www.cadence.com/en_US/home/tools/tools-a-z.html) · [Synopsys design automation portfolio](https://www.synopsys.com/implementation-and-signoff.html) · [Studio analog optimizer](docs/ANALOG_OPTIMIZER.md)

- **AID-01.** Summarize tool reports with inspectable links to raw results, original inputs, and failing checks.
- **AID-02.** Group repeated or related violations by likely shared design cause and show the affected scope.
- **AID-03.** Suggest a small set of locally reviewable changes for failed physical, timing, or circuit requirements.
- **AID-04.** Cross-probe each suggestion to the exact rule, net, path, waveform, or touched geometry.
- **AID-05.** Predict design tradeoffs with uncertainty and compare predictions to actual engine runs.
- **AID-06.** Explore possible synthesis and implementation settings against explicit PPA and acceptance targets.
- **AID-07.** Rank experiments by expected information, cost, and measurable improvement.
- **AID-08.** Detect regressions or anomalous reports across stable benchmarks and historical revisions.
- **AID-09.** Generate verification stimulus or candidate assertions with requirement traceability and review.
- **AID-10.** Suggest reference designs, device candidates, and workflow instructions from applicable documented inputs.
- **AID-11.** Review generated edits transactionally with an exact diff, undo, and retained source or prompt provenance.
- **AID-12.** Run normal simulation, verification, or signoff checks to substantiate an automated suggestion.
- **AID-13.** Support local or approved hosted assistance with explicit project data boundaries.
- **AID-14.** Reproduce search and optimization results with model, tool, seed, search budget, and revision identity.
- **AID-15.** Benchmark assistance on actual projects for completion time, correctness, and false suggestions.

## Functional safety and design assurance

References. [Synopsys Functional Safety Manager](https://www.synopsys.com/verification/vc-functional-safety-manager.html) · [Synopsys fault simulation](https://www.synopsys.com/verification/simulation/vc-z01x.html) · [Siemens Questa formal](https://eda.sw.siemens.com/en-US/ic/questa/formal-verification/)

- **SAF-01.** Map safety and assurance requirements to architecture, implementation, verification, and reviewer evidence.
- **SAF-02.** Track scenario, operating mode, expected behavior, and, where relevant, safe-state requirements.
- **SAF-03.** Model functional and physical fault classes with justified abstractions and fault sites.
- **SAF-04.** Run single and multiple fault injection with retained triggers, scope, and reproducible results.
- **SAF-05.** Classify faults as detected, undetected, unobservable, safe, or unresolved under explicit assumptions.
- **SAF-06.** Trace diagnostic coverage and failure rates into FMEDA or accepted downstream reports.
- **SAF-07.** Analyze common-cause and dependent failures where required by the target methodology.
- **SAF-08.** Verify monitors, watchdogs, fail-safe behavior, voting, redundancy, and recovery mechanisms.
- **SAF-09.** Validate safe-state transition latency and fault detection across power, clock, and reset states.
- **SAF-10.** Manage requirements and proof obligations for secure boot, debug restrictions, and isolation boundaries.
- **SAF-11.** Verify configuration protection, access separation, and resilience of monitored interfaces.
- **SAF-12.** Check tool, model, and runset qualification evidence required by the specific program.
- **SAF-13.** Expose requirements and evidence invalidated by a design, model, or tool revision.
- **SAF-14.** Retain independent reviews, waived obligations, rationale, and remaining risk decisions.
- **SAF-15.** Export safety evidence, requirement traceability, and accepted audit artifacts for the named program.
- **SAF-16.** Link manufacturing and field findings to affected requirements and corrective verification.
