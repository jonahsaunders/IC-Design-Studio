# Four bandgap reference lessons

Open **Student Hub → Analog design projects** and select **Widlar bandgap
reference**, **Brokaw bandgap reference**, **Kuijk bandgap reference**, or
**Banba bandgap reference**. Each lesson has a separate saved workspace,
an editable GF180 transistor circuit, and saved operating-point and startup
testbenches. Use **Open temperature model…** to make a first-order prediction,
then use the testbenches to measure what the transistor circuit actually does.
The older ideal-model projects remain usable as projects.

## Work from a specification

Use the included GF180 simulation models and ngspice. The fixture supplies
3.3 V and loads the reference with 5 pF. Keep the fixture fixed while you
adjust the circuit. These are teaching specifications for this load and the
conditions in the lab.

| Circuit | Final VREF | Nominal-process temperature span | Supply current | Startup peak | Final ripple |
| --- | ---: | ---: | ---: | ---: | ---: |
| Widlar | 1.29–1.55 V | ≤160 mV | ≤180 µA | ≤1.62 V | ≤4 mV |
| Brokaw | 1.14–1.26 V | ≤30 mV | ≤180 µA | ≤1.40 V | ≤4 mV |
| Kuijk | 1.14–1.26 V | ≤30 mV | ≤180 µA | ≤1.80 V | ≤4 mV |
| Banba | 0.57–0.63 V | ≤12 mV | ≤80 µA | ≤0.75 V | ≤2 mV |

1. **Predict and trim.** Estimate the PTAT weighting before changing one
   resistor. Run the six-temperature sweep from −40 to 125 °C. Record
   VREF at 27 °C, the worst current, and peak-to-peak voltage span.
2. **Prove startup.** The two testbenches ramp the supply from zero in
   100 ns and 100 µs. Each ramp checks nominal, SS and FF at −40, 27 and
   125 °C, plus cold/SS at the low supply and hot/FF at the high supply.
   The additional supplies are 3.2/3.4 V for Widlar and 3.0/3.6 V for the
   other references. VREF must settle within its band by 350 µs and stay in
   band through the 500 µs run. Check peak over the full trace and ripple
   over the last 100 µs.
3. **Inspect placement and routing.** Open Layout and generate the editable
   device rows, contacts, vias, and buses. Banba opens with its existing
   routed array. Check device terminals, the BJT emitter geometry, resistor
   lengths, and all three external ports. On the 1:8 layouts, inspect the
   relative emitter centers. Remove one routing via, confirm the terminal
   check catches the open, then undo the edit and rerun.
4. **Repeat on the extracted circuit.** Configure Magic in Physical tools
   setup or select a local executable. **Run extracted comparison** streams
   the current geometry and runs Magic once. The lab compares ports,
   extracted device nets, unit counts and drawn dimensions before running
   ngspice. Six nominal-process operating points and six startup cases
   run on both views. The maximum permitted final voltage shift is 12 mV for
   Banba and 25 mV for the other circuits. In Results, the solid trace is
   schematic and the dashed trace is extracted.

The physical lessons use GF180-B four-metal geometry and M3/M4 MIM.
The included GF180-D bundle supplies the electrical models. The layout
checkpoint covers local geometry and linked connectivity. The extracted
checkpoint adds capacitance and device geometry. Full process DRC, antenna,
density, and distributed wire resistance are separate verification work.
The lesson actions and result rows use explicit names, keyboard selection,
and text status for each case. [Apple accessibility guidance](https://developer.apple.com/design/human-interface-guidelines/accessibility)

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

**Transistor lab.** Trace the three GF180 NPNs and shunt device Q3.
Start with RFEED at 22 µm and R1/R2/R3 at 9/100/9 µm for 1 µm wide
poly. Set RFEED to 44 µm for a trial and compare the hot run with the
original design. Less feed current can leave Q3 without operating
margin even when the nominal resistor ratio looks reasonable. The
resistor-fed variant has a wider drift limit than the feedback references.
Try to reduce the span further and measure what it costs in supply current.

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

**Transistor lab.** The PMOS mirror senses collector-current imbalance
and drives the shared base node, following the active-sense principle.
Start with R1/R2 at 46/10 µm for 1 µm wide poly. Compare the nominal
trim to startup with a wider driver or larger CSTAB. Check the common
emitter return and all eight large-branch NPN emitter units in Layout.

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

**Transistor lab.** A two-stage PMOS-input transistor amplifier balances
the two sense nodes and drives VREF. Start at R1/R2/R3 = 100/95/10 µm
for 1 µm wide poly. Change R2, repeat the drift measurement, and explain
why it affects both ratios. The two supply-tracking tiles keep the
high-side driver closer to off during the rising edge. Shrink both for
one experiment, compare the peak and then restore the passing sizes.

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

**Transistor lab.** The editable routed implementation includes one
center PNP, eight outer PNPs and explicit series resistors and MIM
tiles. Try ROUT at 60 µm and compare against the saved 50.15 µm.
Use RPTAT to trim drift. Retain both matched CTAT branches and inspect
the startup detector, gate tracking, and output filter in the layout.
[Routed GF180 Banba design](../examples/gf180-banba/layout/README.md)

## Compare the four results

For each circuit, record the density and resistor ratios, voltage at
27 °C, slope at 27 °C, and peak-to-peak drift. Explain which parts set
the temperature weighting and which set the voltage scale. The shared
analytic model teaches first-order trim and residual curvature. Record the
measured difference between that prediction, the transistor schematic, and
the extracted layout.

To repeat all four saved checkpoints from source with the same worker used
by the app, run:

```sh
python scripts/verify_student_bandgap_labs.py --out build/bandgap-labs \
  --ngspice /path/to/ngspice --magic /path/to/magic
```

The evidence directory contains the cases, streamed layout, Magic log,
extracted netlist, and both waveform sets. [Measured reference results](validation/student-bandgap-labs-2026-11-18.json)
