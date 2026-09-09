"""Grouped, grid-exact layout alignment and distribution.

Bounds include whole arrays. Planning is read-only; a candidate is published
only after all offsets, ownership and optional connectivity checks pass.
"""
from fractions import Fraction
from .model import clone, validate
from .layout import kdb, polygon

EDGES = ('left', 'right', 'bottom', 'top', 'center_x', 'center_y')


def selection_groups(p, cid, ids, locked=()):
    c = next(c for c in p['cells'] if c['id'] == cid)
    objects = {s['id']: s for s in c['shapes']}
    instances = {i['id']: i for i in c.get('layout_instances', [])}
    chosen = set(ids)
    if not chosen or not chosen <= objects.keys() | instances.keys():
        raise ValueError('Select local shapes or cell instances.')
    parent = {key: key for key in objects}; owners = {}
    def root(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]; key = parent[key]
        return key
    for s in c['shapes']:
        for field in ('generated_device', 'via_group', 'pcell_id'):
            if s.get(field):
                key = (field, s[field]); prior = owners.setdefault(key, s['id'])
                parent[root(s['id'])] = root(prior)
    members = {}
    for key in objects: members.setdefault(root(key), set()).add(key)
    groups = []; done = set()
    for key in ids:
        if key in done: continue
        group = members[root(key)] if key in objects else {key}
        if not group <= chosen:
            raise ValueError('Select the complete device footprint, PCell or via stack.')
        groups.append(group); done.update(group)
    if any(objects[k]['layer'] in locked for k in chosen & objects.keys()):
        raise ValueError('Unlock selected layers before arranging.')
    if locked and chosen & instances.keys():
        by = {c['id']: c for c in p['cells']}; cache = {}
        def layers(key):
            if key not in cache:
                cell = by[key]; result = {s['layer'] for s in cell['shapes']}
                for i in cell.get('layout_instances', []): result.update(layers(i['cell']))
                cache[key] = result
            return cache[key]
        if any(layers(instances[k]['cell']) & set(locked) for k in chosen & instances.keys()):
            raise ValueError('Unlock every affected layer in selected physical cells.')
    return groups


def group_bounds(p, cid, groups):
    c = next(c for c in p['cells'] if c['id'] == cid)
    wanted = set().union(*groups); bounds = {}
    db=kdb()
    for s in c['shapes']:
        if s['id'] in wanted: bounds[s['id']] = db.Box(*s['points'][0],*s['points'][1]) if s['kind']=='rect' else polygon(s).bbox()
    if any(i['id'] in wanted for i in c.get('layout_instances', [])):
        from .layout_scene import LayoutScene
        scene = LayoutScene().update(p, cid)
        for i in c.get('layout_instances', []):
            if i['id'] in wanted: bounds[i['id']] = scene.owner_bounds(i['id'])
    result = []
    for group in groups:
        box = db.Box()
        for key in group: box += bounds[key]
        if box.empty(): raise ValueError('Selected instance has no physical geometry.')
        result.append(box)
    return result


def coordinate(box, edge):
    if edge == 'center_x': return Fraction(box.left + box.right, 2)
    if edge == 'center_y': return Fraction(box.bottom + box.top, 2)
    return getattr(box, edge)


def plan(p, cid, ids, edge, locked=(), offset=0, reference_edge=None):
    groups = selection_groups(p, cid, ids, locked)
    if len(groups) < 2: raise ValueError('Select at least two independent objects or complete groups.')
    distribution = edge in ('distribute_x', 'distribute_y', 'gap_x', 'gap_y')
    if edge not in EDGES and not distribution: raise ValueError('Choose an alignment edge or distribution axis.')
    boxes = group_bounds(p, cid, groups)
    horizontal = edge in ('left', 'right', 'center_x', 'distribute_x', 'gap_x')
    if distribution:
        if len(groups) < 3: raise ValueError('Distribution needs at least three independent groups.')
        axis = 'center_x' if horizontal else 'center_y'
        order = sorted(range(len(boxes)), key=lambda i: coordinate(boxes[i], axis))
        low, high = ('left', 'right') if horizontal else ('bottom', 'top')
        if edge.startswith('gap'):
            widths = [getattr(boxes[i], high)-getattr(boxes[i], low) for i in order]
            gap = Fraction(getattr(boxes[order[-1]], high)-getattr(boxes[order[0]], low)-sum(widths), len(order)-1)
            if gap < 0: raise ValueError('There is insufficient room for nonoverlapping equal gaps.')
            cursor = getattr(boxes[order[0]], low); deltas = {}
            for i, width in zip(order, widths):
                deltas[i] = cursor-getattr(boxes[i], low); cursor += width+gap
        else:
            first = coordinate(boxes[order[0]], axis)
            step = (coordinate(boxes[order[-1]], axis)-first)/(len(order)-1)
            deltas = {i: first+j*step-coordinate(boxes[i], axis) for j, i in enumerate(order)}
    else:
        ref = reference_edge or edge
        if ref not in EDGES or (ref in ('left', 'right', 'center_x')) != horizontal:
            raise ValueError('Reference and moving edges must use the same axis.')
        if type(offset) is not int: raise ValueError('Offset must be an integer number of nanometres.')
        target = coordinate(boxes[0], ref)+offset
        deltas = {i: target-coordinate(box, edge) for i, box in enumerate(boxes) if i}
    moves = {}
    for i, delta in deltas.items():
        if delta != int(delta) or int(delta) % p['pdk']['grid']:
            raise ValueError('Exact arrangement would leave the layout grid. Adjust the dimensions or spacing.')
        if delta:
            for key in groups[i]: moves[key] = (int(delta) if horizontal else 0, 0 if horizontal else int(delta))
    return moves


def translated_cell(c, moves):
    """Copy changed geometry and metadata once; share untouched branches."""
    cell = {**c}; cell['shapes'] = []; device_moves = {}; pcell_moves = {}
    def pt(point, delta): return [point[0]+delta[0], point[1]+delta[1]]
    for s in c['shapes']:
        delta = moves.get(s['id'])
        if delta:
            q = {**s, 'points': [pt(v, delta) for v in s['points']]}
            if 'holes' in s: q['holes'] = [[pt(v, delta) for v in h] for h in s['holes']]
            if s.get('generated_device'): device_moves[s['generated_device']] = delta
            if s.get('pcell_id'): pcell_moves[s['pcell_id']] = delta
            cell['shapes'].append(q)
        else: cell['shapes'].append(s)
    if 'layout_instances' in c:
        cell['layout_instances'] = [{**i, 'x': i['x']+moves[i['id']][0], 'y': i['y']+moves[i['id']][1]} if i['id'] in moves else i for i in c['layout_instances']]
    for record in c.get('parametric_devices', []):
        if record['id'] in pcell_moves and record.get('device_id'):
            device_moves[record['device_id']] = pcell_moves[record['id']]
    if 'layout_pins' in c:
        cell['layout_pins'] = [{**pin, 'point': pt(pin['point'], device_moves[pin['device_id']])} if pin['device_id'] in device_moves else pin for pin in c['layout_pins']]
    if 'pdk_layouts' in c:
        cell['pdk_layouts'] = [{**row, 'origin': pt(row['origin'], device_moves[row['device_id']])} if row['device_id'] in device_moves else row for row in c['pdk_layouts']]
    return cell


def arrange(p, cid, ids, edge, locked=(), offset=0, reference_edge=None, connected=False):
    moves = plan(p, cid, ids, edge, locked, offset, reference_edge)
    c = next(c for c in p['cells'] if c['id'] == cid)
    cell = translated_cell(c, moves); cells = list(p['cells']); cells[cells.index(c)] = cell
    q = {**p, 'cells': cells}
    if connected:
        from .design_ops import flatten_layout
        from .wiring import retarget_path
        from .layout_topology import require_preserved, _check_clearance
        from .layout_index import LayoutBoxIndex
        routes=[(i,s) for i,s in enumerate(cell['shapes']) if s['id'] not in moves and s['kind']=='path']
        moving = [(s['layer'], polygon(s), moves[s['id']]) for s in (flatten_layout(p,cid) if c.get('layout_instances') else c['shapes']) if s['id'] in moves] if routes else []
        index=LayoutBoxIndex([(b.left,b.bottom,b.right,b.top) for _,poly,_ in moving for b in [poly.bbox()]]) if moving else None
        for i, s in routes:
            targets = []
            for end in (s['points'][0], s['points'][-1]):
                nearby=(moving[j] for j in index.query((*end,*end))) if index is not None else ()
                shifts = {delta for layer, poly, delta in nearby if layer == s['layer'] and poly.inside(kdb().Point(*end))}
                if len(shifts) > 1: raise ValueError('Attached footprints require conflicting route endpoint moves.')
                shift = next(iter(shifts), None)
                targets.append([end[0]+shift[0], end[1]+shift[1]] if shift else None)
            if any(v is not None for v in targets):
                if s['layer'] in locked: raise ValueError('Unlock attached route layers before aligning.')
                if any(s.get(k) for k in ('pcell_id', 'generated_device', 'via_group')):
                    raise ValueError('Attached routing belongs to another generated footprint.')
                cell['shapes'][i] = {**s, 'points': retarget_path(s['points'], *targets)}
        graph=require_preserved(p, q, cid); _check_clearance(p, q, cid, graph)
    if connected:
        from .route_constraints import enforce
        enforce(p,q,cid)
    validate(q)
    c.update(cell)
    return moves
