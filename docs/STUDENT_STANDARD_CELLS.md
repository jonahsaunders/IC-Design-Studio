# Standard Cells

## Special-purpose cells

See the [Engineering design labs](STUDENT_ENGINEERING_LABS.md) for the fixtures, design targets, and measurement scope.

Open **Student Hub → Standard Cells** in IC Design Studio. In the cell labs,
start from a transistor schematic, place the devices, finish two Metal 3
connections, and compare the routed cell with the schematic. The row
integration lab starts with two routed cells ready to align.

## Design challenges

| Difficulty | Challenge | Targets |
| --- | --- | --- |
| Easy | Fit an inverter into a 12.8 µm cell | Width ≤ 12.8 µm and both logic levels correct with 10 fF |
| Medium | Drive 40 fF with a faster NAND | B rising to Y falling ≤ 100 ps with A held high, plus all four truth-table vectors |
| Hard | Meet the flip-flop clock-to-Q budget | Q rise ≤ 185 ps and Q fall ≤ 128 ps with 40 fF, combined Q driver width ≤ 5.8 µm, and capture and hold pass |

Open **Size and place** to choose your starting dimensions. Adjust the
inverter pitch, the width of each series NMOS in the NAND, or the separate
NMOS and PMOS widths of the flip-flop's Q driver. Route the gaps and run
the lesson. **Results → Targets** shows each measured value beside its limit.
Use **Revise design** to try another size. Rebuilding opens the two routing
gaps again, and **Undo** restores the earlier layout.

The inverter starter measures 13.8 µm wide. The loaded NAND starter
measures 138.5 ps. The loaded flip-flop starts at 203.0 ps rising and
153.7 ps falling. Each starter passes its logic samples, so the Targets tab
shows exactly which design limits still need work.

![The starter flip-flop passes its width budget and misses both timing targets](images/student-hub/sc-specs-baseline.jpg)

![The revised flip-flop passes both timing targets and the same width budget](images/student-hub/sc-specs-tuned.jpg)

## Row integration and characterization

| Difficulty | Lesson | Passing spec |
| --- | --- | --- |
| Easy | Make two cells fit side by side | Zero horizontal gap and rail offset. VPWR and VGND continuous across the seam. Zero Metal 2 and Metal 3 lesson-spacing violations. |
| Easy | Speed up a NOR’s rising edge | B falling to Y rising at most 75% of the starter delay at 20 fF. Cell width at most 25.4 µm. |
| Medium | Make a NAND easier to drive | Effective B input capacitance at most 80% of the starter. B rising to Y falling within 120 ps at 40 fF. |
| Medium | Keep a mux output steady during switching | Excursions at both equal-input levels stay within 0.18 V with a 1.8 V supply and an explicit 8 fF select-to-output coupling stress. |
| Medium | Build a buffer for four loads | Both input-to-output delays within 120 ps into four identical inverter inputs, with at most 8 µm total transistor width. |
| Hard | Build a lower-energy XOR | Average supply energy per output transition at most 85% of the starter. Each of the four timing arcs within 165 ps under the same load and stimulus. |
| Hard | Find a flip-flop’s setup and hold limits | Bracket both limits. Q stays above 80% of the supply and clock-to-Q stays within 110% of its settled reference at each stable passing offset. |

Open **Align cell row** at the abutment checkpoint to move the NAND in the
hierarchical layout. When the two outlines touch and both rails line up,
**Check this step** checks continuity and spacing across the seam. The two
cells share power and retain independent signals.

![Inverter and NAND abutted with both power rails aligned](images/student-hub/sc-abutment.jpg)

For the comparative labs, **Results → Targets** shows the starter measurement
alongside the current run. Studio measures each from a layout-loaded simulation
using the same fixture. The NAND measurement integrates current from the B
source during the switching event and divides by the input voltage swing.
The XOR measurement integrates power drawn from VDD across a four-transition
cycle and reports the average per transition.

For the flip-flop, open **Results → Timing sweep**. Positive setup offsets put
the rising D edge before the clock. Positive hold offsets put the falling D
edge after it. Move from the 1,500 ps reference toward zero until the capture
or delay criterion fails, then record the adjacent passing and failing offsets.
Select either row to see D, clock, and Q waveforms around the rising edge.
The reported setup and hold values are brackets at the supplied sweep spacing.

![Flip-flop setup and hold sweep with measured clock-to-Q and capture checks](images/student-hub/sc-timing-sweep.jpg)

## Layout lessons

| Cell | What to trace in layout | What to test |
| --- | --- | --- |
| INV | A reaches both gates and Y joins both drains | Both input levels |
| NAND2 | N_STACK joins the two series NMOS devices | All four vectors, including the 11 pull-down |
| NOR2 | P_STACK joins the two series PMOS devices | All four vectors, including the 00 pull-up |
| AOI21 | C reaches the direct pull-down and its complementary pull-up device | All eight vectors, including C overriding A and B |
| MUX2 | Separate S and S_B routing controls both transmission gates | All eight select and data combinations |
| DFF | CLK and CLK_B reach the latch switches. Q reaches the output pin and slave feedback. | Rising-edge capture and hold between edges |

## Place and route

1. Choose **Place cell rows**. Studio places the model-linked SKY130 devices,
   terminal contacts, via stacks, and an unfinished set of metal tracks. Look
   for the PMOS row above the NMOS row. The cells use a 24.5 µm
   teaching row, with the upper VPWR and lower VGND centers at Y = 1.5 µm and 23 µm.
   Both rails reach the side boundaries so adjacent cells can share the rail heights.
2. Inspect the footprint and physical pins. Signal ports reach the left edge
   on Metal 3. Follow the Metal 2 drops and vias to the terminals. Internal
   tracks such as N_STACK and CLK_B stop inside the boundary.
3. In **Complete and check the layout**, find the two gaps. Use **Add route**
   to enter a Metal 3 path's endpoints and width. In **Step by Step**, the
   route form shows the measurements for the selected track. Bridge VPWR
   at 0.9 µm width and the Y or Q signal at 0.64 µm.
4. Choose **Check this step** to confirm physical pin connectivity and the
   exercise widths and spacing. An open or short blocks the layout test.

![Inverter layout with the VPWR and Y tracks connected](images/student-hub/sc-inverter-layout.jpg)

![The native route form with endpoint and width fields for the VPWR gap](images/student-hub/sc-route-editor.jpg)

## Test the routed cell

Choose **Run lesson** for two native ngspice transients using the same 1.8 V
stimulus and fixture load. The basic layout lessons use a 10 fF load. The challenge fixture sets the
load for each measurement. The layout-loaded case adds a lumped
metal-to-ground capacitance estimate from the current connected polygons.
The **Results** window shows the added output capacitance, overlaid voltages,
and a **Samples** table with the expected logic and both measured voltages.
Rerun the pair after editing the layout so the checkpoint can use the current design.

![Overlaid inverter output waveforms with estimated output capacitance](images/student-hub/sc-waveform-results.jpg)

![Schematic and layout-loaded test voltages at the inverter's two input samples](images/student-hub/sc-sample-results.jpg)

The combinational fixture applies binary-count vectors in the listed pin order.
The grader reads the output 8 ns into each 12 ns slot. Logic low is at most
0.36 V and logic high is at least 1.44 V. The flip-flop uses separate data and
clock sources.

The timing challenges measure from the input crossing to the matching
output crossing at 0.9 V, half the supply. The DFF challenge adds an
extra clock edge to measure a rising Q after a known low state.

| Time | D | CLK | Expected Q | What the sample shows |
| --- | --- | --- | --- | --- |
| 30 ns | 1 | 1 | 1 | First rising edge captured a 1 |
| 42 ns | 0 | 1 | 1 | Q held after D fell |
| 56 ns | 0 | 0 | 1 | Falling clock edge kept Q |
| 79 ns | 0 | 1 | 0 | Second rising edge captured a 0 |
| 99 ns | 1 | 0 | 0 | Q held after D rose again |

**Show step images** shows the active layout and route form. **Do It Yourself**
gives the layout and test targets. **Show solution** explains both missing
routes and the expected test samples. The new layout lessons use their own
workspace, so earlier schematic projects are still saved.

The capacitance model uses declared teaching coefficients for area and perimeter.
The same bundled SKY130A transistor models drive both runs. The [CMOS inverter
course](STUDENT_INVERTER.md) covers process-deck DRC, LVS, and handoff.
