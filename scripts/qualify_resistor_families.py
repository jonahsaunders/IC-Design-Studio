"""Independent AC conductance, multiplicity and fault checks for resistor families.

Selected length, bias, temperature and corner points are not complete model
operating envelopes. References below are manual public-model calls, independent
of the application's symbol importer and emitter.
"""
import argparse,cmath,json,math,sys,traceback
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,file_digest,example,save_project
from icstudio.catalog import create_device
from icstudio.engines import run_ngspice,run_deck
from icstudio.osdi import configure,preload
from icstudio.pdks import model_lines,stage_model_deck
from scripts.qualify_standard_mos import load_technology,PROFILES,write

SKY_NAMES=['res_generic_'+s for s in ('m1','m2','m3','m4','nd','pd','po')]+['res_iso_pw']
SKY_NAMES += ['res_'+kind+'_po'+suffix for kind in ('high','xhigh') for suffix in ('','_0p35','_0p69','_1p41','_2p85','_5p73')]
GF_NAMES=['nplus_u','pplus_u','npolyf_s','npolyf_u','ppolyf_s','ppolyf_u','ppolyf_u_1k','ppolyf_u_1k_6p0','ppolyf_u_2k','ppolyf_u_2k_6p0','ppolyf_u_3k','nwell','rm1','rm2','rm3']
NAMES={'sky130A':SKY_NAMES,'gf180mcuC':GF_NAMES,'gf180mcuD':GF_NAMES,'ihp-sg13g2':['rppd','rhigh','rsil']}


def probes(target):
    for index,name in enumerate(NAMES[target]):
        fixed=name.rsplit('_',1)[-1] if target=='sky130A' and name.rsplit('_',1)[-1] in ('0p35','0p69','1p41','2p85','5p73') else None
        width=float(fixed.replace('p','.')) if fixed else (3 if name in ('nwell','res_iso_pw') else 2)
        for length in (5,20):
            for copies in (1,3):
                yield dict(name=name,tag=f'r{index}l{length}m{copies}',w=width,l=length,m=copies,fixed_width=bool(fixed))


def binding(target,row):
    name=row['name']
    if target=='sky130A':return 'sky130_fd_pr/'+name+'.sym',('m','p') if name in ('res_generic_m1','res_generic_m2','res_generic_m3','res_generic_m4','res_generic_po') else ('m','p','b'),'mult'
    if target.startswith('gf180'):return 'symbols/'+name+'.sym',('m','p') if name.startswith('rm') else ('m','p','b'),'m'
    return 'sg13g2_pr/'+name+'.sym',('p','m','body'),'m'


def manual(target,row):
    name,tag,w,l,m=(row[k] for k in ('name','tag','w','l','m'))
    if target=='sky130A':
        model='sky130_fd_pr__'+name
        if name in ('res_generic_m1','res_generic_m2','res_generic_m3','res_generic_m4','res_generic_po'):return f'R{tag} {tag} 0 {model} w={w:g} l={l:g} m={m}'
        size=f'l={l:g}'+('' if row['fixed_width'] else f' w={w:g}')
        return f'X{tag} {tag} 0 0 {model} {size} mult={m} m={m}'
    if target.startswith('gf180'):
        nodes=f'{tag} 0'+('' if name.startswith('rm') else ' 0')
        return f'X{tag} {nodes} {name} r_width={w:g}u r_length={l:g}u m={m}'
    extra='' if name=='rsil' else ' b=0'
    return f'X{tag} {tag} 0 0 {name} w={w:g}u l={l:g}u m={m} mm_ok=1{extra}'


def fixture(tech,target,bias,osdi):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c['name']='resistor_coupon';c['devices']=[]
    for row in probes(target):
        key,pins,mult=binding(target,row);tag=row['tag'];v=device('V','V'+tag,0,0,value=str(bias),nets={'p':tag,'n':'0'});v['source']['ac']='1'
        d=create_device(tech,key,'D'+tag);scale=1 if target=='sky130A' else 1e-6
        d['model_params'].update(l=row['l']*scale,**{mult:row['m']})
        if not row['fixed_width']:d['model_params']['w']=row['w']*scale
        d['nets']=dict(zip(pins,[tag]+['0']*(len(pins)-1)));c['devices'] += [v,d]
    if target=='ihp-sg13g2':p['simulation_runtime']={'osdi':clone(osdi)}
    return p


def vectors(data,target,positive=False):
    if len(data['x'])!=26 or any(not math.isfinite(v) or not math.isclose(v,100*10**(i/5),rel_tol=1e-9) for i,v in enumerate(data['x'])):raise ValueError('Incomplete resistor frequency sweep.')
    mags={k.lower():v for k,v in data['currents'].items()};phases={k.lower():v for k,v in data['current_phase'].items()};result={}
    for row in probes(target):
        key='v'+row['tag'];mag=mags.get(key,[]);phase=phases.get(key,[])
        if len(mag)!=26 or len(phase)!=26 or any(not math.isfinite(v) for v in mag+phase) or any(v<0 for v in mag):raise ValueError('Missing/invalid resistor current '+key)
        result[key]=[cmath.rect(m,math.radians(p)) for m,p in zip(mag,phase)]
        if positive and any(-v.real<1e-9 for v in result[key]):raise ValueError('No positive resistor conductance: '+key)
    return result


def compare(actual,expected,target):
    a=vectors(actual,target);b=vectors(expected,target,True)
    errors={k:max(abs(x-y)/(1e-15+1e-6*abs(y)) for x,y in zip(a[k],v)) for k,v in b.items()}
    return dict(status='PASS' if all(e<=1 for e in errors.values()) else 'MISMATCH',channel_errors=errors,maximum_normalized_error=max(errors.values()),vectors=len(errors),samples=26)


def scaling(data,target):
    v=vectors(data,target,True);errors={}
    for row in probes(target):
        if row['m']==3:
            k='v'+row['tag'];errors[k]=max(abs(a-3*b)/(1e-15+1e-6*abs(3*b)) for a,b in zip(v[k],v[k[:-1]+'1']))
    return dict(status='PASS' if all(e<=1 for e in errors.values()) else 'MISMATCH',
        pairs=len(errors),channel_errors=errors,maximum_normalized_error=max(errors.values()))


def altered(p,target,fault):
    q=clone(p)
    for row in probes(target):
        d=next(d for d in q['cells'][0]['devices'] if d['name']=='D'+row['tag'])
        if fault=='wrong-length':d['model_params']['l']*=1.2
        elif fault=='disconnected':d['nets'][binding(target,row)[1][0]]='0'
        else:raise ValueError('Unknown resistor fault.')
    return q


def case(tech,target,corner,temp,bias,out,engine,osdi):
    name=f'{target}-{corner}-{temp}-{bias:g}';folder=out/name;folder.mkdir();row=dict(name=name,target=target,corner=corner,temperature_c=temp,bias_v=bias,status='RUNNING',faults=[])
    try:
        p=fixture(tech,target,bias,osdi);save_project(p,folder/'input.icproj');settings=dict(type='ac',corner=corner,temperature=temp,start='100',end='10meg',points=5)
        for side in ('application','independent'):(folder/side).mkdir()
        a=run_ngspice(p,p['top'],settings,engine,folder/'application');write(folder/'application/response.json',a)
        lines=['* Independent public resistor calls',*model_lines(tech,corner)]
        for probe in probes(target):lines += [f'V{probe["tag"]} {probe["tag"]} 0 DC {bias:g} AC 1',manual(target,probe)]
        lines += [f'.temp {temp}','.ac dec 5 100 10meg','.end','']
        ref=folder/'independent';deck=preload(p,stage_model_deck(tech,'\n'.join(lines),ref),ref);(ref/'reference.cir').write_bytes(deck.encode())
        b=run_deck(p,p['top'],dict(deck=str(ref/'reference.cir'),analysis=settings),engine,ref);write(ref/'response.json',b)
        row['comparison']=compare(a,b,target)
        if row['comparison']['status']!='PASS':raise ValueError('Independent resistor comparison failed.')
        row['scaling']={side:scaling(data,target) for side,data in [('application',a),('independent',b)]}
        for fault in ('wrong-length','disconnected'):
            dest=folder/fault;dest.mkdir();q=altered(p,target,fault);save_project(q,dest/'input.icproj');measured=run_ngspice(q,q['top'],settings,engine,dest);write(dest/'response.json',measured)
            comparison=compare(measured,b,target)
            if not all(e>1 for e in comparison['channel_errors'].values()):raise ValueError('Resistor fault not detected on every channel: '+fault)
            row['faults'].append(dict(name=fault,detected=True,comparison=comparison))
        row['status']='PASS' if all(item['status']=='PASS' for item in row['scaling'].values()) else 'FAIL'
        if row['status']=='FAIL':row['error']='Independent manual-call agreement passes, but physical parallel scaling fails; affected channels remain unqualified.'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--ngspice',required=True);ap.add_argument('--osdi',type=Path,required=True);ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,5),default=2)
    ap.add_argument('--targets',nargs='+',choices=NAMES,default=list(NAMES));ap.add_argument('--sky130-adapter',type=Path);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);osdi=configure(sorted(a.osdi.glob('*.osdi')))
    sources=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))];before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    report=dict(schema=1,chunk=7,status='RUNNING',chunk_complete=False,qualified=False,cases=[],processes={},devices=NAMES,source_files_sha256=file_digest(out/'source-files.json'),engine_sha256=file_digest(a.ngspice),osdi=osdi,scope=__doc__)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs=[]
        for target in a.targets:
            if target=='sky130A' and a.sky130_adapter:
                from icstudio.pdks import PDKRegistry
                registry=PDKRegistry(out/'registry');key=registry.install(a.sky130_adapter);tech=registry.technology(key)
                if tech['package_lock']['id']!='sky130A':raise ValueError('The adapter must be a SKY130 package.')
                identity=dict(target=target,revision=tech['revision'],manifest_sha256=file_digest(a.sky130_adapter))
            else:tech,identity=load_technology(target)
            report['processes'][target]=identity
            for corner in ('nominal',) if a.pilot else PROFILES[target]['corners']:
                for temp in (27,) if a.pilot else (0,27,85):
                    for bias in (.1,) if a.pilot else (.1,.5):jobs.append(pool.submit(case,tech,target,corner,temp,bias,out,a.ngspice,osdi))
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['cases'] and report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL';report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
