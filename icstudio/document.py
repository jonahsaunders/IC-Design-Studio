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


def from_patch(before,after,patch,label,kind='edit'):
    """Describe stable-index changes directly from the validated undo patch."""
    if not patch or patch[0]!='dict':return describe(before,after,label,kind)
    cp=patch[1].get('cells')
    if cp and cp[0]!='list':return describe(before,after,label,kind)
    cells=[];objects=set();removed=set();structure=False
    for index,delta in (cp[1].items() if cp else []):
        a,b=before['cells'][index],after['cells'][index]
        if delta[0]!='dict' or a['id']!=b['id']:return describe(before,after,label,kind)
        cells.append(b['id']);structure|=a.get('name')!=b.get('name') or a.get('ports')!=b.get('ports')
        for field in COLLECTIONS:
            change=delta[1].get(field)
            if field in delta[2] or field in delta[3] or change and change[0]!='list':return describe(before,after,label,kind)
            if not change:continue
            for position in change[1]:
                left=a[field][position].get('id');right=b[field][position].get('id')
                objects.update(v for v in (left,right) if v)
                if left and left!=right:removed.add(left)
    return ChangeSet(after['id'],after['revision'],label,kind,tuple(cells),tuple(sorted(objects)),tuple(sorted(removed)),bool(structure),before['pdk']!=after['pdk'])


def shape_patch(before,after,cid,indices):
    from .history_delta import difference
    index=next(i for i,c in enumerate(before['cells']) if c['id']==cid)
    a,b=before['cells'][index]['shapes'],after['cells'][index]['shapes']
    rows={i:difference(a[i],b[i]) for i in indices};rows={i:d for i,d in rows.items() if d is not None}
    changes={key:difference(before[key],after[key]) for key in ('revision','modified')}
    changes={key:d for key,d in changes.items() if d is not None}
    if rows:changes['cells']=('list',{index:('dict',{'shapes':('list',rows)},{},{})})
    return ('dict',changes,{},{})
