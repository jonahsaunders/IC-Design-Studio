"""Editable CMOS standard-cell lessons and their measured checkpoints."""

import itertools
import json
from functools import lru_cache
from pathlib import Path

from . import student_cell_characterization as characterization, student_cell_row as row_lab, student_logic_cells as logic
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
    from .student_cell_specs import target_text
    result = []
    for key, unit in course().items():
        if key == row_lab.KEY:
            result.append(row_lesson(unit))
            continue
        base = unit.get('base', key)
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
                 instructions='Compare schematic and layout-loaded capture and hold on Q.' if base == 'dff'
                 else 'Compare schematic and layout-loaded output levels for all input vectors.',
                 rule={'type': 'standard_cell'}),
        ]
        if key=='half-adder':
            steps[2]['instructions'] = 'Close the gaps on VPWR, Y (sum), and CO (carry). Check all three routes.'
        steps.append(dict(id='reflect', kind='reflection', title='Record the design trade-off',
                          instructions=unit['reflection']))
        starter = STARTER + key
        lesson = dict(id='sc-' + key, title=unit['title'], path=PATH['id'], topic=unit['topic'],
                           starter=starter, workspace=starter+'-layout', standard_cell=key,
                           requires=unit.get('requires', [] if key == 'inv' else ['sc-'+base] if base!=key else ['sc-inv']),
                           minutes=40 if unit.get('characterization') else 30,
                           summary=unit['concept'], skills=['CMOS', 'standard cells', 'ngspice', unit['cell']],
                           doc='STUDENT_STANDARD_CELLS.md', steps=steps)
        if unit.get('specs'):
            lesson['goal'] = target_text(unit)
            steps[3]['instructions'] += ' Meet these targets. '+lesson['goal']+'.'
        result.append(lesson)
    return result


def row_lesson(unit):
    starter = STARTER+row_lab.KEY
    return dict(id='sc-'+row_lab.KEY, title=unit['title'], path=PATH['id'], topic=unit['topic'],
                starter=starter, workspace=starter+'-layout', standard_cell=row_lab.KEY,
                requires=unit['requires'], minutes=20, summary=unit['concept'], goal=row_lab.GOAL,
                skills=['standard cells', 'cell abutment', 'power routing'], doc='STUDENT_STANDARD_CELLS.md',
                steps=[
                    dict(id='predict', kind='quiz', title='Plan the shared row', instructions=unit['question'],
                         options=unit['options'], answer=unit['answer'], explanation=unit['explanation']),
                    dict(id='place', kind='check', title='Align and verify the two cells',
                         instructions='Move the NAND until its left edge meets the inverter and the rails align. '
                                      'Check the seam for opens, shorts, and spacing violations.',
                         rule={'type': 'standard_cell'}),
                    dict(id='reflect', kind='reflection', title='Record the seam check', instructions=unit['reflection']),
                ])


def teaching(key):
    unit = course()[key]
    return dict(concept=unit['concept'], worked_example=unit['explanation'],
                try_next=('Slide one child away from the other in a copy. Check how the gap affects rail continuity.'
                          if key == row_lab.KEY else
                          'After the checkpoint, make a copy and use taller or wider routing, then compare the estimated shunt capacitance.'),
                interview=unit['reflection'],
                artifact=('Keep the hierarchical row and the verified seam dimensions.'
                          if key == row_lab.KEY else 'Keep the routed cell, its physical ports, and the paired waveforms and test table.'))


def hints(key):
    unit = course()[key]
    if key == row_lab.KEY:
        return {'predict': [
            ['Which instance should I move?', 'Keep the inverter as the left reference and move the NAND.'],
            ['How do I know where the seam is?', 'Read the right edge of the inverter on the layout ruler.'],
            ['Do signal tracks need to align too?', 'Keep independent signals isolated. Only the two power rails are shared in this row.'],
            ['How do I check the result?', 'Run Check this step after the outlines touch. Studio tests both rails and layer spacing.'],
        ]}
    return {'predict': [
        ['Where are the power rails?', 'Find VPWR and VGND on the upper and lower Metal 3 tracks. Trace the via stacks down to the device contacts.'],
        ['How can I tell two crossing routes apart?', 'Trace each conductor on its own layer. A Metal 2 drop only joins a Metal 3 track where a via connects them.'],
        ['Which net should I inspect for this cell?', unit['focus']],
        ['What should I look for when the cell runs?', unit['explanation']],
    ]}


def practice(key):
    from .student_cell_specs import target_text
    unit = course()[key]
    if key == row_lab.KEY:
        return dict(tasks={'place': [
            row_lab.GOAL,
            ['Open the hierarchical row layout. Find the left inverter and right NAND.',
             'Use the layout ruler to measure the right edge of the inverter.',
             'Choose Align cell row. Enter X at that right edge and Y on the same baseline as the inverter.',
             'Inspect VPWR and VGND at the seam and choose Check this step.'],
            unit['solution'],
        ]}, questions={})
    output = output_pin(key)
    count = len(samples(key))
    verify = ('Check capture and hold under the 40 fF load. Use the Targets tab for both half-supply clock-to-Q measurements.'
              if key == 'dff-clock' else
              'At 30, 42, and 56 ns Q is high. At 79 and 99 ns Q is low. '
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
            'The PMOS row is above the NMOS row. VPWR and VGND share the same track heights across the teaching cells. '
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
    if key=='half-adder':
        tasks['route'][0] = 'Close the VPWR, sum (Y) and carry (CO) gaps in Metal 3.'
        tasks['route'][1][0] = 'Locate all three gaps. Trace the two output pins separately.'
        tasks['route'][1][2] = 'Use 0.9 µm for VPWR and 0.64 µm for both output routes.'
        tasks['route'][2] = 'Bridge VPWR at 0.9 µm and Y and CO at 0.64 µm each. The guided route form lists all three gaps.'
    if unit.get('specs'):
        tasks['place'][1][0] = 'Choose Size and place to enter the design dimensions and build a layout.'
        fixture = characterization.LOAD_DESCRIPTION.get(key, fixture_load(key)+' output load')
        tasks['verify'][0] = 'Hit the targets at 1.8 V with '+fixture+'. '+target_text(unit)+'.'
        tasks['verify'][1] = [
            'Complete both routes and choose Run lesson to capture the schematic and layout-loaded cases.',
            'Open Results and read the measured values against the limits in Targets.',
            'If a target fails, choose Revise design. '+unit['tune'],
            'Review the logic samples and choose Check this step after every target passes.',
        ]
        if key in logic.KEYS:
            tasks['verify'][1].insert(2, unit['measure'])
        if key == 'dff-aperture':
            tasks['verify'][1] = [
                'Run the lesson to capture the routed cell and timing sweep.',
                'Open Timing sweep in Results. Check the settled 1500 ps reference in each group.',
                'Move toward the clock until Q fails to capture or clock-to-Q exceeds 110% of its settled value.',
                'Record the adjacent passing and failing offsets for each group and check the step.',
            ]
        tasks['verify'][2] = unit['solution']
    return dict(tasks=tasks, questions={})


def output_pin(key):
    return 'Q' if course()[key].get('base',key) == 'dff' else 'Y'


def fixture_load(key):
    return course()[key].get('load', LOAD)


def network(key):
    """Return named devices as (polarity, name, gate, drain, source)."""
    def inverter(label, source, target):
        return [('P', 'MP_' + label, source, target, 'VPWR'),
                ('N', 'MN_' + label, source, target, 'VGND')]

    def transmission(label, positive, negative, source, target):
        return [('N', 'MN_' + label, positive, target, source),
                ('P', 'MP_' + label, negative, target, source)]

    key = course()[key].get('base',key)
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
    if key in logic.KEYS:
        return logic.network(key,inverter)
    return characterization.networks(key, inverter, transmission)


def terminals(polarity, gate, drain, source):
    return dict(g=gate, d=drain, s=source, b='VPWR' if polarity == 'P' else 'VGND')


def samples(key):
    if key in logic.SAMPLES: return logic.SAMPLES[key]
    special = {
        'nor-rise': [(8,(0,0),1),(20,(0,1),0),(56,(1,0),0),(68,(1,1),0)],
        'mux-glitch': [(8,(0,0,0),0),(16,(1,0,0),0),(32,(0,0,1),0),(40,(1,0,1),1),
                       (56,(0,1,0),1),(64,(1,1,0),0),(80,(0,1,1),1),(88,(1,1,1),1)],
        'xor-energy': [(8,(0,0),0),(20,(0,1),1),(32,(1,1),0),(44,(1,0),1),(51,(0,0),0)],
        'dff-aperture': [(4,(0,1),0),(8,(1,0),0),(12.8,(1,1),1),(15,(0,1),1),(18,(0,0),1)],
    }
    if key in special:
        return special[key]
    if key == 'dff-clock':
        return [(30, (1, 1), 1), (46, (0, 1), 1), (56, (0, 0), 1),
                (79, (0, 1), 0), (99, (1, 0), 0), (126, (0, 1), 1)]
    if key == 'dff':
        return [(30, (1, 1), 1), (42, (0, 1), 1), (56, (0, 0), 1),
                (79, (0, 1), 0), (99, (1, 0), 0)]
    truth = {
        'inv': lambda a: not a,
        'buffer': lambda a: a,
        'nand2': lambda a, b: not (a and b),
        'nor2': lambda a, b: not (a or b),
        'aoi21': lambda a, b, c: not ((a and b) or c),
        'mux2': lambda s, a, b: b if s else a,
    }[course()[key].get('base',key)]
    vectors = itertools.product((0, 1), repeat=len(course()[key]['inputs']))
    return [(i * VECTOR_NS + 8, bits, int(truth(*bits))) for i, bits in enumerate(vectors)]


def stimulus(key):
    if key in logic.STIMULUS: return logic.STIMULUS[key]
    special = {
        'nor-rise': {'A': (48,96,'.5'), 'B': (12,24,'.5')},
        'mux-glitch': {'S': (12,24,'.25'), 'A': (48,96,'.5'), 'B': (24,48,'.5')},
        'xor-energy': {'A': (24,48,'.5'), 'B': (12,48,'.5')},
        'dff-aperture': {'D': (5,40,'.2'), 'CLK': (2,10,'.4')},
    }
    if key in special:
        return special[key]
    if key == 'dff-clock':
        return {'D': (12, 80, '.4'), 'CLK': (24, 48, '.5')}
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
        net = {('mux-glitch','S'):'s_drive', ('schmitt','A'):'a_drive'}.get((key,pin),pin.lower())
        parts.append(device('V', 'V_'+pin, 120, 260+160*i, source=pulse, nets={'p': net, 'n': '0'}))
    if key != 'buffer-fo4':
        parts.append(device('C', 'CL', 800, 290, value=fixture_load(key), nets={'p': 'out', 'n': '0'}))
    return parts + characterization.extra_sources(key) + logic.extras(key)


def create(key):
    if key == row_lab.KEY:
        return row_lab.create()
    from .catalog import create_device, link_technology
    from .components import configure_component
    from .example_schematics import arrange
    from .project_templates import defaults
    from .student_analog import bundled_technology

    unit = course()[key]
    output = output_pin(key)
    ports = [*unit['inputs'], output, *logic.PORTS.get(key,{}), 'VPWR', 'VGND']
    p = example('empty')
    link_technology(p, bundled_technology())
    models = defaults(p['pdk'])
    bench = p['cells'][0]
    cell_name = key.replace('-', '_')
    bench['name'] = cell_name + '_characterization'
    cell = dict(id=uid(), name=cell_name, ports=ports, shapes=[], devices=[])
    p['cells'].append(cell)
    positions = {'P': 0, 'N': 0}
    for polarity, name, gate, drain, source in network(key):
        kind = 'PMOS' if polarity == 'P' else 'NMOS'
        column = positions[polarity]
        positions[polarity] += 1
        part = create_device(p['pdk'], models[kind], name, 220+240*(column%4),
                             (200 if polarity == 'P' else 385)+395*(column//4))
        width = unit.get('starter_widths', {}).get(name, 2 if polarity == 'P' else 1)
        part['params'].update(w=f'{width:g}u', l='.15u', nf='1', m='1')
        part['nets'] = terminals(polarity, gate, drain, source)
        cell['devices'].append(part)
    configure_component(p, cell['id'], cell_name, ports, {})
    nets = {pin: pin.lower() for pin in unit['inputs']}
    nets.update({output: 'out', 'VPWR': 'vdd', 'VGND': '0'})
    nets.update(logic.PORTS.get(key,{}))
    bench['devices'] = sources(key) + [device('X', 'XDUT', 535, 280, cell=cell['id'], nets=nets)]
    bench['devices'] += logic.extra_instances(key,cell['id'])
    if key == 'buffer-fo4':
        inv, _ = context(create('inv'), 'inv')
        p['cells'].append(inv)
        bench['devices'] += characterization.fo4_devices(inv['id'])
    p['name'] = unit['cell'] + ' · standard cell lesson'
    p['student_standard_cell'] = dict(kind=key, cell=cell['id'], fixture=bench['id'])
    p['analysis'].update(analysis_settings(key))
    arrange(p)
    return validate(p)


def analysis_settings(key):
    stop = {'dff': 104, 'dff-clock': 136, 'nor-rise': 74, 'mux-glitch': 96,
            'buffer-fo4': 32, 'xor-energy': 55, 'dff-aperture': 19}.get(key, VECTOR_NS * len(samples(key)))
    stop = logic.STOP.get(key,stop)
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
    expected_nets.update(logic.PORTS.get(key,{}))
    expected = sources(key) + logic.extra_instances(key,cell['id'])
    if key == 'buffer-fo4':
        load = actual.get('XLOAD1', {}).get('cell')
        inv = next((child for child in project['cells'] if child['id'] == load and child['name'] == 'inv'), None)
        if inv is None:
            raise ValueError('Keep four identical SKY130 inverter loads at the buffer output.')
        check_devices(inv, 'inv', fixed_widths=True)
        expected += characterization.fo4_devices(load)
    if (len(fixture['devices']) != len(expected) + 1 or instance.get('kind') != 'X'
            or instance.get('cell') != cell['id'] or instance.get('nets') != expected_nets):
        raise ValueError('Keep the supplied fixture wired to the reusable XDUT cell.')
    for part in expected:
        supplied = actual.get(part['name'], {})
        if (supplied.get('kind') != part['kind'] or supplied.get('nets') != part['nets']
                or supplied.get('cell') != part.get('cell') or supplied.get('parameters', {}) != part.get('parameters', {})
                or scalar(supplied['value']) != scalar(part['value']) or supplied.get('source') != part.get('source')):
            raise ValueError('Restore the supplied load, supply and input sources in the fixture.')
    return fixture


def check_wiring(project, key):
    cell, _ = context(project, key)
    output = output_pin(key)
    expected_ports = [*course()[key]['inputs'], output, *logic.PORTS.get(key,{}), 'VPWR', 'VGND']
    if cell['ports'] != expected_ports:
        raise ValueError('Preserve the cell pins and their order: ' + ', '.join(expected_ports) + '.')
    if project['pdk'].get('package_lock', {}).get('id') != 'sky130A':
        raise ValueError('Use the supplied SKY130 device models.')
    check_devices(cell,key)
    return dict(standard_cell=key, ports=expected_ports, transistors=len(cell['devices']))


def check_devices(cell, key, fixed_widths=False):
    by_name = {d['name']: d for d in cell['devices']}
    definition = network(key)
    if len(cell['devices']) != len(definition) or set(by_name) != {row[1] for row in definition}:
        raise ValueError('Use the supplied network of SKY130 transistors.')
    if fixed_widths and cell['ports'] != ['A','Y','VPWR','VGND']:
        raise ValueError('Keep the original inverter input and output ports.')
    for polarity, name, gate, drain, source in definition:
        part = by_name.get(name, {})
        kind = 'PMOS' if polarity == 'P' else 'NMOS'
        if part.get('kind') != kind or part.get('model_ref', {}).get('pdk') != 'sky130A':
            raise ValueError(f'Keep {name} as a SKY130 {kind}.')
        if (fixed_widths or course()[key].get('specs')) and any(
                scalar(part['params'].get(field,1)) != scalar(expected)
                for field,expected in (('l','.15u'),('nf',1),('m',1))):
            raise ValueError('Keep the nominal 0.15 µm channel length and one device finger per transistor.')
        if fixed_widths and scalar(part['params']['w']) != scalar('2u' if polarity=='P' else '1u'):
            raise ValueError('Keep the original inverter load dimensions.')
        for pin, net in terminals(polarity, gate, drain, source).items():
            if part['nets'].get(pin) != net:
                raise ValueError(f'Connect {name} terminal {pin} to {net}.')


def build_layout(project, key, dimensions=None, replace=False):
    from .student_cell_layout import PITCH, place
    if key == row_lab.KEY:
        cell, _ = context(project,key)
        if dimensions is not None:
            row_lab.move(project,cell,dimensions)
        return
    check_wiring(project, key)
    cell, _ = context(project, key)
    if dimensions is None:
        place(project, cell, course()[key].get('starter_pitch',PITCH))
        return
    from .student_cell_specs import apply_design
    if cell['shapes'] and not replace:
        raise ValueError('Confirm before replacing the routed layout.')
    pitch = apply_design(cell,key,dimensions)
    for field in ('shapes','layout_pins','layout_ports','layout_texts','layout_instances','pdk_layouts'):
        cell[field] = []
    cell.pop('student_cell_layout',None)
    place(project,cell,pitch)


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
        row = dict(time_ns=ns, inputs=dict(zip(pins, bits)), expected=output, output_V=voltage,
                   passed=level(voltage)==output)
        if key=='half-adder':
            carry = at(result,'carry',time)
            row.update(carry_V=carry, expected_carry=int(all(bits)), passed=row['passed'] and level(carry)==int(all(bits)))
        readings.append(row)
    return readings


def read_samples(result, key):
    measured = readings(result, key)
    for row in measured:
        if not row['passed']:
            vector = ', '.join(f'{pin}={bit}' for pin,bit in row['inputs'].items())
            carry = (f' Carry was {row["carry_V"]:.3g} V, expected logic {row["expected_carry"]}.'
                     if 'carry_V' in row else '')
            raise ValueError(f'At {row["time_ns"]} ns with {vector}, measured {row["output_V"]:.3g} V. '
                             f'Expected logic {row["expected"]}.'+carry)
    return measured


def run(project, job, directory, progress):
    from .engines import run_ngspice
    from .student_cell_layout import check_routing, estimate
    from .student_cell_specs import measure
    key = job['settings']['cell']
    cell, _ = context(project, key)
    check_wiring(project, key)
    geometry = check_routing(project, cell)
    fixture = check_fixture(project, key)
    if fixture['id'] != job['cell'] or job['settings']['analysis'] != analysis_settings(key):
        raise ValueError('Use the Standard Cells lesson fixture and its analysis settings.')
    loaded, caps = estimate(project, cell)
    directory = Path(directory)
    reference_run = key in characterization.REFERENCE_KEYS
    fraction = 1/(3 if reference_run else 2)

    def simulate(model, project, bench_id, index):
        target = directory/model
        target.mkdir(parents=True, exist_ok=True)
        return run_ngspice(project, bench_id, analysis_settings(key), job['executable'], target,
                           lambda done,message: progress((index+done)*fraction, model.title()+ ' · '+message))

    nominal = simulate('schematic', project, fixture['id'], 0)
    if key == 'dff-aperture':
        sweep_cell, sweep_fixture = context(loaded,key)
        characterization.add_sweep(sweep_cell,sweep_fixture)
        validate(loaded)
    result = simulate('layout', loaded, fixture['id'], 1)
    reference = None
    if reference_run:
        starter, reference_fixture = reference_layout(key)
        baseline = simulate('reference', starter, reference_fixture, 2)
        reference = characterization.observed(baseline,key)
    sweep_rows = characterization.sweep(result) if key == 'dff-aperture' else None
    result.update(settings=job['settings'], design_hash=design_digest(project),
                  student_cell_layout=dict(
                      schematic={name:nominal[name] for name in ('x','traces','x_label','settings')},
                      targets=measure(result,cell,geometry,course()[key],reference,sweep_rows),
                      capacitors=caps, artifacts={name:file_digest(directory/name) for name in artifacts(key)}))
    if sweep_rows:
        bench_nodes = {'d','clk','out','sweep_clk'}
        for _,_,tag in characterization.sweep_cases():
            bench_nodes.update(('d_'+tag,'q_'+tag))
        result['traces'] = {k:v for k,v in result['traces'].items() if k in bench_nodes}
        result['currents'] = {}
        result['student_cell_layout']['sweep'] = sweep_rows
    result['warnings'].append('Layout metal load uses the lesson’s lumped ground-capacitance estimate.')
    return result


def artifacts(key):
    if key in characterization.REFERENCE_KEYS:
        return (*ARTIFACTS, 'reference/input.cir', 'reference/result.raw', 'reference/engine.log')
    return ARTIFACTS


def reference_layout(key):
    from .student_cell_layout import close_gap, estimate
    project = create(key)
    cell, fixture = context(project,key)
    build_layout(project,key)
    for net, coordinates in cell['student_cell_layout']['breaks'].items():
        close_gap(project,cell,net,**coordinates)
    return estimate(project,cell)[0], fixture['id']


def validate_result(result, job, directory):
    key = job['settings'].get('cell')
    record = result.get('student_cell_layout', {})
    if key not in course() or result['settings'] != job['settings'] or job.get('student_lesson') != 'sc-'+key:
        raise ValueError('The captured layout experiment does not match this lesson.')
    try:
        hashes = {name:file_digest(directory/name) for name in artifacts(key)}
    except OSError as exc:
        raise ValueError('A captured standard-cell simulation artifact is missing.') from exc
    if record.get('artifacts') != hashes:
        raise ValueError('A captured standard-cell simulation artifact has changed.')
    if not record.get('capacitors'):
        raise ValueError('The layout-loaded simulation is missing its metal capacitance estimate.')
    readings(record.get('schematic', {}), key)
    readings(result, key)
    if course()[key].get('specs'):
        from .student_cell_layout import check_routing
        from .student_cell_specs import measure
        project = job['project']
        cell, _ = context(project,key)
        baseline = characterization.reference_from_raw(directory/'reference/result.raw',key) if key in characterization.REFERENCE_KEYS else None
        sweep_rows = characterization.sweep(result) if key == 'dff-aperture' else None
        if record.get('sweep') != sweep_rows:
            raise ValueError('The timing sweep readings do not match the captured waveforms.')
        if record.get('targets') != measure(result,cell,check_routing(project,cell),course()[key],baseline,sweep_rows):
            raise ValueError('The target readings do not match the captured layout and waveforms.')


def check(project, lesson, step, rows):
    from .student_hub import current_result
    from .student_cell_layout import check_placement, check_routing
    key = lesson['standard_cell']
    cell, _ = context(project, key)
    if key == row_lab.KEY:
        return row_lab.check(project,cell)
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
    drawn = read_samples(result,key)
    schematic = read_samples(layout['schematic'],key)
    targets = layout.get('targets', [])
    for row in targets:
        if not row['passed']:
            value = 'missing transition' if row['value'] is None else f'{row["value"]:.3g} {row["unit"]}'
            limit = f'≥ {row["minimum"]:g}' if 'minimum' in row else f'≤ {row["maximum"]:g}'
            raise ValueError(f'{row["metric"]} measured {value}. Target {limit} {row["unit"]}.')
    if layout.get('sweep'):
        evidence['timing_sweep'] = layout['sweep']
    return dict(**evidence, **geometry, logic_samples=drawn, schematic_samples=schematic,
                capacitance_estimate=layout['capacitors'], targets=targets)
