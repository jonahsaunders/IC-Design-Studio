"""Build a reviewable saved bench from a small vocabulary of electrical inputs."""
import json
import re
from . import testbenches, wiring
from .model import NAME, clone, device, scalar, uid, validate


INSTRUCTIONS = """Return a single JSON object, without prose, with name, analysis, connections, probes and measurements.
name is a unique Studio identifier. analysis is {"type":"op"}, {"type":"tran","step":"100n","stop":"50u"},
or {"type":"ac","start":"10","end":"10Meg","points":40}. Use engineering numbers or strings.
For a circuit with ports, connections maps EVERY port name to an object. Its kind can be ground, observe,
dc (value in volts, optional ac amplitude), pulse (low, high, period, optional delay and duty fraction),
resistor (value in ohms), or capacitor (value in farads). Sources and loads connect to ground.
For a standalone circuit use connections={} and retain its existing sources. probes lists distinct non-ground
port names (standalone: existing net names). measurements is a list of {"name":"output_voltage","node":"actual probe"}
with optional numeric min, max, or at (seconds for transient, Hz for AC). A voltage measurement defaults to the last sample.
Only include pass/fail limits provided by the user. Do not invent device names, design requirements or simulation results."""


def fields(data, allowed, required=()):
    if not isinstance(data, dict) or set(data) - set(allowed) or set(required) - set(data):
        raise ValueError('Invalid testbench fields. Expected ' + ', '.join(allowed) + '.')


def number(raw):
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise ValueError('Use a finite engineering number for each numeric field.')
    try:
        return scalar(raw)
    except OverflowError:
        raise ValueError('The numeric value is outside the supported range.') from None


def analysis_spec(data):
    kind = data.get('type') if isinstance(data, dict) else None
    keys = {'op': (), 'tran': ('step', 'stop'), 'ac': ('start', 'end', 'points')}
    if not isinstance(kind, str) or kind not in keys:
        raise ValueError('Choose operating point, transient, or AC analysis.')
    required = ('type', *keys[kind])
    fields(data, required, required)
    result = {key: number(data[key]) for key in keys[kind]}
    if kind == 'ac' and not result['points'].is_integer():
        raise ValueError('Use a whole number of AC points per decade.')
    if kind == 'ac':
        result['points'] = int(result['points'])
    return dict(type=kind, **result)


def circuit_nets(cell):
    return {net for item in cell['devices'] for net in item['nets'].values()}


def standalone_ready(project, cell):
    if (project.get('spice') or any(d['kind'] not in ('R','C','L','I','V','NMOS','PMOS','D')
                                    or d.get('native_spice') or d.get('array') for d in cell['devices'])):
        raise ValueError('Choose a circuit with exposed ports for this design. A standalone snapshot supports flat, basic analog schematics.')
    if '0' not in circuit_nets(cell):
        raise ValueError('Ground the circuit before creating a standalone testbench.')


def snapshot(project, cell, name, probes):
    standalone_ready(project, cell)
    nets = {n.casefold() for n in circuit_nets(cell)}
    ground = 'TB_GND'
    while ground.casefold() in nets:
        ground += '_'
    copied = []
    for original in cell['devices']:
        item = clone(original)
        item['id'] = uid()
        item.pop('net_labels', None)
        item['nets'] = {p: ground if n == '0' else n for p, n in item['nets'].items()}
        copied.append(item)
    dut = dict(id=uid(), name=name + '_dut', ports=[*probes, ground], devices=copied,
               shapes=[], parameters=clone(cell.get('parameters', {})))
    project['cells'].append(dut)
    wiring.migrate(dut, project)
    return dut, {**{p: p for p in probes}, ground: '0'}


def fixture_device(port, data, index):
    kind = data.get('kind') if isinstance(data, dict) else None
    allowed = {'ground': (), 'observe': (), 'dc': ('value', 'ac'), 'pulse': ('low', 'high', 'period', 'delay', 'duty'),
               'resistor': ('value',), 'capacitor': ('value',)}
    if not isinstance(kind, str) or kind not in allowed:
        raise ValueError('Choose a supported fixture connection for ' + port + '.')
    required = tuple(k for k in allowed[kind] if k not in ('ac', 'delay', 'duty'))
    fields(data, ('kind', *allowed[kind]), required)
    values = {k: number(v) for k, v in data.items() if k != 'kind'}
    if kind in ('ground', 'observe'):
        return '0' if kind == 'ground' else port, None
    symbol = {'resistor': 'R', 'capacitor': 'C', 'dc': 'V', 'pulse': 'V'}[kind]
    item = device(symbol, symbol + str(index + 1), 100 + 180 * (index % 4), 500 + 180 * (index // 4),
                  value=str(values.get('value', values.get('low', 0))), nets={'p': port, 'n': '0'})
    if kind == 'dc':
        item['source']['ac'] = str(values.get('ac', 0))
    elif kind == 'pulse':
        if not 0 < values.get('duty', .5) < 1 or values['period'] <= 0 or values.get('delay', 0) < 0:
            raise ValueError('Use a positive pulse period, nonnegative delay, and duty between zero and one.')
        item['source'].update(type='pulse', ac='0', **{k: str(v) for k, v in values.items()})
    return port, item


def propose(project, cell, answer):
    if len(answer) > 48000:
        raise ValueError('The proposed testbench is too large.')
    block = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', answer.strip(), re.I | re.S)
    try:
        spec = json.loads(block[1] if block else answer)
    except (ValueError, RecursionError):
        raise ValueError('The model did not return a valid testbench JSON object.') from None
    fields(spec, ('name','analysis','connections','probes','measurements'), ('name','analysis','connections','probes','measurements'))
    name = spec['name']
    if not isinstance(name, str) or not NAME.fullmatch(name) or len(name) > 60:
        raise ValueError('Use a unique testbench identifier of up to 60 characters.')
    settings = analysis_spec(spec['analysis'])
    probes = spec['probes']
    ports = cell['ports']
    available = set(ports) if ports else circuit_nets(cell)
    if (not isinstance(probes, list) or not 1 <= len(probes) <= 64 or
        any(not isinstance(p, str) or p not in available or p == '0' for p in probes) or len(set(probes)) != len(probes)):
        raise ValueError('Choose distinct existing non-ground probes from this circuit.')
    connections = spec['connections']
    if not isinstance(connections, dict) or set(connections) != set(ports):
        raise ValueError('Assign exactly one connection to each exposed port. Use an empty mapping for a standalone circuit.')
    measurements = spec['measurements']
    if not isinstance(measurements, list) or len(measurements) > 64:
        raise ValueError('Choose up to 64 voltage measurements.')
    checks = []
    for m in measurements:
        fields(m, ('name','node','min','max','at'), ('name','node'))
        if not isinstance(m['name'], str) or not NAME.fullmatch(m['name']) or m['node'] not in probes:
            raise ValueError('Give each measurement an identifier and a saved probe.')
        checks.append(dict(name=m['name'], node=m['node'], kind='voltage',
                           **{k: number(m[k]) for k in ('min','max','at') if k in m}))
    q = clone(project)
    devices, mapping = [], {}
    if ports:
        dut = cell
        for index, port in enumerate(ports):
            mapping[port], part = fixture_device(port, connections[port], index)
            if part:
                devices.append(part)
        if any(mapping[p] == '0' for p in probes):
            raise ValueError('Choose a probe other than a grounded port.')
    else:
        dut, mapping = snapshot(q, cell, name, probes)
    devices.append(device('X', 'XDUT', 400, 230, cell=dut['id'], nets=mapping))
    fixture = dict(id=uid(), name=name, ports=[], devices=devices, shapes=[])
    if q.get('spice', {}).get('version') == 1:
        fixture['analog_model_scope'] = q['top']
    q['cells'].append(fixture)
    wiring.migrate(fixture, q)
    bench = testbenches.create(q, fixture['id'], name)
    bench.update(analysis={**settings, 'temperature': 27, 'corner': 'nominal'}, probes=probes, measurements=checks)
    q.setdefault('testbenches', []).append(bench)
    validate(q)
    units = {'step':' s', 'stop':' s', 'start':' Hz', 'end':' Hz', 'points':' points/decade'}
    details = [name + ' · ' + {'op':'Operating point','tran':'Transient','ac':'AC sweep'}[settings['type']],
               'Circuit: ' + cell['name'] + (' (linked)' if ports else ' (new standalone circuit snapshot)'),
               'Analysis: ' + ', '.join(f'{k} = {v:g}{units[k]}' for k,v in settings.items() if k != 'type'),
               'Conditions: nominal corner, 27 °C',
               'Probes: ' + ', '.join(probes)]
    if not ports:
        sources = [d['name'] for d in cell['devices'] if d['kind'] in ('V','I')]
        if sources:
            details.append('Existing sources in snapshot: ' + ', '.join(sources))
    details.extend(port + ' → ' + ', '.join(f'{k} = {v}' if k != 'kind' else str(v) for k,v in conn.items())
                   for port, conn in connections.items())
    for m in checks:
        limits = ', '.join(f'{k} = {m[k]}' for k in ('min','max','at') if k in m)
        details.append(f"{m['name']}: V({m['node']})" + (' · ' + limits if limits else ' · last sample'))
    return q['cells'][len(project['cells']):], bench, '\n'.join(s for s in details if s != 'Analysis: ')
