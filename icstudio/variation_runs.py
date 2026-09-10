"""Independent study cases with immutable inputs and restartable manifests."""
import json, math, statistics
from pathlib import Path
from .model import clone, validate, digest, design_digest, atomic_write, now, uid, file_digest
from .studies import cases, set_target


def prepare(job,spec):
    p=job['project'];cid=job['cell'];bench_id=job.get('settings',{}).get('testbench')
    if job['settings']['type'] not in ('tran','op','dc','ac','noise','testbench'):raise ValueError('Choose a circuit analysis or saved testbench for individual cases.')
    sample_spec=clone(spec)
    if spec.get('kind')=='model_mismatch':
        declared=p['pdk'].get('statistical_models',{}).get(spec.get('model',''))
        if not declared or not declared.get('validated') or not declared.get('evidence') or not declared.get('variations'):raise ValueError('This technology has no validated statistical model with evidence and numeric parameter mappings. Use declared component tolerances.')
        sample_spec={**spec,'kind':'monte_carlo','variations':clone(declared['variations'])}
    from .run_environment import stamp
    job={**clone(job),'environment':stamp(job)}
    generated=cases(p,cid,sample_spec);group=uid();out=[]
    for i,(labels,changes,overrides) in enumerate(generated):
        q=clone(p)
        for target,value in changes.items():set_target(q,cid,target,value)
        settings={**job['settings'],**overrides}
        if bench_id:
            t=next(t for t in q['testbenches'] if t['id']==bench_id);t['analysis'].update(overrides)
        validate(q)
        if job['engine']=='builtin':
            from .simulation import Circuit
            Circuit(q,cid,float(settings.get('temperature',27)))
        item={**clone(job),'project':q,'settings':settings,'case':{'group':group,'index':i+1,'labels':labels,'changes':changes,'kind':spec['kind'],'seed':spec.get('seed'),'base_design_hash':design_digest(p)}}
        item['case']['fingerprint']=digest({k:v for k,v in item.items() if k!='case'})
        out.append(item)
    return {'schema':1,'id':group,'created':now(),'name':spec.get('name',spec['kind'].replace('_',' ').title()),'project_id':p['id'],'base_design_hash':design_digest(p),'spec':clone(spec),'jobs':out}


def save(manifest,root):
    path=Path(root)/manifest['project_id']/'studies'/(manifest['id']+'.json');atomic_write(path,json.dumps(manifest,indent=2,allow_nan=False));return path


def load(root,project_id):
    records=[]
    for path in sorted((Path(root)/project_id/'studies').glob('*.json'),key=lambda p:p.stat().st_mtime_ns)[-100:]:
        try:
            m=json.loads(path.read_text())
            if m.get('schema')==1 and m.get('project_id')==project_id and 1<=len(m.get('jobs',[]))<=500:records.append(m)
        except (OSError,ValueError):continue
    return records


def latest(manifest,rows):
    selected={}
    for row in rows:
        case=row['job'].get('case',{})
        if case.get('group')!=manifest['id']:continue
        i=case.get('index');expected=next((j for j in manifest['jobs'] if j['case']['index']==i),None)
        if expected and digest({k:v for k,v in row['job'].items() if k!='case'})==expected['case']['fingerprint']:selected[i]=row
    return selected


def pending(manifest,rows):
    current=latest(manifest,rows)
    return [clone(j) for j in manifest['jobs'] if current.get(j['case']['index'],{}).get('state') not in ('Complete','Running','Queued','Stopping')]


def summary(manifest,rows,spec_name=None):
    current=latest(manifest,rows);values=[];passed=failed=errors=0
    for index,row in current.items():
        if row['state']!='Complete':continue
        specs=row.get('result',{}).get('specifications',[])
        if not specs:errors+=1;continue
        if any(s['status']=='ERROR' for s in specs):errors+=1
        elif all(s['status']=='PASS' for s in specs):passed+=1
        else:failed+=1
        selected=next((s for s in specs if s['name']==spec_name),specs[0])
        if selected.get('value') is not None:values.append({'case':index,'value':selected['value'],'margin':selected['margin'],'name':selected['name']})
    total=len(manifest['jobs']);completed=sum(r['state']=='Complete' for r in current.values());bins=[]
    if values:
        nums=[v['value'] for v in values];lo,hi=min(nums),max(nums);count=min(12,max(1,math.ceil(math.sqrt(len(nums)))));width=(hi-lo)/count if hi>lo else max(abs(lo)*.01,1e-12);bins=[{'low':lo+i*width,'high':lo+(i+1)*width,'count':0} for i in range(count)]
        for value in nums:bins[min(count-1,int((value-lo)/width))]['count']+=1
    return {'total':total,'completed':completed,'passed':passed,'failed':failed,'errors':errors,'yield':passed/total,'values':values,'bins':bins,'worst':min(values,key=lambda v:v['margin']) if values else None,'mean':statistics.fmean(v['value'] for v in values) if values else None,'stddev':statistics.stdev(v['value'] for v in values) if len(values)>1 else 0}
