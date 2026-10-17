"""Selected fixed-layout SKY130 VPP and IHP SVaricap terminal integration.

References explicitly follow public subcircuit terminals, not the symbol order.
Nx is a model geometry input, not an assertion of parallel-unit equivalence.
"""
import argparse,json,sys,traceback
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,example,file_digest,save_project
from icstudio.catalog import create_device
from icstudio.engines import run_ngspice,run_deck
from icstudio.pdks import model_lines,stage_model_deck
from icstudio.osdi import configure,preload
from scripts.qualify_standard_mos import load_technology,PROFILES,write
from scripts.qualify_capacitor_families import compare


def probes(target):
    for shape in ((0,) if target=='sky130A' else (0,1)):
        for copies in (1,3):
            if target=='sky130A':
                yield dict(tag=f'c0s{shape}m{copies}',key='sky130_fd_pr/vpp_cap.sym',pins=['c0','c1','top','sub'],
                    params=dict(mult=copies),reference_order=[0,1,3,2],model='sky130_fd_pr__cap_vpp_11p5x11p7_l1m1m2m3m4_shieldm5',
                    manual=f'mult={copies} m={copies}',fault_parameter='mult')
            else:
                w,l=(3.74,.3) if shape==0 else (9.74,.8)
                yield dict(tag=f'c0s{shape}m{copies}',key='sg13g2_pr/sg13_svaricap.sym',pins=['g2','nw','g1','body'],
                    params=dict(w=w*1e-6,l=l*1e-6,nx=copies,mm_ok=1),reference_order=[2,1,0,3],
                    model='sg13_hv_svaricap',manual=f'w={w:g}u l={l:g}u nx={copies} mm_ok=1',fault_parameter='nx')


def fixture(tech,target,drive,bias,osdi):
    p=example('empty');p['pdk']=clone(tech);p['cells'][0]['devices']=[]
    for index,row in enumerate(probes(target)):
        d=create_device(tech,row['key'],'D'+row['tag'],index*800,0);d['model_params'].update(row['params'])
        d['nets']={pin:row['tag']+'p'+str(i) for i,pin in enumerate(row['pins'])}
        for i,pin in enumerate(row['pins']):
            value=bias if i==0 else .25 if i==2 else -.2 if i==3 else 0
            v=device('V','V'+row['tag']+'p'+str(i),index*800+i*130,400,value=str(value),nets={'p':d['nets'][pin],'n':'0'})
            v['source']['ac']='1' if i==drive else '0';p['cells'][0]['devices'].append(v)
        p['cells'][0]['devices'].append(d)
    if target=='ihp-sg13g2':p['simulation_runtime']={'osdi':clone(osdi)}
    return p


def independent(tech,target,drive,bias,corner,temp):
    lines=['* Explicit model-terminal reference',*model_lines(tech,corner)]
    for row in probes(target):
        nodes=[row['tag']+'p'+str(i) for i in range(4)]
        for i,node in enumerate(nodes):
            value=bias if i==0 else .25 if i==2 else -.2 if i==3 else 0
            lines.append(f'V{node} {node} 0 DC {value:g} AC {int(i==drive)}')
        lines.append('X'+row['tag']+' '+' '.join(nodes[i] for i in row['reference_order'])+' '+row['model']+' '+row['manual'])
    return '\n'.join([*lines,f'.temp {temp}','.ac dec 5 100 10meg','.end',''])


def case(tech,target,drive,bias,corner,temp,out,engine,osdi):
    name=f'{target}-port{drive}-{bias:g}-{corner}-{temp}';folder=out/name;folder.mkdir()
    record=dict(name=name,target=target,drive=drive,bias_v=bias,corner=corner,temperature_c=temp,status='RUNNING')
    rows=list(probes(target))
    try:
        p=fixture(tech,target,drive,bias,osdi);save_project(p,folder/'input.icproj')
        settings=dict(type='ac',corner=corner,temperature=temp,start='100',end='10meg',points=5)
        app,ref=folder/'application',folder/'independent';app.mkdir();ref.mkdir()
        a=run_ngspice(p,p['top'],settings,engine,app)
        text=preload(p,stage_model_deck(tech,independent(tech,target,drive,bias,corner,temp),ref),ref)
        path=ref/'reference.cir';path.write_bytes(text.encode())
        b=run_deck(p,p['top'],dict(deck=str(path),analysis=settings),engine,ref)
        write(app/'comparison-result.json',a);write(ref/'comparison-result.json',b)
        record['comparison']=compare(a,b,rows,drive)
        if record['comparison']['status']!='PASS':raise ValueError('Independent four-terminal response differs.')
        record['raw_sha256']=dict(application=file_digest(app/'result.raw'),independent=file_digest(ref/'deck.raw'))
        record['faults']=[]
        for fault in ('wrong-multiplicity','ground-driven-terminal'):
            q=clone(p)
            for row in rows:
                d=next(d for d in q['cells'][0]['devices'] if d['name']=='D'+row['tag'])
                if fault=='wrong-multiplicity':d['model_params'][row['fault_parameter']]*=2
                else:d['nets'][row['pins'][drive]]='0'
            dest=folder/fault;dest.mkdir();save_project(q,dest/'input.icproj')
            changed=run_ngspice(q,q['top'],settings,engine,dest);write(dest/'comparison-result.json',changed)
            check=compare(changed,b,rows,drive)
            if not all(e>1 for e in check['device_errors'].values()):raise ValueError('Undetected four-terminal fault: '+fault)
            record['faults'].append(dict(fault=fault,status='detected',comparison=check,raw_sha256=file_digest(dest/'result.raw')))
        record['status']='PASS'
    except Exception as error:record.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',record);return record


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--ngspice',required=True);ap.add_argument('--osdi',type=Path,required=True)
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--correct-vpp',action='store_true');ap.add_argument('--correct-svaricap',action='store_true');ap.add_argument('--targets',nargs='+',choices=['sky130A','ihp-sg13g2'],default=['sky130A','ihp-sg13g2']);ap.add_argument('--workers',type=int,choices=range(1,9),default=4);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);osdi=configure(sorted(a.osdi.glob('*.osdi')))
    sources=[Path(__file__),ROOT/'scripts/prepare_sky130_vpp_binding.py',ROOT/'scripts/prepare_sky130_parallel_varactors.py',ROOT/'scripts/prepare_ihp_svaricap_binding.py',ROOT/'scripts/prepare_ihp_isolation_qualification.py',ROOT/'scripts/prepare_ihp_mim_qualification.py',ROOT/'scripts/qualify_capacitor_families.py',ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    report=dict(schema=1,chunk=7,status='RUNNING',chunk_complete=False,qualified=False,processes={},cases=[],engine_sha256=file_digest(a.ngspice),source_files_sha256=file_digest(out/'source-files.json'),
        scope='Selected complex terminal integration for one fixed-layout SKY130 VPP model and IHP SVaricap. No full geometry/bias/reliability/statistical/RF-band or physical qualification.',probes={t:list(probes(t)) for t in a.targets},osdi=osdi)
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[]
        for target in a.targets:
            tech,identity=load_technology(target)
            if target=='sky130A' and a.correct_vpp:
                from scripts.prepare_sky130_vpp_binding import prepare
                root=out/'vpp-package';identity.update(prepare(ROOT/'icstudio/assets/pdks/sky130A',root));package=json.loads((root/'package.json').read_bytes());tech=clone(package['technology']);tech.update(package_root=str(root),package_lock={k:package[k] for k in ('id','revision','files')})
            if target=='ihp-sg13g2' and a.correct_svaricap:
                from scripts.prepare_ihp_svaricap_binding import prepare
                root=out/'svaricap-package';identity.update(prepare(ROOT/'icstudio/assets/pdks/ihp-sg13g2',root));package=json.loads((root/'package.json').read_bytes());tech=clone(package['technology']);tech.update(package_root=str(root),package_lock={k:package[k] for k in ('id','revision','files')})
            report['processes'][target]=identity
            for drive in range(4):
                for bias in ((.5,) if a.pilot else (-.5,.5)):
                    for corner in (('nominal',) if a.pilot else PROFILES[target]['corners']):
                        for temp in ((27,) if a.pilot else (0,27,85)):
                            jobs.append(pool.submit(case,tech,target,drive,bias,corner,temp,out,a.ngspice,osdi))
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['cases'] and report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report);return int(report['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
