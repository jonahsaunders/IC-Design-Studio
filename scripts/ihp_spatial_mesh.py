"""Resolve diagnostic native resistance partitions and integrate local weights.

This establishes a location map on the *captured* resistance graph. It does not
establish identity with another extraction, capacitance accuracy, or timing.
Native single-precision area-transfer roundoff is reported separately from the
unit-sum interpolation basis used to conserve a subsequently assigned quantity.
"""
from collections import defaultdict
import hashlib
import math
from pathlib import Path
import shlex

from icstudio.spatial import SpatialIndex


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _box(value, *, area=False):
    _require(isinstance(value, (list, tuple)) and len(value) == 4 and
             all(type(x) is int and abs(x) <= 2_147_483_647 for x in value),
             'A native integer-grid rectangle is required.')
    _require(value[0] <= value[2] and value[1] <= value[3] and
             (not area or (value[0] < value[2] and value[1] < value[3])),
             'Invalid native support rectangle.')
    return tuple(value)


def _owner(name):
    # ResPrintExtNode removes exactly one trailing Magic global/auto-name mark.
    return name[:-1] if name.endswith(('!', '#')) else name


def resolve(trace, extraction):
    """Resolve pointer generations, merges and native series area transfers.

    Unknown nodes, missing transfers, cycles, split tiles and incomplete output
    names fail closed. Native transfer sums are bounded by one binary32 epsilon;
    their original values and composed residual remain in the diagnostic report.
    """
    trace, extraction = map(Path, (trace, extraction))
    digests = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (trace, extraction)}
    active, edges, names = {}, {}, {}
    regions, native_sums = [], []
    generations = 0
    with trace.open(encoding='ascii') as stream:
        for number, line in enumerate(stream, 1):
            _require(number <= 2_000_000, 'Mesh trace exceeds the event budget.')
            row = line.rstrip('\n').split('\t'); kind = row[0]
            if kind == 'transfer':
                _require(len(row) == 7, 'Malformed native transfer.')
                _, net, src, a, b, wa, wb = row
                wa, wb = float(wa), float(wb)
                _require(all(math.isfinite(v) and v >= 0 for v in (wa, wb)) and
                         abs(wa + wb - 1) <= 2. ** -23,
                         'Invalid native transfer weights.')
                _require(all(n in active for n in (src, a, b)) and src not in (a, b),
                         'Unknown or cyclic native transfer.')
                node = active.pop(src)
                _require(node not in edges and node not in names, 'Reused eliminated mesh node.')
                edges[node] = [(active[a], wa), (active[b], wb)]
                native_sums.append(wa + wb)
                continue
            _require(len(row) == 12, 'Malformed native mesh event.')
            kind, net, a, b, name, typ, split, axis, *bounds = row
            bounds = list(map(int, bounds))
            sign = 1
            if kind == 'area':
                # Native end extensions can subtract an already covered strip.
                # Only a constant, one-axis extension may be signed; preserve it
                # for explicit cancellation against equal positive support.
                inverted = [i for i in (0, 1) if bounds[i] > bounds[i + 2]]
                if inverted:
                    _require(len(inverted) == 1 and int(axis) == inverted[0] + 1 and a == b,
                             'Unsupported inverted mesh partition.')
                    i = inverted[0]; bounds[i], bounds[i + 2] = bounds[i + 2], bounds[i]
                    sign = -1
            bounds = _box(bounds)
            if kind == 'init':
                active[a] = generations; generations += 1
            elif kind in ('merge', 'move'):
                _require(a in active and b in active and a != b, 'Unknown or cyclic mesh merge.')
                left, right = active[a], active.pop(b)
                _require(right not in edges and right not in names, 'Reused eliminated mesh node.')
                edges[right] = [(left, 1.)]
            elif kind == 'area':
                _require(a in active and b in active, 'Unknown partition endpoint.')
                typ, split, axis = int(typ), int(split), int(axis)
                _require(typ >= 0 and split == 0 and axis in (0, 1, 2),
                         'Unsupported split tile or partition axis.')
                _box(bounds, area=True)
                _require(axis != 0 or a == b, 'A whole tile must have one endpoint.')
                regions.append(dict(net=net, a=active[a], b=active[b], type=typ,
                                    split=split, axis=axis, box=list(bounds), sign=sign))
            elif kind == 'name':
                _require(a in active and active[a] not in names and name != '@none',
                         'Unknown or duplicate final mesh node.')
                names[active[a]] = name
            else:
                raise ValueError('Unknown native mesh event.')
    wanted = set()
    for line in extraction.read_text().splitlines():
        if line.startswith('rnode '):
            row = shlex.split(line)
            _require(row[1] not in wanted, 'Duplicate extracted resistance node.')
            wanted.add(row[1])
    _require(regions and wanted and len(set(names.values())) == len(names) and
             set(names.values()) == wanted, 'Incomplete extracted node names.')
    cache = {}
    visiting = set()

    def visit(node):
        if node in cache:
            return cache[node]
        _require(node not in visiting, 'Cyclic native mesh transfers.')
        if node in names:
            _require(node not in edges, 'Named mesh node was eliminated.')
            cache[node] = ({names[node]: 1.}, {names[node]: 1.})
            return cache[node]
        _require(node in edges, 'Unresolved native partition endpoint.')
        visiting.add(node)
        raw, unit = defaultdict(float), defaultdict(float)
        total = math.fsum(w for _, w in edges[node])
        for child, weight in edges[node]:
            a, b = visit(child)
            for name, value in a.items():
                raw[name] += weight * value
            for name, value in b.items():
                unit[name] += weight / total * value
        visiting.remove(node)
        cache[node] = (dict(raw), dict(unit))
        return cache[node]

    residual = 0.
    for region in regions:
        for key in ('a', 'b'):
            native, unit = visit(region[key])
            residual = max(residual, abs(math.fsum(native.values()) - 1))
            _require(all(n.rsplit('.', 1)[0] == _owner(region['net']) for n in unit),
                     'A partition crosses native net ownership.')
            region[key] = unit
            region[key + '_native'] = native
    _require(all(hashlib.sha256(p.read_bytes()).hexdigest() == digests[str(p)]
                 for p in (trace, extraction)), 'Mesh input changed during audit.')
    return dict(schema=1, status='captured-mesh-support-resolved', qualified=False,
                source_sha256=digests, generations=generations, nodes=len(names),
                transfers=len(native_sums), regions=regions,
                signed_extension_regions=sum(r['sign'] < 0 for r in regions),
                maximum_transfer_unity_residue=max((abs(s - 1) for s in native_sums), default=0.),
                maximum_composed_unity_residue=residual,
                scope='Local interpolation on the captured R graph only. Frozen graph identity, capacitance projection and timing remain separate checks.')


class Mesh:
    """Exact area/edge/point integration of piecewise-linear mesh weights."""

    def __init__(self, regions, type_layers):
        groups = defaultdict(list)
        for region in regions:
            box = _box(region['box'], area=True)
            _require(region.get('split') == 0 and region['axis'] in (0, 1, 2),
                     'Unsupported mesh partition.')
            _require(type(region.get('sign', 1)) is int and region.get('sign', 1) in (-1, 1),
                     'Unsupported mesh partition sign.')
            _require(region['type'] in type_layers, 'Unknown native partition layer.')
            for endpoint in ('a', 'b'):
                values = region[endpoint]
                _require(values and all(isinstance(v, (int, float)) and not isinstance(v, bool) and
                         math.isfinite(v) and v >= 0 for v in values.values()) and
                         abs(math.fsum(values.values()) - 1.) <= 1e-12,
                         'Mesh interpolation weights must be finite and normalized.')
                _require(all(n.rsplit('.', 1)[0] == _owner(region['net']) for n in values),
                         'Mesh interpolation crosses net ownership.')
            _require(region['axis'] != 0 or region['a'] == region['b'],
                     'A whole tile must have one interpolation basis.')
            _require(region.get('sign', 1) > 0 or region['a'] == region['b'],
                     'Signed extensions must have a constant interpolation basis.')
            groups[region['net'], type_layers[region['type']]].append((box, region))
        self.indices = {key: SpatialIndex(rows) for key, rows in groups.items()}

    @staticmethod
    def _value(region, x, y):
        axis = region['axis'] - 1
        t = 0. if axis < 0 else ((x, y)[axis] - region['box'][axis]) / (
            region['box'][axis + 2] - region['box'][axis])
        return {n: (1. - t) * region['a'].get(n, 0.) + t * region['b'].get(n, 0.)
                for n in region['a'].keys() | region['b'].keys()}

    def average(self, net, layer, support):
        """Return the normalized integral over a closed rectangle, edge or point.

        Every elementary support must be covered. Multiple overlapping native
        partitions are counted once only when their complete affine bases agree
        on that support; otherwise the location is ambiguous and rejected.
        """
        box = _box(support)
        _require((net, layer) in self.indices, 'No mesh for this net and layer.')
        candidates = self.indices[net, layer].query(box)
        axes = []
        for axis in (0, 1):
            lo, hi = box[axis], box[axis + 2]
            cuts = sorted({lo, hi} | {r['box'][j] for r in candidates for j in (axis, axis + 2)
                                     if lo < r['box'][j] < hi})
            axes.append([(lo, hi)] if lo == hi else list(zip(cuts, cuts[1:])))
        result = defaultdict(list); measure = 0.
        for xl, xh in axes[0]:
            for yl, yh in axes[1]:
                x, y = (xl + xh) / 2, (yl + yh) / 2
                patches = [r for r in candidates if r['box'][0] <= x <= r['box'][2] and
                           r['box'][1] <= y <= r['box'][3]]
                _require(patches, 'Gap in native mesh support.')
                _require(sum(r.get('sign', 1) for r in patches) > 0,
                         'Uncancelled signed native mesh support.')
                # Affine fields agree on a cell iff they agree at its vertices.
                for px, py in {(xl, yl), (xl, yh), (xh, yl), (xh, yh)}:
                    baseline = self._value(patches[0], px, py)
                    for patch in patches[1:]:
                        other = self._value(patch, px, py)
                        _require(all(abs(baseline.get(n, 0.) - other.get(n, 0.)) <= 1e-12
                                     for n in baseline.keys() | other.keys()),
                                 'Ambiguous overlapping native mesh support.')
                area = (xh - xl or 1) * (yh - yl or 1); measure += area
                for name, value in self._value(patches[0], x, y).items():
                    result[name].append(area * value)
        result = {name: math.fsum(values) / measure for name, values in result.items()}
        _require(abs(math.fsum(result.values()) - 1.) <= 1e-12 and
                 all(v >= 0 for v in result.values()), 'Spatial integration lost unit weight.')
        return {name: value for name, value in result.items() if value != 0.}
