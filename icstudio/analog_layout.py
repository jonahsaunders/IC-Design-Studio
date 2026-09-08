"""Bounded editable SKY130 equal-device current mirror, in integer nanometres."""
from .model import clone, uid, validate, digest
from .layout import rect, polygon
from .sky130_layout import layers, specification, resolved, install_mos
from .physical_cells import assign_port


def mirror_devices(p, cid):
    c = next(c for c in p['cells'] if c['id'] == cid)
    if len(c['devices']) != 2 or any(d['kind'] != 'NMOS' for d in c['devices']):
        raise ValueError('The mirror recipe needs exactly two standard SKY130 NMOS devices.')
    ds = [resolved(p, cid, d) for d in c['devices']]
    refs = [d for d in ds if d['nets']['d'] == d['nets']['g']]
    if len(refs) != 1: raise ValueError('Connect exactly one reference device as a diode.')
    a = refs[0]; b = next(d for d in ds if d['id'] != a['id'])
    sa, sb = [specification(p['pdk'], d) for d in (a, b)]
    if sa['dimensions_nm'] != sb['dimensions_nm'] or sa['values'] != sb['values'] or int(sa['values'].get('nf', 1)) != 1:
        raise ValueError('This matching recipe requires equal W/L, equal parameters and one finger per device.')
    ns = a['nets']; nb = b['nets']
    if not (ns['s'] == ns['b'] == nb['s'] == nb['b'] and ns['g'] == nb['g']
            and len({ns['s'], ns['g'], nb['d']}) == 3
            and set(c['ports']) == {ns['s'], ns['g'], nb['d']}):
        raise ValueError('Expose reference, output and common source/body ports for a 1:1 NMOS mirror.')
    return a, b


def generate_mirror(p, cid, replace=False):
    a, b = mirror_devices(p, cid); c = next(c for c in p['cells'] if c['id'] == cid)
    if c['shapes'] or c.get('layout_instances'):
        if not replace or not c.get('mirror_layout'):
            raise ValueError('Existing layout can only be replaced by reviewing regeneration of this mirror recipe.')
    for key in ('shapes', 'layout_pins', 'layout_ports', 'layout_texts', 'layout_instances', 'pdk_layouts'):
        c[key] = []
    ls = layers(p['pdk']); size = specification(p['pdk'], a)['dimensions_nm']
    pitch = size['l'] + 7000
    for d, x in ((a, 0), (b, pitch)): install_mos(p, cid, d['id'], x, 0)
    pins = {(r['device_id'], r['pin']): r['point'] for r in c['layout_pins']}
    def wire(layer, points, net):
        points = [list(v) for i,v in enumerate(points) if not i or list(v) != list(points[i-1])]
        c['shapes'].append({'id': uid(), 'kind': 'path', 'layer': ls[layer], 'points': points,
                            'width': 340, 'net': net, 'device_id': '', 'generated_route': True})
    for d in (a, b):
        for pin in ('s', 'b'):
            pt = pins[d['id'], pin]; wire('m1', [pt, [pt[0], -2200]], a['nets']['s'])
    wire('m1', [[pins[a['id'], 'b'][0], -2200], [pins[b['id'], 's'][0], -2200]], a['nets']['s'])
    ga, gb = pins[a['id'], 'g'], pins[b['id'], 'g']
    wire('m2', [ga, gb], a['nets']['g'])
    dr = pins[a['id'], 'd']; diode = [dr[0], ga[1]]
    wire('m1', [dr, diode], a['nets']['g'])
    for pt in (ga, gb, diode):
        for key, half in (('via', 75), ('m1', 170), ('m2', 170)):
            c['shapes'].append(rect(ls[key], pt[0]-half, pt[1]-half, 2*half, 2*half,
                                    net=a['nets']['g'] if key != 'via' else ''))
    output = pins[b['id'], 'd']; end = [output[0], size['w']+1500]
    wire('m1', [output, end], b['nets']['d'])
    for net, layer, pt in ((a['nets']['g'], 'm2', ga), (b['nets']['d'], 'm1', end),
                            (a['nets']['s'], 'm1', [pins[a['id'], 'b'][0], -2200])):
        assign_port(p, cid, net, ls[layer], pt)
    c['mirror_layout'] = {'api': 1, 'device_ids': [a['id'], b['id']],
                         'matching': 'equal_geometry_and_orientation', 'pitch_nm': pitch,
                         'notes': 'Equal W/L and orientation; corresponding terminals share a transverse axis. No statistical mismatch qualification.'}
    validate(p); return p


def matching_findings(p, cid):
    """Check actual footprint polygons and terminal alignment after user edits."""
    c = next(c for c in p['cells'] if c['id'] == cid); recipe = c.get('mirror_layout')
    if not recipe: return []
    issues = []
    def issue(code, obj, message):
        issues.append({'severity': 'error', 'code': code, 'cell_id': cid, 'object': obj,
                       'message': message, 'fingerprint': digest([cid, code, obj, message])})
    try: a, b = mirror_devices(p, cid)
    except ValueError as exc:
        issue('MATCH.DEVICES', '', str(exc)); return issues
    # Source-to-drain vectors define the device orientation, including a whole-cell transform.
    pins = {(v['device_id'], v['pin']): v['point'] for v in c.get('layout_pins', [])}
    try:
        start, other = pins[a['id'], 's'], pins[b['id'], 's']
        delta = [other[i]-start[i] for i in (0, 1)]
        vector = [pins[a['id'], 'd'][i]-start[i] for i in (0, 1)]
        if vector[0]*delta[1] != vector[1]*delta[0] or not any(delta):
            issue('MATCH.ALIGNMENT', b['id'], 'Matched device terminals are no longer on a common source-to-drain axis.')
        normalized = []
        from .layout import kdb
        for d, origin in ((a, start), (b, other)):
            regions = {}
            for s in c['shapes']:
                if s.get('generated_device') == d['id']:
                    regions.setdefault(s['layer'], kdb().Region()).insert(polygon(s).transformed(kdb().Trans(-origin[0], -origin[1])))
            normalized.append(regions)
        if not normalized[0] or set(normalized[0]) != set(normalized[1]) or any(
                not (r ^ normalized[1][layer]).is_empty() for layer,r in normalized[0].items()):
            issue('MATCH.GEOMETRY', b['id'], 'Matched footprints differ in shape or orientation. Restore equal geometry or regenerate the pair.')
    except KeyError:
        issue('MATCH.TERMINALS', '', 'A matched device terminal is missing.')
    return issues
