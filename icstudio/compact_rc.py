"""Exact factorization of the existing area-weighted lumped C model.

Only native linear E sources and positive capacitors are emitted. Their internal
voltages encode weighted sums; they never replace physical ports or R nodes.
Intrinsic ground C terminates at the original substrate anchor, independently
of any distributed resistance on that substrate net.
"""
from collections import Counter
import math

MAX_SOURCES = 250_000
PREFIX = 'STUDIO_RC_INTERNAL_'


def build(ground, coupling, weights, reference, *, physical_nodes, max_capacitors):
    """Return a bounded SPICE model in farads and its element counts."""
    physical = set(physical_nodes)
    if '0' in physical or reference not in physical:
        raise ValueError('Compact RC needs a named substrate anchor distinct from SPICE ground.')
    if set(ground) != set(weights) or ground.get(reference) != 0:
        raise ValueError('Compact RC ground and weight inventories disagree.')
    groups = [dict(weights[n]) for n in weights]
    indices = {n: i for i, n in enumerate(weights)}
    for group in groups:
        if (not group or not group.keys() <= physical or
                any(not math.isfinite(w) or w <= 0 for w in group.values()) or
                not math.isclose(math.fsum(group.values()), 1., rel_tol=0., abs_tol=1e-12)):
            raise ValueError('Compact RC requires positive normalized endpoint weights.')
    # This singleton is intentional: ground C returns to the actual reference
    # anchor, whereas explicit mutual C uses the reference net's area weights.
    anchor = len(groups); groups.append({reference: 1.})
    adjacency = {i: {} for i in range(len(groups))}
    def connect(a, b, value):
        if not math.isfinite(value) or value < 0 or a == b:
            raise ValueError('Invalid compact RC coupling.')
        if value:
            adjacency[a][b] = adjacency[a].get(b, 0.) + value
            adjacency[b][a] = adjacency[b].get(a, 0.) + value
    for (a, b), value in coupling.items():
        if a not in indices or b not in indices:
            raise ValueError('Unknown compact RC coupling endpoint.')
        connect(indices[a], indices[b], value)
    for n, value in ground.items():
        connect(indices[n], anchor, value)
    active = {i: group for i, group in enumerate(groups) if adjacency[i]}
    capacitor_count = sum(len(g) for g in active.values())
    source_count = capacitor_count + sum(len(adjacency[i]) for i in active)
    if capacitor_count > max_capacitors or source_count > MAX_SOURCES:
        raise ValueError('Compact RC exceeds the declared capacitor or auxiliary-source budget.')
    occupied = {n.casefold() for n in physical}; auxiliary = set(); sources = []; caps = []
    def fresh(name):
        if name.casefold() in occupied or name in auxiliary:
            raise ValueError('Compact RC auxiliary node collides with a physical or generated node.')
        auxiliary.add(name)
        return name
    averages = {i: PREFIX + 'W' + str(i) for i in active}
    def weighted_sum(output, terms):
        previous = '0'
        for j, (node, gain) in enumerate(terms):
            current = fresh(output if j == len(terms) - 1 else output + '_' + str(j))
            if not math.isfinite(gain) or gain <= 0:
                raise ValueError('Invalid compact RC linear-source coefficient.')
            sources.append(f'E_STUDIO_RC_{len(sources)} {current} {previous} {node} 0 {gain:.17g}')
            previous = current
    for i, group in active.items():
        weighted_sum(averages[i], list(group.items()))
    for i, group in active.items():
        neighbors = adjacency[i]; total = math.fsum(neighbors.values())
        if not math.isfinite(total) or total <= 0:
            raise ValueError('Invalid compact RC total capacitance.')
        target = PREFIX + 'U' + str(i)
        weighted_sum(target, [(averages[j], c / total) for j, c in neighbors.items()])
        for node, weight in group.items():
            value = total * weight * 1e-18
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Compact RC capacitance overflow or underflow.')
            caps.append(f'C_STUDIO_RC_{len(caps)} {node} {target} {value:.17g}')
    return {'text': ''.join(line + '\n' for line in sources + caps), 'capacitors': len(caps),
            'sources': len(sources), 'auxiliary_nodes': len(auxiliary),
            'max_sources': MAX_SOURCES}


def records(text, physical_nodes):
    """Parse the narrow generated grammar, rejecting all external drives."""
    physical = set(physical_nodes); defined = {'0', *physical}; folded = {n.casefold() for n in defined}
    names = set(); auxiliary = set(); sources = []; caps = []
    for line in text.splitlines():
        t = line.split()
        if not t or t[0].casefold() in names:
            raise ValueError('Empty or duplicate compact RC record.')
        names.add(t[0].casefold())
        if t[0].startswith('E_STUDIO_RC_') and len(t) == 6:
            _, pos, neg, control, zero, raw = t
            if (not pos.startswith(PREFIX) or pos.casefold() in folded or
                    (neg != '0' and neg not in auxiliary) or control not in defined or zero != '0'):
                raise ValueError('Compact RC source changes a physical node or has an undefined dependency.')
            gain = float(raw)
            if not math.isfinite(gain) or gain <= 0:
                raise ValueError('Invalid compact RC source gain.')
            defined.add(pos); folded.add(pos.casefold()); auxiliary.add(pos); sources.append(t)
        elif t[0].startswith('C_STUDIO_RC_') and len(t) == 4:
            value = float(t[3])
            if t[1] not in physical or t[2] not in auxiliary or not math.isfinite(value) or value <= 0:
                raise ValueError('Invalid compact RC capacitor endpoint or value.')
            caps.append(t)
        else:
            raise ValueError('Unsupported compact RC element.')
    return sources, caps


def audit(text, owner, ground, coupling, reference):
    """Independently contract serialized E equations and C stamps to net C.

    Release intermediate symbolic vectors when their final consumer executes;
    otherwise long sums over supply nets would use quadratic storage.
    """
    sources, caps = records(text, owner)
    uses = Counter(n for t in sources for n in t[2:4])
    uses.update(t[2] for t in caps)
    functions = {'0': {}}
    functions.update({n: {net: 1.} for n, net in owner.items()})
    def consume(node):
        uses[node] -= 1
        if uses[node] == 0 and node not in owner and node != '0':
            functions.pop(node)
    for _, pos, neg, control, _, raw in sources:
        vector = dict(functions[neg]); gain = float(raw)
        for n, coefficient in functions[control].items():
            vector[n] = vector.get(n, 0.) + coefficient * gain
        functions[pos] = vector
        consume(neg); consume(control)
    # Sum equal contracted capacitor endpoints before expanding coefficients.
    grouped = {}
    for _, pos, neg, raw in caps:
        grouped.setdefault((owner[pos], neg), []).append(float(raw) * 1e18)
    observed = {}
    for (net, target), values in grouped.items():
        value = math.fsum(values)
        observed[(net, net)] = observed.get((net, net), 0.) + value
        for other, gain in functions[target].items():
            observed[(net, other)] = observed.get((net, other), 0.) - value * gain
    expected = {}
    def edge(a, b, value):
        for key, sign in (((a, a), 1.), ((b, b), 1.), ((a, b), -1.), ((b, a), -1.)):
            expected.setdefault(key, []).append(value * sign)
    for (a, b), value in coupling.items():
        edge(a, b, value)
    for n, value in ground.items():
        if value:
            edge(n, reference, value)
    expected = {k: math.fsum(v) for k, v in expected.items()}
    keys = expected.keys() | observed.keys()
    if any(not math.isclose(expected.get(k, 0.), observed.get(k, 0.), rel_tol=1e-12, abs_tol=1e-12) for k in keys):
        raise ValueError('Serialized compact RC model does not conserve the original capacitance matrix.')
    return {'status': 'passed', 'method': 'independent-serialized-linear-equations-and-capacitor-stamps',
            'matrix_entries': len(keys), 'maximum_error_af': max((abs(expected.get(k, 0.) - observed.get(k, 0.)) for k in keys), default=0.),
            'relative_tolerance': 1e-12, 'absolute_tolerance_af': 1e-12}
