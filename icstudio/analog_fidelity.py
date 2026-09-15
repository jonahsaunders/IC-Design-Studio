"""Coarse/full SPICE promotion with learned discrepancy and measured finalists."""
import math
import random
from .model import clone, scalar
from . import analog_optimizer as opt, analog_adaptive as adaptive


def coarse_inputs(project,plan,factor):
    q=clone(project);p=clone(plan);changed=False
    for entry in p['entries']:
        s=entry['settings']
        if s['type']=='testbench':s=next(t['analysis'] for t in q['testbenches'] if t['id']==s['testbench'])
        if s['type'] in ('ac','noise'):
            old=int(s['points']);s['points']=max(2,int(old/factor));changed|=old!=s['points']
        elif s['type']=='tran':
            old=scalar(s['step']);s['step']=min(scalar(s['stop']),old*factor);changed|=old!=s['step']
    if not changed:raise ValueError('Model fidelity needs an AC, noise or transient analysis whose sampling resolution can be reduced.')
    return q,p


def level_manifest(m,level):
    return {k:v for k,v in {**m,'jobs':[j for j in m['jobs'] if j['case']['fidelity']['level']==level]}.items() if k!='adaptive'}


def append(m,part,level,ids):
    per=len(part['jobs'])//len(ids);jobs=[]
    for job in part['jobs']:
        candidate=ids[job['case']['candidate']-1]
        job['case'].update(group=m['id'],index=len(m['jobs'])+len(jobs)+1,candidate=candidate,fidelity={'level':level})
        jobs.append(job)
    if len(jobs)!=per*len(ids):raise ValueError('Incomplete fidelity batch.')
    m['jobs'].extend(jobs);return jobs


def prepare(project,cid,plan,spec,prepare_job,pool=12,finalists=6,factor=4,seed=1):
    pool,finalists,factor=int(pool),int(finalists),scalar(factor)
    if not 3<=finalists<=pool<=100 or not 2<=factor<=20:raise ValueError('Use 3–100 full candidates, at least as many coarse candidates, and a resolution factor from 2 to 20.')
    if any(e['engine']!='ngspice' for e in plan['entries']):raise ValueError('Both fidelity levels require ngspice and the same circuit/model family.')
    per=len(plan['entries'])*len(plan['corners'])*len(plan['temperatures'])*max(1,len(plan.get('voltages',[])))
    if (pool+finalists)*per>int(spec['budget']):raise ValueError(f'This study reserves {(pool+finalists)*per} simulations, including all full-resolution conditions. Increase the budget or reduce candidates.')
    spec=clone(spec);spec.update(strategy='grid',screen_op=False);spec.pop('workflow',None)
    grids=adaptive.axes(project,cid,spec);sizes=list(map(len,grids));rng=random.Random(int(seed));coords=[[(n-1)//2 for n in sizes]]
    if math.prod(sizes)<pool:raise ValueError('Increase parameter Samples to provide enough distinct coarse candidates.')
    seen={tuple(coords[0])}
    while len(coords)<pool:
        point=tuple(rng.randrange(n) for n in sizes)
        if point not in seen:seen.add(point);coords.append(list(point))
    changes=[adaptive.delta(grids,c) for c in coords];q,p=coarse_inputs(project,plan,factor)
    coarse=opt.prepare(q,cid,p,spec,prepare_job,_changes=changes)
    full=opt.prepare(project,cid,plan,spec,prepare_job,_changes=changes[:3])
    m={**full,'jobs':[]};append(m,coarse,'coarse',list(range(1,pool+1)));append(m,full,'full',[1,2,3])
    m['name']='Coarse/full SPICE · '+plan['name'];m['advanced']=dict(kind='fidelity',project=clone(project),source_plan=clone(plan),coordinates=coords,
        changes=changes,grids=sizes,pool=pool,finalists=finalists,factor=factor,seed=int(seed),promoted=[1,2,3],done=finalists==3,predictions=[])
    return m


def valid(c):return c['complete']==c['total'] and not c['evidence_errors'] and all(v['score'] is not None for v in c['metrics'])


def predict(m,rows):
    from .analog_bayesian import FittedGP
    meta=m['advanced'];coarse=opt.evaluate(level_manifest(m,'coarse'),rows);full=opt.evaluate(level_manifest(m,'full'),rows)
    cheap={c['candidate']:c for c in coarse['candidates'] if valid(c)};fine={c['candidate']:c for c in full['candidates'] if valid(c)}
    paired=sorted(set(cheap)&set(fine))[-32:]
    remaining=[i for i in range(1,meta['pool']+1) if i not in meta['promoted']]
    if len(paired)<3:return [dict(candidate=i,method='Uncalibrated full-resolution exploration',score=0) for i in remaining]
    feature=lambda i:[v/(n-1) for v,n in zip(meta['coordinates'][i-1],meta['grids'])]
    x=[feature(i) for i in paired];objectives=opt.objectives(m['spec'])
    models=[FittedGP(x,[fine[i]['metrics'][j]['score']-cheap[i]['metrics'][j]['score'] for i in paired]) for j in range(len(objectives))]
    keys=set.intersection(*(set(fine[i]['constraints'])&set(cheap[i]['constraints']) for i in paired))
    keys=sorted(keys,key=lambda k:max(fine[i]['constraints'][k] for i in paired),reverse=True)[:6]
    constraints=[FittedGP(x,[fine[i]['constraints'][k]-cheap[i]['constraints'][k] for i in paired]) for k in keys]
    scales=[max(max(fine[i]['metrics'][j]['score'] for i in paired)-min(fine[i]['metrics'][j]['score'] for i in paired),abs(fine[paired[0]]['metrics'][j]['score'])*.01,1e-30) for j in range(len(objectives))]
    output=[]
    for i in remaining:
        if i not in cheap:
            output.append(dict(candidate=i,method='Coarse evidence unavailable; verify with full SPICE',score=math.inf));continue
        values=[g.predict(feature(i)) for g in models];means=[cheap[i]['metrics'][j]['score']+v[0] for j,v in enumerate(values)]
        limits=[cheap[i]['constraints'][k]+g.predict(feature(i))[0] for k,g in zip(keys,constraints)]
        score=sum((mu-1.5*v[1])/s for mu,v,s in zip(means,values,scales))/len(scales)+10*sum(max(0,v) for v in limits)
        output.append(dict(candidate=i,method='GP correction of coarse SPICE scores',predicted_scores=means,standard_deviations=[v[1] for v in values],score=score,
            paired_observations=len(paired),modeled_constraints=keys,note='Promotion estimate only. All full-resolution saved conditions and limits are required for acceptance.'))
    # Keep reports strict JSON, including candidates with missing coarse data.
    for p in output:
        if not math.isfinite(p['score']):p['score']=1e100
    return sorted(output,key=lambda p:(p['score'],p['candidate']))


def advance(manifest,rows,prepare_job):
    m=clone(manifest);meta=m['advanced']
    if meta['done'] or not m.get('execution_active'):return m,[]
    if not all(opt.evaluate(level_manifest(m,l),rows)['batch_complete'] for l in ('coarse','full')):return m,[]
    proposals=predict(m,rows)
    if not proposals:meta['done']=True;return m,[]
    proposal=proposals[0];i=proposal['candidate'];part=opt.prepare(meta['project'],m['cell_id'],meta['source_plan'],m['spec'],prepare_job,_changes=[meta['changes'][i-1]])
    for job in part['jobs']:
        original=next(j for j in m['jobs'] if j['case']['fidelity']['level']=='full' and j['case']['entry_id']==job['case']['entry_id'])
        if job['environment']!=original['environment']:raise ValueError('Simulation environment changed; the fidelity study is paused.')
    jobs=append(m,part,'full',[i])
    for job in jobs:job['case']['fidelity']['proposal']=clone(proposal)
    meta['promoted'].append(i);meta['predictions'].append(proposal);meta['done']=len(meta['promoted'])>=meta['finalists']
    return m,jobs


def analyze(m,rows):
    coarse=opt.evaluate(level_manifest(m,'coarse'),rows);fine=opt.evaluate(level_manifest(m,'full'),rows)
    return dict(scope='Coarse and full numerical SPICE resolution with identical device models. Full saved PVT conditions determine passing finalists; this does not include extracted-layout signoff.',
        complete=m['advanced']['done'] and coarse['complete'] and fine['complete'],coarse_candidates=coarse['candidates'],full_candidates=fine['candidates'],
        pareto=fine['pareto'],predictions=m['advanced']['predictions'],full_resolution_plan=m['advanced']['source_plan'])


def apply_candidate(project,m,rows,candidate):
    if not analyze(m,rows)['complete']:raise ValueError('Finish the full-resolution validation before applying a finalist.')
    full=clone(level_manifest(m,'full'));full.pop('advanced',None)
    return opt.apply_candidate(project,full,rows,candidate)
