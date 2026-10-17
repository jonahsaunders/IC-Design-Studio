"""Exact factorization of the existing area-weighted lumped C model.

Native linear controlled sources encode weighted sums on internal nodes. A
one-ohm internal termination converts summed currents to voltage; a unity buffer
isolates every capacitive load. No helper resistor touches a physical node.
Intrinsic ground C terminates at the original substrate anchor, independently
of any distributed resistance on that substrate net.
New sums use differences from their largest-weight input, then restore that
input once. Equal physical voltages therefore produce zero capacitor voltage
without relying on rounded coefficients summing to exactly one.
"""
from collections import Counter
import math
import re

MAX_SOURCES = 250_000
MAX_ALLOWED_SOURCES = 1_000_000
PREFIX = 'STUDIO_RC_INTERNAL_'
ELEMENT_PREFIXES = ('R_STUDIO_SUM_', 'G_STUDIO_SUM_', 'E_STUDIO_BUFFER_',
                    'E_STUDIO_RC_', 'C_STUDIO_RC_')
CURRENT_SUM = 'current-sum-v1'
ANCHORED_CURRENT_SUM = 'anchored-current-sum-v2'
SERIES_VOLTAGE = 'series-voltage-v1'


def source_budget(value=None):
    """Keep the default bound; require an explicit bounded larger allocation."""
    value = MAX_SOURCES if value is None else value
    if type(value) is not int or not 0 < value <= MAX_ALLOWED_SOURCES:
        raise ValueError(f'Compact RC auxiliary-source budget must be 1–{MAX_ALLOWED_SOURCES}.')
    return value


def build(ground, coupling, weights, reference, *, physical_nodes, max_capacitors,
          encoding=ANCHORED_CURRENT_SUM, max_sources=None):
    """Return a bounded SPICE model in farads and its element counts."""
    max_sources = source_budget(max_sources)
    physical = set(physical_nodes)
    if encoding not in (CURRENT_SUM, ANCHORED_CURRENT_SUM, SERIES_VOLTAGE):
        raise ValueError('Unsupported compact RC encoding.')
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
    if encoding in (CURRENT_SUM, ANCHORED_CURRENT_SUM):
        source_count += len(active)  # One output buffer for every U sum.
    if capacitor_count > max_capacitors or source_count > max_sources:
        raise ValueError('Compact RC exceeds the declared capacitor or auxiliary-source budget: '
                         f'requires {capacitor_count} capacitors and {source_count} sources; '
                         f'budgets are {max_capacitors} and {max_sources}.')
    occupied = {n.casefold() for n in physical}; auxiliary = set(); sources = []; caps = []
    current_count = buffer_count = resistor_count = 0
    def fresh(name):
        if name.casefold() in occupied or name in auxiliary:
            raise ValueError('Compact RC auxiliary node collides with a physical or generated node.')
        auxiliary.add(name)
        return name
    averages = {i: PREFIX + 'W' + str(i) for i in active}
    def weighted_sum(output, terms, *, buffered=False):
        nonlocal current_count, buffer_count, resistor_count
        if encoding in (CURRENT_SUM, ANCHORED_CURRENT_SUM):
            current = fresh(PREFIX + 'CURRENT_' + str(resistor_count) if buffered else output)
            sources.append(f'R_STUDIO_SUM_{resistor_count} {current} 0 1')
            resistor_count += 1
            anchor = max(terms, key=lambda term: term[1])[0] if encoding == ANCHORED_CURRENT_SUM else '0'
            for node, gain in terms:
                if not math.isfinite(gain) or gain <= 0:
                    raise ValueError('Invalid compact RC linear-source coefficient.')
                # Keep the small coefficients explicitly. The largest coefficient
                # is implicit in anchor + sum(gain * (input - anchor)).
                negative = '0' if node == anchor else anchor
                coefficient = 1. if node == anchor else gain
                sources.append(f'G_STUDIO_SUM_{current_count} 0 {current} {node} {negative} {coefficient:.17g}')
                current_count += 1
            if buffered:
                sources.append(f'E_STUDIO_BUFFER_{buffer_count} {fresh(output)} 0 {current} 0 1')
                buffer_count += 1
            return
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
        weighted_sum(target, [(averages[j], c / total) for j, c in neighbors.items()], buffered=True)
        for node, weight in group.items():
            value = total * weight * 1e-18
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Compact RC capacitance overflow or underflow.')
            caps.append(f'C_STUDIO_RC_{len(caps)} {node} {target} {value:.17g}')
    return {'text': ''.join(line + '\n' for line in sources + caps), 'capacitors': len(caps),
            'encoding': encoding, 'sources': len(sources) - resistor_count,
            'controlled_current_sources': current_count, 'output_buffers': buffer_count,
            'internal_sum_resistors': resistor_count, 'auxiliary_nodes': len(auxiliary),
            'max_sources': max_sources}


def records(text, physical_nodes, *, max_sources=None):
    """Return helper records and capacitors; reject physical drives and leakage.

    Current sums have exactly two layers: physical-node averages, then buffered
    sums of those averages. Each layer may use an affine anchor from its own
    inputs, restored by exactly one unit-gain current. Only buffer outputs may
    carry capacitive loads; neither layer may drive a physical node.
    Retain the original series-source grammar for authenticated older exports.
    """
    max_sources = source_budget(max_sources)
    tokens = [line.split() for line in text.splitlines()]
    if sum(bool(t) and t[0].startswith(('G', 'E')) for t in tokens) > max_sources:
        raise ValueError('Compact RC exceeds the declared auxiliary-source budget.')
    if not tokens or all(t and t[0].startswith(('E_STUDIO_RC_', 'C_STUDIO_RC_')) for t in tokens):
        return _series_records(text, physical_nodes)
    physical = set(physical_nodes)
    folded = {n.casefold() for n in physical} | {'0'}
    names = set(); helpers = []; caps = []; sums = {}; buffers = {}
    current = None; terminated = False; buffered = False
    def fresh(node):
        if not node.startswith(PREFIX) or node.casefold() in folded:
            raise ValueError('Compact RC helper collides with a physical node or another helper.')
        folded.add(node.casefold())
    def finish():
        if current is not None and not sums[current]:
            raise ValueError('Compact RC sum has no controlled currents.')
    for t in tokens:
        if not t or t[0].casefold() in names:
            raise ValueError('Empty or duplicate compact RC record.')
        names.add(t[0].casefold())
        if re.fullmatch(r'R_STUDIO_SUM_\d+', t[0]) and len(t) == 4 and not terminated:
            finish()
            if t[2] != '0' or float(t[3]) != 1.:
                raise ValueError('Compact RC sum requires one internal one-ohm termination.')
            fresh(t[1]); current = t[1]; sums[current] = []; buffered = False
        elif re.fullmatch(r'G_STUDIO_SUM_\d+', t[0]) and len(t) == 6 and not terminated:
            gain = float(t[5])
            if (current is None or buffered or t[1] != '0' or t[2] != current or
                    (t[4] != '0' and t[4] not in physical and t[4] not in sums) or t[4] == current or
                    t[3] == current or (t[3] not in physical and t[3] not in sums) or
                    not math.isfinite(gain) or gain <= 0):
                raise ValueError('Compact RC current source changes a physical node or has an invalid dependency/gain.')
            sums[current].append(t)
        elif re.fullmatch(r'E_STUDIO_BUFFER_\d+', t[0]) and len(t) == 6 and not terminated:
            finish()
            if current is None or buffered or t[2:5] != ['0', current, '0'] or float(t[5]) != 1.:
                raise ValueError('Compact RC load requires an isolated unity output buffer.')
            fresh(t[1]); buffers[t[1]] = current; buffered = True
        elif re.fullmatch(r'C_STUDIO_RC_\d+', t[0]) and len(t) == 4:
            finish(); terminated = True
            value = float(t[3])
            if t[1] not in physical or t[2] not in buffers or not math.isfinite(value) or value <= 0:
                raise ValueError('Compact RC capacitor must join a physical node to a buffered output.')
            caps.append(t); continue
        else:
            raise ValueError('Unsupported compact RC element or ordering.')
        helpers.append(t)
    finish()
    buffered_sums = set(buffers.values()); averages = sums.keys() - buffered_sums
    for node, terms in sums.items():
        inputs = averages if node in buffered_sums else physical
        anchors = {t[4] for t in terms if t[4] != '0'}
        if (any(t[3] not in inputs for t in terms) or not anchors <= inputs or
                len(anchors) > 1):
            raise ValueError('Compact RC sum has an invalid affine anchor or dependency.')
        if anchors:
            anchor = next(iter(anchors))
            returns = [t for t in terms if t[4] == '0']
            if len(returns) != 1 or returns[0][3] != anchor or float(returns[0][5]) != 1.:
                raise ValueError('Compact RC affine anchor must be restored exactly once at unit gain.')
    consumed = {n for node in buffered_sums for t in sums[node] for n in t[3:5] if n != '0'}
    if (consumed != averages or {t[2] for t in caps} != buffers.keys() or
            any(t[3] not in physical for node in averages for t in sums[node]) or
            any(t[3] not in averages for node in buffered_sums for t in sums[node])):
        raise ValueError('Compact RC helpers must form unloaded averages and buffered neighbor sums.')
    return helpers, caps


def _series_records(text, physical_nodes):
    """Read the legacy series-voltage encoding without authorizing other drives."""
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


def audit(text, owner, ground, coupling, reference, *, max_sources=None):
    """Independently contract serialized helper equations and C stamps to net C.

    Release intermediate symbolic vectors when their final consumer executes;
    otherwise long sums over supply nets would use quadratic storage.
    """
    sources, caps = records(text, owner, max_sources=max_sources)
    current_sum = any(t[0].startswith('R_STUDIO_SUM_') for t in sources)
    uses = (Counter(n for t in sources if t[0].startswith(('G', 'E')) for n in t[3:5]) if current_sum
            else Counter(n for t in sources for n in t[2:4]))
    uses.update(t[2] for t in caps)
    functions = {'0': {}}
    functions.update({n: {net: 1.} for n, net in owner.items()})
    pending = {}
    def resolve(node):
        if node in pending:
            functions[node] = {n: math.fsum(values) for n, values in pending.pop(node).items()}
        return functions[node]
    def consume(node):
        uses[node] -= 1
        if uses[node] == 0 and node not in owner and node != '0':
            functions.pop(node)
    for t in sources:
        if t[0].startswith('R_STUDIO_SUM_'):
            functions[t[1]] = {}; pending[t[1]] = {}
            continue
        _, pos, neg, control, control_negative, raw = t
        if current_sum:
            if t[0].startswith('G'):
                vector = pending[neg]
                positive = resolve(control); negative = resolve(control_negative)
                for n in positive.keys() | negative.keys():
                    coefficient = positive.get(n, 0.) - negative.get(n, 0.)
                    if coefficient:
                        vector.setdefault(n, []).append(coefficient * float(raw))
            else:
                functions[pos] = dict(resolve(control))
            consume(control); consume(control_negative)
            continue
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
