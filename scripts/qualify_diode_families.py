"""Selected public diode interfaces, terminal currents and connection controls.

Independent calls use explicit terminal/geometry contracts below. This does not
qualify ESD pulse ratings, breakdown, complete geometry/bias ranges or layouts.
IHP isolbox uses the current default with --isolation-only. The earlier explicit
package remains reproducible with --historical-isolation; saved projects retain
their revisions.
"""
import argparse,json,math,os,sys,traceback
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,example,file_digest,save_project
from icstudio.catalog import create_device
from icstudio.engines import run_ngspice,run_deck
from icstudio.osdi import configure,preload
from icstudio.pdks import model_lines,stage_model_deck
from scripts.qualify_standard_mos import load_technology,PROFILES,write

GF=('diode_dw2ps','diode_nd2ps_03v3','diode_nd2ps_06v0','diode_nw2ps_03v3','diode_nw2ps_06v0','diode_pd2nw_03v3','diode_pd2nw_06v0','diode_pw2dw','sc_diode')
IHP=('dantenna','dpantenna','schottky_nbl1')
ESD=('diodevdd_2kv','diodevdd_4kv','diodevss_2kv','diodevss_4kv')


def probes(target,group):
    names=('isolbox',) if group=='isolation' else GF if target.startswith('gf180') else ESD if group=='esd' else IHP
    for i,name in enumerate(names):
        for shape in (0,1):
            if target.startswith('gf180'):
                size=3 if name=='diode_pw2dw' else 1
                pins=('p','m');params=dict(r_w=str(size*(1+shape))+'u',r_l=str(size)+'u',m=1+2*shape)
                manual=f'area={size*size*(1+shape)*1e-12:.12g} pj={2*size*(2+shape)*1e-6:.12g} m={1+2*shape}'
            elif group=='isolation':
                pins=('isosub','nwell','sub!');params=dict(w=str(3+3*shape)+'u',l=str(3+shape)+'u');manual=f'w={3+3*shape}u l={3+shape}u'
            elif group=='esd':pins=('vdd','pad','vss');params=dict(m=1+2*shape);manual=f'm={1+2*shape}'
            elif name=='schottky_nbl1':pins=('plus','minus','tie');params=dict(nx=1+shape,ny=1);manual=f'nx={1+shape} ny=1'
            else:pins=('d0','d1');params=dict(w=str(.78*(1+shape))+'u',l='.78u');manual=f'w={.78*(1+shape):.12g}u l=.78u'
            yield dict(name=name,tag=f'd{i}s{shape}',pins=pins,params=params,manual=manual,shape=shape)


def voltage(group,index):
    return '1.2' if group=='esd' and index==0 else '-1' if group=='isolation' and index==2 else '0'


def fixture(tech,target,group,osdi):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0]
    c['devices']=[device('V','VG',0,0,value='0',nets={'p':'drive','n':'0'})]
    for row in probes(target,group):
        tag=row['tag'];prefix='symbols/' if target.startswith('gf180') else 'sg13g2_pr/'
        d=create_device(tech,prefix+row['name']+'.sym','D'+tag);d['model_params'].update(row['params'])
        d['nets']={pin:tag+'p'+str(i) for i,pin in enumerate(row['pins'])}
        for i,pin in enumerate(row['pins']):
            driven=i==(1 if group=='esd' else 0)
            c['devices'].append(device('V','V'+tag+'p'+str(i),0,0,value=voltage(group,i),nets={'p':d['nets'][pin],'n':'drive' if driven else '0'}))
        c['devices'].append(d)
    if target=='ihp-sg13g2':p['simulation_runtime']={'osdi':clone(osdi)}
    return p


def sweep(group):return (-.8,2,.05) if group=='esd' else (-2,.5,.025) if group=='isolation' else (-.2,.8,.025)


def vectors(data,target,group,physical=False):
    start,stop,step=sweep(group);length=round((stop-start)/step)+1
    if len(data['x'])!=length or any(not math.isfinite(x) or not math.isclose(x,start+i*step,abs_tol=1e-8) for i,x in enumerate(data['x'])):raise ValueError('Incomplete diode bias domain.')
    current={k.lower():v for k,v in data['currents'].items()};out={}
    for row in probes(target,group):
        keys=['v'+row['tag']+'p'+str(i) for i in range(len(row['pins']))]
        for key in keys:
            v=current.get(key,[])
            if len(v)!=length or any(not math.isfinite(x) for x in v):raise ValueError('Missing or nonfinite diode terminal current: '+key)
            out[key]=v
        if physical:
            if max(max(out[k])-min(out[k]) for k in keys)<1e-12:raise ValueError('Diode fixture does not exercise measurable conduction: '+row['name'])
            for sample in zip(*(out[k] for k in keys)):
                if abs(sum(sample))>1e-12+1e-6*max(abs(v) for v in sample):raise ValueError('Diode terminals violate electrical KCL: '+row['name'])
    return out


def compare(actual,reference,target,group):
    a=vectors(actual,target,group);b=vectors(reference,target,group,True)
    errors={key:max(abs(x-y)/(1e-14+1e-6*abs(y)) for x,y in zip(a[key],v)) for key,v in b.items()}
    device_errors={r['tag']:max(errors['v'+r['tag']+'p'+str(i)] for i in range(len(r['pins']))) for r in probes(target,group)}
    return dict(status='PASS' if all(v<=1 for v in errors.values()) else 'MISMATCH',channel_errors=errors,device_errors=device_errors,vectors=len(b),samples=len(actual['x']),maximum_normalized_error=max(errors.values()))


def case(tech,target,group,corner,temp,out,engine,osdi):
    name=f'{target}-{group}-{corner}-{temp}';folder=out/name;folder.mkdir();row=dict(name=name,target=target,group=group,corner=corner,temperature_c=temp,status='RUNNING',faults=[])
    try:
        p=fixture(tech,target,group,osdi);save_project(p,folder/'input.icproj');start,stop,step=sweep(group);settings=dict(type='dc',corner=corner,temperature=temp,source='VG',dc_start=str(start),dc_stop=str(stop),dc_step=str(step))
        for side in ('application','independent'):(folder/side).mkdir()
        actual=run_ngspice(p,p['top'],settings,engine,folder/'application');write(folder/'application/response.json',actual)
        lines=['* Independent explicit diode calls',*model_lines(tech,corner),'VG drive 0 0']
        for r in probes(target,group):
            tag=r['tag'];nodes=[tag+'p'+str(i) for i in range(len(r['pins']))]
            for i,node in enumerate(nodes):lines.append(f'V{node} {node} '+('drive' if i==(1 if group=='esd' else 0) else '0')+' '+voltage(group,i))
            lines.append(('D' if target.startswith('gf180') else 'X')+tag+' '+' '.join(nodes)+' '+r['name']+' '+r['manual'])
        lines += [f'.temp {temp}',f'.dc VG {start} {stop} {step}','.end','']
        ref=folder/'independent';text=preload(p,stage_model_deck(tech,'\n'.join(lines),ref),ref);(ref/'reference.cir').write_bytes(text.encode())
        expected=run_deck(p,p['top'],dict(deck=str(ref/'reference.cir'),analysis=settings),engine,ref);write(ref/'response.json',expected);row['comparison']=compare(actual,expected,target,group)
        if row['comparison']['status']!='PASS':raise ValueError('Independent diode response differs.')
        for fault in ('reversed-terminals','wrong-geometry'):
            q=clone(p)
            for d,r in zip([d for d in q['cells'][0]['devices'] if d.get('model_ref')],probes(target,group)):
                if fault=='reversed-terminals':
                    a,b=r['pins'][:2];d['nets'][a],d['nets'][b]=d['nets'][b],d['nets'][a]
                else:
                    key='m' if target.startswith('gf180') or group=='esd' else 'nx' if r['name']=='schottky_nbl1' else 'w'
                    if key=='w':d['model_params'][key]='2.34u'
                    else:d['model_params'][key]*=2
            dest=folder/fault;dest.mkdir();save_project(q,dest/'input.icproj');bad=run_ngspice(q,q['top'],settings,engine,dest);write(dest/'response.json',bad);comparison=compare(bad,expected,target,group)
            if not all(v>1 for v in comparison['device_errors'].values()):raise ValueError('Diode fault not detected for every device: '+fault)
            row['faults'].append(dict(name=fault,comparison=comparison,detected_devices=len(comparison['device_errors'])))
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--ngspice',required=True);ap.add_argument('--osdi',type=Path,required=True);ap.add_argument('--pilot',action='store_true');ap.add_argument('--isolation-only',action='store_true');ap.add_argument('--historical-isolation',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,9),default=4);a=ap.parse_args()
    if a.historical_isolation and not a.isolation_only:ap.error('--historical-isolation requires --isolation-only')
    os.environ['OMP_THREAD_LIMIT']='1';out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);osdi=configure(sorted(a.osdi.glob('*.osdi')))
    sources=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/prepare_ihp_isolation_qualification.py',ROOT/'scripts/prepare_ihp_mim_qualification.py',*sorted((ROOT/'icstudio').rglob('*.py'))];before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    report=dict(schema=1,chunk=7,status='RUNNING',chunk_complete=False,qualified=False,scope=__doc__,cases=[],processes={},source_files_sha256=file_digest(out/'source-files.json'),engine_sha256=file_digest(a.ngspice),osdi=osdi,environment={'OMP_THREAD_LIMIT':'1'})
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[]
        for target in (('ihp-sg13g2',) if a.isolation_only else ('gf180mcuC','gf180mcuD','ihp-sg13g2')):
            tech,identity=load_technology(target)
            if a.historical_isolation:
                from scripts.prepare_ihp_isolation_qualification import prepare
                folder=out/'isolation-package';identity=prepare(ROOT/'icstudio/assets/pdks/ihp-sg13g2',folder)
                package=json.loads((folder/'package.json').read_bytes());tech=clone(package['technology'])
                tech.update(package_root=str(folder),package_lock={k:package[k] for k in ('id','revision','files')})
            report['processes'][target]=identity
            for group in (('isolation',) if a.isolation_only else ('junction','esd') if target=='ihp-sg13g2' else ('junction',)):
                for corner in ('nominal',) if a.pilot else PROFILES[target]['corners']:
                    for temp in (27,) if a.pilot else (0,27,85):jobs.append(pool.submit(case,tech,target,group,corner,temp,out,a.ngspice,osdi))
        for future in as_completed(jobs):
            row=future.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};report['status']='PASS' if report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL';write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
