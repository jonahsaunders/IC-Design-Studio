"""Integrate local endpoint pairs over rectangular native field primitives.

This is a diagnostic location model, not an accepted timing extractor. Overlap
uses a uniform area density; halo primitives use the native atan derivative.
Shield rectangles must be supplied separately with their native signed values.
The joint integral preserves correlation along a wire; multiplying independently
averaged endpoint weights would lose it. The resulting pair weights describe a
passive, locally lumped discretization, not a consistent finite-element matrix.
"""
from collections import defaultdict
from functools import lru_cache
import math

from scripts.ihp_spatial_mesh import _box, _require


@lru_cache(maxsize=2)
def _gauss(order):
    """Positive Gauss-Legendre nodes/weights, computed without optional packages."""
    rows = []
    for i in range(1, order + 1):
        x = math.cos(math.pi * (i - .25) / (order + .5))
        for _ in range(32):
            p0, p1 = 1., x
            for k in range(2, order + 1):
                p0, p1 = p1, ((2*k - 1)*x*p1 - (k - 1)*p0)/k
            derivative = order*(x*p1 - p0)/(x*x - 1)
            delta = p1/derivative
            x -= delta
            if abs(delta) < 2e-16:
                break
        else:
            raise ValueError('Field quadrature did not initialize.')
        # Re-evaluate at the converged root before calculating its weight.
        p0, p1 = 1., x
        for k in range(2, order + 1):
            p0, p1 = p1, ((2*k - 1)*x*p1 - (k - 1)*p0)/k
        derivative = order*(x*p1 - p0)/(x*x - 1)
        rows.append(((1+x)/2, 1/((1-x*x)*derivative*derivative)))
    return tuple(rows)


@lru_cache(maxsize=32768)
def halo_moments(near, far, multiplier):
    """Return mass and normalized quadratic Bernstein moments on [near, far].

Positive quadrature avoids cancellation in narrow, distant strips. Two orders
must agree, and their total is checked against the analytic atan integral.
Subdivision is bounded and failures remain explicit.
"""
    _require(all(math.isfinite(x) for x in (near, far, multiplier)) and
             0 <= near < far and multiplier > 0, 'Invalid native fringe interval.')
    span = far-near
    exact = math.atan2(multiplier*span, 1 + multiplier*multiplier*near*far)
    _require(math.isfinite(exact) and exact > 0, 'Unresolvable fringe mass.')

    def values(lo, hi, order):
        rows = [[], [], []]
        for node, weight in _gauss(order):
            t = lo+(hi-lo)*node
            distance = near+span*t
            density = multiplier*span/(1+(multiplier*distance)**2)
            scale = weight*(hi-lo)*density
            for target, value in zip(rows, ((1-t)**2, t*(1-t), t*t)):
                target.append(scale*value)
        return tuple(map(math.fsum, rows))

    def integrate(lo, hi, depth):
        coarse, fine = values(lo, hi, 8), values(lo, hi, 16)
        local_mass = math.atan2(multiplier*span*(hi-lo),
                               1+multiplier*multiplier*(near+span*lo)*(near+span*hi))
        if max(abs(x-y) for x, y in zip(coarse, fine)) <= local_mass*2e-14:
            return fine
        _require(depth < 20, 'Fringe quadrature exceeds its convergence budget.')
        mid = (lo+hi)/2
        return tuple(math.fsum(pair) for pair in zip(integrate(lo, mid, depth+1),
                                                    integrate(mid, hi, depth+1)))
    moments = integrate(0., 1., 0)
    mass = math.fsum((moments[0], 2*moments[1], moments[2]))
    _require(abs(mass-exact) <= exact*2e-13 and all(v >= 0 for v in moments),
             'Fringe quadrature does not conserve native analytic mass.')
    return exact, tuple(v/mass for v in moments)


class Endpoint:
    """A mesh conductor or explicitly identified equipotential conductor.

    Fixed coordinates map an area primitive onto its source edge. Singleton
    conductors are explicit: a missing mesh is never silently made lumped.
    """
    def __init__(self, *, net=None, layer=None, fixed=None, singleton=None):
        self.fixed = dict(fixed or {})
        _require(all(type(k) is int and k in (0, 1) and type(v) is int
                     for k, v in self.fixed.items()), 'Invalid fixed field coordinate.')
        _require((singleton is None and isinstance(net, str) and isinstance(layer, str)) or
                 (isinstance(singleton, str) and singleton and net is None and layer is None
                  and not self.fixed), 'An endpoint needs a mesh or explicit singleton.')
        self.net, self.layer, self.singleton = net, layer, singleton

    def support(self, box):
        result = list(box)
        for axis, value in self.fixed.items():
            result[axis] = result[axis+2] = value
        return tuple(result)

    def candidates(self, mesh, box):
        if self.singleton is not None:
            return []
        _require((self.net, self.layer) in mesh.indices, 'No mesh for field endpoint.')
        return mesh.indices[self.net, self.layer].query(self.support(box))

    def vertices(self, mesh, candidates, box):
        if self.singleton is not None:
            return [{self.singleton: 1.}]*4
        support = self.support(box)
        x, y = (support[0]+support[2])/2, (support[1]+support[3])/2
        patches = [r for r in candidates if r['box'][0] <= x <= r['box'][2] and
                   r['box'][1] <= y <= r['box'][3]]
        _require(patches and sum(r.get('sign', 1) for r in patches) > 0,
                 'Gap or uncancelled correction in field mesh support.')
        result = []
        for x, y in ((support[0], support[1]), (support[2], support[1]),
                     (support[0], support[3]), (support[2], support[3])):
            baseline = mesh._value(patches[0], x, y)
            for patch in patches[1:]:
                other = mesh._value(patch, x, y)
                _require(all(abs(baseline.get(n, 0)-other.get(n, 0)) <= 1e-12
                             for n in baseline.keys() | other.keys()),
                         'Ambiguous overlapping field mesh support.')
            _require(all(v >= 0 for v in baseline.values()), 'Negative spatial basis weight.')
            result.append(baseline)
        return result


def joint_weights(mesh, left, right, support, *, fringe=None):
    """Integrate paired local basis weights, including coincident coordinates.

    fringe is (normal axis, source-edge coordinate, positive native multiplier).
    Its area must lie entirely on one side of that edge. A uniform support may
    also be an edge or point. Every mesh patch must have unambiguous coverage.
    """
    box = _box(support)
    if fringe is not None:
        _require(isinstance(fringe, (tuple, list)) and len(fringe) == 3,
                 'Invalid fringe description.')
        axis, edge, mult = fringe
        _require(type(axis) is int and axis in (0, 1) and type(edge) is int and
                 isinstance(mult, (int, float)) and not isinstance(mult, bool) and
                 math.isfinite(mult) and mult > 0 and box[axis] < box[axis+2] and
                 (box[axis] >= edge or box[axis+2] <= edge), 'Invalid fringe geometry.')
    candidates = [endpoint.candidates(mesh, box) for endpoint in (left, right)]
    cuts = []
    for dimension in (0, 1):
        lo, hi = box[dimension], box[dimension+2]
        values = {lo, hi}
        for endpoint, regions in zip((left, right), candidates):
            if dimension not in endpoint.fixed:
                values.update(r['box'][j] for r in regions for j in (dimension, dimension+2)
                              if lo < r['box'][j] < hi)
        values = sorted(values)
        cuts.append([(lo, hi)] if lo == hi else list(zip(values, values[1:])))
    _require(len(cuts[0])*len(cuts[1]) <= 100000, 'Field partition exceeds its cell budget.')
    totals = defaultdict(list); masses = []
    for xl, xh in cuts[0]:
        for yl, yh in cuts[1]:
            cell = (xl, yl, xh, yh)
            vertices = [endpoint.vertices(mesh, rows, cell)
                        for endpoint, rows in zip((left, right), candidates)]
            moments = []; mass = 1.
            for dimension, (lo, hi) in enumerate(((xl, xh), (yl, yh))):
                if fringe is not None and dimension == axis:
                    near, far = sorted((abs(lo-edge), abs(hi-edge)))
                    weight, values = halo_moments(near, far, float(mult))
                    if hi <= edge:
                        values = values[::-1]
                else:
                    weight, values = (hi-lo, (1/3, 1/6, 1/3)) if lo != hi else (1., (1., 0., 0.))
                mass *= weight; moments.append(values)
            masses.append(mass)
            for i, av in enumerate(vertices[0]):
                for j, bv in enumerate(vertices[1]):
                    weight = mass*moments[0][(i % 2)+(j % 2)]*moments[1][(i // 2)+(j // 2)]
                    if not weight:
                        continue
                    for a, wa in av.items():
                        for b, wb in bv.items():
                            if wa and wb:
                                totals[a, b].append(weight*wa*wb)
    mass = math.fsum(masses)
    result = {pair: math.fsum(values)/mass for pair, values in totals.items()}
    _require(result and all(v > 0 and math.isfinite(v) for v in result.values()) and
             abs(math.fsum(result.values())-1) <= 2e-12, 'Field projection lost unit weight.')
    return result
