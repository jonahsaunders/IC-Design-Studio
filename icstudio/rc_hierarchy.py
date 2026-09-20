"""Flatten a reconciled schematic/layout hierarchy for interconnect estimation.

The original masters are never edited. Orthogonal route centerlines survive the
transform so resistance and coupling are extracted across instance boundaries.
Device recognition remains the responsibility of the process DRC/LVS flow.
"""
from .model import clone, digest, design_digest, validate
from .design_ops import parameters, resolved_device, value
from .physical_cells import ports, transform
from .layout import kdb


def flatten_for_rc(project, cell_id):
    p = clone(project)
    by = {c['id']: c for c in p['cells']}
    if cell_id not in by:
        raise ValueError('Unknown RC extraction cell.')
    from .inductor import reject_parasitic_estimate
    reject_parasitic_estimate(p, cell_id)
    db = kdb()
    globals_ = set(p.get('global_nets', [])) | {'0'}
    global_parameters = parameters(p.get('parameters', {}))
    devices, shapes, pins = [], [], []
    source_devices, source_shapes, occurrences = [], [], []
    root = by[cell_id]
    # Reserve all identifiers outside the replaced master as well as the root
    # names, so source IDs and deliberately similar names cannot collide.
    used_ids = set()
    def reserve(item):
        if isinstance(item, dict):
            if isinstance(item.get('id'), str): used_ids.add(item['id'])
            for v in item.values(): reserve(v)
        elif isinstance(item, list):
            for v in item: reserve(v)
    reserve(p)
    used_names = {d['name'].casefold() for d in root['devices']}
    used_nets = {n.casefold() for d in root['devices'] for n in d['nets'].values()} | {n.casefold() for n in globals_} | {n.casefold() for n in root['ports']}
    net_names = {}

    def unique(prefix, identity, used, casefold=False):
        base = prefix + digest([cell_id, identity])[:32]
        result, suffix = base, 0
        while (result.casefold() if casefold else result) in used:
            suffix += 1; result = base + '_' + str(suffix)
        used.add(result.casefold() if casefold else result)
        return result

    def walk(cell, path, instance_names, tr, mapping, seen):
        if cell['id'] in seen or len(path) > 12:
            raise ValueError('Recursive or excessively deep RC hierarchy.')
        if cell.get('spice_statements') or cell.get('spice_parameters'):
            raise ValueError('Hierarchical calibrated RC does not flatten native SPICE scopes; use process extraction.')
        if 'wires' in cell:
            from .wiring import rebuild
            cell = clone(cell); rebuild(cell, p)
        context = parameters(cell.get('parameters', {}), global_parameters)
        def net(name):
            if not name: return ''
            if name in globals_: return name
            if name in mapping: return mapping[name]
            if not path: return name
            key = (tuple(path), name)
            if key not in net_names:
                net_names[key] = unique('rc_hn_', key, used_nets, True)
            return net_names[key]
        def point(pt):
            result = tr * db.Point(*pt)
            return [result.x, result.y]
        physical_ports = ports(p, cell['id'])
        if len(physical_ports) != len(cell['ports']) or {v['name'] for v in physical_ports} != set(cell['ports']):
            raise ValueError(cell['name'] + ': assign every physical port before hierarchical RC extraction.')
        children = {d['id']: d for d in cell['devices'] if d['kind'] == 'X'}
        placements = {}
        for inst in cell.get('layout_instances', []):
            did = inst.get('device_id')
            if did not in children or inst['cell'] != children[did]['cell']:
                raise ValueError(cell['name'] + ': every physical instance needs one matching schematic instance for calibrated RC.')
            if did in placements:
                raise ValueError(cell['name'] + ': duplicate physical placement for a schematic instance.')
            if inst.get('nx', 1) != 1 or inst.get('ny', 1) != 1:
                raise ValueError('Instantiate electrical arrays explicitly before hierarchical RC extraction.')
            placements[did] = inst
        if placements.keys() != children.keys():
            raise ValueError(cell['name'] + ': place every schematic instance before hierarchical RC extraction.')
        local_ids = {}
        for d in cell['devices']:
            if d['kind'] == 'X': continue
            if d.get('native_spice') or d['kind'] in ('XS', 'SPICE'):
                raise ValueError('Use process extraction for native SPICE devices in a physical hierarchy.')
            dd = resolved_device(d, context)
            if path:
                dd['id'] = unique('rh_d_', [path, d['id']], used_ids)
                dd['name'] = unique(d['kind'][0] + 'hier_', [path, d['id']], used_names, True)
            dd['nets'] = {pin: net(n) for pin, n in d['nets'].items()}
            dd.pop('terminal_ids', None)
            dd.pop('net_labels', None)
            devices.append(dd); local_ids[d['id']] = dd['id']
            source_devices.append({'device_id': dd['id'], 'source_device_id': d['id'],
                                   'source_cell_id': cell['id'], 'instance_path': clone(path),
                                   'display_path': '/'.join([*instance_names, d['name']])})
        for shape in cell['shapes']:
            s = clone(shape)
            if path: s['id'] = unique('rh_s_', [path, shape['id']], used_ids)
            s['points'] = [point(pt) for pt in shape['points']]
            if shape.get('holes'): s['holes'] = [[point(pt) for pt in hole] for hole in shape['holes']]
            s['net'] = net(shape.get('net', ''))
            for key in ('device_id', 'generated_device'):
                if s.get(key): s[key] = local_ids.get(s[key], '')
            # The flattened graph must use these resolved labels, not treat
            # them as annotations in a child coordinate system.
            s.pop('instance_path', None); s.pop('source_id', None)
            shapes.append(s)
            source_shapes.append({'shape_id': s['id'], 'source_shape_id': shape['id'],
                                  'source_cell_id': cell['id'], 'instance_path': clone(path)})
        for pin in cell.get('layout_pins', []):
            if pin['device_id'] in children: continue
            if pin['device_id'] not in local_ids:
                raise ValueError('Physical terminal references a missing primitive device.')
            pp = clone(pin)
            if path: pp['id'] = unique('rh_p_', [path, pin['id']], used_ids)
            pp['device_id'] = local_ids[pin['device_id']]; pp['point'] = point(pin['point'])
            pins.append(pp)
        for did, inst in placements.items():
            d = children[did]; child = by[d['cell']]
            defaults = parameters(child.get('parameters', {}), global_parameters)
            if any(key not in defaults or value(raw, context) != defaults[key] for key, raw in d.get('parameters', {}).items()):
                raise ValueError(d['name'] + ': instance overrides differ from its shared layout; create a concrete cell variant.')
            child_path = [*path, did]
            combined = tr * transform(inst)
            occurrences.append({'instance_path': child_path, 'placement_id': inst['id'], 'cell_id': child['id'],
                                'rotation': round(combined.angle) % 360, 'mirror': combined.is_mirror(),
                                'origin': [combined.disp.x, combined.disp.y]})
            walk(child, child_path, [*instance_names, d['name']], combined,
                 {pin: net(n) for pin, n in d['nets'].items()}, seen | {cell['id']})
        if len(devices) > 3000 or len(shapes) > 100000:
            raise ValueError('Hierarchical calibrated RC supports at most 3,000 primitive devices and 100,000 shapes; use process extraction for larger blocks.')

    walk(root, [], [], db.ICplxTrans(), {}, set())
    # Keep all original masters in the run clone for saved fixture references.
    # Only the selected implementation is flattened. Its root identity and
    # interface remain unchanged, so the same saved bench still applies.
    replacement = {'id': root['id'], 'name': root['name'], 'ports': clone(root['ports']),
                   'devices': devices, 'shapes': shapes, 'layout_pins': pins,
                   'layout_ports': ports(p, cell_id)}
    p['cells'] = [replacement if c['id'] == cell_id else c for c in p['cells']]
    validate(p)
    provenance = {'schema': 1, 'flattened_design_hash': design_digest(p), 'occurrences': occurrences,
                  'devices': source_devices, 'shapes': source_shapes,
                  'scope': 'Linked orthogonal placements with shared-master dimensions; route paths and cross-instance coupling retained.'}
    return p, provenance
