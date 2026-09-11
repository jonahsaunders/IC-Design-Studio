"""Change records shared by local commands, undo, views and review tools."""
from dataclasses import dataclass


COLLECTIONS = ('devices', 'shapes', 'wires', 'layout_instances', 'layout_pins',
               'layout_ports', 'parametric_devices', 'pdk_layouts')


@dataclass(frozen=True)
class ChangeSet:
    project_id: str
    revision: int
    label: str
    kind: str
    cells: tuple
    objects: tuple
    removed: tuple
    structure: bool
    technology: bool


def describe(before, after, label, kind='edit'):
    old = {c['id']: c for c in before['cells']}
    new = {c['id']: c for c in after['cells']}
    cells, objects, removed = [], set(), set()
    structure = old.keys() != new.keys()
    for cid in dict.fromkeys([*old, *new]):
        a, b = old.get(cid, {}), new.get(cid, {})
        if a is b or a == b:
            continue
        cells.append(cid)
        structure |= a.get('name') != b.get('name') or a.get('ports') != b.get('ports')
        for field in COLLECTIONS:
            if a.get(field) is b.get(field):
                continue
            left = {v['id']: v for v in a.get(field, []) if 'id' in v}
            right = {v['id']: v for v in b.get(field, []) if 'id' in v}
            objects.update(i for i in left.keys() | right.keys() if left.get(i) != right.get(i))
            removed.update(left.keys() - right.keys())
    return ChangeSet(after['id'], after['revision'], label, kind, tuple(cells),
                     tuple(sorted(objects)), tuple(sorted(removed)), bool(structure),
                     before['pdk'] != after['pdk'])


def move_plain_shapes(project, cid, ids, dx, dy, locked=()):
    """Copy only ordinary moved geometry; complex owned edits use their commands."""
    from .model import validate_shape
    cell = next(c for c in project['cells'] if c['id'] == cid)
    chosen = set(ids)
    indices = [i for i, s in enumerate(cell['shapes']) if s['id'] in chosen]
    if not chosen or len(indices) != len(chosen):
        return None
    for i in indices:
        s = cell['shapes'][i]
        if any(s.get(k) for k in ('device_id', 'generated_device', 'generated_route', 'pcell_id', 'via_id')):
            return None
        if s['layer'] in locked:
            raise ValueError('Unlock the selected layers before moving their shapes.')
    grid = project['pdk']['grid']
    if any(type(v) is not int or v % grid for v in (dx, dy)):
        raise ValueError('Move distances must be on the manufacturing grid.')
    shapes = list(cell['shapes'])
    layers = {l['name'] for l in project['pdk']['layers']}
    for i in indices:
        old = shapes[i]
        shape = {**old, 'points': [[x + dx, y + dy] for x, y in old['points']]}
        if 'holes' in old:
            shape['holes'] = [[[x + dx, y + dy] for x, y in h] for h in old['holes']]
        validate_shape(shape, layers)
        shapes[i] = shape
    cells = [{**c, 'shapes': shapes} if c['id'] == cid else c for c in project['cells']]
    return {**project, 'cells': cells}, indices
