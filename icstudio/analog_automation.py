"""Explicit analysis stages, bounded retries, and reusable measured evidence."""
import math
import time
from .model import clone, digest, design_digest, scalar


def validate(plan, workflow):
    if not workflow:return
    entries={e['id'] for e in plan['entries']}; stages=workflow.get('stages',[])
    if not 1<=len(stages)<=8:raise ValueError('Use one to eight verification stages.')
    assigned=[entry for stage in stages for entry in stage.get('entries',[])]
    if len(assigned)!=len(set(assigned)) or set(assigned)!=entries:
        raise ValueError('Assign every saved test to exactly one verification stage.')
    if any(not s.get('name','').strip() or not s.get('entries') for s in stages):raise ValueError('Each stage needs a name and at least one test.')
    retries=workflow.get('retries',0)
    if int(retries)!=scalar(retries) or not 0<=int(retries)<=2:raise ValueError('Use zero, one, or two diagnostic retries.')
    seconds=scalar(workflow.get('runtime_seconds',3600))
    if not 1<=seconds<=86400:raise ValueError('Total worker-time budget must be between one second and 24 hours.')


def stage_index(manifest, job):
    stages=manifest['spec']['workflow']['stages']
    return next(i for i,s in enumerate(stages) if job['case']['entry_id'] in s['entries'])


def gate_states(manifest, rows):
    from .analog_optimizer import evaluate
    stages=manifest['spec']['workflow']['stages']; passed=set(); rejected={}; blocked=set()
    for stage in range(len(stages)):
        jobs=[j for j in manifest['jobs'] if stage_index(manifest,j)==stage]
        spec=clone(manifest['spec']); spec.pop('workflow',None);spec.pop('fidelity',None)
        spec.update(screen_op=False,objectives=[]);spec.pop('objective',None)
        part={**manifest,'jobs':jobs,'spec':spec};part.pop('adaptive',None)
        result=evaluate(part,rows)
        for c in result['candidates']:
            key=(c['candidate'],stage)
            if c['complete']==c['total'] and not c.get('evidence_errors'):
                if c['failures']:rejected.setdefault(c['candidate'],stage)
                else:passed.add(key)
            else:blocked.add(key)
    return dict(passed=passed,rejected=rejected,blocked=blocked)


def eligible(manifest, jobs, rows):
    gates=gate_states(manifest,rows)
    return [j for j in jobs if all((j['case']['candidate'],s) in gates['passed'] for s in range(stage_index(manifest,j)))]


def omitted(manifest, job, gates):
    return stage_index(manifest,job)>gates['rejected'].get(job['case']['candidate'],math.inf)


def worker_seconds(manifest, rows):
    total=0.
    for row in rows:
        if row['job'].get('case',{}).get('group')!=manifest['id']:continue
        if row['state'] in ('Running','Stopping') and row.get('started') is not None:total+=time.monotonic()-row['started']
        else:total+=float(row.get('elapsed',0))
    return total


def retries(manifest, rows):
    """Repeat exact failed inputs, never performance failures or cancellations."""
    from .variation_runs import latest
    maximum=int(manifest['spec'].get('workflow',{}).get('retries',0));out=[]
    if not maximum:return out
    current=latest(manifest,rows)
    for j in manifest['jobs']:
        row=current.get(j['case']['index'],{})
        attempts=[r for r in rows if r['job'].get('case',{}).get('group')==manifest['id'] and r['job']['case']['index']==j['case']['index'] and cache_key(r['job'])==j['case']['fingerprint']]
        if row.get('state')=='Failed' and len(attempts)<=maximum:out.append(clone(j))
    return eligible(manifest,out,rows)


def exhausted(manifest,rows):
    workflow=manifest['spec'].get('workflow')
    return bool(workflow and worker_seconds(manifest,rows)>=scalar(workflow['runtime_seconds']))


def blocked(manifest,rows):
    from .analog_optimizer import evaluate,ready_jobs,ACTIVE
    result=evaluate(manifest,rows)
    return (any(c['evidence_errors'] for c in result['candidates']) and not any(r['state'] in ACTIVE for r in result['current'].values())
            and not ready_jobs(manifest,rows) and not retries(manifest,rows) and not result['complete'])


def cache_key(job):
    return digest({k:v for k,v in job.items() if k!='case'})


def reusable(job, rows):
    """Only exact current executable/model/project/settings identities qualify."""
    from .run_environment import verify
    verify(job); key=cache_key(job)
    for row in reversed(rows):
        if row['state']!='Complete' or cache_key(row['job'])!=key:continue
        r=row.get('result',{})
        if r.get('analysis_cases') or r.get('xschem_cases'):continue  # These need original raw artifacts.
        expected=job['settings']
        if expected.get('type')=='testbench':
            expected=next(t['analysis'] for t in job['project']['testbenches'] if t['id']==expected['testbench'])
        if r.get('project_id')!=job['project']['id'] or r.get('cell_id')!=job['cell'] or r.get('design_hash')!=design_digest(job['project']) or r.get('settings')!=expected:continue
        if job['engine']=='ngspice' and r.get('engine_hash')!=job.get('environment',{}).get('executable_sha256'):continue
        if not isinstance(r.get('x'),list) or not isinstance(r.get('traces'),dict):continue
        import json
        try:json.dumps(r,allow_nan=False)
        except (ValueError,TypeError):continue
        if job['engine']=='ngspice':
            from .pdks import model_lines
            from .osdi import verified
            model_lines(job['project']['pdk'],job['settings'].get('corner','nominal'));verified(job['project'])
        return row
    return None


def report(manifest, rows):
    from .analog_optimizer import evaluate
    result=evaluate(manifest,rows)
    return dict(experiment=manifest['id'],base_design_hash=manifest['base_design_hash'],
        scope='Measured saved conditions only; predictions do not establish verification.',
        elapsed_worker_seconds=worker_seconds(manifest,rows),workflow=manifest['spec'].get('workflow'),
        cached_runs=sum(bool(r.get('result',{}).get('reused_from')) for r in result['current'].values()),
        complete=result['complete'],candidates=result['candidates'],skipped=result['skipped'])


def report_document(manifest,result):
    return dict(schema=1,experiment=manifest['id'],name=manifest['name'],created=manifest['created'],project_id=manifest['project_id'],
        base_design_hash=manifest['base_design_hash'],spec=clone(manifest['spec']),plan=clone(manifest['plan']),
        run_inputs=[dict(index=j['case']['index'],candidate=j['case']['candidate'],condition=j['case']['labels'],fingerprint=j['case']['fingerprint'],environment=j.get('environment')) for j in manifest['jobs']],results=result)


def save_report(manifest,result,root):
    import json
    from pathlib import Path
    from .model import atomic_write
    path=Path(root)/manifest['project_id']/'reports'/(manifest['id']+'.json')
    atomic_write(path,json.dumps(report_document(manifest,result),indent=2,allow_nan=False));manifest['report_path']=str(path);return path
