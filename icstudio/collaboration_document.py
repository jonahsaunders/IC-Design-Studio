"""Shared schematic/layout documents and atomic, identity-based changes.

Connectivity is rebuilt by model validation after the entire operation. The
electrical ledger is derived on the server, never merged as independent JSON.
Cell interfaces and project settings have a workspace-wide conflict boundary.
"""
import json

from .model import clone, validate

LAYOUT_FIELDS = {'shapes': 'id', 'layout_instances': 'id', 'layout_texts': None,
                 'layout_ports': 'name', 'layout_pins': 'id', 'pdk_layouts': 'device_id',
                 'parametric_devices': 'id'}
SCHEMATIC_FIELDS = {'devices': 'id', 'wires': 'id', 'labels': 'id',
                    'junctions': None, 'buses': 'id'}
FIELDS = {**LAYOUT_FIELDS, **SCHEMATIC_FIELDS}
STRUCTURE = {'cells', 'cell', 'project'}
PROTECTED = {'id', 'schema', 'created', 'pdk'}


def entities(cell, field):
    key = FIELDS[field]
    values = cell.get(field, [])
    if key is None:
        return {('texts' if field == 'layout_texts' else field): values} if values else {}
    result = {v[key]: v for v in values}
    if len(result) != len(values):
        raise ValueError('Duplicate object identity in ' + field + '.')
    return result


def cell_metadata(cell):
    return dict({k: v for k, v in cell.items() if k not in FIELDS and k != 'electrical'},
                _wired='wires' in cell, _identified='electrical' in cell)


def project_metadata(project):
    return {k: v for k, v in project.items()
            if k not in PROTECTED | {'cells', 'revision', 'modified'}}


def value_at(project, row):
    field, cid, key = row['field'], row['cell'], row['key']
    if field == 'project':
        return project_metadata(project)
    cell = next((c for c in project['cells'] if c['id'] == cid), None)
    if field == 'cells':
        return cell
    if cell is None:
        return None
    return cell_metadata(cell) if field == 'cell' else entities(cell, field).get(key)


def diff(before, after):
    if any(before.get(k) != after.get(k) for k in PROTECTED):
        raise ValueError('Project identity and PDK settings are fixed while collaborating. Leave the workspace to change the technology.')
    rows = []
    def add(cid, field, key, a, b):
        if a != b:
            rows.append(dict(cell=cid, field=field, key=key, before=clone(a), after=clone(b)))
    add(before['id'], 'project', before['id'], project_metadata(before), project_metadata(after))
    old = {c['id']: c for c in before['cells']}
    new = {c['id']: c for c in after['cells']}
    if [c for c in old if c in new] != [c for c in new if c in old]:
        raise ValueError('Reordering existing cells requires leaving the workspace.')
    for cid in dict.fromkeys([*old, *new]):
        a, b = old.get(cid), new.get(cid)
        if a is None or b is None:
            add(cid, 'cells', cid, a, b)
            continue
        add(cid, 'cell', cid, cell_metadata(a), cell_metadata(b))
        for field in FIELDS:
            left, right = entities(a, field), entities(b, field)
            if [k for k in left if k in right] != [k for k in right if k in left]:
                raise ValueError('Reordering existing objects requires leaving the workspace.')
            for key in dict.fromkeys([*left, *right]):
                add(cid, field, key, left.get(key), right.get(key))
    return rows


def install(project, rows, accept_identical=False):
    """Apply all before-value checks before mutation; validate only at the end."""
    q = clone(project)
    for row in rows:
        current = value_at(project, row)
        if current != row['before'] and not (accept_identical and current == row['after']):
            raise ValueError('Another editor changed this object or interface. Your proposed edit is retained; refresh and review it.')
        field, cid, key, value = row['field'], row['cell'], row['key'], clone(row['after'])
        if field == 'project':
            if cid != project['id'] or key != cid or not isinstance(value, dict) or set(value) & (PROTECTED | {'cells', 'revision', 'modified'}):
                raise ValueError('Invalid shared project settings.')
            q = {**{k: v for k, v in q.items() if k in PROTECTED | {'cells', 'revision', 'modified'}}, **value}
        elif field == 'cells':
            q['cells'] = [c for c in q['cells'] if c['id'] != cid]
            if value is not None:
                q['cells'].append(value)
        else:
            cell = next((c for c in q['cells'] if c['id'] == cid), None)
            if cell is None:
                raise ValueError('The edited cell no longer exists.')
            if field == 'cell':
                if not isinstance(value, dict) or set(value) & (set(FIELDS) | {'electrical'}):
                    raise ValueError('Invalid cell interface.')
                wired, identified = value.pop('_wired', False), value.pop('_identified', False)
                if type(wired) is not bool or type(identified) is not bool:
                    raise ValueError('Invalid connectivity representation.')
                collections = {k: v for k, v in cell.items() if k in FIELDS or k == 'electrical'}
                cell.clear(); cell.update(collections); cell.update(value)
                if wired: cell.setdefault('wires', [])
                else: cell.pop('wires', None)
                if identified: cell.setdefault('electrical', {})
                else: cell.pop('electrical', None)
            else:
                values = entities(cell, field)
                if value is None: values.pop(key, None)
                else: values[key] = value
                cell[field] = values.get('texts' if field == 'layout_texts' else field, []) if FIELDS[field] is None else list(values.values())
    validate(q)  # Includes authoritative wire connectivity, labels and hierarchy.
    return q


def resource(cell, field, key):
    return json.dumps([cell, field, key], separators=(',', ':'))


def overlaps(a, b):
    ac, af, ak = json.loads(a); bc, bf, bk = json.loads(b)
    if ac == '*' or bc == '*':
        return True
    if ac != bc:
        return False
    if af == '*' or bf == '*':
        return True
    if af == bf == 'region':
        a, b = json.loads(ak), json.loads(bk)
        return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]
    return (af, ak) == (bf, bk)


def resources(rows, *projects):
    """Electrical names and spatial read/write regions catch touching new wires.

Bounds are conservative: a crossing can need review even if it would remain
electrically disconnected. Property-only changes reserve the device, not its net.
"""
    if any(r['field'] in STRUCTURE for r in rows):
        # Interfaces can rename pins across the before/after symbol definitions.
        # A workspace boundary covers every dependent object without resolving
        # an old terminal against the new interface (or vice versa).
        return {resource('*', '*', '*')}
    result = set()
    contexts = [{c['id']: c for c in p['cells']} for p in projects]
    for row in rows:
        cid, field, key = row['cell'], row['field'], row['key']
        result.add(resource(cid, field, key))
        if field in STRUCTURE:
            result.add(resource('*', '*', '*'))
            continue
        values = [v for v in (row['before'], row['after']) if isinstance(v, dict)]
        if field in LAYOUT_FIELDS:
            if field != 'shapes' or any(v.get('generated_device') or v.get('pcell_id') for v in values):
                result.add(resource(cid, '*', '*'))
            for v in values:
                if v.get('net'): result.add(resource(cid, 'net', v['net']))
                if v.get('generated_device'): result.add(resource(cid, 'device', v['generated_device']))
            continue
        if field == 'devices':
            result.add(resource(cid, 'device', key))
            a, b = row['before'], row['after']
            topology = ('kind', 'cell', 'x', 'y', 'rotation', 'mirror', 'nets', 'net_labels', 'symbol')
            if a is not None and b is not None and all(a.get(k) == b.get(k) for k in topology):
                continue
        if field in ('junctions', 'buses'):
            # Junctions are coordinate lists without IDs; reserve the whole cell.
            result.add(resource(cid, '*', '*'))
        points = []
        for value in values:
            names = list(value.get('nets', {}).values()) + list(value.get('net_labels', {}).values())
            if value.get('net'): names.append(value['net'])
            if field == 'labels': names.append(value.get('name', ''))
            for name in names:
                if name: result.add(resource(cid, 'net', name))
            if field == 'devices':
                from .wiring import pins
                # Resolve linked symbol terminals using each side's hierarchy.
                for project in projects or (None,):
                    points.extend(pins({'devices': [value]}, project).values())
                points.append([value['x'], value['y']])
            elif field == 'wires':
                points.extend(value['points'])
            elif field == 'labels':
                from .net_labels import point, target
                anchor = value.get('anchor', {})
                if anchor.get('kind') == 'point': points.append(anchor['point'])
                for project, context in zip(projects, contexts):
                    cell = context.get(cid)
                    if cell:
                        try:
                            points.append(point(value, cell, project))
                            attached = target(value)
                            if attached:
                                result.add(resource(cid, 'device' if attached[0] != 'wire' else 'wires', attached[0] if attached[0] != 'wire' else attached[1]))
                        except (ValueError, KeyError, StopIteration):
                            pass  # An anchor removed by this transaction has no new point.
        if points:
            xs, ys = zip(*points)
            box = [min(xs)-1e-6, min(ys)-1e-6, max(xs)+1e-6, max(ys)+1e-6]
            result.add(resource(cid, 'region', json.dumps(box)))
    return result


def merge(base, local, remote):
    ours, theirs = diff(base, local), diff(base, remote)
    mine = resources(ours, base, local)
    if any(overlaps(a, b) for a in mine for b in resources(theirs, base, remote)):
        # Exactly repeated publications are harmless, all other overlap is reviewed.
        if any(value_at(remote, r) != r['after'] for r in ours):
            raise ValueError('Concurrent conflict: changes affect the same object, connection or hierarchy. Local changes are retained; refresh and review them.')
    return install(remote, ours, accept_identical=True)
