"""Reusable multi-test plans and specification matrices over immutable jobs."""
import itertools
import math
from .model import clone, uid, scalar, digest, design_digest

MAX_PLAN_CASES = 10000
MAX_INTERACTIVE_CASES = 200


def case_count(plan):
    """Count the actual expansion; digital tests have no analog conditions."""
    analog = len(plan.get('corners', []))*len(plan.get('temperatures', []))*max(1,len(plan.get('voltages', [])))
    trials=(plan.get('statistics') or {}).get('count',1)
    return sum(1 if entry.get('engine') == 'digital' else analog*trials for entry in plan.get('entries', []))


def sources(project):
    entries=[]
    for t in project.get('testbenches',[]):
        entries.append(dict(id='bench:'+t['id'],name=t['name'],cell=t['bench_cell'],engine='ngspice',
                            settings={'type':'testbench','testbench':t['id']}))
    for i,s in enumerate(project.get('simulation_setups',[])):
        if s['settings']['type'] in ('op','tran','dc','ac','noise'):
            entries.append(dict(id='setup:'+str(i),name=s['name'],cell=s['cell'],engine=s['engine'],settings=clone(s['settings'])))
    from .digital_design import config
    for c in project['cells']:
        rtl=config(project,c['id'])
        if not rtl:continue
        cases=rtl.get('tests') or ([{'name':'Default test','testbench':rtl['testbench'],'simulator':'icarus'}] if rtl.get('testbench') else [])
        for index,case in enumerate(cases):
            entries.append(dict(id='digital:'+c['id']+':'+str(index),name=c['name']+' · '+case['name'],cell=c['id'],engine='digital',
                                settings={'type':'digital','stage':'simulate','digital_case':clone(case)}))
    return entries


def validate_plans(project):
    plans=project.get('test_plans',[]);names=set();ids=set();cells={c['id'] for c in project['cells']}
    if not isinstance(plans,list) or len(plans)>30:raise ValueError('Use at most 30 saved test plans.')
    for plan in plans:
        if not isinstance(plan.get('id'),str) or not plan['id'] or plan['id'] in ids:raise ValueError('Each test plan needs a unique identity.')
        ids.add(plan['id']);name=plan.get('name','').strip()
        if not 1<=len(name)<=100 or name.casefold() in names:raise ValueError('Test plan names must be unique and contain 1–100 characters.')
        names.add(name.casefold())
        variables=plan.get('variables',{})
        if not isinstance(variables,dict) or len(variables)>100 or set(variables)-set(project.get('parameters',{})):
            raise ValueError('Plan variables must refer to existing project design variables (at most 100).')
        from .design_ops import parameters
        parameters({**project.get('parameters',{}),**variables})
        if type(plan.get('compare_layout',False)) is not bool:raise ValueError('Choose whether to compare schematic and post-layout results.')
        entries=plan.get('entries',[])
        if not isinstance(entries,list) or not 1<=len(entries)<=30:raise ValueError('Choose 1–30 tests in a plan.')
        entry_ids=set()
        for entry in entries:
            if not isinstance(entry.get('id'),str) or not entry['id'] or entry['id'] in entry_ids:raise ValueError('Each plan test needs a unique identity.')
            entry_ids.add(entry['id'])
            if entry.get('cell') not in cells:raise ValueError('A saved test plan refers to a missing cell. Edit or delete the plan first.')
            if entry.get('engine') not in ('builtin','ngspice','digital'):raise ValueError('Unknown test plan engine.')
            settings=entry.get('settings',{})
            if entry.get('engine')=='digital':
                if variables:raise ValueError('Use a separate analog plan for analog design-variable overrides.')
                from .digital_design import config
                from .digital_regression import validate_tests
                if not config(project,entry['cell']):raise ValueError('A test plan references a cell without RTL.')
                if settings.get('type')!='digital' or settings.get('stage')!='simulate':raise ValueError('Digital plan entries must be simulation tests.')
                validate_tests([settings.get('digital_case',{})])
                if plan.get('compare_layout'):raise ValueError('Use a separate analog layout-comparison plan; RTL tests do not represent analog extracted simulation.')
                continue
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
        from .campaign_statistics import configuration
        configuration(project,plan)
        if case_count(plan)>MAX_PLAN_CASES:raise ValueError('A test plan supports at most 10,000 cases, including statistical trials; split larger plans.')


def prepare(project,plan,prepare_job):
    """Interactive jobs remain small; campaigns consume iter_prepare lazily."""
    if case_count(plan)>MAX_INTERACTIVE_CASES:
        raise ValueError('Plans above 200 cases need a resumable campaign. Choose Create campaign.')
    return list(iter_prepare(project,plan,prepare_job))


def iter_prepare(project,plan,prepare_job,group=None):
    """Expand shared seeded trials across all saved tests and PVT conditions."""
    from .campaign_statistics import configuration,samples
    from .analog_optimizer import set_target,get_target
    validate_plans({**project,'test_plans':[plan]})
    source=clone(project);source.setdefault('parameters',{}).update(clone(plan.get('variables',{})))
    spec=configuration(source,plan)
    if spec is None:
        yield from _iter_conditions(project,plan,prepare_job,group)
        return
    base=design_digest(project);group=group or uid();index=0
    conditions=clone(plan);conditions.pop('statistics',None);conditions['variables']={}
    for trial,changes in samples(source,plan,spec):
        sample=clone(source)
        for target,value in changes.items():set_target(sample,spec['cell'],target,value)
        for job in _iter_conditions(sample,conditions,prepare_job,group,invalid_base=source):
            for target,value in changes.items():
                if job.get('preparation_error'):break
                if not math.isclose(get_target(job['project'],spec['cell'],target),value,rel_tol=1e-12,abs_tol=1e-30):
                    raise ValueError('A PVT or plan override masks the statistical target '+target+'. Choose distinct PVT supply and statistical targets.')
            index+=1;case=job['case'];case.update(index=index,base_design_hash=base,variables=clone(plan.get('variables',{})))
            case['labels'].update(trial=trial,seed=spec['seed'])
            case['statistics']={k:clone(spec[k]) for k in ('kind','seed','cell','sampling','model','model_evidence','scope') if k in spec}
            case['statistics'].update(trial=trial,changes=clone(changes),configuration_hash=digest(spec))
            yield job


def _iter_conditions(project,plan,prepare_job,group=None,invalid_base=None):
    """Yield one immutable job at a time without building the Cartesian product."""
    from .studies import set_target, supply_targets
    from .pdks import model_lines
    from .model import validate
    validate_plans({**project,'test_plans':[plan]})
    group=group or uid();base=design_digest(project)
    conditions=itertools.chain.from_iterable(
        [(entry,'RTL',None,None)] if entry['engine']=='digital' else
        itertools.product([entry],plan['corners'],plan['temperatures'],plan.get('voltages') or [None])
        for entry in plan['entries'])
    for index,(entry,corner,temp,voltage) in enumerate(conditions,1):
        if entry['engine']=='digital':
            job=prepare_job(clone(entry['settings']),'digital',clone(project),entry['cell'])
            job['case']={'group':group,'index':index,'plan_id':plan['id'],'plan_name':plan['name'],
                'entry_id':entry['id'],'test_name':entry['name'],'kind':'test_plan','base_design_hash':base,
                'labels':{'corner':'RTL','temperature':None,'voltage':None}}
            job['case']['fingerprint']=digest({k:v for k,v in job.items() if k!='case'});yield job;continue
        p=clone(project);p.setdefault('parameters',{}).update(clone(plan.get('variables',{})));settings=clone(entry['settings']);temp=scalar(temp)
        from .native_spice import native
        if native(p):
            from .native_analysis import corner_sections
            if corner!='nominal' and corner not in corner_sections(p):raise ValueError('Undeclared embedded library corner: '+corner)
        else:model_lines(p['pdk'],corner)
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
        preparation_error=None
        try:validate(p)
        except ValueError as exc:
            if invalid_base is None:raise
            preparation_error='Invalid statistical realization: '+str(exc)+' Samples were not clipped or resampled.'
        # GUI preparation may validate the project while selecting its runner.
        # Use the nominal design for that selection, then retain the exact failed
        # realization. Workers reject the marker before executing any analysis.
        prepared_project=clone(invalid_base) if preparation_error else p
        job=prepare_job(settings,entry['engine'],prepared_project,entry['cell'])
        if preparation_error:
            job['project']=p;job['preparation_error']=preparation_error
        if settings['type']=='testbench':job['settings']['executable']=job['executable']
        job['case']={'group':group,'index':index,'plan_id':plan['id'],'plan_name':plan['name'],
                     'entry_id':entry['id'],'test_name':entry['name'],'kind':'test_plan','base_design_hash':base,
                     'variables':clone(plan.get('variables',{})),
                     'labels':{'corner':corner,'temperature':temp,'voltage':scalar(voltage) if voltage is not None else None}}
        job['case']['fingerprint']=digest({k:v for k,v in job.items() if k!='case'})
        yield job


def requirements(job):
    if job['settings']['type']=='digital':
        return [dict(name='Testbench execution',definition=digest(job['settings'].get('digital_case',{})),unit='',digital=True)]
    from .specifications import for_job
    rows=[dict(r,definition=digest(r)) for r in for_job(job)]
    key=job.get('settings',{}).get('testbench')
    bench=next((t for t in job['project'].get('testbenches',[]) if t['id']==key),None)
    if bench:
        from .saved_bench_diagnostics import MEASUREMENTS
        rows += [dict(m,definition=digest(m),measurement=True,unit=MEASUREMENTS.get(m['kind'],'A' if m['kind']=='current' else 'V' if m['kind'] in ('voltage','range') else 'Hz' if m['kind']=='frequency' else 's')) for m in bench.get('measurements',[])]
    if job['settings']['type']=='silicon':
        from .silicon_flow import STAGES
        if job['settings'].get('testbench'):
            from .hierarchical_flow import VERIFICATION_STAGES
            STAGES=VERIFICATION_STAGES
        rows=[dict(m,name=m['name']+' · '+stage,source_name=m['name'],stage=stage,definition=digest([m,stage]))
              for m in rows for stage in ('schematic','post-layout')]
        rows += [dict(name=stage.replace('_',' '),stage=stage,check=True,definition=digest(['physical stage',stage]),unit='') for stage in STAGES]
        rows += [dict(name='Physical workflow',stage='workflow',check=True,definition=digest(['physical workflow status']),unit='')]
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
        job=row['job'];case=job['case'];condition=condition_key(case['labels'])
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
            if spec.get('digital') and row.get('result',{}).get('result_type')=='digital':
                actual={'status':'passed','value':1}
            if spec.get('stage'):
                stage_name={'schematic':'schematic_simulation','post-layout':'post_layout_simulation'}.get(spec['stage'],spec['stage'])
                stage=next((s for s in physical.get('stages',[]) if s['name']==stage_name),{})
                actual=stage if spec.get('check') else next((m for m in stage.get('evidence',{}).get('measurements' if spec.get('measurement') else 'specifications',[]) if m['name']==spec['source_name']),None)
                if spec['stage']=='workflow':actual=physical
            state=row['state'].upper()
            if state=='COMPLETE':state='ERROR' if actual is None else {'passed':'PASS','failed':'FAIL','blocked':'FAIL','not_run':'NOT RUN','running':'RUNNING'}.get(actual.get('status'),actual.get('status','ERROR'))
            elif state in ('FAILED','CANCELLED'):state='ERROR' if state=='FAILED' else state
            item['values'][condition]=dict(status=state,value=actual.get('value') if actual else None,
                margin=actual.get('margin') if actual else None,detail=(actual or {}).get('error',row.get('log','')),
                run_id=row['id'],project_hash=design_digest(job['project']))
    return dict(conditions=conditions,rows=list(items.values()))


def condition_key(labels):
    base=tuple(labels.get(k) for k in ('corner','temperature','voltage'))
    return base+(labels['trial'],labels.get('seed')) if 'trial' in labels else base


def condition_name(condition):
    c,t,v=condition[:3]
    text='RTL simulation' if t is None else f'{c} / {t:g} °C'+(f' / {v:g} V' if v is not None else '')
    if len(condition)>3:text+=f' / trial {condition[3]} / seed {condition[4]}'
    return text


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
