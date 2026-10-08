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
Native linear voltage sources implement the weighted sums. Their auxiliary
nodes are internal mathematical variables, not new circuit ports or drivers.

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

The [integration evidence](validation/gf180-compact-export-2026-10-07.json)
binds the source, native results and regression suite. Full-counter exports still
use the earlier audited copies that normalize six minute negative-capacitance
roundoff residues. Production parsing of the original raw files remains strict.
A bounded roundoff policy, actual post-fill timing, complete fill-rule coverage
and production C/D workload acceptance on both operating systems remain open.
