# Student testbenches

## Build an Op-Amp Verification Suite

Open **Student Hub → Testbenches → Build an Op-Amp Verification Suite** and
start with **DC bias and input offset**. The seven lessons share one workspace.
Each checkpoint opens an editable fixture with a setup to complete. The reference
DUT is a behavioral teaching model with two poles under capacitive load, input
offset and headroom, slew limiting, rail feedthrough, and resistor thermal noise.
It runs in ngspice without a process kit.

| Pin | Function |
| --- | --- |
| INP | Noninverting input |
| INN | Inverting input and feedback return |
| OUT | Output under test |
| VDD | Positive supply at 1.8 V DC |
| VSS | Negative supply reference at 0 V DC |

The teaching datasheet applies at the nominal setting and 27 °C.

| Lesson | Conditions and passing measurements |
| --- | --- |
| DC bias and input offset | At 0.90 V input in unity feedback, draw 95–105 µA from VDD and measure a signed equivalent input offset of +0.8 to +1.2 mV. |
| Input common-mode range and output swing | Keep output within 4 mV of 0.90 V while actual common mode moves from 0.35 to 1.45 V. In a separate sweep, span 0.22–1.55 V at the output with a 100 kΩ load to ground. |
| Open-loop gain and feedback stability | At 47 pF, verify the 0.90 V follower bias with a zero-DC series injector. Measure at least 75 dB at 10 Hz, a first falling unity crossing of 1.2–1.8 MHz, and phase margin of at least 55°. Restore direct feedback and compare the step at the same load. |
| Small- and large-signal step response | At 47 pF, a 10 mV step has at most 20% overshoot and settles to within 2% in 1.5 µs. For a 0.70 V step, the 30–70% rising slew rate is 0.15–0.25 V/µs. |
| PSRR and CMRR | At 1 kHz, measure at least 45 dB for each supply independently and at least 45 dB common-mode rejection. The common-mode fixture has a noise gain of 2. |
| Input-referred noise | With 1 kΩ source resistance, plot input-referred density and measure 1.8–2.8 µV RMS from 10 Hz to 100 kHz. |

The loop fixture puts VINJ between OUT and INN (FB). Its 0 V DC value
preserves the normal operating point. After checking bias, apply 1 V AC
and plot the complex return ratio **T = −V(out)/V(fb)**. The Results dialog
shows its gain and phase. Read phase margin as 180° plus the unwrapped phase
at the first falling 0 dB crossing. In the transient checkpoint, reconnect
INN to OUT and keep CL at 47 pF.

In the challenge, screen all three variants at nominal DC. Compare their
diagnostic runs with the reference from the earlier lessons, using the same
stimulus and load. Use **Results → Save plot** to keep one diagnostic plot
per case and record a one-sentence verdict for each in the reflection.

## Balanced differential stimulus

See the [Engineering design labs](STUDENT_ENGINEERING_LABS.md) for the fixtures, design targets, and measurement scope.

Open **Student Hub → Testbenches** in the world map or lesson list. Each project
starts with an editable circuit and three fixture schematics. Work through a
project in order to carry your circuit changes into the later lessons.

| Project | First lesson | Second lesson | Third lesson |
| --- | --- | --- | --- |
| Resistor divider | Repair the ratio and measure the 0.5 V operating point | Sweep VIN and confirm a slope of 0.50 V/V and the 0.4 V reading at 0.8 V | Add the time-domain check and read about 0.316 V at 3 µs |
| Photodiode TIA | Set the photocurrent and check the bias near 0.8 V | Check about 100 kΩ of transimpedance at 100 Hz | Settle within 20 mV of the final level in 12 µs, with at most 20 mV of undershoot |
| Two-stage op amp | Check the 0.9 V follower operating point | Measure loop gain and at least 45 degrees of phase margin | Settle within 20 mV of 0.95 V in 8 µs, with at most 20 mV of overshoot |

The balanced differential exercise uses its own fixture. Results shows both
inputs, common mode, and differential voltage. The common-mode error must
stay within 5 mV of 0.90 V from 2 through 8 µs, including the transition.

## Choose either workflow

On **Create and verify the bench**, pick **Graphical testbench** or **SPICE program**.
Both use the same schematic, probes, native ngspice analysis and
measurement limits. The graphical form and program are saved with the lesson
project. Use **Open workspace** to inspect or edit the circuit under test, sources,
and loads. The Photodiode TIA and Two-stage op amp sequences load Studio's bundled SKY130 models.
If Studio cannot locate ngspice, choose its executable in **Engine setup**.

1. In **Graphical testbench**, choose **Edit testbench**. Fill in **Analysis and
   fixture**, select the output probe under **Probes and startup**, set up the
   required check in **Measurements**, and save.
2. In **SPICE program**, choose **Edit SPICE program**. Type the analysis and
   the `lesson_value` reading. Studio supplies the fixture netlist and wraps
   your commands in `.control` and `.endc`. For the divider DC sweep, for example:

   ```spice
   dc VIN 0 1 .1
   meas dc lesson_value FIND v(out) AT=0.8
   ```

Choose **Run lesson** after saving the configuration. **Results** shows the
measurement, waveform and simulator log. Use its run picker to compare saved
runs from both workflows. **Check this step** accepts a passing run that
matches the current project. Run again after changing the design or its
saved configuration.

In **Step by step**, **Show step images** shows the schematic and the selected
workflow's native controls. **Do it yourself** gives the experiment and target.
**Show solution** supplies both setups and the actual ngspice commands.

The AC readings are linearized magnitudes. Divide by the stimulus amplitude
to report the corresponding gain. A TIA with 1 µA of AC input and 0.1 V at
the output has a magnitude of 100 kΩ. The op-amp fixture uses 1 V of AC
excitation, so the output magnitude in volts is numerically equal to its
small-signal gain in V/V.
