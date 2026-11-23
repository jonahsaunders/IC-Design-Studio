"""Small editable layout labs for integration, signoff concepts and stream review."""

from collections import Counter
from functools import lru_cache
import math
from pathlib import Path

from .layout import drc, kdb, polygon, rect
from .model import clone, design_digest, device, example, file_digest, now, scalar, uid, validate


SHARED = {'floorplan', 'access', 'handoff'}
LABS = SHARED | {'pad-ring', 'density', 'antenna', 'via-current', 'isolation', 'spiral'}
FIXTURES = (LABS - SHARED) | {'macro'}
MACRO_PORTS = ('IN', 'OUT', 'G1', 'G2', 'VSS')
DENSITY_BOX = (0, 0, 40000, 20000)


def fixture(lab):
    return 'macro' if lab in SHARED else lab


def _cell(p, name=None):
    field, value = ('name', name) if name else ('id', p['top'])
    c = next((v for v in p['cells'] if v[field] == value), None)
    if c is None:
        raise ValueError('Restore the original lesson cell.')
    return c


def _path(c, net, points, width=400, layer='metal1', key=None):
    c['shapes'].append(dict(id=key or uid(), kind='path', layer=layer, points=[list(pt) for pt in points],
                            width=width, net=net, device_id=''))


def _rect(c, layer, x, y, w, h, *, key=None, net=''):
    shape = rect(layer, x, y, w, h, net=net)
    if key:
        shape['id'] = key
    c['shapes'].append(shape)
    return shape


def _shape(c, key):
    shape = next((s for s in c['shapes'] if s['id'] == key), None)
    if shape is None:
        raise ValueError('Keep the original ' + key.replace('_', ' ') + '.')
    return shape


def _layer(p, name, gds, color, width=150, space=150, datatype=0):
    p['pdk']['layers'].append(dict(name=name, gds=gds, datatype=datatype, color=color, width=width, space=space))


def _guard_layers(layers, locked):
    if set(layers) & set(locked):
        raise ValueError('Unlock the lesson layers before editing this geometry.')


def _wire_pins(c, d, landings):
    for pin, (layer, x, y) in landings.items():
        c['layout_pins'].append(dict(id=uid(), device_id=d['id'], pin=pin, layer=layer, point=[x, y]))


def _basic(key):
    p = example('empty')
    c = _cell(p)
    c.update(name='layout_' + key.replace('-', '_'), layout_pins=[])
    p['name'] = 'Layout lab · ' + key.replace('-', ' ').title()
    p['student_layout_signoff'] = dict(version=1, fixture=key)
    return p, c


def _core(p, c):
    from .catalog import link_technology
    from .gf180_layout import install_mos, layers
    from .physical_cells import assign_port
    from .student_layout_labs import _gf180, _mos

    link_technology(p, clone(_gf180()))
    core = dict(id=uid(), name='pass_device', ports=[], devices=[], shapes=[], layout_pins=[])
    p['cells'].append(core)
    d = _mos(core, p)
    install_mos(p, core['id'], d['id'])
    metal = layers(p['pdk'])['m1']
    routes = {'d': [(5000, 1000)], 's': [(-500, 3500), (-5000, 3500)],
              'g': [(140, -3500)], 'b': [(-4200, 1000), (-4200, -5500)]}
    for pin in core['layout_pins']:
        net = d['nets'][pin['pin']]
        route = routes[pin['pin']]
        _path(core, net, [pin['point'], *route], layer=metal)
        x, y = route[-1]
        _rect(core, metal, x - 300, y - 300, 600, 600, net=net)
        assign_port(p, core['id'], net, metal, [x, y])
    c['name'] = 'pass_macro'
    c['ports'] = list(MACRO_PORTS)
    c['devices'] = [
        device('X', 'X1', 300, 220, cell=core['id'], nets=dict(SOURCE='IN', OUT='mid', GATE='G1', BODY='VSS')),
        device('X', 'X2', 580, 220, cell=core['id'], nets=dict(SOURCE='mid', OUT='OUT', GATE='G2', BODY='VSS')),
    ]
    _rect(c, metal, 7450, -1700, 1150, 7800, key='channel_blockage')
    place_macro(p, 30000, 8000)


def _macro_pins(p):
    from .physical_cells import instance_pins
    c = _cell(p)
    by_id = {d['id']: d['name'] for d in c['devices']}
    return {(by_id[pin['device_id']], pin['pin']): pin for pin in instance_pins(p, c['id'])}


def place_macro(p, pitch_nm, offset_nm, locked=()):
    from .gf180_layout import layers
    from .physical_cells import assign_port, place

    c = _cell(p)
    metal = layers(p['pdk'])['m1']
    _guard_layers((metal,), locked)
    if any(s.get('via_group') or s.get('net') == 'mid' for s in c['shapes']):
        raise ValueError('Undo the pin route before trying a different floorplan.')
    has_out_label = any(label['text'] == 'OUT' for label in c.get('layout_texts', []))
    c['shapes'] = [s for s in c['shapes'] if s['id'] != 'macro_return']
    c['layout_instances'] = []
    for d, (x, y) in zip(c['devices'], ((0, 0), (pitch_nm, offset_nm))):
        place(p, c['id'], d['id'], x, y)
    pins = _macro_pins(p)
    a, b = [pins[name, 'BODY']['point'] for name in ('X1', 'X2')]
    return_points = [a, b] if a[1] == b[1] else [a, [a[0], min(a[1], b[1]) - 1000],
                                                 [b[0], min(a[1], b[1]) - 1000], b]
    _path(c, 'VSS', return_points, layer=metal, key='macro_return')
    for port, target in zip(MACRO_PORTS, (('X1','SOURCE'), ('X2','OUT'), ('X1','GATE'), ('X2','GATE'), ('X1','BODY'))):
        pin = pins[target]
        assign_port(p, c['id'], port, pin['layer'], pin['point'])
    # This is the staged stream fault, separate from the physical port assignment.
    if not has_out_label:
        c['layout_texts'] = [label for label in c['layout_texts'] if label['text'] != 'OUT']


def current_placement(p):
    instance = _cell(p)['layout_instances'][1]
    return instance['x'], instance['y']


def plan_macro(p, multilayer, locked=()):
    from .gf180_layout import layers
    from .layout_routing import install, plan

    c = _cell(p)
    pins = _macro_pins(p)
    metal = layers(p['pdk'])
    _guard_layers((metal['m1'],), locked)
    if any(s.get('net') == 'mid' for s in c['shapes']):
        raise ValueError('Undo the existing internal route before planning another one.')
    layers_used = [metal['m1'], metal['m2']] if multilayer else [metal['m1']]
    start, end = pins['X1', 'OUT'], pins['X2', 'SOURCE']
    proposal = plan(p, c['id'], start, end, 'mid', 400, layers_used, margin=7500, locked=locked)
    install(p, proposal, locked)


def add_stream_label(p, choice):
    from .physical_cells import assign_port
    c = _cell(p)
    port = next(port for port in c['layout_ports'] if port['name'] == choice)
    assign_port(p, c['id'], choice, port['layer'], port['point'])


def _macro_metrics(p, routed=False):
    from .design_ops import flatten_layout
    from .gf180_layout import audit, layers
    from .layout_routing import length
    from .physical import connectivity
    from .physical_cells import audit as physical_audit

    c = _cell(p)
    core = _cell(p, 'pass_device')
    nets = {'X1': dict(SOURCE='IN', OUT='mid', GATE='G1', BODY='VSS'),
            'X2': dict(SOURCE='mid', OUT='OUT', GATE='G2', BODY='VSS')}
    if (p['pdk'].get('package_lock', {}).get('id') != 'gf180mcuC' or c['ports'] != list(MACRO_PORTS)
            or {d['name']: d['nets'] for d in c['devices']} != nets
            or len(c.get('layout_instances', [])) != 2
            or any(i['cell'] != core['id'] for i in c['layout_instances']) or audit(p, core['id'])):
        raise ValueError('Keep the two linked GF180 devices and the original macro interface.')
    if physical_audit(p, c['id']):
        raise ValueError('Resolve the physical hierarchy and port findings.')
    geometry = drc(p, c['id'])
    if geometry:
        raise ValueError('Resolve geometry DRC before continuing. ' + geometry[0]['message'])
    regions = [polygon(s).bbox() for s in flatten_layout(p, c['id'])]
    area = (max(b.right for b in regions) - min(b.left for b in regions)) * (max(b.top for b in regions) - min(b.bottom for b in regions)) / 1e6
    pins = _macro_pins(p)
    distance = sum(abs(a - b) for a, b in zip(pins['X1','OUT']['point'], pins['X2','SOURCE']['point'])) / 1000
    values = {'Footprint (µm²)': round(area, 2), 'Pin-to-pin Manhattan distance (µm)': round(distance, 3)}
    if routed:
        check = connectivity(p, c['id'])
        issues = check['issues']
        if issues:
            raise ValueError(issues[0]['message'])
        if any(_net_at(check['net_regions'], port['layer'], port['point']) != {port['name']} for port in c['layout_ports']):
            raise ValueError('Place each external port on the conductor that reaches its schematic net.')
        mid = [s for s in c['shapes'] if s.get('net') == 'mid']
        distance_um = length(mid) / 1000
        vias = sum(s['layer'] == layers(p['pdk'])['via'] for s in mid)
        if not 0 < distance_um <= 14 or vias > 2 or area > 345:
            raise ValueError(f'Current layout uses {distance_um:g} µm of route, {vias} vias, and {area:.1f} µm². Meet 14 µm, two vias and 345 µm².')
        values.update({'Internal route length (µm)': distance_um, 'Route vias': vias})
    return values


def project(key):
    p, c = _basic(key)
    if key == 'macro':
        _core(p, c)
    else:
        _BUILDERS[key](p, c)
    return validate(p)


def focus(p, lab, step):
    if p.get('student_layout_signoff') != dict(version=1, fixture=fixture(lab)):
        raise ValueError('Open or resume this Layout lesson from the Student Hub.')
    if lab == 'spiral' and step in ('reference', 'candidate'):
        return _cell(p, 'spiral_' + step)['id']
    if lab == 'antenna' and step in ('jumper', 'diode'):
        return _cell(p, 'antenna_' + step)['id']
    return p['top']


PAD_SITES = {'PWR': (-12000, 11500), 'GND': (12000, -11500), 'INA': (-16000, 4000),
             'INB': (-16000, -4000), 'Y': (16000, 4000)}


def _generic_port_layer(p):
    _layer(p, 'metal1_pin', 4, '#8dbffa', 0, 0, 5)


def _pad_ring(p, c):
    _generic_port_layer(p)
    _layer(p, 'core_boundary', 86, '#8d97ad', 0, 0)
    _rect(c, 'core_boundary', -6600, -7000, 13200, 14000)
    branches = {'PWR': [(-12000, 9000), (-4500, 9000), (-4500, 6000)],
                'GND': [(12000, -9000), (4500, -9000), (4500, -6000)],
                'INA': [(-5500, 4000)], 'INB': [(-5500, -4000)], 'Y': [(5500, 4000)]}
    for index, (net, (x, y)) in enumerate(PAD_SITES.items()):
        # The internal end models a terminal on the block, the outer metal is a pad.
        end_x, end_y = branches[net][-1]
        _rect(c, 'metal1', x - 1200, y - 1200, 2400, 2400, key='pad_' + net)
        _rect(c, 'metal1', end_x - 350, end_y - 350, 700, 700)
        _path(c, net, [(x, y), *branches[net]], width=500)
        d = device('V', 'V_' + net, 120 + index * 155, 230, nets={'p': net, 'n': '0'}, value='0')
        c['devices'].append(d)
        _wire_pins(c, d, {'p': ('metal1', end_x, end_y)})
    c['ports'] = list(PAD_SITES)
    for name, site in (('INA', 'INB'), ('INB', 'INA'), ('Y', 'Y')):
        assign_ring_port(p, name, site)


def assign_ring_port(p, name, site):
    from .physical_cells import assign_port
    assign_port(p, p['top'], name, 'metal1', list(PAD_SITES[site]))


def _net_at(groups, layer, point):
    query = kdb().Point(*point)
    return {group['net'] for group in groups for s in group['shapes']
            if s['layer'] == layer and polygon(s).inside(query)}


def _connected(p):
    from .physical import connectivity
    issues = drc(p, p['top'])
    if issues:
        raise ValueError('Resolve geometry DRC. ' + issues[0]['message'])
    check = connectivity(p, p['top'])
    if check['issues']:
        raise ValueError(check['issues'][0]['message'])
    return check['net_regions']


def _pad_measure(p, step):
    c = _cell(p)
    groups = _connected(p)
    if c['ports'] != list(PAD_SITES):
        raise ValueError('Keep the original five circuit terminals.')
    port_map = {port['name']: _net_at(groups, port['layer'], port['point']) for port in c.get('layout_ports', [])}
    missing = [name for name in PAD_SITES if name not in port_map]
    crossed = [name for name in port_map if port_map[name] != {name}]
    if step == 'trace':
        if set(missing) != {'PWR', 'GND'} or set(crossed) != {'INA', 'INB'}:
            raise ValueError('Capture the original missing supply assignments and swapped inputs first.')
        return {'Unassigned supply pads': missing, 'Incorrect signal pads': crossed}
    if missing or crossed:
        raise ValueError('Unassigned: ' + (', '.join(missing) or 'none') + '. Incorrect: ' + (', '.join(crossed) or 'none') + '.')
    if any(tuple(port['point']) != PAD_SITES[port['name']] for port in c['layout_ports']):
        raise ValueError('Place port labels on the five perimeter landing pads.')
    return {'Verified pad-to-block connections': len(PAD_SITES)}


def _density(p, c):
    _rect(c, 'metal1', 1000, 1000, 15000, 9000, key='left_density_metal')
    _path(c, 'sense', ((21200, 10000), (38800, 10000)), width=600, key='sensitive_route')


def add_fill(p, keepout_nm, locked=()):
    from .layout_inspection import fill
    c = _cell(p)
    _guard_layers(('metal1',), locked)
    # Reuse the production fill planner, replacing only its earlier lesson batch.
    c['shapes'] = [s for s in c['shapes'] if not s.get('student_fill')]
    added = set(fill(p, c['id'], 'metal1', (20200, 0, 40000, 20000),
                     size=2400, pitch=3200, keepout=keepout_nm, locked=locked))
    _cell(p)['shapes'] = [dict(s, student_fill=True) if s['id'] in added else s for s in _cell(p)['shapes']]


def _density_measure(p, step):
    from .layout_inspection import density
    c = _cell(p)
    issues = drc(p, c['id'])
    if issues:
        raise ValueError('Resolve geometry DRC. ' + issues[0]['message'])
    left, right = [d['density'] * 100 for d in density(p, c['id'], 'metal1', DENSITY_BOX, 20000)['rows']]
    conductor = _shape(c, 'sensitive_route')
    if conductor['kind'] != 'path' or conductor['points'] != [[21200, 10000], [38800, 10000]] or conductor['width'] != 600:
        raise ValueError('Keep the sensitive route fixed so both fill cases use the same signal geometry.')
    signal = polygon(conductor).bbox()
    loading = 0.0
    for s in c['shapes']:
        if s['layer'] != 'metal1' or s['id'] in ('sensitive_route', 'left_density_metal'):
            continue
        b = polygon(s).bbox()
        overlap = max(0, min(signal.right, b.right) - max(signal.left, b.left))
        space = max(b.bottom - signal.top, signal.bottom - b.top)
        if overlap and 0 < space <= 5000:
            # Declared 0.1 fF/µm at a 1 µm gap, treating fill as AC ground.
            loading += 0.1 * overlap / space
    if step == 'scan' and right >= 22:
        raise ValueError('Capture the original underfilled right window before adding fill.')
    if step == 'close-fill' and not (22 <= right <= 65 and loading > 1.4):
        raise ValueError(f'Right density {right:.1f}%, load estimate {loading:.2f} fF. Try a smaller keepout for the close-fill comparison.')
    if step == 'repair' and not (22 <= left <= 65 and 22 <= right <= 65 and loading <= 1.4):
        raise ValueError(f'Right density {right:.1f}%, load estimate {loading:.2f} fF. Meet 22–65% and at most 1.4 fF.')
    return {'Left density (%)': round(left, 2), 'Right density (%)': round(right, 2),
            'Estimated fill loading (fF)': round(loading, 3)}


def _antenna(p, c):
    from .student_layout_labs import _cell as new_cell
    _layer(p, 'gate_area', 85, '#f29fa9', 150, 150)
    for name in ('jumper', 'diode'):
        other = new_cell('antenna_' + name)
        p['cells'].append(other)
    for cell in p['cells']:
        _rect(cell, 'gate_area', -500, -500, 1000, 1000)
        for x in (0, 40000):
            _rect(cell, 'metal1', x - 400, -400, 800, 800)
        for name, x, schematic_x in (('VGATE', 0, 160), ('VINPUT', 40000, 390)):
            d = device('V', name, schematic_x, 250, value='0', nets={'p': 'gate', 'n': '0'})
            cell['devices'].append(d)
            _wire_pins(cell, d, {'p': ('metal1', x, 0)})
        _path(cell, 'gate', [(0, 0), (40000, 0)], width=600)
        cell['shapes'][-1]['student_antenna_route'] = True


def repair_antenna(p, cid, method, locked=()):
    from .layout_routing import via_recipes, via_shapes
    c = next(c for c in p['cells'] if c['id'] == cid)
    if any(s.get('student_antenna_repair') for s in c['shapes']):
        raise ValueError('Undo the last repair before comparing another one in this cell.')
    touched = ('metal1', 'metal2', 'via1') if method == 'jumper' else ('metal1', 'active')
    _guard_layers(touched, locked)
    before = {s['id'] for s in c['shapes']}
    if method == 'jumper':
        c['shapes'] = [s for s in c['shapes'] if not s.get('student_antenna_route')]
        recipe = via_recipes(p['pdk'])[0]
        endpoints = ((2300, 0), (37700, 0))
        for endpoint in endpoints:
            c['shapes'].extend(via_shapes(recipe, endpoint, 'gate'))
        _path(c, 'gate', [(0, 0), endpoints[0]], 600)
        _path(c, 'gate', [endpoints[1], (40000, 0)], 600)
        _path(c, 'gate', endpoints, 600, 'metal2')
    else:
        d = device('D', 'DPROTECT', 630, 250, nets={'p': '0', 'n': 'gate'})
        c['devices'].append(d)
        if 'wires' in c:
            from .net_labels import add
            for pin, net in tuple(d['nets'].items()):
                add(c, net, dict(kind='pin', id=d['id'], pin=pin), p)
        _rect(c, 'active', 1500, -4500, 2000, 2000)
        _rect(c, 'metal1', 2200, -3350, 600, 600)
        _rect(c, 'metal1', 4200, -3350, 600, 600)
        _path(c, 'gate', [(2500, 0), (2500, -3050)], width=400)
        _wire_pins(c, d, {'p': ('metal1', 4500, -3050), 'n': ('metal1', 2500, -3050)})
    for s in c['shapes']:
        if s['id'] not in before:
            s['student_antenna_repair'] = True


def _antenna_measure(p, cid, step):
    from .physical import connectivity
    db = kdb()
    c = next(c for c in p['cells'] if c['id'] == cid)
    if drc(p, cid):
        raise ValueError('Resolve geometry findings in the antenna exercise.')
    check = connectivity(p, cid)
    if check['issues']:
        raise ValueError(check['issues'][0]['message'])
    gate = next(g for g in check['net_regions'] if g['net'] == 'gate')
    area = db.Region([polygon(s) for s in gate['shapes'] if s['layer'] == 'metal1']).merged().area() / 1e6
    gate_area = db.Region([polygon(s) for s in c['shapes'] if s['layer'] == 'gate_area']).merged().area()/1e6
    if not math.isclose(gate_area, 1):
        raise ValueError('Keep the original 1 µm² gate.')
    ratio = area / gate_area
    diode = any(d['kind'] == 'D' and d['nets'] == {'p': '0', 'n': 'gate'} for d in c['devices'])
    limit = 32 if diode else 12
    if step == 'fault' and (ratio <= 12 or diode):
        raise ValueError('Measure the original unprotected route first.')
    if step == 'jumper' and (ratio > limit or diode or not any(s['layer']=='via1' for s in c['shapes'])):
        raise ValueError('Use a connected layer jump and bring the early metal ratio to 12 or lower.')
    if step == 'diode' and (not diode or not 12 < ratio <= limit):
        raise ValueError('Keep the long lower-layer wire and connect the exercise diode to pass the protected limit.')
    return {'Early metal area (µm²)': round(area, 3), 'Area ratio': round(ratio, 3), 'Teaching limit': limit}


def _via_current(p, c):
    for layer in ('metal1', 'metal2'):
        _rect(c, layer, 18900, -1100, 2200, 2200, key=layer + '_via_landing')
    _path(c, 'rail', ((0, 0), (20000, 0)), 1000, 'metal1', 'via_feed')
    _path(c, 'rail', ((20000, 0), (40000, 0)), 1000, 'metal2', 'via_load')
    for kind, name, layer, x, value, schematic_x in (('V', 'VDD', 'metal1', 0, '1.8', 160),
                                                    ('I', 'ILOAD', 'metal2', 40000, '1.2m', 410)):
        _rect(c, layer, x - 550, -550, 1100, 1100)
        d = device(kind, name, schematic_x, 250, value=value, nets={'p': 'rail', 'n': '0'})
        c['devices'].append(d)
        _wire_pins(c, d, {'p': (layer, x, 0)})
    _rect(c, 'via1', 19925, -75, 150, 150, key='current_cut')
    c['shapes'][-1]['student_via_array'] = True


def set_via_array(p, rows, columns, locked=()):
    c = _cell(p)
    if not 1 <= rows <= 4 or not 1 <= columns <= 4:
        raise ValueError('Use one to four rows and columns.')
    _guard_layers(('via1',), locked)
    c['shapes'] = [s for s in c['shapes'] if not s.get('student_via_array')]
    for row in range(rows):
        for column in range(columns):
            x = 20000 + 400 * column - 200 * (columns - 1)
            y = 400 * row - 200 * (rows - 1)
            s = _rect(c, 'via1', x - 75, y - 75, 150, 150)
            s['student_via_array'] = True


def _via_measure(p, step):
    from .layout_routing import length
    _connected(p)
    c = _cell(p)
    load = next(d for d in c['devices'] if d['name'] == 'ILOAD')
    if load['kind'] != 'I' or load['nets'] != {'p': 'rail', 'n': '0'} or not math.isclose(scalar(load['value']), .0012):
        raise ValueError('Keep the original 1.2 mA load.')
    cut_polygons = [polygon(s) for s in c['shapes'] if s['layer'] == 'via1']
    cuts = [poly.bbox() for poly in cut_polygons]
    landings = [polygon(_shape(c, layer + '_via_landing')).bbox() for layer in ('metal1', 'metal2')]
    if not cuts or any(b.width() != 150 or b.height() != 150 or
                       any(min(b.left-a.left, a.right-b.right, b.bottom-a.bottom, a.top-b.top) < 75 for a in landings)
                       for b in cuts):
        raise ValueError('Use equally sized 0.15 µm cuts with 75 nm minimum enclosure in both metal landings.')
    if len(list(kdb().Region(cut_polygons).merged().each())) != len(cuts):
        raise ValueError('Each via cut must be physically distinct.')
    current = 1.2 / len(cuts)
    feed = [_shape(c, key) for key in ('via_feed', 'via_load')]
    resistance = sum(.04 * length([s]) / s['width'] for s in feed) + .08 / len(cuts)
    drop = resistance * 1.2
    if drop > 10 or (step == 'diagnose' and current <= .45) or (step == 'repair' and current > .45):
        raise ValueError(f'Drop {drop:.2f} mV, cut current {current:.3f} mA. The cut limit is 0.45 mA and the drop limit is 10 mV.')
    return {'Legal via cuts': len(cuts), 'Equal-share current per cut (mA)': round(current, 3),
            'Estimated voltage drop (mV)': round(drop, 3)}


SIDE_BOXES = {'bottom': (-6000, -6000, 12000, 600), 'top': (-6000, 5400, 12000, 600),
              'left': (-6000, -5400, 600, 10800), 'right': (5400, -5400, 600, 10800)}
TAP_POINTS = ((0, 5700), (5700, 5700), (5700, 0), (5700, -5700),
              (0, -5700), (-5700, -5700), (-5700, 0), (-5700, 5700))


def _isolation(p, c):
    _layer(p, 'quiet_block', 86, '#a2aefc', 0, 0)
    _rect(c, 'quiet_block', -3000, -3000, 6000, 6000, key='quiet_block')
    for side in ('bottom', 'left', 'right'):
        add_guard_side(p, side)
    set_taps(p, 2)
    _rect(c, 'metal1', -9800, -400, 800, 800)
    _path(c, 'quiet', ((-9400, 0), (-5700, 0)), 400)
    _path(c, 'switch', ((8800, -4500), (8800, 4500)), 500)
    for pin, letter, location, schematic_x in (('quiet', 'VQUIET', (-9400, 0), 160),
                                             ('switch', 'VCLOCK', (8800, 0), 410)):
        d = device('V', letter, schematic_x, 250, value='0', nets={'p': pin, 'n': '0'})
        c['devices'].append(d)
        _wire_pins(c, d, {'p': ('metal1', *location)})


def add_guard_side(p, side, locked=()):
    c = _cell(p)
    _guard_layers(('active', 'metal1'), locked)
    if any(s['id'] == 'guard_metal_' + side for s in c['shapes']):
        raise ValueError('That side is already present. Identify the gap in the ring.')
    for layer, role in (('active', 'guard_active_'), ('metal1', 'guard_metal_')):
        _rect(c, layer, *SIDE_BOXES[side], key=role + side)


def set_taps(p, count, locked=()):
    c = _cell(p)
    _guard_layers(('contact',), locked)
    if count not in (2, 4, 8):
        raise ValueError('Compare two, four or eight uniformly spaced contacts.')
    c['shapes'] = [s for s in c['shapes'] if not s.get('student_guard_tap')]
    # The two-contact starter uses the two already built sidewalls.
    points = (TAP_POINTS[2], TAP_POINTS[6]) if count == 2 else TAP_POINTS[::8//count]
    for x, y in points:
        cut = _rect(c, 'contact', x - 100, y - 100, 200, 200)
        cut['student_guard_tap'] = True


def _isolation_measure(p, step):
    c = _cell(p)
    db = kdb()
    groups = _connected(p)
    block = polygon(_shape(c, 'quiet_block'))
    masks = {layer: db.Region([polygon(s) for s in c['shapes'] if s['id'].startswith(prefix)]).merged()
             for layer, prefix in (('metal1', 'guard_metal_'), ('active', 'guard_active_'))}
    surrounded = all(any((db.Region(block)-db.Region(db.Polygon(list(poly.each_point_hole(i))))).is_empty()
                         for poly in region.each() for i in range(poly.holes())) for region in masks.values())
    if not surrounded:
        raise ValueError('Close the ring on both active and metal around the quiet block.')
    if _net_at(groups, 'metal1', [0, 5700]) != {'quiet'}:
        raise ValueError('Connect the metal ring to the quiet return, separate from the switching net.')
    if step == 'ring':
        return {'Enclosed quiet block': True, 'Verified ring net': 'quiet'}
    taps = [polygon(s) for s in c['shapes'] if s['layer'] == 'contact']
    locations = {tuple((poly.bbox().center().x, poly.bbox().center().y)) for poly in taps}
    if len(taps) != len(locations) or not locations or not locations <= set(TAP_POINTS):
        raise ValueError('Use distinct contacts on the marked perimeter sites.')
    if any(any(not (db.Region(tap)-mask).is_empty() for mask in masks.values()) or
           _net_at(groups, 'metal1', [tap.bbox().center().x, tap.bbox().center().y]) != {'quiet'} for tap in taps):
        raise ValueError('Every contact needs active coverage, metal coverage and a quiet return.')
    indices = sorted(TAP_POINTS.index(point) for point in locations)
    intervals = [b - a for a, b in zip(indices, indices[1:] + [indices[0] + len(TAP_POINTS)])]
    pitch = 5.7 * max(intervals)
    if pitch > 12:
        raise ValueError(f'The largest contact gap along the ring is {pitch:g} µm. Meet the 12 µm teaching limit.')
    return {'Connected contacts': len(taps), 'Maximum perimeter gap (µm)': round(pitch, 2)}


def _spiral(p, c):
    from .inductor import defaults, install, plan
    from .student_layout_labs import _cell as new_cell
    p['pdk'].update(parasitics={'metal1': {'sheet_ohm': .09}, 'metal2': {'sheet_ohm': .045}},
                    via_resistance_ohm={'M1 to M2': .26})
    c['name'] = 'spiral_reference'
    candidate = new_cell('spiral_candidate')
    p['cells'].append(candidate)
    for cell in (c, candidate):
        spec = defaults(p)
        install(p, plan(p, cell['id'], spec))


def tune_spiral(p, cid, field, value, locked=()):
    from .inductor import current_spec, install, plan
    c = next(c for c in p['cells'] if c['id'] == cid)
    if c['name'] != 'spiral_candidate' or field not in ('turns', 'width', 'spacing'):
        raise ValueError('Select a candidate coil dimension.')
    record = c['parametric_devices'][0]
    spec = current_spec(c, record)
    spec[field] = value
    # Preserve the same stack, inner opening and device identity across both layouts.
    install(p, plan(p, cid, spec, did=record['device_id'], use_estimate=True, locked=locked), locked)


def _spiral_measure(p, cid, step):
    from .inductor import contact_findings, current_spec, geometry
    from .inductor_electrical import resistance
    c = next(c for c in p['cells'] if c['id'] == cid)
    if len(c.get('parametric_devices', [])) != 1 or contact_findings(p, cid) or drc(p, cid):
        raise ValueError('Keep one recognized, connected, DRC-clean spiral.')
    record = c['parametric_devices'][0]
    shape = geometry(p['pdk'], current_spec(c, record))
    l_h = shape['estimate_h']
    r_ohm = resistance(p['pdk'], shape)['total_ohm']
    if r_ohm is None or r_ohm <= 0:
        raise ValueError('Restore the declared educational metal and via resistances.')
    spec = shape['spec']
    c_f = 10e-15 + shape['winding_length_nm'] * spec['width'] * 1e-6 * 1e-17
    omega = 2 * math.pi * 1e9
    impedance = 1 / (1 / complex(r_ohm, omega * l_h) + complex(0, omega * c_f))
    q = impedance.imag / impedance.real
    resonance = math.sqrt(max(0.0, 1 / (l_h*c_f) - (r_ohm/l_h)**2))/(2*math.pi)
    if step == 'candidate':
        ref = _spiral_measure(p, _cell(p, 'spiral_reference')['id'], 'reference')
        if (q <= ref['Q at 1 GHz'] * 1.05 or resonance < 3e9 or l_h < 1.8e-9):
            raise ValueError(f'L {l_h*1e9:.2f} nH, Q {q:.2f}, resonance {resonance/1e9:.2f} GHz. Improve Q by 5% and retain 1.8 nH and 3 GHz.')
    elif not (spec['turns'] == 3 and spec['width'] == 10000 and spec['spacing'] == 3000):
        raise ValueError('Keep the original three-turn, 10 µm width, 3 µm spacing reference.')
    return {'Inductance (nH)': round(l_h*1e9, 4), 'Series resistance (Ω)': round(r_ohm, 4),
            'Shunt capacitance estimate (fF)': round(c_f*1e15, 3), 'Q at 1 GHz': round(q, 4),
            'Estimated self-resonance (GHz)': round(resonance/1e9, 4)}


_BUILDERS = {'pad-ring': _pad_ring, 'density': _density, 'antenna': _antenna,
             'via-current': _via_current, 'isolation': _isolation, 'spiral': _spiral}


def _read_stream(p, path):
    """Read actual GDS masks, labels and placements without using the sidecar."""
    from .design_ops import flatten_layout
    from .gf180_layout import layers

    db = kdb()
    ly = db.Layout()
    ly.read(str(path))
    c = _cell(p)
    top = ly.cell(c['name'])
    if top is None or [t.name for t in ly.top_cells()] != [c['name']] or not math.isclose(ly.dbu, p['pdk']['dbu_um']):
        raise ValueError('Unexpected top cell or database units in the re-opened GDS.')
    layer_ids = {l['name']: (l['gds'], l['datatype']) for l in p['pdk']['layers']}
    expected = {}
    for s in flatten_layout(p, c['id']):
        expected.setdefault(layer_ids[s['layer']], db.Region()).insert(polygon(s))
    actual = {}
    for i in ly.layer_indexes():
        shapes = top.begin_shapes_rec(i)
        shapes.shape_flags = db.Shapes.SBoxes | db.Shapes.SPolygons | db.Shapes.SPaths
        layer = ly.get_info(i)
        actual[layer.layer, layer.datatype] = db.Region(shapes)
    if any(not (expected.get(mask, db.Region()) ^ actual.get(mask, db.Region())).is_empty()
           for mask in expected.keys() | actual.keys()):
        raise ValueError('Written masks differ from the project on at least one layer/datatype.')
    placements = Counter((ly.cell(i.cell_index).name, i.cplx_trans.disp.x, i.cplx_trans.disp.y,
                          i.cplx_trans.angle, i.cplx_trans.is_mirror()) for i in top.each_inst())
    names = {c['id']: c['name'] for c in p['cells']}
    wanted = Counter((names[i['cell']], i['x'], i['y'], i.get('rotation',0), i.get('mirror',False))
                     for i in c['layout_instances'])
    if placements != wanted:
        raise ValueError('Written instance placement or hierarchy differs from the project.')
    label_mask = layer_ids[layers(p['pdk'])['m1label']]
    labels = Counter((s.text.string, (ly.get_info(i).layer, ly.get_info(i).datatype), s.text.trans.disp.x, s.text.trans.disp.y)
                     for i in ly.layer_indexes() for s in top.shapes(i).each() if s.is_text())
    wanted = Counter((port['name'], label_mask, *port['point']) for port in c['layout_ports'])
    return {'Top cell': top.name, 'Database unit (µm)': ly.dbu, 'Placed child instances': sum(placements.values()),
            'Verified mask layers': len(expected), 'Missing labels': sorted(row[0] for row in (wanted-labels).elements()),
            'Unexpected labels': sorted(row[0] for row in (labels-wanted).elements())}


def run_name(lab, step):
    return 'Export and inspect GDS' if lab == 'handoff' and step in ('fault', 'verify') else ''


def prepare(p, lesson, step):
    from .run_environment import stamp
    cid = focus(p, lesson['layout_lab'], step)
    if not run_name(lesson['layout_lab'], step):
        raise ValueError('Use Check this step for this task.')
    _macro_metrics(p, routed=True)
    job = dict(project=clone(p), cell=cid, engine='builtin', settings={'type': 'student_layout_stream'},
               student_lesson=lesson['id'], student_layout_step=step)
    job['environment'] = stamp(job)
    return job


def stream_run(p, job, directory):
    from .interchange import export_layout
    path = Path(directory) / 'pass_macro.gds'
    export_layout(p, path)
    inspection = _read_stream(p, path)
    return dict(schema=1, created=now(), project_id=p['id'], cell_id=job['cell'],
                design_hash=design_digest(p), revision=p['revision'],
                settings=clone(job['settings']), engine='Studio layout export + KLayout stream readback',
                x=[], x_label='', y_label='', traces={}, phase={}, operating_point={}, warnings=[],
                student_stream={'file': path.name, 'sha256': file_digest(path), 'inspection': inspection})


def _handoff(p, lesson, step, rows):
    from .student_hub import current_result
    candidates = [row for row in rows if row['job'].get('student_lesson') == lesson['id']
                  and row['job'].get('student_layout_step') == step and row['job']['cell'] == p['top']]
    result, evidence = current_result(p, candidates)
    stream = result.get('student_stream', {})
    path = Path(evidence['run']) / 'pass_macro.gds'
    if not path.is_file() or file_digest(path) != stream.get('sha256'):
        raise ValueError('The captured stream is missing or changed. Export and inspect it again.')
    inspection = _read_stream(p, path)
    if inspection != stream.get('inspection'):
        raise ValueError('The saved readback report differs from the captured stream.')
    expected = ['OUT'] if step == 'fault' else []
    if inspection['Missing labels'] != expected or inspection['Unexpected labels']:
        raise ValueError('Inspect the actual stream pin labels. Capture the original missing OUT, then add it and export again.')
    return dict(**evidence, stream_sha256=stream['sha256'], layout_study=inspection)


@lru_cache(maxsize=10)
def _rules(key):
    return project(key)['pdk']


def check(p, lesson, step, rows):
    lab = lesson['layout_lab']
    cid = focus(p, lab, step)
    base = _rules(fixture(lab))
    locked_fields = ('grid', 'layers', 'connectivity', 'routing_vias', 'parasitics', 'via_resistance_ohm', 'package_lock')
    if any(base.get(key) != p['pdk'].get(key) for key in locked_fields):
        raise ValueError('Restore the fixed lesson geometry rules, layers and coefficients.')
    if lab == 'handoff':
        _macro_metrics(p, routed=True)
        return _handoff(p, lesson, step, rows)
    if lab in ('floorplan', 'access'):
        values = _macro_metrics(p, routed=lab == 'access' and step == 'route')
        area, length = values['Footprint (µm²)'], values['Pin-to-pin Manhattan distance (µm)']
        if lab == 'floorplan' and ((step == 'loose' and area < 500) or (step == 'compact' and (area > 345 or length > 12))):
            raise ValueError(f'Footprint {area:.1f} µm², pin distance {length:.1f} µm. Capture the loose floorplan before meeting 345 µm² and 12 µm.')
        if step == 'access':
            from .gf180_layout import layers
            from .layout_routing import plan
            pins = _macro_pins(p)
            first = plan(p, cid, pins['X1','OUT'], pins['X2','SOURCE'], 'mid', 400,
                         [layers(p['pdk'])['m1']], margin=7500)
            if area > 345 or first['length_nm'] <= 14000:
                raise ValueError('Capture the compact floorplan with an over-budget metal-1 detour.')
            values['Metal-1-only detour (µm)'] = first['length_nm'] / 1000
    else:
        checks = {'pad-ring': _pad_measure, 'density': _density_measure,
                  'via-current': _via_measure, 'isolation': _isolation_measure}
        values = ({'antenna': _antenna_measure, 'spiral': _spiral_measure}[lab](p, cid, step)
                  if lab in ('antenna', 'spiral') else checks[lab](p, step))
    return {'layout_study': values}
