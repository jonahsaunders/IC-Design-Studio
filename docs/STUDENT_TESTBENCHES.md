# Student testbenches

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
Both use the same schematic, output node, native ngspice analysis and
measurement limits. The graphical form and program are saved with the lesson
project. Use **Open workspace** to inspect or edit the circuit under test, sources,
and loads. The TIA and op-amp projects load Studio's bundled SKY130 models.
If Studio cannot locate ngspice, choose its executable in **Engine setup**.

1. In **Graphical testbench**, choose **Edit testbench**. Fill in **Analysis and
   fixture**, select the output probe under **Probes and startup**, set up the
   voltage check in **Measurements**, and save.
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
