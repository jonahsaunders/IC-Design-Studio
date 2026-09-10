"""Local geometry snapping on the manufacturing lattice, in screen tolerance.

Callers supply spatially queried shapes. Snapping is a geometric reference;
it never changes the target, its layer, its net, or its lock state.
"""
from dataclasses import dataclass
from math import gcd


@dataclass(frozen=True)
class SnapTarget:
    point: tuple
    kind: str
    layer: str
    owner: str


def segment_point(a, b, pointer, grid):
    """Closest grid point *on* an integer segment, including slanted edges.

    The primitive integer direction visits every integer point on the line.
    Bezout coefficients locate the grid phase without walking a long segment.
    This also handles imported endpoints that are off the project grid.
    """
    dx, dy = b[0]-a[0], b[1]-a[1]
    steps = gcd(dx, dy)
    if not steps:
        return tuple(a) if not (a[0] % grid or a[1] % grid) else None
    ux, uy = dx//steps, dy//steps
    old_r, r, old_s, s, old_t, t = ux, uy, 1, 0, 0, 1
    while r:
        q = old_r//r
        old_r, r, old_s, s, old_t, t = r, old_r-q*r, s, old_s-q*s, t, old_t-q*t
    phase = (-(old_s*a[0]+old_t*a[1])*old_r) % grid
    if phase > steps or (a[0]+phase*ux) % grid or (a[1]+phase*uy) % grid:
        return None
    projection = ((pointer[0]-a[0])*ux+(pointer[1]-a[1])*uy)/(ux*ux+uy*uy)
    index = phase+grid*max(0, min((steps-phase)//grid, round((projection-phase)/grid)))
    return a[0]+index*ux, a[1]+index*uy


def features(shape, pointer, grid):
    pts = shape.get('_snap_path', shape['points'])
    path = shape['kind'] == 'path' or '_snap_path' in shape
    if shape['kind'] == 'rect' and not path:
        (x1, y1), (x2, y2) = pts
        pts = [(x1,y1), (x2,y1), (x2,y2), (x1,y2)]
        yield ((x1+x2)/2, (y1+y2)/2), 'Center', True
    rings = [pts] if path else [pts]+shape.get('holes', [])
    for ring in rings:
        for i, pt in enumerate(ring):
            yield pt, 'Endpoint' if path and i in (0,len(ring)-1) else 'Corner', True
        segments = zip(ring, ring[1:] if path else list(ring[1:])+[ring[0]])
        for a, b in segments:
            yield ((a[0]+b[0])/2, (a[1]+b[1])/2), 'Midpoint', True
            point = segment_point(a, b, pointer, grid)
            if point is not None:
                yield point, 'Segment' if path else 'Edge', False


def nearest_target(pointer, shapes, terminals, grid, scale, visible, active_layer):
    """Prefer anchors within 6 px, then the nearest feature within 8 px.

    Distance wins within each group; coincident targets favor the active layer.
    Stable tie breaks keep overlapping shapes from flickering between frames.
    """
    best = None

    def consider(point, kind, anchor, layer, owner):
        nonlocal best
        if layer not in visible or point[0] % grid or point[1] % grid:
            return
        distance = ((point[0]-pointer[0])**2+(point[1]-pointer[1])**2)*scale**2
        if distance > 64:
            return
        target = SnapTarget(tuple(map(int, point)), kind, layer, owner)
        rank = (0 if anchor and distance <= 36 else 1, distance,
                layer != active_layer, 0 if kind == 'Terminal' else 1,
                layer, str(owner), kind, target.point)
        if best is None or rank < best[0]:
            best = rank, target

    for terminal in terminals:
        consider(terminal['point'], 'Terminal', True, terminal['layer'], terminal.get('id',''))
    for shape in shapes:
        if shape['layer'] not in visible:
            continue
        for point, kind, anchor in features(shape, pointer, grid):
            consider(point, kind, anchor, shape['layer'], shape['id'])
    return best[1] if best else None
