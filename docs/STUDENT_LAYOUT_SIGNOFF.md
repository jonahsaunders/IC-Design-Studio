# Layout integration and signoff labs

## Passive placement and routing

See the [Engineering design labs](STUDENT_ENGINEERING_LABS.md) for the fixtures, design targets, and measurement scope.

Open **Student Hub → Map → Layout** to find the nine advanced labs. They are
also searchable in **List**. Each opens an editable Studio project with a
prediction, measurable checkpoints and a reflection.

| Topic | Lessons | Evidence |
| --- | --- | --- |
| Floorplanning | Plan a block before routing, Fix a pin-access bottleneck | Placement area, pin distance, legal detour, routed length and via count |
| Chip integration | Build a pad ring | The checked links from five perimeter pads to the core-side interface |
| Process signoff | Repair a metal-density violation, Fix an antenna violation | Local metal coverage, estimated fill loading, and early-stage and protected area-ratio comparisons |
| Power & reliability | Find the via current bottleneck | Legal cuts, estimated equal-share cut current and voltage drop |
| Isolation | Place taps and guard rings | Closed active and metal, quiet-return continuity and contact pitch |
| RF & passives | Tune an on-chip spiral | Generated layout, inductance, DC series resistance, and modeled Q and self-resonance |
| Tapeout handoff | Catch a bad GDS export | Original and corrected streams, SHA-256, and independently checked masks, hierarchy and labels |

## Use one saved macro from floorplan through handoff

1. Record the initial GF180 pass-device placement. Move the second physical
   instance to meet the footprint and terminal-distance targets. The guide
   adjusts its port landings with the instance.
2. Measure the metal-1 detour around the fixed channel obstruction. Try another
   placement or allow metal2 in **Plan pin route** and check size, length and vias.
3. Capture the first GDS with **Export and inspect GDS**. Open **Results** to
   see its actual top cell, hierarchy, mask layers, labels and output path.
   Restore the missing pin-purpose label with **Assign stream pin label**,
   then export and inspect again.

Readback opens the GDS directly in KLayout. It verifies masks using geometric
XOR and separately compares placements and top-level label positions and
layer/datatype. It never restores the Studio sidecar during that comparison.
Both GDS files remain in their respective run folders and each checkpoint
records its own checksum. An edited layout requires a new capture.

## Scope of the exercise measurements

- The macro uses real GF180MCU C device geometry. Its checkpoints grade declared
  layout rules, linked connectivity, and stream equivalence. The corrected
  GDS still needs the target process DRC, LVS and submission checks.
- The pad ring is an interface coupon that checks geometry, port mapping and
  pad-to-core routing. Pad cell selection, ESD and package acceptance are
  subsequent engineering work.
- Density uses Studio's real mask-area windows and fill generator. The loading
  comparison is an explicit edge-gap estimate treating fill as AC ground.
  The antenna lab uses a fixed, staged teaching rule and an educational diode
  credit. Use the target process deck to evaluate permitted devices and rules.
- Via current uses fixed load and equal sharing. Guard-ring checks prove
  enclosure, contact coverage and linked continuity in the coupon. Process
  reliability and isolation require independent evidence.
- The coil uses Studio's spiral geometry and DC models with a declared lumped
  capacitance. Its RF results are repeatable estimates for comparison. An EM
  solver or calibrated measurements can refine the result.

The [device and post-layout labs](STUDENT_LAYOUT_LABS.md) cover process MOS
verification, the matched amplifier, the capacitor DAC and RC comparisons.
