# Why layout choices matter

Open **Student Hub → Layout → Why layout choices matter**. The lab has
three editable layout cells. **Open workspace** takes you to the cell for the
selected step. Inspect your edits with generic geometry checks and measure
their electrical effect with the same circuit and AC sweep.

## Decide what the layout must preserve

| Decision | Why it matters | Evidence to look for |
| --- | --- | --- |
| Floorplan and orientation | A short signal path reduces R and C. Matching depends on how devices see edges, gradients, stress and nearby heat. | Trace signal and return routes. Compare orientation, surroundings, contact count and distance to sensitive nodes. |
| Width, spacing and vias | Wide metal reduces resistance and current density. Additional overlap can increase capacitance. A poorly enclosed via can be resistive or open after alignment variation. | Measure width, spacing and enclosure on both metals. Check current density and via limits for the actual process. |
| Differential matching | Equal devices need similar electrical and physical environments. Common-centroid placement cancels a first-order gradient for equal unit groups. Edge dummies help equalize surroundings. | Compare centroids, unit geometry, gate and body ties, route resistance and capacitive loading. |
| Supply, substrate and return paths | Return impedance moves local ground. Aggressors couple through the substrate and through neighboring conductors. | Inspect ties, return loop, decoupling, long parallel runs and any shield connections. Use appropriate supply and coupling checks. |
| Signal and power integrity | Added R shifts operating points and slows edges. Coupling can inject noise. Limited current density and temperature determine reliability. | Review extracted simulation, supply drop, electromigration and reliability separately from width and spacing. |

## Repair two coupons and diagnose an open

Move the 0.15 µm via inward until the 0.50 µm pads enclose it on every
side on both layers. Measure what remains under a hypothetical alignment
shift. In the matching coupon, change AABB to ABBA or BAAB. For AABB, the
two mean positions are 0.60 and 2.20 µm. ABBA puts them both at 1.40 µm.
A linear gradient then contributes the same first-order shift to both groups.
Random mismatch, nonlinear gradients and unequal wiring still need attention.

In the routing cell, delete just the `vout` path. Compare **Geometry DRC**
with the linked connectivity check, then undo the deletion. The separated
pads can satisfy geometry rules while the output is open. DRC checks
geometry and process constraints. LVS compares extracted device identity
and connectivity against the schematic. The linked connectivity check in
this lab makes the open visible using the teaching layout and declared pins.

## Treat routing as part of the circuit

Use `Rwire ≈ Rsheet × length/width` and
`f₃dB ≈ 1/(2πRC)` to estimate what should happen. The schematic’s 1 kΩ and
10 fF imply a corner close to 15.92 GHz. The 22.665 µm route with a 2 Ω/□
teaching coefficient adds distributed resistance and capacitance. Run
**Compare route RC** at three widths using the same schematic and AC sweep.

| Width | Modeled route R | Added capacitance | Modeled bandwidth |
| --- | ---: | ---: | ---: |
| 0.20 µm | 226.7 Ω | 0.91 fF | 12.16 GHz |
| 0.40 µm | 113.3 Ω | 1.36 fF | 12.78 GHz |
| 0.80 µm | 56.7 Ω | 2.27 fF | 12.41 GHz |

The target is 12.50 GHz. The narrow route loses bandwidth to resistance.
The wide route saves resistance and adds enough capacitance to miss the
target again. Look for a shorter route, make room at sensitive nodes, and
verify after each change. The lesson uses declared teaching coefficients and
a distributed RC estimate. For a process design, follow the applicable
decks, extraction mode and verification flow.
[Process verification and extraction](ANALOG_REFERENCE_WORKFLOW.md)
