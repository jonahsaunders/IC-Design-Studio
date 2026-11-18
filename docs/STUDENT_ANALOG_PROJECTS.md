# Build a TIA or op amp in Student Hub

Open **Student Hub → Analog design projects**. Choose **Design a photodiode
TIA** or **Design a two-stage op amp**. Each starts an independent, editable
SKY130A project and opens the lesson guide beside the editor. Choose
**Open workspace** to go to the circuit or test fixture for the selected step.

| Project | Nominal specification |
| --- | --- |
| Photodiode TIA | 90–110 kΩ at 100 Hz, at least 200 kHz bandwidth, no more than 2 dB peaking, and a 90–110 mV drop from a 1 µA step. The output must settle within 8 µs at 2% of the step. |
| Two-stage Miller op amp | At least 40 dB gain, 100 kHz unity-gain frequency, and 45° phase margin with a 1 pF load. The saved fixtures also check supply power, output bias, noise and startup. |

## From a specification to measurements

1. Fix the starting testbench. Set the op amp’s load to 1 pF or match the
   TIA’s AC and transient feedback networks at 100 kΩ and 2 pF. Inspect the
   output, supply, inputs and sign of the feedback before simulating.
2. Estimate input-pair transconductance from the frequency goal and Miller
   capacitance. Choose a gm/ID value, calculate branch current, and use measured
   current per width to estimate device size. Compare two equal M1/M2 widths
   and check the measured current, gm, gm/ID, and saturation margin.
   [Original gm/ID method](https://people.engr.tamu.edu/spalermo/ecen474/gm_ID_methodology_silveira_jssc_1996.pdf)
3. Trim the PMOS mirror’s RSET from its deliberately low starting resistance.
   The saved compliance sweep steps the output clamp from 0.45 V to 0.85 V.
   The entire range must stay within 4–6 µA. Use the PVT plan to explore how
   supply, temperature and process affect the result.
4. Run the saved amplifier tests, inspect the failed measurements, and
   iterate on sizing or compensation. The Hub checks the specified limits
   from the completed results for the current design.
5. Generate layouts for the amplifier core and PMOS bias mirror. Inspect
   matching, body ties, supply straps, labelled pins, and the Miller
   capacitors. Run post-layout checks for the same saved amplifier and
   current-reference fixtures. Review DRC, LVS, extraction, and how the
   before/after measurements changed. Record the results and your reasoning
   in the learning portfolio.

The TIA uses the integrated op amp with external feedback and a simulated
photodiode and board load. The current-reference exercise uses a separate
PMOS mirror with an external programming resistor. Both amplifier projects use an ideal
5 µA bias in their scored fixtures so they can isolate the effects of
amplifier sizing and extraction.

## Tools and evidence

The bundled SKY130A model package works for schematic simulation with
ngspice. For process DRC, LVS, and extraction, register a complete SKY130A
process folder. If you started with the bundled models, choose **Migrate PDK
revision…** and review each device mapping. Use **Tools → Physical tools
setup** for Magic and Netgen, or configure those executables in the Hub’s
engine setup. The saved testbench controls its extraction mode. The default
is capacitance extraction.
[Analog physical verification and supported extraction modes](ANALOG_REFERENCE_WORKFLOW.md)

The guide shows actions for the current step, names results by testbench,
and keeps feedback beside the action. Existing Student Hub keyboard search
and text size controls work with both projects.
[Apple layout](https://developer.apple.com/design/human-interface-guidelines/layout) ·
[Apple feedback](https://developer.apple.com/design/human-interface-guidelines/feedback) ·
[Apple accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility)
