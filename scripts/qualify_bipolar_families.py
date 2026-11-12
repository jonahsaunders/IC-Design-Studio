"""Selected bipolar terminal-current comparisons, KCL and connection controls.

This tests application integration with independent calls to the same public
models. Selected points are not full operating envelopes or silicon validation.
IHP NX represents emitter geometry, not a promise of independent parallel units;
five-terminal HBT thermal ports are clamped to zero temperature rise here.
"""
import argparse,json,math,sys,traceback
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,example,file_digest,save_project
from icstudio.catalog import create_device
from icstudio.engines import run_ngspice,run_deck
from icstudio.osdi import configure,preload
from icstudio.pdks import model_lines,stage_model_deck
from scripts.qualify_standard_mos import load_technology,PROFILES,write

GF=['npn_00p54x02p00','npn_00p54x04p00','npn_00p54x08p00','npn_00p54x16p00','npn_05p00x05p00','npn_10p00x10p00',
    'pnp_05p00x00p42','pnp_05p00x05p00','pnp_10p00x00p42','pnp_10p00x10p00']
NAMES={'sky130A':['npn_05v5','pnp_05v5'],'gf180mcuC':GF,'gf180mcuD':GF,
    'ihp-sg13g2':['npn13G2','npn13G2_5t','npn13G2l','npn13G2l_5t','npn13G2v','npn13G2v_5t','pnpMPA']}


def probes(target,polarity):
    for i,name in enumerate(NAMES[target]):
        if not name.startswith('npn' if polarity=='n' else 'pnp'):continue
        for factor in (1,) if target=='sky130A' and polarity=='n' else (1,3):
            yield dict(name=name,tag=f'q{i}m{factor}',factor=factor,polarity=polarity)


def definition(target,row):
    name=row['name'];pnp=row['polarity']=='p';pins=('collector','base','emitter') if pnp and target in ('sky130A','ihp-sg13g2') else ('c','b','e')
    if not pnp:pins+=('s',)
    if name.endswith('_5t'):pins+=('t',)
    prefix='sky130_fd_pr/' if target=='sky130A' else 'sg13g2_pr/' if target=='ihp-sg13g2' else 'symbols/'
    return prefix+name+'.sym',pins


def manual(target,row):
    name=row['name'];tag=row['tag'];factor=row['factor'];_,pins=definition(target,row)
    nodes=' '.join(tag+p for p in ('c','b','e')+(() if row['polarity']=='p' else ('s',)))+(' 0' if 't' in pins else '')
    if target=='sky130A':
        model='sky130_fd_pr__'+('npn_05v5_w1p00l2p00' if row['polarity']=='n' else 'pnp_05v5_W3p40L3p40');params='' if row['polarity']=='n' else f' m={factor}'
    elif target.startswith('gf180'):model=name;params=f' m={factor}'
    else:
        model=name
        if row['polarity']=='p':params=f' a=1.4e-12 p=5.4e-6 m={factor}'
        else:params=f' nx={factor} mm_ok=1'+(' el=1' if name.startswith(('npn13G2l','npn13G2v')) else '')
    return f'X{tag} {nodes} {model}{params}'


def fixture(tech,target,polarity,collector,osdi):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c['devices']=[device('V','VB',0,0,value='0',nets={'p':'drive','n':'0'})]
    sign=1 if polarity=='n' else -1
    for row in probes(target,polarity):
        tag=row['tag'];key,pins=definition(target,row);d=create_device(tech,key,'D'+tag)
        d['nets']=dict(zip(pins,[tag+x for x in ('c','b','e')+(() if polarity=='p' else ('s',))]+(['0'] if 't' in pins else [])))
        if target=='ihp-sg13g2' and polarity=='n':
            d['model_params']['nx']=row['factor']
            if row['name'].startswith(('npn13G2l','npn13G2v')):d['model_params']['el']=1
        elif not(target=='sky130A' and polarity=='n'):d['model_params']['m']=row['factor']
        for pin in ('c','b','e')+(() if polarity=='p' else ('s',)):
            c['devices'].append(device('V','V'+tag+pin,0,0,value=str(sign*collector if pin=='c' else 0),nets={'p':tag+pin,'n':'drive' if pin=='b' else '0'}))
        c['devices'].append(d)
    if target=='ihp-sg13g2':p['simulation_runtime']={'osdi':clone(osdi)}
    return p


def vectors(data,target,polarity,physical=False):
    sign=1 if polarity=='n' else -1
    if len(data['x'])!=31 or any(not math.isfinite(v) or not math.isclose(v,sign*(.45+i*.01),abs_tol=1e-9) for i,v in enumerate(data['x'])):raise ValueError('Incomplete bipolar base sweep.')
    currents={k.lower():v for k,v in data['currents'].items()};out={}
    for row in probes(target,polarity):
        keys=['v'+row['tag']+pin for pin in ('c','b','e')+(() if polarity=='p' else ('s',))]
        for key in keys:
            v=currents.get(key,[])
            if len(v)!=31 or any(not math.isfinite(x) for x in v):raise ValueError('Missing/nonfinite bipolar terminal current: '+key)
            out[key]=v
        if physical:
            ic=out[keys[0]];ib=out[keys[1]]
            if -sign*ic[-1]<1e-9 or abs(ic[-1])<10*max(abs(ic[0]),1e-15) or abs(ib[-1])<1e-15:raise ValueError('Missing bipolar forward turn-on or base current: '+row['tag'])
            if abs(ic[-1]/ib[-1])<.1:raise ValueError('Bipolar current gain below this fixture sanity bound.')
            for sample in zip(*(out[k] for k in keys)):
                if abs(sum(sample))>1e-10+1e-6*max(abs(v) for v in sample):raise ValueError('Bipolar electrical terminals violate KCL: '+row['tag'])
    return out


def compare(actual,expected,target,polarity):
    a=vectors(actual,target,polarity);b=vectors(expected,target,polarity,True)
    errors={k:max(abs(x-y)/(1e-12+1e-6*abs(y)) for x,y in zip(a[k],v)) for k,v in b.items()}
    return dict(status='PASS' if all(e<=1 for e in errors.values()) else 'MISMATCH',terminal_vectors=len(errors),samples=31,channel_errors=errors,maximum_normalized_error=max(errors.values()))


def case(tech,target,polarity,corner,temp,collector,out,engine,osdi):
    name=f'{target}-{polarity}-{corner}-{temp}-{collector:g}';folder=out/name;folder.mkdir();row=dict(name=name,target=target,polarity=polarity,corner=corner,temperature_c=temp,collector_magnitude_v=collector,status='RUNNING',faults=[])
    try:
        p=fixture(tech,target,polarity,collector,osdi);save_project(p,folder/'input.icproj');sign=1 if polarity=='n' else -1
        settings=dict(type='dc',corner=corner,temperature=temp,source='VB',dc_start=str(sign*.45),dc_stop=str(sign*.75),dc_step=str(sign*.01))
        for side in ('application','independent'):(folder/side).mkdir()
        actual=run_ngspice(p,p['top'],settings,engine,folder/'application');write(folder/'application/response.json',actual)
        lines=['* Independent public bipolar calls',*model_lines(tech,corner),'VB drive 0 0']
        for probe in probes(target,polarity):
            tag=probe['tag']
            for pin in ('c','b','e')+(() if polarity=='p' else ('s',)):lines.append(f'V{tag+pin} {tag+pin} '+('drive' if pin=='b' else '0')+f' {sign*collector if pin=="c" else 0:g}')
            lines.append(manual(target,probe))
        lines += [f'.temp {temp}',f'.dc VB {sign*.45:g} {sign*.75:g} {sign*.01:g}','.end',''];ref=folder/'independent';deck=preload(p,stage_model_deck(tech,'\n'.join(lines),ref),ref);(ref/'reference.cir').write_bytes(deck.encode())
        expected=run_deck(p,p['top'],dict(deck=str(ref/'reference.cir'),analysis=settings),engine,ref);write(ref/'response.json',expected);row['comparison']=compare(actual,expected,target,polarity)
        if row['comparison']['status']!='PASS':raise ValueError('Bipolar independent currents differ.')
        vectors(actual,target,polarity,True)
        for fault in ('base-emitter-short','collector-emitter-swap'):
            q=clone(p)
            for d in q['cells'][0]['devices']:
                if not d.get('model_ref'):continue
                c,b,e=('collector','base','emitter') if 'collector' in d['nets'] else ('c','b','e')
                if fault=='base-emitter-short':d['nets'][b]=d['nets'][e]
                else:d['nets'][c],d['nets'][e]=d['nets'][e],d['nets'][c]
            dest=folder/fault;dest.mkdir();save_project(q,dest/'input.icproj');bad=run_ngspice(q,q['top'],settings,engine,dest);write(dest/'response.json',bad);comparison=compare(bad,expected,target,polarity)
            channels=['v'+probe['tag']+'c' for probe in probes(target,polarity)]
            if not all(comparison['channel_errors'][k]>1 for k in channels):raise ValueError('Bipolar connection fault not detected on every device.')
            row['faults'].append(dict(name=fault,detected_devices=len(channels),comparison=comparison))
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--ngspice',required=True);p.add_argument('--osdi',type=Path,required=True);p.add_argument('--pilot',action='store_true');p.add_argument('--workers',type=int,choices=range(1,5),default=2)
    p.add_argument('--targets',nargs='+',choices=NAMES,default=list(NAMES));p.add_argument('--sky130-adapter',type=Path);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);osdi=configure(sorted(a.osdi.glob('*.osdi')));sources=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))];before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    report=dict(schema=1,chunk=7,status='RUNNING',qualified=False,chunk_complete=False,scope=__doc__,cases=[],processes={},source_files_sha256=file_digest(out/'source-files.json'),engine_sha256=file_digest(a.ngspice),osdi=osdi,devices=NAMES)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs=[]
        for target in a.targets:
            if target=='sky130A' and a.sky130_adapter:
                from icstudio.pdks import PDKRegistry
                registry=PDKRegistry(out/'registry');key=registry.install(a.sky130_adapter);tech=registry.technology(key)
                if tech['package_lock']['id']!='sky130A':raise ValueError('The adapter must be SKY130.')
                identity=dict(target=target,revision=tech['revision'],manifest_sha256=file_digest(a.sky130_adapter))
            else:tech,identity=load_technology(target)
            report['processes'][target]=identity
            for polarity in ('n','p'):
                for corner in ('nominal',) if a.pilot else PROFILES[target]['corners']:
                    for temp in (27,) if a.pilot else (0,27,85):
                        for collector in (.6,) if a.pilot else (.6,1.2):jobs.append(pool.submit(case,tech,target,polarity,corner,temp,collector,out,a.ngspice,osdi))
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error','')[:240],flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};report['status']='PASS' if report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL';write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
