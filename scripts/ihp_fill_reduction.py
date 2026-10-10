"""Bounded experimental IHP floating-metal reduction; no field calibration.

The production dense solver is limited to 256 floating nodes per component.
The captured IHP model has larger, sparse components. This implementation uses
Jacobi-preconditioned conjugate gradients, verifies the actual residual, and
fails on nonconvergence or loss of passivity. Independent finite-R validation
is still required before treating its output as an accepted timing model.
"""
from collections import defaultdict
import math


def require(ok, message):
    if not ok:
        raise ValueError(message)


def solve(diagonal, off_diagonal, rhs):
    """Solve a symmetric positive definite capacitance block, with a checked residual."""
    n = len(diagonal)
    require(n > 0 and len(off_diagonal) == len(rhs) == n, 'Incomplete capacitance system.')
    require(all(math.isfinite(v) and v > 0 for v in diagonal), 'Invalid matrix diagonal.')
    scale = max(diagonal)
    d = [v / scale for v in diagonal]
    rows = [[(j, v / scale) for j, v in row] for row in off_diagonal]
    b = [v / scale for v in rhs]
    require(all(math.isfinite(v) and v >= 0 for v in b), 'Invalid boundary capacitance.')
    for i, row in enumerate(rows):
        require(len({j for j, _ in row}) == len(row), 'Repeated matrix entry.')
        for j, value in row:
            require(type(j) is int and 0 <= j < n and j != i and
                    math.isfinite(value) and value <= 0, 'Invalid matrix edge.')
            require(dict(rows[j]).get(i) == value, 'Asymmetric capacitance system.')
        require(d[i] + math.fsum(v for _, v in row) >= -1e-14, 'Nonpassive capacitance system.')
    def product(x):
        return [d[i] * x[i] + math.fsum(v * x[j] for j, v in row) for i, row in enumerate(rows)]
    def dot(a, b):
        return math.fsum(x * y for x, y in zip(a, b))
    norm = max(map(abs, b))
    if norm == 0:
        return [0.] * n, 0, 0.
    x = [0.] * n; r = b[:]; z = [r[i] / d[i] for i in range(n)]
    p = z[:]; rho = dot(r, z)
    for iteration in range(1, min(4096, 4*n+16)+1):
        ap = product(p); curvature = dot(p, ap)
        require(math.isfinite(curvature) and curvature > 0, 'Capacitance matrix is not positive definite.')
        alpha = rho / curvature
        x = [a + alpha*v for a, v in zip(x, p)]
        r = [a - alpha*v for a, v in zip(r, ap)]
        if max(map(abs, r)) <= norm*1e-12:
            actual = max(abs(v-w) for v, w in zip(product(x), b)) / norm
            require(math.isfinite(actual) and actual <= 1e-11, 'Capacitance solve residual failed.')
            return x, iteration, actual
        z = [r[i] / d[i] for i in range(n)]
        next_rho = dot(r, z)
        require(math.isfinite(next_rho) and next_rho > 0, 'Invalid iterative solve state.')
        beta = next_rho / rho; p = [a + beta*v for a, v in zip(z, p)]; rho = next_rho
    raise ValueError('Capacitance solve did not converge within its fixed budget.')


def reduce_floating(ground, coupling, floating):
    require(isinstance(ground, dict) and 0 < len(ground) <= 100_000 and
            isinstance(coupling, dict) and len(coupling) <= 100_000, 'Unbounded capacitance model.')
    require(all(isinstance(n, str) and n for n in ground), 'Invalid capacitance node.')
    def value(v):
        v = float(v)
        require(math.isfinite(v) and v >= 0, 'Nonpassive input capacitance.')
        return v
    ground = {n: value(v) for n, v in ground.items()}
    floats = set(floating)
    require(floats <= ground.keys(), 'Missing floating node.')
    adj = {n: {} for n in ground}; caps = defaultdict(float)
    for pair, raw in coupling.items():
        require(isinstance(pair, tuple) and len(pair) == 2 and pair[0] != pair[1]
                and all(n in ground for n in pair), 'Invalid coupling endpoint.')
        caps[tuple(sorted(pair))] += value(raw)
    for (a, b), v in caps.items():
        if v:
            adj[a][b] = v; adj[b][a] = v
    result_ground = {n: v for n, v in ground.items() if n not in floats}
    result_caps = {p: v for p, v in caps.items() if not floats.intersection(p)}
    pending = set(floats); parts = []; iterations = 0; residual = 0.; roundoff = 0.
    while pending:
        first = min(pending); pending.remove(first); members = {first}; stack = [first]
        while stack:
            for n in adj[stack.pop()]:
                if n in pending:
                    pending.remove(n); members.add(n); stack.append(n)
        nodes = sorted(members)
        boundary = sorted({n for f in nodes for n in adj[f] if n not in floats})
        part = dict(floating_nodes=nodes, retained_boundary=boundary)
        parts.append(part)
        if not boundary:
            part['status'] = 'unobservable'; continue
        require(len(nodes) <= 1024 and len(boundary) <= 256, 'Observable component exceeds its fixed budget.')
        index = {n: i for i, n in enumerate(nodes)}
        diagonal = [math.fsum([ground[n], *adj[n].values()]) for n in nodes]
        rows = [[(index[b], -v) for b, v in sorted(adj[a].items()) if b in index] for a in nodes]
        vectors = {n: [adj[f].get(n, 0.) for f in nodes] for n in boundary}
        solutions = {}
        for n, rhs in vectors.items():
            x, count, err = solve(diagonal, rows, rhs)
            solutions[n] = x; iterations = max(iterations, count); residual = max(residual, err)
        correction = {(a, b): math.fsum(v*x for v, x in zip(vectors[a], solutions[b]))
                      for a in boundary for b in boundary}
        scale = max(diagonal); tolerance = scale * 1e-11
        def nonnegative(v):
            nonlocal roundoff
            require(math.isfinite(v) and v >= -tolerance, 'Reduction lost capacitance passivity.')
            roundoff = max(roundoff, max(0., -v)); return max(0., v)
        for a in boundary:
            result_ground[a] += nonnegative(math.fsum(vectors[a]) - math.fsum(correction[a,b] for b in boundary))
        for i, a in enumerate(boundary):
            for b in boundary[i+1:]:
                require(abs(correction[a,b] - correction[b,a]) <= tolerance, 'Reduction lost matrix symmetry.')
                result_caps[a,b] = result_caps.get((a,b), 0.) + nonnegative((correction[a,b]+correction[b,a])/2)
        part.update(status='reduced', scale_f=scale)
    return dict(schema=1, algorithm='experimental-ihp-floating-fill-pcg-v1', ground_f=result_ground,
                coupling_f=[dict(a=a,b=b,value_f=v) for (a,b),v in sorted(result_caps.items()) if v],
                floating_nodes=sorted(floats), components=parts, maximum_iterations=iterations,
                maximum_relative_solve_residual=residual, maximum_passivity_roundoff_f=roundoff,
                limits=dict(nodes=100_000,edges=100_000,observable_component=1024,boundary=256),
                scope='Zero-charge equipotential metal fill within the supplied C model; no field or finite-R acceptance.')
