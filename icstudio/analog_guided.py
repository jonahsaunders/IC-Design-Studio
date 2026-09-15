"""Reviewable analog fixtures generated from explicit DUT port roles and goals."""
from .model import clone, device, uid, validate, scalar, NAME

TEMPLATES = {
    'amplifier': ('input', 'output', 'supply', 'ground'),
    'differential_pair': ('input_positive', 'input_negative', 'output', 'output_negative', 'supply', 'ground'),
    'current_mirror': ('reference', 'output', 'supply', 'ground'),
}
DEFAULTS = dict(supply='1.8', common_mode='.8', load='1p', gain_min='1', bandwidth_min='100k',
                power_max='1m', settling_max='', start_frequency='10', end_frequency='100Meg',
                stop_time='100u', input_step='1m', reference_current='20u', mirror_ratio='1',
                current_tolerance='.05', compliance='.9', temperature='27')


def port_defaults(cell, template):
    aliases = dict(input=('IN', 'VIN', 'INP'), input_positive=('INP', 'VINP', 'IN'),
                   input_negative=('INN', 'VINN'), output=('OUT', 'VOUT', 'OUTP'),
                   output_negative=('OUTN', 'VOUTN'), supply=('VDD', 'VPWR'), ground=('VSS', 'GND', 'VGND'),
                   reference=('REF', 'IREF', 'IN'))
    used, result = set(), {}
    for role in TEMPLATES[template]:
        match = next((p for alias in aliases[role] for p in cell['ports'] if p.upper() == alias and p not in used), '')
        result[role] = match
        if match: used.add(match)
    return result


def teaching_example(project, template):
    """Add a clearly labelled generic DUT; never replace the user's circuit."""
    if template not in TEMPLATES: raise ValueError('Choose a supported circuit template.')
    q = clone(project); names = {c['name'] for c in q['cells']}; name = 'teaching_' + template
    while name in names: name += '_new'
    ports = ['IN', 'OUT', 'VDD', 'VSS'] if template == 'amplifier' else ['INP', 'INN', 'OUT', 'OUTN', 'VDD', 'VSS'] if template == 'differential_pair' else ['REF', 'OUT', 'VDD', 'VSS']
    c = dict(id=uid(), name=name, ports=ports, devices=[], shapes=[], parameters={})
    if template == 'amplifier':
        c['devices'] = [device('NMOS', 'M1', 300, 300, nets={'d': 'OUT', 'g': 'IN', 's': 'VSS', 'b': 'VSS'}),
                        device('R', 'RL', 300, 150, value='10k', nets={'p': 'VDD', 'n': 'OUT'})]
    elif template == 'differential_pair':
        c['devices'] = [device('NMOS', 'M1', 260, 270, nets={'d': 'OUT', 'g': 'INP', 's': 'TAIL', 'b': 'VSS'}),
                        device('NMOS', 'M2', 540, 270, nets={'d': 'OUTN', 'g': 'INN', 's': 'TAIL', 'b': 'VSS'}),
                        device('R', 'RL1', 260, 130, value='50k', nets={'p': 'VDD', 'n': 'OUT'}),
                        device('R', 'RL2', 540, 130, value='50k', nets={'p': 'VDD', 'n': 'OUTN'}),
                        device('I', 'ITAIL', 400, 430, value='20u', nets={'p': 'TAIL', 'n': 'VSS'})]
    else:
        c['devices'] = [device('NMOS', 'MREF', 280, 240, nets={'d': 'REF', 'g': 'REF', 's': 'VSS', 'b': 'VSS'}),
                        device('NMOS', 'MOUT', 540, 240, nets={'d': 'OUT', 'g': 'REF', 's': 'VSS', 'b': 'VSS'})]
    for d in c['devices']:
        if d['kind'] in ('NMOS', 'PMOS'): d['model_mode'] = 'generic'
    q['cells'].append(c)
    from .components import configure_component
    configure_component(q, c['id'], c['name'], c['ports'], {})
    validate(q); return q, c['id']


def generate(project, cid, spec):
    """Return a complete proposal. Existing cells, sources and limits are untouched."""
    from .testbenches import create
    from .model import design_digest
    template = spec['template']; name = spec.get('name', 'guided_' + template)
    if template not in TEMPLATES or not NAME.fullmatch(name): raise ValueError('Choose a template and an identifier for the experiment name.')
    q = clone(project); dut = next(c for c in q['cells'] if c['id'] == cid)
    if not dut['ports']: raise ValueError('Choose a DUT with exposed ports, or add a teaching example.')
    roles = spec['ports']; used = []
    for role in TEMPLATES[template]:
        port = roles.get(role, '')
        if role == 'output_negative' and not port: continue
        if port not in dut['ports'] or port in used: raise ValueError('Assign a distinct DUT port to ' + role.replace('_', ' ') + '.')
        used.append(port)
    biases = spec.get('biases', {})
    if set(biases) != set(dut['ports']) - set(used): raise ValueError('Assign an explicit DC voltage to every remaining bias port.')
    values = {k: scalar(v) for k, v in {**DEFAULTS, **spec.get('values', {})}.items() if v not in ('', None)}
    for key in ('supply', 'load', 'start_frequency', 'end_frequency', 'stop_time', 'input_step', 'reference_current', 'mirror_ratio'):
        if values[key] <= 0: raise ValueError(key.replace('_', ' ') + ' must be positive.')
    for key in ('gain_min', 'bandwidth_min', 'power_max', 'settling_max'):
        if key in values and values[key] <= 0: raise ValueError(key.replace('_', ' ') + ' must be positive or blank.')
    if values['end_frequency'] <= values['start_frequency'] or values['temperature'] <= -273.15:
        raise ValueError('Use increasing AC frequencies and a valid temperature.')
    if not 0 < values['current_tolerance'] < 1: raise ValueError('Current tolerance must be between zero and one.')
    if 'bandwidth_min' in values and not values['start_frequency'] < values['bandwidth_min'] < values['end_frequency']:
        raise ValueError('The bandwidth goal must lie inside the requested AC frequency range.')
    engine = spec.get('engine', 'builtin')
    if engine not in ('builtin', 'ngspice'): raise ValueError('Choose the teaching solver or ngspice.')
    if engine == 'builtin':
        if q.get('spice', {}).get('version') == 1: raise ValueError('Native projects require ngspice. Choose ngspice for this setup.')
        from .model import flatten
        devices = flatten(q, cid)
        if any(d.get('native_spice') or d.get('model_ref') for d in devices): raise ValueError('Use ngspice for native/process devices.')
        if values['temperature'] != 27 and any(d['kind'] in ('NMOS', 'PMOS') for d in devices): raise ValueError('MOS temperature sweeps require ngspice and suitable models.')
    mapping = {'input': 'vin', 'input_positive': 'vinp', 'input_negative': 'vinn', 'output': 'vout',
               'output_negative': 'voutn', 'supply': 'vdd', 'ground': '0', 'reference': 'ref'}
    nets = {port: mapping[role] for role, port in roles.items() if role in TEMPLATES[template] and port}
    for i, port in enumerate(biases): nets[port] = 'bias' + str(i + 1)
    kinds = ['op'] if template == 'current_mirror' else ['op', 'ac'] + (['tran'] if 'settling_max' in values else [])
    if len(q.get('testbenches', [])) + len(kinds) > 50: raise ValueError('Remove old testbenches before adding more than 50.')
    entries, fixtures, generated_specs = [], [], []
    prefix = len(q.get('simulation_setups', []))
    for kind in kinds:
        cell_name = name + '_' + kind
        if any(c['name'].casefold() == cell_name.casefold() for c in q['cells']) or any(t['name'].casefold() == cell_name.casefold() for t in q.get('testbenches', [])):
            raise ValueError('That experiment name is already used. Choose another name.')
        ds = [device('V', 'VDD', 100, 100, value=str(values['supply']), nets={'p': 'vdd', 'n': '0'}),
              device('X', 'XDUT', 440, 280, cell=cid, nets=clone(nets)),
              device('C', 'CL', 720, 280, value=str(values['load']), nets={'p': 'vout', 'n': '0'})]
        if roles.get('output_negative'): ds.append(device('C', 'CLN', 720, 460, value=str(values['load']), nets={'p': 'voutn', 'n': '0'}))
        for i, (port, voltage) in enumerate(biases.items()):
            ds.append(device('V', 'VBIAS' + str(i + 1), 100, 540 + i * 120, value=str(scalar(voltage)), nets={'p': nets[port], 'n': '0'}))
        if template == 'current_mirror':
            ds += [device('I', 'IREF', 100, 280, value=str(values['reference_current']), nets={'p': 'vdd', 'n': 'ref'}),
                   device('V', 'VLOAD', 720, 100, value=str(values['compliance']), nets={'p': 'vout', 'n': '0'})]
        else:
            inputs = [('VIN', 'vin', 1.)] if template == 'amplifier' else [('VINP', 'vinp', .5), ('VINN', 'vinn', -.5)]
            for i, (source, net, amplitude) in enumerate(inputs):
                d = device('V', source, 100 + i * 160, 340, value=str(values['common_mode']), nets={'p': net, 'n': '0'})
                d['source']['ac'] = str(amplitude)
                if kind == 'tran':
                    d['source'].update(type='pulse', low=str(values['common_mode']), high=str(values['common_mode'] + amplitude * values['input_step']),
                                       period=str(values['stop_time'] * 4), delay=str(values['stop_time'] * .1), duty='.5')
                ds.append(d)
        for d in ds:
            if d['kind'] == 'V' and not d['name'].startswith('VIN'): d['source']['ac'] = '0'
        settings = {**clone(q['analysis']), 'type': kind, 'temperature': values['temperature'], 'corner': spec.get('corner', 'nominal'),
                    'start': str(values['start_frequency']), 'end': str(values['end_frequency']), 'points': 80,
                    'stop': str(values['stop_time']), 'step': str(values['stop_time'] / 1000)}
        output = 'V("vout")' if not roles.get('output_negative') else '(V("vout")-V("voutn"))'
        input_wave = 'V("vin")' if template == 'amplifier' else '(V("vinp")-V("vinn"))'
        requirements = []
        def requirement(title, expression, unit, **limits): requirements.append(dict(name=title, expression=expression, unit=unit, **limits))
        if kind == 'op':
            if 'power_max' in values:
                power = 'abs(final(V("vdd")*I("VDD")))'
                if template == 'current_mirror': power += '+abs(final(V("vout")*I("VLOAD")))'
                requirement('DC supply power', power, 'W', max=values['power_max'])
            if template == 'current_mirror':
                target = values['reference_current'] * values['mirror_ratio']; tolerance = values['current_tolerance']
                requirement('Mirror output current', 'abs(final(I("VLOAD")))', 'A', min=target * (1 - tolerance), max=target * (1 + tolerance))
            else:
                requirement('Output bias', 'final(V("vout"))', 'V', min=0, max=values['supply'])
        if kind == 'ac':
            gain = f'abs({output}/{input_wave})'; low = f'at({gain},{values["start_frequency"]!r})'
            if 'gain_min' in values: requirement('Low-frequency gain', low, '1', min=values['gain_min'])
            if 'bandwidth_min' in values: requirement('Bandwidth', f'crossing({gain},{low}/sqrt(2),-1)', 'Hz', min=values['bandwidth_min'])
        if kind == 'tran':
            edge = values['stop_time'] * .1; stop = values['stop_time']; clipped = f'clip({output},{edge!r},{stop!r})'
            tolerance = f'abs(final({clipped})-at({output},{edge!r}))*.02'
            requirement('Settling time (2%)', f'settling({clipped},final({clipped}),{tolerance})-at(x,{edge!r})', 's', max=values['settling_max'])
        fixture = dict(id=uid(), name=cell_name, ports=[], devices=ds, shapes=[], specifications=requirements)
        if q.get('spice', {}).get('version') == 1: fixture['analog_model_scope'] = project['top']
        q['cells'].append(fixture)
        from .wiring import migrate
        migrate(fixture, q)
        bench = create(q, fixture['id'], cell_name); bench['analysis'] = clone(settings); bench['specifications'] = clone(requirements)
        q.setdefault('testbenches', []).append(bench)
        q.setdefault('simulation_setups', []).append(dict(name=cell_name, cell=fixture['id'], engine=engine, settings=settings))
        entries.append(dict(id='setup:' + str(prefix + len(entries)), name=cell_name, cell=fixture['id'], engine=engine, settings=clone(settings), supply='VDD.value'))
        fixtures.append(fixture['id']); generated_specs.extend(dict(r, test=cell_name) for r in requirements)
    plan = dict(id=uid(), name=name, entries=entries, corners=[spec.get('corner', 'nominal')], temperatures=[values['temperature']], voltages=[])
    q.setdefault('test_plans', []).append(plan)
    q.setdefault('analog_guides', []).append(dict(id=uid(), name=name, dut_cell=cid, spec=clone(spec), fixture_cells=fixtures, plan_id=plan['id']))
    validate(q)
    return q, dict(base_design_hash=design_digest(project), plan_id=plan['id'], fixture_cells=fixtures,
                   requirements=generated_specs, tests=entries, dut_cell=cid, name=name)
