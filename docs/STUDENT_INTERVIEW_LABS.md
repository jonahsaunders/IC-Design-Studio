# Analog IC interview labs

Open **Student Hub → Analog design projects** and search for a topic or
**interview practice**. Each lesson starts with a prediction, gives you an
editable circuit and a measured experiment, and ends with a follow-up
question. Use **Open circuit** to edit the circuit, **Open workspace** to go
to the current fixture, and **Results** to switch cases and signals. The
measured checkpoint follows the current saved circuit revision.

Most experiments use the bundled SKY130A models and ngspice. Offset
and mismatch use an explicit threshold model in the built-in solver.
Post-layout debugging uses the built-in distributed interconnect extractor
with declared teaching coefficients. Result controls support keyboard
selection and show the relevant quantities with units.
[Apple keyboard guidance](https://developer.apple.com/design/human-interface-guidelines/keyboards/) ·
[Apple accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility)

## Differential pair and common-mode range

Start with the current path from both resistors through the input pair and
tail device. At zero differential input a matched pair splits the current.
For a small differential input the branch-current difference is about
`gm × vid`, where gm is the transconductance of one transistor at its
quiescent current. The branch with more current pulls its drain lower.
Beyond the local linear range, the tail current steers almost entirely
into one side. In the second sweep both inputs move together with a fixed
10 mV difference. Compare the tail voltage and branch currents near the
edge of the usable range. Tell an interviewer which device to inspect first
when gain collapses at low common mode.
[MIT differential amplifier lecture](https://web.mit.edu/6.012/FALL00/www/handouts/lec25.pdf)

## Choosing a PMOS or NMOS input pair

| Check | Bottom-tail NMOS pair | Top-tail PMOS pair |
| --- | --- | --- |
| Sketch the source voltage | `VS ≈ VCM − VGS` | `VS ≈ VCM + abs(VSG)` |
| First tail-device limit to estimate | `VCM,min ≈ VSS + VGS + VDS,sat,tail` | `VCM,max ≈ VDD − abs(VSG) − abs(VSD,sat,tail)` |
| Check the other side | Input transistors need drain voltage above their sources | Input transistors need drain voltage below their sources |

Run both 1.8 V fixtures. Measured usable range requires tail current within
20% of its value at 0.70 V and at least 70% of the differential gain there.
The saved NMOS case covers 0.62 V through the 1.80 V sweep endpoint.
The PMOS case covers 0–0.78 V. The tail currents at 0.70 V are 2.66
and 2.62 µA. To try another bias, edit VBIAS in the corresponding
`nmos_common_mode_fixture` or `pmos_common_mode_fixture`.
Compare the measured ranges against a sensor's specified input common mode.
If you compare gain, noise, or speed, first measure current and pick a fair
bias condition. Consider body effect, device area, source impedance and
input capacitance. PMOS often helps with flicker noise in a given process,
while actual sizing and device-model data determine the comparison.
Complementary pairs can widen the range. Where both conduct, their
transconductances and offsets combine, so check the transition and feedback
stability there.

## Gain, swing, and transistor headroom

Use one middle-gate drain sweep for output conductance. Use the two nearby
gate sweeps for transconductance at the same drain voltage.

```text
gm ≈ [ID(VG+ΔV, VD) − ID(VG−ΔV, VD)] / (2ΔV)
gds ≈ [ID(VG, VD+ΔV) − ID(VG, VD−ΔV)] / (2ΔV)
ro = 1/gds
Av ≈ −gm(ro || RD)
```

Compare 0.08 V and 0.80 V at the drain. Explain why even the larger
intrinsic gain is reduced by a 50 kΩ load. At the whiteboard, mark the
allowed output swing before proposing a cascode. Increasing channel
length and increasing current are separate experiments with effects on
output conductance, transconductance, capacitance, and power.

## Slew rate and precision settling

Try a 20 mV command and 500 mV steps in both directions on the same
follower. Repeat the large steps with four times the load. Compare
sourcing and sinking. `I=C dV/dt` gives an estimate of
the current needed for a required large-signal slope. A measured 10–90%
slope averages current-limited and linear portions of a trace. Inspect
the waveform for an approximately constant-slope interval. Dynamic 2%
settling uses the last exit from a band around the measured final output.
The displayed DC tracking error lets you apply a separate absolute
accuracy requirement to the commanded voltage. A good phase margin can
coexist with a large-signal slew limit or a DC error that exceeds the band.
[Texas Instruments op-amp specifications](https://www.ti.com/lit/an/sloa011b/sloa011b.pdf)

With 2 pF, the 500 mV falling step takes about 141 ns between its 10%
and 90% levels. With 8 pF it takes about 384 ns. The rising transition
changes little in that comparison, while its 2% settling increases from
204 ns to 308 ns. Use the asymmetry to discuss which circuit node or
current may be limiting each part of the response.

## Noise budgeting

Predict `sqrt(4kTR)` for the source resistor before opening the 10 Hz–1 MHz
noise spectrum. At room temperature, 1 kΩ contributes about 4.1 nV/√Hz
and 100 kΩ about 40.7 nV/√Hz at its own terminals. Independent noise
contributions sum in mean square after each is referred to the same node
with its transfer function. Integrate squared voltage density over
frequency and then take the square root. Compare input-referred and
output RMS and use the reported contributors to identify the resistor
and MOS noise terms. Device subtotals already contain their component
terms. Describe how a wider input device can lower flicker noise while
increasing source loading and changing bandwidth.

## Offset and mismatch

Both pairs have the same width-to-length ratio. Doubling both dimensions
quadruples area. The explicit classroom threshold model has
`sigma(VTH) = (4 mV·µm)/sqrt(WL)` for each device. A 300 Ω load imbalance
adds a deterministic shift. Compare means and spread, then match the
load resistors and rerun with the same seed. Estimate input-referred
error by dividing the differential output error by the slope from a local
voltage sweep. The two 64-trial samples illustrate sensitivity to area and
mean shift. Foundry mismatch models and more complete yield sampling are
separate checks. [Pelgrom and coauthors](https://ewh.ieee.org/r5/denver/sscs/References/1989_10_Pelgrom.pdf)

## Dynamic comparator

Trace the precharge devices, differential input pair, and regenerative
feedback in order. Define decision delay from the 20 ns clock edge to an
output separation of 0.9 V. Compare 3 mV and 40 mV input overdrive.
Select an input signal and compare it with the ideal driver on the other
side of the source resistor. Charge coupled through transistor
capacitances changes the input voltage briefly. Try a different source
resistance and discuss what could change if a sampling capacitor supplies
the input. [Razavi's StrongARM circuit walkthrough](https://seas.ucla.edu/brweb/papers/Journals/BR_Magzine4.pdf)

## Sampler and SAR capacitor DAC

At 300 K a 60 µV RMS sampled-noise budget needs about 1.15 pF by
`C >= kT/vn²`. The corrected four-bit array uses 1.60 pF including the
dummy capacitor. With an ideal 1.60 V reference, an 800 fF MSB gives a
0.80 V trial step. Measure error immediately before the switch opens,
the hold pedestal after it opens, and the change when the MSB bottom
plate is driven. The latter isolates an incorrect bit weight from the
initial acquisition error. The reported code combines a measured MSB
voltage with calculated lower weights and ideal decisions. For full
clocked control logic and converter output codes, see the
[existing SAR converter project](../examples/sar-adc/README.md).
[Analog Devices capacitor DAC walkthrough](https://www.analog.com/media/en/training-seminars/tutorials/mt-021.pdf)

## LDO and power delivery

Find the pass PMOS, feedback divider and error-amplifier polarity.
A 0.90 V reference with 20 kΩ/60 kΩ gives 1.20 V. At 25 µA load, sweep
input supply and identify where the output first enters the 2% regulation
band. Inspect the error amplifier's input common mode and the pass gate
before attributing the full measured headroom to the pass transistor.
Keep the supply fixed and apply a 25-to-100 µA load step. The
capacitor initially supplies the current difference. `ΔI/C` estimates
the initial droop slope and `ΔI × ESR` the resistive change. Compare
two ESR values on the same load step, then test a line step and power-on
ramp. The fixture supplies the reference and bias separately. Explain
why a favorable ESR in this circuit gives no universal capacitor rule,
and what you would sweep before accepting a load or capacitor change.
[Texas Instruments LDO stability experiments](https://www.ti.com/lit/an/slva115a/slva115a.pdf)

## Debug extracted settling

The schematic passes a 50 ps, 2% settling target. At 0.20 µm width the
extracted route adds about 227 Ω and 0.91 fF. It settles in about 51.75 ps.
Try 0.40 µm and then 0.80 µm with identical stimulus, load and measurement.
The wider routes reduce resistance, and their extra capacitance reverses
the improvement at 0.80 µm. Use the plot and extracted metrics to explain
the failure, then save a passing route. This interconnect experiment
uses the declared-coefficient R/C model and the existing linked-terminal
geometry checks. [Physical layout lesson](STUDENT_LAYOUT_DECISIONS.md)

## Practice the interview answer

Name the operating state and controlling node before quoting a
measurement. Draw the current path or reduced model and write the one
equation that predicts the direction of the change. Use two measured
values to explain how you separated possible causes. Finish with a
tradeoff and the next measurement that would test your conclusion.

Run the same saved experiments and checkpoints from a source checkout:

```sh
python scripts/verify_student_interview_labs.py --out build/interview-labs --ngspice /path/to/ngspice
```

[Measured reference results](validation/student-interview-labs-2026-11-18.json)
