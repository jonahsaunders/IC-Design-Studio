"""Native second-MiM geometry, extracted connectivity and terminal response.

Finite local recipe checks, not complete operating or manufacturing acceptance.
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
from icstudio.catalog import create_device, link_technology
from icstudio.model import clone, example, file_digest, save_project, load_project, scalar
from icstudio.physical_cells import assign_port
from icstudio.sky130_devices import install
from icstudio.sky130_mim2 import layers
from icstudio.layout_verification import run, reference
from icstudio.interchange import export_layout
from icstudio.layout_import import read_layout
from icstudio.stream_contract import compare
from icstudio.sky130_rf_verification import drc
from scripts.qualify_standard_mos_layout import technology
from scripts.qualify_sky130_threshold_layouts import rejected
from scripts.qualify_sky130_devices import measure

SIZES=((2,2,1),(5,5,1),(10,10,1),(3.005,3.005,1),(30,30,1),(2,2,3),(2,2,16))
FAULTS=('dielectric-missing','top-open','bottom-open','reference-width','reference-count')


def fixture(tech,size):
    w,l,count=size;p=example('empty');p['pdk']=clone(tech);c=p['cells'][0]
    c.update(name='device_coupon',ports=['P','N'])
    d=create_device(tech,'sky130_fd_pr/cap_mim_m3_2.sym','C1')
    d['model_params'].update(w=w,l=l,mf=count);d['nets']=dict(c0='P',c1='N');c['devices']=[d]
    install(p,c['id'],d['id'])
    for pin in c['layout_pins']:assign_port(p,c['id'],d['nets'][pin['pin']],pin['layer'],pin['point'])
    return p


def independent(size,fault=None):
    w,l,count=size
    if fault=='reference-width':w*=1.2
    if fault=='reference-count':count+=1
    return f'.subckt device_coupon P N\nX1 P N sky130_fd_pr__cap_mim_m3_2 w={w:g} l={l:g} m={count}\n.ends device_coupon\n'


def altered(original,fault):
    p=clone(original);c=p['cells'][0];ls=layers(p['pdk'])
    if fault=='dielectric-missing':removed=[s for s in c['shapes'] if s['layer']==ls['cap2m']]
    elif fault in ('top-open','bottom-open'):
        role='passive:top_via_' if fault=='top-open' else 'passive:bottom_via'
        removed=[s for s in c['shapes'] if role in s.get('generator_role','')]
    elif fault.startswith('reference-'):return p
    else:raise ValueError('Unknown fault.')
    if not removed:raise ValueError('No actual masks selected for fault.')
    c['shapes']=[s for s in c['shapes'] if s not in removed];return p


def audit_native(path,size):
    w,l,count=size;text=re.sub(r'\n\s*\+\s*',' ',path.read_text(encoding='utf-8'))
    rows=[v.split() for v in text.splitlines() if v.strip() and not v.lstrip().startswith('*')]
    if rows[0]!=['.subckt','device_coupon','P','N'] or rows[-1] not in (['.ends'],['.ends','device_coupon']):
        raise ValueError('Unexpected extracted circuit boundary.')
    units=0
    for row in rows[1:-1]:
        if not row[0].startswith('X') or row[1:4]!=['P','N','sky130_fd_pr__cap_mim_m3_2']:
            raise ValueError('Extracted model or electrode polarity differs: '+' '.join(row))
        values=dict(v.split('=',1) for v in row[4:])
        if len(values)!=len(row)-4 or set(values)-{'w','l','m'} or not {'w','l'}<=values.keys():
            raise ValueError('Unexpected extracted parameters.')
        if any(not math.isclose(scalar(values[k]),value,abs_tol=1e-8,rel_tol=0) for k,value in (('w',w),('l',l))):
            raise ValueError('Extracted capacitor dimensions differ.')
        m=scalar(values.get('m','1'))
        if not math.isfinite(m) or m<=0:raise ValueError('Invalid extracted count.')
        units+=m
    if units!=count:raise ValueError('Extracted parallel count differs.')
    return dict(model='sky130_fd_pr__cap_mim_m3_2',terminals=['P','N'],dimensions_um=[w,l],units=units,sha256=file_digest(path))


def execute(tech,size,index,output,tools,pilot):
    folder=Path(output)/str(index);folder.mkdir();row=dict(size=size,status='RUNNING',layouts=[],faults=[],measurements=[])
    try:
        original=fixture(tech,size);save_project(original,folder/'input.icproj');original=load_project(folder/'input.icproj')
        export_layout(original,folder/'original.gds')
        for angle in ((0,) if pilot else (0,90,180,270)):
            import klayout.db as db
            ly=db.Layout();ly.read(str(folder/'original.gds'));ly.top_cell().transform(db.Trans(angle//90,False,0,0));ly.write(str(folder/f'input-{angle}.gds'))
            p,_=read_layout(folder/f'input-{angle}.gds');link_technology(p,tech);p['cells'][0]['ports']=['P','N']
            export_layout(p,folder/f'roundtrip-{angle}.oas');p,_=read_layout(folder/f'roundtrip-{angle}.oas');link_technology(p,tech);p['cells'][0]['ports']=['P','N']
            export_layout(p,folder/f'roundtrip-{angle}.gds')
            exchange=compare(folder/f'input-{angle}.gds',folder/f'roundtrip-{angle}.gds',text_presentation=False)
            dest=folder/f'valid-{angle}';report=run(p,p['top'],dest,tools,reference(independent(size),'device_coupon'))
            if report['status']!='passed':raise ValueError(report.get('error','Native verification failed.'))
            native=audit_native(dest/'lvs-extraction/extracted.spice',size)
            public=drc(tools['klayout'],dest/'layout.gds','device_coupon',tech,dest/'public-drc')
            if public['violations']:raise ValueError('Public DRC failed: '+str(public['rules']))
            row['layouts'].append(dict(angle=angle,native=native,exchange=exchange,public_drc=public,report_sha256=file_digest(dest/'report.json')))
        from icstudio.testbenches import native_subcircuit
        decks=dict(schematic=native_subcircuit(original,original['top']),extracted=(folder/'valid-0/lvs-extraction/extracted.spice').read_text(),independent=independent(size))
        for corner,temp in (('nominal',27),) if pilot else (('nominal',27),('ss',0),('ff',85)):
            values=measure(original,decks,'cap',corner,temp,tools,folder/f'electrical-{corner}-{temp}')
            if any(abs(value/values['independent']-1)>1e-6 for value in values.values()):raise ValueError('Schematic/extracted/reference admittance differs: '+str(values))
            row['measurements'].append(dict(corner=corner,temperature=temp,capacitance_F=values))
        for fault in FAULTS:
            dest=folder/fault;report=run(altered(original,fault),original['top'],dest,tools,reference(independent(size,fault),'device_coupon'))
            if not rejected(report,dest):raise ValueError('Intended native fault was not detected: '+fault+' '+str(report.get('error')))
            row['faults'].append(dict(name=fault,detected=True,error=report.get('error'),report_sha256=file_digest(dest/'report.json')))
        row['status']='PASS'
    except Exception as e:row.update(status='FAIL',error=str(e),traceback=traceback.format_exc())
    (folder/'record.json').write_bytes((json.dumps(row,indent=2)+'\n').encode());return row


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('output','sky130','magic','netgen','klayout','ngspice'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--workers',type=int,default=2);ap.add_argument('--pilot',action='store_true')
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tech,identity=technology('sky130A',a.sky130)
    files=[*sorted((ROOT/'icstudio').glob('*.py')),Path(__file__),*[ROOT/'scripts'/n for n in ('qualify_standard_mos_layout.py','qualify_standard_mos.py','qualify_sky130_devices.py','qualify_sky130_threshold_layouts.py')]]
    hashes={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    (out/'source-files.json').write_bytes((json.dumps(hashes,indent=2)+'\n').encode())
    tools={n:str(getattr(a,n).resolve(strict=True)) for n in ('magic','netgen','klayout','ngspice')}
    record=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,package=identity,engine_sha256={k:file_digest(p) for k,p in tools.items()},cases=[])
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for job in as_completed([pool.submit(execute,tech,size,i,out,tools,a.pilot) for i,size in enumerate(SIZES[:1] if a.pilot else SIZES)]):
            row=job.result();record['cases'].append(row);print(row['size'],row['status'],row.get('error',''),flush=True)
            (out/'record.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
    record['source_unchanged']=hashes=={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    record['status']='PASS' if record['source_unchanged'] and all(c['status']=='PASS' for c in record['cases']) else 'FAIL'
    (out/'record.json').write_bytes((json.dumps(record,indent=2)+'\n').encode());return int(record['status']!='PASS')

if __name__=='__main__':raise SystemExit(main())
