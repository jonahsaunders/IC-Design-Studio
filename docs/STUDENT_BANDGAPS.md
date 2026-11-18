# Four bandgap reference lessons

Open **Student Hub → Analog design projects** and select **Widlar bandgap
reference**, **Brokaw bandgap reference**, **Kuijk bandgap reference**, or
**Banba bandgap reference**. Each lesson has a separate saved workspace,
worked prediction, temperature study, and reflection. Use **Open temperature
study** to sweep the model from −40 to 125 °C. The editable starter schematic
lets you check the voltage or current summation at 27 °C.

## Start with two current densities

For ideal matched junctions, `VBE ≈ VT ln(IC/IS)`, where `VT = (k/q)T`
and `T` is in kelvin. Saturation current scales with emitter area in this
model. If junction 1 has higher current density than junction 2,

```text
ΔVBE = VBE1 − VBE2 = (k/q)T ln(J₁/J₂)
J₁/J₂ = (I₁/I₂)(A₂/A₁)
```

A fixed density ratio makes the difference proportional to absolute
temperature (PTAT). The voltage across a forward-biased junction usually
falls with temperature under the bias used here (CTAT). The classroom
model uses `VBE = 0.700 − 0.0018 ΔT − 0.0000012 ΔT²` in volts, with
`ΔT = T°C − 27`. At 27 °C, cancel the negative slope by adding
`G × ΔVBE`, where `G ≈ 1.8 mV/K ÷ ((k/q)ln(J₁/J₂))`.
The quadratic term survives that trim. With exact first-order cancellation,
the example still drops about 11.5 mV from 27 to 125 °C before any output
scaling.

## Widlar

The original circuit develops a voltage difference from transistors at
different current densities, converts it to current with R₃, and adds
the drop across R₂ to a junction voltage. The lesson uses equal emitter
areas, so a 10:1 current ratio gives the 10:1 density ratio.

```text
Vref = VBE,Q3 + (R₂/R₃)ΔVBE
```

At 27 °C, the difference is about 59.6 mV. With R₂/R₃ = 9.1 the
model gives about 1.242 V. Reduce the current ratio to 4 and observe the
negative room-temperature slope. Predict the new ratio R₂/R₃, about
15.07, then compare local slope and full-range drift after the trim.
[Widlar, 1971, Figure 2](https://class.ece.iastate.edu/djchen/ee501/2013/BandGapRefFirstRealPaperByBobWidlarJSSC1971.pdf)

## Brokaw

The feedback loop holds the two collector currents near equality. An
8:1 emitter-area ratio sets an 8:1 density ratio. The resistor carrying
both branch currents contributes the factor of two.

```text
Vref = VBE1 + (2R₁/R₂)ΔVBE
```

At 27 °C, ΔVBE is about 53.8 mV. R₁/R₂ = 5 gives about 1.238 V
and the local trim is about 5.02. Try changing the emitter-area ratio
to 4 and recovering the slope with R₁/R₂ ≈ 7.53. In a real cell,
check collector-current balance, transistor base currents, loop stability,
resistor matching, and startup.
[Brokaw, 1974, Figure 2](https://class.ece.iastate.edu/djchen/ee501/2013/bandgaprefpaperbypaulbrokawjssc1974.pdf)

## Kuijk

The amplifier balances the sense voltages. The current-setting resistors
and the emitter areas jointly set the density ratio. The resistor ratio that
weights ΔVBE can be tuned independently in the lesson.

```text
J₁/J₂ = (R₂/R₁)(A₂/A₁)
Vref = VBE1 + (R₂/R₃)(k/q)T ln((R₂/R₁)(A₂/A₁))
```

With A₂/A₁ = 8 and R₂/R₁ = 1, choose R₂/R₃ ≈ 10.05 for the
room-temperature trim. Double R₂/R₁ to get a density ratio of 16
and predict the new trim, about 7.53. The amplifier’s input offset and
drift perturb the sense equality, so check the real loop across common
mode, supply, and temperature.
[Kuijk, 1973, Equation 2](https://class.ece.iastate.edu/djchen/ee501/2013/BandGapRefPaperByKarelKuijkJSSC1973.pdf)

## Banba

The sense amplifier and mirrors combine CTAT and PTAT currents. An
output resistor converts the sum to a chosen voltage.

```text
Iref = Vf/R₂ + ΔVf/R₃
Vref = R₄ Iref = (R₄/R₂)[Vf + (R₂/R₃)ΔVf]
```

With an 8:1 density ratio, R₂ = 100 kΩ and R₃ = 10 kΩ, the model gives
about 7.00 µA CTAT plus 5.38 µA PTAT at 27 °C. R₄ = 50 kΩ gives
about 0.619 V. Reduce R₄ to 40 kΩ to get about 0.495 V. Both voltage
contributions scale by 0.8 and the cancellation ratio stays the same.
A real circuit's minimum supply also depends on the sense amplifier
input range, forward junction voltages, mirror compliance, and startup
path. Use the bundled GF180 Banba-style demonstrator for a follow-up
on these checks.
[Banba et al., 1999, Equations 8–12](https://class.ece.iastate.edu/djchen/ee501/2013/BandGapRefPaperByBanbaJSSC1999.pdf) ·
[GF180 Banba-style demonstrator](BANDGAP_COMPATIBILITY.md)

## Compare the four results

For each circuit, record the density and resistor ratios, voltage at
27 °C, slope at 27 °C, and peak-to-peak drift. Explain which parts set
the temperature weighting and which set the voltage scale. The shared
analytic model and ideal summation schematics teach first-order trim and
residual curvature. A transistor reference also needs process models,
mismatch and resistor temperature coefficients, startup, supply rejection,
and load verification.
