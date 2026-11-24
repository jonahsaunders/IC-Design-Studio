"""Paired native measurement workflows for Student Hub bench projects."""

import json
import math
import re
from functools import lru_cache
from pathlib import Path

from .model import clone, design_digest, device, file_digest, scalar, uid, validate
from . import student_opamp_verification as verification, testbenches

STARTER = 'testbench-project-'
PATH = dict(id='testbenches', title='Testbenches', subtitle='Build and measure the same circuit with a saved testbench or a SPICE program.')
WORKFLOWS = {'graphical': 'Graphical testbench', 'spice': 'SPICE program'}
ARTIFACTS = {'graphical': ('testbench.cir', 'deck.raw', 'engine.log'),
             'spice': ('input.cir', 'waveforms/case1.raw', 'engine.log')}
FIELDS = {'op': (), 'dc': ('source','dc_start','dc_stop','dc_step'), 'ac': ('points','start','end'),
          'tran': ('step','stop'), 'noise': ('points','start','end','output','noise_source')}


@lru_cache(maxsize=1)
def course():
    from .getting_started import resource_root
    path = resource_root()/'examples/student-hub/testbench-course.json'
    return {**{item['id']: item for item in json.loads(path.read_text(encoding='utf-8'))}, **verification.units()}


def checkpoint_key(lesson, step=None):
    checkpoints = lesson.get('bench_checkpoints')
    if not checkpoints:
        return lesson['id']
    if step == 'reflect':
        return list(checkpoints.values())[-1]
    return checkpoints.get(step, next(iter(checkpoints.values())))


def workspace_key(lesson, step=None):
    key = checkpoint_key(lesson, step)
    return course()[key].get('reuse', key)


def analyses(unit):
    expected = unit['analysis']
    kind = expected['type']
    if kind == 'noise':
        return ['noise', f'v({expected["output"]})', expected['noise_source'], 'dec',
                *[str(expected[key]) for key in ('points','start','end')]]
    args = [str(expected[key]) for key in FIELDS[kind]]
    return [kind, *(['dec'] if kind=='ac' else []), *args]


def program(unit):
    kind = unit['analysis']['type']
    line = ' '.join(analyses(unit))
    if kind == 'noise':
        return line+'\nlet lesson_value = inoise_total\nprint lesson_value'
    if measurement(unit)['kind'] == 'current':
        return line+f'\nlet lesson_value = i({measurement(unit)["source"].lower()})\nprint lesson_value'
    if unit.get('reference'):
        return line+'\nlet stimulus = v(inp)-v(inn)\nmeas tran lesson_value FIND stimulus AT='+unit['at']
    if kind=='op':
        return line+'\nlet lesson_value = v(out)\nprint lesson_value'
    if kind=='ac':
        return line+'\nlet lesson_mag = mag(v(out))\nmeas ac lesson_value FIND lesson_mag AT='+unit['at']
    return line+'\nmeas '+kind+' lesson_value FIND v(out) AT='+unit['at']


def target(unit):
    if 'goal' in unit:
        return unit['goal']
    kind = unit['analysis']['type']
    sample = unit.get('at')
    when = {'op':'at the operating point', 'dc':f'at input {sample} V',
            'ac':f'at {sample} Hz', 'tran':f'at {scalar(sample)*1e6:g} µs' if kind=='tran' else ''}[kind]
    low, high = unit['limits']
    node = unit.get('node','out')
    reading = f'{node} relative to {unit["reference"]}' if unit.get('reference') else node
    text = f'Measure {reading} {when}. The target range is {low:g} to {high:g} V.'
    limits = {
        'tb-balanced-stimulus': 'Keep common mode within 5 mV of 0.90 V throughout the transition.',
        'tb-divider-sweep': 'Verify a gain of 0.50 V/V and linear response across the full sweep.',
        'tb-opamp-ac': 'Measure the first unity crossing and meet 45° phase margin.',
        'tb-opamp-step': 'Limit overshoot to 20 mV and settle to within 20 mV of 0.95 V in 8 µs.',
        'tb-tia-step': 'Limit undershoot to 20 mV and settle to within 20 mV of 0.80 V in 12 µs.',
    }
    return ' '.join(filter(None,(text,limits.get(unit['id']))))


def lessons():
    result = []
    for key, unit in course().items():
        if unit['project'] == verification.PROJECT:
            continue
        starter = STARTER+unit['project']
        result.append(dict(id=key, title=unit['title'], path=PATH['id'], topic=unit['topic'], starter=starter,
            bench_project=unit['project'], workspace=starter, requires=unit['requires'], minutes=25,
            summary=unit['concept'], skills=['testbench creation','ngspice',unit['analysis']['type'],unit['topic']],
            doc='STUDENT_TESTBENCHES.md', steps=[
                dict(id='predict', kind='quiz', title='Predict the measurement', instructions=unit['question'],
                     options=unit['options'], answer=unit['answer'], explanation=unit['explanation']),
                dict(id='measure', kind='check', title='Create and verify the bench', instructions=target(unit), rule={'type':'bench_lesson'}),
                dict(id='reflect', kind='reflection', title='Record your reasoning', instructions=unit['reflection'])]))
    prior = []
    for key, (title, steps, concept, question, options, reflection) in verification.LESSONS.items():
        identifier = verification.PREFIX+key
        starter = STARTER+verification.PROJECT
        checks = {step: verification.PREFIX+step for step in steps}
        result.append(dict(id=identifier, title=title, path=PATH['id'], topic=verification.TOPIC,
            starter=starter, workspace=starter, bench_project=verification.PROJECT, bench_checkpoints=checks,
            requires=prior.copy() if key=='challenge' else prior[-1:], minutes=15+10*len(steps), summary=concept,
            skills=['testbench creation','ngspice','op-amp characterization'], doc='STUDENT_TESTBENCHES.md', steps=[
                dict(id='predict', kind='quiz', title='Predict the measurement', instructions=question,
                     options=list(options), answer=0, explanation=concept),
                *(dict(id=step, kind='check', title=course()[unit]['title'], instructions=target(course()[unit]),
                       rule={'type':'bench_lesson'}) for step,unit in checks.items()),
                dict(id='reflect', kind='reflection', title='Record your evidence', instructions=reflection)]))
        prior.append(identifier)
    return result


def teaching(key):
    if key.removeprefix(verification.PREFIX) in verification.LESSONS:
        _, steps, concept, _, _, reflection = verification.LESSONS[key.removeprefix(verification.PREFIX)]
        return dict(concept=concept, worked_example=target(course()[verification.PREFIX+steps[0]]),
                    try_next='Repeat a checkpoint in the other workflow and compare the captured reading.',
                    interview='Explain how the stimulus, load, and observed waveform isolate the specification.',
                    artifact=reflection)
    unit = course()[key]
    return dict(concept=unit['concept'], worked_example=target(unit),
                try_next='Run the same fixture using the other testbench workflow and compare the captured readings.',
                interview='Explain what you drew in the fixture, what you configured in the analysis, and how the saved measurement checks the requirement.',
                artifact='Keep the schematic, saved measurement and result. Record the workflow and the conditions you used.')


def hints(key):
    if key.removeprefix(verification.PREFIX) in verification.LESSONS:
        _, steps, concept, _, _, _ = verification.LESSONS[key.removeprefix(verification.PREFIX)]
        unit = course()[verification.PREFIX+steps[0]]
        return {'predict': [('Which relationship applies?', concept), ('What should I inspect?', unit['work']),
                            ('What is the target?', target(unit)),
                            ('How do I test it?', 'Run the first fixture in either workflow and compare Results with the target.')]}
    unit = course()[key]
    return {'predict': [('What physical relationship should I use?', unit['concept']),
                        ('What should I look for on the schematic?', unit['work']),
                        ('Which reading will confirm the prediction?', target(unit)),
                        ('How can I check this with a simulation?', f'Build the {unit["analysis"]["type"]} analysis in either workflow and inspect the two input traces for a differential reading.' if unit.get('reference') else f'Build the {unit["analysis"]["type"]} analysis in either workflow and inspect out before recording your prediction.')]}


def practice(key):
    if key.removeprefix(verification.PREFIX) in verification.LESSONS:
        _, steps, *_ = verification.LESSONS[key.removeprefix(verification.PREFIX)]
        walkthroughs = {step: walkthrough(course()[verification.PREFIX+step]) for step in steps}
        return dict(tasks={step: task for step,(task, _) in walkthroughs.items()}, questions={},
                    bench_workflows={step: workflows for step,(_, workflows) in walkthroughs.items()})
    task, workflows = walkthrough(course()[key])
    return dict(tasks={'measure': task}, questions={}, bench_workflows={'measure': workflows})


def walkthrough(unit):
    if source := unit.get('reuse'):
        title = course()[source]['title']
        reuse = (f'Reuse your saved bench from “{title}”. Choose the workflow you configured there. '
                 'Open workspace to inspect the shared fixture. Compare reference and variant runs the same bench twice and substitutes only the DUT on the second run.')
        compare = 'Open Results to compare traces and measured limits. Choose Check this step to record the comparison.'
        steps = [reuse, compare]
        return [unit['goal']+' '+reuse, steps, unit.get('fault') or unit['goal']], dict(
            graphical=steps, spice=steps, program=program(course()[source]))
    kind = unit['analysis']['type']
    labels = {'source':'DC source name', 'dc_start':'DC start', 'dc_stop':'DC stop',
              'dc_step':'DC step', 'start':'Frequency start (Hz)', 'end':'Frequency end (Hz)',
              'points':'Frequency points / decade', 'step':'Transient step', 'stop':'Transient stop',
              'output':'Noise output net', 'noise_source':'Noise input voltage source'}
    settings = ', '.join(f'{labels[field]} = {unit["analysis"][field]}' for field in FIELDS[kind])
    at = f' Set At to {unit["at"]}.' if 'at' in unit else ' Leave At blank.'
    low, high = unit['limits']
    node, reference = unit.get('node','out'),unit.get('reference')
    ref = f'Set Reference net to {reference}.' if reference else 'Leave Reference net blank.'
    measure = (f'Open Measurements and choose Add measurement. Set Measure to voltage and Output net to {node}.{at} '
               f'Enter Minimum {low:g} and Maximum {high:g}. {ref} Leave Start and Stop blank.')
    if measurement(unit)['kind'] == 'current':
        measure = 'In Measurements add current, choose VDD as the voltage source, and set Minimum -105u and Maximum -95u.'
    elif kind == 'noise':
        measure = 'In Diagnostics select noise. In Measurements add input_noise and set Minimum 1.8u and Maximum 2.8u.'
    setup = f'Use analysis {kind} at nominal model corner and 27 °C.'
    if settings:
        setup += f' Set {settings}.'
    common = 'Choose Run lesson. When the run finishes, open Results, review the measurement and choose Check this step.'
    graph = ['Choose Open workspace. '+unit['work'], 'Choose Edit testbench and open Analysis and fixture. '+setup,
             f'In Probes and startup, check {", ".join(probes(unit))} and leave Initial voltage empty.', measure, 'Choose Save.', common]
    text = ['Choose Open workspace. '+unit['work'],
            'Choose Edit SPICE program. Enter the ngspice commands shown to configure the analysis and capture lesson_value.',
            'Choose Save.', common]
    goal = ' '.join((setup, target(unit))) if unit.get('goal') else ' '.join((unit['work'], setup, target(unit)))
    if unit.get('goal'):
        goal += ' Use Open workspace to complete the fixture and configure the matching analysis.'
    return [goal, graph, unit.get('fault') or target(unit)], {'graphical':graph,'spice':text,'program':program(unit)}


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


def _balanced():
    from .model import example
    p = example('empty')
    cell = p['cells'][0]
    cell['name'] = 'balanced_stimulus_fixture'
    for name, net, x in [('VPLUS','inp',250),('VMINUS','inn',620)]:
        source = device('V',name,x,250,value='.85',nets={'p':net,'n':'0'})
        _pulse(source,'.85','.95','4u','24u')
        cell['devices'].append(source)
    load = dict(id=uid(),name='differential_load',ports=['P','N'],shapes=[],devices=[
        device('R','RDIFF',425,135,rotation=270,value='100k',nets={'p':'P','n':'N'})])
    p['cells'].append(load)
    cell['devices'].append(device('X','XLOAD',435,150,cell=load['id'],nets={'P':'inp','N':'inn'}))
    return p


def create(kind):
    if kind == verification.PROJECT:
        p = verification.project()
    else:
        p = _divider() if kind=='divider' else _balanced() if kind=='balanced' else _analog(kind)
    names = {'tb-opamp-bias':'opamp_op_fixture'}
    fixtures = {key:next(c['id'] for c in p['cells'] if c['name']==names.get(key,
                (key if kind==verification.PROJECT else key.removeprefix('tb-')).replace('-','_')+'_fixture'))
                for key,unit in course().items() if unit['project']==kind and not unit.get('reuse')}
    p['top'] = next(iter(fixtures.values()))
    p['testbenches'] = []
    p.pop('test_plans',None)
    p['student_bench'] = dict(project=kind, fixtures=fixtures, programs={})
    topic = verification.TOPIC if kind == verification.PROJECT else next(item['topic'] for item in course().values() if item['project']==kind)
    p['name'] = 'Student bench · '+topic
    return validate(p)


def fixture(project, key):
    cid = project.get('student_bench',{}).get('fixtures',{}).get(key)
    if not cid or not any(c['id']==cid for c in project['cells']):
        raise ValueError('Open this testbench lesson project from Student Hub.')
    return cid


def saved_bench(project, key):
    cid = fixture(project,key)
    return next((t for t in project.get('testbenches',[]) if t['bench_cell']==cid),None)


def probes(unit):
    if 'probes' in unit:
        return unit['probes'].copy()
    node = unit.get('node','out')
    return [node,unit['reference']] if unit.get('reference') else [node]


def measurement(unit):
    if 'measurement' in unit:
        return dict(unit['measurement'], name='lesson_value')
    low, high = unit['limits']
    out = dict(name='lesson_value',kind='voltage',node=unit.get('node','out'),min=low,max=high)
    if unit.get('reference'):
        out['reference'] = unit['reference']
    if 'at' in unit:out['at'] = unit['at']
    return out


def read_measurement(result, unit):
    expected = dict(analysis=unit['analysis'], measurements=[measurement(unit)], probes=probes(unit))
    return testbenches.measure(result, expected)['measurements'][0]


def same_fields(actual, wanted):
    for key,value in wanted.items():
        found = actual.get(key)
        if found is None:
            return False
        if key in ('type','source','kind','node','reference','output','noise_source'):
            if str(found).casefold()!=str(value).casefold():return False
        elif not math.isclose(scalar(found),scalar(value),rel_tol=1e-10):return False
    return True


def validate_bench(bench, unit):
    if not bench:
        raise ValueError('Choose Edit testbench, configure the analysis and save it first.')
    if (bench.get('implementation_view') or bench.get('initial_conditions') or bench['analysis'].get('uic')
            or bench['analysis'].get('dc_startup')
            or not same_fields(bench['analysis'], {**unit['analysis'],'temperature':27})
            or bench['analysis'].get('corner','nominal')!='nominal'):
        raise ValueError('Use the specified schematic analysis at nominal corner and 27 °C.')
    diagnostic = bench['analysis'].get('diagnostic')
    if unit['analysis']['type']=='noise':
        if not diagnostic or diagnostic.get('kind')!='noise':
            raise ValueError('Enable the saved noise diagnostic to capture input and output spectra.')
    elif diagnostic:
        raise ValueError('Use the requested analysis without an additional diagnostic.')
    target_fields = {k:v for k,v in measurement(unit).items() if k!='name'}
    matching = [m for m in bench.get('measurements',[]) if not any(m.get(field) for field in ('start','stop'))
                and (m.get('reference') or None)==unit.get('reference') and same_fields(m,target_fields)]
    if not set(probes(unit)).issubset(bench['probes']) or not matching:
        raise ValueError('Save the required probes and measurement with the specified settings and limits.')


def validate_program(text, unit):
    lines = [' '.join(line.casefold().split()) for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    expected = program(unit).casefold().splitlines()
    if len(lines)!=len(expected):
        raise ValueError('Enter one native analysis and the lesson_value measurement in the SPICE program.')
    actual, wanted = lines[0].split(), expected[0].split()
    if len(actual)!=len(wanted) or actual[0]!=wanted[0]:
        raise ValueError('Use the analysis command and settings for this checkpoint.')
    for first, second in zip(actual[1:],wanted[1:]):
        if first!=second:
            try:
                same = math.isclose(scalar(first),scalar(second),rel_tol=1e-10)
            except ValueError:
                same = False
            if not same:
                raise ValueError('Use the analysis command and settings for this checkpoint.')
    for first, second in zip(lines[1:],expected[1:]):
        a,b = first.split('at='),second.split('at=')
        if a[0].replace(' ','')!=b[0].replace(' ','') or len(a)!=len(b) or (
                len(a)==2 and not math.isclose(scalar(a[1]),scalar(b[1]),rel_tol=1e-10)):
            raise ValueError('Measure out as lesson_value at the specified point.')


def prepare(project, lesson, workflow, tools, step='measure'):
    from .spice_program import find_ngspice
    from .run_environment import stamp
    key = checkpoint_key(lesson, step)
    source = workspace_key(lesson,step)
    cid = fixture(project,source)
    try:
        validate_setup(project,cid,source,workflow)
    except ValueError as exc:
        if source!=key:
            raise ValueError(f'Use the saved {WORKFLOWS.get(workflow, "testbench")} from “{course()[source]["title"]}”. {exc}') from exc
        raise
    exe = find_ngspice(tools.get('ngspice',''))
    if not exe:raise ValueError('Choose ngspice in the Student Hub Engine setup.')
    settings = dict(type='student_bench_lab',lesson=lesson['id'],workflow=workflow)
    if lesson.get('bench_checkpoints'):
        settings['checkpoint'] = key
    if source!=key:
        settings['reuse'] = source
    job = dict(project=clone(project),cell=cid,engine='ngspice',executable=exe,
               settings=settings,student_lesson=lesson['id'],student_bench_step=step)
    job['environment'] = stamp(job)
    return job


def validate_setup(project, cid, key, workflow):
    unit = course()[key]
    if 'edit' in unit:
        verification.validate_fixture(project, next(c for c in project['cells'] if c['id']==cid), unit)
    if workflow=='graphical':
        validate_bench(saved_bench(project,key),unit)
    elif workflow=='spice':
        validate_program(project['student_bench']['programs'].get(key,''),unit)
    else:
        raise ValueError('Choose one of the testbench workflows.')


def artifact_names(project, workflow):
    if workflow=='graphical' and project.get('spice',{}).get('version')==1:
        return 'input.cir', 'result.raw', 'engine.log'
    return ARTIFACTS[workflow]


def solution_bench(project, cid, unit):
    bench = testbenches.create(project,cid,'lesson_measurement')
    bench['analysis'].update(unit['analysis'], temperature=27, corner='nominal')
    bench['measurements'] = [measurement(unit)]
    if unit.get('reference') or unit.get('probes'):
        bench['probes'] = probes(unit)
    if unit['analysis']['type']=='noise':
        bench['analysis']['diagnostic'] = dict(kind='noise', output=unit['analysis']['output'], source=unit['analysis']['noise_source'])
    return bench


def run(job, directory, progress):
    p = job['project']
    settings = job['settings']
    key, workflow = settings.get('checkpoint',settings['lesson']), settings['workflow']
    unit = course()[key]
    source = settings.get('reuse')
    if source != unit.get('reuse'):
        raise ValueError('Prepare this comparison again with its saved reference fixture.')
    cid = fixture(p,source or key)
    if workflow not in WORKFLOWS or cid != job['cell']:
        raise ValueError('The saved run does not match this lesson fixture and workflow.')
    directory = Path(directory)
    if source:
        validate_setup(p,cid,source,workflow)
        reference = capture(p,cid,source,settings,job['executable'],directory/'reference',
                            lambda fraction,message:progress(fraction/2,'Reference · '+message))
        variant = verification.substitute(p,cid,unit['variant'])
        result = capture(variant,cid,source,settings,job['executable'],directory,
                         lambda fraction,message:progress(.5+fraction/2,'Variant · '+message))
        result['design_hash'] = design_digest(p)
        result['reference_trace'] = {field:reference[field] for field in ('x','traces','phase','currents') if field in reference}
        result['student_bench']['reference'] = reference['student_bench']['check']
        result['student_bench']['artifacts'].update({f'reference/{name}':content_hash
            for name,content_hash in reference['student_bench']['artifacts'].items()})
        return result
    return capture(p,cid,key,settings,job['executable'],directory,progress)


def capture(p, cid, key, settings, executable, directory, progress):
    from .native_analysis import circuit_text
    from .pdks import stage_model_deck
    from .spice_program import run_program

    unit, workflow = course()[key], settings['workflow']
    directory.mkdir(parents=True,exist_ok=True)
    standard = solution_bench(p,cid,unit)
    noise = unit['analysis']['type']=='noise'
    if workflow=='graphical':
        bench = saved_bench(p,key)
        validate_bench(bench,unit)
        result = testbenches.simulate(p,bench,executable,directory,progress=progress)
        if noise:
            from .engines import parse_raw
            variables, rows, _ = parse_raw(directory/'result.raw')
            result['traces'] = {name:[float(row[variables.index(name)]) for row in rows]
                                for name in ('inoise_spectrum','onoise_spectrum')}
    else:
        text = p['student_bench']['programs'].get(key,'')
        validate_program(text,unit)
        def deck(project, root):
            circuit = circuit_text(testbenches.spice_testbench(project,standard,root))
            return stage_model_deck(project['pdk'], circuit+'.temp 27\n.control\n'+text+'\n.endc\n.end\n',root)
        vectors = ['v('+node+')' for node in standard['probes']]
        if measurement(unit)['kind']=='current':
            vectors.append('i('+measurement(unit)['source'].lower()+')')
        result = run_program(p,cid,{**settings,'probes':' '.join(vectors),'timeout':90,'noise_spectrum':noise},executable,directory,
                             progress,deck,'ngspice · lesson SPICE program',{},'analysis_cases')
        cases = result['analysis_cases']
        if len(cases)!=1 or result['program_status']!='Complete':
            raise ValueError('The program did not complete the requested analysis. See Job log.')
        if noise:
            from .analog_diagnostics import noise_report
            result['diagnostics'] = noise_report(['frequency','inoise_spectrum','onoise_spectrum'],
                list(zip(result['x'], result['traces']['inoise_spectrum'], result['traces']['onoise_spectrum'])))
    if measurement(unit)['kind']=='current':
        result['currents'] = {name.casefold():values for name,values in result['currents'].items()}
    row = read_measurement(result,unit)
    if workflow=='spice':
        readings = [m['value'] for m in cases[0].get('measurements',[]) if m['name'].casefold()=='lesson_value']
        if (len(readings)!=1 or 'value' not in row or not math.isclose(readings[0],row['value'],
                rel_tol=.005 if noise else .002,abs_tol=1e-11 if noise else .00001)):
            raise ValueError('SPICE lesson_value is missing or disagrees with the captured waveform.')
    result.update(settings=settings,plot_kind=unit['analysis']['type'],student_bench={
        'lesson':settings['lesson'],'workflow':workflow,'check':row,
        'artifacts':{name:file_digest(directory/name) for name in artifact_names(p,workflow)}})
    if 'checkpoint' in settings:
        result['student_bench']['checkpoint'] = settings['checkpoint']
    return result


def validate_result(job, result, directory):
    settings = job['settings']
    workflow, lesson = settings.get('workflow'), settings.get('lesson')
    key = settings.get('checkpoint',lesson)
    source = settings.get('reuse')
    record = result.get('student_bench', {})
    if (key not in course() or workflow not in WORKFLOWS or result.get('settings') != settings
            or record.get('checkpoint',record.get('lesson')) != key or record.get('workflow') != workflow
            or record.get('lesson') != lesson or lesson != job.get('student_lesson')
            or course()[key].get('lesson',key) != lesson or course()[key].get('step','measure') != job.get('student_bench_step')
            or (source and course()[key].get('reuse')!=source)
            or fixture(job['project'], source or key) != job['cell']):
        raise ValueError('Testbench result does not match its saved lesson and workflow.')
    artifacts = record.get('artifacts', {})
    names = artifact_names(job['project'],workflow)
    if source:
        names += tuple('reference/'+name for name in names)
    try:
        expected = {name: file_digest(directory/name) for name in names}
    except OSError as exc:
        raise ValueError('A saved testbench artifact is missing.') from exc
    if artifacts != expected:
        raise ValueError('A saved testbench artifact has changed.')
    measured = read_measurement(result, course()[key])
    if record.get('check') != measured:
        raise ValueError('The saved testbench measurement does not match the waveform.')
    if source and record.get('reference') != read_measurement(result.get('reference_trace',{}),course()[source]):
        raise ValueError('The saved reference measurement does not match the reference waveform.')


def waveform_figures(key, result, verify=False):
    """Assess timing and balance from the same trace in either bench workflow."""
    unit = course()[key]
    if unit.get('metric'):
        return verification.figures(unit,result,verify)
    from .student_hub import at
    from .testbenches import crossings
    xs, traces = result['x'],result['traces']
    if key == 'tb-balanced-stimulus':
        plus, minus = traces['inp'],traces['inn']
        first, last = 2e-6,8e-6
        plateaus = [tuple(at(result,node,when) for node in ('inp','inn')) for when in (first,last)]
        pairs = [*plateaus,*((a,b) for t,a,b in zip(xs,plus,minus) if first<t<last)]
        peak = max(abs((a+b)/2-.9) for a,b in pairs)
        if verify and (peak > .005 or any(abs(a-b-expected) > .005 for (a,b),expected in zip(plateaus,(-.1,.1)))):
            raise ValueError(f'Peak common-mode error is {peak*1e3:.2f} mV. Hold it within 5 mV throughout the transition and reach both differential plateaus.')
        return {'Peak common-mode error (mV)':peak*1e3}
    if key == 'tb-divider-sweep':
        span = xs[-1]-xs[0]
        slope = (traces['out'][-1]-traces['out'][0])/span if span else 0
        intercept = traces['out'][0]-slope*xs[0]
        residual = max(abs(y-(slope*x+intercept)) for x,y in zip(xs,traces['out']))
        if verify and (abs(slope-.5)>.01 or abs(intercept)>.01 or residual>.01):
            raise ValueError('The sweep must follow the divider line throughout the applied input range.')
        return {'DC gain (V/V)':slope,'Maximum line error (V)':residual}
    if key == 'tb-tia-ac':
        return {'Transimpedance at the sample (Ω)':at(result,'out',scalar(course()[key]['at']))/1e-6}
    if key == 'tb-opamp-ac':
        import cmath
        from .student_ahuja import unity, unwrap
        phase = result.get('phase',{}).get('out')
        try:
            if not phase:
                raise ValueError('Capture the output gain and phase.')
            gain = [20*math.log10(max(v,1e-30)) for v in traces['out']]
            angles = unwrap(cmath.rect(1,math.radians(value)) for value in phase)
            frequency,margin = unity(xs,gain,angles)
        except ValueError:
            if verify:
                raise
            return {'First unity crossing (Hz)':None,'Phase margin (°)':None}
        if verify and margin<45:
            raise ValueError(f'Phase margin at the first unity crossing is {margin:.1f}°. Meet 45°.')
        return {'First unity crossing (Hz)':frequency,'Phase margin (°)':margin}
    if key not in ('tb-opamp-step','tb-tia-step'):
        return {}
    if key=='tb-opamp-step':
        name, edge, end, initial, final, peak_limit, deadline = 'vin',5e-6,15e-6,.85,.95,.02,8e-6
    else:
        # TIA output falls when the photocurrent rises; compare excursion
        # below the expected plateau rather than the starting voltage.
        name, edge, end, initial, final, peak_limit, deadline = None,10e-6,30e-6,.9,.8,.02,12e-6
    if name and name in traces:
        triggers = crossings(xs,traces[name],(initial+final)/2,start=edge,stop=end)
        if triggers:
            edge = triggers[0]
    times = [edge,*[t for t in xs if edge<t<end],end]
    voltage = [at(result,'out',edge),*[v for t,v in zip(xs,traces['out']) if edge<t<end],at(result,'out',end)]
    peak = max(0,max(v-final for v in voltage) if final>initial else max(final-v for v in voltage))
    outside = [i for i,v in enumerate(voltage) if abs(v-final)>.02]
    last = outside[-1] if outside else -1
    settled = (times[last+1]-edge) if last+1<len(times) else None
    excursion = 'Overshoot' if final>initial else 'Undershoot'
    if verify and (peak > peak_limit or settled is None or settled > deadline):
        settle = 'did not settle' if settled is None else f'settled in {settled*1e6:.2f} µs'
        raise ValueError(f'Output {settle} with {peak*1e3:.2f} mV {excursion.lower()}. Meet the step-response limits.')
    return {f'{excursion} (mV)':peak*1e3,'Settling within 20 mV (µs)':None if settled is None else settled*1e6}


def check(project, lesson, rows, step='measure'):
    from .student_hub import current_result
    key = checkpoint_key(lesson, step)
    tagged = [row for row in rows if row['job'].get('student_lesson')==lesson['id']
              and row['job'].get('settings',{}).get('type')=='student_bench_lab'
              and row['job'].get('student_bench_step','measure')==step]
    result, evidence = current_result(project,tagged)
    captured = result['student_bench']
    unit = course()[key]
    comparison = {}
    if source := unit.get('reuse'):
        if result['settings'].get('reuse')!=source or 'reference_trace' not in result:
            raise ValueError('Choose Compare reference and variant to capture both results with the reused bench.')
        baseline = captured['reference']
        if baseline['status']!='passed':
            raise ValueError('The reused bench must pass on the reference amplifier before it can identify the variant.')
        comparison = dict(reference_checkpoint=source, reference_reading=baseline['value'],
                          reference_figures=waveform_figures(source,result['reference_trace'],verify=True))
    measured = captured['check']
    if measured['status']!='passed':
        value = measured.get('value')
        reading = f'Measured {value:.5g} {measured.get("unit","V")}. ' if value is not None else ''
        raise ValueError(reading+target(course()[key]))
    figures = waveform_figures(key,result,verify=True)
    cell = next(c for c in project['cells'] if c['id']==fixture(project,unit.get('reuse',key)))
    parts = {part['name']: part for part in cell['devices']}
    if key=='tb-tia-ac' and not math.isclose(scalar(parts.get('IPHOTO', {}).get('source', {}).get('ac', '0')),1e-6):
        raise ValueError('Set the AC amplitude of IPHOTO to 1u before converting output voltage into transimpedance.')
    if key=='tb-opamp-ac':
        load = parts.get('CL', {})
        if (load.get('kind')!='C' or set(load['nets'].values())!={'out','0'}
                or not math.isclose(scalar(load['value']),1e-12)):
            raise ValueError('Connect the 1 pF load CL from out to ground in the loop fixture.')
    return dict(**evidence,bench_workflow=captured['workflow'],bench_reading=measured['value'],
                bench_unit=measured.get('unit','V'),bench_figures=figures, **comparison)
