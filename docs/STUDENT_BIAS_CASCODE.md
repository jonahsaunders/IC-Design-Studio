# Bias a current mirror and a cascode

Open **Student Hub → Analog design projects**. Start with **Build a current
reference and bias a mirror**, then open **Cascode mirrors across process
and temperature**. Both lessons use the same editable SKY130A project.
Configure ngspice in **Engine setup**. The exercises use the bundled models
for the 1.8 V NMOS devices.

## Work backward from the spec

Begin with the signal requirement and the allowable node voltages. For
example, a target of 100 µS transconductance at `gm/ID = 20 V⁻¹` needs
`ID = 100 µS / 20 V⁻¹ = 5 µA`. Pick a channel length for gain, speed and
matching, then find the corresponding current density `J = |ID|/W` at
that length, drain voltage, well bias, process corner and temperature.
Use `W = |ID|/J`. A measured `J = 0.5 µA/µm` gives a starting width of
10 µm for 5 µA. Use the total active width and preserve consistent width,
finger and multiplier conventions when comparing model data.

Choosing current by itself leaves inversion and capacitance unspecified.
At fixed current, increasing width lowers `ID/W`, usually raises
`gm/ID` in the relevant inversion region, and adds device capacitance.
At fixed width, process and temperature can change the current, moving
the density and sometimes the efficiency and saturation margin as well.
Measure each quantity at the actual circuit bias. The same density can
produce different `gm/ID` at another corner.
[Jespers and Murmann’s device lookup methodology](https://github.com/bmurmann/Book-on-gm-ID-design)

## Build and trim a simple reference

In the simple fixture, `RSET` feeds a diode-connected NMOS. The output
MOS shares its gate voltage. Estimate `RSET = (VDD − VSET)/IREF` and
verify in the loaded circuit. With 1.8 V supply, a measured reference
node near 0.61 V and a 5 µA starting current, the estimate is about
238 kΩ. Run the operating-point test at the 1.4 V clamp. The lesson
accepts output current between 4.5 and 5.5 µA with at least 50 mV of
model saturation margin `VDS − VDSsat`.

Read `|I(VDD)|` for reference current and `|I(VCLAMP)|` for output
current. Check those separately. For a 1:1 matched pair, unequal drain
voltages and channel-length modulation can move their ratio away from
one. The resistor-set reference also follows supply and transistor
behavior. A more demanding absolute-current spec can use a stable
reference voltage, feedback, and an appropriate resistor and temperature
coefficient. Verify its startup, power and supply range separately.

## Add a cascode and find its headroom cost

The reference stack establishes two gate voltages. The upper output MOS
acts as a common-gate device, so the drain of the lower MOS moves much
less as the output swings. With stiff gate biases, the small-signal estimate is

```text
rout ≈ ro,lower + ro,upper + (gm,upper + gmb,upper) · ro,lower · ro,upper
```

The conventional stack also needs the upper device to remain in
saturation above the lower drain voltage. The lower drain approximately
tracks the lower reference device’s gate-source voltage under matched
bias. Start with `Vout,min ≈ Vmid + VDSsat,upper`, then measure the
sweep because the device voltages and current move through dropout.
[MIT cascode current mirror exercise](https://ocw.mit.edu/courses/6-301-solid-state-circuits-fall-2010/2696f5eee7da1234102c0ca2b152890a_MIT6_301F10_assn05.pdf)

Use the same 4–6 µA range at the 1.4 V clamp for both mirrors. Sweep
output voltage from 25 mV to 1.55 V and estimate `rout = ΔV/ΔI` near
the operating point, between 1.20 and 1.50 V. The lab's measured
compliance knee is the lowest sampled voltage after which the current
stays within 5% of the 1.4 V value for the rest of that sweep. This
defines the accuracy criterion for the lab. Other applications can set a
different tolerance and measure both rising and falling output swing.

At 27 °C in the nominal model, try 240 kΩ for the simple mirror and
82 kΩ for the cascode. The two sinks measure about 5.34 µA and 5.46 µA.
Their output resistances are about 2.21 MΩ and 395 MΩ. The 5% current
flatness knees in this sweep are 0.85 V and 0.25 V, while the local
saturation floors estimated at the nominal clamp are 0.074 V and 0.862 V.
Current can stay within tolerance while a stacked device leaves saturation.
A nominal saturation floor also cannot predict the precise dropout voltage
as the internal nodes move. Check both measures against your design spec.

## Verify one design over process and temperature

Choose **Run nine PVT cases** and open **Results**. Use one geometry and
one resistor for nominal, SS and FF at −40, 27 and 85 °C. The supply
stays at 1.8 V and the output clamp at 1.4 V during this experiment.

| Measure | Read it as a design check |
| --- | --- |
| `IREF` and `IOUT` | Compare absolute drift and mirror ratio separately. A cascode can improve the ratio without making the reference current temperature-stable. |
| `ID/W` and `gm/ID` | Find which conditions move the device away from its nominal current density or efficiency. Re-estimate width and current together. |
| Minimum `VDS − VDSsat` across the output stack | Find the device and condition that limits swing. Verify compliance at that condition before using the current source in an amplifier. |
| Current and headroom target | The table shows 3–7 µA and at least 50 mV as explicit exercise limits. Keep all completed rows, including failures, when you revise the design. |

With the 82 kΩ example, the nine cases span about 4.05–6.70 µA and
0.405–0.670 µA/µm. The lower output device's gm/ID ranges from about
16.82 to 23.70 V⁻¹. The smallest stack margin is about 475 mV at FF,
85 °C. The mirror ratio stays near one while the absolute current varies.

Finish by checking the chosen bias where it will be used, including
signal swing, common mode, device region, and saturation through
transients. Add supply extremes and statistical mismatch runs when the
spec requires them. Process corners shift correlated model behavior.
Use mismatch models and physical layout review to address local
device-to-device variation.
