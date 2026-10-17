"""Independently test every newly exposed source-listed electrical model view.

Selected terminal/parameter integration, not complete operating, physical,
statistical, metal-option or silicon qualification. All checks execute locally.
"""
import argparse,json,math,sys,traceback
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,example,file_digest,save_project
from icstudio.catalog import create_device
from icstudio.engines import run_ngspice,run_deck
from icstudio.pdks import model_lines,stage_model_deck
from icstudio.ngspice_compat import behavior
from scripts.prepare_alternate_models import prepare,alias_key,NOTE
from scripts.qualify_standard_mos import write
from scripts.qualify_capacitor_families import compare as compare_ac
from scripts.qualify_catalog_interfaces import one as interface

# Independent references transcribed from the locked source declarations.
# Do not derive these contracts from the newly emitted catalog bindings.
DIODES=('diode_pd2nw_05v5','diode_pd2nw_05v5_hvt','diode_pd2nw_05v5_lvt',
        'diode_pd2nw_11v0','diode_pw2nd_05v5_lvt','diode_pw2nd_05v5_nvt',
        'diode_pw2nd_11v0','model__parasitic__diode_ps2dn',
        'model__parasitic__diode_ps2nw','model__parasitic__diode_pw2dn')
LVS_DIODES=('diode_pd2nw_05v5','diode_pd2nw_11v0','diode_pw2nd_11v0','model__parasitic__diode_ps2dn')
VPP=('04p4x04p6_m1m2m3_shieldl1m5_floatm4','06p8x06p1_l1m1m2m3_shieldpom4',
     '06p8x06p1_m1m2m3_shieldl1m4','08p6x07p8_m1m2m3_shieldl1m5_floatm4',
     '11p5x11p7_l1m1m2m3_shieldm4','11p5x11p7_l1m1m2m3m4_shieldpom5',
     '11p5x11p7_m1m2m3_shieldl1m5_floatm4','11p5x11p7_m1m2m3m4_shieldl1m5')


def probes(target,family):
    if family=='diode':
        entries=[(s,'sky130_fd_pr__'+m) for s,names in [('diode',DIODES),('lvsdiode',LVS_DIODES)] for m in names]
    elif target=='sky130A':entries=[('vpp_cap','sky130_fd_pr__cap_vpp_'+m) for m in VPP]
    else:entries=[('cap_mim_analog',f'cap_mim_{density}_m{level}m{level+1}_noshield')
                 for density in ('1f0','1f5','2f0') for level in (2,3,4,5) if (density,level)!=('2f0',3)]
    for index,(symbol,model) in enumerate(entries):
        parent=('sky130_fd_pr/' if target=='sky130A' else 'symbols/')+symbol+'.sym'
        for shape in ((0,1) if target!='sky130A' else (0,)):
            for copies in (1,3):
                if family=='diode':
                    pins=['d0','d1'];params=dict(area=copies*1e12);manual=f'area={copies*1e12:g}'
                elif target=='sky130A':
                    pins=['c0','c1','top','sub'];params=dict(mult=copies);manual=f'mult={copies} m={copies}'
                else:
                    w,l=(2,2) if shape==0 else (7,7)
                    pins=['g','b'];params=dict(w=w*1e-6,l=l*1e-6,m=copies);manual=f'c_width={w}u c_length={l}u m={copies}'
                yield dict(tag=f'c{index}s{shape}m{copies}',key=alias_key(parent,model),model=model,
                           prefix='D' if family=='diode' else 'X',pins=pins,params=params,manual=manual,
                           reference_order=[0,1,3,2] if target=='sky130A' and family=='capacitor' else list(range(len(pins))))


def fixture(tech,rows,family,drive,bias):
    p=example('empty');p['pdk']=clone(tech);p['cells'][0]['devices']=[];devices=p['cells'][0]['devices']
    if family=='diode':devices.append(device('V','VG',value='0',nets={'p':'drive','n':'0'}))
    for r in rows:
        d=create_device(tech,r['key'],'D'+r['tag']);d['model_params'].update(r['params'])
        d['nets']={pin:r['tag']+'p'+str(i) for i,pin in enumerate(r['pins'])}
        for i,pin in enumerate(r['pins']):
            value=0 if family=='diode' else bias if i==0 else .25 if i==2 else -.2 if i==3 else 0
            v=device('V','V'+r['tag']+'p'+str(i),value=str(value),nets={'p':d['nets'][pin],'n':'drive' if family=='diode' and i==0 else '0'})
            v['source']['ac']=str(int(i==drive));devices.append(v)
        devices.append(d)
    return p


def independent(tech,rows,family,drive,bias,corner,temp,area_scale):
    lines=['* Explicit alternate model contracts',*model_lines(tech,corner)]
    if family=='diode':lines.append('VG drive 0 0')
    for r in rows:
        nodes=[r['tag']+'p'+str(i) for i in range(len(r['pins']))]
        for i,node in enumerate(nodes):
            value=0 if family=='diode' else bias if i==0 else .25 if i==2 else -.2 if i==3 else 0
            lines.append(f'V{node} {node} '+('drive' if family=='diode' and i==0 else '0')+f' DC {value:g} AC {int(i==drive)}')
        manual=f"area={r['params']['area']*area_scale:.12g}" if family=='diode' else r['manual']
        lines.append(r['prefix']+r['tag']+' '+' '.join(nodes[i] for i in r['reference_order'])+' '+r['model']+' '+manual)
    return '\n'.join([*lines,f'.temp {temp}', '.dc VG -.2 .8 .025' if family=='diode' else '.ac dec 5 100 10meg','.end',''])


def compare_dc(actual,reference,rows):
    def vectors(data,physical):
        x=data.get('x',[])
        if len(x)!=41 or any(not math.isfinite(v) or not math.isclose(v,-.2+i*.025,abs_tol=1e-9) for i,v in enumerate(x)):
            raise ValueError('Incomplete diode voltage domain.')
        data={k.casefold():v for k,v in data.get('currents',{}).items()};result={}
        for r in rows:
            for i in (0,1):
                key='v'+r['tag']+'p'+str(i);values=data.get(key,[])
                if len(values)!=41 or any(not math.isfinite(v) for v in values):raise ValueError('Invalid diode terminal current.')
                result[key]=values
            a,b=[result['v'+r['tag']+'p'+str(i)] for i in (0,1)]
            # Measurable rectification relative to the actual comparison floor.
            # A fixed 100 nA minimum incorrectly rejects valid cold P diodes.
            # This is a response-sanity check, not a silicon current specification.
            if physical and (a[-1]>=-100*1e-14 or abs(a[-1])<=100*max(abs(a[0]),1e-15)):
                raise ValueError('Reference lacks forward conduction/rectification: '+r['tag'])
            if physical and any(abs(u+v)>1e-14+1e-6*max(abs(u),abs(v)) for u,v in zip(a,b)):
                raise ValueError('Reference diode violates terminal KCL.')
        return result
    a,b=vectors(actual,False),vectors(reference,True)
    errors={k:max(abs(u-v)/(1e-14+1e-6*abs(v)) for u,v in zip(a[k],b[k])) for k in b}
    per={r['tag']:max(errors['v'+r['tag']+'p'+str(i)] for i in (0,1)) for r in rows}
    return dict(status='PASS' if max(errors.values())<=1 else 'MISMATCH',channel_errors=errors,device_errors=per,
                maximum_normalized_error=max(errors.values()),vectors=len(errors),samples=41,relative_tolerance=1e-6,absolute_tolerance_a=1e-14)


def case(tech,target,family,drive,bias,corner,temp,out,engine,area_scale):
    name=f'{target}-{family}-port{drive}-{bias:g}-{corner}-{temp}';folder=out/name;folder.mkdir()
    record=dict(name=name,target=target,family=family,drive=drive,bias_v=bias,corner=corner,temperature_c=temp,status='RUNNING')
    rows=list(probes(target,family));compare=(lambda a,b:compare_dc(a,b,rows)) if family=='diode' else (lambda a,b:compare_ac(a,b,rows,drive))
    try:
        p=fixture(tech,rows,family,drive,bias);save_project(p,folder/'input.icproj')
        settings=dict(type='dc',corner=corner,temperature=temp,source='VG',dc_start='-.2',dc_stop='.8',dc_step='.025') if family=='diode' else dict(type='ac',corner=corner,temperature=temp,start='100',end='10meg',points=5)
        app,ref=folder/'application',folder/'independent';app.mkdir();ref.mkdir()
        a=run_ngspice(p,p['top'],settings,engine,app)
        path=ref/'reference.cir';path.write_bytes(stage_model_deck(tech,independent(tech,rows,family,drive,bias,corner,temp,area_scale),ref).encode())
        b=run_deck(p,p['top'],dict(deck=str(path),analysis=settings),engine,ref)
        write(app/'comparison-result.json',a);write(ref/'comparison-result.json',b);record['comparison']=compare(a,b)
        if record['comparison']['status']!='PASS':raise ValueError('Independent alternate-model response differs.')
        record['faults']=[]
        for fault in ('wrong-parameter','wrong-connection'):
            q=clone(p)
            for r in rows:
                d=next(d for d in q['cells'][0]['devices'] if d['name']=='D'+r['tag'])
                if fault=='wrong-parameter':d['model_params']['area' if family=='diode' else 'mult' if target=='sky130A' else 'm']*=1.5
                elif family=='diode':d['nets']['d0'],d['nets']['d1']=d['nets']['d1'],d['nets']['d0']
                else:d['nets'][r['pins'][drive]]='0'
            dest=folder/fault;dest.mkdir();save_project(q,dest/'input.icproj')
            changed=run_ngspice(q,q['top'],settings,engine,dest);write(dest/'comparison-result.json',changed);control=compare(changed,b)
            if not all(v>1 for v in control['device_errors'].values()):raise ValueError('Undetected alternate-model fault: '+fault)
            record['faults'].append(dict(fault=fault,status='detected',comparison=control))
        record['status']='PASS'
    except Exception as error:record.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',record);return record


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--ngspice',required=True)
    ap.add_argument('--packages',type=Path,help='Previously prepared alternate packages; otherwise build new packages.')
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,9),default=4)
    ap.add_argument('--families',nargs='+',choices=['diode','capacitor'],default=['diode','capacitor'])
    ap.add_argument('--targets',nargs='+',choices=['sky130A','gf180mcuC','gf180mcuD'],default=['sky130A','gf180mcuC','gf180mcuD']);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'scripts/prepare_alternate_models.py',ROOT/'scripts/alternate_model_source.py',ROOT/'scripts/inventory_device_models.py',ROOT/'scripts/qualify_capacitor_families.py',ROOT/'scripts/qualify_catalog_interfaces.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    convention=behavior(a.ngspice,out);area_scale=1e-12 if convention['mode']=='unscaled-explicit-area' else 1
    report=dict(schema=1,chunk=7,status='RUNNING',chunk_complete=False,qualified=False,scope=__doc__,processes={},cases=[],interfaces=[],
                engine_sha256=file_digest(a.ngspice),source_files_sha256=file_digest(out/'source-files.json'),geometry_convention=convention)
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[]
        for target in a.targets:
            root=(a.packages/target).resolve() if a.packages else out/'packages'/target
            if not a.packages:prepare(ROOT/'icstudio/assets/pdks'/target,root)
            package=json.loads((root/'package.json').read_bytes());note=json.loads((root/NOTE).read_bytes())
            if file_digest(root/NOTE)!=package['files'][NOTE] or any(file_digest(root/rel)!=h for rel,h in package['files'].items()):raise ValueError('Changed alternate package.')
            tech=clone(package['technology']);tech.update(package_root=str(root),package_lock={k:package[k] for k in ('id','revision','files')})
            report['processes'][target]=dict(revision=package['revision'],manifest_sha256=file_digest(root/'package.json'),choices=note['choices'])
            expected={r['key'] for f in (('diode','capacitor') if target=='sky130A' else ('capacitor',)) for r in probes(target,f)}
            if expected!={r['device'] for r in note['choices'] if r['status']=='AVAILABLE'}:raise ValueError('Independent probe inventory differs from prepared choices.')
            for row in note['choices']:
                check=interface(tech,row['device'],out/'interfaces'/target/Path(row['device']).stem);check['target']=target;report['interfaces'].append(check)
            for family in (('diode','capacitor') if target=='sky130A' else ('capacitor',)):
                if family not in a.families:continue
                for drive in (range(1) if family=='diode' else range(4 if target=='sky130A' else 2)):
                    for bias in ((.5,) if a.pilot or family=='diode' else (-.5,.5)):
                        for corner in (('nominal',) if a.pilot else ('nominal','ss','ff')):
                            for temp in ((27,) if a.pilot else (0,27,85)):
                                jobs.append(pool.submit(case,tech,target,family,drive,bias,corner,temp,out,a.ngspice,area_scale))
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['cases'] and report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']) and all(r['status'] in ('PASS','EXPECTED_UNSUPPORTED') for r in report['interfaces']) else 'FAIL'
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report);return int(report['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
