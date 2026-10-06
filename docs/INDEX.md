# Documentation

Use the guides below for the current **0.23.0 engineering preview** source. Desktop packages have their own source identities and acceptance records; check [release status](RELEASE_STATUS.md) before applying source-only instructions to a downloaded build. Older versioned notes at the end are historical snapshots.

**Quick links:** [First waveform](GETTING_STARTED.md) · [Examples](../examples/README.md) · [Feature tour](../README.md#explore-the-workspace) · [Source setup](../README.md#start-in-three-steps) · [Simulation engines](../SIMULATION_SETUP.md)

For development toward a complete analog/digital release, see the
[SKY130, GF180MCU and IHP acceptance targets](PUBLIC_RELEASE_TARGETS.md).

## Find a complete example

| Circuit | Start here | Main purpose |
|---|---|---|
| **Supplied GF180 5 V bandgap** | [Files and three program variants](../examples/gf180-bandgap/README.md) | Startup, original 144-analysis characterization and a separate six-case compatibility test; approximately 1.2 V reference |
| **Native GF180MCU Banba reference** | [Build](../examples/gf180-banba/README.md) → [optimize](../examples/gf180-banba/pass2/README.md) → [lay out](../examples/gf180-banba/layout/README.md) | Independent 3.3 V / approximately 0.6 V design with editable hierarchy and physical evidence |
| **SKY130 voltage monitor** | [Overvoltage-detector walkthrough](OPEN_PROJECTS.md) | Pinned external source, generated runnable bench, 16 trip codes and linked schematic/layout |
| **SKY130 two-stage amplifier** | [Native project](../examples/sky130_two_stage_opamp.icproj) · [guide](ANALOG_REFERENCE_WORKFLOW.md) | Operating point, gain/loop margin, noise, startup and schematic/extracted comparison |
| **Mixed-signal SAR ADC** | [Native project](../examples/sar-adc/README.md) · [walkthrough](MIXED_SIGNAL_SAR.md) | Analog sample/hold and DAC coupled to a Verilog controller |
| **Sensor acquisition capstone** | [Student projects](../examples/student-hub/README.md) · [course](STUDENT_HUB.md) | Filter, converter, averaging and alarm with measured repair milestones |
| **Counter, UART and APB FIFO** | [Digital flow](DIGITAL_FLOW.md) | Editable RTL, simulation/regression and implementation examples |

The [gallery catalog](../README.md#example-library) contains 13 guided entries. The external voltage monitor is generated from its separately downloaded, pinned source; it is not a bundled gallery entry. The supplied bandgap and native Banba reference are different circuits.

## Start here

- [Desktop downloads and package identity](DOWNLOADS.md)
- [Your first circuit and waveform](GETTING_STARTED.md)
- [Projects, libraries and saved work](PROJECT_HUB.md)
- [41 core lessons and the sensor-acquisition capstone](STUDENT_HUB.md)
- [Included and installed PDKs](PDK_GUIDE.md)
- [Linux launch and engine setup](LINUX_SETUP.md)
- [Circuit, layout, CLI and plugin workflows](USER_GUIDE.md)

## Analog design and simulation

- [Integrated analog workspace](ANALOG_WORKSPACE.md)
- [Optimization, gm/Id and device characterization](ANALOG_OPTIMIZER.md)
- [Extraction, constraints and durable verification campaigns](ANALOG_CLOSURE.md)
- [Two-stage amplifier, diagnostics and statistical plans](ANALOG_REFERENCE_WORKFLOW.md)
- [Process RC, device multiplicity and physical hierarchy](ANALOG_IMPLEMENTATION_EXTENSIONS.md)
- [Saved testbenches, PVT and engineering studies](PROFESSIONAL_WORKFLOWS.md)
- [Compare schematic and captured extracted implementations](REFERENCE_IMPLEMENTATIONS.md)

## Digital and mixed signal

- [RTL editing, debug, timing and physical inspection](DIGITAL_WORKSPACE.md)
- [Digital engines, constraints and RTL-to-GDS implementation](DIGITAL_FLOW.md)
- [Eight interactive offline RTL presets](VGA_PLAYGROUND.md)
- [Four-bit SAR ADC with clocked ngspice/Icarus coupling](MIXED_SIGNAL_SAR.md)
- [Native buses, ordered slices and instance arrays](NATIVE_VECTORS.md)

## Layout, inductors and exchange

- [Vias and Autovia previews](LAYOUT_VIAS.md)
- [3D geometry inspection and image export](LAYOUT_3D.md)
- [Large layouts, linked edits and concurrent work](LAYOUT_SCALE_AND_COLLABORATION.md)
- [Drawing, geometry operations and grids](DRAWING_0.22.md)
- [Snapping, gestures and navigation](GESTURES_0.22.md)
- [Layout commands and constraints](PRIORITIES_0.22.md)
- [Spiral inductors, target-L search and physical profiles](INDUCTOR_CREATOR.md)
- [Electromagnetic simulation and characterization](OPENEMS.md)
- [Xschem, Magic, SPICE, GDSII and OASIS exchange](INTEROPERABILITY.md)
- [Migration into editable native process devices](NATIVE_CATALOG_MIGRATION.md)

## Collaboration, editing and recovery

- [Live desktop editing, hosting and roles](LIVE_COLLABORATION.md)
- [Linked workflow review, checkpoints and discussions](WORKFLOW_REVIEW_0.22.md)
- [Recovery of submitted review actions](REVIEW_RECOVERY.md)
- [Schematic edits and conflict handling](SCHEMATIC_COLLABORATION.md)
- [Project persistence, recovery and editing](STABILITY_0.22.md)
- [Receipt-verified recovery and evidence-driven workflow states](RELIABLE_DESIGN_WORKFLOWS.md)
- [Component browsing, placement and floating panels](USABILITY_FEEDBACK.md)
- [Export the visible workspace](VIEW_SCREENSHOTS.md)

## Reference circuits and physical qualification

- [Supplied GF180 bandgap: six-case compatibility bench](BANDGAP_COMPATIBILITY.md)
- [SKY130 voltage monitor: import, simulation and both views](OPEN_PROJECTS.md)
- [Real-reference exchanges and physical compatibility](REFERENCE_COMPATIBILITY.md)
- [Managed physical tools and experimental extraction repairs](REFERENCE_COMPATIBILITY_REPAIRS.md)
- [Public-layout DRC/LVS compatibility](PUBLIC_DESIGN_COMPATIBILITY.md)
- [Generated archived Banba qualification summary](REFERENCE_QUALIFICATION.md)
- [Pinned SKY130 inverter reference](SKY130_REFERENCE.md)
- [Reproduce hierarchy, detector and physical gates](QUALIFICATION_0.22.md)

## Build, release and acceptance

- [Windows desktop build and acceptance](WINDOWS_RELEASE.md)
- [Prepare and verify a desktop release](RELEASING.md)
- [Recorded source/package status and open acceptance](RELEASE_STATUS.md)
- [IC Design Studio 0.23.0 — desktop engineering preview](UPDATE_0.23.0.md)
- [Remaining release follow-ups](RELEASE_FOLLOWUPS.md)
- [Historical dev25 candidate and manual acceptance handoff](DEV25_ACCEPTANCE_HANDOFF.md)
- [Native consumer-machine acceptance procedure](NATIVE_DESKTOP_ACCEPTANCE.md)
- [Statistical campaign and two-host worker acceptance](CAMPAIGN_WORKER_ACCEPTANCE.md)

## Architecture, performance and audits

- [Code organization and extension boundaries](ARCHITECTURE.md)
- [Editing responsiveness and retained benchmarks](DESKTOP_RESPONSIVENESS.md)
- [Interactive viewport and rendering measurements](INTERACTIVE_RENDERING_PERFORMANCE.md)
- [Analog workspace audit and retained observations](ANALOG_GUI_AUDIT.md)
- [Student Hub interface and build audit](STUDENT_HUB_AUDIT.md)
- [Remaining work and acceptance goals](ROADMAP.md)

## Historical release and implementation notes

These documents preserve the commands, feature boundaries and executed results of their named version or milestone. A historical statement that a feature is planned or a platform is untested does not describe the current source. Use the topic guides above for current instructions, and the recorded source/engine identities when reproducing an old result.

<details>
<summary><strong>Browse versioned snapshots and earlier acceptance records</strong></summary>

- [Layout capability matrix — 0.11.0](CAPABILITY_MATRIX_0.11.md)
- [0.12 capture capability ledger](CAPABILITY_MATRIX_0.12.md)
- [0.13 capability ledger](CAPABILITY_MATRIX_0.13.md)
- [Fresh-desktop and experienced-user acceptance](DESKTOP_ACCEPTANCE_0.13.md)
- [IC Design Studio 0.14 — a workspace for drawing](GUI_OVERHAUL.md)
- [IC Design Studio 0.21.0](RELEASE_0.21.md)
- [IC Design Studio 0.22.0.dev20 — engineering preview](RELEASE_0.22.md)
- [Historical verification — 0.8.0](TEST_REPORT.md)
- [IC Design Studio — desktop interface redesign](UI_REDESIGN.md)
- [IC Design Studio 0.10.0 — analog physical workflow](UPDATE_0.10.md)
- [IC Design Studio 0.11.0 — native layout editor](UPDATE_0.11.md)
- [IC Design Studio 0.12.0 — schematic and symbol capture](UPDATE_0.12.md)
- [IC Design Studio 0.13.0](UPDATE_0.13.md)
- [IC Design Studio 0.15.0 — simulation and direct editing](UPDATE_0.15.md)
- [IC Design Studio 0.16.0 — design goals and verification](UPDATE_0.16.md)
- [IC Design Studio 0.17.1 — Xschem dependency repair](UPDATE_0.17.1.md)
- [IC Design Studio 0.17.0 — Direct Xschem project exchange](UPDATE_0.17.md)
- [IC Design Studio 0.18.1 — simulation startup fixes](UPDATE_0.18.1.md)
- [IC Design Studio 0.18 — Xschem projects](UPDATE_0.18.md)
- [IC Design Studio 0.19.0 — Native project migration](UPDATE_0.19.md)
- [IC Design Studio 0.2.1](UPDATE_0.2.1.md)
- [IC Design Studio 0.2.2 — component symbol refinement](UPDATE_0.2.2.md)
- [IC Design Studio 0.20.0 — Connected native workflows](UPDATE_0.20.md)
- [IC Design Studio 0.21.1.dev1](UPDATE_0.21.1.md)
- [Layout development — 0.22.0.dev6](UPDATE_0.22.md)
- [Experimental dev21: component shortcuts, workflow and recovery](UPDATE_0.22_DEV21.md)
- [Experimental dev22: inductor creator](UPDATE_0.22_DEV22.md)
- [Experimental dev23: inductor design and characterization](UPDATE_0.22_DEV23.md)
- [IC Design Studio 0.22.0.dev24 — packaged VGA qualification](UPDATE_0.22_DEV24.md)
- [IC Design Studio 0.22.0.dev25 — analog reference and release qualification](UPDATE_0.22_DEV25.md)
- [IC Design Studio 0.3.0](UPDATE_0.3.0.md)
- [IC Design Studio 0.3.1 — manual wiring and keyboard editing](UPDATE_0.3.1.md)
- [IC Design Studio 0.4.0](UPDATE_0.4.0.md)
- [IC Design Studio 0.5.0 — Project and PDK workspaces](UPDATE_0.5.md)
- [IC Design Studio 0.6.0](UPDATE_0.6.md)
- [IC Design Studio 0.7.0](UPDATE_0.7.md)
- [IC Design Studio 0.8.0](UPDATE_0.8.md)
- [IC Design Studio 0.9.0 — analog characterization](UPDATE_0.9.md)
- [Working with IC Design Studio 0.3](WORKFLOWS_0.3.md)

</details>

## Evidence, sources and maintenance

- [September 30 documentation audit](validation/documentation-audit-2026-09-30.json) records the 118 reviewed documents, source basis, corrections, retained historical scope and validation limits.
- [Analog extension evidence](validation/analog_extensions/README.md) and [dev25 reference record](validation/analog-reference-qualification.json) retain exact source/tool scope.
- [README screenshot provenance](images/readme/README.md) distinguishes actual application captures from decorative artwork and identifies historical screenshots.
- [Contributing](../CONTRIBUTING.md) explains focused changes and validation; [third-party notices](../THIRD_PARTY_NOTICES.md) record redistribution sources and licenses.
- [Included simulation PDKs](../icstudio/assets/pdks/START-HERE.md) and [fixed SKY130 PNP geometry](../icstudio/assets/physical/sky130_fixed/README.md) describe the packaged asset subsets.

Run `python scripts/check_release.py` after documentation changes. It checks local document/image targets, the version badge, generated qualification summaries and the gallery projects. Also check heading links and rendered layout when changing navigation or screenshots. Keep current instructions in topic guides and retain historical results with their original evidence.
