"""Sampled native SKY130 LI/metal resistor layout, exchange and fault controls.

The pinned physical package is distinct from the bundled simulation package.
Straight single resistors only; no snake/array or continuous-domain qualification.
"""
import argparse,json,math,re,subprocess,sys,traceback
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,file_digest,load_project,save_project,scalar
from icstudio.catalog import link_technology
from icstudio.layout import kdb,polygon,rect
from icstudio.layout_import import read_layout
from icstudio.physical_cells import assign_port
from icstudio.layout_verification import reference,run
from icstudio.interchange import export_layout
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import write
from scripts.qualify_standard_mos_layout import technology,fault_detected
from scripts.qualification_geometry import regions,same_masks,rotated

# LI resistor rule li.7 requires .29 um outside areaid.ed, even though the
# generator's electrical default is .17 um. No exemption marker is added.
MODELS={'l1':(67,.29),'m1':(68,.14),'m2':(69,.14),'m3':(70,.30),'m4':(71,.30)}
SIZES=((.5,.5),(.5,10),(10,.5),(2,5),(5,2))
FAULTS=('terminal-open','terminal-short','reference-width','reference-length','reference-model')


def selected_reference(model,w,l):
    if model not in MODELS:raise ValueError('Unknown metal resistor.')
    # This SKY130 deck and model use numerical micrometres for R primitives.
    return reference(f'.subckt coupon R1 R2\nR1 R1 R2 sky130_fd_pr__res_generic_{model} w={w:g} l={l:g} m=1\n.ends coupon\n','coupon')


def generate(tech,model,w,l,folder,magic):
    if model not in MODELS or (w,l) not in (*SIZES,(MODELS[model][1],)*2):raise ValueError('Use a reviewed sampled geometry.')
    folder.mkdir();source=Path(tech['package_root'])/'libs.tech/magic';full='sky130_fd_pr__res_generic_'+model
    script=f'''tech load {{{source/'sky130A.tech'}}}
scalegrid 1 2
source {{{source/'sky130A.tcl'}}}
load coupon -silent
box values 0 0 0 0
set parameters [dict merge [sky130::{full}_defaults] [dict create w {w:g} l {l:g} m 1 nx 1 snake 0]]
if {{[catch {{sky130::{full}_draw $parameters}} err]}} {{puts stderr "GENERATOR_FAILED $err"; quit -noprompt}}
select top cell
box select
save coupon
gds write coupon.gds
puts GENERATOR_COMPLETE
quit -noprompt
'''
    (folder/'generate.tcl').write_bytes(script.encode());(folder/'empty.magicrc').write_bytes(b'')
    r=subprocess.run([magic,'-dnull','-noconsole','-rcfile','empty.magicrc','generate.tcl'],cwd=folder,capture_output=True,timeout=120)
    log=r.stdout+r.stderr;(folder/'console.log').write_bytes(log)
    if r.returncode or log.count(b'GENERATOR_COMPLETE')!=1 or b'GENERATOR_FAILED' in log or re.search(rb'\d+ problems occurred',log):raise ValueError('Native generator failed; see console.log.')
    p,_=read_layout(folder/'coupon.gds');raw=clone(p);link_technology(p,tech);c=p['cells'][0];c['ports']=['R1','R2'];gds=MODELS[model][0]
    masks=regions(p);ends=(masks[(gds,20)]-masks[(gds,13)]).merged()
    if ends.count()!=2:raise ValueError('Resistor does not have exactly two terminal landings.')
    conductor=next(v['name'] for v in p['pdk']['layers'] if (v['gds'],v['datatype'])==(gds,20))
    for name,poly in zip(c['ports'],sorted(ends.each(),key=lambda q:q.bbox().center().y)):
        center=poly.bbox().center()
        if not poly.inside(center):raise ValueError('Nonrectangular terminal needs explicit placement.')
        assign_port(p,c['id'],name,conductor,[center.x,center.y])
    same_masks(raw,p);return p


def altered(p,model,fault):
    q=clone(p);c=q['cells'][0];db=kdb();gds=MODELS[model][0];masks=regions(q)
    name=next(v['name'] for v in q['pdk']['layers'] if (v['gds'],v['datatype'])==(gds,20));ports={v['name']:v for v in c['layout_ports']}
    body=masks[(gds,13)].bbox();a,b=[ports[k]['point'] for k in ('R1','R2')]
    if fault=='terminal-open':
        # Keep the port landing; remove a narrow conductor strip between it and
        # the resistor. The original marker and all other masks remain intact.
        mid=(a[1]+body.bottom)//2;gap=10
        cut=db.Region(db.Box(body.left-100,mid-gap//2,body.right+100,mid+gap//2))
        remaining=(masks[(gds,20)]-cut).merged()
        if (remaining^masks[(gds,20)]).is_empty():raise ValueError('Open did not remove conductor.')
        c['shapes']=[s for s in c['shapes'] if s['layer']!=name]
        from icstudio.layout import shape_from_polygon
        c['shapes'].extend(shape_from_polygon(poly,name) for poly in remaining.each())
    elif fault=='terminal-short':
        width=400;x=body.right+1000
        c['shapes'] += [rect(name,min(a[0],x)-width//2,a[1]-width//2,abs(x-a[0])+width,width),
            rect(name,x-width//2,min(a[1],b[1])-width//2,width,abs(b[1]-a[1])+width),
            rect(name,min(b[0],x)-width//2,b[1]-width//2,abs(x-b[0])+width,width)]
    else:raise ValueError('Unknown physical fault.')
    return q


def audit_extracted(path,model,w,l):
    text=path.read_text();devices=[line.split() for line in text.splitlines() if re.match(r'(?i)^[rxmdq]\S*\s',line)]
    if len(devices)!=1:raise ValueError('Expected exactly one extracted resistor.')
    row=devices[0]
    if not row[0].lower().startswith('r') or set(row[1:3])!={'R1','R2'} or row[3]!='sky130_fd_pr__res_generic_'+model:raise ValueError('Incorrect extracted model or terminals.')
    params=dict(v.split('=',1) for v in row[4:] if '=' in v)
    for key,value in (('w',w),('l',l)):
        if key not in params or not math.isclose(scalar(params[key]),value,rel_tol=1e-10,abs_tol=1e-9):raise ValueError('Incorrect extracted '+key+': '+str(params))
    return dict(model=row[3],terminals=row[1:3],width_um=w,length_um=l,sha256=file_digest(path))


def case(tech,model,w,l,out,tools):
    folder=out/f'{model}-w{w:g}-l{l:g}';folder.mkdir();row=dict(name=folder.name,model=model,width_um=w,length_um=l,status='RUNNING',layouts=[],faults=[])
    try:
        p=generate(tech,model,w,l,folder/'generator',tools['magic']);ref=selected_reference(model,w,l)
        save_project(p,folder/'saved.icproj');q=load_project(folder/'saved.icproj');same_masks(p,q)
        for angle in (0,90):
            if angle:q=rotated(q)
            baseline=folder/f'baseline-{angle}.gds';export_layout(q,baseline);oas=folder/f'layout-{angle}.oas';export_layout(q,oas)
            ly=kdb().Layout();ly.read(str(oas));external=folder/f'external-{angle}.oas';ly.write(str(external))
            imported,_=read_layout(external);link_technology(imported,tech);imported['cells'][0]['ports']=['R1','R2'];same_masks(q,imported)
            exported=folder/f'reimported-{angle}.gds';export_layout(imported,exported)
            exchange=dict(gds=compare(baseline,exported),oasis=compare(external,exported,text_presentation=False))
            dest=folder/f'physical-{angle}';result=run(imported,imported['top'],dest,tools,ref)
            if result['status']!='passed':raise ValueError(result.get('error','Native verification failed.'))
            row['layouts'].append(dict(rotation=angle,drc_count=result['drc_count'],exchange=exchange,report_sha256=file_digest(dest/'report.json'),extracted=audit_extracted(dest/'lvs-extraction/extracted.spice',model,w,l)))
        for fault in FAULTS:
            changed=altered(p,model,fault) if not fault.startswith('reference-') else p
            selected=selected_reference(model,w*1.2,l) if fault=='reference-width' else selected_reference(model,w,l*1.2) if fault=='reference-length' else selected_reference('m1' if model=='l1' else 'l1',w,l) if fault=='reference-model' else ref
            dest=folder/fault;result=run(changed,changed['top'],dest,tools,selected);detected=fault_detected(result,dest)
            row['faults'].append(dict(name=fault,detected=detected,status=result['status'],error=result.get('error'),report_sha256=file_digest(dest/'report.json')))
            if not detected:raise ValueError('Native checks did not detect '+fault)
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--sky130',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--magic',required=True);ap.add_argument('--netgen',required=True);ap.add_argument('--pilot',action='store_true');ap.add_argument('--models',nargs='+',choices=MODELS,default=list(MODELS));ap.add_argument('--workers',type=int,choices=range(1,5),default=2)
    ap.add_argument('--development',action='store_true',help='Selected physical development pilot; never release acceptance.')
    ap.add_argument('--select',nargs='*',help='Development case selection; currently only l1-w2-l5.')
    ap.add_argument('--resume-from',type=Path,help='Original completed development run; outputs are independently re-audited.')
    a=ap.parse_args()
    if a.development:
        from scripts.sky130_li_resume import execute
        return execute(a,sys.modules[__name__],technology)
    if a.select is not None or a.resume_from is not None:
        ap.error('--select and --resume-from require --development; exhaustive/release runs always execute fresh.')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);tech,identity=technology('sky130A',a.sky130);tools={k:str(Path(getattr(a,k)).resolve(strict=True)) for k in ('magic','netgen')}
    sources=[Path(__file__),ROOT/'scripts/qualification_geometry.py',ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py'))];before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes());report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,process=identity,cases=[],source_files_sha256=file_digest(out/'source-files.json'))
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(case,tech,m,w,l,out,tools) for m in a.models for w,l in ([(2,5)] if a.pilot else [*SIZES,(MODELS[m][1],)*2])]
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};report['status']='PASS' if report['implementation_unchanged'] and len(report['cases'])==len(jobs) and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
