"""IHP tap schematic integration at declared points, with independent oracles.

Use complete locked model includes and compiled IHP models. The two tap models
are electrically identical in this source revision. Exact identity is checked
separately; numerical comparisons cannot distinguish swapping those names.
Selected geometry/bias/frequency/temperature points are not fabrication limits.
"""
import argparse,bisect,cmath,json,math,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,example,file_digest,save_project
from icstudio.catalog import create_device
from icstudio.catalog_migration import emit
from icstudio.engines import run_ngspice,run_deck
from icstudio.osdi import configure,preload
from icstudio.pdks import PDKRegistry,model_lines,stage_model_deck
from scripts.qualify_catalog_interfaces import one
from scripts.qualify_standard_mos import write

SIZES=((.78,.78),(.78,5),(5,.78),(2,2),(10,10))


def points():
    for model in ('ntap1','ptap1'):
        for i,(w,l) in enumerate(SIZES):
            yield dict(model=model,w=w,l=l,tag='out'+model[0]+str(i))


def resistance(w,l):
    # Independent conductance sum, using SI geometry and source coefficients.
    return 1/(w*l/9.8e-10 + 2*(w+l)/9.8e-4)


def fixture(tech,analysis,osdi):
    p=example('empty');p['pdk']=clone(tech);p['simulation_runtime']={'osdi':clone(osdi)}
    c=p['cells'][0];c['name']='tap_coupon';v=device('V','VDRIVE',0,0,value='.0005',nets={'p':'input','n':'0'});v['source']['ac']='1'
    if analysis=='tran':v['source'].update(type='sine',low='.00055',high='.001',period='200n',delay='10n')
    c['devices']=[v]
    for row in points():
        tag=row['tag'];d=create_device(tech,'sg13g2_pr/'+row['model']+'.sym','D'+tag)
        d['model_params'].update(w=row['w']*1e-6,l=row['l']*1e-6);d['nets']={'p':'input','m':tag}
        c['devices'] += [d,device('R','RL'+tag,0,0,value='1k',nets={'p':tag,'n':'0'},model_mode='generic'),
                        device('C','CL'+tag,0,0,value='1p',nets={'p':tag,'n':'0'},model_mode='generic')]
    return p


def settings(analysis,corner,temp,output='outn0'):
    return dict(type=analysis,corner=corner,temperature=temp,source='VDRIVE',dc_start='-.01',dc_stop='.01',dc_step='.001',
                start='100',end='10meg',points=5,step='1n',stop='600n',output=output,noise_source='VDRIVE')


def independent(tech,analysis,corner,temp,output='outn0'):
    lines=['* Independent public tap calls; R computed outside catalog',*model_lines(tech,corner),
           'VDRIVE input 0 '+('SIN(.00055 .00045 5meg 10n) AC 1' if analysis=='tran' else 'DC .0005 AC 1')]
    for row in points():
        tag=row['tag'];w=row['w']*1e-6;l=row['l']*1e-6;r=resistance(w,l)
        lines += [f'XREF{tag} input {tag} {row["model"]} w={w:.15g} l={l:.15g} r={r:.15g}',
                  f'RL{tag} {tag} 0 1000',f'CL{tag} {tag} 0 1p']
    directive={'dc':'.dc VDRIVE -.01 .01 .001','ac':'.ac dec 5 100 10meg','tran':'.tran 1n 600n',
               'noise':f'.noise V({output}) VDRIVE dec 5 100 10meg'}[analysis]
    return '\n'.join([*lines,f'.temp {temp}',directive,'.end',''])


def values(result,analysis,output='outn0'):
    x=result.get('x',[])
    if len(x)<2 or any(not math.isfinite(t) for t in x) or any(a>=b for a,b in zip(x,x[1:])):
        raise ValueError('Incomplete tap sweep.')
    if analysis=='dc' and (len(x)!=21 or not math.isclose(x[0],-.01,abs_tol=1e-12) or not math.isclose(x[-1],.01,abs_tol=1e-12)):
        raise ValueError('Incomplete tap DC sweep.')
    if analysis in ('ac','noise') and (len(x)!=26 or any(not math.isclose(f,100*10**(i/5),rel_tol=1e-9) for i,f in enumerate(x))):
        raise ValueError('Incomplete tap frequency sweep.')
    if analysis=='tran' and (x[0]>1e-12 or not math.isclose(x[-1],600e-9,rel_tol=1e-8)):
        raise ValueError('Incomplete tap transient.')
    names=[output] if analysis=='noise' else [r['tag'] for r in points()];out={}
    for name in names:
        v=result.get('traces',{}).get(name,[])
        if len(v)!=len(x) or any(not math.isfinite(n) for n in v):raise ValueError('Missing finite tap response: '+name)
        if analysis in ('noise','ac') and (min(v)<0 or max(v)<=0):raise ValueError('Unexercised passive response.')
        if analysis=='ac':
            phases=result.get('phase',{}).get(name,[])
            if len(phases)!=len(x) or any(not math.isfinite(n) for n in phases):raise ValueError('Missing tap phase.')
            v=[cmath.rect(a,math.radians(b)) for a,b in zip(v,phases)]
        out[name]=v
    return x,out


def compare(actual,expected,analysis,output='outn0'):
    x,left=values(actual,analysis,output);y,right=values(expected,analysis,output)
    rel=2e-4 if analysis=='tran' else 1e-6;absolute=1e-18 if analysis=='noise' else 1e-8 if analysis=='tran' else 1e-10
    if analysis!='tran' and (len(x)!=len(y) or any(not math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-15) for a,b in zip(x,y))):
        raise ValueError('Different tap sweep coordinates.')
    errors={}
    for name,reference in right.items():
        if analysis=='tran':
            interpolated=[]
            for t in x:
                i=max(0,min(len(y)-2,bisect.bisect_right(y,t)-1));f=(t-y[i])/(y[i+1]-y[i])
                interpolated.append(reference[i]+f*(reference[i+1]-reference[i]))
            reference=interpolated
        if analysis in ('dc','tran') and max(reference)-min(reference)<1e-5:raise ValueError('Unexercised reference output.')
        errors[name]=max(abs(a-b)/(absolute+rel*abs(b)) for a,b in zip(left[name],reference))
    return dict(status='PASS' if max(errors.values())<=1 else 'MISMATCH',channels=len(errors),samples=len(x),
                channel_errors=errors,relative_tolerance=rel,absolute_tolerance=absolute)


def analytical(result,analysis,temp,output='outn0'):
    x,out=values(result,analysis,output);worst=0.
    for row in points():
        name=row['tag']
        if name not in out:continue
        r=resistance(row['w']*1e-6,row['l']*1e-6);parallel=1/(1/r+1/1000)
        for f,value in zip(x,out[name]):
            if analysis=='dc':expected=f*1000/(r+1000)
            elif analysis=='ac':expected=(1000/(r+1000))/(1+2j*math.pi*f*parallel*1e-12)
            elif analysis=='noise':expected=math.sqrt(4*1.380649e-23*(temp+273.15)*parallel/(1+(2*math.pi*f*parallel*1e-12)**2))
            else:raise ValueError('No analytical transient oracle declared.')
            absolute=1e-18 if analysis=='noise' else 1e-10
            error=abs(value-expected)/(absolute+1e-6*abs(expected));worst=max(worst,error)
    if worst>1:raise ValueError('Analytical tap response mismatch: '+str(worst))
    return dict(status='PASS',maximum_normalized_error=worst)


def case(tech,corner,temp,root,engine,osdi):
    folder=root/f'{corner}-{temp}';folder.mkdir();record=dict(corner=corner,temperature_c=temp,status='RUNNING',analyses={},faults=[])
    try:
        for analysis,output in [('dc','outn0'),('ac','outn0'),('tran','outn0'),('noise','outn0'),('noise','outp0')]:
            name=analysis if analysis!='noise' else analysis+'-'+output;s=settings(analysis,corner,temp,output)
            p=fixture(tech,analysis,osdi);save_project(p,folder/(name+'.icproj'))
            expected_calls={row['tag']:row['model'] for row in points()}
            for d in p['cells'][0]['devices']:
                if d.get('model_ref') and emit(d,tech).split()[3]!=expected_calls[d['nets']['m']]:raise ValueError('Wrong emitted tap model identity.')
            app=folder/name/'application';ref=folder/name/'independent';app.mkdir(parents=True);ref.mkdir()
            actual=run_ngspice(p,p['top'],s,engine,app);write(app/'result.json',actual)
            path=ref/'reference.cir';path.write_bytes(preload(p,stage_model_deck(tech,independent(tech,analysis,corner,temp,output),ref),ref).encode())
            expected=run_deck(p,p['top'],dict(deck=str(path),analysis=s),engine,ref);write(ref/'result.json',expected)
            check=compare(actual,expected,analysis,output)
            if check['status']!='PASS':raise ValueError('Independent tap mismatch: '+name)
            record['analyses'][name]=dict(comparison=check,analytical=analytical(actual,analysis,temp,output) if analysis!='tran' else None,
                raw_sha256={'application':file_digest(app/'result.raw'),'independent':file_digest(ref/'deck.raw')})
            if analysis=='dc':dc=expected
        for fault in ('wrong-width','disconnected-terminal'):
            p=fixture(tech,'dc',osdi)
            for d in p['cells'][0]['devices']:
                if not d.get('model_ref'):continue
                if fault=='wrong-width':d['model_params']['w']*=1.2
                else:d['nets']['p']='0'
            dest=folder/fault;dest.mkdir();save_project(p,dest/'input.icproj')
            bad=run_ngspice(p,p['top'],settings('dc',corner,temp),engine,dest);write(dest/'result.json',bad);check=compare(bad,dc,'dc')
            if not all(e>1 for e in check['channel_errors'].values()):raise ValueError('Tap fault not detected for every device: '+fault)
            record['faults'].append(dict(name=fault,status='detected',comparison=check,raw_sha256=file_digest(dest/'result.raw')))
        record['status']='PASS'
    except Exception as exc:record.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
    write(folder/'record.json',record);return record


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--package',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--ngspice',required=True);ap.add_argument('--osdi',type=Path,required=True);ap.add_argument('--pilot',action='store_true');a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);registry=PDKRegistry(out/'registry');key=registry.install(a.package/'package.json');tech=registry.technology(key);osdi=configure(sorted(a.osdi.glob('*.osdi')))
    sources=[Path(__file__),ROOT/'scripts/qualify_catalog_interfaces.py',*sorted((ROOT/'icstudio').rglob('*.py'))];before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,geometry_um=SIZES,models=['ntap1','ptap1'],
        manifest_sha256=file_digest(a.package/'package.json'),revision=tech['revision'],engine_sha256=file_digest(a.ngspice),osdi=osdi,source_files_sha256=file_digest(out/'source-files.json'),cases=[])
    report['interfaces']=[one(tech,'sg13g2_pr/'+m+'.sym',out/('interface-'+m)) for m in ('ntap1','ptap1')]
    for corner in ('nominal',) if a.pilot else ('nominal','slow','fast'):
        for temp in (27,) if a.pilot else (0,27,85):
            row=case(tech,corner,temp,out,a.ngspice,osdi);report['cases'].append(row);write(out/'qualification.json',report);print(corner,temp,row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']+report['interfaces']) else 'FAIL'
    write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
