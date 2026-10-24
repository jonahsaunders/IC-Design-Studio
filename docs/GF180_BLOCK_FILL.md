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

## Completed six-reference density gate

The [complete chunk 4 record](validation/gf180-fill-closure-2026-10-09.json)
binds six integrated implementations to native and manual-rule acceptance.
Its [native evidence](validation/gf180-density-2026-10-09.json) shows that every reference passes strict
device and supply connectivity, logic equivalence and three captured timing
conditions; each deliberate logic mutation fails. The filled abstract LEF covers
every added metal square. Windows and Linux independently reproduce the same
mask/model/export audit, and both installed runtimes pass 34 checks and 18 timing
pairs. The final application suite passed: 1,680 tests run with 62 environment
skips. All 57 focused closure tests also passed on both Windows and Linux.

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

The existing passing reference evidence concerns the existing C/D counter, UART and APB blocks
and their original density findings. It uses three captured Liberty conditions
and each stack's typical interconnect model. The independent finite-resistance
comparison and fault controls are described in [post-fill timing](GF180_POSTFILL_TIMING.md).
These establish the bounded model comparison, not field accuracy or general
signal-integrity behavior.

The selected reference floorplan keeps the original die/core and places 40 µm
streets immediately outside all four die edges. The stricter main-table DCF.7a
clearance of 26 µm excludes margin COMP candidates. A conservative continuous
origin-space proof finds no legal 5 µm COMP square in the remaining interior.
It covers the entire original footprint without sampling or reducing density
denominators. All six references pass 108 supplemental checks. Six native-clean
trial COMP additions fail DCF.7a and remain separate negative controls.

The [pinned manual's metal-fill procedure](https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_13_3.html)
specifies 200 µm windows stepped by 100 µm and a total-die fill threshold.
Every full window is measured; additional clipped windows keep their actual
denominators. The cited procedure supplies no separate numeric local-window
limit, so none is invented or claimed passed. Foundry-specific local acceptance
and complete-chip/reticle approval remain unqualified.

The supplemental checker alone still reports
`checks_passed_coverage_incomplete`: native layout checks, connectivity and
electrical acceptance must come from independently bound records. The closure
validator combines them for these exact six references. It cannot promote a
native-only report, changed source, missing window or untested boundary to a pass.
The separate full transistor-RC experiments retain their unfinished status;
their waveform acceptance is not inferred from digital equivalence or timing.

## Conditional rules and complete drawing-site enumeration

The supplemental checker now reports applicability from the actual recursively
merged GDS operands. DCF.8b, DCF.11b and the DCF.13 row requirement activate for
the relevant rectangular marker when both dimensions exceed 80 µm. Merged
markers cannot evade this threshold; nonrectangular markers remain unqualified.
Absence of a marker is recorded explicitly. The same report distinguishes
absent unsupported vendor-memory layers, absent pad operands and absent dummy
COMP/poly from unchecked geometry. Absence does not waive missing fill.

The whole-footprint COMP audit enumerates every site of a declared staggered
array, including the margins. It uses the written circuit, poly, well boundaries
and exclusion masks with the manual's Euclidean clearances. It reports exact
missing-square locations; nearby or truncated dummy polygons cannot satisfy
them. Fixed footprint and density denominators remain unchanged.

For the six current exports, the relevant exclusion and vendor-memory markers
are absent. The trial COMP array has 150 unblocked sites per counter and 312
per UART/APB. These are candidate sites under circuit/well
clearances alone. Every candidate is prohibited by the declared reference
scribe boundary, and the trial additions correctly fail that boundary rule.
The audit deliberately keeps boundary and electrical acceptance separate.
The [retained coverage evidence](validation/gf180-fill-coverage-2026-10-09.json)
records matching Windows/Linux results and separate trial-layout checks.
