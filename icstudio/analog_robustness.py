"""Bounded environmental search and explicit correlated variation experiments."""
import math
import random
from .model import clone, scalar, design_digest, digest
from . import analog_optimizer as opt


def nominal(project, cid, plan, target):
    if target=='temperature':return scalar(plan['temperatures'][0])
    if target=='supply':
        if plan.get('voltages'):return scalar(plan['voltages'][0])
        entry=plan['entries'][0]
        if not entry.get('supply'):raise ValueError('Select a DC supply target for every plan entry before varying supply.')
        return opt.get_target(project,entry['cell'],entry['supply'])
    return opt.get_target(project,cid,target)


def validate_variables(project, cid, plan, variables, method):
    targets=[v['target'] for v in variables]
    if not 1<=len(targets)<=8 or len(set(targets))!=len(targets):raise ValueError('Choose one to eight distinct uncertain parameters.')
    for v in variables:
        target=v['target']
        if target.rsplit('.',1)[-1].lower() in ('nf','m','mult'):raise ValueError('Continuous robustness sampling does not support integer finger/multiplicity parameters. Use an integer circuit search.')
        if target not in ('temperature','supply') and target not in opt.targets(project,cid):raise ValueError('Unknown uncertain parameter: '+target)
        mean=nominal(project,cid,plan,target)
        if method=='worst':
            lo,hi=scalar(v['lower']),scalar(v['upper'])
            if not lo<hi:raise ValueError('Worst-case bounds must increase.')
            if target=='temperature' and lo<=-273.15:raise ValueError('Temperature must exceed absolute zero.')
        else:
            sigma=scalar(v.get('absolute_sigma',0)) or abs(mean)*scalar(v.get('relative_sigma',0))
            if sigma<=0:raise ValueError('Every variation needs a positive absolute or relative standard deviation.')
            if v.get('distribution','normal') not in ('normal','uniform'):raise ValueError('Choose normal or uniform variation.')
            rho=scalar(v.get('rho',1 if v.get('group') else 0))
            if not -1<=rho<=1 or (rho and not v.get('group')):raise ValueError('Shared normal factors need a group and a correlation loading in [-1, 1].')
            if v.get('distribution','normal')=='uniform' and v.get('group'):raise ValueError('Shared factors currently support normal distributions. Uniform variations are independent.')


def draw(project, cid, plan, variables, count, seed, method, center=None):
    rng=random.Random(int(seed)); output=[]
    if method=='worst':
        d=len(variables); coords=[]
        if center is None:
            baseline=[max(0,min(1,(nominal(project,cid,plan,v['target'])-scalar(v['lower']))/(scalar(v['upper'])-scalar(v['lower'])))) for v in variables]
            coords.append(baseline)
            for axis in range(d):
                for value in (0.,1.):coords.append(baseline[:axis]+[value]+baseline[axis+1:])
        else:
            base=[(center[v['target']]-scalar(v['lower']))/(scalar(v['upper'])-scalar(v['lower'])) for v in variables]
            for _ in range(max(1,count//2)):coords.append([max(0,min(1,x+rng.uniform(-.2,.2))) for x in base])
        # Stratified global coverage remains present during refinement.
        remaining=max(0,count-len(coords));columns=[]
        for _ in variables:
            column=[(i+rng.random())/max(1,remaining) for i in range(remaining)];rng.shuffle(column);columns.append(column)
        coords.extend([list(p) for p in zip(*columns)])
        return [{v['target']:scalar(v['lower'])+x*(scalar(v['upper'])-scalar(v['lower'])) for v,x in zip(variables,p)} for p in coords[:count]]
    return list(iter_tolerance(project,cid,plan,variables,count,seed))


def iter_tolerance(project,cid,plan,variables,count,seed):
    """Stream the same seeded shared-factor draws used by robustness studies."""
    rng=random.Random(int(seed))
    for _ in range(count):
        shared={v['group']:rng.gauss(0,1) for v in variables if v.get('group')};point={}
        for v in variables:
            mean=nominal(project,cid,plan,v['target']);sigma=scalar(v.get('absolute_sigma',0)) or abs(mean)*scalar(v.get('relative_sigma',0))
            if v.get('distribution','normal')=='uniform':z=rng.uniform(-math.sqrt(3),math.sqrt(3))
            else:
                rho=scalar(v.get('rho',1 if v.get('group') else 0))
                z=rho*shared.get(v.get('group'),0)+math.sqrt(max(0,1-rho*rho))*rng.gauss(0,1)
            point[v['target']]=mean+sigma*z
        yield point


def batch(project, cid, plan, spec, scenarios, prepare_job):
    jobs=[]; first=None
    for candidate, changes in enumerate(scenarios,1):
        q=clone(project); p=clone(plan)
        for target,value in changes.items():
            if target=='temperature':p['temperatures']=[value]
            elif target=='supply':p['voltages']=[value]
            else:opt.set_target(q,cid,target,value)
        try:part=opt.prepare(q,cid,p,spec,prepare_job,_changes=[{}])
        except (ValueError,KeyError) as exc:raise ValueError(f'Variation sample {candidate} is invalid ({changes}): {exc}. Samples were not clipped or resampled.') from exc
        if first is None:first=part
        for job in part['jobs']:
            for target,value in changes.items():
                if target not in ('temperature','supply') and not math.isclose(opt.get_target(job['project'],cid,target),value,rel_tol=1e-12,abs_tol=1e-30):
                    raise ValueError('A plan override masks the uncertain parameter '+target)
            job['case'].update(group=first['id'],index=len(jobs)+1,candidate=candidate,changes=clone(changes),base_design_hash=design_digest(project))
            job['case']['labels']['sample']=candidate;jobs.append(job)
            if len(jobs)>int(spec['budget']):raise ValueError('Variation cases exceed the simulation budget. Reduce samples or PVT conditions.')
    first.update(jobs=jobs,base_design_hash=design_digest(project));return first


def prepare(project, cid, plan, spec, prepare_job, variables, method='worst', count=20, seed=1, model=None, validation_of=None):
    if plan.get('statistics'):raise ValueError('This plan already defines statistical trials. Run its durable campaign, or use a plan without trials for a separate robustness study.')
    if method not in ('worst','tolerance','statistical'):raise ValueError('Choose worst conditions, declared tolerances, or a validated statistical model.')
    variables=clone(variables);evidence=None
    if method=='statistical':
        declared=project['pdk'].get('statistical_models',{}).get(model,{})
        if not declared.get('validated') or not declared.get('evidence') or not declared.get('variations'):
            raise ValueError('Choose a validated statistical model with evidence and explicit numeric mappings from this PDK.')
        variables=clone(declared['variations']);evidence=clone(declared)
    validate_variables(project,cid,plan,variables,method)
    count=int(count)
    if not 4<=count<=500:raise ValueError('Use 4–500 robustness samples within the job budget.')
    if method=='worst' and count<2*len(variables)+1:raise ValueError('Worst-condition search needs a baseline and two boundary probes per uncertain parameter.')
    spec=clone(spec);spec.update(strategy='grid',screen_op=False);spec.pop('fidelity',None);spec.pop('workflow',None)
    initial=min(count,max(2*len(variables)+1,8)) if method=='worst' else count
    scenarios=draw(project,cid,plan,variables,initial,seed,method)
    m=batch(project,cid,plan,spec,scenarios,prepare_job)
    per_case=len(m['jobs'])//initial
    if count*per_case>int(spec['budget']):raise ValueError(f'{count} samples need {count*per_case} jobs. Increase the budget or reduce samples/PVT conditions.')
    from .test_plans import requirements
    if not any(r.get('min') not in (None,'') or r.get('max') not in (None,'') for j in m['jobs'] for r in requirements(j)):raise ValueError('Save scalar or testbench measurement limits before a robustness study.')
    m['name']={'worst':'Worst conditions','tolerance':'Declared tolerances','statistical':'Statistical verification'}[method]+' · '+plan['name']
    m['advanced']=dict(kind='robustness',method=method,variables=variables,count=count,seed=int(seed),model=model,
        model_evidence=evidence,validation_of=validation_of,project=clone(project),source_plan=clone(plan),scenarios=scenarios,round=0,done=initial==count)
    return m


def advance(manifest, rows, prepare_job):
    m=clone(manifest);meta=m['advanced'];result=opt.evaluate(m,rows)
    if meta['method']!='worst' or meta['done'] or not m.get('execution_active') or not result['batch_complete']:return m,[]
    valid=[c for c in result['candidates'] if c['constraints'] and not c['evidence_errors']]
    if not valid:
        m['execution_active']=False;meta['pause_reason']='No valid requirement evidence for worst-condition refinement.';return m,[]
    worst=max(valid,key=lambda c:max(c['constraints'].values()));center=meta['scenarios'][worst['candidate']-1]
    count=min(4,meta['count']-len(meta['scenarios']));meta['round']+=1
    scenarios=draw(meta['project'],m['cell_id'],meta['source_plan'],meta['variables'],count,meta['seed']+7919*meta['round'],'worst',center)
    part=batch(meta['project'],m['cell_id'],meta['source_plan'],m['spec'],scenarios,prepare_job);offset=len(meta['scenarios'])
    for i,job in enumerate(part['jobs'],len(m['jobs'])+1):
        original=next(j for j in m['jobs'] if j['case']['entry_id']==job['case']['entry_id'])
        if original['environment']!=job['environment']:raise ValueError('Simulation environment changed during worst-condition search.')
        job['case'].update(group=m['id'],index=i,candidate=job['case']['candidate']+offset)
        job['case']['labels']['sample']=job['case']['candidate']
    m['jobs'].extend(part['jobs']);meta['scenarios'].extend(scenarios);meta['done']=len(meta['scenarios'])==meta['count']
    return m,part['jobs']


def wilson(passed, total):
    if not total:return None
    z=1.959963984540054;p=passed/total;den=1+z*z/total
    center=(p+z*z/(2*total))/den;half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [max(0,center-half),min(1,center+half)]


def analyze(manifest, rows):
    result=opt.evaluate(manifest,rows);meta=manifest['advanced'];complete=result['complete'] and meta['done']
    known=[c for c in result['candidates'] if c['complete']==c['total'] and not c['evidence_errors']]
    passed=sum(c['state']=='Passed' for c in known);failed=len(known)-passed;unknown=meta['count']-len(known)
    worst=max((c for c in known if c['constraints']),key=lambda c:max(c['constraints'].values()),default=None)
    statistical=meta['method']!='worst'
    scope=('Validated PDK statistical model: '+str(meta['model']) if meta['method']=='statistical' else
           'User-declared tolerances; this is not foundry manufacturing yield.' if statistical else
           'Worst measured condition in bounded exploration; this is not proof of the global worst case.')
    return dict(scope=scope,complete=complete,passed=passed,failed=failed,unresolved=unknown,samples=meta['count'],seed=meta['seed'],
        pass_fraction=passed/meta['count'] if complete and unknown==0 and statistical else None,
        confidence_95=wilson(passed,meta['count']) if complete and unknown==0 and statistical else None,
        worst_candidate=worst['candidate'] if worst else None,worst_conditions=worst['changes'] if worst else None,
        validation_of=meta.get('validation_of'),candidates=result['candidates'])
