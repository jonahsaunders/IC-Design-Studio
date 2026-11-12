"""Prove invariant native cell capacitance, including floating-poly paths.

Unchanged capacitors directly touching device terminals are insufficient: an
unused poly conductor can couple a device to new fill through other unused
conductors. Protect each complete floating component touching an internal
terminal and compare every incident capacitor exactly before any reduction.
The caller must independently establish the device and floating-node inventory.
This checks an extraction graph, not field accuracy or Liberty characterization.
"""
from collections import defaultdict
import math

# Match the existing native overlap-subtraction bounds in raw_capacitors.
# Keep these residues in the model; this audit only records their uncertainty.
NATIVE_RESIDUE_AF = 1e-10
TOTAL_NATIVE_RESIDUE_AF = 1e-7


def _inventory(graph):
    nodes = set(graph['nodes'])
    if len(nodes) != len(graph['nodes']) or graph['ground'] not in nodes:
        raise ValueError('Invalid native node inventory.')
    values = defaultdict(list)
    neighbors = defaultdict(set)
    for a, b, c in graph['edges_af']:
        if (a not in nodes or b not in nodes or a == b or
                not math.isfinite(c) or c <= 0):
            raise ValueError('Invalid native capacitor.')
        values[tuple(sorted((a, b)))].append(c)
        neighbors[a].add(b)
        neighbors[b].add(a)
    return {pair: math.fsum(v) for pair, v in values.items()}, neighbors


def protected_floating(graph, internal, floating):
    """Return floating components connected capacitively to internal terminals."""
    _, neighbors = _inventory(graph)
    internal, floating = set(internal), set(floating)
    nodes = set(graph['nodes'])
    if (not internal or not internal <= nodes or not floating <= nodes or
            internal & floating or graph['ground'] in internal | floating):
        raise ValueError('Invalid internal or independently verified floating-node inventory.')
    pending = list(set().union(*(neighbors[n] for n in internal)) & floating)
    protected = set()
    while pending:
        node = pending.pop()
        if node in protected:
            continue
        protected.add(node)
        pending.extend((neighbors[node] & floating) - protected)
    return protected


def compare(before, after, internal, floating):
    """Compare the subnetwork sufficient to preserve internal Schur rows.

    With identical incident capacitors and floating components, eliminating
    floating conductors leaves identical internal-terminal rows algebraically.
    Only sub-1e-10 aF overlap-subtraction residues may differ, with the existing
    cumulative 1e-7 aF bound. Both endpoints of a comparison must be residues;
    this is not a relative tolerance on ordinary physical capacitors.
    """
    internal, floating = set(internal), set(floating)
    if before['ground'] != after['ground']:
        raise ValueError('The substrate reference changed.')
    protected = set(internal) | protected_floating(before, internal, floating)
    if not protected <= set(after['nodes']):
        raise ValueError('A protected circuit conductor disappeared.')
    left, _ = _inventory(before)
    right, _ = _inventory(after)
    relevant = lambda pairs: {p: v for p, v in pairs.items() if set(p) & protected}
    left, right = relevant(left), relevant(right)
    changed = sorted(p for p in left.keys() | right.keys() if left.get(p, 0.) != right.get(p, 0.))
    residues = [dict(nodes=p, before_af=left.get(p, 0.), after_af=right.get(p, 0.))
                for p in changed if max(left.get(p, 0.), right.get(p, 0.)) < NATIVE_RESIDUE_AF]
    meaningful = [p for p in changed if max(left.get(p, 0.), right.get(p, 0.)) >= NATIVE_RESIDUE_AF]
    residual_total = math.fsum(abs(r['after_af']-r['before_af']) for r in residues)
    if meaningful or residual_total > TOTAL_NATIVE_RESIDUE_AF:
        raise ValueError(f'Cell environment changed at {len(changed)} capacitor pairs; first: {changed[0]}.')
    return dict(schema=1, status='cell-capacitance-subnetwork-preserved' if residues else 'cell-capacitance-subnetwork-identical', qualified=False,
                internal_nodes=len(set(internal)), protected_floating_nodes=len(protected-set(internal)),
                compared_pairs=len(left.keys() | right.keys()),
                maximum_raw_change_af=max((abs(left.get(p, 0.)-right.get(p, 0.)) for p in changed), default=0.),
                native_overlap_residues=residues, total_native_residue_change_af=residual_total,
                native_residue_limit_af=NATIVE_RESIDUE_AF, total_native_residue_limit_af=TOTAL_NATIVE_RESIDUE_AF,
                scope='Native internal/floating-component capacitance invariance within explicitly recorded overlap-subtraction residue bounds. Capacitors are not removed from the physical model. Independent field accuracy, spatial wire distribution and timing remain separate checks.')
