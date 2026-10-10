"""Keep distributed-node charge while eliminating quasistatic metal fill.

Reducing the original net matrix and then distributing it misses same-net terms.
Restore delta * (diag(w) - w w^T), where delta is the net's Schur diagonal
correction, as positive capacitors between its resistance endpoints. This uses
the original bounded solver; it does not enlarge its dense matrix allocation.
"""
from collections import defaultdict
import math

from icstudio.compact_rc import build
from scripts.ihp_native_capacitance import reduce_capacitors


def prepare(graph, ground, weights, physical_nodes, *, relative_charge_error=1e-5,
            capacitor_only_nodes=(), connected_nodes=None):
    physical = set(physical_nodes)
    if set(weights) != set(graph['nodes']):
        raise ValueError('Original nodes and resistance endpoint groups differ.')
    if weights[ground] != {ground: 1.}:
        raise ValueError('The ideal substrate must retain its singleton anchor.')
    owners = [n for group in weights.values() for n in group]
    if len(owners) != len(set(owners)):
        raise ValueError('Resistance endpoint groups overlap.')
    for name, group in weights.items():
        if name.startswith('FILL') and group != {name: 1.}:
            raise ValueError('Fill elimination requires explicit quasistatic fill nodes.')
    extra = set(capacitor_only_nodes)
    if extra:
        connected = None if connected_nodes is None else set(connected_nodes)
        if connected is None or not connected <= physical:
            raise ValueError('Floating conductor removal needs a complete physical connection inventory.')
        if (not extra <= weights.keys() or ground in extra or
                any(weights[n] != {n: 1.} or n in connected or n.startswith('FILL001_')
                    for n in extra)):
            raise ValueError('Only singleton capacitor-only nodes without devices, resistors or ports may be eliminated.')
    reduced = reduce_capacitors(graph, ground, relative_charge_error=relative_charge_error,
                                additional_floating_nodes=extra)
    retained = set(reduced['ground_af']) | {ground}
    ground_caps = dict(reduced['ground_af'], **{ground: 0.})
    coupling = {(a, b): c for a, b, c in reduced['couplings_af']}
    kept_weights = {name: weights[name] for name in sorted(retained)}
    used = {n for group in kept_weights.values() for n in group}
    if not used <= physical:
        raise ValueError('A resistance endpoint is absent from the physical graph.')
    model = build(ground_caps, coupling, kept_weights, ground,
                  physical_nodes=physical, max_capacitors=50000, max_sources=750000)
    if sum(len(group) * (len(group) - 1) // 2 for group in kept_weights.values()) > 500000:
        raise ValueError('Same-net correction exceeds the explicit capacitor budget.')
    original_diagonal, final_diagonal = defaultdict(list), defaultdict(list)
    for a, b, c in graph['edges_af']:
        original_diagonal[a].append(c)
        original_diagonal[b].append(c)
    for n, c in reduced['ground_af'].items():
        final_diagonal[n].append(c)
    for a, b, c in reduced['couplings_af']:
        final_diagonal[a].append(c)
        final_diagonal[b].append(c)
    correction, diagonal_roundoff = [], []
    for name in sorted(retained - {ground}):
        before = math.fsum(original_diagonal[name])
        after = math.fsum(final_diagonal[name])
        delta = before - after
        if delta < -max(1e-7, before * 1e-12):
            raise ValueError('Metal elimination increased a physical diagonal.')
        if abs(delta) <= max(1e-9, before * 2e-14):
            if delta:
                diagonal_roundoff.append(abs(delta))
            delta = 0.
        delta = max(0., delta)
        group = list(kept_weights[name].items())
        for i, (a, wa) in enumerate(group):
            for b, wb in group[i + 1:]:
                value = delta * wa * wb
                if value:
                    correction.append((a, b, value))
    tail = ''.join(f'CIHP_SCHUR_{i} {a} {b} {c * 1e-18:.17g}\n'
                   for i, (a, b, c) in enumerate(correction))
    return dict(text=model['text'] + tail, compact_text=model['text'],
                corrections_af=correction, reduced=reduced, ground_af=ground_caps,
                coupling_af=coupling, weights=kept_weights,
                capacitor_count=model['capacitors'] + len(correction),
                source_count=model['sources'], qualified=False,
                diagonal_roundoff_count=len(diagonal_roundoff),
                maximum_diagonal_roundoff_af=max(diagonal_roundoff, default=0.),
                scope='Conserved area-weighted lumped C on the captured R graph; '
                      'quasistatic floating metal and verified capacitor-only conductors, '
                      'explicit active junctions and ideal supplies.')
