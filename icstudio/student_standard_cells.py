"""Editable CMOS standard-cell lessons and their measured checkpoints."""

import itertools
import json
from functools import lru_cache

from .model import clone, device, example, scalar, uid, validate


STARTER = 'standard-cell-'
PATH = dict(id='standard-cells', title='Standard Cells',
            subtitle='Build reusable CMOS gates and storage cells with measured test fixtures.')
SUPPLY = 1.8
LOAD = '10f'
VECTOR_NS = 12


@lru_cache(maxsize=1)
def course():
    from .getting_started import resource_root
    path = resource_root() / 'examples/student-hub/standard-cell-course.json'
    return {unit['key']: unit for unit in json.loads(path.read_text(encoding='utf-8'))}


def lessons():
    result = []
    for key, unit in course().items():
        steps = [
            dict(id='predict', kind='quiz', title='Predict how the cell switches',
                 instructions=unit['question'], options=unit['options'], answer=unit['answer'],
                 explanation=unit['explanation']),
            dict(id='wire', kind='check', title='Complete the transistor network',
                 instructions=f'Complete {unit["cell"]} and preserve its signal pins, VPWR and VGND.',
                 rule={'type': 'standard_cell', 'devices': unit['focus']}),
            dict(id='verify', kind='check', title='Verify the loaded cell',
                 instructions='Measure rising-edge capture and hold on Q.' if key == 'dff'
                 else 'Measure Y for each input combination with the supplied load.',
                 rule={'type': 'standard_cell'}),
        ]
        if key == 'inv':
            steps.append(dict(id='physical', kind='check', title='Make the first cell layout',
                              instructions='Generate the SKY130 inverter layout and verify its four physical ports.',
                              rule={'type': 'standard_cell'}))
        steps.append(dict(id='reflect', kind='reflection', title='Record the design trade-off',
                          instructions=unit['reflection']))
        starter = STARTER + key
        result.append(dict(id='sc-' + key, title=unit['title'], path=PATH['id'], topic=unit['topic'],
                           starter=starter, workspace=starter, standard_cell=key,
                           requires=[] if key == 'inv' else ['sc-inv'], minutes=30,
                           summary=unit['concept'], skills=['CMOS', 'standard cells', 'ngspice', unit['cell']],
                           doc='STUDENT_STANDARD_CELLS.md', steps=steps))
    return result


def teaching(key):
    unit = course()[key]
    return dict(concept=unit['concept'], worked_example=unit['explanation'],
                try_next='After the checkpoint, duplicate the project and repeat the run with twice the load. Compare the edge shape.',
                interview=unit['reflection'],
                artifact='Keep the reusable cell, its pin list, and the captured output waveform with your verification notes.')


def hints(key):
    unit = course()[key]
    return {'predict': [
        ['Which signal should I trace first?', 'Start at the output and trace the devices named in the schematic task.'],
        ['How do I tell when a MOSFET conducts?', 'A high gate turns on an NMOS with a low source. A low gate turns on a PMOS with a high source.'],
        ['What should I write down for a test vector?', 'Record the input levels, the conducting path, and the resulting output level. Include the clock edge for a storage cell.'],
        ['How can I verify my prediction?', unit['explanation']],
    ]}


def practice(key):
    unit = course()[key]
    output = 'Q' if key == 'dff' else 'Y'
    signal_pins = ', '.join([*unit['inputs'], output])
    count = len(samples(key))
    verify = ('At 30, 42, and 56 ns Q is high. At 79 and 99 ns Q is low. '
              'The 42 and 99 ns samples show hold after D changes.' if key == 'dff'
              else f'Check {count} input combinations. Read Y 8 ns into each 12 ns slot. '
              'Use at most 0.36 V for low and at least 1.44 V for high.')
    table = ', '.join(
        f'{"".join(str(bit) for bit in bits)} → {y}' for _, bits, y in samples(key)
    )
    tasks = {
        'wire': [f'Complete the CMOS network. Keep pins {signal_pins}, VPWR and VGND.',
                 ['Choose Open workspace to see the reusable cell.', unit['repair'],
                  'Choose Check this step to validate the interface and wiring.'],
                 unit['repair']],
        'verify': ['Use the 1.8 V, 10 fF fixture to verify the output. ' + verify,
                   ['Choose Open workspace to inspect the input sources, XDUT and CL.',
                    f'Choose Run lesson to simulate the cell with CL = {LOAD}.',
                    f'Open Results and inspect the input and out traces. {verify}',
                    'Choose Check this step to record the measured levels.'],
                   verify + (f' In pin order {", ".join(unit["inputs"])}, the expected output is {table}.'
                             if key != 'dff' else '')],
    }
    if key == 'inv':
        tasks['physical'] = [
            'Create a native SKY130 inverter layout with A, Y, VPWR and VGND physical ports.',
            ['Choose Open workspace to switch to Layout.',
             'Choose Generate inverter layout. Locate the two device rows and the supply contacts.',
             'Find the A and Y signal ports and the VPWR and VGND supply ports.',
             'Choose Check this step to check device bindings and port coverage.'],
            'The generated layout has two model-linked devices and physical ports A, Y, VPWR and VGND. '
            'The NMOS body goes to VGND and the PMOS body goes to VPWR.',
        ]
    return dict(tasks=tasks, questions={})


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
    from .wiring import set_label

    unit = course()[key]
    output = 'Q' if key == 'dff' else 'Y'
    ports = [*unit['inputs'], output, 'VPWR', 'VGND']
    p = example('empty')
    link_technology(p, bundled_technology())
    models = defaults(p['pdk'])
    bench = p['cells'][0]
    bench['name'] = key + '_characterization'
    cell = dict(id=uid(), name=key, ports=ports, shapes=[], devices=[])
    p['cells'].append(cell)
    # Give each repair terminal its own label before routing. Its starter
    # label can then be corrected in Properties without renaming another wire.
    isolated = {(name, pin): 'REPAIR_' + name for name, pin, _ in unit['faults']}
    positions = {'P': 0, 'N': 0}
    for polarity, name, gate, drain, source in network(key):
        kind = 'PMOS' if polarity == 'P' else 'NMOS'
        column = positions[polarity]
        positions[polarity] += 1
        part = create_device(p['pdk'], models[kind], name, 220+240*(column%4),
                             (200 if polarity == 'P' else 385)+395*(column//4))
        part['params'].update(w='2u' if polarity == 'P' else '1u', l='.15u', nf='1', m='1')
        nets = terminals(polarity, gate, drain, source)
        part['nets'] = {pin: isolated.get((name, pin), net) for pin, net in nets.items()}
        cell['devices'].append(part)
    configure_component(p, cell['id'], key, ports, {})
    nets = {pin: pin.lower() for pin in unit['inputs']}
    nets.update({output: 'out', 'VPWR': 'vdd', 'VGND': '0'})
    bench['devices'] = sources(key) + [device('X', 'XDUT', 510, 280, cell=cell['id'], nets=nets)]
    p['name'] = unit['cell'] + ' · standard cell lesson'
    p['student_standard_cell'] = dict(kind=key, cell=cell['id'], fixture=bench['id'])
    p['analysis'].update(analysis_settings(key))
    arrange(p)
    parts = {part['name']: part for part in cell['devices']}
    for name, pin, bad_net in unit['faults']:
        set_label(cell, parts[name]['id'], pin, bad_net, p)
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
    cell, fixture = context(project, key)
    if step in ('verify', 'reflect'):
        return fixture['id'], 'schematic'
    return cell['id'], 'layout' if step == 'physical' else 'schematic'


def check_fixture(project, key):
    cell, fixture = context(project, key)
    actual = {part['name']: part for part in fixture['devices']}
    inputs = course()[key]['inputs']
    expected_nets = {pin: pin.lower() for pin in inputs}
    expected_nets.update({'Q' if key == 'dff' else 'Y': 'out', 'VPWR': 'vdd', 'VGND': '0'})
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
    output = 'Q' if key == 'dff' else 'Y'
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


def build_layout(project):
    from .sky130_layout import generate_inverter
    check_wiring(project, 'inv')
    cell, _ = context(project, 'inv')
    generate_inverter(project, cell['id'])


def prepare(project, lesson, tools):
    from .run_environment import stamp
    from .spice_program import find_ngspice
    key = lesson['standard_cell']
    fixture = check_fixture(project, key)
    exe = find_ngspice(tools.get('ngspice', ''))
    if not exe:
        raise ValueError('Choose ngspice in Student Hub Engine setup.')
    job = dict(project=clone(project), cell=fixture['id'], engine='ngspice', executable=exe,
               settings=analysis_settings(key), student_lesson=lesson['id'], student_cell_step='verify')
    job['environment'] = stamp(job)
    return job


def read_samples(result, key):
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
        if level(voltage) != output:
            raise ValueError(f'At {ns} ns with {vector}, measured {voltage:.3g} V. Expected logic {output}.')
        readings.append(dict(time_ns=ns, inputs=dict(zip(pins, bits)), expected=output, output_V=voltage))
    return readings


def check(project, lesson, step, rows):
    from .student_hub import current_result
    key = lesson['standard_cell']
    if step == 'wire':
        return check_wiring(project, key)
    if step == 'physical':
        from .physical import connectivity
        from .sky130_layout import audit
        check_wiring(project, key)
        cell, _ = context(project, key)
        ports = {port['name'] for port in cell.get('layout_ports', [])}
        devices = {e['device_id'] for e in cell.get('pdk_layouts', [])}
        if (not cell.get('inverter_layout') or devices != {d['id'] for d in cell['devices']}
                or ports != set(cell['ports']) or audit(project, cell['id'])):
            raise ValueError('Generate the current inverter layout and keep all four physical ports.')
        issues = connectivity(project, cell['id'])['issues']
        if issues:
            raise ValueError(issues[0]['message'])
        return dict(physical_ports=sorted(ports), physical_devices=len(devices))
    fixture = check_fixture(project, key)
    tagged = [row for row in rows if row['job'].get('student_lesson') == lesson['id']
              and row['job'].get('student_cell_step') == 'verify' and row['job']['cell'] == fixture['id']]
    result, evidence = current_result(project, tagged)
    if result['settings'] != analysis_settings(key):
        raise ValueError('Run the supplied characterization analysis from the lesson guide.')
    readings = read_samples(result, key)
    return dict(**evidence, **check_wiring(project, key), logic_samples=readings)
