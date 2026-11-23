# Layout world labs

Open **Student Hub → Map → Layout**. The same lessons appear in **List**.
Complete the introductory geometry labs to unlock the advanced topics.
Each lesson has an editable project, a prediction, checked work and a
reflection. **Practice lesson** lets you open any starter early.

| Topic | Lessons | Evidence |
| --- | --- | --- |
| Device layout | Fold a MOSFET, Fix a floating body | GF180MCU C single- and four-finger devices, a repaired body tie, and fresh process DRC/LVS reports |
| Precision layout | Match a differential pair, Lay out a capacitor DAC | Balanced placement and routing, plus effective DAC weights and the eight modeled code levels |
| Connectivity debug | Find a DRC-clean LVS failure, Change a shared cell safely | Repaired open, short and swapped-port cases, plus a resized master and two verified parent placements |
| Post-layout lab | Recover amplifier settling time, Quiet a noisy neighbor | Schematic and estimated interconnect transients on identical benches |
| Power & reliability | Repair a weak supply route | Load voltage and static supply drop at the same current |

## Follow the amplifier through three lessons

**Match a differential pair**, **Find a DRC-clean LVS failure**, and **Recover
amplifier settling time** share one saved project. The first lesson puts the
main cell’s input and output routes into balance. The three connectivity faults
live in separate cells, so repairing them preserves the main amplifier.
The settling experiment returns to that amplifier. Keep the two long stubs
until you capture the failing baseline. Compare the layouts at the same 1.4 ns
deadline against the settled schematic value at 2.5 ns.

Choose **Open workspace** after changing steps when a lab switches cells.
**Results** opens the captured comparison. **Check this step** validates the
current design and records the measurements with the learning record. An edit
after a captured run requires a new comparison for the edited design.

## Verification scopes

- The folding and body-tie lessons require the bundled GF180MCU C process
  package and working Magic and Netgen. Open **Tools → Physical tools setup**
  to configure the included runtime. These checkpoints require real process
  DRC and an extracted device and connectivity match. Missing tools or decks
  cannot earn credit.
- The three DRC-clean faults use fixed generic geometry rules with a linked
  terminal and physical port comparison. The shared-cell lesson uses real
  GF180 geometry and checks the regenerated footprint and parent wiring. The
  full process-device LVS flow is taught in the two Device layout labs.
- The interconnect labs use Studio’s distributed RC estimator and fixed
  training coefficients. The DAC uses ideal charge redistribution to compute
  endpoint-normalized levels and INL from the layout-derived bit weights.
  The noise estimator models same-layer coupling and shield loading. It
  omits cross-layer coupling and electrostatic screening, which students
  address in their reflection. The supply lab checks voltage drop at 1 mA.
  Current density and via reliability require separate process evidence.

The recorded work is available in an exported Student Hub learning record.
Continue with the [layout integration and signoff labs](STUDENT_LAYOUT_SIGNOFF.md)
to floorplan, route and independently read back a GF180 macro.
