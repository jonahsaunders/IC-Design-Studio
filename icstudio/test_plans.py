"""Reusable multi-test plans and specification matrices over immutable jobs."""
import itertools
from .model import clone, uid, scalar, digest, design_digest


def sources(project):
    entries=[]
    for t in project.get('testbenches',[]):
        entries.append(dict(id='bench:'+t['id'],name=t['name'],cell=t['bench_cell'],engine='ngspice',
                            settings={'type':'testbench','testbench':t['id']}))
    for i,s in enumerate(project.get('simulation_setups',[])):
        if s['settings']['type'] in ('op','tran','dc','ac','noise'):
            entries.append(dict(id='setup:'+str(i),name=s['name'],cell=s['cell'],engine=s['engine'],settings=clone(s['settings'])))
    return entries


def validate_plans(project):
    plans=project.get('test_plans',[]);names=set();ids=set();cells={c['id'] for c in project['cells']}
    if not isinstance(plans,list) or len(plans)>30:raise ValueError('Use at most 30 saved test plans.')
    for plan in plans:
        if not isinstance(plan.get('id'),str) or not plan['id'] or plan['id'] in ids:raise ValueError('Each test plan needs a unique identity.')
        ids.add(plan['id']);name=plan.get('name','').strip()
        if not 1<=len(name)<=100 or name.casefold() in names:raise ValueError('Test plan names must be unique and contain 1–100 characters.')
        names.add(name.casefold())
        if type(plan.get('compare_layout',False)) is not bool:raise ValueError('Choose whether to compare schematic and post-layout results.')
        entries=plan.get('entries',[])
        if not isinstance(entries,list) or not 1<=len(entries)<=30:raise ValueError('Choose 1–30 tests in a plan.')
        entry_ids=set()
        for entry in entries:
            if not isinstance(entry.get('id'),str) or not entry['id'] or entry['id'] in entry_ids:raise ValueError('Each plan test needs a unique identity.')
            entry_ids.add(entry['id'])
            if entry.get('cell') not in cells:raise ValueError('A saved test plan refers to a missing cell. Edit or delete the plan first.')
            if entry.get('engine') not in ('builtin','ngspice'):raise ValueError('Unknown test plan engine.')
            settings=entry.get('settings',{})
            if settings.get('type') not in ('op','tran','dc','ac','noise','testbench'):raise ValueError('Unsupported analysis in test plan.')
            if plan.get('compare_layout') and settings.get('type')!='testbench':raise ValueError('Layout comparison requires saved testbenches for every selected test.')
            if settings['type']=='testbench':
                bench=next((t for t in project.get('testbenches',[]) if t['id']==settings.get('testbench')),None)
                if bench is None or bench['bench_cell']!=entry['cell']:raise ValueError('A saved test plan refers to a missing or changed testbench.')
        corners=plan.get('corners',[]);temperatures=plan.get('temperatures',[]);voltages=plan.get('voltages',[])
        if not corners or any(not isinstance(c,str) or not c.strip() or len(c)>100 for c in corners):raise ValueError('Enter model corner names.')
        if len(set(corners))!=len(corners):raise ValueError('Model corners must be unique.')
        if not temperatures or any(scalar(t)<=-273.15 for t in temperatures):raise ValueError('Temperatures must exceed absolute zero.')
        for v in voltages:scalar(v)
        if len({scalar(t) for t in temperatures})!=len(temperatures) or len({scalar(v) for v in voltages})!=len(voltages):
            raise ValueError('Temperatures and supply voltages must be unique.')
        if len(entries)*len(corners)*len(temperatures)*max(1,len(voltages))>200:raise ValueError('A test plan supports at most 200 cases.')


def prepare(project,plan,prepare_job):
    from .studies import set_target, supply_targets
    from .pdks import model_lines
    from .model import validate
    validate_plans({**project,'test_plans':[plan]})
    group=uid();jobs=[];base=design_digest(project)
    for entry,corner,temp,voltage in itertools.product(plan['entries'],plan['corners'],plan['temperatures'],plan.get('voltages') or [None]):
        p=clone(project);settings=clone(entry['settings']);temp=scalar(temp)
        model_lines(p['pdk'],corner)
        for target,value in p['pdk'].get('corners',{}).get(corner,{}).get('overrides',{}).items():set_target(p,entry['cell'],target,value)
        if voltage is not None:
            target=entry.get('supply','')
            if target not in supply_targets(p,entry['cell']):raise ValueError(entry['name']+': choose its DC supply target before sweeping voltages.')
            set_target(p,entry['cell'],target,voltage)
        settings.update(corner=corner,temperature=temp)
        if settings['type']=='testbench':
            bench=next(t for t in p['testbenches'] if t['id']==settings['testbench'])
            bench['analysis'].update(corner=corner,temperature=temp)
            if plan.get('compare_layout'):settings['type']='silicon'
        validate(p)
        job=prepare_job(settings,entry['engine'],p,entry['cell'])
        if settings['type']=='testbench':job['settings']['executable']=job['executable']
        job['case']={'group':group,'index':len(jobs)+1,'plan_id':plan['id'],'plan_name':plan['name'],
                     'entry_id':entry['id'],'test_name':entry['name'],'kind':'test_plan','base_design_hash':base,
                     'labels':{'corner':corner,'temperature':temp,'voltage':scalar(voltage) if voltage is not None else None}}
        job['case']['fingerprint']=digest({k:v for k,v in job.items() if k!='case'})
        jobs.append(job)
    return jobs


def requirements(job):
    from .specifications import for_job
    rows=[dict(r,definition=digest(r)) for r in for_job(job)]
    key=job.get('settings',{}).get('testbench')
    bench=next((t for t in job['project'].get('testbenches',[]) if t['id']==key),None)
    if bench:
        rows += [dict(m,definition=digest(m),measurement=True,unit='A' if m['kind']=='current' else 'V' if m['kind'] in ('voltage','range') else 'Hz' if m['kind']=='frequency' else 's') for m in bench.get('measurements',[])]
    if job['settings']['type']=='silicon':
        from .silicon_flow import STAGES
        rows=[dict(m,name=m['name']+' · '+stage,source_name=m['name'],stage=stage,definition=digest([m,stage]))
              for m in rows if m.get('measurement') for stage in ('schematic','post-layout')]
        rows += [dict(name=stage.replace('_',' '),stage=stage,check=True,definition=digest(['physical stage',stage]),unit='') for stage in STAGES]
    return rows


def matrix(rows,group):
    """Missing/error runs stay visible; comparisons require identical definitions."""
    if not group:return dict(conditions=[],rows=[])
    chosen={}
    for row in rows:
        case=row['job'].get('case',{})
        if case.get('kind')=='test_plan' and case.get('group')==group:chosen[(case['entry_id'],digest(case['labels']))]=row
    conditions=[];items={}
    for row in chosen.values():
        job=row['job'];case=job['case'];condition=tuple(case['labels'].get(k) for k in ('corner','temperature','voltage'))
        if condition not in conditions:conditions.append(condition)
        expected=requirements(job)
        if not expected:expected=[dict(name='No saved requirements',definition='missing',unit='')]
        specs=row.get('result',{}).get('specifications',[])
        measurements=row.get('result',{}).get('measurements',{}).get('measurements',[])
        physical=row.get('result',{}).get('silicon_report',{})
        for spec in expected:
            key=(case['entry_id'],spec['name'],spec['definition'],bool(spec.get('measurement')))
            item=items.setdefault(key,dict(key=key,test=case['test_name'],name=spec['name'],unit=spec.get('unit',''),definition=spec,values={}))
            results=measurements if spec.get('measurement') else specs
            actual=next((r for r in results if r['name']==spec['name']),None)
            if spec.get('stage'):
                stage_name={'schematic':'schematic_simulation','post-layout':'post_layout_simulation'}.get(spec['stage'],spec['stage'])
                stage=next((s for s in physical.get('stages',[]) if s['name']==stage_name),{})
                actual=stage if spec.get('check') else next((m for m in stage.get('evidence',{}).get('measurements',[]) if m['name']==spec['source_name']),None)
            state=row['state'].upper()
            if state=='COMPLETE':state='ERROR' if actual is None else {'passed':'PASS','failed':'FAIL','not_run':'NOT RUN','running':'RUNNING'}.get(actual.get('status'),actual.get('status','ERROR'))
            elif state in ('FAILED','CANCELLED'):state='ERROR' if state=='FAILED' else state
            item['values'][condition]=dict(status=state,value=actual.get('value') if actual else None,
                margin=actual.get('margin') if actual else None,detail=(actual or {}).get('error',row.get('log','')),
                run_id=row['id'],project_hash=design_digest(job['project']))
    return dict(conditions=conditions,rows=list(items.values()))


def compare(current,baseline):
    by={r['key']:r for r in baseline['rows']};out=clone(current)
    for row in out['rows']:
        old=by.get(row['key'])
        if not old or old['unit']!=row['unit']:continue
        for condition,cell in row['values'].items():
            before=old['values'].get(condition)
            if before and cell['value'] is not None and before['value'] is not None:
                cell['baseline']=before['value'];cell['delta']=cell['value']-before['value']
                cell['regressed']=before['status']=='PASS' and cell['status']=='FAIL'
    return out
