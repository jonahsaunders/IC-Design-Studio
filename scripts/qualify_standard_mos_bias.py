"""Independent terminal-current sweeps with separate drain and body biases.

These are declared test points, not a full model/reliability envelope. Grouped
isolated devices share only the swept ideal gate drive, reducing model reloads.
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
from scripts.qualify_standard_mos import PROFILES,independent_device,load_technology,write

DRAIN_FRACTIONS=(.05,.5,1.)
REVERSE_BODY_VOLTS=(0.,.15,.3)
SIZE=dict(w=4,l=1,fingers=1,copies=1)
RELATIVE_TOLERANCE=1e-6
ABSOLUTE_TOLERANCE=1e-12
FAULTS=('gate-drain-swap','body-to-source','wrong-model')
OTHER_MODELS={'sky130A':'sky130_fd_pr/nfet_01v8_lvt.sym',
    'gf180mcuC':'symbols/nfet_06v0.sym','gf180mcuD':'symbols/nfet_06v0.sym',
    'ihp-sg13g2':'sg13g2_pr/sg13_hv_nmos.sym'}


def points(target):
    supply=PROFILES[target]['supply']
    for polarity in ('n','p'):
        for di,fraction in enumerate(DRAIN_FRACTIONS):
            for bi,reverse in enumerate(REVERSE_BODY_VOLTS):
                tag=f'{polarity}{di}{bi}';pm=polarity=='p'
                yield dict(tag=tag,polarity=polarity,drain_fraction=fraction,reverse_body_v=reverse,
                    nodes={pin:tag+'_'+pin for pin in ('d','g','s','b')},
                    dc={'d':supply*(1-fraction) if pm else supply*fraction,
                        'g':0,'s':supply if pm else 0,'b':supply+reverse if pm else -reverse})


def fixture(tech,target,osdi=()):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c['name']='mos_bias_coupon';c['devices']=[]
    source=device('V','VG',0,0,value='0',nets={'p':'gate_drive','n':'0'});source['source']['ac']='0'
    c['devices'].append(source)
    for row in points(target):
        tag=row['tag']
        for pin,value in row['dc'].items():
            probe=device('V','V'+tag+pin,0,0,value=str(value),
                nets={'p':row['nodes'][pin],'n':'gate_drive' if pin=='g' else '0'})
            probe['source']['ac']='0';c['devices'].append(probe)
        spec=PROFILES[target];key=spec['prefix']+spec['symbols'][row['polarity']=='p']+'.sym'
        d=create_device(p['pdk'],key,'M'+tag);d['params'].update(w='4u',l='1u')
        d['nets']=row['nodes'];c['devices'].append(d)
    if target=='ihp-sg13g2':p['simulation_runtime']={'osdi':clone(list(osdi))}
    return p


def independent(tech,target,corner,temp):
    supply=PROFILES[target]['supply'];lines=['* Independent isolated four-terminal current probes',*model_lines(tech,corner),'VG gate_drive 0 DC 0 AC 0']
    for row in points(target):
        tag=row['tag']
        for pin,value in row['dc'].items():
            lines.append(f'V{tag}{pin} {row["nodes"][pin]} '+('gate_drive' if pin=='g' else '0')+f' DC {value:.12g} AC 0')
        fields=independent_device(target,row['polarity'],SIZE).split();fields[0]='XREF'+tag
        fields[1:5]=[row['nodes'][pin] for pin in ('d','g','s','b')];lines.append(' '.join(fields))
    lines += [f'.temp {temp}',f'.dc VG 0 {supply:.12g} {supply/40:.12g}','.end','']
    return '\n'.join(lines)


def current_vectors(result,target):
    currents={k.casefold():v for k,v in result['currents'].items()};x=result['x']
    if len(x)!=41 or not all(math.isfinite(v) for v in x) or any(a>=b for a,b in zip(x,x[1:])):
        raise ValueError('Missing or invalid gate sweep.')
    selected={}
    for row in points(target):
        vectors=[]
        for pin in ('d','g','s','b'):
            name='v'+row['tag']+pin;values=currents.get(name,[])
            if len(values)!=len(x) or not all(math.isfinite(v) for v in values):raise ValueError('Missing or nonfinite terminal current: '+name)
            selected[name]=values;vectors.append(values)
        drain=vectors[0]
        if max(drain)-min(drain)<1e-7 or (row['polarity']=='n' and min(drain)>-1e-7) or (row['polarity']=='p' and max(drain)<1e-7):
            raise ValueError('Reference transistor lacks a signed current response: '+row['tag'])
        for sample in zip(*vectors):
            if abs(sum(sample))>1e-12+1e-7*max(abs(v) for v in sample):raise ValueError('Terminal-current conservation failed: '+row['tag'])
    return selected


def compare(actual,reference,target):
    # Prove that the reference actually exercises all terminals. Faulted
    # application curves may be flat; they must still load and be finite.
    expected=current_vectors(reference,target);x=actual['x'];y=reference['x']
    if len(x)!=len(y) or any(not math.isfinite(a) or not math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-15) for a,b in zip(x,y)):
        raise ValueError('Different current-comparison sweep coordinates.')
    currents={k.casefold():v for k,v in actual['currents'].items()};maximum=0
    for name,values in expected.items():
        measured=currents.get(name,[])
        if len(measured)!=len(values) or not all(math.isfinite(v) for v in measured):raise ValueError('Missing or nonfinite measured current: '+name)
        maximum=max(maximum,max(abs(a-b)/(ABSOLUTE_TOLERANCE+RELATIVE_TOLERANCE*abs(b)) for a,b in zip(measured,values)))
    if maximum>1:raise ValueError('Independent terminal currents differ: normalized error '+str(maximum))
    current_vectors(actual,target)
    return dict(status='PASS',terminal_vectors=len(expected),samples=len(x),maximum_normalized_error=maximum,
        relative_tolerance=RELATIVE_TOLERANCE,absolute_tolerance_a=ABSOLUTE_TOLERANCE)


def altered(p,target,fault):
    p=clone(p);c=p['cells'][0];d=next(d for d in c['devices'] if d['name']=='Mn11')
    if fault=='gate-drain-swap':d['nets']['g'],d['nets']['d']=d['nets']['d'],d['nets']['g']
    elif fault=='body-to-source':d['nets']['b']=d['nets']['s']
    elif fault=='wrong-model':
        replacement=create_device(p['pdk'],OTHER_MODELS[target],d['name']);replacement['params'].update(w='4u',l='1u');replacement['nets']=clone(d['nets'])
        c['devices'][c['devices'].index(d)]=replacement
    else:raise ValueError('Unknown electrical fault.')
    return p


def case(tech,target,corner,temp,out,ngspice,osdi):
    name=f'{target}-{corner}-{temp}';folder=out/name;folder.mkdir();row=dict(name=name,target=target,corner=corner,temperature_c=temp,status='RUNNING',faults=[])
    try:
        p=fixture(tech,target,osdi);save_project(p,folder/'input.icproj');supply=PROFILES[target]['supply']
        settings=dict(type='dc',corner=corner,temperature=temp,source='VG',dc_start='0',dc_stop=str(supply),dc_step=str(supply/40))
        app=folder/'application';ref=folder/'independent';app.mkdir();ref.mkdir()
        actual=run_ngspice(p,p['top'],settings,ngspice,app)
        text=preload(p,stage_model_deck(tech,independent(tech,target,corner,temp),ref),ref);path=ref/'reference.cir';path.write_bytes(text.encode())
        expected=run_deck(p,p['top'],dict(deck=str(path),analysis=settings),ngspice,ref)
        write(app/'comparison-result.json',actual);write(ref/'comparison-result.json',expected)
        row['comparison']=compare(actual,expected,target)
        row['raw_sha256']={'application':file_digest(app/'result.raw'),'independent':file_digest(ref/'deck.raw')}
        for fault in FAULTS:
            fp=altered(p,target,fault);dest=folder/fault;dest.mkdir();save_project(fp,dest/'input.icproj')
            measured=run_ngspice(fp,fp['top'],settings,ngspice,dest)
            write(dest/'comparison-result.json',measured)
            try:compare(measured,expected,target)
            except ValueError as error:
                if not str(error).startswith('Independent terminal currents differ:'):raise
                row['faults'].append(dict(fault=fault,status='detected',error=str(error),raw_sha256=file_digest(dest/'result.raw')))
            else:raise ValueError('Electrical fault was not detected: '+fault)
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ngspice',required=True);parser.add_argument('--osdi',type=Path,required=True)
    parser.add_argument('--temperatures',nargs='+',type=int,default=[0,27,85]);parser.add_argument('--nominal-only',action='store_true')
    parser.add_argument('--workers',type=int,choices=range(1,5),default=2);a=parser.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    (out/'executed-runner.py').write_bytes(Path(__file__).read_bytes());osdi=configure(sorted(a.osdi.glob('*.osdi')))
    report=dict(schema=1,chunk=7,status='RUNNING',chunk_complete=False,qualified=False,cases=[],processes={},
        source_files_sha256=file_digest(out/'source-files.json'),source_sha256=file_digest(__file__),engine_sha256=file_digest(a.ngspice),osdi=osdi,
        scope='Independent standard MOS terminal currents at selected separate drain/body biases and injected electrical pin/model faults. No complete operating envelope, calibrated silicon accuracy or full device/chunk qualification.',
        geometry_um=SIZE,drain_fractions=DRAIN_FRACTIONS,reverse_body_volts=REVERSE_BODY_VOLTS,temperatures=a.temperatures,nominal_only=a.nominal_only)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs=[]
        for target in PROFILES:
            tech,identity=load_technology(target);report['processes'][target]=identity
            for corner in ('nominal',) if a.nominal_only else PROFILES[target]['corners']:
                for temp in a.temperatures:jobs.append(pool.submit(case,tech,target,corner,temp,out,a.ngspice,osdi))
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report)
            print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
