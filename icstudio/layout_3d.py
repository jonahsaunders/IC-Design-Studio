"""Bounded, read-only layout extrusion. XY input is integer nm; output is µm.

The native hierarchy query visits only the requested window. Meshes use a local
XY origin to retain precision on designs far from (0, 0). Layer Z coordinates
remain separate so visibility, thickness and exploded views need no remeshing.
"""
from dataclasses import dataclass, field
import math

from .layout import kdb, polygon
from .layout_scene import LayoutScene

MAX_TRIANGLES = 60000
MAX_INPUT_VERTICES = 20000
LIMIT_MESSAGE = ('This region exceeds the 3D detail budget. Zoom into the 2D '
                 'layout, choose Current 2D viewport, then Refresh. No partial geometry is shown.')


@dataclass
class Layer:
    name: str
    color: str
    z_um: float
    thickness_um: float
    illustrative: bool = True
    visible: bool = True
    triangles: list = field(default_factory=list)


@dataclass
class Mesh:
    layers: list
    origin_um: tuple
    bounds_um: tuple
    shape_count: int
    expanded_count: int
    cropped: bool
    source: str

    @property
    def triangle_count(self):
        return sum(len(layer.triangles) for layer in self.layers)


def stack_layers(pdk):
    """Read optional stack_3d metadata without guessing process dimensions."""
    stack = pdk.get('stack_3d', {})
    if not isinstance(stack, dict) or not isinstance(stack.get('layers', []), list):
        raise ValueError('PDK stack_3d must contain a layers list.')
    known = {layer['name'] for layer in pdk['layers']}
    supplied = {}
    for entry in stack.get('layers', []):
        if not isinstance(entry, dict) or entry.get('layer') not in known:
            raise ValueError('Each stack_3d entry must name an existing PDK layer.')
        name = entry['layer']
        if name in supplied:
            raise ValueError('Duplicate stack_3d layer: ' + name)
        try:
            z, thickness = float(entry['z_um']), float(entry['thickness_um'])
        except (KeyError, ValueError, TypeError):
            raise ValueError('Each stack_3d layer needs numeric z_um and thickness_um.') from None
        if not math.isfinite(z) or not math.isfinite(thickness) or abs(z) > 100000 or not .001 <= thickness <= 100000:
            raise ValueError('3D elevation must be finite within ±100,000 µm; thickness must be 0.001–100,000 µm.')
        supplied[name] = (z, thickness)
    layers = []
    for i, spec in enumerate(pdk['layers']):
        z, thickness = supplied.get(spec['name'], (i * .5, .2))
        layers.append(Layer(spec['name'], spec['color'], z, thickness, spec['name'] not in supplied))
    return layers, str(stack.get('source', '')).strip()


def extrude(poly, origin_um, limit=MAX_TRIANGLES):
    """Triangulate caps through KLayout trapezoids; preserve inner side walls.

    Vertices have unit Z (0 or 1). Each triangle carries an outward normal.
    A polygon with a hole therefore has neither a cap nor material in the hole.
    """
    triangles = []

    def vertex(p, z):
        return (p.x / 1000 - origin_um[0], p.y / 1000 - origin_um[1], z)

    def add(a, b, c, normal):
        if len(triangles) >= limit:
            raise ValueError(LIMIT_MESSAGE)
        triangles.append((a, b, c, normal))

    for piece in poly.decompose_trapezoids():
        points = list(piece.each_point())
        for i in range(1, len(points) - 1):
            a, b, c = points[0], points[i], points[i + 1]
            add(vertex(c, 1), vertex(b, 1), vertex(a, 1), (0, 0, 1))
            add(vertex(a, 0), vertex(b, 0), vertex(c, 0), (0, 0, -1))
    loops = [list(poly.each_point_hull())]
    loops.extend(list(poly.each_point_hole(i)) for i in range(poly.holes()))
    for loop in loops:
        for a, b in zip(loop, loop[1:] + loop[:1]):
            dx, dy = b.x - a.x, b.y - a.y
            length = math.hypot(dx, dy)
            if not length:
                continue
            normal = (-dy / length, dx / length, 0)
            add(vertex(a, 0), vertex(b, 1), vertex(b, 0), normal)
            add(vertex(a, 0), vertex(a, 1), vertex(b, 1), normal)
    return triangles


def build_mesh(project, cid, box=None):
    layers, source = stack_layers(project['pdk'])
    by_name = {layer.name: layer for layer in layers}
    scene = LayoutScene().update(project, cid)
    if scene.bounds.empty():
        return Mesh(layers, (0, 0), (0, 0, 1, 1), 0, 0, box is not None, source)
    if box is None:
        b = scene.bounds
        window = (b.left, b.bottom, b.right, b.top)
    else:
        if len(box) != 4 or not all(math.isfinite(v) for v in box) or box[0] >= box[2] or box[1] >= box[3]:
            raise ValueError('Choose a nonempty, finite 2D viewport.')
        window = tuple(box)
    # render=True enforces the hierarchy query budget; its overview must never
    # be passed off as solid geometry. This cache is private to the 3D viewer.
    rows = scene.query(window, cache=False, render=True)
    if any(s.get('_overview') for s in rows):
        raise ValueError(LIMIT_MESSAGE)
    vertices = sum(len(s['points']) + sum(len(h) for h in s.get('holes', [])) for s in rows)
    if vertices > MAX_INPUT_VERTICES:
        raise ValueError(LIMIT_MESSAGE)
    db = kdb()
    clip = db.Region(db.Box(math.floor(window[0]), math.floor(window[1]), math.ceil(window[2]), math.ceil(window[3])))
    origin = ((window[0] + window[2]) / 2000, (window[1] + window[3]) / 2000)
    bounds = db.Box()
    count = total = 0
    for shape in rows:
        layer = by_name.get(shape['layer'])
        if layer is None:
            raise ValueError('No PDK layer for 3D geometry: ' + shape['layer'])
        region = db.Region(polygon(shape))
        if box is not None:
            region &= clip
        contributed = False
        for poly in region.each():
            if poly.area() <= 0:
                continue
            triangles = extrude(poly, origin, MAX_TRIANGLES - total)
            total += len(triangles)
            layer.triangles.extend(triangles)
            bounds += poly.bbox()
            contributed = True
        count += contributed
    extent = (bounds.left / 1000 - origin[0], bounds.bottom / 1000 - origin[1],
              bounds.right / 1000 - origin[0], bounds.top / 1000 - origin[1]) if not bounds.empty() else (-.5, -.5, .5, .5)
    return Mesh(layers, origin, extent, count, scene.expanded_count, box is not None, source)
