"""Paired native measurement workflows for three Student Hub bench projects."""

import json
import math
import re
from functools import lru_cache
from pathlib import Path

from .model import clone, device, file_digest, scalar, uid, validate
from . import testbenches

STARTER = 'testbench-project-'
PATH = dict(id='testbenches', title='Testbenches', subtitle='Build and measure the same circuit with a saved testbench or a SPICE program.')
WORKFLOWS = {'graphical': 'Graphical testbench', 'spice': 'SPICE program'}
ARTIFACTS = {'graphical': ('testbench.cir', 'deck.raw', 'engine.log'),
             'spice': ('input.cir', 'waveforms/case1.raw', 'engine.log')}
FIELDS = {'op': (), 'dc': ('source','dc_start','dc_stop','dc_step'), 'ac': ('points','start','end'), 'tran': ('step','stop')}


@lru_cache(maxsize=1)
def course():
    from .getting_started import resource_root
    path = resource_root()/'examples/student-hub/testbench-course.json'
    return {item['id']: item for item in json.loads(path.read_text(encoding='utf-8'))}


def analyses(unit):
    expected = unit['analysis']
    kind = expected['type']
    args = [str(expected[key]) for key in FIELDS[kind]]
    return [kind, *(['dec'] if kind=='ac' else []), *args]


def program(unit):
    kind = unit['analysis']['type']
    line = ' '.join(analyses(unit))
    if kind=='op':
        return line+'\nlet lesson_value = v(out)\nprint lesson_value'
    if kind=='ac':
        return line+'\nlet lesson_mag = mag(v(out))\nmeas ac lesson_value FIND lesson_mag AT='+unit['at']
    return line+'\nmeas '+kind+' lesson_value FIND v(out) AT='+unit['at']


def target(unit):
    when = dict(op='at the operating point', dc=f'at input {unit.get("at")} V',
                ac=f'at {unit.get("at")} Hz', tran=f'at {unit.get("at")} s')[unit['analysis']['type']]
    low, high = unit['limits']
    return f'Measure out {when}. The target range is {low:g} to {high:g} V.'


def lessons():
    result = []
    for key, unit in course().items():
        starter = STARTER+unit['project']
        result.append(dict(id=key, title=unit['title'], path=PATH['id'], topic=unit['topic'], starter=starter,
            bench_project=unit['project'], workspace=starter, requires=unit['requires'], minutes=25,
            summary=unit['concept'], skills=['testbench creation','ngspice',unit['analysis']['type'],unit['topic']],
            doc='STUDENT_TESTBENCHES.md', steps=[
                dict(id='predict', kind='quiz', title='Predict the measurement', instructions=unit['question'],
                     options=unit['options'], answer=unit['answer'], explanation=unit['explanation']),
                dict(id='measure', kind='check', title='Create and verify the bench', instructions=target(unit), rule={'type':'bench_lesson'}),
                dict(id='reflect', kind='reflection', title='Record your reasoning', instructions=unit['reflection'])]))
    return result


def teaching(key):
    unit = course()[key]
    return dict(concept=unit['concept'], worked_example=target(unit),
                try_next='Run the same fixture using the other testbench workflow and compare the captured readings.',
                interview='Explain what you drew in the fixture, what you configured in the analysis, and how the saved measurement checks the requirement.',
                artifact='Keep the schematic, saved measurement and result. Record the workflow and the conditions you used.')


def hints(key):
    unit = course()[key]
    return {'predict': [('What physical relationship should I use?', unit['concept']),
                        ('What should I look for on the schematic?', unit['work']),
                        ('Which reading will confirm the prediction?', target(unit)),
                        ('How can I check this with a simulation?', f'Build the {unit["analysis"]["type"]} analysis in either workflow and inspect out before recording your prediction.')]}


def practice(key):
    unit = course()[key]
    kind = unit['analysis']['type']
    labels = {'source':'DC source name', 'dc_start':'DC start', 'dc_stop':'DC stop',
              'dc_step':'DC step', 'start':'Frequency start (Hz)', 'end':'Frequency end (Hz)',
              'points':'Frequency points / decade', 'step':'Transient step', 'stop':'Transient stop'}
    settings = ', '.join(f'{labels[field]} = {unit["analysis"][field]}' for field in FIELDS[kind])
    at = f' Set At to {unit["at"]}.' if 'at' in unit else ' Leave At blank.'
    low, high = unit['limits']
    measure = (f'Open Measurements and choose Add measurement. Set Measure to voltage and Output net to out.{at} '
               f'Enter Minimum {low:g} and Maximum {high:g}. Leave Reference net, Start and Stop blank.')
    setup = f'Use analysis {kind} at nominal model corner and 27 °C.'
    if settings:
        setup += f' Set {settings}.'
    common = 'Choose Run lesson. When the run finishes, open Results, review the measurement and choose Check this step.'
    graph = ['Choose Open workspace. '+unit['work'], 'Choose Edit testbench and open Analysis and fixture. '+setup,
             'In Probes and startup, check out and leave Initial voltage empty.', measure, 'Choose Save.', common]
    text = ['Choose Open workspace. '+unit['work'],
            'Choose Edit SPICE program. Enter the ngspice commands shown to configure the analysis and capture lesson_value.',
            'Choose Save.', common]
    goal = ' '.join((unit['work'], setup, target(unit)))
    return dict(tasks={'measure': [goal, graph, teaching(key)['worked_example']]}, questions={},
                bench_workflows={'measure': {'graphical':graph,'spice':text,'program':program(unit)}})


def _named(cell, name):
    return next(d for d in cell['devices'] if d['name']==name)


def _pulse(source, low, high, delay, period):
    source['source'].update(type='pulse', low=low, high=high, delay=delay, period=period, duty='.8', ac='0')


def _divider():
    from .model import example
    p = example('rc')
    core = p['cells'][0]
    core.update(name='resistor_divider', ports=['IN','OUT','GND'], devices=[
        device('R','R1',180,180,value='1k',nets={'p':'IN','n':'OUT'}),
        device('R','R2',180,330,value='2k',nets={'p':'OUT','n':'GND'})])
    for key in ('bias','sweep','transient'):
        source = device('V','VIN',110,160,value='1',nets={'p':'vin','n':'0'})
        parts = [source, device('X','XDUT',360,160,cell=core['id'],nets={'IN':'vin','OUT':'out','GND':'0'})]
        if key=='transient':
            _pulse(source,'0','1','2u','30u')
            parts.append(device('C','CLOAD',580,230,value='2n',nets={'p':'out','n':'0'}))
        p['cells'].append(dict(id=uid(), name='divider_'+key+'_fixture', ports=[], devices=parts, shapes=[]))
    return p


def _analog(kind):
    from .student_analog import project as design_project
    p = design_project(kind)
    by_name = {c['name']:c for c in p['cells']}
    old_benches = [t for t in p['testbenches'] if t['name'] in ('opamp_op','opamp_ac','tia_ac','tia_step')]
    if kind=='tia':
        extra = clone(by_name['tia_step_fixture'])
        extra.update(id=uid(),name='tia_bias_fixture')
        for part in extra['devices']:part['id'] = uid()
        photo = _named(extra,'IPHOTO')
        photo['value'] = '.5u'
        photo['source'].update(type='dc',ac='0')
    else:
        extra = clone(by_name['opamp_op_fixture'])
        extra.update(id=uid(),name='opamp_step_fixture')
        for part in extra['devices']:part['id'] = uid()
        _pulse(_named(extra,'VIN'),'.85','.95','5u','40u')
    keep = {t['dut_cell'] for t in old_benches} | {t['bench_cell'] for t in old_benches if t['name'].startswith(kind)}
    p['cells'] = [c for c in p['cells'] if c['id'] in keep] + [extra]
    return p


def create(kind):
    p = _divider() if kind=='divider' else _analog(kind)
    names = {'tb-opamp-bias':'opamp_op_fixture'}
    fixtures = {key:next(c['id'] for c in p['cells'] if c['name']==names.get(key,key.removeprefix('tb-').replace('-','_')+'_fixture'))
                for key,unit in course().items() if unit['project']==kind}
    p['top'] = next(iter(fixtures.values()))
    p['testbenches'] = []
    p.pop('test_plans',None)
    p['student_bench'] = dict(project=kind, fixtures=fixtures, programs={})
    p['name'] = 'Student bench · '+next(item['topic'] for item in course().values() if item['project']==kind)
    return validate(p)


def fixture(project, key):
    cid = project.get('student_bench',{}).get('fixtures',{}).get(key)
    if not cid or not any(c['id']==cid for c in project['cells']):
        raise ValueError('Open this testbench lesson project from Student Hub.')
    return cid


def saved_bench(project, key):
    cid = fixture(project,key)
    return next((t for t in project.get('testbenches',[]) if t['bench_cell']==cid),None)


def measurement(unit):
    low, high = unit['limits']
    out = dict(name='lesson_value',kind='voltage',node='out',min=low,max=high)
    if 'at' in unit:out['at'] = unit['at']
    return out


def read_measurement(result, unit):
    expected = dict(analysis=unit['analysis'], measurements=[measurement(unit)], probes=['out'])
    return testbenches.measure(result, expected)['measurements'][0]


def same_fields(actual, wanted):
    for key,value in wanted.items():
        found = actual.get(key)
        if found is None:
            return False
        if key in ('type','source','kind','node'):
            if str(found).casefold()!=str(value).casefold():return False
        elif not math.isclose(scalar(found),scalar(value),rel_tol=1e-10):return False
    return True


def validate_bench(bench, unit):
    if not bench:
        raise ValueError('Choose Edit testbench, configure the analysis and save it first.')
    if (bench.get('implementation_view') or bench.get('initial_conditions') or bench['analysis'].get('uic')
            or bench['analysis'].get('dc_startup') or bench['analysis'].get('diagnostic')
            or not same_fields(bench['analysis'], {**unit['analysis'],'temperature':27})
            or bench['analysis'].get('corner','nominal')!='nominal'):
        raise ValueError('Use the specified schematic analysis at nominal corner and 27 °C.')
    target_fields = {k:v for k,v in measurement(unit).items() if k!='name'}
    matching = [m for m in bench.get('measurements',[]) if not any(m.get(field) for field in ('reference','start','stop'))
                and same_fields(m,target_fields)]
    if 'out' not in bench['probes'] or not matching:
        raise ValueError('Save out as a probe and a voltage measurement with the specified sample and limits.')


def validate_program(text, unit):
    lines = [' '.join(line.casefold().split()) for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    expected = program(unit).casefold().splitlines()
    if len(lines)!=len(expected):
        raise ValueError('Enter one native analysis and the lesson_value measurement in the SPICE program.')
    actual, wanted = lines[0].split(), expected[0].split()
    if len(actual)!=len(wanted) or actual[0]!=wanted[0]:
        raise ValueError('Use the analysis command and settings for this checkpoint.')
    for first, second in zip(actual[1:],wanted[1:]):
        if first!=second and (second in ('dec','vin') or not math.isclose(scalar(first),scalar(second),rel_tol=1e-10)):
            raise ValueError('Use the analysis command and settings for this checkpoint.')
    for first, second in zip(lines[1:],expected[1:]):
        a,b = first.split('at='),second.split('at=')
        if a[0].replace(' ','')!=b[0].replace(' ','') or len(a)!=len(b) or (
                len(a)==2 and not math.isclose(scalar(a[1]),scalar(b[1]),rel_tol=1e-10)):
            raise ValueError('Measure out as lesson_value at the specified point.')


def prepare(project, lesson, workflow, tools):
    from .spice_program import find_ngspice
    from .run_environment import stamp
    key = lesson['id']
    unit = course()[key]
    cid = fixture(project,key)
    if workflow=='graphical':validate_bench(saved_bench(project,key),unit)
    elif workflow=='spice':validate_program(project['student_bench']['programs'].get(key,''),unit)
    else:raise ValueError('Choose one of the testbench workflows.')
    exe = find_ngspice(tools.get('ngspice',''))
    if not exe:raise ValueError('Choose ngspice in the Student Hub Engine setup.')
    job = dict(project=clone(project),cell=cid,engine='ngspice',executable=exe,
               settings=dict(type='student_bench_lab',lesson=key,workflow=workflow),student_lesson=key,student_bench_step='measure')
    job['environment'] = stamp(job)
    return job


def run(job, directory, progress):
    from .native_analysis import circuit_text
    from .pdks import stage_model_deck
    from .spice_program import run_program
    p = job['project']
    settings = job['settings']
    key, workflow = settings['lesson'], settings['workflow']
    unit, cid = course()[key], fixture(p,key)
    if workflow not in WORKFLOWS or cid != job['cell']:
        raise ValueError('The saved run does not match this lesson fixture and workflow.')
    directory = Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    standard = testbenches.create(p,cid,'lesson_measurement')
    standard['analysis'].update(unit['analysis'])
    standard['analysis'].update(temperature=27,corner='nominal')
    standard['measurements'] = [measurement(unit)]
    if workflow=='graphical':
        bench = saved_bench(p,key)
        validate_bench(bench,unit)
        result = testbenches.simulate(p,bench,job['executable'],directory,progress=progress)
    else:
        text = p['student_bench']['programs'].get(key,'')
        validate_program(text,unit)
        def deck(project, root):
            circuit = circuit_text(testbenches.spice_testbench(project,standard,root))
            return stage_model_deck(project['pdk'], circuit+'.temp 27\n.control\n'+text+'\n.endc\n.end\n',root)
        probes = ' '.join('v('+node+')' for node in standard['probes'])
        result = run_program(p,cid,{**settings,'probes':probes,'timeout':90},job['executable'],directory,
                             progress,deck,'ngspice · lesson SPICE program',{},'analysis_cases')
        cases = result['analysis_cases']
        if len(cases)!=1 or result['program_status']!='Complete':
            raise ValueError('The program did not complete the requested analysis. See Job log.')
    row = read_measurement(result,unit)
    if workflow=='spice':
        readings = [m['value'] for m in cases[0].get('measurements',[]) if m['name'].casefold()=='lesson_value']
        if (len(readings)!=1 or 'value' not in row or not math.isclose(readings[0],row['value'],rel_tol=.002,abs_tol=.00001)):
            raise ValueError('SPICE lesson_value is missing or disagrees with the captured waveform.')
    result.update(settings=settings,plot_kind=unit['analysis']['type'],student_bench={
        'lesson':key,'workflow':workflow,'check':row,
        'artifacts':{name:file_digest(directory/name) for name in ARTIFACTS[workflow]}})
    return result


def validate_result(job, result, directory):
    settings = job['settings']
    workflow, key = settings.get('workflow'), settings.get('lesson')
    record = result.get('student_bench', {})
    if (key not in course() or workflow not in WORKFLOWS or result.get('settings') != settings
            or record.get('lesson') != key or record.get('workflow') != workflow
            or key != job.get('student_lesson') or fixture(job['project'], key) != job['cell']):
        raise ValueError('Testbench result does not match its saved lesson and workflow.')
    artifacts = record.get('artifacts', {})
    try:
        expected = {name: file_digest(directory/name) for name in ARTIFACTS[workflow]}
    except OSError as exc:
        raise ValueError('A saved testbench artifact is missing.') from exc
    if artifacts != expected:
        raise ValueError('A saved testbench artifact has changed.')
    measured = read_measurement(result, course()[key])
    if record.get('check') != measured:
        raise ValueError('The saved testbench measurement does not match the waveform.')


def check(project, lesson, rows):
    from .student_hub import current_result
    key = lesson['id']
    tagged = [row for row in rows if row['job'].get('student_lesson')==key
              and row['job'].get('settings',{}).get('type')=='student_bench_lab']
    result, evidence = current_result(project,tagged)
    captured = result['student_bench']
    measured = captured['check']
    if measured['status']!='passed':
        value = measured.get('value')
        reading = f'Measured {value:.5g} V. ' if value is not None else ''
        raise ValueError(reading+target(course()[key]))
    cell = next(c for c in project['cells'] if c['id']==fixture(project,key))
    parts = {part['name']: part for part in cell['devices']}
    if key=='tb-tia-ac' and not math.isclose(scalar(parts.get('IPHOTO', {}).get('source', {}).get('ac', '0')),1e-6):
        raise ValueError('Set the AC amplitude of IPHOTO to 1u before converting output voltage into transimpedance.')
    if key=='tb-opamp-ac':
        load = parts.get('CL', {})
        if (load.get('kind')!='C' or set(load['nets'].values())!={'out','0'}
                or not math.isclose(scalar(load['value']),1e-12)):
            raise ValueError('Connect the 1 pF load CL from out to ground in the loop fixture.')
    return dict(**evidence,bench_workflow=captured['workflow'],bench_reading=measured['value'])
