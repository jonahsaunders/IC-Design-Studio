"""Editable CMOS standard-cell lessons and their measured checkpoints."""

import itertools
import json
from functools import lru_cache
from pathlib import Path

from .model import clone, design_digest, device, example, file_digest, scalar, uid, validate


STARTER = 'standard-cell-'
PATH = dict(id='standard-cells', title='Standard Cells',
            subtitle='Place CMOS devices, finish the routing, and test the physical cell.')
SUPPLY = 1.8
LOAD = '10f'
VECTOR_NS = 12
RUN_TYPE = 'student_cell_layout_lab'
ARTIFACTS = tuple(model+'/'+name for model in ('schematic','layout')
                  for name in ('input.cir','result.raw','engine.log'))


@lru_cache(maxsize=1)
def course():
    from .getting_started import resource_root
    path = resource_root() / 'examples/student-hub/standard-cell-course.json'
    return {unit['key']: unit for unit in json.loads(path.read_text(encoding='utf-8'))}


def lessons():
    result = []
    for key, unit in course().items():
        steps = [
            dict(id='predict', kind='quiz', title='Plan the cell layout',
                 instructions=unit['question'], options=unit['options'], answer=unit['answer'],
                 explanation=unit['explanation']),
            dict(id='place', kind='check', title='Place devices and inspect the footprint',
                 instructions='Build two device rows and locate the boundary, power rails, and signal pins.',
                 rule={'type': 'standard_cell'}),
            dict(id='route', kind='check', title='Complete and check the layout',
                 instructions=f'Close the gaps on VPWR and {output_pin(key)}. Verify layer, width, and connectivity.',
                 rule={'type': 'standard_cell'}),
            dict(id='verify', kind='check', title='Test the routed cell',
                 instructions='Compare schematic and layout-loaded capture and hold on Q.' if key == 'dff'
                 else 'Compare schematic and layout-loaded output levels for all input vectors.',
                 rule={'type': 'standard_cell'}),
        ]
        steps.append(dict(id='reflect', kind='reflection', title='Record the design trade-off',
                          instructions=unit['reflection']))
        starter = STARTER + key
        result.append(dict(id='sc-' + key, title=unit['title'], path=PATH['id'], topic=unit['topic'],
                           starter=starter, workspace=starter+'-layout', standard_cell=key,
                           requires=[] if key == 'inv' else ['sc-inv'], minutes=30,
                           summary=unit['concept'], skills=['CMOS', 'standard cells', 'ngspice', unit['cell']],
                           doc='STUDENT_STANDARD_CELLS.md', steps=steps))
    return result


def teaching(key):
    unit = course()[key]
    return dict(concept=unit['concept'], worked_example=unit['explanation'],
                try_next='After the checkpoint, make a copy and use taller or wider routing, then compare the estimated shunt capacitance.',
                interview=unit['reflection'],
                artifact='Keep the routed cell, its physical ports, and the paired waveforms and test table.')


def hints(key):
    unit = course()[key]
    return {'predict': [
        ['Where are the power rails?', 'Find VPWR and VGND on the upper and lower Metal 3 tracks. Trace the via stacks down to the device contacts.'],
        ['How can I tell two crossing routes apart?', 'Trace each conductor on its own layer. A Metal 2 drop only joins a Metal 3 track where a via connects them.'],
        ['Which net should I inspect for this cell?', unit['focus']],
        ['What should I look for when the cell runs?', unit['explanation']],
    ]}


def practice(key):
    unit = course()[key]
    output = output_pin(key)
    count = len(samples(key))
    verify = ('At 30, 42, and 56 ns Q is high. At 79 and 99 ns Q is low. '
              'The 42 and 99 ns samples show hold after D changes.' if key == 'dff'
              else f'Check {count} input combinations. Read Y 8 ns into each 12 ns slot. '
              'Use at most 0.36 V for low and at least 1.44 V for high.')
    table = ', '.join(
        f'{"".join(str(bit) for bit in bits)} → {y}' for _, bits, y in samples(key)
    )
    tasks = {
        'place': [
            'Place the model-linked transistors in two device rows. Preserve the common 24.5 µm footprint height.',
            ['Choose Place cell rows to create the device geometry, outline, contacts, and unfinished routes.',
             'Open workspace and find the PMOS row above the NMOS row. The width depends on the number of devices.',
             'Check where the upper and lower rails meet the side boundaries for an adjacent cell.',
             unit['focus'], 'Choose Check this step to verify the footprint and physical port inventory.'],
            'The PMOS row is above the NMOS row. VPWR and VGND share the same track heights across all six cells. '
            + unit['focus'],
        ],
        'route': [
            f'Complete the Metal 3 gaps on VPWR and {output}. Match each track width and stay inside the footprint.',
            ['Choose Open workspace. Find the gap in the upper VPWR rail and the gap in the '+output+' signal track.',
             'Choose Add route and select one open net. Select Metal 3 and enter the two endpoints and the width shown for that track.',
             f'Add a 0.9 µm path for VPWR and a 0.64 µm path for {output}. Connect the existing Metal 3 ends.',
             'Choose Check this step to verify the connected pins, routing geometry, and spacing.'],
            f'Bridge the two straight Metal 3 gaps in the Add route form. VPWR uses 0.9 µm width and {output} uses 0.64 µm. '
            'Each path lands on both existing track ends. In Step by Step, the form shows the exact coordinates.',
        ],
        'verify': [
            'Compare the schematic with the routed cell under a 1.8 V, 10 fF fixture. '+verify,
            ['Fix any layout connectivity findings before testing.',
             f'Choose Run lesson to test both models with CL = {LOAD}. The layout case adds the estimated metal capacitance.',
             f'Open Results. Compare the waveforms and use the Samples tab to check the voltages. {verify}',
             'Compare the added output capacitance and record the result with Check this step.'],
            verify + (f' In pin order {", ".join(unit["inputs"])}, the expected output is {table}.'
                      if key != 'dff' else '') + ' Both models should reach the same logic levels at the sample times.',
        ],
    }
    return dict(tasks=tasks, questions={})


def output_pin(key):
    return 'Q' if key == 'dff' else 'Y'


def network(key):
    """Return named devices as (polarity, name, gate, drain, source)."""
    def inverter(label, source, target):
        return [('P', 'MP_' + label, source, target, 'VPWR'),
                ('N', 'MN_' + label, source, target, 'VGND')]

    def transmission(label, positive, negative, source, target):
        return [('N', 'MN_' + label, positive, target, source),
                ('P', 'MP_' + label, negative, target, source)]

    if key == 'inv':
        return inverter('A', 'A', 'Y')
    if key == 'nand2':
        return [('P', 'MP_A', 'A', 'Y', 'VPWR'), ('P', 'MP_B', 'B', 'Y', 'VPWR'),
                ('N', 'MN_A', 'A', 'Y', 'N_STACK'), ('N', 'MN_B', 'B', 'N_STACK', 'VGND')]
    if key == 'nor2':
        return [('P', 'MP_A', 'A', 'P_STACK', 'VPWR'), ('P', 'MP_B', 'B', 'Y', 'P_STACK'),
                ('N', 'MN_A', 'A', 'Y', 'VGND'), ('N', 'MN_B', 'B', 'Y', 'VGND')]
    if key == 'aoi21':
        return [('P', 'MP_C', 'C', 'P_BRANCH', 'VPWR'),
                ('P', 'MP_A', 'A', 'Y', 'P_BRANCH'), ('P', 'MP_B', 'B', 'Y', 'P_BRANCH'),
                ('N', 'MN_A', 'A', 'Y', 'N_STACK'), ('N', 'MN_B', 'B', 'N_STACK', 'VGND'),
                ('N', 'MN_C', 'C', 'Y', 'VGND')]
    if key == 'mux2':
        return (inverter('SEL', 'S', 'S_B')
                + transmission('A', 'S_B', 'S', 'A', 'SELECTED')
                + transmission('B', 'S', 'S_B', 'B', 'SELECTED')
                + inverter('BUF1', 'SELECTED', 'Y_B') + inverter('BUF2', 'Y_B', 'Y'))
    if key == 'dff':
        return (inverter('CLK', 'CLK', 'CLK_B')
                + transmission('M_IN', 'CLK_B', 'CLK', 'D', 'M0')
                + inverter('M1', 'M0', 'M1') + inverter('M2', 'M1', 'M2')
                + transmission('M_FB', 'CLK', 'CLK_B', 'M2', 'M0')
                + transmission('S_IN', 'CLK', 'CLK_B', 'M2', 'S0')
                + inverter('S1', 'S0', 'S1') + inverter('Q', 'S1', 'Q')
                + transmission('S_FB', 'CLK_B', 'CLK', 'Q', 'S0'))
    raise ValueError('Unknown standard cell.')


def terminals(polarity, gate, drain, source):
    return dict(g=gate, d=drain, s=source, b='VPWR' if polarity == 'P' else 'VGND')


def samples(key):
    if key == 'dff':
        return [(30, (1, 1), 1), (42, (0, 1), 1), (56, (0, 0), 1),
                (79, (0, 1), 0), (99, (1, 0), 0)]
    truth = {
        'inv': lambda a: not a,
        'nand2': lambda a, b: not (a and b),
        'nor2': lambda a, b: not (a or b),
        'aoi21': lambda a, b, c: not ((a and b) or c),
        'mux2': lambda s, a, b: b if s else a,
    }[key]
    vectors = itertools.product((0, 1), repeat=len(course()[key]['inputs']))
    return [(i * VECTOR_NS + 8, bits, int(truth(*bits))) for i, bits in enumerate(vectors)]


def stimulus(key):
    if key == 'dff':
        return {'D': (12, 80, '.3'), 'CLK': (24, 48, '.5')}
    pins = course()[key]['inputs']
    delays = [VECTOR_NS * 2 ** i for i in reversed(range(len(pins)))]
    return {pin: (delay, delay * 2, '.5') for pin, delay in zip(pins, delays)}


def sources(key):
    parts = [device('V', 'VDD', 120, 100, value=str(SUPPLY), nets={'p': 'vdd', 'n': '0'})]
    for i, (pin, (delay, period, duty)) in enumerate(stimulus(key).items()):
        pulse = dict(type='pulse', low='0', high=str(SUPPLY), delay=f'{delay}n', period=f'{period}n',
                     duty=duty, rise='100p', fall='100p', ac='0')
        parts.append(device('V', 'V_'+pin, 120, 260+160*i, source=pulse, nets={'p': pin.lower(), 'n': '0'}))
    parts.append(device('C', 'CL', 800, 290, value=LOAD, nets={'p': 'out', 'n': '0'}))
    return parts


def create(key):
    from .catalog import create_device, link_technology
    from .components import configure_component
    from .example_schematics import arrange
    from .project_templates import defaults
    from .student_analog import bundled_technology

    unit = course()[key]
    output = output_pin(key)
    ports = [*unit['inputs'], output, 'VPWR', 'VGND']
    p = example('empty')
    link_technology(p, bundled_technology())
    models = defaults(p['pdk'])
    bench = p['cells'][0]
    bench['name'] = key + '_characterization'
    cell = dict(id=uid(), name=key, ports=ports, shapes=[], devices=[])
    p['cells'].append(cell)
    positions = {'P': 0, 'N': 0}
    for polarity, name, gate, drain, source in network(key):
        kind = 'PMOS' if polarity == 'P' else 'NMOS'
        column = positions[polarity]
        positions[polarity] += 1
        part = create_device(p['pdk'], models[kind], name, 220+240*(column%4),
                             (200 if polarity == 'P' else 385)+395*(column//4))
        part['params'].update(w='2u' if polarity == 'P' else '1u', l='.15u', nf='1', m='1')
        part['nets'] = terminals(polarity, gate, drain, source)
        cell['devices'].append(part)
    configure_component(p, cell['id'], key, ports, {})
    nets = {pin: pin.lower() for pin in unit['inputs']}
    nets.update({output: 'out', 'VPWR': 'vdd', 'VGND': '0'})
    bench['devices'] = sources(key) + [device('X', 'XDUT', 510, 280, cell=cell['id'], nets=nets)]
    p['name'] = unit['cell'] + ' · standard cell lesson'
    p['student_standard_cell'] = dict(kind=key, cell=cell['id'], fixture=bench['id'])
    p['analysis'].update(analysis_settings(key))
    arrange(p)
    return validate(p)


def analysis_settings(key):
    stop = 104 if key == 'dff' else VECTOR_NS * len(samples(key))
    return dict(type='tran', step='20p', stop=f'{stop}n', temperature=27, corner='nominal', uic=False)


def context(project, key):
    bound = project.get('student_standard_cell', {})
    by_id = {cell['id']: cell for cell in project['cells']}
    if bound.get('kind') != key or not all(bound.get(k) in by_id for k in ('cell', 'fixture')):
        raise ValueError('Resume this standard-cell project from Student Hub.')
    return by_id[bound['cell']], by_id[bound['fixture']]


def focus(project, key, step):
    cell, _ = context(project, key)
    return cell['id'], 'layout'


def check_fixture(project, key):
    cell, fixture = context(project, key)
    actual = {part['name']: part for part in fixture['devices']}
    inputs = course()[key]['inputs']
    expected_nets = {pin: pin.lower() for pin in inputs}
    expected_nets.update({output_pin(key): 'out', 'VPWR': 'vdd', 'VGND': '0'})
    instance = actual.get('XDUT', {})
    if (len(fixture['devices']) != len(inputs) + 3 or instance.get('kind') != 'X'
            or instance.get('cell') != cell['id'] or instance.get('nets') != expected_nets):
        raise ValueError('Keep the supplied fixture wired to the reusable XDUT cell.')
    for expected in sources(key):
        part = actual.get(expected['name'], {})
        if (part.get('kind') != expected['kind'] or part.get('nets') != expected['nets']
                or scalar(part['value']) != scalar(expected['value'])
                or part.get('source') != expected.get('source')):
            raise ValueError('Restore the supplied load, supply and input sources in the fixture.')
    return fixture


def check_wiring(project, key):
    cell, _ = context(project, key)
    output = output_pin(key)
    expected_ports = [*course()[key]['inputs'], output, 'VPWR', 'VGND']
    if cell['ports'] != expected_ports:
        raise ValueError('Preserve the cell pins and their order: ' + ', '.join(expected_ports) + '.')
    by_name = {d['name']: d for d in cell['devices']}
    definition = network(key)
    if len(cell['devices']) != len(definition) or project['pdk'].get('package_lock', {}).get('id') != 'sky130A':
        raise ValueError('Use the supplied network of SKY130 transistors.')
    for polarity, name, gate, drain, source in definition:
        part = by_name.get(name, {})
        kind = 'PMOS' if polarity == 'P' else 'NMOS'
        if part.get('kind') != kind or part.get('model_ref', {}).get('pdk') != 'sky130A':
            raise ValueError(f'Keep {name} as a SKY130 {kind}.')
        for pin, net in terminals(polarity, gate, drain, source).items():
            if part['nets'].get(pin) != net:
                raise ValueError(f'Connect {name} terminal {pin} to {net}.')
    return dict(standard_cell=key, ports=expected_ports, transistors=len(definition))


def build_layout(project, key):
    from .student_cell_layout import place
    check_wiring(project, key)
    cell, _ = context(project, key)
    place(project, cell)


def prepare(project, lesson, tools):
    from .run_environment import stamp
    from .spice_program import find_ngspice
    from .student_cell_layout import check_routing
    key = lesson['standard_cell']
    cell, _ = context(project, key)
    check_routing(project, cell)
    fixture = check_fixture(project, key)
    exe = find_ngspice(tools.get('ngspice', ''))
    if not exe:
        raise ValueError('Choose ngspice in Student Hub Engine setup.')
    job = dict(project=clone(project), cell=fixture['id'], engine='ngspice', executable=exe,
               settings=dict(type=RUN_TYPE, cell=key, analysis=analysis_settings(key)),
               student_lesson=lesson['id'], student_cell_step='verify')
    job['environment'] = stamp(job)
    return job


def readings(result, key):
    from .student_hub import at

    def level(voltage):
        if voltage <= 0.2 * SUPPLY:
            return 0
        if voltage >= 0.8 * SUPPLY:
            return 1
        return None

    readings = []
    for ns, bits, output in samples(key):
        time = ns * 1e-9
        pins = course()[key]['inputs']
        actual = tuple(level(at(result, pin.lower(), time)) for pin in pins)
        voltage = at(result, 'out', time)
        vector = ', '.join(f'{pin}={bit}' for pin, bit in zip(pins, bits))
        if actual != bits:
            raise ValueError(f'At {ns} ns the fixture did not apply {vector}.')
        readings.append(dict(time_ns=ns, inputs=dict(zip(pins, bits)), expected=output, output_V=voltage,
                             passed=level(voltage)==output))
    return readings


def read_samples(result, key):
    measured = readings(result, key)
    for row in measured:
        if not row['passed']:
            vector = ', '.join(f'{pin}={bit}' for pin,bit in row['inputs'].items())
            raise ValueError(f'At {row["time_ns"]} ns with {vector}, measured {row["output_V"]:.3g} V. '
                             f'Expected logic {row["expected"]}.')
    return measured


def run(project, job, directory, progress):
    from .engines import run_ngspice
    from .student_cell_layout import check_routing, estimate
    key = job['settings']['cell']
    cell, _ = context(project, key)
    check_wiring(project, key)
    check_routing(project, cell)
    fixture = check_fixture(project, key)
    if fixture['id'] != job['cell'] or job['settings']['analysis'] != analysis_settings(key):
        raise ValueError('Use the Standard Cells lesson fixture and its analysis settings.')
    loaded, caps = estimate(project, cell)
    directory = Path(directory)
    def simulate(model, project, offset):
        target = directory/model
        target.mkdir(parents=True, exist_ok=True)
        return run_ngspice(project, fixture['id'], analysis_settings(key), job['executable'], target,
                           lambda fraction,message: progress(offset+fraction/2, model.title()+ ' · '+message))
    nominal = simulate('schematic', project, 0)
    result = simulate('layout', loaded, .5)
    result.update(settings=job['settings'], design_hash=design_digest(project),
                  student_cell_layout=dict(
                      schematic={name:nominal[name] for name in ('x','traces','x_label','settings')},
                      capacitors=caps, artifacts={name:file_digest(directory/name) for name in ARTIFACTS}))
    result['warnings'].append('Layout metal load uses the lesson’s lumped ground-capacitance estimate.')
    return result


def validate_result(result, job, directory):
    key = job['settings'].get('cell')
    record = result.get('student_cell_layout', {})
    if key not in course() or result['settings'] != job['settings'] or job.get('student_lesson') != 'sc-'+key:
        raise ValueError('The captured layout experiment does not match this lesson.')
    try:
        hashes = {name:file_digest(directory/name) for name in ARTIFACTS}
    except OSError as exc:
        raise ValueError('A captured standard-cell simulation artifact is missing.') from exc
    if record.get('artifacts') != hashes:
        raise ValueError('A captured standard-cell simulation artifact has changed.')
    if not record.get('capacitors'):
        raise ValueError('The layout-loaded simulation is missing its metal capacitance estimate.')
    readings(record.get('schematic', {}), key)
    readings(result, key)


def check(project, lesson, step, rows):
    from .student_hub import current_result
    from .student_cell_layout import check_placement, check_routing
    key = lesson['standard_cell']
    cell, _ = context(project, key)
    check_wiring(project, key)
    if step == 'place':
        return check_placement(project, cell)
    geometry = check_routing(project, cell)
    if step == 'route':
        return geometry
    fixture = check_fixture(project, key)
    tagged = [row for row in rows if row['job'].get('student_lesson') == lesson['id']
              and row['job']['settings']['type']==RUN_TYPE and row['job']['cell'] == fixture['id']]
    result, evidence = current_result(project, tagged)
    layout = result['student_cell_layout']
    return dict(**evidence, **geometry, logic_samples=read_samples(result, key),
                schematic_samples=read_samples(layout['schematic'], key),
                capacitance_estimate=layout['capacitors'])
