"""Device-level GF180 bandgap projects and saved, repeatable bench conditions."""

import json
import math
from pathlib import Path

from .catalog import create_device, link_technology
from .components import configure_component
from .getting_started import resource_root
from .model import atomic_write, clone, design_digest, example, file_digest, flatten, load_project, scalar, uid, validate
from .student_analog import _bench, _cell, _element, _get_bench, _latest, _named
from .student_bandgap import NAMES

SUPPLY = '3.3'
FAST = '100n'
SLOW = '100u'
PROCESS_CORNERS = ('nominal','ss','ff')
STARTUP_TEMPERATURES = (-40,27,125)
ACCURACY_TEMPERATURES = (-40,0,27,60,85,125)


def _example(name):
    return load_project(resource_root() / 'examples/gf180-banba' / name)


def _technology():
    root = resource_root() / 'icstudio/assets/pdks/gf180mcuD'
    manifest = json.loads((root / 'package.json').read_text(encoding='utf-8'))
    return {**manifest['technology'], 'package_root': str(root),
            'package_lock': {key: manifest[key] for key in ('id', 'revision', 'files')}}


def part(project, model, name, nets, **dimensions):
    item = create_device(project['pdk'], 'symbols/' + model + '.sym', name, 0, 0)
    if item['kind'] in ('NMOS', 'PMOS'):
        item['params'].update(w=dimensions.pop('w'), l=dimensions.pop('l'))
    item['model_params'].update(dimensions)
    item['nets'] = nets
    item['symbol']['primitives'] = [shape for shape in item['symbol']['primitives'] if shape['kind'] != 'text']
    return item


def _r(p, name, positive, negative, length):
    return part(p, 'ppolyf_u_1k', name, dict(p=positive, m=negative, b='VSS'), w='1u', l=length)


def _q(p, name, collector, base, emitter, polarity='n'):
    nets = dict(c=collector, b=base, e=emitter)
    if polarity == 'n':
        nets['s'] = 'VSS'
    return part(p, ('npn' if polarity == 'n' else 'pnp') + '_05p00x05p00', name, nets, m='1')


def _pm(p, name, drain, gate, w='8u', l='4u'):
    return part(p, 'pfet_03v3', name, dict(d=drain, g=gate, s='VDD', b='VDD'), w=w, l=l)


def _cap(p, name, positive, negative, side):
    return part(p, 'cap_mim_analog', name, dict(g=positive, b=negative), w=side, l=side)


def _widlar(p):
    return [
        _r(p, 'RFEED', 'VDD', 'VREF', '22u'),
        _r(p, 'R1', 'VREF', 'BASE12', '9u'),
        _r(p, 'R2', 'VREF', 'BASE3', '100u'),
        _r(p, 'R3', 'EMIT2', 'VSS', '9u'),
        _q(p, 'Q1', 'BASE12', 'BASE12', 'VSS'),
        _q(p, 'Q2', 'BASE3', 'BASE12', 'EMIT2'),
        _q(p, 'Q3', 'VREF', 'BASE3', 'VSS'),
    ]


def _brokaw(p):
    return [
        _pm(p, 'MSENSE1', 'COL1', 'COL1'), _pm(p, 'MSENSE2', 'COL2', 'COL1'),
        _pm(p, 'MDRIVE', 'VREF', 'COL2', '2u', '4u'),
        _q(p, 'Q1', 'COL1', 'VREF', 'EMIT1'),
        *[_q(p, f'Q2_{n}', 'COL2', 'VREF', 'EMIT2') for n in range(1, 9)],
        _r(p, 'R1', 'EMIT1', 'VSS', '46u'),
        _r(p, 'R2', 'EMIT2', 'EMIT1', '10u'),
        _r(p, 'RSTART', 'VDD', 'VREF', '600u'),
        _r(p, 'RSINK', 'VREF', 'VSS', '130u'),
        _cap(p, 'CSTAB', 'VREF', 'COL2', '15u'),
        _cap(p, 'COUT', 'VREF', 'VSS', '90u'),
        *[_cap(p, f'COUT_{i}', 'VREF', 'VSS', '96u') for i in range(1,3)],
    ]


def _kuijk(p):
    # Use the same transistor error amplifier as the Banba reference. Here
    # its actuator sources VREF directly and both diode branches return to it.
    source = _example('pass2/banba.icproj')
    ota = next(c for c in source['cells'] if c['name'] == 'error_amplifier')
    amp = flatten(source, ota['id'])
    mapping = dict(VA='SENSE1', VB='SENSE2', OUT='GATE', VDD='VDD', VSS='VSS')
    for item in amp:
        fresh = create_device(p['pdk'], item['model_ref']['device'], item['name'], 0, 0)
        item.update(id=uid(), name='AMP_' + item['name'],
                    model_ref=fresh['model_ref'],
                    nets={pin: mapping.get(net, 'AMP_' + net) for pin, net in item['nets'].items()})
        item.pop('net_labels', None)
        if item['name']=='AMP_CMILLER':
            item['model_params'].update(w='44.72u',l='44.72u')
    return [
        _pm(p, 'MDRIVE', 'VREF', 'GATE', '3u', '4u'),
        _r(p, 'R1', 'VREF', 'SENSE1', '100u'),
        _r(p, 'R2', 'VREF', 'SENSE2', '95u'),
        _r(p, 'R3', 'SENSE2', 'EMIT2', '10u'),
        _r(p, 'RSTART', 'VDD', 'VREF', '350u'),
        _q(p, 'Q1', 'VSS', 'VSS', 'SENSE1', 'p'),
        *[_q(p, f'Q2_{n}', 'VSS', 'VSS', 'EMIT2', 'p') for n in range(1, 9)],
        _cap(p, 'COUT', 'VREF', 'VSS', '80u'),
        *[_cap(p, f'CTRACK_{i}', 'VDD', 'GATE', '96u') for i in range(1,3)],
        *[_cap(p, f'COUT_{i}', 'VREF', 'VSS', '96u') for i in range(1,4)],
        *amp,
    ]


def _banba(p):
    from .student_bandgap_layout import topology_digest
    source = _example('layout/banba-layout.icproj')
    core = clone(next(c for c in source['cells'] if c['name'] == 'banba_layout'))
    # Segment dimensions and layout terminals belong to the same schematic.
    p['pdk'] = source['pdk']
    core['student_layout_digest'] = topology_digest(core)
    return core


def _segments(part):
    if part['model_ref']['device'] != 'symbols/ppolyf_u_1k.sym':
        return [part]
    length = round(scalar(part['model_params']['l'])*2e8)
    count = math.ceil(length/20000)
    if count<=1:
        return [part]
    name = part['name']
    step, remainder = divmod(length,count)
    result = []
    for i in range(count):
        segment = clone(part)
        segment['id'] = uid()
        segment['name'] = f'{name}_{i+1}'
        segment['net_labels'] = {}
        segment['model_params']['l'] = f'{(step+(i<remainder))*.005:g}u'
        if i:
            segment['nets']['p'] = f'{name}_series_{i}'
        if i+1<count:
            segment['nets']['m'] = f'{name}_series_{i+1}'
        result.append(segment)
    return result


def limits(kind):
    if kind == 'widlar':
        return dict(target=1.42, minimum=1.29, maximum=1.55, peak=1.62, current=180e-6,
                    temperature_span=.160, max_shift=.025, ripple=.004)
    if kind == 'banba':
        return dict(target=.6, minimum=.57, maximum=.63, peak=.75, current=80e-6,
                    temperature_span=.012, max_shift=.012, ripple=.002)
    return dict(target=1.2, minimum=1.14, maximum=1.26, peak=1.8 if kind=='kuijk' else 1.4, current=180e-6,
                temperature_span=.030, max_shift=.025, ripple=.004)


def _install_bench(p, core, name, ramp=None):
    criteria = limits(p['student_bandgap_lab']['topology'])
    supply = _element('V', 'VDD', SUPPLY, 'vdd', '0')
    load = _element('C', 'CL', '5p', 'vref', '0')
    settings = dict(type='op', corner='nominal', temperature=27)
    measures = [
        dict(name='reference_voltage', node='vref', kind='voltage', min=criteria['minimum'], max=criteria['maximum']),
        dict(name='supply_current', source='VDD', kind='current', min=-criteria['current'], max=0),
    ]
    specs = [dict(name='Supply current', expression='-final(I("VDD"))', unit='A', max=criteria['current'])]
    if ramp:
        stop = '500u'
        settings.update(type='tran', stop=stop, step='250n',
                        diagnostic=dict(kind='startup', source='VDD', output='vref',
                                        initial_node='vref', initial_voltage='0', ramp=ramp, supply=SUPPLY,
                                        stop=stop, minimum=criteria['minimum'], maximum=criteria['maximum'],
                                        tail_fraction=.2))
        measures.append(dict(name='settled_by', kind='startup_settling', max='350u'))
        specs.extend([
            dict(name='Startup peak', expression='max(V("vref"))', unit='V', max=criteria['peak']),
            dict(name='Final ripple', expression='max(clip(V("vref"),.0004,.000499))-min(clip(V("vref"),.0004,.000499))',
                 unit='V', max=criteria['ripple']),
        ])
    bench = _bench(p, name, core, dict(VDD='vdd', VSS='0', VREF='vref'), [supply, load], settings, specs)
    bench['probes'] = ['vdd', 'vref']
    bench['measurements'] = measures
    return bench


def project(kind):
    p = example('empty')
    p.update(name='Student · ' + NAMES[kind] + ' transistor bandgap', cells=[], testbenches=[],
             student_bandgap_lab=dict(topology=kind))
    link_technology(p, _technology())
    p['analysis'].update(type='op', corner='nominal', temperature=27)
    if kind == 'banba':
        core = _banba(p)
    else:
        build = {'widlar': _widlar, 'brokaw': _brokaw, 'kuijk': _kuijk}[kind]
        parts = [section for part in build(p) for section in _segments(part)]
        for index, item in enumerate(parts):
            item.update(x=160+index%5*300, y=180+index//5*260)
        core = dict(id=uid(), name=kind+'_core', ports=['VDD', 'VSS', 'VREF'], devices=parts, shapes=[])
    p['cells'].append(core)
    configure_component(p, core['id'], core['name'], core['ports'], {})
    dc = _install_bench(p, core, 'bandgap_accuracy')
    _install_bench(p, core, 'bandgap_fast_startup', FAST)
    _install_bench(p, core, 'bandgap_slow_startup', SLOW)
    p['top'] = dc['bench_cell']
    return validate(p)


def core_cell(p):
    return _cell(p, _get_bench(p, 'bandgap_accuracy')['dut_cell'])


STAGES = {'accuracy': 'bandgap_accuracy', 'startup': 'bandgap_fast_startup', 'post-layout': 'bandgap_accuracy'}
BENCHES = ('bandgap_fast_startup', 'bandgap_slow_startup')


def focus(p, step):
    if step in ('accuracy','startup'):
        return _get_bench(p, STAGES[step])['bench_cell']
    return core_cell(p)['id']


def verify_fixture(p):
    criteria = limits(p['student_bandgap_lab']['topology'])
    for name in ('bandgap_accuracy', *BENCHES):
        bench = _get_bench(p,name)
        cell = _cell(p,bench['bench_cell'])
        load = _named(cell,'CL')
        supply = _named(cell,'VDD')
        dut = _named(cell,'XDUT')
        if (len(cell['devices'])!=3 or bench.get('initial_conditions')
                or dut['nets']!={'VDD':'vdd','VSS':'0','VREF':'vref'} or dut['cell']!=core_cell(p)['id']
                or load['kind']!='C' or scalar(load['value'])!=scalar('5p')
                or set(load['nets'].values())!={'vref','0'}
                or supply['kind']!='V' or supply['source']['type']!='dc'
                or supply['nets']!={'p':'vdd','n':'0'} or scalar(supply['value'])!=scalar(SUPPLY)
                or not {'vref','vdd'}<=set(bench['probes'])):
            raise ValueError('Restore the saved 3.3 V source, 5 pF load, probes, and DUT connections.')
        if bench.get('implementation_view'):
            raise ValueError('Clear the selected implementation in the saved testbench. The lab captures its own layout.')
        analysis = bench['analysis']
        expected = ('op',None) if name=='bandgap_accuracy' else ('tran',FAST if name==BENCHES[0] else SLOW)
        diagnostic = analysis.get('diagnostic') or {}
        if analysis['type']!=expected[0] or (expected[1] and (
                diagnostic.get('kind')!='startup' or diagnostic.get('source')!='VDD' or diagnostic.get('output')!='vref'
                or diagnostic.get('initial_node')!='vref' or scalar(diagnostic.get('initial_voltage',1))!=0
                or diagnostic.get('supply_from_source',True) is not True
                or scalar(diagnostic.get('ramp',0))!=scalar(expected[1])
                or scalar(diagnostic.get('minimum',0))!=criteria['minimum']
                or scalar(diagnostic.get('maximum',0))!=criteria['maximum']
                or scalar(diagnostic.get('tail_fraction',.2))!=.2
                or scalar(analysis['stop'])!=scalar('500u'))):
            raise ValueError('Restore the saved DC or zero-start supply ramp before running.')


def prepare(p, step, tools):
    from .run_environment import stamp
    from .spice_program import find_ngspice
    from .student_bandgap_layout import check as check_layout

    verify_fixture(p)
    if step not in STAGES:
        raise ValueError('Select a measured bandgap checkpoint.')
    exe = find_ngspice(tools.get('ngspice',''))
    if not exe or not Path(exe).is_file():
        raise ValueError('Choose ngspice in Engine setup to run GF180 process models.')
    bench = _get_bench(p,STAGES[step])
    settings = dict(type='student_bandgap_lab', testbench=bench['id'], stage=step)
    if step=='post-layout':
        from .student_bandgap_pex import magic_tool
        check_layout(p)
        settings['tools'] = magic_tool(tools.get('magic'))
    job = dict(project=clone(p), cell=bench['bench_cell'], settings=settings, engine='ngspice',
               executable=str(Path(exe).resolve()), student_analog=dict(project='bandgap',stage=step,bench=bench['name']))
    job['environment'] = stamp(job)
    return [job]


def _cases(kind, step):
    accuracy = [(STAGES['accuracy'],'nominal',temp,3.3) for temp in ACCURACY_TEMPERATURES]
    low, high = (3.2,3.4) if kind=='widlar' else (3.0,3.6)
    representative = [('ss',-40,low),('nominal',27,3.3),('ff',125,high)]
    if step=='accuracy':
        return accuracy
    if step=='post-layout':
        return [*accuracy,*[(bench,*case) for bench in BENCHES for case in representative]]
    corners = [(corner,temp,3.3) for corner in PROCESS_CORNERS for temp in STARTUP_TEMPERATURES]
    return [(bench,*case) for bench in BENCHES for case in [*corners,representative[0],representative[2]]]


def _metrics(wave, limits, ramp):
    x = wave['x']
    v = wave['traces']['vref']
    current = -wave['currents']['vdd'][-1]
    errors = []
    values = dict(voltage_V=v[-1], current_A=current)
    if not limits['minimum']<=v[-1]<=limits['maximum']:
        errors.append('Final voltage')
    if not 0<current<=limits['current']:
        errors.append('Supply current')
    if ramp:
        tail = [sample for time,sample in zip(x,v) if time>=.0004]
        if not tail or x[-1]<.000499:
            raise ValueError('The transient did not finish the full 500 µs observation.')
        startup = wave['diagnostics']
        peak, ripple, settled = max(v), max(tail)-min(tail), startup.get('settled_by_s')
        values.update(peak_V=peak, ripple_V=ripple, settled_s=settled)
        if not startup.get('passed') or settled is None or not 0<=settled<=.00035:
            errors.append('Settling by 350 µs')
        if peak>limits['peak']:
            errors.append('Startup peak')
        if ripple>limits['ripple']:
            errors.append('Final ripple')
    return values, errors


def run_job(p, job, directory, progress):
    from .student_bandgap_pex import extract
    from .testbenches import simulate

    verify_fixture(p)
    kind = p['student_bandgap_lab']['topology']
    step = job['settings']['stage']
    criteria = limits(kind)
    cases = _cases(kind,step)
    directory = Path(directory).resolve()
    result = dict(project_id=p['id'], revision=p['revision'], cell_id=job['cell'],
                  design_hash=design_digest(p), settings=job['settings'],
                  engine='GF180 transistor-level bandgap lab', evidence_directory=str(directory),
                  requirements=criteria, x=[], traces={}, phase={}, operating_point={}, bandgap_rows=[])
    path, ports = None, None
    if step=='post-layout':
        progress(.01,'Extracting capacitance from the current GF180 layout')
        tools = job['settings']['tools']
        if file_digest(tools['magic']) != tools['magic_sha256']:
            raise ValueError('Magic changed after the job was queued. Requeue the comparison.')
        path,ports,result['extraction'] = extract(p,core_cell(p),tools['magic'],
                                                   directory/'extraction',tools.get('runtime'))
    for index,(name,corner,temp,supply) in enumerate(cases):
        progress((index+.05)/len(cases), f'{name} · {corner} · {temp} °C · {supply:g} V')
        sample = clone(p)
        bench = _get_bench(sample,name)
        bench['analysis'].update(corner=corner,temperature=temp)
        _named(_cell(sample,bench['bench_cell']),'VDD')['value'] = str(supply)
        folder = directory/f'case-{index+1:03}'
        row = dict(bench=name, corner=corner, temperature=temp, supply_V=supply, status='failed', errors=[])
        result['bandgap_rows'].append(row)
        try:
            for stage in ('schematic','extracted') if path else ('schematic',):
                work = folder/stage
                alternate = (path,ports) if stage=='extracted' else (None,None)
                wave = simulate(sample,bench,job['executable'],work,*alternate)
                values, errors = _metrics(wave,criteria,name in BENCHES)
                evidence = work/'result.json'
                row[stage] = dict(values=values, file=evidence.relative_to(directory).as_posix(),
                                  sha256=file_digest(evidence))
                row['errors'].extend(f'{stage}: {failure}' for failure in errors)
            if path:
                delta = row['extracted']['values']['voltage_V']-row['schematic']['values']['voltage_V']
                row['delta_V'] = delta
                if abs(delta)>criteria['max_shift']:
                    row['errors'].append('Extracted final voltage shifted beyond the limit')
            if not row['errors']:
                row['status'] = 'passed'
        except InterruptedError:
            raise
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            row['errors'].append(str(error))
    if step in ('accuracy','post-layout'):
        for stage in ('schematic','extracted') if path else ('schematic',):
            dc = [row for row in result['bandgap_rows'] if row['bench']==STAGES['accuracy'] and stage in row]
            if len(dc)!=len(ACCURACY_TEMPERATURES):
                continue
            voltages = [row[stage]['values']['voltage_V'] for row in dc]
            result[stage+'_temperature_span_V'] = max(voltages)-min(voltages)
    progress(1,'Bandgap measurements ready')
    return result


def read_wave(result, row, stage):
    entry = row[stage]
    base = Path(result['evidence_directory']).resolve()
    path = (base/entry['file']).resolve()
    if not path.is_relative_to(base) or not path.is_file() or file_digest(path)!=entry['sha256']:
        raise ValueError('Bandgap waveform evidence is missing or changed.')
    wave = json.loads(path.read_text(encoding='utf-8'))
    if wave['project_id']!=result['project_id']:
        raise ValueError('The waveform belongs to a different project.')
    return wave


def check(p, step, rows):
    from .student_bandgap_layout import check as check_layout

    if step=='layout':
        return check_layout(p)
    verify_fixture(p)
    if step=='post-layout':
        check_layout(p)
    _, result, evidence = _latest(p,'bandgap',step,STAGES[step],rows)
    criteria = limits(p['student_bandgap_lab']['topology'])
    cases = result['bandgap_rows']
    if any(row['status']!='passed' for row in cases):
        raise ValueError('Open Results and revise the failing cases. '+next(
            ', '.join(row['errors']) for row in cases if row['status']!='passed'))
    labels = [(row['bench'],row['corner'],row['temperature'],row['supply_V']) for row in cases]
    if labels!=_cases(p['student_bandgap_lab']['topology'],step):
        raise ValueError('Complete the entire saved bandgap sweep.')
    for stage in ('schematic','extracted') if step=='post-layout' else ('schematic',):
        if step!='startup' and result[stage+'_temperature_span_V']>criteria['temperature_span']:
            raise ValueError('Trim the resistor ratio to reduce temperature drift. Open Results for measured voltages.')
        for row in cases:
            read_wave(result,row,stage)
    return dict(bandgap_runs=dict(cases=len(cases), stage=step,
                                 temperature_span_V=result.get('schematic_temperature_span_V')),
                analog_runs=[evidence])
