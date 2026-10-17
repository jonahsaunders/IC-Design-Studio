"""Sampled public IHP NPN reference masks, four rotations and fault controls.

Explicit NPN-corrected package, full Magic DRC, unfiltered public KLayout
extraction and strict Netgen comparison. Not complete bipolar qualification.
"""
import argparse,json,math,re,sys,traceback
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
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
from scripts.qualify_ihp_resistor_layouts import regions,same_masks,rotated
from scripts.qualify_diode_layouts import detected_fault
from scripts.prepare_ihp_npn_qualification import prepare
SOURCE=ROOT/'icstudio/assets/physical/ihp_bipolars'
CASES=(('npn13G2L',.07,1,1),('npn13G2L$1',.07,2.5,1),('npn13G2L$2',.07,2,3),('npn13G2V$1',.12,1,2),('npn13G2V$2',.12,5,4),('npn13G2$2',.07,.9,2),('npn13G2',.07,.9,5),('npn13G2$3',.07,.9,8),('npn13G2$4',.07,.9,10))
FAULTS=('C-open','B-open','E-open','S-open','C-B-short','unrelated-diffusion','unrelated-well','reference-reversed','reference-width','reference-length','reference-count')


def model_name(item):
    return 'npn13G2l' if 'G2L' in item[0] else 'npn13G2v' if 'G2V' in item[0] else 'npn13G2'


def selected_reference(item,fault=None):
    name,w,l,nx=item;model=model_name(item)
    if fault=='reference-width':w*=1.2
    if fault=='reference-length':l*=1.2
    if fault=='reference-count':nx+=1
    nodes='E B C S' if fault=='reference-reversed' else 'C B E S'
    return reference(f'.subckt coupon C B E S\nX1 {nodes} {model} we={w:.12g}u le={l:.12g}u Nx={nx}\n.ends coupon\n','coupon')


def generate(tech,item,folder):
    name,w,l,nx=item;folder.mkdir();lock=json.loads((SOURCE/'SOURCE.json').read_bytes())
    for rel,r in lock['files'].items():
        if file_digest(SOURCE/rel)!=r['sha256']:raise ValueError('Changed public NPN fixture: '+rel)
    db=kdb();ly=db.Layout();ly.read(str(SOURCE/'npn_adv.gds'));target=db.Layout();target.dbu=ly.dbu
    c=target.create_cell('coupon');c.copy_tree(ly.cell(name));target.write(str(folder/'native.gds'))
    p,_=read_layout(folder/'native.gds');original=clone(p);link_technology(p,tech);c=p['cells'][0];c['ports']=['C','B','E','S'];metal=regions(p)
    for terminal in ('C','B','E'):
        labels=[t for t in c['layout_texts'] if t['text']==terminal]
        if len(labels)!=1:raise ValueError('Missing/ambiguous native NPN terminal.')
        point=[labels[0]['x'],labels[0]['y']];layer=(10,0) if terminal=='E' else (8,0)
        if not any(poly.inside(db.Point(*point)) for poly in metal[layer].each()):raise ValueError('NPN terminal outside its conductor.')
        mapped=next(v['name'] for v in p['pdk']['layers'] if (v['gds'],v['datatype'])==layer);assign_port(p,c['id'],terminal,mapped,point)
    same_masks(original,p)
    guards=[poly for poly in (metal[1,0]&metal[14,0]).merged().each() if poly.holes()==1]
    if len(guards)!=1:raise ValueError('Expected one public P+ guard ring.')
    guard=db.Region(guards[0]);additions=[]
    for part in guard.decompose_trapezoids_to_region().each():
        box=part.bbox()
        if part.area()!=box.area():raise ValueError('Unsupported nonrectangular guard segment.')
        additions.append(rect('Metal1.drawing',box.left,box.bottom,box.width(),box.height()))
        horizontal=box.width()>box.height();low,high=(box.left,box.right) if horizontal else (box.bottom,box.top)
        centers=list(range(low+250,high-249,1000))
        if high-250 not in centers:centers.append(high-250)
        centers=[v for i,v in enumerate(centers) if i==0 or v-centers[i-1]>=340]
        for value in centers:
            point=db.Point(value,box.center().y) if horizontal else db.Point(box.center().x,value)
            if not (db.Region(db.Box(point.x-150,point.y-150,point.x+150,point.y+150))-guard).is_empty():raise ValueError('Guard contact lacks required enclosure.')
            additions.append(rect('Cont.drawing',point.x-80,point.y-80,160,160))
    c['shapes']+=additions;assign_port(p,c['id'],'S','Metal1.drawing',[point.x,point.y])
    write(folder/'local-additions.json',additions)
    # The only geometry change is the explicit substrate connection inside the
    # existing P+ ring. Every original source mask remains a geometric subset.
    after=regions(p)
    for layer,old in metal.items():
        if not (old-after[layer]).is_empty():raise ValueError('Removed original NPN geometry.')
        if layer not in ((8,0),(6,0)) and not (old^after[layer]).is_empty():raise ValueError('Changed an NPN device mask.')
    return p


def altered(p,fault):
    q=clone(p);c=q['cells'][0];db=kdb();ls={(l['gds'],l['datatype']):l['name'] for l in q['pdk']['layers']};ports={v['name']:v for v in c['layout_ports']}
    if fault.endswith('-open'):
        terminal=fault[0];pair=(10,0) if terminal=='E' else (8,0);cut=(19,0) if terminal=='E' else (6,0)
        selected=[v for v in regions(q)[pair].each() if v.inside(db.Point(*ports[terminal]['point']))]
        if len(selected)!=1:raise ValueError('Expected one terminal conductor for fault.')
        removed=[s for s in c['shapes'] if s['layer']==ls[cut] and not (db.Region(polygon(s))&db.Region(selected[0])).is_empty()]
        if not removed:raise ValueError('No contacts selected for NPN open fault.')
        c['shapes']=[s for s in c['shapes'] if s not in removed]
    elif fault=='C-B-short':
        a,b=[ports[k]['point'] for k in ('C','B')];width=400
        c['shapes'] += [rect(ls[8,0],min(a[0],b[0])-200,a[1]-200,abs(a[0]-b[0])+width,width),rect(ls[8,0],b[0]-200,min(a[1],b[1])-200,width,abs(a[1]-b[1])+width)]
    elif fault in ('unrelated-diffusion','unrelated-well'):
        # Place a separate island in the device's interior keepout above the
        # active structure and below its guard. It must remain unexempted.
        allm=regions(q);guard=next(poly for poly in (allm[1,0]&allm[14,0]).merged().each() if poly.holes()==1)
        box=guard.bbox();x=box.center().x;y=box.top-1800
        c['shapes'].append(rect(ls[(1,0) if fault=='unrelated-diffusion' else (31,0)],x-200,y-200,400,400))
    else:raise ValueError('Unknown physical NPN fault.')
    return q


def audit_extracted(path,item,native=False):
    rows=[line.split() for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith(('*','.','+'))]
    name,w,l,nx=item;model=model_name(item)
    if len(rows)!=1 or rows[0][1:6]!=['C','B','E','S',model]:raise ValueError('NPN extraction changed model, device count or terminals.')
    params={k.lower():v for k,v in (s.split('=',1) for s in rows[0][6:])};expected={'we':w*1e-6,'le':l*1e-6,'nx':nx,'m':1}
    if set(params)!=set(expected):raise ValueError('Unexpected extracted NPN parameter set.')
    for key,value in expected.items():
        if not math.isclose(scalar(params[key]),value,rel_tol=1e-9,abs_tol=abs(value)*1e-10):raise ValueError('Wrong NPN geometry: '+key)
    return dict(model=model,terminals=rows[0][1:5],parameters=expected,sha256=file_digest(path))


def detected(result,folder,ports=('C','B','E','S')):
    if detected_fault(result,folder):return True
    stages={s['name']:s for s in result['stages']}
    if result['status']!='failed' or any(stages[s]['status']!='passed' for s in ('preflight','layout_export')):return False
    stage=stages['lvs_extraction'];path=folder/'lvs-extraction/native.cir'
    if stage['status']=='failed' and stage.get('error')=='IHP extracted port names differ from the schematic.' and path.is_file():
        text=path.read_text();declaration=re.findall(r'(?im)^\.subckt\s+coupon\s+([^\n]*)',text)
        return len(declaration)==1 and set(declaration[0].split())!=set(ports)
    return False


def case(tech,item,out,tools):
    folder=out/item[0];folder.mkdir();row=dict(name=item[0],geometry=item[1:],status='RUNNING',layouts=[],faults=[])
    try:
        p=generate(tech,item,folder/'source');save_project(p,folder/'saved.icproj');q=load_project(folder/'saved.icproj');same_masks(p,q);ref=selected_reference(item)
        for angle in (0,90,180,270):
            if angle:q=rotated(q)
            baseline=folder/f'baseline-{angle}.gds';export_layout(q,baseline);exported=folder/f'rotation-{angle}.oas';export_layout(q,exported)
            ly=kdb().Layout();ly.read(str(exported));external=folder/f'external-{angle}.oas';ly.write(str(external))
            imported,_=read_layout(external);link_technology(imported,tech);imported['cells'][0]['ports']=['C','B','E','S'];same_masks(q,imported)
            dest=folder/f'physical-{angle}';result=run(imported,imported['top'],dest,tools,ref,lvs_extractor='ihp-klayout')
            if result['status']!='passed':raise ValueError(result.get('error','Native NPN verification failed.'))
            row['layouts'].append(dict(rotation=angle,drc_count=result['drc_count'],report_sha256=file_digest(dest/'report.json'),exchange=compare(baseline,dest/'original.gds'),extracted=audit_extracted(dest/'lvs-extraction/extracted.spice',item),native=audit_extracted(dest/'lvs-extraction/native.cir',item,True)))
        for fault in FAULTS:
            q=p if fault.startswith('reference-') else altered(p,fault);selected=selected_reference(item,fault) if fault.startswith('reference-') else ref
            dest=folder/fault;result=run(q,q['top'],dest,tools,selected,lvs_extractor='ihp-klayout');found=detected(result,dest)
            if fault.startswith('unrelated-'):
                findings=(dest/'drc/findings.tsv').read_text();found=result['status']=='failed' and result.get('drc_count',0)>0 and 'No unrelated diffusion or well may exist in the NPN area' in findings
            row['faults'].append(dict(name=fault,detected=found,status=result['status'],report_sha256=file_digest(dest/'report.json'),error=result.get('error')))
            if not found:raise ValueError('NPN verification missed '+fault)
        row['status']='PASS'
    except Exception as e:row.update(status='FAIL',error=repr(e),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--magic',required=True);ap.add_argument('--netgen',required=True);ap.add_argument('--klayout',required=True);ap.add_argument('--workers',type=int,choices=range(1,5),default=2);ap.add_argument('--family',choices=('all','npn13G2','npn13G2l','npn13G2v'),default='all');a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'scripts/prepare_ihp_npn_qualification.py',ROOT/'scripts/qualify_diode_layouts.py',ROOT/'scripts/qualify_ihp_resistor_layouts.py',*sorted((ROOT/'icstudio').rglob('*.py'))];before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before)
    (out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    identity=prepare(ROOT/'icstudio/assets/pdks/ihp-sg13g2',out/'package');package=json.loads((out/'package/package.json').read_bytes());tech=clone(package['technology']);tech.update(package_root=str(out/'package'),package_lock={k:package[k] for k in ('id','revision','files')})
    tools={k:str(Path(getattr(a,k)).resolve(strict=True)) for k in ('magic','netgen','klayout')};report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,package=identity,cases=[])
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(case,tech,item,out,tools) for item in CASES if a.family=='all' or model_name(item)==a.family]
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};report['status']='PASS' if report['implementation_unchanged'] and len(report['cases'])==len(jobs) and all(r['status']=='PASS' for r in report['cases']) else 'FAIL';write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
