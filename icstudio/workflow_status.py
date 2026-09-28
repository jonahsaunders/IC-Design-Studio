"""Evidence-backed workflow states. Never combine conditions from different runs."""
import itertools

from .model import digest,design_digest,scalar
from .test_plans import matrix,case_count,condition_key,validate_plans


def state(status,detail,**evidence):
    return dict(status=status,detail=detail,**evidence)


def run_state(row):
    execution=row.get('state','').lower()
    if execution in ('queued','running','stopping'):
        return state('Running',execution.title(),run_id=row['id'])
    if execution=='failed':return state('Failed',row.get('log') or 'Run failed',run_id=row['id'])
    if execution!='complete':return state('Blocked',execution.title() or 'Unknown run state',run_id=row['id'])
    if not row.get('result'):return state('Blocked','The completed run has no result',run_id=row['id'])
    return None


def requirement_state(rows,group):
    """Use the same captured requirement evaluation as the results matrix."""
    data=matrix(rows,group)
    cells=[(r,v) for r in data['rows'] for v in r['values'].values()]
    if not cells or any(r['definition'].get('definition')=='missing' for r,_ in cells):
        return state('Blocked','Save measurable requirements before claiming verification')
    for expected,actual in cells:
        if actual['status']=='FAIL':
            return state('Failed',expected['test']+' · '+expected['name'],run_id=actual['run_id'],requirement=expected['name'])
    for expected,actual in cells:
        if actual['status']!='PASS':
            return state('Blocked',expected['test']+' · '+expected['name']+': '+actual['status'],
                         run_id=actual['run_id'],requirement=expected['name'])
    return state('Passed',str(len(cells))+' requirement results passed')


def bench_status(project,bench,rows,current_hash=None,physical=False):
    if bench is None:return state('Not run','Choose a saved testbench')
    kinds=('silicon',) if physical else ('testbench',)
    chosen=[r for r in rows if r.get('job',{}).get('project',{}).get('id')==project['id']
            and r['job'].get('settings',{}).get('testbench')==bench['id']
            and r['job']['settings'].get('type') in kinds and not r['job'].get('case')]
    if not chosen:return state('Not run','No saved physical run' if physical else 'No saved electrical run')
    row=chosen[-1];current_hash=current_hash or design_digest(project)
    if design_digest(row['job']['project'])!=current_hash:
        return state('Stale','The design or testbench changed',run_id=row['id'])
    execution=run_state(row)
    if execution:return execution
    result=row['result']
    if result.get('design_hash')!=current_hash or result.get('project_id')!=project['id']:
        return state('Blocked','Result identity does not match its captured inputs',run_id=row['id'])
    if physical:
        report=result.get('silicon_report',{})
        if report.get('cell_id')!=bench['dut_cell']:
            return state('Blocked','Physical result belongs to a different circuit',run_id=row['id'])
        status={'passed':'Passed','failed':'Failed','blocked':'Blocked','running':'Running','not_run':'Not run'}.get(report.get('status'),'Blocked')
        return state(status,report.get('error') or 'DRC, LVS and extraction · '+status.lower(),run_id=row['id'])
    # Adapt a standalone bench to the same requirement evaluator without editing
    # the original run or inventing a persistent verification group.
    case=dict(group='workflow',kind='test_plan',entry_id=bench['id'],test_name=bench['name'],labels={})
    adapted={**row,'job':{**row['job'],'case':case}}
    return {**requirement_state([adapted],'workflow'),'run_id':row['id']}


def expected_cases(plan):
    """Exact condition identities, including trials and one-off digital tests."""
    statistics=plan.get('statistics');trials=range(1,statistics['count']+1) if statistics else (None,)
    # iter_prepare repeats digital entries per statistical realization too.
    for trial in trials:
        for entry in plan['entries']:
            conditions=[('RTL',None,None)] if entry['engine']=='digital' else itertools.product(
                plan['corners'],map(scalar,plan['temperatures']),map(scalar,plan.get('voltages',[])) if plan.get('voltages') else [None])
            for corner,temperature,voltage in conditions:
                labels=dict(corner=corner,temperature=temperature,voltage=voltage)
                if statistics:labels.update(trial=trial,seed=statistics['seed'])
                yield entry['id'],condition_key(labels)


def plan_status(project,plan,rows,current_hash=None):
    if plan is None:return state('Not run','Choose a saved verification plan')
    try:validate_plans({**project,'test_plans':[plan]})
    except (ValueError,KeyError,TypeError) as exc:return state('Blocked',str(exc))
    groups={}
    for row in rows:
        job=row.get('job',{});case=job.get('case',{})
        if job.get('project',{}).get('id')==project['id'] and case.get('kind')=='test_plan' and case.get('plan_id')==plan['id']:
            groups.setdefault(case['group'],[]).append(row)
    if not groups:return state('Not run',str(case_count(plan))+' cases have no saved run; open a campaign for external campaign evidence')
    group=list(groups)[-1];chosen=groups[group];current_hash=current_hash or design_digest(project)
    plan_hash=digest(plan);latest={}
    for row in chosen:
        job=row['job'];case=job['case']
        saved_plan=next((p for p in job['project'].get('test_plans',[]) if p['id']==plan['id']),None)
        recorded=case.get('plan_hash') or (digest(saved_plan) if saved_plan else None)
        if case.get('base_design_hash')!=current_hash or recorded!=plan_hash:
            return state('Stale','The design, requirements or operating conditions changed',group=group,plan_id=plan['id'])
        latest[(case['entry_id'],condition_key(case['labels']))]=row
    expected=set(expected_cases(plan))
    if set(latest)-expected:return state('Blocked','Saved run contains unexpected operating conditions',group=group,plan_id=plan['id'])
    unresolved=[]
    for row in latest.values():
        execution=run_state(row)
        if execution:unresolved.append(execution)
        elif (row['result'].get('project_id')!=project['id'] or
              row['result'].get('design_hash')!=design_digest(row['job']['project'])):
            unresolved.append(state('Blocked','Result identity does not match its captured inputs',run_id=row['id']))
    for status in ('Failed','Running','Blocked'):
        found=next((r for r in unresolved if r['status']==status),None)
        if found:return dict(found,group=group,plan_id=plan['id'])
    if set(latest)!=expected:
        return state('Blocked',f'{len(latest)} of {len(expected)} expected cases retained; rerun missing conditions',group=group,plan_id=plan['id'])
    result=requirement_state(list(latest.values()),group)
    if result['status']=='Passed':result['detail']=f'{len(expected)} of {len(expected)} cases passed every saved requirement'
    return dict(result,group=group,plan_id=plan['id'])
