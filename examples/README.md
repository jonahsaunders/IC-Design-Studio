# Example projects

## Choose a reference circuit

| Design | Where to start | What is included |
|---|---|---|
| **Supplied GF180 5 V bandgap** | [Bandgap guide](gf180-bandgap/README.md); gallery entries **07–08** | Short startup and original 144-analysis programs, plus a separate six-case compatibility schematic; approximately 1.2 V reference |
| **Native GF180MCU Banba bandgap** | [First schematic](gf180-banba/README.md), [improved schematic](gf180-banba/pass2/README.md), [routed layout](gf180-banba/layout/README.md); gallery **10–12** | Independent 3.3 V / approximately 0.6 V design with editable hierarchy, optimization and physical evidence |
| **SKY130 voltage monitor / overvoltage detector** | [Pinned external-project walkthrough](../docs/OPEN_PROJECTS.md) | Generated native schematic/layout project and runnable `overvoltage-bench.icproj`; four input bits select 16 nominal rising trip thresholds |
| **SKY130 two-stage op-amp** | [Native project](sky130_two_stage_opamp.icproj) and [reference workflow](../docs/ANALOG_REFERENCE_WORKFLOW.md) | Saved operating-point, loop-gain, noise and startup fixtures, PVT plans and bounded physical comparisons |
| **Mixed-signal SAR ADC** | [Native project](sar-adc/sar-adc.icproj); gallery **13** | Four-bit Verilog controller coupled to a native analog sample/hold and resistor DAC |

The [main README catalog](../README.md#example-library) lists all **13** guided gallery entries. The external voltage monitor and generated digital/reference workflows are additional examples; they are not extra gallery entries.

## Guided first circuits

For an external hierarchical SKY130 design, see the [overvoltage import and qualification walkthrough](../docs/OPEN_PROJECTS.md). Its source is pinned and downloaded explicitly. Archived strict full-circuit LVS passes with the recorded resistor extraction correction; see the walkthrough for the exact scope and remaining limits.

Use **File → Start here / example gallery** for guided examples that open as independent copies. The first six projects below use embedded native definitions or generic teaching models; none needs a downloaded PDK. Five have short, saved analyses. The sixth is a placement exercise. Later entries include real-PDK simulations and the Banba design sequence described below.

| Order | Project | Expected result / exercise | Engine |
|---|---|---|---|
| 1 | [RC low-pass](rc.icproj) | Smooth charging after an input edge; inspect X/Y markers | Built-in |
| 2 | [Native divider](native-divider.icproj) | **0.5 V** at `out` from a 1 V source and two 1 kΩ resistors | ngspice |
| 3 | [Inverter with layout](inverter_layout.icproj) | Output switches opposite to input; inspect teaching geometry | Built-in |
| 4 | [Native RC](native-rc.icproj) | Short transient baseline with mapped R/C geometry for parasitic comparison | ngspice |
| 5 | [Reusable divider](reusable-divider.icproj) | Enter a child circuit, inspect ports and run through the parent | Built-in |
| 6 | [Common-centroid resistors](common-centroid-resistors.icproj) | Review saved constraints and arrange four resistors | None |

## From waveform to a measurement

Open the RC example, run with **F5**, then select **Results → Waveforms**. Choose the output trace. Use **Markers…** to enter exact X/Y coordinates and select a threshold comparison. Move the marker, observe its readout and save your copy. See the [waveform workflow guide](../docs/UPDATE_0.15.md) for additional controls.

## Native parameter studies

Open the native divider and run its saved operating point. In **Analysis → Variation cases**, configure a native parameter study using `R1.native.value`. The baseline output is 0.5 V. Increasing the upper resistor to 3 kΩ makes the ideal output 0.25 V. The [native workflow guide](../docs/UPDATE_0.20.md) covers the review table, sensitivity, bounded search and applying a selected case.

## Explore layout

The inverter uses generic educational geometry and models. For the common-centroid example, choose **Layout → Placement and constraints** to inspect the saved group before arranging it. The native RC project adds explicit electrical-to-geometry mappings. Choose **Analysis → Post-layout → Distributed RC and specification comparison** to compare its baseline against declared interconnect estimates. These are teaching exercises; their dimensions and RC coefficients are not process-calibrated.

## Exchange and reusable components

- [Xschem amplifier](xschem-amplifier/amplifier.sch): small hierarchical import/exchange exercise with local symbols.
- [Amplifier testbench](amplifier-testbench.icproj): reusable circuit and fixture structure.
- [Interface update](amplifier-interface-update.icproj): compare an edited reusable component interface.
- [Manual wiring](manual-wiring.icproj): practice net labels, wire editing and connection inspection.
- [KLayout teaching rules](klayout/teaching-widths.drc): self-contained demonstration script for the external rule runner. Requires an installed KLayout executable and matching teaching layers.
- [Educational PDK package](pdk-educational/package.json): a small checksummed package for learning the installation flow.

Additional `.icproj` files are working development examples; the gallery provides the shortest introduction. Keep long PDK circuits out of routine smoke tests. Use a small representative circuit to test a new engine, model or adapter.

## Included real-PDK simulations

The gallery includes the supplied GF180 bandgap in two forms: a short 5 V / 25 °C startup check and the byte-for-byte original 144-analysis characterization. A SKY130 1.8 V inverter is also included. Open a copy and press F5; bundled symbols and models resolve automatically.

The [bandgap guide](gf180-bandgap/README.md) distinguishes the original gallery upload from the later upload used by the six-case compatibility reduction. Each has its own identity record. Use [simulation setup](../SIMULATION_SETUP.md) for engines and output locations, and the [compatibility walkthrough](../docs/BANDGAP_COMPATIBILITY.md) for the six-case import/export check.

## Native Banba design exercise

Follow the GF180MCU Banba reference through three gallery entries. Each opens an independent project copy using the bundled models and ngspice.

| Gallery entry | What to explore | Status |
|---|---|---|
| 10 · [Build a Banba bandgap](gf180-banba/README.md) | Native core, transistor-level amplifier, startup circuit, two testbenches and a 27-simulation resistor search | About 0.596 V at 27 °C; fast startup overshoots and retains a failing requirement |
| 11 · [Improve the Banba bandgap](gf180-banba/pass2/README.md) | Revised bias and startup, three optimizer searches with 420 simulations, before/after performance plots and independent PVT checks | About 0.601 V at 44.40 µA nominal; lower current and overshoot trade against settling, capacitor area and mid-band supply rejection |
| 12 · [Lay out the Banba bandgap](gf180-banba/layout/README.md) | Routed native layout and GDS, 1:8 common-centroid PNP array, matching constraints, segmented resistors and tiled MIM capacitors | Archived native connectivity, core LVS, separate filled-layout DRC/LVS and core capacitance-only checks pass within their recorded scope; distributed RC, fill coupling and fabrication signoff remain open. See [shared qualification](../docs/REFERENCE_QUALIFICATION.md) |

[![The routed Banba example in the native layout editor.](gf180-banba/layout/studio-layout.png)](gf180-banba/layout/README.md)

Select **banba_layout → Layout** in the third project. These examples use a 3.3 V supply and an unbuffered output with a 5 pF external testbench load; they do not establish fabrication readiness. See the linked guides for measured conditions, trade-offs and reproduction steps.

## Mixed-signal SAR ADC and guided learning

Gallery entry **13 · Build a mixed-signal SAR ADC** opens an independent [four-bit ADC project](sar-adc/sar-adc.icproj). Select local `ngspice`, `iverilog` and `vvp` executables, then choose **Run coupled simulation**. With the default 0.93 V input and 1.8 V reference, expect code **8** after four comparisons. Inspect the analog waveforms and digital decision table, then edit the DAC or RTL and rerun. No downloaded PDK is required; the comparator and sampling switch are behavioral. [Walkthrough and qualification limits](../docs/MIXED_SIGNAL_SAR.md).

Open **File → Student Hub** for four learning paths and a sensor-acquisition capstone: **28 lessons and 112 steps** using the native editors. The [course guide](../docs/STUDENT_HUB.md) describes prerequisites, practice mode, saved progress and local engine setup. The [student examples](student-hub/README.md) distinguish the correct sensor reference from the intentionally faulty lesson starter.
