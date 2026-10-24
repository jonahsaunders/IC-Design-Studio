"""Native geometry and connectivity checks for SKY130 1.8 V threshold variants.

Finite Studio-generator fixtures, not complete device or foundry qualification.
References name the expected physical model independently of the generator.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
from pathlib import Path
import re
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.catalog import create_device,link_technology
from icstudio.model import clone,example,file_digest,save_project,load_project,scalar
from icstudio.physical_cells import assign_port
from icstudio.sky130_layout import install_mos,layers
from icstudio.layout_verification import reference,run
from icstudio.interchange import export_layout
from icstudio.layout_import import read_layout
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos_layout import technology,fault_detected

MODELS=('nfet_01v8_lvt','pfet_01v8_lvt','pfet_01v8_hvt')
FAULTS=('implant-missing','implant-wrong','drain-open','gate-open','body-open',
        'reference-width','reference-length','reference-gate-body')


def sizes(model):
    return ((.42,.35 if model=='pfet_01v8_lvt' else .15,1,1,False),
            (4.,1.,1,1,False),(1.,.5,2,1,True),(.42,.5,8,1,True),
            (1.,.5,2,3,True))


def fixture(tech,model,size):
    width,length,nf,copies,per_finger=size
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0]
    c.update(name='vt_coupon',ports=['D','G','S','B'])
    key='sky130_fd_pr/'+model+('_nf' if per_finger else '')+'.sym'
    d=create_device(p['pdk'],key,'M1');d['params'].update(w=f'{width:g}u',l=f'{length:g}u')
    d['model_params'].update(nf=nf,mult=copies);d['nets']=dict(d='D',g='G',s='S',b='B')
    c['devices']=[d];install_mos(p,c['id'],d['id'])
    for pin in c['layout_pins']:assign_port(p,c['id'],d['nets'][pin['pin']],pin['layer'],pin['point'])
    return p


def selected(model,size,fault=None):
    width,length,nf,copies,per_finger=size
    total=width*nf if per_finger else width
    if fault=='reference-width':total*=1.2
    if fault=='reference-length':length*=1.2
    terminals='D B S G' if fault=='reference-gate-body' else 'D G S B'
    return reference(f'.subckt vt_coupon D G S B\nX1 {terminals} sky130_fd_pr__{model} w={total:g} l={length:g} nf={nf} m={copies}\n.ends vt_coupon\n','vt_coupon')


def altered(p,fault):
    p=clone(p);c=p['cells'][0];ls=layers(p['pdk'])
    if fault.startswith('implant-'):
        by={(v['gds'],v['datatype']):v['name'] for v in p['pdk']['layers']}
        masks={by[(125,44)],by[(78,44)]}
        shapes=[s for s in c['shapes'] if s['layer'] in masks]
        if not shapes:raise ValueError('No threshold implant selected for control.')
        if fault=='implant-missing':c['shapes']=[s for s in c['shapes'] if s not in shapes]
        else:
            for s in shapes:s['layer']=by[(78,44)] if s['layer']==by[(125,44)] else by[(125,44)]
    elif fault.endswith('-open'):
        pin={'drain-open':'d','gate-open':'g','body-open':'b'}[fault]
        # Remove every licon reaching this terminal's physical LI. This also
        # covers routed multifinger and parallel terminals away from the cuts.
        from icstudio.layout import polygon,kdb
        db=kdb();connected=db.Region()
        for s in c['shapes']:
            if s['layer']==ls['li'] and s.get('net')==c['devices'][0]['nets'][pin]:connected.insert(polygon(s))
        cuts=[s for s in c['shapes'] if s['layer']==ls['licon'] and not (db.Region(polygon(s))&connected).is_empty()]
        if not cuts:raise ValueError('No terminal cuts selected for control.')
        c['shapes']=[s for s in c['shapes'] if s not in cuts]
    elif not fault.startswith('reference-'):raise ValueError('Unknown threshold control.')
    return p


def audit_native(path,model,size):
    """Read all native device statements, without using the comparison result."""
    text=re.sub(r'\n\s*\+\s*',' ',path.read_text())
    lines=[line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    if (len(lines)<3 or lines[0]!=['.subckt','vt_coupon','D','G','S','B']
            or lines[-1] not in (['.ends'],['.ends','vt_coupon'])
            or any(row[0].startswith('.') for row in lines[1:-1])):
        raise ValueError('Native extraction must contain exactly the expected flat four-terminal circuit.')
    rows=lines[1:-1]
    if not rows:raise ValueError('Empty native MOS extraction.')
    width,length,nf,copies,per_finger=size;total=width*(nf if per_finger else 1)*copies
    measured=0
    for row in rows:
        if len(row)<8 or not row[0].lower().startswith('x') or row[5]!='sky130_fd_pr__'+model:
            raise ValueError('Native extraction contains another device or model: '+' '.join(row))
        if row[2]!='G' or row[4]!='B' or set((row[1],row[3]))!={'D','S'}:
            raise ValueError('Native terminal topology differs.')
        params=dict(item.split('=',1) for item in row[6:])
        if (len(params)!=len(row)-6 or not {'w','l'}<=params.keys()
                or params.keys()-{'w','l','ad','as','pd','ps','m'}
                or any(not math.isfinite(scalar(v)) for v in params.values())
                or any(scalar(params.get(n,'1'))<=0 for n in ('w','l','m'))):
            raise ValueError('Invalid or ambiguous native device parameters.')
        if abs(scalar(params['l'])-length)>1e-8:raise ValueError('Native channel length differs.')
        measured+=scalar(params['w'])*scalar(params.get('m','1'))
    if abs(measured-total)>1e-8:raise ValueError(f'Native total channel width differs: {measured} versus {total}')
    return dict(devices=len(rows),model='sky130_fd_pr__'+model,total_width_um=measured,length_um=length)


def rejected(report,folder):
    if fault_detected(report,folder):return True
    stages={s['name']:s['status'] for s in report['stages']}
    log=folder/'lvs/lvs.log'
    return (report['status']=='failed' and all(stages.get(n)=='passed' for n in
            ('preflight','layout_export','lvs_extraction')) and stages.get('lvs')=='failed'
            and log.is_file() and 'Final result: Top level cell failed pin matching.' in log.read_text())


def execute_case(tech,model,size,index,out,tools,pilot):
    name=model+'-'+str(index);folder=Path(out)/name;folder.mkdir()
    row=dict(name=name,model=model,size=size,status='RUNNING',layouts=[],faults=[])
    try:
        original=fixture(tech,model,size)
        for angle in ((0,) if pilot else (0,90,180,270)):
            p=clone(original);c=p['cells'][0]
            save_project(p,folder/f'input-{angle}.icproj');p=load_project(folder/f'input-{angle}.icproj')
            export_layout(p,folder/'unrotated.gds')
            import klayout.db as k
            ly=k.Layout();ly.read(str(folder/'unrotated.gds'));ly.top_cell().transform(k.Trans(angle//90,False,0,0))
            ly.write(str(folder/f'input-{angle}.gds'))
            p,_=read_layout(folder/f'input-{angle}.gds');link_technology(p,tech);p['cells'][0]['ports']=['D','G','S','B']
            export_layout(p,folder/f'roundtrip-{angle}.oas');p,_=read_layout(folder/f'roundtrip-{angle}.oas')
            link_technology(p,tech);p['cells'][0]['ports']=['D','G','S','B']
            export_layout(p,folder/f'roundtrip-{angle}.gds')
            exchange=compare(folder/f'input-{angle}.gds',folder/f'roundtrip-{angle}.gds',text_presentation=False)
            dest=folder/f'valid-{angle}';result=run(p,p['top'],dest,tools,selected(model,size))
            if result['status']!='passed':raise ValueError(result.get('error','Verification failed.'))
            native=audit_native(dest/'lvs-extraction/extracted.spice',model,size)
            from icstudio.sky130_rf_verification import drc
            public=drc(tools['klayout'],dest/'layout.gds','vt_coupon',tech,dest/'public-drc')
            if public['violations']:raise ValueError('Public mask DRC failed: '+str(public['rules']))
            row['layouts'].append(dict(angle=angle,native=native,exchange=exchange,public_drc=public,report_sha256=file_digest(dest/'report.json')))
        for fault in FAULTS:
            p=altered(original,fault);dest=folder/fault
            result=run(p,p['top'],dest,tools,selected(model,size,fault))
            if not rejected(result,dest):raise ValueError('Native comparison did not detect '+fault+': '+result.get('error',''))
            row['faults'].append(dict(name=fault,detected=True,error=result.get('error'),report_sha256=file_digest(dest/'report.json')))
        row['status']='PASS'
    except Exception as exc:row.update(status='FAIL',error=str(exc),traceback=traceback.format_exc())
    (folder/'result.json').write_text(json.dumps(row,indent=2)+'\n')
    return row


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('output','sky130','magic','netgen','klayout'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,default=2)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tech,identity=technology('sky130A',a.sky130)
    files=[Path(__file__),ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    hashes={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    (out/'source-files.json').write_text(json.dumps(hashes,indent=2)+'\n')
    result=dict(schema=1,status='RUNNING',chunk=7,chunk_complete=False,qualified=False,
                scope=__doc__,package=identity,source_files_sha256=file_digest(out/'source-files.json'),cases=[])
    tools={n:str(getattr(a,n).resolve(strict=True)) for n in ('magic','netgen','klayout')}
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(execute_case,tech,model,size,index,out,tools,a.pilot)
              for model in MODELS for index,size in enumerate(sizes(model)[:1] if a.pilot else sizes(model))]
        for job in as_completed(jobs):
            row=job.result();result['cases'].append(row);print(row['name'],row['status'],row.get('error',''),flush=True)
            (out/'record.json').write_text(json.dumps(result,indent=2)+'\n')
    result['implementation_unchanged']=hashes=={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    result['status']='PASS' if result['implementation_unchanged'] and all(c['status']=='PASS' for c in result['cases']) else 'FAIL'
    (out/'record.json').write_text(json.dumps(result,indent=2)+'\n')
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
