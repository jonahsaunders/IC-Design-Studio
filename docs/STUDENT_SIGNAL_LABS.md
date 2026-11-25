# Student Hub signal experiments

## Circuit design challenges

See the [Engineering design labs](STUDENT_ENGINEERING_LABS.md) for the fixtures, design targets, and measurement scope.

In Student Hub, use **Map** to find the topic in its world, or use **List** and
search by title. Each lesson opens a saved, editable schematic. Start with the
prediction and capture the starter measurements. Use the task's edit control
or the schematic properties to tune the circuit. Run the task again, inspect
**Results**, then use **Check this step** to save measured evidence. The
Results window lists exact values and lets you select a test case and plot.

| World | Lesson | What you measure |
| --- | --- | --- |
| Analog | Trade gain for linearity | Compare fundamental gain and harmonics 2–5 with a fixed 10 kHz input and matched 43–49 µA drain bias. Target at most 3% THD. |
| Analog | Measure PSRR and CMRR | Isolate differential, common-mode and positive-rail excitation. At 10 kHz, target 28 dB CMRR, 30 dB input-referred PSRR+ and at least 1 V/V differential gain. |
| Analog | Drive a difficult load | Compare a follower and a compensated feedback buffer into 100 pF and 500 pF. Measure DC command error, overshoot, settling and drain supply current. |
| Mixed signal | Characterize an ADC with a ramp | Decode 4,096 uniformly sampled comparator snapshots. Find the collapsed code-3 bin, repair the ladder and read code counts, transitions, DNL and full-scale-referenced INL. |
| Analog design projects | Build a chopper amplifier | Align the modulation and demodulation clocks. Compare bypassed and chopped gain, output offset, ripple and average settling as you tune the low-pass filter. |
| Analog design projects | Design a relaxation oscillator | Set the timing components for about 2.2 kHz. Check startup, duty cycle and frequency at nominal, cold/low-rail and hot/high-rail conditions. |
| Analog design projects | Tune a simple PLL | Compare overshoot, lock time and phase drift after upward and downward 100 Hz reference steps. |
| Analog design projects | Build a programmable-gain amplifier | Size a switched feedback ladder for 2×, 4× and 8×. Verify each code's low-frequency gain and bandwidth, then measure settling during gain changes. |
| Advanced project | Build a calibrated temperature monitor | Set the divider span, fit signed integer gain and offset from 0 °C and 80 °C anchors, and validate all 15 held-out temperature and supply combinations to ±2.5 °C. |

The load, ramp, chopper, oscillator, PLL and programmable-gain projects use ngspice.
**Engine setup** in Student Hub can select a local executable. The remaining
experiments use the included solver. The fixtures use generic models. The
chopper uses ideal modulation with an injected offset, the oscillator
uses a behavioral comparator and an explicit startup pulse, and the PGA
uses a behavioral amplifier. The PGA AC bench holds the switches at their
declared on or off resistances for linearization. The temperature experiment
pairs a simulated analog front end with an ideal 10-bit ADC and an integer
readout. These assumptions define the scope of the measurements.

The checker grades the saved waveforms from the current schematic and task.
After editing, recapture the experiment before checking the step. The
temperature monitor has its own saved workspace and is available after the
ramp ADC lesson. Its two calibration coefficients are saved with the project.

## Tune a simple PLL

In **Analog design projects**, open **Tune a simple PLL** after **Set bandwidth
with an RC pole**. Capture the starter with **Run lock test**. In **Results**,
choose `vco_hz` for frequency or `phase_error` for phase in cycles.

The starter has a 4 ms RC time constant and about 44% overshoot. Use **Tune
the loop filter** to edit RFILT or CFILT. A 5 kΩ resistor with 100 nF gives a
0.5 ms time constant and about 4.3% overshoot. Verify that the loop stays
within 2 Hz of the reference within 6 ms after each step. The checker also
limits final phase error to 0.15 cycles and late phase drift to 0.01 cycles
peak-to-peak.

The idealized phase-domain model uses a linear phase detector and integrates
the VCO frequency deviation around a 1 kHz carrier. The measurements teach
the loop’s transient response to small frequency steps. Clock waveforms,
cycle slips, jitter, and transistor effects are outside this model.

## Device and circuit labs

These eight labs use ngspice with generic teaching models. Open **Analyze
before running** to identify the DC or charging path and save an estimate.
Compare it with the measured values from the same checkpoint. Where the
lesson offers a region prediction, the DC case provides device data for the
schematic annotations.

| Lab | Measurement |
| --- | --- |
| Extract MOSFET output resistance from a DC sweep | Compute the inverse drain-current slope between 0.8 V and 1.2 V and report the bias conditions. |
| Make body effect visible | Find the gate voltage at 10 µA for body-tied and reverse-biased cases. Report the gate-voltage shift. |
| Compare MOSFET and resistor loads | Match the DC operating points. Compare the 100 Hz gain using a resistor and a diode-connected PMOS. |
| Measure a complementary transmission gate | Use a 5 mV test drop to measure switch resistance at three common-mode voltages. Compare the complementary gate with an NMOS alone. |
| Compare thermal and flicker noise | Subtract squared amplitude densities of matched benches to isolate the modeled flicker contribution. |
| Explore leakage in a bias network | Infer reverse-biased diode current from the resistor drop at 27 °C and 85 °C. Reduce the hot bias error by changing the bias resistance. |
| Design a common-mode feedback loop | Tune loop gain and compensation after a common-mode disturbance. Check recovery, residual error and the preserved differential signal. |
| Separate charge injection and clock feedthrough | Capture a modeled charge packet, explicit overlap capacitance and their combined effect. Compare the held-voltage steps. |

The common-mode lab uses a symmetric behavioral output stage. The sampling
lab uses an ideal switch, an explicit charge pulse and a separate overlap
capacitor. Their measurements cover those teaching circuits.
