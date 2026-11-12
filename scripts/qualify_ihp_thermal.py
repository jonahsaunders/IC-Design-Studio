"""Finite IHP five-terminal HBT self-heating and thermal-connection controls.

Compare independent public-model calls, electrical KCL and the corresponding
four-terminal model. The T port is temperature rise, not an extra chip pad.
No calibrated thermal environment or continuous operating envelope is claimed.
"""
import argparse,bisect,cmath,json,math,sys,traceback
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,example,file_digest,save_project
from icstudio.catalog import create_device
from icstudio.engines import run_ngspice,run_deck
from icstudio.osdi import configure,preload
from icstudio.pdks import model_lines,stage_model_deck
from scripts.qualify_standard_mos import load_technology,write


def probes():
    for family in ('npn13G2','npn13G2l','npn13G2v'):
        for nx in (1,4):
            for el in (None,) if family=='npn13G2' else (1,2.5):
                yield dict(model=family+'_5t',nx=nx,el=el,tag='q'+family.lower().replace('npn13g2','')+'n'+str(nx)+'l'+str(el or 0).replace('.','p'))


def fixture(tech,analysis,osdi):
    p=example('empty');p['pdk']=clone(tech);p['simulation_runtime']={'osdi':clone(osdi)};c=p['cells'][0];c['name']='thermal_coupon'
    v=device('V','VB',0,0,value='.75',nets={'p':'drive','n':'0'});v['source']['ac']='1'
    if analysis=='tran':v['source'].update(type='sine',low='.665',high='.78',delay='10n',period='200n')
    c['devices']=[v]
    for row in probes():
        tag=row['tag'];d=create_device(tech,'sg13g2_pr/'+row['model']+'.sym','D'+tag);d['model_params']['nx']=row['nx']
        if row['el'] is not None:d['model_params']['el']=row['el']
        d['nets']={pin:tag+pin for pin in ('c','b','e','s','t')};c['devices'].append(d)
        for pin in ('c','b','e','s'):
            v=device('V','V'+tag+pin,0,0,value='1' if pin=='c' else '0',nets={'p':tag+pin,'n':'drive' if pin=='b' else '0'});v['source']['ac']='0';c['devices'].append(v)
    return p


def settings(analysis,corner,temp):
    return dict(type=analysis,corner=corner,temperature=temp,source='VB',dc_start='.45',dc_stop='.78',dc_step='.01',start='100k',end='1g',points=5,step='1n',stop='600n')


def independent(tech,analysis,corner,temp,four=False):
    # Smooth 5 MHz heating cycle; this is not a picosecond edge/timing test.
    lines=['* Independent IHP HBT thermal reference',*model_lines(tech,corner),'VB drive 0 '+('SIN(.665 .115 5meg 10n) AC 1' if analysis=='tran' else 'DC .75 AC 1')]
    for row in probes():
        tag=row['tag'];model=row['model'].removesuffix('_5t') if four else row['model'];nodes=' '.join(tag+p for p in ('c','b','e','s')+(() if four else ('t',)))
        for pin in ('c','b','e','s'):lines.append(f'V{tag+pin} {tag+pin} '+('drive' if pin=='b' else '0')+(' DC 1 AC 0' if pin=='c' else ' DC 0 AC 0'))
        params=f'nx={row["nx"]} mm_ok=1'+('' if row['el'] is None else f' el={row["el"]:g}')
        lines.append(f'X{tag} {nodes} {model} {params}')
    directive={'dc':'.dc VB .45 .78 .01','ac':'.ac dec 5 100k 1g','tran':'.tran 1n 600n'}[analysis]
    return '\n'.join([*lines,f'.temp {temp}',directive,'.end',''])


def vectors(result,analysis,thermal=True):
    x=result.get('x',[])
    if len(x)<2 or not all(math.isfinite(t) for t in x) or any(a>=b for a,b in zip(x,x[1:])):raise ValueError('Incomplete thermal analysis.')
    if analysis=='dc' and (len(x)!=34 or not math.isclose(x[-1],.78,abs_tol=1e-10)):raise ValueError('Incomplete HBT DC sweep.')
    if analysis=='ac' and (len(x)!=21 or any(not math.isclose(f,1e5*10**(i/5),rel_tol=1e-9) for i,f in enumerate(x))):raise ValueError('Incomplete thermal frequency sweep.')
    if analysis=='tran' and (x[0]>1e-12 or not math.isclose(x[-1],600e-9,rel_tol=1e-8)):raise ValueError('Incomplete thermal transient.')
    out={};currents={k.lower():v for k,v in result.get('currents',{}).items()};iphase={k.lower():v for k,v in result.get('current_phase',{}).items()}
    for row in probes():
        tag=row['tag']
        for pin in ('c','b','e','s')+(('t',) if thermal else ()):
            key=tag+pin if pin=='t' else 'v'+tag+pin;data=result.get('traces',{}) if pin=='t' else currents;phases=result.get('phase',{}) if pin=='t' else iphase;v=data.get(key,[])
            if len(v)!=len(x) or not all(math.isfinite(n) for n in v):raise ValueError('Missing thermal/electrical vector: '+key)
            if analysis=='ac':
                phase=phases.get(key,[])
                if len(phase)!=len(x) or not all(math.isfinite(n) for n in phase):raise ValueError('Missing thermal/electrical phase: '+key)
                v=[cmath.rect(a,math.radians(b)) for a,b in zip(v,phase)]
            out[key]=v
        for sample in zip(*(out['v'+tag+p] for p in ('c','b','e','s'))):
            if abs(sum(sample))>1e-10+1e-6*max(abs(v) for v in sample):raise ValueError('Electrical terminals violate KCL: '+tag)
    return x,out


def compare(actual,expected,analysis,thermal=True):
    x,a=vectors(actual,analysis,thermal);y,b=vectors(expected,analysis,thermal);errors={}
    if analysis!='tran' and (len(x)!=len(y) or any(not math.isclose(v,w,rel_tol=1e-10,abs_tol=1e-14) for v,w in zip(x,y))):raise ValueError('Thermal sweep coordinates differ.')
    for key,values in b.items():
        if analysis=='tran':
            sampled=[]
            for t in x:
                i=max(0,min(len(y)-2,bisect.bisect_right(y,t)-1));f=(t-y[i])/(y[i+1]-y[i]);sampled.append(values[i]+f*(values[i+1]-values[i]))
            values=sampled
        relative=2e-4 if analysis=='tran' else 1e-6;absolute=(1e-5 if analysis=='tran' else 1e-8) if key.endswith('t') else (1e-8 if analysis=='tran' else 1e-12)
        errors[key]=max(abs(v-w)/(absolute+relative*abs(w)) for v,w in zip(a[key],values))
    return dict(status='PASS' if max(errors.values())<=1 else 'MISMATCH',maximum_normalized_error=max(errors.values()),channel_errors=errors,vectors=len(errors),samples=len(x))


def check_stimulus(result,analysis):
    x=result['x'];drive=result.get('traces',{}).get('drive',[])
    if len(drive)!=len(x) or not all(math.isfinite(v) for v in drive):raise ValueError('Missing or nonfinite heating-cycle input.')
    expected=x if analysis=='dc' else [1.]*len(x) if analysis=='ac' else [.665+.115*math.sin(2*math.pi*5e6*max(0,t-10e-9)) for t in x]
    error=max(abs(a-b) for a,b in zip(drive,expected))
    if not math.isfinite(error) or error>1e-9:raise ValueError('Heating-cycle stimulus differs from the declared input.')
    return dict(samples=len(x),maximum_voltage_error=error)


def reference_run(p,tech,analysis,corner,temp,folder,engine,four=False):
    folder.mkdir(parents=True);path=folder/'reference.cir';path.write_bytes(preload(p,stage_model_deck(tech,independent(tech,analysis,corner,temp,four),folder),folder).encode())
    result=run_deck(p,p['top'],dict(deck=str(path),analysis=settings(analysis,corner,temp)),engine,folder);write(folder/'result.json',result);return result


def case(tech,corner,temp,root,engine,osdi):
    folder=root/f'{corner}-{temp}';folder.mkdir();record=dict(corner=corner,temperature_c=temp,status='RUNNING',analyses={},faults=[])
    try:
        for analysis in ('dc','ac','tran'):
            p=fixture(tech,analysis,osdi);save_project(p,folder/(analysis+'.icproj'));app=folder/analysis/'application';app.mkdir(parents=True)
            actual=run_ngspice(p,p['top'],settings(analysis,corner,temp),engine,app);write(app/'result.json',actual);stimulus=check_stimulus(actual,analysis)
            expected=reference_run(p,tech,analysis,corner,temp,folder/analysis/'independent',engine);check=compare(actual,expected,analysis)
            record['analyses'][analysis]=dict(comparison=check,stimulus=stimulus)
            if check['status']!='PASS':raise ValueError('Independent five-terminal thermal comparison differs: '+analysis)
            if analysis in ('dc','tran'):
                for row in probes():
                    t=actual['traces'][row['tag']+'t']
                    if max(t)<1e-4 or min(t)<-1e-4 or max(t)>100:raise ValueError('Thermal test did not exercise a bounded positive temperature rise.')
                    if analysis=='tran' and max(t)-min(t)<1e-4:raise ValueError('Thermal output did not respond to the heating cycle.')
            four=reference_run(p,tech,analysis,corner,temp,folder/analysis/'four-terminal',engine,True);equivalent=compare(actual,four,analysis,False)
            record['analyses'][analysis]['four_terminal_comparison']=equivalent
            if equivalent['status']!='PASS':raise ValueError('Floating thermal output changes the corresponding four-terminal device: '+analysis)
            record['analyses'][analysis]=dict(comparison=check,four_terminal_comparison=equivalent,stimulus=stimulus,raw_sha256={name:file_digest(folder/analysis/name/('result.raw' if name=='application' else 'deck.raw')) for name in ('application','independent','four-terminal')})
            if analysis=='dc':dc=expected
        for fault in ('clamped-temperature','wrong-emitter-count'):
            q=fixture(tech,'dc',osdi)
            for d in q['cells'][0]['devices']:
                if not d.get('model_ref'):continue
                if fault=='clamped-temperature':d['nets']['t']='0'
                else:d['model_params']['nx']+=1
            dest=folder/fault;dest.mkdir();save_project(q,dest/'input.icproj');bad=run_ngspice(q,q['top'],settings('dc',corner,temp),engine,dest);write(dest/'result.json',bad);check=compare(bad,dc,'dc',False)
            if not all(check['channel_errors']['v'+row['tag']+'c']>1 for row in probes()):raise ValueError('Thermal/count fault not detected in every device.')
            record['faults'].append(dict(name=fault,status='detected',detected_devices=10,comparison=check,raw_sha256=file_digest(dest/'result.raw')))
        record['status']='PASS'
    except Exception as error:record.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',record);return record


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--ngspice',required=True);ap.add_argument('--osdi',type=Path,required=True);ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,5),default=3);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);tech,identity=load_technology('ihp-sg13g2');osdi=configure(sorted(a.osdi.glob('*.osdi')))
    sources=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))];before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    report=dict(schema=1,chunk=7,status='RUNNING',chunk_complete=False,qualified=False,scope=__doc__,process=identity,probes=list(probes()),engine_sha256=file_digest(a.ngspice),osdi=osdi,cases=[],source_files_sha256=file_digest(out/'source-files.json'))
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(case,tech,corner,temp,out,a.ngspice,osdi) for corner in (('nominal',) if a.pilot else ('nominal','slow','fast')) for temp in ((27,) if a.pilot else (0,27,85))]
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['corner'],row['temperature_c'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};report['status']='PASS' if report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL';write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
