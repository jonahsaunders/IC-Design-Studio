"""Independent electrical controls for the source-checked SKY130 LI binding.

Finite geometry, temperature and corner selections qualify application wiring,
not a continuous operating envelope or the accuracy of the public silicon model.
"""
import argparse,bisect,cmath,json,math,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,example,file_digest,save_project
from icstudio.catalog import create_device
from icstudio.engines import run_ngspice,run_deck
from icstudio.pdks import PDKRegistry,model_lines,stage_model_deck
from scripts.qualify_standard_mos import write
from scripts.qualify_catalog_interfaces import one
from scripts.prepare_sky130_li_qualification import KEY

SIZES=((.17,.17),(.17,10),(1,1),(2,5),(5,2),(10,.17))
FAULTS=('wrong-width','wrong-metal-model','disconnected-terminal','wrong-multiplicity')


def points():
    for i,(w,l) in enumerate(SIZES):
        for m in (1,3):yield dict(tag=f'outg{i}m{m}',w=w,l=l,m=m)


def fixture(tech,analysis):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c['name']='li_coupon';c['devices']=[]
    v=device('V','VDRIVE',100,100,value='.0005',nets={'p':'input','n':'0'})
    v['source']['ac']='1'
    if analysis=='tran':v['source'].update(type='pulse',low='.0001',high='.001',period='20n',delay='1n',duty='.5')
    c['devices'].append(v)
    for row in points():
        tag=row['tag'];d=create_device(tech,KEY,'D'+tag)
        d['model_params'].update(w=row['w'],l=row['l'],mult=row['m']);d['nets']={'m':'input','p':tag}
        c['devices'].extend([d,device('R','RL'+tag,500,100,value='1k',nets={'p':tag,'n':'0'},model_mode='generic'),
            device('C','CL'+tag,500,300,value='1p',nets={'p':tag,'n':'0'},model_mode='generic')])
    return p


def settings(analysis,corner,temp):
    return dict(type=analysis,corner=corner,temperature=temp,source='VDRIVE',dc_start='0',dc_stop='.001',dc_step='.000025',
        start='100',end='10meg',points=5,step='50p',stop='60n',output='outg1m1',noise_source='VDRIVE')


def independent(tech,analysis,corner,temp):
    lines=['* Independent canonical local-interconnect model calls',*model_lines(tech,corner),
        'VDRIVE input 0 '+('PULSE(.0001 .001 1n .2p .2p 10n 20n) AC 1' if analysis=='tran' else 'DC .0005 AC 1')]
    for row in points():
        tag,w,l,m=(row[k] for k in ('tag','w','l','m'))
        lines.extend([f'RREF{tag} input {tag} sky130_fd_pr__res_generic_l1 w={w:g} l={l:g} m={m}',
            f'RL{tag} {tag} 0 1000',f'CL{tag} {tag} 0 1p'])
    directive={'dc':'.dc VDRIVE 0 .001 .000025','ac':'.ac dec 5 100 10meg','tran':'.tran 50p 60n',
        'noise':'.noise V(outg1m1) VDRIVE dec 5 100 10meg'}[analysis]
    return '\n'.join([*lines,f'.temp {temp}',directive,'.end',''])


def values(result,analysis):
    x=result.get('x',[])
    if len(x)<2 or not all(math.isfinite(t) for t in x) or any(a>=b for a,b in zip(x,x[1:])):raise ValueError('Incomplete sweep.')
    if analysis=='dc' and (len(x)!=41 or not math.isclose(x[-1],.001,rel_tol=1e-10)):raise ValueError('Incomplete DC sweep.')
    if analysis in ('ac','noise') and (len(x)!=26 or any(not math.isclose(t,100*10**(i/5),rel_tol=1e-9) for i,t in enumerate(x))):raise ValueError('Incomplete frequency sweep.')
    if analysis=='tran' and (x[0]>1e-12 or not math.isclose(x[-1],60e-9,rel_tol=1e-8)):raise ValueError('Incomplete transient.')
    names=['outg1m1'] if analysis=='noise' else [r['tag'] for r in points()];out={}
    for name in names:
        v=result.get('traces',{}).get(name,[])
        if len(v)!=len(x) or not all(math.isfinite(n) for n in v):raise ValueError('Missing finite output vector: '+name)
        if analysis in ('noise','ac') and (min(v)<0 or max(v)<=0):raise ValueError('Missing passive response: '+name)
        if analysis=='ac':
            phase=result.get('phase',{}).get(name,[])
            if len(phase)!=len(x) or not all(math.isfinite(n) for n in phase):raise ValueError('Missing phase: '+name)
            v=[cmath.rect(a,math.radians(b)) for a,b in zip(v,phase)]
        out[name]=v
    return x,out


def compare(actual,reference,analysis):
    x,left=values(actual,analysis);y,right=values(reference,analysis)
    relative=2e-4 if analysis=='tran' else 1e-6;absolute=1e-18 if analysis=='noise' else 1e-8 if analysis=='tran' else 1e-10
    if analysis!='tran' and (len(x)!=len(y) or any(not math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-15) for a,b in zip(x,y))):raise ValueError('Different sweep coordinates.')
    errors={}
    for name,expected in right.items():
        if analysis=='tran':
            interpolated=[]
            for t in x:
                i=max(0,min(len(y)-2,bisect.bisect_right(y,t)-1));fraction=(t-y[i])/(y[i+1]-y[i])
                interpolated.append(expected[i]+fraction*(expected[i+1]-expected[i]))
            expected=interpolated
        if analysis in ('dc','tran') and max(expected)-min(expected)<1e-5:raise ValueError('Unexercised independent resistor output.')
        errors[name]=max(abs(a-b)/(absolute+relative*abs(b)) for a,b in zip(left[name],expected))
    return dict(status='PASS' if max(errors.values())<=1 else 'MISMATCH',channels=len(errors),samples=len(x),
        maximum_normalized_error=max(errors.values()),channel_errors=errors,relative_tolerance=relative,absolute_tolerance=absolute)


def altered(p,fault):
    p=clone(p)
    for d in p['cells'][0]['devices']:
        if d.get('model_ref',{}).get('device')!=KEY:continue
        if fault=='wrong-width':d['model_params']['w']*=1.2
        elif fault=='wrong-metal-model':d['model_ref']['device']='sky130_fd_pr/res_generic_m1.sym'
        elif fault=='disconnected-terminal':d['nets']['m']='0'
        elif fault=='wrong-multiplicity':d['model_params']['mult']+=1
        else:raise ValueError('Unknown LI fault.')
    return p


def case(tech,corner,temp,out,engine):
    folder=out/f'{corner}-{temp}';folder.mkdir();row=dict(corner=corner,temperature_c=temp,status='RUNNING',analyses={},faults=[])
    try:
        for analysis in ('dc','ac','tran','noise'):
            p=fixture(tech,analysis);s=settings(analysis,corner,temp);save_project(p,folder/(analysis+'.icproj'))
            app=folder/analysis/'application';ref=folder/analysis/'independent';app.mkdir(parents=True);ref.mkdir()
            actual=run_ngspice(p,p['top'],s,engine,app)
            path=ref/'reference.cir';path.write_bytes(stage_model_deck(tech,independent(tech,analysis,corner,temp),ref).encode())
            expected=run_deck(p,p['top'],dict(deck=str(path),analysis=s),engine,ref)
            write(app/'comparison-result.json',actual);write(ref/'comparison-result.json',expected)
            comparison=compare(actual,expected,analysis)
            if comparison['status']!='PASS':raise ValueError('Independent LI response mismatch: '+analysis)
            row['analyses'][analysis]=dict(**comparison,application_raw_sha256=file_digest(app/'result.raw'),independent_raw_sha256=file_digest(ref/'deck.raw'))
            if analysis=='dc':dc_reference=expected
        for fault in FAULTS:
            p=altered(fixture(tech,'dc'),fault);dest=folder/fault;dest.mkdir();save_project(p,dest/'input.icproj')
            actual=run_ngspice(p,p['top'],settings('dc',corner,temp),engine,dest);write(dest/'comparison-result.json',actual)
            comparison=compare(actual,dc_reference,'dc')
            if comparison['status']!='MISMATCH' or not all(e>1 for e in comparison['channel_errors'].values()):raise ValueError('LI fault did not change every selected device: '+fault)
            row['faults'].append(dict(name=fault,status='detected',comparison=comparison,raw_sha256=file_digest(dest/'result.raw')))
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--package',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--ngspice',required=True);ap.add_argument('--pilot',action='store_true');a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);registry=PDKRegistry(out/'registry');key=registry.install(a.package/'package.json');tech=registry.technology(key)
    sources=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/qualify_catalog_interfaces.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,geometry_um=SIZES,copies=[1,3],noise_output='outg1m1',
        manifest_sha256=file_digest(a.package/'package.json'),revision=tech['revision'],engine_sha256=file_digest(a.ngspice),source_files_sha256=file_digest(out/'source-files.json'),cases=[])
    report['interface']=one(tech,KEY,out/'interface')
    for corner in ('nominal',) if a.pilot else ('nominal','ss','ff'):
        for temp in (27,) if a.pilot else (-40,27,125):
            row=case(tech,corner,temp,out,a.ngspice);report['cases'].append(row);write(out/'qualification.json',report);print(corner,temp,row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['implementation_unchanged'] and report['interface']['status']=='PASS' and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
