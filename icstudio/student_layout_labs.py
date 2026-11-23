"""Editable Layout course fixtures and their independently checked goals."""

import json
import math
from functools import lru_cache
from pathlib import Path

from .model import clone, design_digest, device, example, file_digest, scalar, uid, validate

STARTER = 'layout-study-'
AMPLIFIER = {'match', 'lvs', 'settle'}
PROCESS = {'fold', 'body'}
RC = {'settle', 'noise', 'supply'}
INPUTS = {'inp': 4000, 'inn': -4000, 'outp': 16000, 'outn': -16000}
COEFFICIENTS = dict(sheet_ohm=2, cap_f_per_um2=2e-16,
                    edge_f_per_um=2e-17, coupling_f_per_um=1e-16)


def course():
    from .getting_started import resource_root
    path = resource_root() / 'examples/student-hub/layout-course.json'
    return json.loads(path.read_text(encoding='utf-8'))


def lessons(source):
    result = []
    for unit in source:
        key = unit['id']
        workspace = STARTER + ('amplifier' if key in AMPLIFIER else key)
        steps = [dict(id='predict', kind='quiz', title='Predict what changes',
                      **unit['quiz'])]
        steps.extend(dict(id=step['id'], kind='check', title=step['title'],
                          instructions=step['instructions'], rule={'type': 'layout_study'})
                     for step in unit['tasks'])
        steps.append(dict(id='reflect', kind='reflection', title='Record your reasoning',
                          instructions=unit['reflection']))
        result.append(dict(id='l-' + key, path='layout', title=unit['title'],
                           summary=unit['summary'], skills=unit['skills'], minutes=unit['minutes'],
                           requires=unit['requires'], workspace=workspace, starter=workspace,
                           layout_lab=key, layout_topic=unit['topic'], steps=steps,
                           doc='STUDENT_LAYOUT_LABS.md'))
    return result


def _cell(name):
    return dict(id=uid(), name=name, ports=[], devices=[], shapes=[], layout_pins=[])


def _find(p, cid):
    return next(c for c in p['cells'] if c['id'] == cid)


def _path(c, net, points, width=400, layer='metal1', key=None):
    shape = dict(id=key or uid(), kind='path', layer=layer, points=[list(pt) for pt in points],
                 width=width, net=net, device_id='')
    c['shapes'].append(shape)
    return shape


def _pad(c, point, layer='metal1', size=700):
    from .layout import rect
    x, y = point
    c['shapes'].append(rect(layer, x - size // 2, y - size // 2, size, size))


def _pin(c, d, pin, pt, layer='metal1'):
    c['layout_pins'].append(dict(id=uid(), device_id=d['id'], pin=pin, layer=layer, point=list(pt)))


def _element(c, kind, name, value, connections, source=None):
    d = device(kind, name, 100 + 160 * (len(c['devices']) % 5),
               110 + 145 * (len(c['devices']) // 5), value=value,
               nets={pin: net for pin, (net, _) in connections.items()})
    if source:
        d['source'].update(source)
    c['devices'].append(d)
    for pin, (_, pt) in connections.items():
        if pt is not None:
            _pin(c, d, pin, pt)
    return d


def _rails(c, rows):
    for net, y in rows.items():
        for x in (0, 12000):
            _pad(c, (x, y))
        _path(c, net, ((0, y), (12000, y)), key=net + '_route')


def _pulse(low='0', high='1', delay='1n', period='6n'):
    return dict(type='pulse', low=low, high=high, delay=delay, period=period, duty='.5')


def _amp(c):
    from .layout import rect
    _rails(c, INPUTS)
    ground, supply, tail = (-6000, -3000), (-6000, 0), (-6000, 3000)
    for pt in (ground, supply, tail):
        _pad(c, pt)
    _element(c, 'V', 'VDD', '1.8', {'p': ('vdd', supply), 'n': ('0', ground)})
    _element(c, 'I', 'ITAIL', '100u', {'p': ('tail', tail), 'n': ('0', ground)})
    for side, bias in (('p', '.65'), ('n', '.65')):
        g, d = 'in' + side, 'out' + side
        gy, dy = INPUTS[g], INPUTS[d]
        _element(c, 'V', 'VIN' + side.upper(), bias, {'p': (g, (0, gy)), 'n': ('0', ground)},
                 _pulse('.65', '.69') if side == 'p' else None)
        mos = _element(c, 'NMOS', 'M' + side.upper(), '', {'g': (g, (12000, gy)),
                       'd': (d, (0, dy)), 's': ('tail', tail), 'b': ('0', ground)})
        mos['params'].update(w='10u', l='1u', vto='.45', kp='100u', **{'lambda': '.02'})
        _element(c, 'R', 'R' + side.upper(), '6k', {'p': ('vdd', supply), 'n': (d, (0, dy))})
        _element(c, 'C', 'C' + side.upper(), '12f', {'p': (d, (12000, dy)), 'n': ('0', ground)})
        _path(c, d, [(6000, dy), (6000, dy + (64000 if side == 'p' else -64000))],
              width=2400, key=d + '_stub')
    for index, name in enumerate(('dummy_l', 'a1', 'a2', 'b1', 'b2', 'dummy_r')):
        tile = rect('active', 16000 + 1800 * index, 0, 900, 900)
        tile['id'] = 'pair_' + name
        c['shapes'].append(tile)
    _shape(c, 'inp_route')['width'] = 200
    diff = 'V("outp")-V("outn")'
    c['specifications'] = [dict(name='Differential settling error', unit='V', max='12m',
                                expression=f'abs(at({diff},1.4e-9)-at({diff},2.5e-9))')]


def _shape(c, key):
    match = next((s for s in c['shapes'] if s['id'] == key), None)
    if match is None:
        raise ValueError('Keep the original layout feature ' + key + '.')
    return match


def _copy_cell(c, name):
    q = clone(c)
    q.update(id=uid(), name=name)
    ids = {d['id']: uid() for d in q['devices']}
    for d in q['devices']:
        d['id'] = ids[d['id']]
    for pin in q['layout_pins']:
        pin.update(id=uid(), device_id=ids[pin['device_id']])
    for shape in q['shapes']:
        shape['id'] = uid()
    return q


def _amplifier(p, c):
    from .physical_cells import assign_port
    _amp(c)
    c['ports'] = list(INPUTS)
    for net,y in INPUTS.items():
        assign_port(p,c['id'],net,'metal1',[12000,y])
    for fault in ('open', 'short', 'swap'):
        q = _copy_cell(c, 'lvs_' + fault)
        route = next(s for s in q['shapes'] if s.get('net') == 'inp')
        route['width'] = 400
        if fault == 'open':
            route['points'][-1][0] = 10000
        elif fault == 'short':
            _path(q, '', ((6000, -4000), (6000, 4000)))
        p['cells'].append(q)
        if fault == 'swap':
            set_input_ports(p, q['id'], False)


def _dac(c):
    from .layout import rect
    _pad(c, (-2500, -3000))
    for bit, y in enumerate((11000, 24000, 40000)):
        width = 1 << bit
        net = 'bit' + str(bit)
        _element(c, 'V', 'VB' + str(bit), '0', {'p': (net, (0, y)), 'n': ('0', (-2500, -3000))})
        _pad(c, (0, y))
        _path(c, net, ((0, y), (12000, y)), key=net + '_rail')
        for index in range(width):
            x = 1000 + 2500 * index
            cap = _element(c, 'C', f'C{bit}{index}', '10f', {'p': ('dac', (x, 0)), 'n': (net, (x, y))})
            # Each ideal unit is a visible teaching footprint beside its landing.
            tile_x = x + (11000 if bit == 2 and index == 3 else 0)
            c['shapes'].append(rect('unit_capacitor', tile_x - 450, y + 1150, 900, 900, cap['id']))
    _pad(c, (0, 0))
    _path(c, 'dac', ((0, 0), (25000, 0)), key='dac_rail')
    _element(c, 'R', 'RBLEED', '1G', {'p': ('dac', (0, 0)), 'n': ('0', (-2500, -3000))})
    # The long bit-2 stub approaches the top plate bus from beyond the other rails.
    _path(c, 'bit2', ((12000, 40000), (24500, 40000), (24500, 800), (400, 800)), key='bit2_stub')


def _noise(c, variant):
    spacing = 1400
    layer = 'metal2' if variant == 'layer' else 'metal1'
    gnd = (-4000, -3000)
    _pad(c, gnd)
    for net, y, route_layer in (('sense', 0, 'metal1'), ('clock', spacing, layer)):
        for x in (0, 50000):
            _pad(c, (x, y), route_layer)
        _path(c, net, ((0, y), (50000, y)), layer=route_layer, key=c['name'] + '_' + net + '_route')
    _element(c, 'R', 'RSENSE', '15k', {'p': ('sense', (0, 0)), 'n': ('0', gnd)})
    _element(c, 'C', 'CSENSE', '12f', {'p': ('sense', (50000, 0)), 'n': ('0', gnd)})
    clk = _element(c, 'V', 'VCLK', '0', {'p': ('clock', None), 'n': ('0', gnd)}, _pulse())
    _pin(c, clk, 'p', (0, spacing), layer)
    load = _element(c, 'C', 'CCLK', '2f', {'p': ('clock', None), 'n': ('0', gnd)})
    _pin(c, load, 'p', (50000, spacing), layer)
    # Put the physical sense port at the load, so V(sense) is the observed node.
    c['ports'] = ['sense']
    c['layout_ports'] = [dict(name='sense', layer='metal1', point=[50000, 0])]
    c['specifications'] = [dict(name='Peak sense disturbance', unit='V', max='85m',
                                expression='max(abs(V("sense")))')]
    if variant == 'shield':
        _path(c, 'shield', ((0, 700), (50000, 700)), width=300, key='shield_route')
        _element(c, 'V', 'VSHIELD', '0', {'p': ('shield', (0, 700)), 'n': ('0', gnd)})
        _element(c, 'R', 'RSHIELD', '1', {'p': ('shield', (50000, 700)), 'n': ('0', gnd)})


def set_clock_spacing(p, cid, distance_nm):
    c = _find(p, cid)
    clock = _shape(c, c['name'] + '_clock_route')
    old_y = clock['points'][0][1]
    pads = [s for s in c['shapes'] if s['kind'] == 'rect' and s['layer'] == clock['layer']
            and s['points'][0][1] == old_y - 350 and s['points'][1][1] == old_y + 350]
    by_id = {d['id']: d for d in c['devices']}
    pins = [pin for pin in c['layout_pins'] if by_id[pin['device_id']]['nets'][pin['pin']] == 'clock']
    if len(pads) != 2 or len(pins) != 2:
        raise ValueError('Keep both clock landing pads and their terminal assignments.')
    for points in [clock['points'], *(s['points'] for s in pads), [pin['point'] for pin in pins]]:
        for point in points:
            point[1] += distance_nm - old_y


def set_input_ports(p, cid, upper_is_positive):
    from .physical_cells import assign_port
    for name, y in (('inp', 4000), ('inn', -4000)):
        assign_port(p, cid, name, 'metal1', [12000, y if upper_is_positive else -y])


def _supply(c):
    for pt in ((0, 0), (50000, 0), (50000, -10000)):
        _pad(c, pt)
    _path(c, 'supply', ((0, 0), (50000, 0)), width=250, key='supply_route')
    _element(c, 'V', 'VDD', '1.8', {'p': ('supply', (0, 0)), 'n': ('0', (50000, -10000))})
    _element(c, 'I', 'ILOAD', '1m', {'p': ('supply', (50000, 0)), 'n': ('0', (50000, -10000))})
    c['ports'] = ['supply']
    c['layout_ports'] = [dict(name='supply', layer='metal1', point=[50000, 0])]
    c['specifications'] = [dict(name='Load-side supply', unit='V', min='1.65',
                                expression='final(V("supply"))')]


@lru_cache(maxsize=1)
def _gf180():
    from .bundled_pdks import packages
    root = Path(next(p['path'] for p in packages() if p['name'] == 'gf180mcuC'))
    m = json.loads((root / 'package.json').read_text(encoding='utf-8'))
    return {**m['technology'], 'package_root': str(root),
            'package_lock': {key: m[key] for key in ('id', 'revision', 'files')}}


def _mos(c, p, body=False):
    from .catalog import create_device
    choices = p['pdk']['simulation']['catalog']
    key = next(key for key, item in choices.items() if item.get('model') == 'nfet_03v3'
               and item.get('pin_order') == ['d', 'g', 's', 'b'] and 'nf' in item.get('emit_parameters', {}))
    d = create_device(p['pdk'], key, 'MN1', 340, 250)
    d['params'].update(w='2u', l='.28u')
    d['nets'] = {'d': 'OUT', 'g': 'GATE', 's': 'SOURCE', 'b': 'SOURCE' if body else 'BODY'}
    c['devices'] = [d]
    c['ports'] = list(dict.fromkeys(d['nets'].values()))
    return d


def _ports_for_mos(p, c):
    from .physical_cells import assign_port
    d = c['devices'][0]
    for pin in c['layout_pins']:
        if pin['pin'] != 'b' or d['nets']['s'] != d['nets']['b']:
            assign_port(p, c['id'], d['nets'][pin['pin']], pin['layer'], pin['point'])


def build_fold(p, cid, fingers=None):
    from .gf180_layout import install_mos, specification
    c = _find(p, cid)
    if c['shapes']:
        raise ValueError('This cell already has geometry. Use the schematic-driven layout review for later changes.')
    if fingers is not None and specification(p['pdk'], c['devices'][0])['values'].get('nf', 1) != fingers:
        raise ValueError(f'Set the schematic nf parameter to {fingers} before generating layout.')
    install_mos(p, cid, c['devices'][0]['id'])
    _ports_for_mos(p, c)


def _process_fixture(p, c, key):
    from .catalog import link_technology
    link_technology(p, clone(_gf180()))
    if key == 'eco':
        _hierarchy(p, c)
        return
    _mos(c, p, body=key == 'body')
    if key == 'body':
        build_fold(p, c['id'])
    elif key == 'fold':
        single = _cell('single_finger')
        p['cells'].append(single)
        _mos(single, p)
        build_fold(p, single['id'])


def _hierarchy(p, c):
    from .gf180_layout import install_mos, layers
    from .physical_cells import assign_port, place
    core = _cell('shared_device')
    p['cells'].append(core)
    d = _mos(core, p)
    install_mos(p, core['id'], d['id'])
    metal = layers(p['pdk'])['m1']
    xy = {'d': (4200, 1000), 'g': (140, -3000), 's': (-500, 3000), 'b': (-4200, 1000)}
    for pin in core['layout_pins']:
        name = pin['pin']
        pt = xy[name]
        net = d['nets'][name]
        _pad(core, pt, metal)
        _path(core, net, (pin['point'], pt), layer=metal)
        assign_port(p, core['id'], net, metal, pt)
    for index, x in enumerate((0, 15000)):
        inst = device('X', 'X' + str(index + 1), 300 + index * 270, 250, cell=core['id'],
                      nets={port: 'clk' if port == 'GATE' else f'{port.lower()}_{index + 1}' for port in core['ports']})
        c['devices'].append(inst)
        place(p, c['id'], inst['id'], x, 0)
    _path(c, 'clk', ((140, -3000), (15140, -3000)), layer=metal, key='shared_clock')


def project(key):
    p = example('empty')
    c = _cell({'amplifier': 'matched_amplifier', 'fold': 'folded_device',
               'eco': 'shared_parent', 'noise': 'noise_close'}.get(key, key))
    p.update(name='Layout lab · ' + key.replace('-', ' ').title(), top=c['id'], cells=[c])
    if key in PROCESS or key == 'eco':
        _process_fixture(p, c, key)
    else:
        p['pdk']['parasitics'] = {'metal1': dict(COEFFICIENTS), 'metal2': dict(COEFFICIENTS)}
        if key == 'amplifier':
            drawing = next(l for l in p['pdk']['layers'] if l['name'] == 'metal1')
            p['pdk']['layers'].append({**drawing, 'name': 'metal1_pin', 'datatype': 5, 'width': 0, 'space': 0})
            _amplifier(p, c)
        elif key == 'noise':
            _noise(c, 'close')
            for variant in ('space', 'layer', 'shield'):
                other = _cell('noise_' + variant)
                _noise(other, variant)
                p['cells'].append(other)
        elif key == 'dac':
            p['pdk']['layers'].append(dict(name='unit_capacitor', gds=85, datatype=0,
                                         color='#c4a5ff', width=900, space=500))
            _dac(c)
        else:
            _supply(c)
    p['student_layout_study'] = dict(version=1, fixture=key, cells={c['name']: c['id'] for c in p['cells']})
    return validate(p)


def focus(p, lab, step):
    record = p.get('student_layout_study', {})
    fixture = 'amplifier' if lab in AMPLIFIER else lab
    if record.get('version') != 1 or record.get('fixture') != fixture:
        raise ValueError('Open or resume this Layout lesson from the Student Hub.')
    wanted = (f'lvs_{step}' if lab == 'lvs' and step in ('open', 'short', 'swap') else
              f'noise_{step}' if lab == 'noise' and step in ('close', 'space', 'layer', 'shield') else
              'single_finger' if lab == 'fold' and step == 'single' else
              'shared_device' if lab == 'eco' and step == 'update' else None)
    cid = record['cells'].get(wanted) if wanted else p['top']
    if cid not in record['cells'].values() or not any(c['id'] == cid for c in p['cells']):
        raise ValueError('Restore the original lesson cell.')
    return cid


def run_name(lab, step):
    if lab in PROCESS and step in ('single', 'folded', 'tie'):
        return 'Run process DRC/LVS'
    if lab in RC and step in ('baseline', 'repair', 'close', 'space', 'layer', 'shield'):
        return 'Compare schematic and layout'
    return ''


def prepare(p, lesson, step, tools):
    from .run_environment import stamp
    lab = lesson['layout_lab']
    cid = focus(p, lab, step)
    if not run_name(lab, step):
        raise ValueError('Use Check this step for this task.')
    if lab in PROCESS:
        from .layout_verification import reference
        from .physical_backend import prepare as prepare_physical
        from .testbenches import native_subcircuit
        if not _find(p, cid)['shapes']:
            raise ValueError('Build the process device layout before running verification.')
        settings = dict(type='silicon', verification_mode='drc_lvs',
                        reference=reference(native_subcircuit(p, cid), _find(p, cid)['name']),
                        physical_toolchain='auto', tools={key: tools.get(key, '') for key in ('magic', 'netgen', 'ngspice')})
        job = dict(project=clone(p), cell=cid, engine='physical', settings=settings)
        prepare_physical(job)
    else:
        _checked_geometry(p, cid, lab)
        analysis = (dict(type='op', corner='nominal') if lab == 'supply' else
                    dict(type='tran', stop='3n', step='5p', corner='nominal'))
        job = dict(project=clone(p), cell=cid, engine='builtin',
                   settings=dict(type='rc_compare', analysis=analysis))
    job.update(student_lesson=lesson['id'], student_layout_step=step)
    job['environment'] = stamp(job)
    return job


def _expected_deck(p, lab):
    expected = _reference('amplifier' if lab in AMPLIFIER else lab)['pdk']
    keys = ('parasitics', 'layers', 'connectivity', 'grid')
    if any(p['pdk'].get(k) != expected.get(k) for k in keys):
        raise ValueError('Restore the fixed layout lab geometry rules and RC coefficients.')


@lru_cache(maxsize=8)
def _reference(fixture):
    return project(fixture)


def _electrical_signature(c):
    return sorted((d['name'], d['kind'], d['nets'], d['params'], d['value'], d.get('source')) for d in c['devices'])


def _terminal_signature(c):
    devices = {d['id']: d for d in c['devices']}
    result = []
    for pin in c['layout_pins']:
        d = devices[pin['device_id']]
        x, y = pin['point']
        if c['name'] == 'noise_space' and d['nets'][pin['pin']] == 'clock':
            y = None  # The spacing control moves the clock and both of its terminals.
        result.append((d['name'], pin['pin'], pin['layer'], x, y))
    return sorted(result)


def _checked_geometry(p, cid, lab):
    from .layout import drc, kdb, polygon
    from .physical import connectivity
    _expected_deck(p, lab)
    c = _find(p, cid)
    other = _reference('amplifier' if lab in AMPLIFIER else lab)
    reference = next((r for r in other['cells'] if r['name'] == c['name']), None)
    if lab != 'eco':
        if not reference or _electrical_signature(c) != _electrical_signature(reference):
            raise ValueError('Restore the original circuit and source settings. Make changes in Layout.')
        if c['ports'] != reference['ports'] or _terminal_signature(c) != _terminal_signature(reference):
            raise ValueError('Keep the original circuit terminals and port declarations.')
        if lab in ('noise', 'supply') and c.get('layout_ports') != reference.get('layout_ports'):
            raise ValueError('Keep the original observation port at its load.')
    issues = drc(p, cid)
    if issues:
        raise ValueError('Resolve geometry findings first. ' + issues[0]['message'])
    check = connectivity(p, cid)
    if check['issues']:
        raise ValueError('Geometry is clean. ' + check['issues'][0]['message'])
    if set(c['ports']) != {r['name'] for r in c.get('layout_ports', [])}:
        raise ValueError('Keep all declared physical port assignments.')
    for port in c.get('layout_ports', []):
        nets = {group['net'] for group in check['net_regions'] for s in group['shapes']
                if s['layer'] == port['layer'] and polygon(s).inside(kdb().Point(*port['point']))}
        if nets != {port['name']}:
            raise ValueError(f'Port {port["name"]} lands on {", ".join(sorted(nets)) or "no conductor"}. Reassign its physical position.')
    return check


def _process_result(p, lesson, step, rows):
    from .student_hub import current_result
    cid = focus(p, lesson['layout_lab'], step)
    candidates = [r for r in rows if r['job'].get('student_lesson') == lesson['id']
                  and r['job'].get('student_layout_step') == step and r['job']['cell'] == cid]
    result, evidence = current_result(p, candidates)
    report = result.get('silicon_report', {})
    stages = {s['name']: s for s in report.get('stages', [])}
    integrity = stages.get('integrity', {}).get('evidence', {})
    if (report.get('design_hash') != design_digest(p) or report.get('mode') != 'drc_lvs'
            or not integrity.get('verified') or any(stages.get(k, {}).get('status') != 'passed' for k in ('drc', 'lvs', 'integrity'))):
        raise ValueError('A fresh GF180 process DRC and LVS pass is required. Review the verification report for tool setup or findings.')
    root = Path(result['evidence_directory'])
    if any(not (root / name).is_file() or file_digest(root / name) != sha for name, sha in integrity['files'].items()):
        raise ValueError('Physical evidence is missing or changed. Run verification again.')
    return evidence, {'PDK': 'GF180MCU C', 'DRC': 'Passed', 'LVS': 'Passed'}


def _matched(p, c):
    from .distributed_rc import extract
    from .physical import capacitance_estimate
    names = ('a1', 'a2', 'b1', 'b2', 'dummy_l', 'dummy_r')
    tiles = [_shape(c, 'pair_' + name) for name in names]
    points = [tuple(s['points'][0]) for s in tiles]
    xs = [pt[0] for pt in points]
    if (len({pt[1] for pt in points}) != 1 or len(set(xs)) != len(xs)
            or xs[0] + xs[1] != xs[2] + xs[3] or xs[4] >= min(xs[:4]) or xs[5] <= max(xs[:4])
            or any(s['kind'] != 'rect' or s['layer'] != 'active' or
                   [b - a for a, b in zip(*s['points'])] != [900, 900] for s in tiles)):
        raise ValueError('Keep all four equal active tiles in one row. Match the A/B centroids and keep a dummy on each outer edge.')
    if min(b - a for a, b in zip(sorted(xs), sorted(xs)[1:])) < 1050:
        raise ValueError('Separate all six tiles by at least 0.15 µm.')
    network = extract(p, c['id'])
    caps = {r['net']: r['capacitance'] for r in capacitance_estimate(p, c['id'])['capacitors']}
    resistance = {net: sum(r['value'] for r in network['resistors'] if r['shape'] == net + '_route') for net in INPUTS}
    result = {}
    for label, nets in (('Input', ('inp', 'inn')), ('Output', ('outp', 'outn'))):
        a, b = nets
        if min(resistance[a], resistance[b], caps.get(a, 0), caps.get(b, 0)) <= 0:
            raise ValueError('Keep both routes on each side in the extracted interconnect.')
        if not (math.isclose(resistance[a], resistance[b], rel_tol=.05) and math.isclose(caps[a], caps[b], rel_tol=.05)):
            raise ValueError(f'{label} routes differ: {resistance[a]:.1f}/{resistance[b]:.1f} Ω and {caps[a]*1e15:.2f}/{caps[b]*1e15:.2f} fF. Match both within 5%.')
        result[f'{label} resistance (Ω)'] = [round(resistance[n], 2) for n in nets]
        result[f'{label} capacitance (fF)'] = [round(caps[n] * 1e15, 2) for n in nets]
    return result


def _dac_weights(p, c):
    from .distributed_rc import extract
    network = extract(p, c['id'])
    shape_nets = {s['id']: s.get('net') for s in c['shapes']}
    coupling = {f'bit{i}': 0.0 for i in range(3)}
    for cap in network['capacitors']:
        if cap['kind'] == 'coupling':
            pair = {shape_nets[s] for s in cap['shapes']}
            for bit in pair - {'dac'} if 'dac' in pair else ():
                if bit in coupling:
                    coupling[bit] += cap['value']
    weights = [(10e-15 * (1 << i) + coupling[f'bit{i}']) * 1e15 for i in range(3)]
    levels = [sum(w for i, w in enumerate(weights) if code & (1 << i)) / sum(weights) for code in range(8)]
    inl = max(abs(value * 7 - code) for code, value in enumerate(levels))
    return {'Effective weights (fF)': [round(w, 3) for w in weights],
            'Normalized code levels': [round(v, 5) for v in levels], 'Peak endpoint INL (LSB)': round(inl, 4)}


def _dac_array(c):
    units = {d['id']: d for d in c['devices'] if d['kind'] == 'C'}
    tiles = [s for s in c['shapes'] if s['layer'] == 'unit_capacitor']
    if len(tiles) != len(units) or {s['device_id'] for s in tiles} != units.keys():
        raise ValueError('Keep one physical teaching tile for every unit capacitor.')
    anchors = {pin['device_id']: pin['point'] for pin in c['layout_pins'] if pin['pin'] == 'n'}
    for tile in tiles:
        x, y = anchors[tile['device_id']]
        if tile['kind'] != 'rect' or tile['points'] != [[x - 450, y + 1150], [x + 450, y + 2050]]:
            raise ValueError(f'Place {units[tile["device_id"]]["name"]} next to its bit-rail landing at X = {x/1000:g} µm.')
    return {'Unit groups': '1 / 2 / 4', 'Unit capacitance (fF)': 10}


def _eco(p, cid, step):
    from .gf180_layout import audit
    core = next(c for c in p['cells'] if c['name'] == 'shared_device')
    if len(core['devices']) != 1 or not math.isclose(scalar(core['devices'][0]['params']['w']), 3e-6):
        raise ValueError('Set the shared NMOS total width to 3 µm.')
    if audit(p, core['id']) or len(core.get('pdk_layouts', [])) != 1:
        raise ValueError('Review and apply the schematic change to the shared physical device.')
    if step == 'update':
        return {'Shared device width (µm)': 3}
    parent = _find(p, cid)
    instances = parent.get('layout_instances', [])
    if len(instances) != 2 or any(i['cell'] != core['id'] for i in instances):
        raise ValueError('Keep two placed instances of the same physical cell.')
    _checked_geometry(p, core['id'], 'eco')
    _checked_geometry(p, cid, 'eco')
    return {'Verified parent instances': 2, 'Shared connection': 'clk'}


def _rc_result(p, lesson, step, rows):
    from .student_hub import at, current_result
    lab = lesson['layout_lab']
    cid = focus(p, lab, step)
    candidates = [r for r in rows if r['job'].get('student_lesson') == lesson['id']
                  and r['job'].get('student_layout_step') == step and r['job']['cell'] == cid]
    result, evidence = current_result(p, candidates)
    if (result.get('settings', {}).get('type') != 'rc_compare' or
            result.get('extraction', {}).get('cell_id') != cid):
        raise ValueError('Compare the schematic and layout for this lesson step.')
    root = Path(evidence['run'])
    records = result.get('provenance', {}).get('waveforms', [])
    waves = []
    for index, case in enumerate(('before', 'after')):
        path = root / case / 'result.json'
        if len(records) != 2 or not path.is_file() or file_digest(path) != records[index].get('waveform_sha256'):
            raise ValueError('Waveform evidence is missing or changed. Run the comparison again.')
        wave = json.loads(path.read_text(encoding='utf-8'))
        if wave != result[f'{case}_waveform'] or wave.get('design_hash') != design_digest(p):
            raise ValueError('The saved waveform differs from this design comparison.')
        waves.append(wave)
    before, after = waves
    if lab == 'supply':
        drop = (at(before, 'supply') - at(after, 'supply')) * 1000
        if (step == 'baseline' and drop < 300) or (step == 'repair' and not 0 < drop <= 150):
            raise ValueError(f'Supply drop is {drop:.1f} mV. Capture the weak route first, then bring it below 150 mV.')
        values = {'Supply drop (mV)': round(drop, 2), 'Load voltage (V)': round(at(after, 'supply'), 4)}
    elif lab == 'noise':
        first = max(abs(v) for v in after['traces']['sense']) * 1000
        if step == 'close' and first < 150:
            raise ValueError('Keep the close parallel clock route to measure the baseline glitch.')
        if step == 'space' and first >= 85:
            raise ValueError(f'Peak glitch is {first:.1f} mV. Increase spacing to bring it below 85 mV.')
        if step == 'layer' and first >= 1:
            raise ValueError('Use metal2 for the clock in this comparison.')
        if step == 'shield':
            if not any(s.get('net') == 'shield' for s in _find(p, cid)['shapes']):
                raise ValueError('Keep the grounded shield between the signal and the clock.')
        values = {'Peak victim glitch (mV)': round(first, 2), 'Case': step}
    else:
        # The observation is at a fixed deadline after the rising stimulus.
        def output(wave, time):
            return at(wave, 'outp', time) - at(wave, 'outn', time)
        ideal = output(before, 2.5e-9)
        base_error = abs(output(before, 1.4e-9) - ideal) * 1000
        error = abs(output(after, 1.4e-9) - ideal) * 1000
        if (step == 'baseline' and error <= 12) or (step == 'repair' and error > 12):
            raise ValueError(f'At 1.4 ns, extracted differential settling error is {error:.1f} mV. The limit is 12 mV.')
        values = {'Schematic settling error (mV)': round(base_error, 3), 'Extracted settling error (mV)': round(error, 3)}
    return evidence, values


def check(p, lesson, step, rows):
    lab = lesson['layout_lab']
    cid = focus(p, lab, step)
    c = _find(p, cid)
    captured = {}
    if lab in PROCESS:
        wanted = 4 if step == 'folded' else 1
        record = (c.get('pdk_layouts') or [{}])[0].get('spec', {})
        if (p['pdk'].get('package_lock', {}).get('id') != 'gf180mcuC' or
                record.get('values', {}).get('nf') != wanted or record.get('dimensions_nm', {}).get('w') != 2000):
            raise ValueError(f'Use the GF180 2 µm total-width device with {wanted} physical finger(s).')
        captured, values = _process_result(p, lesson, step, rows)
        values['Physical fingers'] = wanted
    elif lab in RC:
        _checked_geometry(p, cid, lab)
        captured, values = _rc_result(p, lesson, step, rows)
    elif lab == 'eco':
        values = _eco(p, cid, step)
    else:
        _checked_geometry(p, cid, lab)
        if lab == 'match':
            values = _matched(p, c)
        elif lab == 'dac':
            values = _dac_array(c)
            if step != 'array':
                values = _dac_weights(p, c)
                error = values['Peak endpoint INL (LSB)']
                if (step == 'baseline' and error < .16) or (step == 'repair' and error >= .16):
                    raise ValueError(f'Peak DAC error is {error:.3f} LSB. Capture the original coupling first, then bring it below 0.16 LSB.')
        else:
            values = {'Geometry': 'Clean', 'Port and terminal connectivity': 'Match', 'Repaired case': step}
    return dict(**captured, layout_study=values)
