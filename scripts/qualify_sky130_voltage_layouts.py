"""Sample physical and extracted SKY130 thick-oxide/native MOS layouts.

Independent expected geometries include all native nominal model-bin centers,
ordinary and per-finger views, rotations and parallel copies. This does not
qualify continuous operating ranges, reliability or complete-chip signoff.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
from pathlib import Path
import sys
import traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,file_digest,save_project,load_project
from icstudio.catalog import link_technology
from icstudio.layout_import import read_layout
from icstudio.interchange import export_layout
from icstudio.stream_contract import compare
from icstudio.layout_verification import run
from icstudio.sky130_rf_verification import drc
from scripts.qualify_standard_mos_layout import technology
from scripts.qualify_sky130_threshold_layouts import fixture,selected,audit_native,rejected,altered as contact_fault

MODELS=('nfet_g5v0d10v5','pfet_g5v0d10v5','nfet_03v3_nvt','nfet_05v0_nvt')
# Independently transcribed centers from the pinned public native .pm3 models.
NATIVE={
    'nfet_03v3_nvt': ((10,.5),(1,.5),(1,.6),(4,.5),(.42,.5),(.42,.6),(.42,.8),(.7,.5),(.7,.6)),
    'nfet_05v0_nvt': ((10,2),(10,4),(10,.9),(1,25),(1,2),(1,4),(1,8),(1,.9),(.42,1),(.42,.9),(.7,.9)),
}

def sizes(model):
    if model in NATIVE:
        return tuple((w,l,1,1,False) for w,l in NATIVE[model])+((1,.5 if model.endswith('3v3_nvt') else .9,2,3,True),)
    return ((.42,.5,1,1,False),(4,1,1,1,False),(1,.5,2,1,True),(.42,.5,8,1,True),(1,.5,2,3,True))

def faults(model,size=None):
    result=['oxide-missing','drain-open','gate-open','body-open','reference-width','reference-length','reference-gate-body']
    if model in NATIVE:result.append('native-implant-missing')
    if model=='nfet_03v3_nvt':result.append('native-identifier-missing')
    if model=='nfet_05v0_nvt' and size is not None and size[1]>10:result.append('long-tap-missing')
    return tuple(result)

def altered(p,fault):
    if fault=='long-tap-missing':
        p=clone(p);cell=p['cells'][0];removed=[s for s in cell['shapes'] if s.get('generator_role','').startswith('long_channel_body_')]
        if not removed:raise ValueError('No long-channel body tap selected for fault.')
        cell['shapes']=[s for s in cell['shapes'] if s not in removed];return p
    pair={'oxide-missing':(75,20),'native-implant-missing':(125,44),'native-identifier-missing':(81,60)}.get(fault)
    if pair is None:return contact_fault(p,fault)
    p=clone(p);layer=next(l['name'] for l in p['pdk']['layers'] if (l['gds'],l['datatype'])==pair)
    cell=p['cells'][0];removed=[s for s in cell['shapes'] if s['layer']==layer]
    if not removed:raise ValueError('No physical process mask selected for fault.')
    cell['shapes']=[s for s in cell['shapes'] if s not in removed];return p

def execute(tech,model,size,index,output,tools,pilot):
    folder=Path(output)/(model+'-'+str(index));folder.mkdir()
    row=dict(model=model,size=size,status='RUNNING',layouts=[],faults=[])
    try:
        original=fixture(tech,model,size)
        for angle in ((0,) if pilot else (0,90,180,270)):
            p=clone(original);save_project(p,folder/f'input-{angle}.icproj');p=load_project(folder/f'input-{angle}.icproj')
            export_layout(p,folder/'unrotated.gds')
            import klayout.db as db
            ly=db.Layout();ly.read(str(folder/'unrotated.gds'));ly.top_cell().transform(db.Trans(angle//90,False,0,0));ly.write(str(folder/f'input-{angle}.gds'))
            p,_=read_layout(folder/f'input-{angle}.gds');link_technology(p,tech);p['cells'][0]['ports']=['D','G','S','B']
            export_layout(p,folder/f'roundtrip-{angle}.oas');p,_=read_layout(folder/f'roundtrip-{angle}.oas');link_technology(p,tech);p['cells'][0]['ports']=['D','G','S','B']
            export_layout(p,folder/f'roundtrip-{angle}.gds')
            exchange=compare(folder/f'input-{angle}.gds',folder/f'roundtrip-{angle}.gds',text_presentation=False)
            dest=folder/f'valid-{angle}';report=run(p,p['top'],dest,tools,selected(model,size))
            if report['status']!='passed':raise ValueError(report.get('error','Native verification failed'))
            native=audit_native(dest/'lvs-extraction/extracted.spice',model,size)
            public=drc(tools['klayout'],dest/'layout.gds','vt_coupon',tech,dest/'public-drc')
            if public['violations']:raise ValueError('Public mask DRC failed: '+str(public['rules']))
            row['layouts'].append(dict(angle=angle,native=native,exchange=exchange,public_drc=public,report_sha256=file_digest(dest/'report.json')))
        for fault in faults(model,size):
            dest=folder/fault;report=run(altered(original,fault),original['top'],dest,tools,selected(model,size,fault))
            detected=rejected(report,dest)
            if fault=='long-tap-missing':
                stages={s['name']:s['status'] for s in report['stages']}
                detected=(report['status']=='failed' and stages.get('drc')=='failed'
                    and all(stages.get(n)=='passed' for n in ('preflight','layout_export','lvs_extraction','lvs','integrity'))
                    and any('LU.2' in f['message'] and f['code']=='MAGIC.DRC' for f in report.get('findings',[])))
            if not detected:raise ValueError('Native comparison did not detect '+fault+': '+report.get('error',''))
            row['faults'].append(dict(name=fault,detected=True,error=report.get('error'),report_sha256=file_digest(dest/'report.json')))
        row['status']='PASS'
    except Exception as e:row.update(status='FAIL',error=str(e),traceback=traceback.format_exc())
    (folder/'result.json').write_bytes((json.dumps(row,indent=2)+'\n').encode());return row

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('output','sky130','magic','netgen','klayout'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,default=2)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tech,identity=technology('sky130A',a.sky130)
    files=[Path(__file__),ROOT/'scripts/qualify_sky130_threshold_layouts.py',ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    hashes={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    (out/'source-files.json').write_bytes((json.dumps(hashes,indent=2)+'\n').encode())
    result=dict(schema=1,status='RUNNING',chunk=7,chunk_complete=False,qualified=False,scope=__doc__,package=identity,source_files_sha256=file_digest(out/'source-files.json'),cases=[])
    tools={name:str(getattr(a,name).resolve(strict=True)) for name in ('magic','netgen','klayout')}
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(execute,tech,model,size,i,out,tools,a.pilot) for model in MODELS for i,size in enumerate(sizes(model)[:1] if a.pilot else sizes(model))]
        for job in as_completed(jobs):
            row=job.result();result['cases'].append(row);print(row['model'],row['size'],row['status'],row.get('error',''),flush=True)
            (out/'record.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
    result['implementation_unchanged']=hashes=={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    result['status']='PASS' if result['implementation_unchanged'] and all(c['status']=='PASS' for c in result['cases']) else 'FAIL'
    (out/'record.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
