"""Finite-difference sensitivity and bounded, reproducible parameter search."""
import itertools, math
from .model import scalar, design_digest


def cases(p,cid,spec):
    from .studies import get_target
    if spec['kind']=='sensitivity':
        targets=list(dict.fromkeys(spec['targets']))
        if not 1<=len(targets)<=100:raise ValueError('Choose 1–100 numeric sensitivity targets.')
        relative=scalar(spec.get('relative_step',.01));absolute=scalar(spec.get('absolute_step',1e-6))
        if not 0<relative<=.5 or absolute<=0:raise ValueError('Use a relative step above zero and at most 0.5, and a positive step for zero-valued parameters.')
        out=[({'role':'nominal'},{},{})]
        for target in targets:
            nominal=get_target(p,cid,target);step=abs(nominal)*relative if nominal else absolute
            for sign in (-1,1):out.append(({'target':target,'side':sign,'nominal':nominal,'step':step},{target:nominal+sign*step},{}))
        return out
    axes=spec.get('axes',[])
    if not 1<=len(axes)<=3 or len({a['target'] for a in axes})!=len(axes):raise ValueError('A bounded search supports 1–3 distinct parameter axes.')
    grids=[]
    for axis in axes:
        get_target(p,cid,axis['target']);lo,hi=scalar(axis['lower']),scalar(axis['upper']);count=int(axis['count'])
        if not lo<hi or not 2<=count<=500:raise ValueError('Each search axis needs increasing bounds and 2–500 samples.')
        grids.append([lo+(hi-lo)*i/(count-1) for i in range(count)])
    if math.prod(map(len,grids))>500:raise ValueError('The search must contain at most 500 cases.')
    if spec.get('goal','target') not in ('target','minimize','maximize'):raise ValueError('Choose a target, minimize or maximize objective.')
    scalar(spec.get('objective',0))
    return [({'candidate':i+1},dict(zip((a['target'] for a in axes),values)),{}) for i,values in enumerate(itertools.product(*grids))]


def evaluate(manifest,rows):
    from .variation_runs import latest
    current=latest(manifest,rows);spec=manifest['spec'];metric=spec.get('metric','');samples={}
    for job in manifest['jobs']:
        i=job['case']['index'];row=current.get(i,{})
        if row.get('state')!='Complete':continue
        results=row.get('result',{}).get('specifications',[])
        selected=next((r for r in results if r['name']==metric),None)
        if selected and selected.get('value') is not None and math.isfinite(selected['value']) and selected.get('status')!='ERROR':samples[i]=(selected['value'],all(r['status']=='PASS' for r in results))
    complete=len(samples)==len(manifest['jobs']);out={'complete':complete,'measured':len(samples),'total':len(manifest['jobs']),'metric':metric}
    if spec['kind']=='sensitivity':
        base=next((samples[j['case']['index']][0] for j in manifest['jobs'] if j['case']['labels'].get('role')=='nominal' and j['case']['index'] in samples),None);groups={}
        for job in manifest['jobs']:
            labels=job['case']['labels'];i=job['case']['index']
            if labels.get('target') and i in samples:groups.setdefault(labels['target'],{})[labels['side']]=(samples[i][0],labels)
        derivatives=[]
        for target,pair in groups.items():
            if set(pair)!={-1,1}:continue
            labels=pair[1][1];slope=(pair[1][0]-pair[-1][0])/(2*labels['step'])
            derivatives.append({'target':target,'derivative':slope,'normalized':slope*labels['nominal']/base if base else None,'step':labels['step']})
        out.update(nominal=base,sensitivities=derivatives)
    else:
        goal=spec.get('goal','target');objective=scalar(spec.get('objective',0));candidates=[]
        for job in manifest['jobs']:
            i=job['case']['index']
            if i not in samples or not samples[i][1]:continue
            value=samples[i][0];score=abs(value-objective) if goal=='target' else value if goal=='minimize' else -value
            candidates.append({'case':i,'value':value,'score':score,'changes':job['case']['changes']})
        out['best']=min(candidates,key=lambda r:(r['score'],r['case'])) if candidates else None
    return out


def apply_best(project,manifest,rows):
    from .studies import set_target
    if design_digest(project)!=manifest['base_design_hash']:raise ValueError('The circuit changed after this search was planned. Run a new search for the current design.')
    report=evaluate(manifest,rows)
    if not report['complete'] or not report.get('best'):raise ValueError('Finish every search case with valid measurements and at least one passing candidate before applying values.')
    cid=manifest['jobs'][0]['cell']
    for target,value in report['best']['changes'].items():set_target(project,cid,target,value)
    return report['best']
