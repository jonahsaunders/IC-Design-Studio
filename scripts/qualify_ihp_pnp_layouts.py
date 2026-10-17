"""Sampled public IHP lateral PNP layouts with native terminal/geometry checks.

This covers five rectangular single-emitter layouts at two orientations, not
the NPN/HBT families, thermal/RF behavior or a continuous operating envelope.
"""
import argparse,math,re,subprocess,sys,traceback
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,file_digest,load_project,save_project,scalar
from icstudio.catalog import link_technology
from icstudio.layout import kdb,polygon,rect
from icstudio.layout_import import read_layout
from icstudio.physical_cells import assign_port,infer_ports
from icstudio.layout_verification import reference,run
from icstudio.interchange import export_layout
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import load_technology,write
from scripts.qualify_ihp_resistor_layouts import regions,same_masks,rotated
from scripts.qualify_diode_layouts import detected_fault
from scripts.qualify_ihp_npn_layouts import detected as ihp_fault_detected
SIZES=((2,.7),(2,5),(10,.7),(2,7),(7,2))
FAULTS=('collector-open','base-open','emitter-open','collector-emitter-short','reference-reversed','reference-area','reference-perimeter')


def selected_reference(w,l,fault=None):
    area=w*l*1e-12*(1.2 if fault=='reference-area' else 1);perimeter=2*(w+l)*1e-6*(1.2 if fault=='reference-perimeter' else 1)
    nodes='E B C' if fault=='reference-reversed' else 'C B E'
    # Native comparison uses zero tolerance for a/p. Stable decimal rendering
    # avoids exposing binary float multiplication noise in exact geometry.
    return reference(f'.subckt coupon C B E\nX1 {nodes} pnpMPA a={area:.12g} p={perimeter:.12g}\n.ends coupon\n','coupon')


def generate(tech,w,l,folder,magic):
    if (w,l) not in SIZES:raise ValueError('Use a reviewed sampled PNP geometry.')
    folder.mkdir();source=Path(tech['package_root'])/'libs.tech/magic'
    script=f'''tech load {{{source/'ihp-sg13g2.tech'}}}
scalegrid 1 2
drc euclidean on
random seed 12345
source {{{source/'ihp-sg13g2.tcl'}}}
load coupon -silent
box values 0 0 0 0
set parameters [dict merge [sg13g2::pnpMPA_defaults] [dict create w {w:g} l {l:g} doports 1 vias 0]]
if {{[catch {{sg13g2::pnpMPA_draw $parameters}} err]}} {{puts stderr "GENERATOR_FAILED $err"; quit -noprompt}}
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
    if r.returncode or log.count(b'GENERATOR_COMPLETE')!=1 or re.search(rb'GENERATOR_FAILED|Unknown layer:|\d+ problems occurred',log):raise ValueError('Native generator failed; see console.log.')
    p,_=read_layout(folder/'coupon.gds');raw=clone(p);link_technology(p,tech);c=p['cells'][0];c['ports']=['C','B','E'];pins=infer_ports(p,c)
    if len(pins)!=3 or {v['name'] for v in pins}!=set(c['ports']):raise ValueError('Missing/ambiguous PNP interface.')
    metal=regions(p)[8,0];db=kdb();components=list(metal.each())
    if len(components)!=3:raise ValueError('Expected three independent PNP metal conductors.')
    for pin in pins:
        selected=[v for v in components if v.inside(db.Point(*pin['point']))]
        if len(selected)!=1 or pin['layer']!='Metal1.drawing':raise ValueError('PNP terminal is outside its expected conductor.')
        assign_port(p,c['id'],pin['name'],pin['layer'],pin['point'])
    by={v['name']:v for v in c['layout_ports']}
    if by['E']['point']!=[0,0] or abs(by['C']['point'][1])<=abs(by['B']['point'][1]):raise ValueError('PNP central emitter, inner base and outer collector were not preserved.')
    same_masks(raw,p);return p


def altered(p,fault):
    q=clone(p);c=q['cells'][0];db=kdb();ls={(l['gds'],l['datatype']):l['name'] for l in q['pdk']['layers']};ports={v['name']:v for v in c['layout_ports']}
    if fault.endswith('-open'):
        name={'collector-open':'C','base-open':'B','emitter-open':'E'}[fault];pin=ports[name]
        selected=[v for v in regions(q)[8,0].each() if v.inside(db.Point(*pin['point']))]
        if len(selected)!=1:raise ValueError('PNP port does not select one conductor.')
        removed=[s for s in c['shapes'] if s['layer']==ls[6,0] and not (db.Region(polygon(s))&db.Region(selected[0])).is_empty()]
        if not removed:raise ValueError('No PNP contacts selected for open control.')
        c['shapes']=[s for s in c['shapes'] if s not in removed]
    elif fault=='collector-emitter-short':
        a,b=[ports[k]['point'] for k in ('C','E')];width=400
        c['shapes'] += [rect(ls[8,0],min(a[0],b[0])-width//2,a[1]-width//2,abs(a[0]-b[0])+width,width),rect(ls[8,0],b[0]-width//2,min(a[1],b[1])-width//2,width,abs(a[1]-b[1])+width)]
    else:raise ValueError('Unknown PNP physical fault.')
    return q


def audit_extracted(path,w,l):
    rows=[line.split() for line in path.read_text().splitlines() if re.match(r'(?i)^x\S+\s',line)]
    if len(rows)!=1 or rows[0][1:5]!=['C','B','E','pnpMPA']:raise ValueError('Extracted PNP model/terminals differ.')
    params={k.lower():v for k,v in (s.split('=',1) for s in rows[0][5:] if '=' in s)};expected={'a':w*l*1e-12,'p':2*(w+l)*1e-6}
    for key,value in expected.items():
        if key not in params or not math.isclose(scalar(params[key]),value,rel_tol=1e-9,abs_tol=abs(value)*1e-10):raise ValueError('Extracted PNP geometry differs: '+key)
    return dict(model='pnpMPA',terminals=['C','B','E'],parameters=expected,sha256=file_digest(path))


def case(tech,w,l,out,tools):
    name=f'pnpMPA-w{w:g}-l{l:g}';folder=out/name;folder.mkdir();row=dict(name=name,width_um=w,length_um=l,status='RUNNING',layouts=[],faults=[])
    try:
        p=generate(tech,w,l,folder/'generator',tools['magic']);ref=selected_reference(w,l);save_project(p,folder/'saved.icproj')
        reopened=load_project(folder/'saved.icproj');same_masks(p,reopened)
        for angle in (0,90):
            q=reopened if angle==0 else rotated(reopened);baseline=folder/f'baseline-{angle}.gds';export_layout(q,baseline)
            exported=folder/f'rotation-{angle}.oas';export_layout(q,exported);ly=kdb().Layout();ly.read(str(exported));external=folder/f'external-{angle}.oas';ly.write(str(external))
            imported,_=read_layout(external);link_technology(imported,tech);imported['cells'][0]['ports']=['C','B','E'];same_masks(q,imported);outgds=folder/f'reimported-{angle}.gds';export_layout(imported,outgds)
            exchange=dict(full_gds=compare(baseline,outgds),oasis=compare(external,outgds,text_presentation=False));dest=folder/f'physical-{angle}';result=run(imported,imported['top'],dest,tools,ref,lvs_extractor='ihp-klayout')
            if result['status']!='passed':raise ValueError(result.get('error','Native PNP verification failed.'))
            row['layouts'].append(dict(rotation=angle,native_status=result['status'],drc_count=result['drc_count'],exchange=exchange,report_sha256=file_digest(dest/'report.json'),extracted=audit_extracted(dest/'lvs-extraction/extracted.spice',w,l)))
        for fault in FAULTS:
            q=p if fault.startswith('reference-') else altered(p,fault);selected=selected_reference(w,l,fault) if fault.startswith('reference-') else ref
            dest=folder/fault;result=run(q,q['top'],dest,tools,selected,lvs_extractor='ihp-klayout');detected=ihp_fault_detected(result,dest,('C','B','E'))
            row['faults'].append(dict(name=fault,detected=detected,status=result['status'],report_sha256=file_digest(dest/'report.json'),error=result.get('error')))
            if not detected:raise ValueError('Native PNP checks missed '+fault)
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--magic',required=True);ap.add_argument('--netgen',required=True);ap.add_argument('--klayout',required=True);ap.add_argument('--workers',type=int,choices=range(1,5),default=2);a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'scripts/qualify_diode_layouts.py',ROOT/'scripts/qualify_ihp_resistor_layouts.py',ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    tech,identity=load_technology('ihp-sg13g2');tools={k:str(Path(getattr(a,k)).resolve(strict=True)) for k in ('magic','netgen','klayout')};report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,process=identity,source_files_sha256=file_digest(out/'source-files.json'),cases=[])
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(case,tech,w,l,out,tools) for w,l in SIZES]
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};report['status']='PASS' if report['implementation_unchanged'] and len(report['cases'])==len(jobs) and all(r['status']=='PASS' for r in report['cases']) else 'FAIL';report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
