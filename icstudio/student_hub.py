"""Curriculum, durable learning records and evidence-based checkpoints (no Qt)."""
import json
import math
import re
import sys
from functools import lru_cache
from pathlib import Path

from .model import atomic_write, clone, design_digest, digest, file_digest, load_project, now, scalar

RULES = {'structure','nets','value','hierarchy','layout','saved','result','current','difference','standard_cell',
         'digital_sources','digital','sar','config','config_number','rtl_contains','capstone','campaign',
         'device_metrics','layout_exercise','inverter','analog_project','layout_decisions','layout_study','signal_study','lc_bode','bench_lesson','loop_study'}
# Increment for a change to grading semantics. Unrelated application releases
# must not erase a student's earned progression; exact grader identity is also
# retained on each newly awarded evidence record.
CHECKER_REVISION = 1
DIFFICULTIES = ('Easy', 'Medium', 'Hard')

# Credit earned under the audited rubric remains historical evidence. New
# runs are always checked against the current lesson.
REVIEWED_PROGRESS = {
    "a-gmid-tradeoff": "a2345e20ed2ffd6dd7b8cebd50085d168d40f1cf33b6ec8085720128e7d8c40a",
    "a-switch-drive": "c0a2db3a977f5be3f479a09d0ef770134caf2c0ea5ccc654ab69751f8aa2565b",
    "tb-tia-step": "8bced99a3c98b11d1cbcdc2f1ff4c8192560f3b46c206f085a7605ff58b1c2c1",
    "tb-opamp-step": "f77cb95e030e5339d0d6117f76c206330d4badcb7a24816ea741531c21aede7a",
    "tb-balanced-stimulus": "61f1165fb5897625e7f2f77d85ad8a52bed1bc5d1ff5fb983437caa799a5b922",
    "tb-divider-sweep": "a720f793ea5c2aac1fa85c38b6f88796f63d87a55c3827275ce37fd3d849d5e0",
    "tb-opamp-ac": "0848e211e6e68b3d5d9837053de72871251c8967263ba2481ff562a9a0e1b75f",
}


@lru_cache(maxsize=1)
def difficulty_map():
    from .getting_started import resource_root
    source = resource_root()/'examples/student-hub/difficulty.json'
    bands = json.loads(source.read_text(encoding='utf-8'))
    labels = {key: band for band, keys in bands.items() for key in keys}
    if set(bands) != set(DIFFICULTIES) or len(labels) != sum(map(len,bands.values())):
        raise ValueError('Assign each lesson exactly one difficulty.')
    return labels


def difficulty_for(key):
    try:
        return difficulty_map()[key]
    except KeyError as exc:
        raise ValueError('Assign a difficulty to lesson '+key+'.') from exc


def curriculum():
    from .getting_started import resource_root
    from .student_layout_labs import course, lessons
    from . import student_beacon, student_signal_labs, student_standard_cells, student_testbench
    data = json.loads((resource_root()/'examples/student-hub/curriculum.json').read_text(encoding='utf-8'))
    data['lessons'].extend(lessons(course()))
    data['lessons'].extend(student_signal_labs.lessons(student_signal_labs.course()))
    data['paths'].append(dict(student_testbench.PATH))
    data['lessons'].extend(student_testbench.lessons())
    data['paths'].append(dict(student_standard_cells.PATH))
    data['lessons'].extend(student_standard_cells.lessons())
    data['lessons'].extend(student_beacon.lessons())
    from .student_loop_study import add_checkpoints
    add_checkpoints(data['lessons'])
    for lesson in data['lessons']:
        lesson['difficulty'] = difficulty_for(lesson['id'])
    validate_curriculum(data)
    from .student_paths import validate_routes
    validate_routes(data['lessons'])
    return data


def validate_curriculum(data):
    paths = [p['id'] for p in data['paths']]
    if (data.get('version') != 1 or len(paths) != len(set(paths)) or
            not {'foundations','analog','digital','mixed'} <= set(paths) or
            any(not re.fullmatch('[a-z][a-z0-9-]{1,60}', p) or p == 'capstone' for p in paths)):
        raise ValueError('Unsupported student curriculum.')
    ids = set()
    for lesson in data['lessons']:
        if not re.fullmatch('[a-z][a-z0-9-]{1,60}',lesson['id']) or lesson['id'] in ids:
            raise ValueError('Lesson IDs must be stable and unique.')
        ids.add(lesson['id'])
        if lesson['path'] not in {*paths,'capstone'}:
            raise ValueError('Unknown learning path.')
        if lesson.get('difficulty') not in DIFFICULTIES:
            raise ValueError('Choose Easy, Medium or Hard for every lesson.')
        if not re.fullmatch('[a-z][a-z0-9-]{1,60}',lesson['workspace']):raise ValueError('Invalid lesson workspace.')
        steps = lesson['steps']
        if not steps or len({s['id'] for s in steps}) != len(steps):raise ValueError('Steps need unique IDs.')
        for step in steps:
            if step['kind'] not in ('quiz','check','reflection'):raise ValueError('Unsupported checkpoint kind.')
            if step['kind']=='check' and step['rule']['type'] not in RULES:raise ValueError('Unknown checkpoint rule.')
            if step['kind']=='quiz' and (type(step['answer']) is not int or not 0<=step['answer']<len(step['options'])):
                raise ValueError('Invalid knowledge check.')
    by_id = {l['id']:l for l in data['lessons']}; visiting=set(); visited=set()
    def visit(key):
        if key not in by_id:raise ValueError('Unknown prerequisite: '+key)
        if key in visiting:raise ValueError('Cyclic learning prerequisites.')
        if key in visited:return
        visiting.add(key)
        for parent in by_id[key]['requires']:visit(parent)
        visiting.remove(key);visited.add(key)
    for key in ids:visit(key)


@lru_cache(maxsize=1)
def checker_stamp():
    if getattr(sys,'frozen',False):
        from .build_info import WORKFLOW_SOURCE_HASH
        return WORKFLOW_SOURCE_HASH
    return digest([file_digest(__file__),file_digest(Path(__file__).with_name('student_capstone.py')),
                   file_digest(Path(__file__).with_name('student_projects.py')),
                   file_digest(Path(__file__).with_name('student_design_labs.py')),
                   file_digest(Path(__file__).with_name('student_inverter.py')),
                   file_digest(Path(__file__).with_name('student_analog.py')),
                   file_digest(Path(__file__).with_name('student_filters.py')),
                   file_digest(Path(__file__).with_name('student_layout_decisions.py')),
                   file_digest(Path(__file__).with_name('student_layout_labs.py')),
                   file_digest(Path(__file__).with_name('student_layout_signoff.py')),
                   file_digest(Path(__file__).with_name('student_signal_labs.py')),
                   file_digest(Path(__file__).with_name('student_signal_circuits.py')),
                   file_digest(Path(__file__).with_name('student_testbench.py')),
                   file_digest(Path(__file__).with_name('student_opamp_verification.py')),
                   file_digest(Path(__file__).with_name('student_paths.py')),
                   file_digest(Path(__file__).with_name('student_beacon.py')),
                   file_digest(Path(__file__).with_name('student_standard_cells.py')),
                   file_digest(Path(__file__).with_name('student_cell_layout.py')),
                   file_digest(Path(__file__).with_name('student_cell_specs.py')),
                   file_digest(Path(__file__).with_name('student_cell_characterization.py')),
                   file_digest(Path(__file__).with_name('student_cell_row.py')),
                   file_digest(Path(__file__).with_name('student_circuit_challenges.py')),
                   file_digest(Path(__file__).with_name('student_logic_cells.py')),
                   file_digest(Path(__file__).with_name('student_layout_passives.py')),
                   file_digest(Path(__file__).with_name('student_spi.py')),
                   file_digest(Path(__file__).with_name('student_loop_study.py'))])


def lesson_stamp(lesson):
    graded = {key:value for key,value in lesson.items() if key!='difficulty'}
    return digest(dict(lesson=graded,checker_revision=CHECKER_REVISION))


def earned(state, lesson):
    record=state.get('lessons',{}).get(lesson['id'],{})
    if record.get('stamp')==lesson_stamp(lesson):
        return record.get('steps',{})
    prior = REVIEWED_PROGRESS.get(lesson['id'])
    if prior and record.get('stamp')==prior:
        return record.get('steps',{})
    from .student_loop_study import legacy_lesson
    old = legacy_lesson(lesson)
    if old and record.get('stamp')==lesson_stamp(old):
        # The new experiment must be earned, while earlier correct answers
        # and written reflections retain their historical evidence.
        return record.get('steps',{})
    return {}


def complete(state, lesson):
    return all(s['id'] in earned(state,lesson) for s in lesson['steps'])


def missing_prerequisites(state, lesson, data):
    by_id={l['id']:l for l in data['lessons']}
    missing=[];visited=set()
    def visit(key):
        if key in visited:return
        visited.add(key)
        for parent in by_id[key]['requires']:
            visit(parent)
            if not complete(state,by_id[parent]) and parent not in missing:missing.append(parent)
    visit(lesson['id']);return missing


def next_lesson(state, data):
    return next((l for l in data['lessons'] if not complete(state,l) and not missing_prerequisites(state,l,data)),None)


class Portfolio:
    """Atomic writes and optimistic conflict detection; never silently reset work."""
    def __init__(self, root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'progress.json'
        self.token=file_digest(self.path) if self.path.exists() else None
        self.state=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else dict(version=1,workspaces={},lessons={})
        self.validate(self.state)

    @staticmethod
    def validate(state):
        if not isinstance(state,dict) or state.get('version')!=1 or not isinstance(state.get('workspaces'),dict) or not isinstance(state.get('lessons'),dict):
            raise ValueError('Cannot read student progress. Preserve progress.json and restore a valid learning record.')
        for record in state['workspaces'].values():
            if not isinstance(record,dict) or not isinstance(record.get('project_id'),str) or not isinstance(record.get('path'),str):
                raise ValueError('Invalid saved lesson workspace.')
        for record in state['lessons'].values():
            if not isinstance(record,dict) or not isinstance(record.get('steps',{}),dict) or not isinstance(record.get('notes',{}),dict):
                raise ValueError('Invalid saved lesson progress.')
            for step in record.get('steps',{}).values():
                if not isinstance(step,dict) or step.get('kind') not in ('quiz','check','reflection') or not isinstance(step.get('evidence'),dict):
                    raise ValueError('Invalid saved checkpoint evidence.')

    def write(self, state):
        self.validate(state)
        current=file_digest(self.path) if self.path.exists() else None
        if current!=self.token:raise ValueError('Student progress changed in another window. Reopen the Student Hub before saving progress.')
        atomic_write(self.path,json.dumps(state,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
        self.state=clone(state);self.token=file_digest(self.path)

    def attach(self, lesson, project, path):
        state=clone(self.state)
        state['workspaces'][lesson['workspace']]=dict(project_id=project['id'],path=str(Path(path).resolve()))
        self.write(state)

    def workspace(self, lesson):return self.state['workspaces'].get(lesson['workspace'])

    def save_note(self, lesson, step, text):
        if len(text)>20000:raise ValueError('Keep each reflection under 20,000 characters.')
        state=clone(self.state);record=state['lessons'].setdefault(lesson['id'],{})
        record.setdefault('notes',{})[step['id']]=text;self.write(state)

    def award(self, lesson, step, evidence, data):
        workspace=self.workspace(lesson)
        if not workspace or workspace['project_id']!=evidence.get('project_id'):
            raise ValueError('Checkpoint evidence belongs to another lesson project.')
        if missing_prerequisites(self.state,lesson,data):raise ValueError('Practice check passed. Complete the listed prerequisites to earn progression credit.')
        previous=lesson['steps'][:lesson['steps'].index(step)]
        if any(s['id'] not in earned(self.state,lesson) for s in previous):raise ValueError('Complete the earlier steps in this lesson first.')
        state=clone(self.state);record=state['lessons'].setdefault(lesson['id'],{})
        stamp=lesson_stamp(lesson)
        if record.get('stamp')!=stamp:record['steps']=clone(earned(self.state,lesson))
        record['stamp']=stamp
        record['steps'][step['id']]=dict(kind=step['kind'],earned=now(),evidence=clone(evidence))
        self.write(state)

    def export(self, destination, data):
        payload=dict(version=1,exported=now(),curriculum=digest(data),progress=clone(self.state),projects={})
        for key, record in self.state['workspaces'].items():
            path=Path(record['path'])
            if path.is_file():
                project=load_project(path)
                if project['id']!=record['project_id']:raise ValueError('A saved lesson project was replaced: '+str(path))
                payload['projects'][key]=dict(project=project,sha256=file_digest(path))
            else:payload['projects'][key]=dict(missing=True,path=str(path))
        # Run directories stay beside the application; hashes and paths identify
        # the evidence. This export is a learning record, not a signoff package.
        atomic_write(destination,json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def tools_for_lesson(lesson):
    from .student_signal_circuits import NATIVE
    from .student_layout_labs import PROCESS
    requirements = []
    stage = lesson.get('inverter_stage')
    mixed = any(s.get('rule',{}).get('type') in {'sar','capstone','campaign'} for s in lesson['steps'])
    if (lesson.get('bench_project') or lesson.get('signal_lab') in NATIVE
            or (lesson.get('standard_cell') and lesson['standard_cell']!='abutment')
            or lesson.get('analog_project') or stage in ('dc','transient','handoff') or mixed):
        requirements.append('ngspice')
    if lesson['path']=='digital' or mixed:
        requirements.append('Icarus Verilog')
    if lesson.get('vga_lesson'):
        requirements.append('VGA Playground assets for live preview')
    if stage in ('drc','lvs','handoff') or lesson.get('layout_lab') in PROCESS or any(
            s['id']=='post-layout' for s in lesson['steps']):
        requirements.append('Matching process verification decks and physical tools')
    return tuple(requirements)


def prepare_lesson(project, tools=None, toolchain='auto'):
    from .digital_design import config
    if project.get('mixed_signal'):
        from .mixed_signal import prepare
        return prepare(project,tools,setup_panel='Student Hub → Engine setup')
    if config(project,project['top']):
        from .digital_flow import prepare
        return prepare(project,tools=tools,toolchain=toolchain)
    from .run_environment import stamp
    p=clone(project);job=dict(project=p,cell=p['top'],engine='builtin',settings=clone(p['analysis']))
    job['environment']=stamp(job);return job


def campaign_jobs(project, tools=None):
    from .student_capstone import CASES,case_project
    key=design_digest(project);jobs=[]
    for name in CASES:
        job=prepare_lesson(case_project(project,name),tools)
        job['student_campaign']=dict(base_design=key,case=name)
        jobs.append(job)
    return jobs


def captured(row):
    from .job_store import read_result
    if row.get('state')!='Complete':raise ValueError('Wait for a successfully completed run.')
    root=Path(row['path']);job=json.loads((root/'input.json').read_text(encoding='utf-8'))
    result=read_result(root/'result.json',job['project']['id'])
    if result.get('settings')!=job['settings']:raise ValueError('Captured analysis settings do not match.')
    return job,result,dict(run=str(root),input_sha256=file_digest(root/'input.json'),result_sha256=file_digest(root/'result.json'),
                           environment=job.get('environment'),engine=result.get('engine'))


def current_result(project, rows):
    key=design_digest(project)
    candidates=[r for r in rows if r.get('state')=='Complete' and r.get('result',{}).get('design_hash')==key and not r['job'].get('student_campaign')]
    if not candidates:raise ValueError('Run this lesson after your latest edits. No completed result matches the current design.')
    job,result,evidence=captured(candidates[-1])
    if design_digest(job['project'])!=key:raise ValueError('Captured result belongs to an earlier design.')
    return result,evidence


def at(result, name, time=None):
    values=result.get('traces',{}).get(name);xs=result.get('x',[])
    if not values or len(xs)!=len(values):raise ValueError('Missing measured trace: '+name)
    if any(not math.isfinite(v) for v in values):raise ValueError('Non-finite measured trace.')
    if time is None:return values[0]
    if not xs[0]<=time<=xs[-1]:raise ValueError('The run does not cover the required measurement point.')
    import bisect
    i=bisect.bisect_left(xs,time)
    if not i or xs[i]==time:return values[i]
    return values[i-1]+(values[i]-values[i-1])*(time-xs[i-1])/(xs[i]-xs[i-1])


def evaluate(step, lesson, project, rows=(), path=None, answer=None, note=''):
    evidence=dict(project_id=project['id'],design_hash=design_digest(project),checker=checker_stamp())
    if step['kind']=='quiz':
        if answer!=step['answer']:raise ValueError('Try again. '+step['explanation'])
        return dict(**evidence,answer=answer,explanation=step['explanation'])
    if step['kind']=='reflection':
        from .student_paths import reflection_body
        body = reflection_body(note)
        terms = set(re.findall(r'[^\W_]+',body.casefold()))
        if len(body)<40 or len(terms)<4:
            raise ValueError('Record the test conditions, an observation and your reasoning in at least 40 characters.')
        return dict(**evidence,note=note.strip(),assessment='Recorded reflection for instructor review.')
    rule=step['rule'];kind=rule['type']
    if kind=='analog_project':
        from .student_analog import check
        return dict(**evidence, **check(project, lesson['analog_project'], step['id'], rows))
    if kind=='layout_study':
        from .student_layout_labs import check
        return dict(**evidence, **check(project, lesson, step['id'], rows))
    if kind=='signal_study':
        from .student_signal_labs import check
        return dict(**evidence, **check(project, lesson, step['id'], rows))
    if kind=='bench_lesson':
        from .student_testbench import check
        return dict(**evidence, **check(project, lesson, rows, step['id']))
    if kind=='loop_study':
        from .student_loop_study import check
        return dict(**evidence, loop_measurements=check(project,lesson['starter']))
    if kind=='standard_cell':
        from .student_standard_cells import check
        return dict(**evidence, **check(project, lesson, step['id'], rows))
    if kind in ('layout_decisions','lc_bode'):
        if kind=='layout_decisions':
            from .student_layout_decisions import EXTRACTION_STEPS, check_geometry, check_run
            if step['id'] not in EXTRACTION_STEPS:
                return dict(**evidence, **check_geometry(project, step['id']))
        else:
            from .student_filters import check as check_run
        result,record=current_result(project, rows)
        return dict(**evidence, **record, lesson_measurements=check_run(project,result,step['id']))
    devices=[d for c in project['cells'] for d in c['devices']]
    def find(name):
        ds=[d for d in devices if d['name']==name]
        if len(ds)!=1:raise ValueError('Find exactly one device named '+name)
        return ds[0]
    def require(ok,message):
        if not ok:raise ValueError(message)
    if kind=='inverter':
        from .student_inverter import check
        evidence.update(check(project,lesson,rule,rows))
    elif kind=='structure':require(all(any(d['name']==n for d in devices) for n in rule['devices']),'Find the named devices in this lesson project.')
    elif kind=='value':
        value=find(rule['device'])
        for field in rule['field'].split('.'):value=value[field]
        numeric=scalar(value)
        if lesson['id']=='f-debug' and rule['device']=='Rload':
            require(numeric>0,'Use a positive load resistance.')
            for name in ('R1','R2'):
                require(math.isclose(scalar(find(name)['value']),1e4),'Keep the two divider resistors at 10 kΩ.')
            evidence['load_resistance_ohm']=numeric
        elif lesson['id'] in ('a-gmid-size','a-gmid-tradeoff') and rule['field']=='params.w':
            require(numeric>0,'Use a positive transistor width. The next checkpoint checks the measured bias targets.')
            evidence['device_width_m']=numeric
        else:
            require(math.isclose(numeric,scalar(rule['value']),rel_tol=1e-9),f'Set {rule["device"]} {rule["field"]} to {rule["value"]}.')
    elif kind=='nets':require(find(rule['device'])['nets']==rule['nets'],'Review the terminal net assignments.')
    elif kind=='hierarchy':require(len(project['cells'])>=rule['minimum'] and any(d['kind']=='X' for d in devices),'Keep the reusable cell and its instance.')
    elif kind=='layout':require(sum(len(c['shapes']) for c in project['cells'])>=rule['minimum'],'Open the lesson geometry before checking. This checks geometry presence only.')
    elif kind=='layout_exercise':
        from .student_design_labs import check_layout
        evidence.update(check_layout(project,rule['exercise']))
    elif kind=='saved':
        require(path and Path(path).is_file(),'Choose Save work before checking this step.')
        require(digest(load_project(path))==digest(project),'Save your latest changes before checking this step.')
        evidence['saved_sha256']=file_digest(path)
    elif kind in ('config','config_number'):
        value=project.get('mixed_signal',{})
        for key in rule['path']:value=value[key]
        ok=math.isclose(scalar(value),scalar(rule['value']),rel_tol=1e-9) if kind=='config_number' else value==rule['value']
        require(ok,'Apply the requested bridge configuration before checking.')
    elif kind in ('digital_sources','rtl_contains'):
        from .digital_design import config
        cid=project.get('mixed_signal',{}).get('digital_cell',project['top']);rtl=config(project,cid)
        require(bool(rtl),'Open the lesson RTL project.')
        if kind=='rtl_contains':require(any(rule['text'] in f['text'] for f in rtl['files'] if f['role']=='rtl'),'Apply the requested RTL edit before checking.')
        else:require(any(f['role']=='rtl' for f in rtl['files']) and any(f['role']=='testbench' for f in rtl['files']),'Keep the design and reference testbench.')
    elif kind=='campaign':
        from .student_capstone import CASES,case_project,report
        evidence['cases']=[]
        for case in CASES:
            expected=case_project(project,case)
            candidates=[r for r in rows if r.get('state')=='Complete' and r['job'].get('student_campaign')==dict(base_design=design_digest(project),case=case)]
            require(bool(candidates),'Run qualification for the latest design. Missing completed case: '+case)
            job,result,record=captured(candidates[-1])
            require(design_digest(job['project'])==design_digest(expected),'Qualification input differs from the declared case: '+case)
            checked=report(result,case);require(checked['status']=='PASS',case+': '+', '.join(c['name'] for c in checked['checks'] if not c['passed']))
            evidence['cases'].append(dict(case=case,report=checked,**record))
    else:
        result,record=current_result(project,rows);evidence.update(record)
        if kind=='device_metrics':
            from .analog_optimizer import read_gmid
            require(result['settings'].get('type')=='op','Run an operating-point analysis for this bias checkpoint.')
            point=read_gmid(dict(project=project,cell=project['top']),result,rule['device'])
            failures=[]
            for metric, bounds in rule['bounds'].items():
                value=point.get(metric)
                if not isinstance(value,(int,float)) or not math.isfinite(value) or not bounds[0]<=value<=bounds[1]:
                    failures.append(f'{metric}: {value}; target {bounds[0]:g}–{bounds[1]:g}')
            require(not failures,'Bias requirements failed. '+ '; '.join(failures))
            evidence['device_metrics']=point
        elif kind in ('result','current','difference'):
            expected_type=rule.get('analysis','op')
            require(result['settings'].get('type')==expected_type,'Run the requested '+expected_type+' analysis.')
            if kind=='current':measured=abs(result.get('operating_currents',{}).get(rule['name'],float('nan')))
            elif kind=='difference':measured=at(result,rule['positive'])-at(result,rule['negative'])
            else:measured=at(result,rule['trace'],rule.get('at'))
            require(math.isfinite(measured) and rule['low']<=measured<=rule['high'],f'Measured {measured:.6g}; target {rule["low"]:.6g}–{rule["high"]:.6g}. Inspect the circuit and analysis settings.')
            evidence['measurement']=measured
        elif kind=='digital':
            from .digital_design import config
            from .student_projects import digital_project
            files=config(project,project['top'])['files'];reference=config(digital_project(rule['design']))
            wanted=next(f for f in reference['files'] if f['role']=='testbench')
            require([f for f in files if f['role']=='testbench']==[wanted],'Restore the original reference testbench before earning this checkpoint.')
            require(result.get('digital_result',{}).get('stage')=='simulate','Run the reference simulation, not only compilation or synthesis.')
            log=result['digital_result']['artifacts']['log']['path']
            marker = 'STUDENT_CHECKS PASS '+rule['design']
            output = (Path(record['run'])/log).read_text(encoding='utf-8')
            if checkpoint := rule.get('checkpoint'):
                require(marker+' '+checkpoint in (line.strip() for line in output.splitlines()),
                        'The reference testbench did not pass this checkpoint. Review the run log.')
            else:
                require(marker in output,'The reference testbench did not finish all checks.')
        elif kind=='sar':
            samples=result.get('mixed_signal',{}).get('samples',[]);done=[s for s in samples if s['outputs'].get('done')==1]
            actual=[s['outputs'].get('code') for s in done];edges=[s['edge'] for s in done]
            require(actual==rule['codes'] and edges==rule['edges'],f'Observed codes {actual} at edges {edges}; expect {rule["codes"]} at {rule["edges"]}.')
            evidence.update(codes=actual,edges=edges)
        elif kind=='capstone':
            from .student_capstone import report
            checked=report(result);checks=checked['checks']
            if rule['checks']!='all':checks=[c for c in checks if c['name'] in rule['checks']]
            require(bool(checks) and all(c['passed'] for c in checks),'Requirements failed: '+', '.join(c['name'] for c in checks if not c['passed']))
            evidence['checks']=checks
        else:raise ValueError('Unsupported checkpoint.')
    return evidence
