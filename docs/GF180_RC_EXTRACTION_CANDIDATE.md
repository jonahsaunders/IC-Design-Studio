# GF180 post-fill resistance extraction candidate

This is chunk 4 diagnostic work. Neither this engine candidate nor the compact
capacitance experiment qualifies final-layout timing, a process, or tapeout.
The default installed engine and its historical acceptance scopes are unchanged.

The [candidate source lock](../examples/gf180-fill-rc-engine-lock.json) pins Magic
8.3.684 and a hash-checked [patch](../packaging/physical/magic-gf180-fill-rc.patch).
It retains the earlier GF180 cross-plane device and undriven-conductor repairs,
and places device connections at the actual overlap with the conductor tile.
Using the whole device center can put a connection outside a smaller tile,
producing negative tile area and a negative capacitance redistribution weight.
The correction changes connection geometry; it does not clamp negative weights.

Build this explicit candidate in a new directory with:

```sh
python scripts/build_physical_engines.py --output /tmp/gf180-fill-rc --lock examples/gf180-fill-rc-engine-lock.json --only magic
```

The matched counter experiments preserve original capacitance records, all
4,184 device records and eight ports. Every network is extracted: 4,058 before
fill and 4,969 after fill. Both runs have no negative resistance-node weights.
Eighteen pinned foundry-cell controls preserve their device inventories. These
checks do not establish general extraction accuracy or full PDK device coverage.

## Compact coupling experiment

The application's original area-weighted model expands each original mutual
capacitance across every pair of endpoint resistance nodes. On this counter,
that would require roughly 142 million components. The existing size guard
continues to reject this expansion.

A factorized model can retain the same endpoint equations. For original net
`a`, define its weighted potential `W_a = sum_i(w_ai V_ai)`, total mutual
capacitance `D_a = sum_b(C_ab)`, and buffered neighbor potential
`U_a = sum_b(C_ab W_b) / D_a`. A capacitor `D_a w_ai` from each physical
endpoint to `U_a` gives the same endpoint current as the expanded network.
The initial implementation uses linear voltage-source chains for the weighted
sums. The current implementation uses controlled-current sums with buffered
outputs, described below. Their auxiliary nodes are internal mathematical
variables, not new circuit ports or drivers.

The [native qualification runner](../scripts/qualify_compact_rc_coupling.py)
compares every endpoint's frequency response with an independently constructed
full matrix, checks transient behavior with a floating conductor pair, and
requires detection of an intentionally corrupted coefficient:

```sh
python scripts/qualify_compact_rc_coupling.py --out /tmp/compact-coupling --ngspice /path/to/ngspice
```

The initial polynomial-source implementation failed transient convergence and
is retained as failed evidence. Native linear sources pass the same limits.
This preserves the existing lumped approximation; it adds no spatial field
accuracy. The initial experiment left production export, internal-node validation,
topology contraction and floating-network handling for the integration below.
Actual post-fill circuit timing remains unqualified. No production capacitance
threshold or size guard is relaxed.

The complete counter mutual-capacitance operators also pass four independent
all-node algebraic action and energy comparisons. Native KLU simulations of
both operators agree with the pairwise reference at 33 selected endpoints and
four frequencies from 1 MHz through 1 GHz. These voltage-imposed operator
checks establish representation agreement, not circuit timing. An initial
linear sweep returned incomplete frequency coverage and was rejected; the
successful decade sweep explicitly verifies every requested frequency.

| Counter | Physical R nodes | Expanded mutual capacitors | Compact mutual capacitors | Auxiliary linear sources |
|---|---:|---:|---:|---:|
| Before fill | 37,520 | 137,599,390 | 24,458 | 65,230 |
| Filled | 39,343 | 141,872,298 | 26,280 | 74,216 |

These counts exclude intrinsic ground capacitance, which the factorization
does not change. The full-size experiments use the previously recorded copies
that normalize six negligible negative mutual-capacitance roundoff residues.
Original raw files remain retained, and production parsing still rejects them.

The [candidate evidence record](validation/gf180-rc-extraction-candidate-2026-10-07.json)
retains source identities, native results, failures and remaining gates.

## Production export integration

The [compact model](../icstudio/compact_rc.py) now connects to the application's
normalization, final export, topology comparison and island checks. Small models
retain the expanded representation. Models that exceed its budget use the exact
factorization if both the original capacitor budget and a separate 250,000-source
budget permit it; otherwise normalization fails before replacing its inputs.

Intrinsic ground capacitance joins the same representation through an additional
singleton group at the original substrate anchor. This preserves its actual
return path even when the substrate net also has distributed resistance.
Explicit mutual capacitance to that net still uses its original area weights.
Both meanings are checked independently on a distributed-substrate fixture.

The finalizer rebuilds ownership and weights from retained raw extraction and
requires the serialized model to match. It independently checks the complete
capacitance matrix, physical resistor edges and values, device parameters and
port order. Source equations may sense physical nodes but drive only generated
internal nodes. Contraction and island analysis authorize only the exact model
bound to the finalized export. Changed gains, metadata, physical connections,
node collisions and over-budget models are rejected.

| Counter | Total generated capacitors | Auxiliary linear sources | Preserved resistors | Preserved devices |
|---|---:|---:|---:|---:|
| Before fill | 24,459 | 73,337 | 46,757 | 4,184 |
| Filled | 26,281 | 84,145 | 47,668 | 4,184 |

These counts include intrinsic ground capacitance and stay below the unchanged
50,000-capacitor default. Native exports preserve every device parameter and all
eight ports. Contracting wire resistance reproduces the same device-reference
netlist in both cases. Island analysis removes no resistors or coupling; the
911 floating fill conductors remain in the full finite-resistance network.
The separate equipotential floating-capacitance reducer keeps its existing limit.

The native small-circuit runner now exercises the production generator alongside
the independent expanded and compact implementations. Each passes all seven
frequency-basis drives, and the deliberately corrupted coefficient is detected.
The production transient agrees with the expanded model within the predeclared
2 microvolt limit, including a floating pair with zero initial charge and no
artificial leakage. This does not establish full-counter transient behavior.

A separate nominal device-reference control also passes reset, counting and
rollover over eighteen clock edges. Its 50 ns period and 10 fF output loads come
from the retained implementation input, whose die and core remain unchanged.
The fixture fixes a 5 V supply, 25 C temperature and zero-charge startup before
execution. This device-only control establishes the functional reference for
the next comparison; it does not include extracted interconnect or fill coupling.

The initial [integration evidence](validation/gf180-compact-export-2026-10-07.json)
binds that source, native results and regression suite. Those historical exports
use audited copies that normalize six minute negative-capacitance roundoff
residues. The later [shielding candidates](validation/gf180-shielding-fill-candidate-2026-10-08.json)
correct the native cause and export untouched inputs. Production parsing remains
strict; no roundoff allowance was introduced.

## Buffered current-sum integration

The series-source model made the full counter transient impractically slow.
The application now encodes each weighted sum with positive controlled currents
entering an internal node terminated by one ohm. A unity voltage buffer separates
every capacitive load from that termination. All physical-node currents still
come from the original capacitors; helper resistors connect only internal nodes
to the mathematical reference. This changes the encoding, not the lumped model,
physical resistance graph, initial charge or circuit specification.

The parser requires exactly two layers: unloaded physical-node averages and
buffered neighbor sums. It rejects external drives, physical helper connections,
cycles, unbuffered capacitive loads, missing or altered terminations/buffers,
duplicate names and unsupported elements. The 250,000-source limit includes the
output buffers. The finalizer rebuilds the exact model from raw records and
checks its serialized capacitance matrix. Island analysis preserves authenticated
internal terminations without treating them as physical ground connections.
Authenticated historical series-source exports remain readable.

The [current-sum evidence](validation/gf180-current-sum-integration-2026-10-08.json)
records native SPARSE and KLU checks against an independent expanded matrix.
Each solver passes all seven frequency-basis drives for all three positive
representations. Both detect corrupted series and current-source gains and an
injected physical leakage resistor. The floating-pair production transient
differs from the expanded reference by less than 0.94 microvolt, within the fixed
2 microvolt limit.

| Counter | Capacitors | Controlled currents | Output buffers | Internal one-ohm terminations | Physical resistors |
|---|---:|---:|---:|---:|---:|
| Before fill | 24,459 | 72,963 | 4,058 | 8,116 | 46,757 |
| Filled | 26,281 | 83,771 | 4,969 | 9,938 | 47,668 |

Retained untouched extraction inputs from both shielding candidates regenerate
on Windows and Linux. Their capacitor/helper text matches the tested prototype
exactly; all other finalized circuit lines are unchanged. Each export retains
4,184 devices, eight ports and every physical resistor, including the floating
fill network. These checks establish export preservation, not complete-chip
behavior. The full-counter transient, post-fill timing, complete fill rules,
native extraction repeatability and C/D production workload acceptance remain
open.

## Capacitance distribution precision candidate

The [precision candidate lock](../examples/gf180-cap-precision-engine-lock.json)
extends the rectangular-shield candidate with double-precision capacitance
accumulation, transfer to the resistance extractor, and total-area arithmetic.
Individual distributed node values retain their existing float storage. The
default engine and installed application runtime are unchanged.

The previous extractor accumulated the same coupling terms in different orders
into float totals. It also summed the areas of large supply networks in float
precision. Repeated full-counter extractions preserved the capacitance inputs
and resistance graphs but produced different printed capacitance weights.

The [native arithmetic runner](../scripts/qualify_magic_capacitance_arithmetic.py)
calls the actual capacitor reader and distribution function in isolated copies
with a private test command. Four input orders, three scales and both parser
modes produce 24 cases. The candidate passes all 24; the earlier engine passes
six. The fixed limits are 1e-12 relative error for the accumulated total and
8e-8 for final float node values, checked against independently summed inputs.
Candidate outputs are identical across the tested orders.

Two independent full extractions per geometry and a third extraction from a
fresh source-lock build match every printed capacitance weight after a unique
node-graph bijection. This covers 37,513 before-fill and 39,335 filled nodes.
The previous raw capacitance records, physical resistor values/connections,
4,184 devices and eight ports remain preserved. Deliberately changing one
printed weight is detected in each geometry. Production exports pass on Linux;
Windows reproduces all seven checked artifacts byte for byte for each geometry.

The [precision evidence](validation/gf180-capacitance-precision-2026-10-08.json)
retains the earlier diagnostic mapping errors and the original differing
extractions. These results establish repeatability for the recorded references,
not general field accuracy or post-fill timing. The full-circuit simulations
started before this candidate retain their earlier source circuit identities.
Timing, complete fill rules, polygon/corner coverage and production C/D workload
acceptance remain open.

## Full-counter startup diagnostics

The [exclusion and simulator checkpoint](validation/gf180-exclusion-controls-2026-10-08.json)
retains a failed filled-circuit transient on the earlier frozen current-sum
export. After about 3,617 elapsed seconds, ngspice reports a timestep-too-small
error at 2 ps, naming `xdut.vdd.n5401`. Its process exit code is zero; the
functional checker rejects the numerical error and does not claim a pass.
The unfilled case has its own process and acceptance state.

Read-only instruction and register samples were taken from both then-running
processes, with immediate detachment and no register or circuit changes.
Official debug data matches the installed binary's ELF build identity. The
sampled hot loop resolves to `klu_refactor`, with one sample in the solve
routine. Sixteen floating-point samples per process show no subnormal operands
or products in the inspected multiplication; this limited sample does not
explain the convergence failure.

Separate KLU and SPARSE diagnostics use the complete newer precision-candidate
filled circuit, original 900 ns transient command, models and numerical limits,
with an observation stop at 100 ps. Both hit the fixed 240-second CPU soft limit
without producing a waveform at that observation point. Changing the solver
alone therefore has not resolved startup within that diagnostic bound. These
failed controls do not relax the original full-run acceptance requirements.

Historical `ngspice_sha256` fields in these early full-run records identify the
`/opt/icstudio/bin/ngspice` launcher. New diagnostics separately record that
launcher and the actual `/usr/bin/ngspice` binary from package
`42+ds-3build1`; the original records remain unchanged.

## Matrix-ordering diagnostic candidate

The [ordering source lock](../examples/ngspice-ordering-diagnostic-lock.json)
pins an isolated ngspice 42 build with a private AMD/COLAMD selector. Its patch
changes the matrix ordering and logs its choice and matrix dimensions. It does
not change pivot thresholds, circuit components or numerical tolerances. The
installed engine and application default remain unchanged. The tested build
disables the optional predictor, as the installed Ubuntu package does; the
initial predictor-enabled build is retained but was not used for the comparison.
This is not a byte-identical rebuild of the installed package.

The [simulator investigation](validation/gf180-simulator-ordering-2026-10-08.json)
retains two rejected alternatives. A current-return representation exceeds the
50,000-capacitor guard on the filled circuit (55,025 capacitors). Both solvers
also fail its existing AC absolute limit at mathematically zero entries because
of cancellation residues, despite passing the small floating transient. Those
limits remain unchanged. An explicit 60,000-capacitor diagnostic allowance did
not establish startup within the CPU bound; it is not a production limit change.
Exact power-of-two scaling of the existing sum rows preserves all other circuit
lines and passes the small controls on both solvers, but neither tested scaling
reaches the full-circuit startup observation point within the same CPU bound.

On the isolated ordering build, AMD and COLAMD each pass the production RC
controls (45 native analyses including injected gain/leakage faults) and the
frozen device-only counter's 18 functional samples. The complete filled RC
circuit is then identical between ordering trials: 59,213 matrix unknowns and
351,024 original nonzero entries. COLAMD reaches 103.715 ps in about 30 seconds
elapsed; AMD exhausts its 240-second CPU soft limit with a last reported time
of 7.011 ps. The successful startup trial retains 32 waveform rows. Its statistics
report 4,498,428 additional matrix entries, 70 iterations and 21.592 seconds of
factorization time; startup speed does not establish full-circuit correctness.

Full before/filled 900 ns comparisons have started on the same COLAMD build,
using the precision-candidate exports and unchanged stimulus, models, physical
and floating nodes, numerical limits and original component budgets. Each run
has a six-hour CPU limit and separate 48-hour wall guard. Their own complete
waveforms and functional checks, followed by post-fill timing, production
integration and platform qualification, are required before acceptance.
