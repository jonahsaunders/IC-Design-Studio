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
| Analog design projects | Build a programmable-gain amplifier | Size a switched feedback ladder for 2×, 4× and 8×. Verify each code's low-frequency gain and bandwidth, then measure settling during gain changes. |
| Advanced project | Build a calibrated temperature monitor | Set the divider span, fit signed integer gain and offset from 0 °C and 80 °C anchors, and validate all 15 held-out temperature and supply combinations to ±2.5 °C. |

The load, ramp, chopper, oscillator and programmable-gain projects use ngspice.
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
