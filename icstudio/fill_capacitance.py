"""Eliminate bounded equipotential floating fill from an extracted C matrix.

No process coefficients are invented. The input is the extraction engine's
ground and mutual capacitance in farads. The zero-charge Schur complement
retains fill-to-fill paths and shielding already present in that matrix. It
does not model finite fill resistance, initial trapped charge or unextracted
long-range fields, and is not a foundry signoff extractor.
"""
from __future__ import annotations

import math
import hashlib
from pathlib import Path

def reduce_floating(ground, coupling, floating, *, max_component=256):
    """Return retained ground/mutual C after exact linear floating-node removal.

    ``coupling`` maps two-node tuples to nonnegative farads. Disconnected fill
    components cannot affect retained nodes and are recorded without solving.
    Connected components larger than the declared numerical budget fail closed.
    """
    if type(max_component) is not int or not 1 <= max_component <= 256:
        raise ValueError('Use a floating-fill component budget from 1 to 256.')
    if not isinstance(ground, dict) or not ground or not isinstance(coupling, dict) or len(coupling) > 100_000:
        raise ValueError('Provide a bounded extracted capacitance matrix.')
    def positive(value):
        value = float(value)
        if not math.isfinite(value) or value < 0:
            raise ValueError('Capacitance must be finite and nonnegative.')
        return value
    g = {name: positive(value) for name, value in ground.items()}
    if any(not isinstance(n, str) or not n for n in g):
        raise ValueError('Capacitance nodes need distinct nonempty names.')
    floats = set(floating)
    if not floats <= g.keys():
        raise ValueError('Floating-fill declaration contains an unknown node.')
    caps = {}
    for pair, value in coupling.items():
        if not isinstance(pair, tuple) or len(pair) != 2 or pair[0] == pair[1] or any(n not in g for n in pair):
            raise ValueError('Invalid mutual-capacitance endpoints.')
        pair = tuple(sorted(pair)); caps[pair] = caps.get(pair, 0.) + positive(value)
    adjacency = {n: {} for n in g}
    for (a, b), value in caps.items():
        if value:
            adjacency[a][b] = value; adjacency[b][a] = value
    output_ground = {n: value for n, value in g.items() if n not in floats}
    output_coupling = {pair: value for pair, value in caps.items() if not (set(pair) & floats)}
    pending = set(floats); components = []; maximum_residual = 0.; maximum_roundoff = 0.
    while pending:
        stack = [min(pending)]; members = set()
        while stack:
            node = stack.pop()
            if node in members:
                continue
            members.add(node); pending.discard(node)
            stack.extend(n for n in adjacency[node] if n in floats and n not in members)
        nodes = sorted(members)
        boundary = sorted({n for f in nodes for n in adjacency[f] if n not in floats})
        item = {'floating_nodes': nodes, 'retained_boundary': boundary}
        components.append(item)
        if not boundary:
            item['status'] = 'unobservable'; continue
        if len(nodes) > max_component or len(boundary) > max_component:
            raise ValueError('Floating-fill component exceeds the declared numerical budget.')
        diagonal = [math.fsum([g[n], *adjacency[n].values()]) for n in nodes]
        scale = max(diagonal)
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError('Invalid floating-fill matrix scale.')
        matrix = [[(diagonal[i] if i == j else -adjacency[nodes[i]].get(nodes[j], 0.)) / scale
                   for j in range(len(nodes))] for i in range(len(nodes))]
        lower = [[0.] * len(nodes) for _ in nodes]
        for i in range(len(nodes)):
            for j in range(i + 1):
                value = matrix[i][j] - math.fsum(lower[i][k] * lower[j][k] for k in range(j))
                if i == j:
                    if not math.isfinite(value) or value <= 1e-14:
                        raise ValueError('Floating-fill matrix is singular or too ill-conditioned.')
                    lower[i][j] = math.sqrt(value)
                else:
                    lower[i][j] = value / lower[j][j]
        vectors = {n: [adjacency[f].get(n, 0.) / scale for f in nodes] for n in boundary}
        solutions = {}
        for n, rhs in vectors.items():
            y = [0.] * len(nodes); x = [0.] * len(nodes)
            for i in range(len(nodes)):
                y[i] = (rhs[i] - math.fsum(lower[i][j] * y[j] for j in range(i))) / lower[i][i]
            for i in reversed(range(len(nodes))):
                x[i] = (y[i] - math.fsum(lower[j][i] * x[j] for j in range(i + 1, len(nodes)))) / lower[i][i]
            residual = max(abs(math.fsum(matrix[i][j] * x[j] for j in range(len(nodes))) - rhs[i]) for i in range(len(nodes)))
            if not math.isfinite(residual) or residual > 1e-11:
                raise ValueError('Floating-fill matrix solve failed its residual check.')
            maximum_residual = max(maximum_residual, residual); solutions[n] = x
        schur = {(a, b): scale * math.fsum(vectors[a][i] * solutions[b][i] for i in range(len(nodes)))
                 for a in boundary for b in boundary}
        tolerance = scale * 1e-11
        def nonnegative(value):
            nonlocal maximum_roundoff
            if not math.isfinite(value) or value < -tolerance:
                raise ValueError('Floating-fill reduction violated capacitance passivity.')
            maximum_roundoff = max(maximum_roundoff, max(0., -value))
            return max(0., value)
        for a in boundary:
            extra = scale * math.fsum(vectors[a]) - math.fsum(schur[(a, b)] for b in boundary)
            output_ground[a] += nonnegative(extra)
        for i, a in enumerate(boundary):
            for b in boundary[i + 1:]:
                if abs(schur[(a, b)] - schur[(b, a)]) > tolerance:
                    raise ValueError('Floating-fill reduction lost matrix symmetry.')
                pair = (a, b)
                output_coupling[pair] = output_coupling.get(pair, 0.) + nonnegative((schur[(a, b)] + schur[(b, a)]) / 2.)
        item.update(status='reduced', scale_f=scale)
    return {'schema': 1, 'algorithm': 'floating-fill-zero-charge-schur-v1',
            'ground_f': output_ground,
            'coupling_f': [{'a': a, 'b': b, 'value_f': value} for (a, b), value in sorted(output_coupling.items()) if value],
            'floating_nodes': sorted(floats), 'components': components,
            'equation': 'C_effective = C_kk - C_kf * inverse(C_ff) * C_fk; Q_f = 0',
            'max_component': max_component, 'maximum_normalized_solve_residual': maximum_residual,
            'maximum_passivity_roundoff_f': maximum_roundoff,
            'scope': 'Linear equipotential floating conductors with zero initial net charge; extracted deck capacitance only, no fill resistance or unextracted fields.'}


def from_ext(path, floating, *, max_component=256):
    """Read authoritative full-precision flat Magic capacitance, then reduce it."""
    from .magic_rc import _records, _ORIGINAL_KEYS, _aliases, _scale, _device, _number
    path = Path(path); raw = path.read_bytes(); records = _records(raw.decode('utf-8'), _ORIGINAL_KEYS)
    declarations = [t[1] for _, t in records if t and t[0] in ('node', 'substrate')]
    if len(set(declarations)) != len(declarations):
        raise ValueError('Duplicate fill extraction node record.')
    records, _, aliases = _aliases(records, [])
    cscale = _scale(records)[1] * 1e-18
    nodes = {t[1]: _number(t[3], 'fill ground capacitance') * cscale for _, t in records if t and t[0] in ('node', 'substrate')}
    refs = [t[1] for _, t in records if t and t[0] == 'substrate']
    if len(refs) != 1 or nodes[refs[0]] != 0:
        raise ValueError('Fill extraction requires one explicit zero-capacitance substrate reference.')
    reference = refs[0]; nodes.pop(reference)
    floats = {aliases.get(n, n) for n in floating}
    if reference in floats:
        raise ValueError('The substrate reference cannot be declared floating fill.')
    ports = {t[1] for _, t in records if t and t[0] == 'port'}
    if floats & ports:
        raise ValueError('An external port cannot be declared floating fill.')
    coupling = {}
    for _, t in records:
        if not t:
            continue
        if t[0] == 'fet':
            raise ValueError('Floating-fill reduction requires modern device records to verify terminal isolation.')
        if t[0] == 'device' and floats & set(_device(t)['electrical']):
            raise ValueError('Floating fill is connected to a physical device terminal.')
        if t[0] == 'cap':
            a, b = t[1:3]; cap = _number(t[3], 'fill mutual capacitance') * cscale
            if reference in (a, b):
                other = b if a == reference else a
                if other not in nodes:
                    raise ValueError('Unknown fill capacitance node.')
                nodes[other] += cap
            else:
                pair = tuple(sorted((a, b))); coupling[pair] = coupling.get(pair, 0.) + cap
    result = reduce_floating(nodes, coupling, floats, max_component=max_component)
    if path.read_bytes() != raw:
        raise ValueError('Fill extraction changed during capacitance reduction.')
    result.update(source=path.name, source_sha256=hashlib.sha256(raw).hexdigest(), substrate_reference=reference,
                  input_ground_f=nodes,
                  input_coupling_f=[{'a': a, 'b': b, 'value_f': value} for (a, b), value in sorted(coupling.items())])
    return result
