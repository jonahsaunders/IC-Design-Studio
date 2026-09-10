"""Reviewable schematic-to-layout updates for linked process MOS footprints."""
from .model import clone, design_digest, validate
from .layout import kdb, polygon


def roles(data):
    counts = {}; nf = data['record']['spec']['values'].get('nf', 1)
    for s in data['shapes']:
        key = (s['layer'], s['kind']); index = counts.get(key, 0); counts[key] = index+1
        s.setdefault('generator_role', f'{nf}:{key[0]}:{key[1]}:{index}')
    return data


def regenerate(p, cid, did):
    from .process_adapters import adapter
    from .sky130_layout import resolved
    c = next(c for c in p['cells'] if c['id'] == cid)
    old = next((r for r in c.get('pdk_layouts', []) if r['device_id'] == did), None)
    if old is None: raise ValueError('No generated footprint is linked to this device.')
    if old.get('transformed') and 'orientation' not in old:
        raise ValueError('This legacy footprint lacks its saved orientation. Restore the original orientation or regenerate the cell.')
    implementation = adapter(p['pdk']).implementation()
    d = resolved(p, cid, next(d for d in c['devices'] if d['id'] == did))
    data = roles(implementation.mos(p['pdk'], d, *old['origin']))
    prior = roles({'shapes': clone([s for s in c['shapes'] if s.get('generated_device') == did]), 'record': old})
    by_role = {s['generator_role']: s['id'] for s in prior['shapes']}
    pins = {v['pin']: v['id'] for v in c.get('layout_pins', []) if v['device_id'] == did}
    orientation = old.get('orientation', {'rotation': 0, 'mirror': False})
    x, y = old['origin']; db = kdb()
    tr = db.ICplxTrans(1, 0, False, x, y)*db.ICplxTrans(1, orientation['rotation'], orientation['mirror'], 0, 0)*db.ICplxTrans(1, 0, False, -x, -y)
    def point(pt): v = tr*db.Point(*pt); return [v.x, v.y]
    for s in data['shapes']:
        s['id'] = by_role.get(s['generator_role'], s['id']); s['points'] = [point(pt) for pt in s['points']]
        if 'holes' in s: s['holes'] = [[point(pt) for pt in h] for h in s['holes']]
    for pin in data['pins']:
        pin['id'] = pins.get(pin['pin'], pin['id']); pin['point'] = point(pin['point'])
    data['record'].update(orientation=clone(orientation), transformed=bool(orientation['rotation'] or orientation['mirror']))
    c['shapes'] = [s for s in c['shapes'] if s.get('generated_device') != did]+data['shapes']
    c['layout_pins'] = [v for v in c.get('layout_pins', []) if v['device_id'] != did]+data['pins']
    c['pdk_layouts'] = [r for r in c['pdk_layouts'] if r['device_id'] != did]+[data['record']]
    validate(p)
    return data


def inventory(p, cid):
    from .process_adapters import adapter
    from .sky130_layout import resolved
    from .physical import connectivity
    c = next(c for c in p['cells'] if c['id'] == cid)
    records = {r['device_id']: r for r in c.get('pdk_layouts', [])}
    instances = {i.get('device_id'): i for i in c.get('layout_instances', [])}
    ds = {d['id']: d for d in c['devices']}; rows = []
    for did, d in ds.items():
        row = {'device_id': did, 'name': d['name'], 'status': 'current', 'detail': ''}
        if did in records:
            try:
                current = adapter(p['pdk']).implementation().specification(p['pdk'], resolved(p, cid, d))
                if current != records[did]['spec']:
                    row.update(status='changed', detail=', '.join(k for k in current if current[k] != records[did]['spec'].get(k)))
            except ValueError as e: row.update(status='unsupported', detail=str(e))
        elif d['kind'] == 'X' and did in instances:
            if instances[did]['cell'] != d['cell']: row.update(status='changed hierarchy', detail='Place the matching physical cell explicitly.')
        else: row.update(status='missing', detail='Place a physical implementation explicitly.')
        rows.append(row)
    for did in records.keys()-ds.keys(): rows.append({'device_id': did, 'name': did, 'status': 'orphan', 'detail': 'Schematic device was deleted; physical geometry is retained for review.'})
    check = connectivity(p, cid)
    return {'design_hash': design_digest(p), 'cell_id': cid, 'devices': rows, 'connectivity': check['issues']}


def propose(p, cid, device_ids, locked=(), preserve_routes=True):
    """Parameters and terminals update at their saved origins; no device deletion."""
    report = inventory(p, cid); eligible = {r['device_id'] for r in report['devices'] if r['status'] == 'changed'}
    chosen = set(device_ids)
    if not chosen or not chosen <= eligible: raise ValueError('Choose changed linked process devices from the current review.')
    c = next(c for c in p['cells'] if c['id'] == cid); q = clone(p)
    if any(s['layer'] in locked and s.get('generated_device') in chosen for s in c['shapes']):
        raise ValueError('Unlock every layer of the updated footprints.')
    for did in chosen: regenerate(q, cid, did)
    cell = next(c for c in q['cells'] if c['id'] == cid)
    changed_routes = []
    if preserve_routes:
        from .wiring import retarget_path
        old_pins = {(v['device_id'], v['pin']): v for v in c.get('layout_pins', []) if v['device_id'] in chosen}
        new_pins = {(v['device_id'], v['pin']): v for v in cell.get('layout_pins', []) if v['device_id'] in chosen}
        for s in cell['shapes']:
            if s.get('generated_device') or s.get('pcell_id') or s['kind'] != 'path': continue
            targets = []
            for pt in (s['points'][0], s['points'][-1]):
                found = {tuple(new_pins[k]['point']) for k, pin in old_pins.items() if pin['layer'] == s['layer'] and pin['point'] == pt}
                if len(found) > 1: raise ValueError('Shared endpoint needs incompatible terminal moves; route it explicitly.')
                targets.append(list(next(iter(found))) if found else None)
            if any(v is not None for v in targets):
                if s['layer'] in locked: raise ValueError('Unlock attached route layers before applying the update.')
                points = retarget_path(s['points'], *targets)
                if points != s['points']: s['points'] = points; changed_routes.append(s['id'])
        # Regeneration may change shape counts; compare terminal partitions only.
        from .layout_topology import partition
        before, after = partition(p, cid), partition(q, cid)
        anchors = {k for k in before if k[0] != 'shape'}
        if not anchors <= after.keys() or any(before[k] & anchors != after[k] & anchors for k in anchors):
            raise ValueError('The update changes terminal connectivity. Adjust routes or review with fixed route coordinates.')
        from .layout_topology import _check_clearance
        _check_clearance(p, q, cid)
    validate(q)
    report.update(updated=sorted(chosen), adjusted_routes=changed_routes, after=inventory(q, cid))
    return q, report


def apply(p, candidate, report):
    if report['design_hash'] != design_digest(p): raise ValueError('Layout update review is stale. Review the current schematic again.')
    validate(candidate)
    p.clear(); p.update(clone(candidate))
