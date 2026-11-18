"""SKY130 design projects with revision-bound circuit and physical checkpoints."""

import json
from pathlib import Path
import shutil

from .model import clone, design_digest, device, file_digest, scalar, uid, validate
from .testbenches import create as save_bench

PROJECTS = {
    'opamp': ('opamp_op', 'opamp_ac', 'opamp_noise', 'opamp_startup'),
    'tia': ('tia_ac', 'tia_step'),
}
REFERENCE = 'reference_compliance'
MIN_SATURATION_MARGIN = 0.015

TIA_GAIN = 'abs(V("out") / I("VSENSE"))'
TIA_LOW_GAIN = f'at({TIA_GAIN},100)'
TIA_SPECS = [
    dict(name='Transimpedance at 100 Hz', expression=TIA_LOW_GAIN, unit='Ohm', min='90k', max='110k'),
    dict(name='Bandwidth', expression=f'crossing({TIA_GAIN},{TIA_LOW_GAIN}/sqrt(2),-1)', unit='Hz', min='200k'),
    dict(name='Normalized peaking', expression=f'db20(max({TIA_GAIN})/{TIA_LOW_GAIN})', unit='dB', max=2),
]
STEP_SPECS = [
    dict(name='Output step', expression='at(V("out"),5e-6)-at(V("out"),30e-6)', unit='V', min='.09', max='.11'),
    dict(name='Settling after current edge', expression='settling(clip(V("out"),10.1e-6,39e-6),at(V("out"),35e-6),.02*abs(at(V("out"),5e-6)-at(V("out"),35e-6)))-at(x,10.1e-6)',
         unit='s', max='8u'),
]
REFERENCE_SPECS = [
    dict(name='Minimum reference current', expression='min(I("VCLAMP"))', unit='A', min='4u'),
    dict(name='Maximum reference current', expression='max(I("VCLAMP"))', unit='A', max='6u'),
]


def choose_technology(profiles, current):
    """Prefer the student's linked full process; preserve offline simulation."""
    from .process_adapters import capabilities

    candidates = [profile['technology'] for profile in profiles.values()
                  if profile['ready'] and profile['technology']['package_lock']['id'] == 'sky130A']
    if current.get('package_lock', {}).get('id') == 'sky130A' and capabilities(current)['external_verification']:
        return current
    if not candidates:
        raise ValueError('Register SKY130A in PDK Manager, then reload the Student Hub.')
    return max(candidates, key=lambda tech: bool(capabilities(tech)['external_verification']))


def bundled_technology():
    from .getting_started import resource_root

    root = resource_root() / 'icstudio/assets/pdks/sky130A'
    manifest = json.loads((root / 'package.json').read_text(encoding='utf-8'))
    return {**manifest['technology'], 'package_root': str(root),
            'package_lock': {key: manifest[key] for key in ('id', 'revision', 'files')}}


def _element(kind, name, value, positive, negative):
    item = device(kind, name, 0, 0, value=value, nets={'p': positive, 'n': negative})
    if kind in ('I', 'V'):
        item['source']['ac'] = '0'
    return item


def _bench(project, name, dut, ports, elements, analysis, specifications):
    instance = device('X', 'XDUT', 720, 385, cell=dut['id'], nets=ports)
    positions = {
        'VDD': (100, 105), 'VCM': (100, 320), 'IREF': (100, 530),
        'IPHOTO': (300, 495), 'VSENSE': (470, 495), 'CPD': (490, 685),
        'RF': (650, 105), 'CF': (650, 230), 'CL': (1050, 500),
        'RSET': (430, 640), 'VCLAMP': (1010, 510),
    }
    for item in elements:
        item['x'], item['y'] = positions[item['name']]
        if item['name'] in ('RF', 'CF', 'VSENSE'):
            item['rotation'] = 270
    cell = dict(id=uid(), name=name + '_fixture', ports=[], devices=[instance, *elements], shapes=[])
    project['cells'].append(cell)
    bench = save_bench(project, cell['id'], name)
    bench.update(analysis={**bench['analysis'], **analysis}, specifications=clone(specifications))
    project['testbenches'].append(bench)
    return bench


def _reference(project, core):
    """Use layout-capable SKY130 PMOS devices in a resistor-programmed mirror."""
    from .components import configure_component

    mirror = dict(id=uid(), name='resistor_current_reference', ports=['VDD', 'SET', 'OUT'], devices=[], shapes=[])
    for name, drain, x in (('MPREF', 'SET', 270), ('MPOUT', 'OUT', 690)):
        mos = clone(_named(core, 'M3'))
        mos.update(id=uid(), name=name, x=x, nets=dict(d=drain, g='SET', s='VDD', b='VDD'))
        mirror['devices'].append(mos)
    project['cells'].append(mirror)
    configure_component(project, mirror['id'], mirror['name'], mirror['ports'], {})
    return _bench(project, REFERENCE, mirror, dict(VDD='vdd', SET='iset', OUT='iref'), [
        _element('V', 'VDD', '1.8', 'vdd', '0'),
        _element('R', 'RSET', '82k', 'iset', '0'),
        _element('V', 'VCLAMP', '.65', 'iref', '0'),
    ], dict(type='dc', source='VCLAMP', dc_start='.45', dc_stop='.85', dc_step='.025'), REFERENCE_SPECS)


def _tia(project, core):
    for name in PROJECTS['tia']:
        is_ac = name == 'tia_ac'
        input_current = _element('I', 'IPHOTO', '0', '0', 'diode')
        if is_ac:
            input_current['source']['ac'] = '1u'
            settings = dict(type='ac', start='100', end='100Meg', points=60)
        else:
            input_current['source'].update(type='pulse', low='0', high='1u', delay='10u',
                                           rise='100n', fall='100n', period='100u', duty='.7')
            settings = dict(type='tran', stop='40u', step='20n')
        _bench(project, name, core, dict(INP='vcm', INN='sense', OUT='out', IBIAS='bias', VDD='vdd', VSS='0'), [
            _element('V', 'VDD', '1.8', 'vdd', '0'),
            _element('V', 'VCM', '.9', 'vcm', '0'),
            _element('I', 'IREF', '5u', 'vdd', 'bias'),
            input_current,
            _element('V', 'VSENSE', '0', 'diode', 'sense'),
            _element('C', 'CPD', '2p', 'sense', '0'),
            _element('R', 'RF', '47k' if is_ac else '100k', 'out', 'sense'),
            _element('C', 'CF', '2p', 'out', 'sense'),
            _element('C', 'CL', '1p', 'out', '0'),
        ], settings, TIA_SPECS if is_ac else STEP_SPECS)


def project(kind, technology=None):
    from .two_stage_opamp import reference

    if kind not in PROJECTS:
        raise ValueError('Unknown analog design project.')
    project, core_id, _ = reference(technology or bundled_technology())
    core = _cell(project, core_id)
    project['name'] = 'Student · ' + ('Photodiode TIA' if kind == 'tia' else 'Two-stage Miller op amp')
    if kind == 'tia':
        # Keep the unity-follower OP fixture for input-pair sizing.
        op = _get_bench(project, 'opamp_op')
        project['cells'] = [core, _cell(project, op['bench_cell'])]
        project['testbenches'] = [op]
        _tia(project, core)
        project['top'] = _get_bench(project, 'tia_ac')['bench_cell']
    else:
        # A deliberate fixture error to fix before taking measurements.
        _named(_cell(project, _get_bench(project, 'opamp_ac')['bench_cell']), 'CL')['value'] = '5p'
    _reference(project, core)
    tests = [*PROJECTS[kind], REFERENCE]
    project['test_plans'] = [dict(id=uid(), name='Student analog PVT', variables={}, compare_layout=False,
        corners=['nominal', 'ss', 'ff'], temperatures=[0, 27, 85], voltages=[1.71, 1.8, 1.89],
        entries=[dict(id='bench:'+b['id'], name=b['name'], cell=b['bench_cell'], engine='ngspice',
                      settings=dict(type='testbench', testbench=b['id']), supply='VDD.value')
                 for b in project['testbenches'] if b['name'] in tests])]
    return validate(project)


def _named(cell, name):
    matches = [item for item in cell['devices'] if item['name'] == name]
    if len(matches) != 1:
        raise ValueError('Find exactly one ' + name + ' in ' + cell['name'] + '.')
    return matches[0]


def _cell(project, cid):
    cell = next((item for item in project['cells'] if item['id'] == cid), None)
    if cell is None:
        raise ValueError('The lesson circuit or fixture is missing.')
    return cell


def _get_bench(project, name):
    bench = next((item for item in project.get('testbenches', []) if item['name'] == name), None)
    if bench is None:
        raise ValueError('Restore the saved ' + name + ' testbench before continuing.')
    return bench


def run_names(kind, step):
    return {
        'sizing': ('opamp_op',),
        'bias': (REFERENCE,),
        'schematic': PROJECTS[kind],
        'post-layout': (*PROJECTS[kind], REFERENCE),
    }.get(step, ())


def focus_cell(project, kind, step):
    bench = _get_bench(project, REFERENCE if step in ('bias', 'bias-layout') else
                       'opamp_op' if step in ('sizing', 'layout', 'post-layout') else
                       'tia_ac' if kind == 'tia' else 'opamp_ac')
    return bench['dut_cell'] if step in ('sizing', 'layout', 'bias-layout', 'post-layout') else bench['bench_cell']


def prepare(project, kind, step, tools):
    from .physical_backend import prepare as prepare_physical
    from .run_environment import stamp
    from .spice_program import find_ngspice

    if step in ('schematic', 'post-layout'):
        _fixture(project, kind)
    if step == 'post-layout':
        _layout(project, kind, 'layout')
        _layout(project, kind, 'bias-layout')
    names = run_names(kind, step)
    if not names:
        raise ValueError('Follow the instructions for this step before running a simulation.')
    jobs = []
    for name in names:
        bench = _get_bench(project, name)
        if step == 'post-layout':
            settings = dict(type='silicon', testbench=bench['id'],
                            tools={key: tools.get(key) or shutil.which(key) or ''
                                   for key in ('magic', 'netgen', 'ngspice')})
            job = dict(project=clone(project), cell=bench['dut_cell'], settings=settings, engine='physical')
            prepare_physical(job)
        else:
            exe = find_ngspice(tools.get('ngspice', ''))
            if not exe or not Path(exe).is_file():
                raise ValueError('Choose ngspice in Engine setup to run SKY130 process models.')
            settings = dict(type='testbench', testbench=bench['id'], executable=str(Path(exe).resolve()))
            job = dict(project=clone(project), cell=bench['bench_cell'], settings=settings, engine='ngspice',
                       executable=settings['executable'])
        job['student_analog'] = dict(project=kind, stage=step, bench=name)
        job['environment'] = stamp(job)
        jobs.append(job)
    return jobs


def _fixture(project, kind):
    bench = _get_bench(project, 'tia_ac' if kind == 'tia' else 'opamp_ac')
    fixture = _cell(project, bench['bench_cell'])
    load = _named(fixture, 'CL')
    if load['kind'] != 'C' or scalar(load['value']) != scalar('1p') or set(load['nets'].values()) != {'out', '0'}:
        raise ValueError('Connect CL from out to ground and set it to 1 pF in the AC testbench.')
    dut_ports = _named(fixture, 'XDUT')['nets']
    if kind == 'tia':
        pulse_fixture = _cell(project, _get_bench(project, 'tia_step')['bench_cell'])
        for pin, device_kind in (('RF', 'R'), ('CF', 'C')):
            ac, pulse = (_named(cell, pin) for cell in (fixture, pulse_fixture))
            if any(part['kind'] != device_kind or set(part['nets'].values()) != {'out', 'sense'}
                   for part in (ac, pulse)):
                raise ValueError('Wire '+pin+' between out and sense in both TIA fixtures.')
            if scalar(ac['value']) != scalar(pulse['value']):
                raise ValueError('Set '+pin+' to the same value in both TIA fixtures. Start with 100 kΩ RF and 2 pF CF.')
        if dut_ports.get('INN') != 'sense' or dut_ports.get('INP') != 'vcm':
            raise ValueError('Connect the feedback node to INN and common-mode reference to INP.')
    elif dut_ports.get('INN') != 'feedback' or dut_ports.get('INP') != 'inp':
        raise ValueError('Connect INN to the DC feedback node and INP to the injection source.')
    return dict(bench=bench['name'], load_F=scalar(load['value']))


def _layout(project, kind, step):
    from .analog_constraints import findings
    from .physical import connectivity

    cid = focus_cell(project, kind, step)
    cell = _cell(project, cid)
    if not cell.get('shapes') or not cell.get('layout_ports'):
        target = 'bias mirror' if step == 'bias-layout' else 'op-amp core'
        raise ValueError(f'Generate the {target} layout, then inspect its shapes and labelled pins.')
    if {port['name'] for port in cell['layout_ports']} != set(cell['ports']):
        raise ValueError('Provide a physical port for every core schematic pin.')
    if connectivity(project, cid)['issues'] or findings(project, cid):
        raise ValueError('Resolve linked-layout connectivity and matching findings before running process checks.')
    return dict(layout_cell=cell['name'], ports=cell['ports'], scope='linked connectivity and matching')


def _latest(project, kind, step, name, rows):
    from .job_store import read_result

    key = design_digest(project)
    tag = dict(project=kind, stage=step, bench=name)
    candidates = [row for row in rows if row.get('state') == 'Complete'
                  and row['job'].get('student_analog') == tag
                  and row['job']['project']['id'] == project['id']
                  and row.get('result', {}).get('design_hash') == key]
    if not candidates:
        raise ValueError(f'Run {name} again. Its completed result must match the current project.')
    root = Path(candidates[-1]['path'])
    inputs, outputs = root/'input.json', root/'result.json'
    job = json.loads(inputs.read_text(encoding='utf-8'))
    bench = _get_bench(project, name)
    result = read_result(outputs, project['id'])
    if (job.get('student_analog') != tag or job['settings'].get('testbench') != bench['id']
            or design_digest(job['project']) != key or result.get('design_hash') != key):
        raise ValueError('The stored result belongs to another design or testbench. Run this step again.')
    return job, result, dict(bench=name, run=str(root), input_sha256=file_digest(inputs), result_sha256=file_digest(outputs))


def _limits(name, specs, measures):
    expected = {
        'opamp_op': {'output_bias': (.85, .95), 'static_power': (0, 180e-6)},
        'opamp_ac': {'phase_margin': (45, 180), 'unity_frequency': (100e3, 50e6), 'dc_gain': (40, None)},
        'opamp_noise': {'integrated_input_noise': (0, 200e-6), 'integrated_output_noise': (0, 200e-6)},
        'opamp_startup': {'startup_settling': (0, 100e-6), 'final_output': (.85, .95)},
        'tia_ac': {row['name']: (row.get('min'), row.get('max')) for row in TIA_SPECS},
        'tia_step': {row['name']: (row.get('min'), row.get('max')) for row in STEP_SPECS},
        REFERENCE: {row['name']: (row.get('min'), row.get('max')) for row in REFERENCE_SPECS},
    }[name]
    by_name = {row['name']: row for row in [*measures, *specs]}
    values = {}
    for metric, (low, high) in expected.items():
        row = by_name.get(metric, {})
        value = row.get('value')
        if (row.get('status') not in ('PASS', 'passed') or value is None
                or low is not None and value < scalar(low) or high is not None and value > scalar(high)):
            raise ValueError(f'{name} · {metric} did not meet the project target. Open Results and inspect the measurement.')
        values[metric] = dict(value=value, unit=row.get('unit', ''))
    return values


def check(project, kind, step, rows):
    if step == 'fixture':
        return _fixture(project, kind)
    if step in ('layout', 'bias-layout'):
        return _layout(project, kind, step)
    evidence = []
    for name in run_names(kind, step):
        job, result, record = _latest(project, kind, step, name, rows)
        if step == 'post-layout':
            report = result.get('silicon_report', {})
            stages = {stage['name']: stage for stage in report.get('stages', [])}
            if report.get('testbench_id') != job['settings']['testbench'] or report.get('status') != 'passed':
                raise ValueError(f'{name} · {report.get("error") or "Inspect the physical report for the first incomplete stage."}')
            measurements = {}
            for side in ('schematic_simulation', 'post_layout_simulation'):
                data = stages.get(side, {}).get('evidence', {})
                measurements[side] = _limits(name, data.get('specifications', []), data.get('measurements', []))
            record.update(metrics=measurements, physical_status=report['status'])
        elif step == 'sizing':
            record.update(gmid=_bias_point(project, result))
        else:
            record.update(metrics=_limits(name, result.get('specifications', []),
                                          result.get('measurements', {}).get('measurements', [])))
        evidence.append(record)
    if not evidence:
        raise ValueError('Unknown analog project checkpoint.')
    return dict(analog_runs=evidence)


def _bias_point(project, result):
    bench = _get_bench(project, 'opamp_op')
    core = _cell(project, bench['dut_cell'])
    dimensions = [{key: scalar(_named(core, name)['params'][key]) for key in ('w', 'l')} for name in ('M1', 'M2')]
    if dimensions[0] != dimensions[1]:
        raise ValueError('Use matching W and L for the differential input pair M1 and M2.')
    points = {name.casefold(): values for name, values in result.get('device_operating_point', {}).items()}
    point = points.get('xdut/m2', {})
    if 'id' not in point or 'gm' not in point:
        raise ValueError('Run the saved opamp_op bias fixture and inspect the M2 operating point.')
    current, gm = abs(scalar(point['id'])), abs(scalar(point['gm']))
    efficiency = gm/current if current else 0
    margin = scalar(point.get('headroom', 0))
    if not 6 <= efficiency <= 28 or not 25e-6 <= gm <= 150e-6 or margin < MIN_SATURATION_MARGIN:
        raise ValueError('Aim for M2 gm of 25–150 µS, gm/ID of 6–28 V⁻¹, and at least 15 mV saturation margin.')
    return dict(current_A=current, gm_S=gm, gm_over_id=efficiency, margin_V=margin,
                current_per_width_A_per_m=current/dimensions[1]['w'], width_m=dimensions[1]['w'])
