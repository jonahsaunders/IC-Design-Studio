"""Selected public IHP resistor PCells through editable exchange and native checks.

Uses the immutable bundled Magic generators with Metal1 terminals (vias=0).
Selected straight, single-device geometries are not a continuous geometry range,
electrical characterization, statistical, density or fabrication qualification.
"""
import argparse,json,math,re,subprocess,sys,traceback
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,file_digest,load_project,save_project,scalar
from icstudio.catalog import link_technology
from icstudio.layout import kdb,polygon,rect
from icstudio.layout_import import read_layout
from icstudio.physical_cells import infer_ports,assign_port
from icstudio.layout_verification import reference,run
from icstudio.interchange import export_layout
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import load_technology,write
from scripts.qualify_standard_mos_layout import fault_detected
from scripts.qualification_geometry import regions,same_masks,rotated

MODELS=('rsil','rppd','rhigh')
SIZES=((.5,.5),(.5,20),(20,.5),(2,7),(7,2))
FAULTS=('terminal-open','body-open','terminal-short','reference-width','reference-model')






def selected_reference(model,w,l):
    if model not in MODELS:raise ValueError('Unknown reviewed resistor.')
    extra='' if model=='rsil' else ' b=0'
    return reference(f'.subckt coupon R1 R2 B\nX1 R1 R2 B {model} w={w:g}u l={l:g}u m=1{extra}\n.ends coupon\n','coupon')


def generate(tech,model,w,l,folder,magic):
    if model not in MODELS or (w,l) not in SIZES:raise ValueError('Use a reviewed sampled geometry.')
    folder.mkdir();source=Path(tech['package_root'])/'libs.tech/magic'
    # Model/dimensions come only from the finite reviewed cases above.
    script=f'''tech load {{{source/'ihp-sg13g2.tech'}}}
source {{{source/'ihp-sg13g2.tcl'}}}
load coupon -silent
box values 0 0 0 0
set parameters [dict merge [sg13g2::{model}_defaults] [dict create w {w:g} l {l:g} doports 1 vias 0]]
if {{[catch {{sg13g2::{model}_draw $parameters}} err]}} {{puts stderr "GENERATOR_FAILED $err"; quit -noprompt}}
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
    if r.returncode or log.count(b'GENERATOR_COMPLETE')!=1 or b'GENERATOR_FAILED' in log or re.search(rb'\d+ problems occurred',log):
        raise ValueError('Native generator failed; see console.log.')
    p,_=read_layout(folder/'coupon.gds');raw=clone(p);link_technology(p,tech);c=p['cells'][0];c['ports']=['R1','R2','B']
    ports=infer_ports(p,c)
    if len(ports)!=3 or {v['name'] for v in ports}!=set(c['ports']):raise ValueError('Missing/ambiguous native resistor ports.')
    for port in ports:
        metal=kdb().Region()
        for s in c['shapes']:
            if s['layer']==port['layer']:metal.insert(polygon(s))
        if not any(poly.inside(kdb().Point(*port['point'])) for poly in metal.merged().each()):raise ValueError('Port lies outside its conductor.')
        assign_port(p,c['id'],port['name'],port['layer'],port['point'])
    same_masks(raw,p);return p




def altered(p,fault,metal_pair=(8,0),contact_pair=(6,0)):
    q=clone(p);c=q['cells'][0];db=kdb();ls={(l['gds'],l['datatype']):l['name'] for l in q['pdk']['layers']}
    ports={v['name']:v for v in c['layout_ports']}
    if fault in ('terminal-open','body-open'):
        pin=ports['R1' if fault=='terminal-open' else 'B'];metal=regions(q)[metal_pair]
        selected=[poly for poly in metal.each() if poly.inside(db.Point(*pin['point']))]
        if len(selected)!=1:raise ValueError('Port does not select one connected conductor.')
        region=db.Region(selected[0]);removed=[s for s in c['shapes'] if s['layer']==ls[contact_pair] and not (db.Region(polygon(s))&region).is_empty()]
        if not removed:raise ValueError('No contacts selected by the negative control.')
        c['shapes']=[s for s in c['shapes'] if s not in removed]
    elif fault=='terminal-short':
        a,b=[ports[k]['point'] for k in ('R1','R2')];width=400
        c['shapes'] += [rect(ls[metal_pair],min(a[0],b[0])-width//2,a[1]-width//2,abs(a[0]-b[0])+width,width),
            rect(ls[metal_pair],b[0]-width//2,min(a[1],b[1])-width//2,width,abs(a[1]-b[1])+width)]
    else:raise ValueError('Unknown physical resistor control.')
    return q


def audit_extracted(path,model,w,l):
    text=path.read_text();lines=[line.split() for line in text.splitlines() if re.match(r'(?i)^x\S+\s',line)]
    if len(lines)!=1:raise ValueError('Expected exactly one extracted resistor.')
    row=lines[0]
    if len(row)<7 or row[4]!=model or set(row[1:3])!={'R1','R2'} or row[3]!='B':
        raise ValueError('Extracted resistor model or terminals differ.')
    params=dict(v.split('=',1) for v in row[5:] if '=' in v)
    for key,value in (('w',w),('l',l)):
        if key not in params or not math.isclose(scalar(params[key])*1e6,value,rel_tol=1e-10,abs_tol=1e-9):
            raise ValueError('Extracted resistor dimension differs: '+key)
    return dict(model=model,terminals=row[1:4],width_um=w,length_um=l,sha256=file_digest(path))


def case(tech,model,w,l,out,tools):
    name=f'{model}-w{w:g}-l{l:g}';folder=out/name;folder.mkdir();row=dict(name=name,model=model,width_um=w,length_um=l,status='RUNNING',layouts=[],faults=[])
    try:
        p=generate(tech,model,w,l,folder/'generator',tools['magic']);ref=selected_reference(model,w,l)
        save_project(p,folder/'saved.icproj');reopened=load_project(folder/'saved.icproj');same_masks(p,reopened)
        for angle in (0,90):
            q=reopened if angle==0 else rotated(reopened)
            baseline=folder/f'baseline-{angle}.gds';export_layout(q,baseline)
            exported=folder/f'rotation-{angle}.oas';export_layout(q,exported)
            # Import an independent OASIS rewrite, without an application sidecar.
            ly=kdb().Layout();ly.read(str(exported));external=folder/f'external-{angle}.oas';ly.write(str(external))
            imported,_=read_layout(external);link_technology(imported,tech);imported['cells'][0]['ports']=['R1','R2','B']
            same_masks(q,imported);outgds=folder/f'reimported-{angle}.gds';export_layout(imported,outgds)
            # OASIS has no native text appearance. Require full presentation
            # agreement with the original GDS as well as electrical anchors
            # and geometry agreement with the independently rewritten OASIS.
            exchange=dict(full_gds=compare(baseline,outgds),oasis=compare(external,outgds,text_presentation=False))
            dest=folder/f'physical-{angle}';result=run(imported,imported['top'],dest,tools,ref)
            item=dict(rotation=angle,native_status=result['status'],drc_count=result.get('drc_count'),exchange=exchange,report_sha256=file_digest(dest/'report.json'))
            if result['status']!='passed':raise ValueError(result.get('error','Native verification failed.'))
            item['extracted']=audit_extracted(dest/'lvs-extraction/extracted.spice',model,w,l);row['layouts'].append(item)
        for fault in FAULTS:
            q=altered(p,fault) if not fault.startswith('reference-') else p
            selected=selected_reference(model,w*1.2,l) if fault=='reference-width' else selected_reference(MODELS[(MODELS.index(model)+1)%len(MODELS)],w,l) if fault=='reference-model' else ref
            dest=folder/fault;result=run(q,q['top'],dest,tools,selected);detected=fault_detected(result,dest)
            row['faults'].append(dict(name=fault,kind='schematic reference' if fault.startswith('reference-') else 'physical geometry',detected=detected,status=result['status'],report_sha256=file_digest(dest/'report.json'),error=result.get('error')))
            if not detected:raise ValueError('Native checks did not detect '+fault)
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--magic',required=True);ap.add_argument('--netgen',required=True)
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,5),default=2);a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'scripts/qualification_geometry.py',ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    tech,identity=load_technology('ihp-sg13g2');tools={k:str(Path(getattr(a,k)).resolve(strict=True)) for k in ('magic','netgen')}
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,process=identity,source_files_sha256=file_digest(out/'source-files.json'),cases=[])
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(case,tech,model,w,l,out,tools) for model in MODELS for w,l in ([(2,7)] if a.pilot else SIZES)]
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['implementation_unchanged'] and len(report['cases'])==len(jobs) and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
