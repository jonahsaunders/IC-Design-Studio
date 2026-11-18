"""Editable SKY130 bias reference and cascode mirror with measured PVT checkpoints."""

from bisect import bisect_left
from itertools import product as combinations
from pathlib import Path

from .model import clone, example, scalar, uid, validate
from .student_analog import _bench, _cell, _element, _get_bench, _latest, _named, bundled_technology
from .testbenches import create as save_bench

NOMINAL_OUTPUT = 1.4
STUDY = dict(kind='pvt', target='VDD.value', corners=['nominal', 'ss', 'ff'],
             temperatures=[-40, 27, 85], voltages=[1.8], compare_layout=False)
RUNS = {'reference': ('simple_bias',), 'compare': ('simple_compliance', 'cascode_compliance', 'simple_bias', 'cascode_bias'),
        'corners': ('cascode_bias',)}
CURRENT_BOUNDS = (3e-6, 7e-6)


def project(technology=None):
    from .catalog import create_device, link_technology
    from .components import configure_component
    from .student_inverter import profile

    technology = technology or bundled_technology()
    if technology.get('package_lock', {}).get('id') != 'sky130A':
        raise ValueError('Choose a SKY130A technology for the bias lab.')
    key = profile(technology)['models'].get('NMOS')
    if not key:
        raise ValueError('The bias lab needs the SKY130A 1.8 V four-terminal NMOS model.')
    p = example('empty')
    p.update(name='Student · Current reference and cascode', cells=[], testbenches=[])
    link_technology(p, technology)
    p['analysis'].update(type='op', corner='nominal', temperature=27)
    base = [('MREF', 260, 560, 'bias1', 'bias1', 'VSS'),
            ('MOUT', 680, 560, 'MID', 'bias1', 'VSS')]
    for name in ('simple', 'cascode'):
        cascode = name == 'cascode'
        dut = dict(id=uid(), name=name+'_mirror', ports=['SET', 'OUT', 'VSS'], devices=[], shapes=[])
        if cascode:
            devices = [*base, ('MCREF', 260, 250, 'SET', 'SET', 'bias1'),
                       ('MCOUT', 680, 250, 'OUT', 'SET', 'MID')]
        else:
            devices = [('MREF', 260, 410, 'SET', 'SET', 'VSS'),
                       ('MOUT', 680, 410, 'OUT', 'SET', 'VSS')]
        for label, x, y, drain, gate, source in devices:
            mos = create_device(p['pdk'], key, label, x, y)
            mos['params'].update(w='10u', l='1u')
            mos['nets'] = dict(d=drain, g=gate, s=source, b='VSS')
            dut['devices'].append(mos)
        p['cells'].append(dut)
        configure_component(p, dut['id'], dut['name'], dut['ports'], {})
        current = dict(name='output_current', kind='current', source='VCLAMP')
        op = _bench(p, name+'_bias', dut, dict(SET='vset', OUT='out', VSS='0'), [
            _element('V', 'VDD', '1.8', 'vdd', '0'),
            _element('R', 'RSET', '47k' if cascode else '100k', 'vdd', 'vset'),
            _element('V', 'VCLAMP', str(NOMINAL_OUTPUT), 'out', '0'),
        ], dict(diagnostic={'kind': 'bias'}), [])
        op['measurements'] = [current, dict(name='reference_current', kind='current', source='VDD')]
        dc = save_bench(p, op['bench_cell'], name+'_compliance')
        dc.update(analysis={**dc['analysis'], 'type': 'dc', 'source': 'VCLAMP',
                            'dc_start': '.025', 'dc_stop': '1.55', 'dc_step': '.025'},
                  measurements=[clone(current)])
        p['testbenches'].append(dc)
    p['top'] = _get_bench(p, 'simple_bias')['bench_cell']
    return validate(p)


def run_names(step):
    return RUNS.get(step, ())


def focus(project, step):
    name = 'cascode_bias' if step in ('headroom', 'compare', 'corners') else 'simple_bias'
    bench = _get_bench(project, name)
    return bench['dut_cell'] if step == 'headroom' else bench['bench_cell']


def verify_fixture(project, bench):
    fixture = _cell(project, bench['bench_cell'])
    if (scalar(_named(fixture, 'VDD')['value']) != 1.8
            or scalar(_named(fixture, 'VCLAMP')['value']) != NOMINAL_OUTPUT):
        raise ValueError('Restore the 1.8 V supply and 1.4 V output clamp before running this checkpoint.')


def prepare(project, step, tools):
    from .run_environment import stamp
    from .spice_program import find_ngspice

    exe = find_ngspice(tools.get('ngspice', ''))
    if not exe or not Path(exe).is_file():
        raise ValueError('Choose ngspice in Engine setup to run SKY130 process models.')
    names = run_names(step)
    if not names:
        raise ValueError('Select a measured checkpoint before running.')
    jobs = []
    for name in names:
        bench = _get_bench(project, name)
        verify_fixture(project, bench)
        if step == 'corners':
            settings = dict(type='characterization', testbench=bench['id'], study=clone(STUDY))
        else:
            settings = dict(type='testbench', testbench=bench['id'], executable=str(Path(exe).resolve()))
        job = dict(project=clone(project), cell=bench['bench_cell'], settings=settings, engine='ngspice',
                   executable=str(Path(exe).resolve()), student_analog=dict(project='bias', stage=step, bench=name))
        job['environment'] = stamp(job)
        jobs.append(job)
    return jobs


def bias_readings(project, bench, result):
    cell = _cell(project, bench['dut_cell'])
    points = {name.casefold(): point for name, point in result.get('device_operating_point', {}).items()}
    currents = {name.casefold(): value for name, value in result.get('operating_currents', {}).items()}
    devices = ('MOUT', 'MCOUT') if bench['name']=='cascode_bias' else ('MOUT',)
    try:
        current, reference = (abs(scalar(currents[name])) for name in ('vclamp','vdd'))
        point = points['xdut/mout']
        device = _named(cell,'MOUT')
        width = scalar(device['params']['w'])*scalar(device.get('model_params',{}).get('m',1))
        margin = min(scalar(points['xdut/'+name.casefold()]['headroom']) for name in devices)
        output = scalar(result['traces']['out'][0])
        output_margin = scalar(points['xdut/'+devices[-1].casefold()]['headroom'])
        gm = abs(scalar(point['gm']))
        density = abs(scalar(point['id'])) / width
    except (KeyError, TypeError, ZeroDivisionError, ValueError) as error:
        raise ValueError('Run the operating-point bench with MOS bias diagnostics enabled.') from error
    if not min(current, reference, gm, density) > 0:
        raise ValueError('Check that the reference is powered and both mirror branches conduct.')
    return dict(output_A=current, reference_A=reference, density_uA_per_um=density,
                gm_over_id=gm/abs(scalar(point['id'])), headroom_V=margin, ratio=current/reference,
                saturation_floor_V=output-output_margin,
                width_um=width*1e6)


def compliance(result):
    try:
        xs = result['x']
        currents = {name.casefold(): values for name, values in result['currents'].items()}
        current = [abs(v) for v in currents['vclamp']]
        at_nominal = sample_linear(xs, current, NOMINAL_OUTPUT)
        delta = sample_linear(xs, current, 1.50) - sample_linear(xs, current, 1.20)
        last_outside = max((i for i,v in enumerate(current) if not .95*at_nominal <= v <= 1.05*at_nominal), default=-1)
        knee = xs[last_outside+1]
    except (KeyError, IndexError, ValueError) as error:
        raise ValueError('Run the saved clamp sweep over the full output-voltage range.') from error
    if at_nominal <= 0 or delta <= 0:
        raise ValueError('The output sweep has no valid current or local slope.')
    return dict(output_A=at_nominal, resistance_ohm=.30/delta, compliance_V=knee)


def sample_linear(xs, ys, x):
    if not xs or not xs[0] <= x <= xs[-1] or len(xs)!=len(ys):
        raise ValueError('The sweep lacks the required output voltage.')
    i=bisect_left(xs,x)
    if not i or xs[i]==x:
        return ys[i]
    ratio=(x-xs[i-1])/(xs[i]-xs[i-1])
    return ys[i-1]+ratio*(ys[i]-ys[i-1])


def check(project, step, rows):
    names = run_names(step)
    if not names:
        raise ValueError('Choose a measured bias checkpoint.')
    runs = [_latest(project, 'bias', step, name, rows) for name in names]
    if step=='reference':
        point = bias_readings(project, _get_bench(project, names[0]), runs[0][1])
        if not 4.5e-6 <= point['output_A'] <= 5.5e-6 or point['headroom_V'] < .05:
            raise ValueError('Trim RSET for 4.5–5.5 µA at the nominal clamp and keep at least 50 mV saturation margin.')
        return dict(bias_readings=point, analog_runs=[runs[0][2]])
    if step=='compare':
        simple, cascode = (compliance(run[1]) for run in runs[:2])
        for data, name, (_, result, _) in zip((simple, cascode), names[2:], runs[2:]):
            point = bias_readings(project, _get_bench(project, name), result)
            data['saturation_floor_V'] = point['saturation_floor_V']
        if any(not 4e-6 <= row['output_A'] <= 6e-6 for row in (simple, cascode)):
            raise ValueError('Trim each reference so its mirror sinks 4–6 µA at 1.4 V, then repeat both sweeps.')
        if cascode['resistance_ohm'] <= 2*simple['resistance_ohm'] or cascode['saturation_floor_V'] <= simple['saturation_floor_V']:
            raise ValueError('Check cascode connections. Look for higher output resistance and a higher estimated saturation floor.')
        return dict(bias_comparison={'simple':simple,'cascode':cascode}, analog_runs=[run[2] for run in runs])
    job, result, evidence = runs[0]
    if job['settings'].get('study') != STUDY:
        raise ValueError('Run the fixed nine-corner comparison from this lesson.')
    return dict(bias_corners=corner_readings(project, result), analog_runs=[evidence])


def corner_readings(project, result):
    from .characterization import read_case

    expected = set(combinations(STUDY['corners'], STUDY['temperatures']))
    case_rows = result.get('characterization_rows', [])
    if len(case_rows)!=len(expected) or {(row['corner'], row['temperature']) for row in case_rows}!=expected:
        raise ValueError('Complete all nine process and temperature cases.')
    bench = _get_bench(project, 'cascode_bias')
    values = []
    for index, row in enumerate(case_rows):
        point = bias_readings(project, bench, read_case(result,index))
        point.update(corner=row['corner'], temperature=row['temperature'], voltage=row['voltage'])
        point['passes'] = CURRENT_BOUNDS[0]<=point['output_A']<=CURRENT_BOUNDS[1] and point['headroom_V']>=.05
        values.append(point)
    return values
