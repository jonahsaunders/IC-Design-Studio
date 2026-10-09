# GF180 standard-cell block fill

The physical settings editor provides **Generate GF180 C/D block density fill**
for the supplied 9-track, 5-metal, 5 V digital platforms. Select it before
implementation, then run to GDS. Changing this setting invalidates the physical
checkpoints. The C 9K and D 11K stacks keep separate extraction rules.
Large filled blocks can exceed the examples' ten-minute tool limit during
device-level comparison. Set the digital execution timeout to 3,600 seconds
when reproducing the UART/APB reference checks; this changes the tool's allowed
running time, not the design's clock or electrical limits.

The versioned recipe uses the supplied capacitive filler cells, a captured
power-grid configuration, and staggered 2 µm Metal1 squares outside the core.
It preserves the declared die/core area, RTL, clock and I/O constraints. Original
PDK files remain unchanged. Custom power grids, macro placement, pre-existing
dummy fill and memory geometry require separate recipes and are rejected by this
option. Generation is bounded to a 1 mm² block and 100,000 squares; these are
resource limits, not an assertion that every block inside them is qualified.

Finish writes the filled GDS and checks every added square against the declared
circuit/marker clearances. An extraction copy of the final database represents
each square at exactly its written bounds, with no circuit terminals attached.
Readback verifies the serialized geometry and unchanged original wires. OpenRCX
extracts the full coupling matrix using the matching typical interconnect deck.

The timing model eliminates floating conductors using their zero-charge,
quasistatic capacitance matrix. Signal terminal and resistance records survive
unchanged; both ends of every mutual capacitance must agree. The raw extraction,
geometry representation, reduction and original inputs are retained with the job.
Timing uses the resulting SPEF with explicit coupling factor 1.0 and the existing
complete-annotation guard. A pre-fill result cannot satisfy a design that requests
fill. The macro bundle includes a new abstract LEF whose obstructions cover the
added metal, along with the filled GDS and all model evidence.

## Completed reference gate

The [source-bound chunk 4 record](validation/gf180-density-2026-10-09.json)
contains six fresh integrated implementations. Every reference passes strict
device and supply connectivity, logic equivalence and three captured timing
conditions; each deliberate logic mutation fails. The filled abstract LEF covers
every added metal square. Windows and Linux independently reproduce the same
mask/model/export audit, and both installed runtimes pass 34 checks and 18 timing
pairs. The application suite passed 1,657 tests with 62 environment skips.

| Reference | Native main / antenna / density markers | Minimum setup / hold slack (ns) |
|---|---|---|
| c-counter | 0 / 0 / 0 | 44.368145 / 0.293279 |
| c-uart | 0 / 0 / 0 | 0.550356 / 0.508568 |
| c-apb | 0 / 0 / 0 | 8.153233 / 0.313971 |
| d-counter | 0 / 0 / 0 | 44.368137 / 0.293281 |
| d-uart | 0 / 0 / 0 | 0.545770 / 0.508568 |
| d-apb | 0 / 0 / 0 | 8.153145 / 0.313974 |

The permanent archive was read back and every member verified. The failed initial
attempts remain retained, including larger-block command timeouts and the
separately corrected audit-harness checks. Evidence locations and exact hashes
are in the acceptance record.

## Acceptance boundaries

Generation and extraction are distinct from acceptance. Every new design still
needs full layout rules, device/supply connectivity, equivalence and timing.
The pinned native deck is supplemented by written-layout checks because native
zero-marker counts alone do not establish complete dummy-fill coverage.

The chunk-4 reference gate concerns the existing C/D counter, UART and APB blocks
and their original density findings. It uses three captured Liberty conditions
and each stack's typical interconnect model. The independent finite-resistance
comparison and fault controls are described in [post-fill timing](GF180_POSTFILL_TIMING.md).
These establish the bounded model comparison, not field accuracy or general
signal-integrity behavior.

DCF.1a/local COMP interpretation outside the declared core, exclusion-edge
tie/fill rows, complete-chip prime/scribe boundaries, pad/memory geometry, local-density
and process coverage, additional interconnect corners and foundry acceptance
remain explicit requirements in [chunks 7–12](PDK_QUALIFICATION_PLAN.md). The
supplemental checker retains its `checks_passed_coverage_incomplete` result for a
passing subset; this option never turns that result into process qualification.
The separate full transistor-RC experiments retain their actual results and
cannot inherit a passing waveform from static timing or equivalence.
