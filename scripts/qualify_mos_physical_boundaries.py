"""Native full DRC and strict LVS at published standard-MOS geometry points."""
import argparse,json,sys,time,traceback
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,example,file_digest
from icstudio.catalog import create_device
from icstudio.process_adapters import ADAPTERS
from icstudio.physical_cells import assign_port
from icstudio.layout_verification import reference,run
from scripts.qualify_standard_mos import PROFILES,independent_device,load_technology,write
from scripts.qualify_standard_mos_layout import altered as original_fault,fault_detected
from scripts.qualify_mos_boundaries import contract,source_identity

TARGETS=('gf180mcuC','gf180mcuD','ihp-sg13g2')
FAULTS=('wrong-length','wrong-width','drain-open','source-open','gate-open','body-open','gate-drain-short')

def fixture(tech,target,polarity,width,length):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c.update(name='mos_coupon',ports=['D','G','S','B'])
    profile=PROFILES[target]
    d=create_device(p['pdk'],profile['prefix']+profile['symbols'][polarity=='p']+'.sym','M1')
    d['params'].update(w=f'{width}u',l=f'{length}u');d['nets']=dict(d='D',g='G',s='S',b='B');c['devices']=[d]
    implementation=ADAPTERS[target].implementation();implementation.install_mos(p,c['id'],d['id'])
    for pin in c['layout_pins']:assign_port(p,c['id'],d['nets'][pin['pin']],pin['layer'],pin['point'])
    fields=independent_device(target,polarity,dict(w=width,l=length,fingers=1,copies=1)).split()
    fields[1:5]=c['ports']
    ref=reference('.subckt mos_coupon D G S B\n'+' '.join(fields)+'\n.ends mos_coupon\n','mos_coupon')
    return p,c,implementation.layers(p['pdk']),ref

def altered(project,layers,fault):
    if fault in ('drain-open','gate-drain-short'):return original_fault(project,layers,fault)
    p=clone(project);c=p['cells'][0]
    if fault.endswith('-open'):
        pin={'source-open':'s','gate-open':'g','body-open':'b'}[fault]
        x,y=next(r['point'] for r in c['layout_pins'] if r['pin']==pin)
        cuts=[s for s in c['shapes'] if s['layer']==layers['contact'] and
            min(a for a,b in s['points'])<=x<=max(a for a,b in s['points']) and
            min(b for a,b in s['points'])<=y<=max(b for a,b in s['points'])]
        if len(cuts)!=1:raise ValueError('Expected exactly one selected contact cut.')
        c['shapes'].remove(cuts[0])
    elif fault in ('wrong-length','wrong-width'):
        from icstudio.layout import kdb,polygon
        db=kdb();other=db.Region()
        selected='poly' if fault=='wrong-length' else 'diff'
        for s in c['shapes']:
            if s['layer']==layers['diff' if selected=='poly' else 'poly']:other.insert(polygon(s))
        shapes=[s for s in c['shapes'] if s['layer']==layers[selected] and not (db.Region(polygon(s)) & other).is_empty()]
        if len(shapes)!=1:raise ValueError('Expected one selected channel rectangle.')
        shape=shapes[0];axis=0 if fault=='wrong-length' else 1
        high=max(pt[axis] for pt in shape['points']);low=min(pt[axis] for pt in shape['points'])
        delta=max(25,5*round((high-low)/50))
        shape['points']=[[v-delta if i==axis and v==high else v for i,v in enumerate(pt)] for pt in shape['points']]
    else:raise ValueError('Unknown physical fault.')
    return p

def execute_case(tech,target,polarity,width,length,output,tools):
    name=f'{target}-{polarity}-w{width:g}-l{length:g}';folder=output/name;start=time.monotonic()
    row=dict(name=name,target=target,polarity=polarity,width_um=width,length_um=length,status='RUNNING',faults=[])
    try:
        p,c,layers,ref=fixture(tech,target,polarity,width,length)
        result=run(p,c['id'],folder,tools,ref)
        row.update(native_status=result['status'],drc_count=result.get('drc_count'),report_sha256=file_digest(folder/'report.json'))
        if result['status']!='passed':raise ValueError(result.get('error','Native verification did not pass.'))
        for fault in FAULTS:
            changed=altered(p,layers,fault);dest=output/(name+'-'+fault)
            result=run(changed,c['id'],dest,tools,ref);detected=fault_detected(result,dest)
            row['faults'].append(dict(fault=fault,detected=detected,observed=result['status'],
                report_sha256=file_digest(dest/'report.json'),error=result.get('error')))
            if not detected:raise ValueError('Fault was not detected by native size/connectivity evidence: '+fault)
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    row['elapsed_seconds']=time.monotonic()-start
    return row

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--magic',required=True);parser.add_argument('--netgen',required=True)
    parser.add_argument('--targets',nargs='+',choices=TARGETS,default=list(TARGETS));parser.add_argument('--pilot',action='store_true')
    parser.add_argument('--workers',type=int,choices=range(1,5),default=2)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/qualify_standard_mos_layout.py',ROOT/'scripts/qualify_mos_boundaries.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    report=dict(schema=1,chunk=7,status='RUNNING',chunk_complete=False,qualified=False,pilot=args.pilot,
        scope='Native full DRC and strict device/size/terminal LVS at published standard-MOS geometry points. Single finger and multiplicity one. No density, antenna, reliability, continuous geometry or complete-device-family qualification.',
        sources=source_identity(),processes={},cases=[],source_files_sha256=file_digest(out/'source-files.json'))
    tools={k:str(Path(getattr(args,k)).resolve(strict=True)) for k in ('magic','netgen')}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs=[]
        for target in args.targets:
            tech,identity=load_technology(target);report['processes'][target]=identity
            sizes=contract(target)['sizes'];sizes=sizes[:1] if args.pilot else sizes
            for polarity in ('n','p'):
                for width,length in sizes:jobs.append(pool.submit(execute_case,tech,target,polarity,width,length,out,tools))
        report['expected_cases']=len(jobs)
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report)
            print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['implementation_unchanged'] and len(report['cases'])==len(jobs) and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report)
    return 0 if report['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
