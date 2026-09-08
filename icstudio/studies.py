"""Reproducible parameter, PVT and explicitly declared tolerance studies."""
from __future__ import annotations
import itertools, math, random, statistics
from pathlib import Path
from .model import clone, scalar, flatten, validate, digest, design_digest, now
from .build_info import WORKFLOW_SOURCE_HASH

METRICS=('final','min','max','mean','rms','peak_to_peak','peak_x')

def measure(result, trace, metric='final'):
    if metric not in METRICS: raise ValueError('Unknown measurement: '+metric)
    if trace not in result['traces']: raise ValueError('Unknown measurement trace: '+trace)
    ys=result['traces'][trace]
    if not ys: raise ValueError('The selected trace is empty.')
    if metric=='final': return ys[-1]
    if metric=='min': return min(ys)
    if metric=='max': return max(ys)
    if metric=='mean': return statistics.fmean(ys)
    if metric=='rms': return math.sqrt(statistics.fmean(v*v for v in ys))
    if metric=='peak_to_peak': return max(ys)-min(ys)
    return result['x'][max(range(len(ys)),key=lambda i:abs(ys[i]))]

def set_target(p, cid, target, value):
    """Targets are active-cell instance names followed by an allowed field."""
    parts=target.split('.')
    if len(parts)<2: raise ValueError('Use a target such as R1.value or MN1.params.w.')
    cell=next(c for c in p['cells'] if c['id']==cid)
    d=next((d for d in cell['devices'] if d['name']==parts[0]),None)
    if d is None: raise ValueError('Target device not found: '+parts[0])
    field='.'.join(parts[1:])
    if field=='value' and d['kind'] in ('R','C','L','V','I'):
        if d['kind'] in ('V','I') and d['source']['type']!='dc':raise ValueError('A pulsed source uses source.high or source.low; its DC value is inactive.')
        d['value']=str(scalar(value))
    elif len(parts)==3 and parts[1] in ('params','source') and parts[2] in d.get(parts[1],{}) and parts[2]!='type': d[parts[1]][parts[2]]=str(scalar(value))
    else: raise ValueError('Unsupported numeric target: '+target)

def get_target(p,cid,target):
    parts=target.split('.');cell=next(c for c in p['cells'] if c['id']==cid)
    d=next(d for d in cell['devices'] if d['name']==parts[0])
    from .design_ops import resolved_device,parameters
    d=resolved_device(d,parameters(cell.get('parameters',{}),parameters(p.get('parameters',{}))))
    for key in parts[1:]: d=d[key]
    return scalar(d)

def cases(p,cid,spec):
    kind=spec.get('kind','sweep');out=[]
    if kind=='sweep':
        values=spec.get('values',[])
        if not values or len(values)>500: raise ValueError('Enter 1–500 sweep values.')
        out=[({'value':scalar(v)}, {spec['target']:scalar(v)}, {}) for v in values]
    elif kind=='pvt':
        parts=spec['target'].split('.')
        supply=next((d for c in p['cells'] if c['id']==cid for d in c['devices'] if d['name']==parts[0]),None)
        if not supply or supply['kind']!='V' or supply['source']['type']!='dc' or parts[1:]!=['value']:raise ValueError('PVT voltage sweeps require a DC voltage source target, such as VDD.value.')
        corners=spec.get('corners',['nominal']);volts=spec.get('voltages',[1.8]);temps=spec.get('temperatures',[27])
        if not corners or not volts or not temps or len(corners)*len(volts)*len(temps)>500: raise ValueError('PVT requires 1–500 combinations.')
        for corner,v,t in itertools.product(corners,volts,temps):
            config=p['pdk'].get('corners',{}).get(corner)
            sections=[item['sections'] for item in p['pdk'].get('simulation',{}).get('includes',[]) if item.get('sections')]
            model_corner=bool(sections) and all(corner in mapping for mapping in sections)
            if (sections and not model_corner) or (corner!='nominal' and config is None and not model_corner): raise ValueError('Corner is not declared by the active technology: '+corner)
            t=scalar(t)
            if t<=-273.15: raise ValueError('Temperature must exceed absolute zero.')
            changes=clone((config or {}).get('overrides',{}));changes[spec['target']]=scalar(v)
            out.append(({'corner':corner,'voltage':scalar(v),'temperature':t},changes,{'temperature':t,'corner':corner}))
    elif kind=='monte_carlo':
        count=int(spec.get('count',50));seed=int(spec.get('seed',1));variations=spec.get('variations',[])
        if not 2<=count<=500 or not variations: raise ValueError('Monte Carlo requires 2–500 trials and explicit component tolerances.')
        rng=random.Random(seed)
        for trial in range(count):
            changes={}
            for v in variations:
                sigma=scalar(v['relative_sigma']);dist=v.get('distribution','normal');target=v['target']
                if not 0<sigma<1 or dist not in ('normal','uniform'): raise ValueError('Tolerance sigma must be between 0 and 1; choose normal or uniform.')
                nominal=get_target(p,cid,target)
                multiplier=1+(rng.gauss(0,sigma) if dist=='normal' else rng.uniform(-math.sqrt(3)*sigma,math.sqrt(3)*sigma))
                changes[target]=nominal*multiplier
            out.append(({'trial':trial+1},changes,{}))
    else: raise ValueError('Unsupported study kind.')
    return out

def run_study(p,cid,settings,spec,engine='builtin',executable='',directory=None,progress=lambda *_:None):
    from .simulation import run
    from .engines import run_ngspice
    jobs=cases(p,cid,spec);rows=[];measure_spec=spec.get('measurement',{'trace':'vout','metric':'max'});last=None
    from .model import uid
    directory=Path(directory or '.').resolve()/('study-'+uid())
    for i,(labels,changes,overrides) in enumerate(jobs):
        sample=clone(p);analysis={**settings,**overrides}
        for target,value in changes.items():set_target(sample,cid,target,value)
        validate(sample);progress(i/len(jobs),f'Run {i+1} of {len(jobs)}')
        work=directory/f'case-{i+1:04d}';work.mkdir(parents=True,exist_ok=True)
        if engine=='builtin':last=run(sample,cid,analysis,lambda f,m:progress((i+f)/len(jobs),m))
        elif engine=='ngspice':last=run_ngspice(sample,cid,analysis,executable,work,lambda f,m:progress((i+f)/len(jobs),m))
        else:raise ValueError('Unsupported study engine.')
        measured=measure(last,measure_spec['trace'],measure_spec.get('metric','max'))
        from .model import atomic_write
        import json
        atomic_write(work/'input.json',json.dumps({'project':sample,'settings':analysis},allow_nan=False))
        atomic_write(work/'result.json',json.dumps(last,allow_nan=False))
        rows.append({'index':i+1,**labels,'changes':changes,'measurement':measured,'design_hash':last['design_hash'],'result_file':str(work/'result.json')})
    values=[r['measurement'] for r in rows];summary={'min':min(values),'max':max(values),'mean':statistics.fmean(values),'stddev':statistics.stdev(values) if len(values)>1 else 0}
    if 'lower' in measure_spec or 'upper' in measure_spec:
        lower=scalar(measure_spec['lower']) if 'lower' in measure_spec else -math.inf;upper=scalar(measure_spec['upper']) if 'upper' in measure_spec else math.inf
        if lower>upper:raise ValueError('Measurement lower limit exceeds upper limit.')
        summary['pass_count']=sum(lower<=v<=upper for v in values);summary['yield']=summary['pass_count']/len(values)
    return {'schema':1,'created':now(),'engine':last['engine'],'engine_hash':last['engine_hash'],'study_engine_hash':WORKFLOW_SOURCE_HASH,'project_id':p['id'],'revision':p['revision'],'design_hash':design_digest(p),'pdk_hash':digest(p['pdk']),'rule_hash':digest(p['pdk']['layers']),'cell_id':cid,'settings':{'type':'study','analysis':settings,'study':spec},'study_rows':rows,'summary':summary,'x':[r['index'] for r in rows],'x_label':'Study run','y_label':measure_spec['metric']+' · '+(last['x_label'] if measure_spec['metric']=='peak_x' else last['y_label']),'traces':{measure_spec['trace']:values},'phase':{},'operating_point':{},'warnings':last['warnings']+(['Component tolerances are user-declared; these are not foundry statistical models.'] if spec['kind']=='monte_carlo' else [])}
