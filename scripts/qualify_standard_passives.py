"""Independent complex admittance checks for selected resistor/capacitor models.

The geometry, bias and frequency points are test selections, not full device
operating limits. Manual reference calls do not use the catalog's emitter.
"""
import argparse,cmath,json,math,sys,traceback
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,device,example,file_digest,save_project
from icstudio.catalog import create_device
from icstudio.engines import run_ngspice,run_deck
from icstudio.osdi import configure,preload
from icstudio.pdks import model_lines,stage_model_deck
from scripts.qualify_standard_mos import load_technology,PROFILES,write

DEVICES={
    'sky130A':{'res':('sky130_fd_pr/res_generic_po.sym',('m','p'),'mult'),
               'cap':('sky130_fd_pr/cap_mim_m3_1.sym',('c0','c1'),'mf')},
    'gf180mcuC':{'res':('symbols/ppolyf_u_1k.sym',('m','p','b'),'m'),
                 'cap':('symbols/cap_mim_1f5fF.sym',('g','b'),'m')},
    'gf180mcuD':{'res':('symbols/ppolyf_u_1k.sym',('m','p','b'),'m'),
                 'cap':('symbols/cap_mim_1f5fF.sym',('g','b'),'m')},
    'ihp-sg13g2':{'res':('sg13g2_pr/rppd.sym',('p','m','body'),'m'),
                  'cap':('sg13g2_pr/cap_cmim.sym',('c0','c1'),'m')},
}
for _target in ('gf180mcuC','gf180mcuD'):
    DEVICES[_target].update({kind:('symbols/'+symbol+'.sym',('g','b'),'m') for kind,symbol in (
        ('cap10','cap_mim_1f0fF'),('cap20','cap_mim_2f0fF'),
        ('cap20alias','cap_mim_2p0fF'),('capstack','cap_mim_analog'))})
GF_CAP_MODELS={'cap':'cap_mim_1f5fF','cap10':'cap_mim_1f0fF','cap20':'cap_mim_2f0fF',
    'cap20alias':'cap_mim_2f0fF','capstack':'cap_mim_2f0_m3m4_noshield'}
GEOMETRIES={'res':((.5,2),(1,10),(2,20)),'cap':((2,2),(7,7),(10,10))}
RELATIVE_TOLERANCE=1e-6
ABSOLUTE_TOLERANCE=1e-15
FAULTS=('wrong-width','disconnected-terminal')


def points(target='sky130A'):
    for kind in DEVICES[target]:
        sizes=GEOMETRIES['res' if kind=='res' else 'cap']
        for index,(w,l) in enumerate(sizes):
            for copies in (1,3):
                yield dict(tag=f'{kind}{index}m{copies}',kind=kind,w=w,l=l,copies=copies)


def fixture(tech,target,bias,osdi):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c['name']='passive_coupon';c['devices']=[]
    for row in points(target):
        tag=row['tag'];key,pins,mult=DEVICES[target][row['kind']]
        v=device('V','V'+tag,0,0,value=str(bias),nets={'p':tag,'n':'0'});v['source']['ac']='1'
        d=create_device(p['pdk'],key,'D'+tag)
        scale=1 if target=='sky130A' else 1e-6
        d['model_params'].update(w=row['w']*scale,l=row['l']*scale,**{mult:row['copies']})
        d['nets']=dict(zip(pins,[tag]+['0']*(len(pins)-1)));c['devices'].extend([v,d])
    if target=='ihp-sg13g2':p['simulation_runtime']={'osdi':clone(osdi)}
    return p


def independent_call(target,row):
    kind,tag,w,l,m=(row[k] for k in ('kind','tag','w','l','copies'))
    if target=='sky130A':
        if kind=='res':return f'R{tag} {tag} 0 sky130_fd_pr__res_generic_po w={w:g} l={l:g} m={m}'
        return f'X{tag} {tag} 0 sky130_fd_pr__cap_mim_m3_1 w={w:g} l={l:g} mf={m} m={m}'
    if target.startswith('gf180'):
        if kind=='res':return f'X{tag} {tag} 0 0 ppolyf_u_1k r_width={w:g}u r_length={l:g}u m={m}'
        return f'X{tag} {tag} 0 {GF_CAP_MODELS[kind]} c_width={w:g}u c_length={l:g}u m={m}'
    if target=='ihp-sg13g2':
        if kind=='res':return f'X{tag} {tag} 0 0 rppd w={w:g}u l={l:g}u m={m} b=0 mm_ok=1'
        return f'X{tag} {tag} 0 cap_cmim w={w:g}u l={l:g}u m={m} mm_ok=1'
    raise ValueError('Unknown passive process.')


def independent(tech,target,corner,temp,bias):
    lines=['* Independent two-terminal admittance probes; resistor bodies grounded',*model_lines(tech,corner)]
    for row in points(target):lines.extend([f'V{row["tag"]} {row["tag"]} 0 DC {bias:g} AC 1',independent_call(target,row)])
    return '\n'.join([*lines,f'.temp {temp}','.ac dec 5 100 10meg','.end',''])


def currents(result,target='sky130A'):
    x=result['x']
    if len(x)!=26 or any(not math.isfinite(v) or not math.isclose(v,100*10**(i/5),rel_tol=1e-9) for i,v in enumerate(x)):
        raise ValueError('Missing or invalid frequency sweep.')
    magnitudes={k.casefold():v for k,v in result['currents'].items()};phases={k.casefold():v for k,v in result['current_phase'].items()}
    selected={}
    for row in points(target):
        key='v'+row['tag'];mag=magnitudes.get(key,[]);phase=phases.get(key,[])
        if len(mag)!=26 or len(phase)!=26 or not all(math.isfinite(v) for v in mag+phase) or any(v<0 for v in mag):
            raise ValueError('Missing or invalid complex passive current: '+key)
        selected[key]=[cmath.rect(m,math.radians(p)) for m,p in zip(mag,phase)]
    return selected


def reference_values(result,target='sky130A'):
    selected=currents(result,target);values={}
    for row in points(target):
        y=[-v for v in selected['v'+row['tag']]]
        if row['kind']=='res':
            if any(v.real<1e-9 for v in y):raise ValueError('Reference resistor has no positive conductance.')
            value=1/y[0].real
        else:
            cs=[v.imag/(2*math.pi*f) for v,f in zip(y,result['x'])]
            if any(v<1e-16 for v in cs) or abs(y[-1])<1000*abs(y[0]):raise ValueError('Reference capacitor has no frequency-dependent capacitive response.')
            value=cs[0]
        values[row['tag']]={'kind':row['kind'],'value_at_100hz':value,'unit':'ohm' if row['kind']=='res' else 'F'}
    return selected,values


def compare(actual,reference,target='sky130A'):
    expected,values=reference_values(reference,target);measured=currents(actual,target);errors={}
    for name,vector in expected.items():
        errors[name]=max(abs(a-b)/(ABSOLUTE_TOLERANCE+RELATIVE_TOLERANCE*abs(b)) for a,b in zip(measured[name],vector))
    return {'status':'PASS' if all(e<=1 for e in errors.values()) else 'MISMATCH',
        'maximum_normalized_error':max(errors.values()),'channel_errors':errors,'reference_values':values,
        'complex_vectors':len(expected),'samples':len(actual['x']),
        'relative_tolerance':RELATIVE_TOLERANCE,'absolute_tolerance_a':ABSOLUTE_TOLERANCE}


def altered(p,target,fault):
    p=clone(p)
    for row in points(target):
        d=next(d for d in p['cells'][0]['devices'] if d['name']=='D'+row['tag'])
        if fault=='wrong-width':d['model_params']['w']*=1.2
        elif fault=='disconnected-terminal':d['nets'][DEVICES[target][row['kind']][1][0]]='0'
        else:raise ValueError('Unknown passive fault.')
    return p


def case(tech,target,corner,temp,bias,out,ngspice,osdi):
    name=f'{target}-{corner}-{temp}-{bias:g}';folder=out/name;folder.mkdir();row={'name':name,'target':target,'corner':corner,'temperature_c':temp,'bias_v':bias,'status':'RUNNING','faults':[]}
    try:
        p=fixture(tech,target,bias,osdi);save_project(p,folder/'input.icproj')
        settings=dict(type='ac',corner=corner,temperature=temp,start='100',end='10meg',points=5)
        app=folder/'application';ref=folder/'independent';app.mkdir();ref.mkdir()
        actual=run_ngspice(p,p['top'],settings,ngspice,app)
        text=preload(p,stage_model_deck(tech,independent(tech,target,corner,temp,bias),ref),ref)
        path=ref/'reference.cir';path.write_bytes(text.encode());expected=run_deck(p,p['top'],dict(deck=str(path),analysis=settings),ngspice,ref)
        write(app/'comparison-result.json',actual);write(ref/'comparison-result.json',expected)
        row['comparison']=compare(actual,expected,target)
        if row['comparison']['status']!='PASS':raise ValueError('Independent passive admittances differ.')
        row['raw_sha256']={'application':file_digest(app/'result.raw'),'independent':file_digest(ref/'deck.raw')}
        for fault in FAULTS:
            fp=altered(p,target,fault);dest=folder/fault;dest.mkdir();save_project(fp,dest/'input.icproj')
            measured=run_ngspice(fp,fp['top'],settings,ngspice,dest);write(dest/'comparison-result.json',measured)
            comparison=compare(measured,expected,target)
            if comparison['status']!='MISMATCH' or not all(e>1 for e in comparison['channel_errors'].values()):
                raise ValueError('Passive fault was not detected on every isolated device: '+fault)
            row['faults'].append(dict(fault=fault,status='detected',channels=len(comparison['channel_errors']),comparison=comparison,raw_sha256=file_digest(dest/'result.raw')))
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--ngspice',required=True);ap.add_argument('--osdi',type=Path,required=True)
    ap.add_argument('--nominal-only',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,5),default=2)
    ap.add_argument('--temperatures',type=int,nargs='+',default=[0,27,85]);ap.add_argument('--biases',type=float,nargs='+',choices=(.1,.5),default=[.1,.5]);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);osdi=configure(sorted(a.osdi.glob('*.osdi')))
    sources=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    report=dict(schema=1,chunk=7,status='RUNNING',chunk_complete=False,qualified=False,cases=[],processes={},
        source_files_sha256=file_digest(out/'source-files.json'),source_sha256=file_digest(__file__),engine_sha256=file_digest(a.ngspice),osdi=osdi,
        scope='Selected resistor/MIM capacitor application integration and isolated electrical faults using independent manual calls to the same public models; no complete operating envelope, physical or silicon-model-accuracy qualification.',
        devices=DEVICES,geometry_um=GEOMETRIES,copies=[1,3],biases_v=a.biases,temperatures_c=a.temperatures,nominal_only=a.nominal_only)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs=[]
        for target in DEVICES:
            tech,identity=load_technology(target);report['processes'][target]=identity
            for corner in ('nominal',) if a.nominal_only else PROFILES[target]['corners']:
                for temp in a.temperatures:
                    for bias in a.biases:jobs.append(pool.submit(case,tech,target,corner,temp,bias,out,a.ngspice,osdi))
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['cases'] and report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
