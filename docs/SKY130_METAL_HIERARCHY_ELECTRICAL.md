# SKY130 metal-resistor hierarchy electrical checks

The selected repeated-cell LI/M1–M4 layouts now pass independent electrical
checks on Windows and native Linux. The [validation record](validation/sky130-metal-hierarchy-electrical-2026-10-28.json)
binds the original source snapshot, native layouts, simulator inputs and raw
outputs. This adds a finite electrical milestone to the
[physical hierarchy milestone](SKY130_METAL_RESISTOR_HIERARCHY.md).

Each of the five models has two retained rotations. All ten layouts are checked
at each of five explicit passive sections at 27 °C: fifty contexts per host.
Every context executes four DC terminal excitations, four AC basis excitations
and a wrong-section control, totaling 450 native executions per host.
The application, independent literal reference and native-extracted network
must agree; numeric, crossed-connection, missing-device and wrong-width controls
must fail their declared comparisons.

The independent reader derives its current matrix from the retained upstream
coefficients and network topology. Both hosts pass all terminal-current and
conservation comparisons, including 41,300 zero-current observations and 18,200
conservation checks per host. Each also rejects all seventeen deliberately
corrupted, fully rehashed evidence sets. The maximum normalized current error
is approximately 6.44 × 10⁻¹⁰ of the fixed acceptance bound.

The first reader rejected a saved summary because independently parsed source
coefficients and frozen JSON literals differ in their final floating-point
bit. The corrected reader separately checks the producer's summary using its
original arithmetic; the scientific comparisons still use independently
derived coefficients. The original failed reader, its output and the correction
are retained separately. No scientific bound was relaxed.

The compact archive stores shared bytes once and preserves the original
execution identities. Both original host results have been restored and read
on both platforms. Three representative corruptions were reconstructed exactly
and rejected on each host. The archive and its recovery sidecars have also been
independently rehashed after integration.

This scope contains two reused 2 × 5 µm straight leaves per hierarchy. The native
physical extraction uses an exact-mask flattened copy of the selected hierarchy.
It does not establish general hierarchical extraction, arbitrary geometry,
distributed interconnect RC, an operating or reliability envelope, precision
resistor suitability, installed acceptance, full-family qualification or chunk 7
completion. The upstream warning about generic resistors in precision analog
use continues to apply.
