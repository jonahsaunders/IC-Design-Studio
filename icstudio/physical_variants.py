"""Atomic specialization and regeneration of parameterized physical hierarchies."""
from .model import clone, uid, digest, design_digest, flatten, validate
from .design_ops import parameters, value, resolved_device


def clone_master(source):
    mapping = {}
    def scan(obj):
        if isinstance(obj, dict):
            if 'id' in obj: mapping.setdefault(obj['id'], uid())
            for item in obj.values(): scan(item)
        elif isinstance(obj, list):
            for item in obj: scan(item)
    scan(source)
    def remap(obj):
        if isinstance(obj, dict): return {key: remap(item) for key, item in obj.items()}
        if isinstance(obj, list): return [remap(item) for item in obj]
        return mapping.get(obj, obj) if isinstance(obj, str) else obj
    return remap(source)


def electrical_signature(project, cid):
    fields = ('name', 'kind', 'nets', 'value', 'params', 'source', 'model_ref', 'model_params', 'native_spice')
    return [{key: d[key] for key in fields if key in d} for d in flatten(project, cid)]


def _hierarchy_hash(project, cid):
    """Include descendant edits, not just the immediate cell's saved identity."""
    by = {c['id']: c for c in project['cells']}; seen = set(); records = {}
    def walk(ident):
        if ident in seen: return
        seen.add(ident); cell = by[ident]
        records[ident] = {key: val for key, val in cell.items() if key != 'physical_variant'}
        for child in [d['cell'] for d in cell['devices'] if d['kind'] == 'X'] + [i['cell'] for i in cell.get('layout_instances', [])]:
            walk(child)
    walk(cid)
    return digest(records)


def _refresh_geometry(candidate, cid, created, sources, baseline, bindings):
    """Use the normal ECO safety checks; never bless copied stale geometry."""
    from .parametric import electrical_signature as signature
    from .layout_eco_hierarchy import inventory, propose as regenerate
    global_ = parameters(candidate.get('parameters', {}))
    by = {c['id']: c for c in candidate['cells']}
    for ident in created:
        target, source = by[ident], sources[ident]
        if not target['shapes'] and not target.get('layout_instances'): continue
        old_context = parameters(source.get('parameters', {}), global_)
        new_context = parameters(target.get('parameters', {}), global_)
        generated = {r.get('device_id') for key in ('pdk_layouts', 'parametric_devices') for r in target.get(key, [])}
        for old, new in zip(source['devices'], target['devices']):
            if new['kind'] == 'X' or new['kind'] in ('V', 'I'): continue
            if signature(resolved_device(old, old_context)) != signature(resolved_device(new, new_context)) and new['id'] not in generated:
                raise ValueError(target['name']+'/'+new['name']+': changed parameters have no regenerable footprint. Add a process or parametric recipe before automatic physical specialization.')
    rows = inventory(candidate, cid)['devices']
    selected = [(r['cell_id'], r['device_id']) for r in rows if r['cell_id'] in created and r['action'] in ('update', 'rebind')]
    # Rebinding a parent must run the same route and connectivity checks as a
    # device change, because regenerated child ports can move.
    selected += [(r['cell_id'], r['device_id']) for r in rows if r['action'] == 'rebind' and (r['cell_id'], r['device_id']) not in selected]
    result = candidate; changes = []
    if selected:
        # The specialization may bind a cached master whose ports have already
        # moved. Its baseline must be the original physical implementation, not
        # the newly rebound hierarchy passed to the generator.
        result, report = regenerate(candidate, cid, selected, preserve_routes=False)
        changes = report['changes']
    affected = {}
    for row in changes + bindings:
        affected.setdefault(row['cell_id'], set()).add(row['device_id'])
    from .physical_cells import reachable
    from .layout_eco_hierarchy import _retarget
    from .layout_topology import partition, _check_clearance
    from .route_constraints import enforce_affected
    for ident in reachable(result, cid):
        if ident not in affected: continue
        _retarget(baseline, result, ident, affected[ident], ())
        old, new = partition(baseline, ident), partition(result, ident)
        anchors = {key for key in old if key[0] != 'shape'} & set(new)
        if any(old[key] & anchors != new[key] & anchors for key in anchors):
            raise ValueError('Physical specialization changes surviving terminal connectivity. Review the routes and cell ports.')
        _check_clearance(baseline, result, ident)
    enforce_affected(baseline, result, list(affected), False)
    return result, changes


def propose(project, cid, *, regenerate=True, require_changes=True, device_ids=None):
    """Bind overrides to cached concrete masters in a reviewable transaction.

    Cache entries are reusable only while their source hierarchy, technology,
    global parameters, and generated implementation remain unchanged. Existing
    generated footprints are regenerated through the ordinary ECO checks;
    unsupported manual geometry fails without modifying the input project.
    """
    before = electrical_signature(project, cid)
    candidate = clone(project); baseline = clone(project); by = {c['id']: c for c in candidate['cells']}
    templates = {c['id']: clone(c) for c in project['cells']}
    global_ = parameters(candidate.get('parameters', {})); visited = set(); active = set(); rows = []
    context_hash = digest({'parameters': global_, 'pdk': candidate['pdk']})
    cache = {}; created = set(); sources = {}; reused = set()
    names = {c['name'].casefold() for c in candidate['cells']}
    source_hashes = {}
    def source_hash(ident):
        if ident not in source_hashes: source_hashes[ident] = _hierarchy_hash(project, ident)
        return source_hashes[ident]
    for cell in candidate['cells']:
        record = cell.get('physical_variant', {})
        source = record.get('source_cell')
        if (source in templates and record.get('geometry_refreshed') is True and record.get('context_hash') == context_hash and
                record.get('source_hash') == source_hash(source) and
                record.get('implementation_hash') == _hierarchy_hash(candidate, cell['id'])):
            cache[(source, digest(record.get('parameters', {})))] = cell['id']

    def walk(ident, depth=0):
        if depth > 12 or ident in active: raise ValueError('Recursive or excessively deep physical specialization hierarchy.')
        if ident in visited: return
        active.add(ident); cell = by[ident]
        context = parameters(cell.get('parameters', {}), global_)
        for d in cell['devices']:
            if d['kind'] != 'X': continue
            if ident == cid and device_ids is not None and d['id'] not in device_ids: continue
            source = templates.get(d['cell'], by[d['cell']])
            if d.get('native_spice', {}).get('parameters'):
                raise ValueError(d['name']+': native SPICE parameter overrides need an explicit native implementation before physical specialization.')
            defaults = parameters(source.get('parameters', {}), global_)
            actual = parameters({**source.get('parameters', {}),
                                 **{key: value(raw, context) for key, raw in d.get('parameters', {}).items()}}, global_)
            if actual != defaults:
                bound = {key: str(actual[key]) for key in source.get('parameters', {})}
                key = (source['id'], digest(bound))
                if key not in cache:
                    variant = clone_master(source); variant.pop('physical_variant', None)
                    stem = source['name'][:40]+'_p_'+key[1][:8]; name = stem; suffix = 1
                    while name.casefold() in names: suffix += 1; name = stem+'_'+str(suffix)
                    variant['name'] = name; names.add(name.casefold()); variant['parameters'] = bound
                    variant['physical_variant'] = {'source_cell': source['id'], 'source_hash': source_hash(source['id']),
                                                   'context_hash': context_hash, 'parameters': clone(bound)}
                    candidate['cells'].append(variant); by[variant['id']] = variant; cache[key] = variant['id']
                    baseline['cells'].append(clone(variant))
                    created.add(variant['id']); sources[variant['id']] = source
                else: reused.add(cache[key])
                target = by[cache[key]]
                rows.append({'cell_id': ident, 'device_id': d['id'], 'instance': cell['name']+'/'+d['name'],
                             'source': source['name'], 'variant': target['name'], 'parameters': actual})
                d['cell'] = target['id']; d['parameters'] = {}
                for inst in cell.get('layout_instances', []):
                    if inst.get('device_id') == d['id']: inst['cell'] = target['id']
                for bench in candidate.get('testbenches', []):
                    if bench['dut_instance'] == d['id']: bench['dut_cell'] = target['id']
            walk(d['cell'], depth+1)
        active.remove(ident); visited.add(ident)
    walk(cid)
    if not rows and require_changes: raise ValueError('This hierarchy has no differing parameter overrides to specialize.')
    validate(candidate)
    regenerated = []
    if regenerate and rows: candidate, regenerated = _refresh_geometry(candidate, cid, created, sources, baseline, rows)
    # Hash the completed hierarchy after nested specialization and regeneration.
    for cell in candidate['cells']:
        if cell['id'] in created:
            cell['physical_variant']['implementation_hash'] = _hierarchy_hash(candidate, cell['id'])
            cell['physical_variant']['geometry_refreshed'] = bool(regenerate)
    validate(candidate)
    if electrical_signature(candidate, cid) != before:
        raise ValueError('Specialization changed the resolved circuit. The candidate was rejected.')
    return candidate, {'design_hash': design_digest(project), 'candidate_hash': design_digest(candidate),
                       'cell_id': cid, 'variants': len(created), 'reused_variants': len(reused),
                       'instances': rows, 'regenerated': regenerated}


def materialize(project, cid, device_ids=None):
    """Prepare a parameter-correct hierarchy; safe to call when already concrete."""
    return propose(project, cid, device_ids=device_ids, require_changes=False)
