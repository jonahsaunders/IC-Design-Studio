"""Compare standard process MOS simulation to independent four-terminal decks.

This is an executable part of chunk 7, not a device/foundry qualification claim.
The complete operating envelope, physical verification and other device families
remain separate requirements. No expected numeric waveform is fitted to a run.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
from pathlib import Path
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.model import atomic_write,clone,device,example,file_digest,save_project
from icstudio.catalog import create_device,parameter_values
from icstudio.engines import run_ngspice,run_deck
from icstudio.interchange import export_xschem
from icstudio.xschem_io import import_package
from icstudio.pdks import model_lines,stage_model_deck
from icstudio.osdi import configure,preload

PROFILES={
    'sky130A':dict(prefix='sky130_fd_pr/',symbols=('nfet_01v8','pfet_01v8'),
        models=('sky130_fd_pr__nfet_01v8','sky130_fd_pr__pfet_01v8'),supply=1.8,minimum_length=.15,
        corners=('nominal','ss','ff')),
    'gf180mcuC':dict(prefix='symbols/',symbols=('nfet_03v3','pfet_03v3'),
        models=('nfet_03v3','pfet_03v3'),supply=3.3,minimum_length=.28,corners=('nominal','ss','ff')),
    'gf180mcuD':dict(prefix='symbols/',symbols=('nfet_03v3','pfet_03v3'),
        models=('nfet_03v3','pfet_03v3'),supply=3.3,minimum_length=.28,corners=('nominal','ss','ff')),
    'ihp-sg13g2':dict(prefix='sg13g2_pr/',symbols=('sg13_lv_nmos','sg13_lv_pmos'),
        models=('sg13_lv_nmos','sg13_lv_pmos'),supply=1.2,minimum_length=.13,corners=('nominal','slow','fast')),
}
# These are declared application test points, not inferred model/reliability limits.
GEOMETRIES=('interior','narrow-short','narrow-long','wide-short','wide-long','parallel')
TOLERANCES={'dc':(1e-6,1e-9),'ac':(1e-6,1e-9),'tran':(2e-4,1e-7),'noise':(1e-6,1e-18)}


def write(path,value):
    # A cancelled session must not replace completed evidence with a truncated
    # progress file. Publish the synchronized new file in one replacement.
    atomic_write(path,json.dumps(value,indent=2,allow_nan=False)+'\n')


def geometry(target,name):
    short=PROFILES[target]['minimum_length']
    return dict(zip(('w','l','fingers','copies'),{
        'interior':(4,.5,1,1),'narrow-short':(1,short,1,1),'narrow-long':(1,2,1,1),
        'wide-short':(10,short,1,1),'wide-long':(10,2,1,1),'parallel':(4,.5,2,3)}[name]))


def load_technology(target):
    folder=ROOT/'icstudio/assets/pdks'/target;raw=(folder/'package.json').read_bytes();package=json.loads(raw)
    collection=json.loads((folder.parent/'collection.json').read_bytes())
    expected=next(r['manifest_sha256'] for r in collection['packages'] if r['variant']==target)
    if file_digest(folder/'package.json')!=expected:raise ValueError('Changed process manifest: '+target)
    for relative,expected in package['files'].items():
        path=(folder/relative).resolve()
        if not path.is_relative_to(folder.resolve()) or file_digest(path)!=expected:
            raise ValueError('Changed locked process resource: '+target+'/'+relative)
    tech=clone(package['technology'])
    tech.update(package_root=str(folder),package_lock={k:package[k] for k in ('id','revision','files')})
    return tech,dict(target=target,revision=package['revision'],manifest_sha256=file_digest(folder/'package.json'))


def fixture(technology,target,polarity,size,analysis,osdi=()):
    profile=PROFILES[target];supply=profile['supply'];pm=polarity=='p';index=int(pm)
    p=example('empty');p['pdk']=clone(technology);c=p['cells'][0];c['name']='mos_coupon'
    key=profile['prefix']+profile['symbols'][index]+'.sym'
    d=create_device(p['pdk'],key,'M1');d['params'].update(w=f"{size['w']}u",l=f"{size['l']}u")
    d['model_params'].update({('ng' if target=='ihp-sg13g2' else 'nf'):size['fingers'],
        ('mult' if target=='sky130A' else 'm'):size['copies']})
    d['nets']=dict(d='out',g='gate',s='vdd' if pm else '0',b='vdd' if pm else '0')
    supply_device=device('V','VDD',100,100,value=str(supply),nets={'p':'vdd','n':'0'})
    supply_device['source']['ac']='0'
    gate=device('V','VG',100,300,value=str(supply/2),nets={'p':'gate','n':'0'})
    if analysis=='tran':gate['source'].update(type='pulse',low=str(.1*supply),high=str(.9*supply),period='20n',delay='1n',duty='.5')
    c['devices']=[supply_device,gate,device('R','RL',600,150,value='10k',
        nets={'p':'0' if pm else 'vdd','n':'out'},model_mode='generic'),
        device('C','CL',600,350,value='10f',nets={'p':'out','n':'0'},model_mode='generic'),d]
    if target=='ihp-sg13g2':p['simulation_runtime']={'osdi':clone(list(osdi))}
    return p,d


def settings(target,analysis,corner,temperature):
    supply=PROFILES[target]['supply']
    return dict(type=analysis,corner=corner,temperature=temperature,source='VG',dc_start='0',dc_stop=str(supply),
        dc_step=str(supply/40),start='1k',end='1g',points=5,step='50p',stop='60n',output='out',noise_source='VG')


def independent_device(target,polarity,size):
    """Explicit source-symbol conventions, without reading the catalog emitter."""
    w,l,nf,m=(size[k] for k in ('w','l','fingers','copies'));model=PROFILES[target]['models'][polarity=='p']
    terminals='out gate vdd vdd' if polarity=='p' else 'out gate 0 0'
    if target=='ihp-sg13g2':
        params=f'w={w:.12g}u l={l:.12g}u ng={nf} m={m} mm_ok=1'
    else:
        scale=1 if target=='sky130A' else 1e-6;extension=.29 if target=='sky130A' else .18
        wd=w*scale;ld=l*scale;e=extension*scale
        values=dict(w=wd,l=ld,nf=nf,ad=math.floor((nf+1)/2)*wd/nf*e,
            **{'as':math.floor((nf+2)/2)*wd/nf*e},pd=2*math.floor((nf+1)/2)*(wd/nf+e),
            ps=2*math.floor((nf+2)/2)*(wd/nf+e),nrd=e/wd,nrs=e/wd,sa=0,sb=0,sd=0,m=m)
        if target=='sky130A':values['mult']=m
        params=' '.join(f'{k}={v:.12g}' for k,v in values.items())
    return f'XREFERENCE {terminals} {model} {params}'


def independent_deck(tech,target,polarity,size,analysis,corner,temperature):
    v=PROFILES[target]['supply'];pm=polarity=='p'
    gate=(f'PULSE({.1*v:.12g} {.9*v:.12g} 1n .2p .2p 10n 20n) AC 1'
        if analysis=='tran' else f'DC {v/2:.12g} AC 1')
    directive={'dc':f'.dc VG 0 {v:.12g} {v/40:.12g}',
        'ac':'.ac dec 5 1k 1g','tran':'.tran 50p 60n','noise':'.noise V(out) VG dec 5 1k 1g'}[analysis]
    return '\n'.join(['* Independent four-terminal MOS reference',*model_lines(tech,corner),
        f'VDD vdd 0 DC {v:.12g} AC 0','VG gate 0 '+gate,
        'RL '+('0' if pm else 'vdd')+' out 10000','CL out 0 10f',independent_device(target,polarity,size),
        f'.temp {temperature}',directive,'.end',''])


def compare(actual,reference,analysis):
    """Compare output shape and complex AC phase; reject empty/degenerate probes."""
    rel,absolute=TOLERANCES[analysis];a=actual['traces'].get('out',[]);b=reference['traces'].get('out',[])
    x=actual['x'];y=reference['x']
    if len(a)<10 or len(a)!=len(x) or len(b)!=len(y) or not all(math.isfinite(v) for v in [*a,*b,*x,*y]):
        raise ValueError('Missing, nonfinite or incomplete comparison samples.')
    # Different instance names can alter the adaptive transient grid. Compare
    # both waveforms on the frozen application sample times by interpolation.
    if any(t>=u for t,u in zip(x,x[1:])) or any(t>=u for t,u in zip(y,y[1:])):
        raise ValueError('Non-increasing comparison sample coordinates.')
    if analysis=='tran':
        from bisect import bisect_left
        if abs(x[0]-y[0])>1e-15 or abs(x[-1]-y[-1])>1e-15:raise ValueError('Transient domains differ.')
        interpolated=[]
        for value in x:
            i=min(max(1,bisect_left(y,value)),len(y)-1)
            fraction=(value-y[i-1])/(y[i]-y[i-1])
            interpolated.append(b[i-1]+fraction*(b[i]-b[i-1]))
        b=interpolated
    elif len(x)!=len(y) or any(not math.isclose(t,u,rel_tol=1e-10,abs_tol=1e-15) for t,u in zip(x,y)):
        raise ValueError('Comparison sweep coordinates differ.')
    if analysis in ('dc','tran') and max(b)-min(b)<.05:raise ValueError('Reference does not exercise a switching device.')
    if analysis in ('ac','noise') and (min(b)<0 or max(b)<=absolute):raise ValueError('Reference response is empty or nonphysical.')
    errors=[abs(u-v)/(absolute+rel*abs(v)) for u,v in zip(a,b)]
    if max(errors)>1:raise ValueError('Independent MOS response differs: normalized error '+str(max(errors)))
    phase_error=None
    if analysis=='ac':
        left=actual.get('phase',{}).get('out',[]);right=reference.get('phase',{}).get('out',[])
        if len(left)!=len(a) or len(right)!=len(a) or not all(math.isfinite(v) for v in [*left,*right]):
            raise ValueError('Missing complex AC phase evidence.')
        phase_error=max(abs((u-v+180)%360-180) for u,v in zip(left,right))
        if phase_error>1e-4:raise ValueError('Independent MOS AC phase differs.')
    return dict(status='PASS',samples=len(a),relative_tolerance=rel,absolute_tolerance=absolute,
        maximum_normalized_error=max(errors),maximum_phase_error_degrees=phase_error)


def case_run(tech,target,polarity,shape,corner,temp,out,ngspice,osdi):
    name=f'{target}-{polarity}-{shape}-{corner}-{temp}';folder=out/name;folder.mkdir()
    size=geometry(target,shape);row=dict(name=name,target=target,polarity=polarity,geometry=size,
        corner=corner,temperature_c=temp,status='RUNNING',analyses={});start=time.monotonic()
    try:
        for analysis in TOLERANCES:
            p,d=fixture(tech,target,polarity,size,analysis,osdi);s=settings(target,analysis,corner,temp)
            app=folder/analysis/'application';ref=folder/analysis/'independent';app.mkdir(parents=True);ref.mkdir()
            if analysis=='dc':
                save_project(p,folder/'input.icproj');export_xschem(p,folder/'xschem');q,_=import_package(folder/'xschem')
                entry=tech['simulation']['catalog'][d['model_ref']['device']]
                from icstudio.catalog_migration import instance_name
                after=next(v for v in q['cells'][0]['devices'] if v['name']==instance_name(d,entry))
                before_values=parameter_values(entry,d);after_values=parameter_values(entry,after)
                if d['model_ref']!=after['model_ref'] or d['nets']!=after['nets'] or before_values.keys()!=after_values.keys() or any(
                    not math.isclose(v,after_values[k],rel_tol=5e-11,abs_tol=0) for k,v in before_values.items()):
                    raise ValueError('MOS Xschem model, terminals or dimensions changed.')
                row['interface_roundtrip']='PASS'
            actual=run_ngspice(p,p['top'],s,ngspice,app)
            text=independent_deck(tech,target,polarity,size,analysis,corner,temp)
            text=preload(p,stage_model_deck(tech,text,ref),ref);path=ref/'independent.cir';path.write_bytes(text.encode())
            from icstudio.ngspice_compat import prepare
            path.write_bytes(prepare(text,ngspice,ref).encode())
            reference=run_deck(p,p['top'],dict(deck=str(path),analysis=s),ngspice,ref)
            write(app/'comparison-result.json',actual);write(ref/'comparison-result.json',reference)
            row['analyses'][analysis]=dict(**compare(actual,reference,analysis),
                application_deck_sha256=file_digest(app/'input.cir'),reference_deck_sha256=file_digest(path),
                application_raw_sha256=file_digest(app/'result.raw'),reference_raw_sha256=file_digest(ref/'deck.raw'))
        # A wrong width must produce a real response mismatch against the same
        # independent reference. A runtime/model-loading failure is not a pass.
        p,d=fixture(tech,target,polarity,size,'dc',osdi);d['params']['w']=str(size['w']*1.2)+'u'
        fault=folder/'wrong-width';fault.mkdir();actual=run_ngspice(p,p['top'],settings(target,'dc',corner,temp),ngspice,fault)
        reference=json.loads((folder/'dc/independent/comparison-result.json').read_bytes())
        try:compare(actual,reference,'dc')
        except ValueError as error:
            if not str(error).startswith('Independent MOS response differs:'):raise
            row['wrong_width_fault']=dict(status='detected',error=str(error),raw_sha256=file_digest(fault/'result.raw'))
        else:raise ValueError('Wrong MOS width was not detected.')
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    row['elapsed_seconds']=time.monotonic()-start;write(folder/'record.json',row);return row


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ngspice',required=True);parser.add_argument('--osdi',type=Path,required=True)
    parser.add_argument('--targets',nargs='+',choices=PROFILES,default=list(PROFILES))
    parser.add_argument('--geometries',nargs='+',choices=GEOMETRIES,default=list(GEOMETRIES))
    parser.add_argument('--temperatures',nargs='+',type=int,default=[0,27,85]);parser.add_argument('--nominal-only',action='store_true')
    parser.add_argument('--workers',type=int,choices=range(1,17),default=2);a=parser.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);osdi=configure(sorted(a.osdi.glob('*.osdi')))
    sources=[Path(__file__),*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    report=dict(schema=1,chunk=7,status='RUNNING',chunk_complete=False,qualified=False,
        scope='Selected standard four-terminal MOS interface and independent DC/AC/transient/noise comparisons only. Model accuracy against silicon, complete operating envelopes, physical checks, other devices and release qualification remain open.',
        source_sha256=file_digest(__file__),source_files_sha256=file_digest(out/'source-files.json'),
        engine_sha256=file_digest(a.ngspice),osdi=osdi,processes={},cases=[],
        temperatures=a.temperatures,geometries=a.geometries,nominal_only=a.nominal_only)
    # Each case owns its project and output directory. Processes also parallelize
    # Python netlisting/model staging instead of serializing that work on the GIL.
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[]
        for target in a.targets:
            tech,identity=load_technology(target);report['processes'][target]=identity
            for polarity in ('n','p'):
                for shape in a.geometries:
                    for corner in ('nominal',) if a.nominal_only else PROFILES[target]['corners']:
                        for temp in a.temperatures:
                            jobs.append(pool.submit(case_run,tech,target,polarity,shape,corner,temp,out,a.ngspice,osdi))
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report)
            print(row['name'],row['status'],row.get('error',''),flush=True)
    report['status']='PASS' if report['cases'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    if not report['implementation_unchanged']:report.update(status='FAIL',error='Implementation changed during qualification.')
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report)
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
