"""Explicit, atomic schematic-driven layout changes across shared cell masters."""
from .model import clone, design_digest, validate
from .physical_cells import reachable
from .parametric import electrical_signature


def _cell(p, cid):
    return next(c for c in p['cells'] if c['id'] == cid)


def _resolved(p, cid, d):
    from .sky130_layout import resolved
    return resolved(p, cid, d) if not d.get('native_spice') else d


def _recipe(p, cid, d):
    if d['kind'] == 'X': return 'hierarchy'
    if d.get('model_ref'):
        from .process_adapters import adapter
        adapter(p['pdk']).implementation().specification(p['pdk'], _resolved(p, cid, d))
        return 'process'
    from .parametric import build
    c = {**_cell(p, cid), 'devices': [_resolved(p, cid, d)]}
    q = {**p, 'cells': [c]}
    build(q, cid, d['id'], {})
    return 'parametric'


def inventory(p, cid, hierarchy=True):
    """Visit each master once; shared instances never duplicate a proposed edit."""
    cells = reachable(p, cid) if hierarchy else [cid]
    rows = []
    for ident in cells:
        c = _cell(p, ident); ds = {d['id']: d for d in c['devices']}
        process = {r['device_id']: r for r in c.get('pdk_layouts', [])}
        generic = {r['device_id']: r for r in c.get('parametric_devices', []) if r.get('device_id')}
        physical = {i['device_id']: i for i in c.get('layout_instances', []) if i.get('device_id')}
        for did, d in ds.items():
            row = dict(cell_id=ident, cell=c['name'], device_id=did, name=d['name'], status='current', action='', detail='')
            if d['kind'] in ('V', 'I') or d.get('native_spice', {}).get('type') == 'program':
                row.update(status='external', detail='Stimulus or simulation command; no physical implementation.')
            else:
                try:
                    recipe = _recipe(p, ident, d); row['recipe'] = recipe
                    if did in process:
                        from .process_adapters import adapter
                        spec = adapter(p['pdk']).implementation().specification(p['pdk'], _resolved(p, ident, d))
                        if process[did]['spec'] != spec: row.update(status='changed', action='update', detail='Process parameters or terminal nets changed.')
                    elif did in generic:
                        from .parametric import geometry_signature, rules
                        from .model import digest
                        r = generic[did]
                        if (r['source_signature'] != electrical_signature(_resolved(p, ident, d)) or
                            r['rules_hash'] != digest(rules(p['pdk'])) or
                            r['geometry_signature'] != geometry_signature([s for s in c['shapes'] if s.get('pcell_id') == r['id']])):
                            row.update(status='changed', action='update', detail='Parameters, terminal nets, recipe or generated geometry changed.')
                    elif did in physical:
                        i = physical[did]
                        if i['cell'] != d.get('cell') or i.get('schematic_signature') != electrical_signature(d):
                            row.update(status='changed hierarchy', action='rebind', detail='Review child master, parameters and terminal mapping at the saved placement.')
                    elif any(s.get('device_id') == did for s in c['shapes']):
                        row.update(status='manual', detail='Manually linked geometry; review terminals and connectivity explicitly.')
                    else: row.update(status='missing', action='add', detail='Create the declared '+recipe+' implementation.')
                except (ValueError, KeyError) as exc:
                    row.update(status='unsupported', action='', detail=str(exc))
            rows.append(row)
        for did in (process.keys() | generic.keys() | physical.keys()) - ds.keys():
            rows.append(dict(cell_id=ident, cell=c['name'], device_id=did, name=did, status='orphan', action='remove', detail='Remove owned footprint/instance and pins; retain independent routes.'))
    return dict(design_hash=design_digest(p), cell_id=cid, cells=cells, devices=rows)


def _owned(c, did):
    pcells = {r['id'] for r in c.get('parametric_devices', []) if r.get('device_id') == did}
    return [s for s in c['shapes'] if s.get('generated_device') == did or s.get('pcell_id') in pcells]


def _terminals(p, cid):
    from .physical_cells import terminals
    return {(v['device_id'], v['pin']): v for v in terminals(p, cid)}


def _retarget(before, after, cid, chosen, locked):
    from .wiring import retarget_path
    old = _terminals(before, cid); new = _terminals(after, cid); adjusted = []
    for s in _cell(after, cid)['shapes']:
        if s.get('generated_device') or s.get('pcell_id') or s['kind'] != 'path': continue
        targets = []
        for pt in (s['points'][0], s['points'][-1]):
            matching = [k for k, v in old.items() if k[0] in chosen and v['layer'] == s['layer'] and v['point'] == pt]
            if any(k not in new or new[k]['layer'] != old[k]['layer'] for k in matching):
                raise ValueError('An attached terminal was removed or changed layer. Review with fixed route coordinates.')
            points = {tuple(new[k]['point']) for k in matching}
            if len(points) > 1: raise ValueError('A shared endpoint needs incompatible terminal moves.')
            targets.append(list(next(iter(points))) if points else None)
        if any(t is not None for t in targets):
            points = retarget_path(s['points'], *targets)
            if points != s['points']:
                if s['layer'] in locked: raise ValueError('Unlock attached route layers.')
                s['points'] = points; adjusted.append(s['id'])
    return adjusted


def _check_instance(p, cid, d):
    from .design_ops import parameters, value
    from .physical_cells import ports
    child = _cell(p, d['cell']); c = _cell(p, cid)
    if not child['shapes'] and not child.get('layout_instances'): raise ValueError(d['name']+': implement the child layout first, or select its missing devices in this review.')
    if set(v['name'] for v in ports(p, child['id'])) != set(child['ports']): raise ValueError(d['name']+': assign every physical child port before linking.')
    global_ = parameters(p.get('parameters', {})); defaults = parameters(child.get('parameters', {}), global_)
    context = parameters(c.get('parameters', {}), global_)
    actual = parameters({**child.get('parameters', {}), **{k: value(v, context) for k, v in d.get('parameters', {}).items()}}, global_)
    if actual != defaults: raise ValueError(d['name']+': parameter overrides require a concrete physical cell variant. A shared master cannot represent different geometry.')
    if d.get('native_spice', {}).get('parameters'):
        defaults = child.get('spice_parameters', {})
        if any(str(v) != str(defaults.get(k)) for k, v in d['native_spice']['parameters'].items()):
            raise ValueError(d['name']+': resolve native instance overrides into a concrete physical cell variant first.')


def propose(p, cid, selections, locked=(), preserve_routes=True, origin=(0, 0), pitch=20000, hierarchy=True):
    """Selected (cell ID, device ID) pairs become one reviewable transaction."""
    report = inventory(p, cid, hierarchy); rows = {(r['cell_id'], r['device_id']): r for r in report['devices']}
    chosen = set(map(tuple, selections))
    if not chosen or any(k not in rows or not rows[k]['action'] for k in chosen): raise ValueError('Select actionable devices from the current hierarchy review.')
    grid = p['pdk']['grid']
    if len(origin) != 2 or any(type(v) is not int or v % grid for v in origin) or type(pitch) is not int or pitch <= 0 or pitch % grid:
        raise ValueError('Use a positive placement pitch and origin on the technology grid.')
    q = clone(p); changes = []; routes = []; affected = []
    for ident in report['cells']:
        local = [r for r in report['devices'] if r['cell_id'] == ident and (ident, r['device_id']) in chosen]
        if not local: continue
        affected.append(ident); c = _cell(q, ident); added = 0
        for row in local:
            did = row['device_id']; action = row['action']; owned = _owned(c, did)
            if any(s['layer'] in locked for s in owned): raise ValueError(c['name']+': unlock every layer of the affected footprint.')
            if action == 'remove':
                for inst in c.get('layout_instances', []):
                    if inst.get('device_id') == did:
                        masters=set(reachable(q,inst['cell'],physical=True))
                        if any(s['layer'] in locked for child in q['cells'] if child['id'] in masters for s in child['shapes']): raise ValueError('Unlock hierarchy layers before removing the orphan instance.')
                ids = {s['id'] for s in owned}; c['shapes'] = [s for s in c['shapes'] if s['id'] not in ids]
                for key in ('pdk_layouts', 'parametric_devices', 'layout_instances', 'layout_pins'):
                    if key in c: c[key] = [v for v in c[key] if v.get('device_id') != did]
            else:
                d = next(d for d in c['devices'] if d['id'] == did)
                x, y = origin[0]+added*pitch, origin[1]
                if row['recipe'] == 'hierarchy':
                    _check_instance(q, ident, d)
                    from .physical_cells import place
                    if action == 'add': place(q, ident, did, x, y)
                    i = next(i for i in c['layout_instances'] if i.get('device_id') == did)
                    affected_masters=set(reachable(q,i['cell'],physical=True)) | set(reachable(q,d['cell'],physical=True))
                    if any(s['layer'] in locked for cell in q['cells'] if cell['id'] in affected_masters for s in cell['shapes']): raise ValueError('Unlock hierarchy geometry layers before changing the link.')
                    i.update(cell=d['cell'], schematic_signature=electrical_signature(d))
                elif row['recipe'] == 'process':
                    if action == 'update':
                        from .layout_eco import regenerate
                        regenerate(q, ident, did)
                    else:
                        from .process_adapters import adapter
                        data = adapter(q['pdk']).implementation().mos(q['pdk'], _resolved(q, ident, d), x, y)
                        c['shapes'].extend(data['shapes']); c.setdefault('layout_pins', []).extend(data['pins']); c.setdefault('pdk_layouts', []).append(data['record'])
                else:
                    from .parametric import install
                    old = next((r for r in c.get('parametric_devices', []) if r.get('device_id') == did), None)
                    spec = clone(old['spec']) if old else {'x': x, 'y': y}
                    original = clone(d); resolved = _resolved(q, ident, d); d.clear(); d.update(resolved)
                    try: install(q, ident, did, spec)
                    finally: d.clear(); d.update(original)
                if any(s['layer'] in locked for s in _owned(c, did)): raise ValueError('Unlock every layer of the proposed footprint.')
                if action == 'add': added += 1
            changes.append({**row, 'action': action})
        if preserve_routes:
            routes.extend(_retarget(p, q, ident, {r['device_id'] for r in local}, locked))
            from .layout_topology import partition, _check_clearance
            before, after = partition(p, ident), partition(q, ident)
            anchors = {k for k in before if k[0] != 'shape'} & set(after)
            if any(before[k] & anchors != after[k] & anchors for k in anchors): raise ValueError('The update changes surviving terminal connectivity. Review with fixed route coordinates or adjust the routes.')
            _check_clearance(p, q, ident)
    validate(q)
    # Shared-master changes affect ancestor connectivity as well as edited cells.
    from .physical import connectivity
    findings = {}
    for ident in report['cells']:
        if ident in affected or any(child in affected for child in reachable(q, ident, physical=True)):
            try: findings[ident] = connectivity(q, ident)['issues']
            except ValueError as exc: findings[ident] = [{'code': 'ECO.CHECK_LIMIT', 'message': str(exc)}]
    report.update(changes=changes, affected_cells=affected, adjusted_routes=routes, connectivity=findings, after=inventory(q, cid, hierarchy))
    return q, report
