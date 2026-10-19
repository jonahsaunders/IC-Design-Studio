"""IHP varactor physical interfaces using pinned public masks and oxide formula.

Tests the 20 public W/L/Nx combinations in all orthogonal rotations. This does
not establish continuous geometry, operating-envelope or foundry qualification.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import re
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest, save_project, load_project
from icstudio.catalog import link_technology
from icstudio.layout_import import read_layout
from icstudio.layout_verification import reference, run
from icstudio.interchange import export_layout
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import load_technology, write

SOURCES=ROOT/'icstudio/assets/qualification/ihp-varactors'
SOURCE_HASH='9dc6002cb1e3f22c42c4ef8a72907bd249d3ee175a15368b25f9873120f1f77a'
GENERATOR_HASH='276fd8eae4a8faf7a4a15b03909fe8b2c77574372359eb7a8f6e75f005d7d31f'
FAULTS=('missing-oxide','missing-recognition','duplicate-recognition','gate-open','gate-short',
        'reference-width','reference-length','reference-fingers','reference-multiplicity',
        'reference-well','reference-substrate','reference-gate')


def contact_ties(ly,c,nx):
    """Explicit small-device coupon additions; never repair an imported design."""
    import klayout.db as k
    # Extend the right well/active/oxide boundary by 300 nm to provide room for
    # a second well-contact column. The original gates and all pins stay intact.
    for layer in (1,31,32,44):
        shapes=[s for s in c.shapes(ly.layer(layer,0)).each() if s.bbox().left>=-100]
        if not shapes:continue  # The missing-oxide fault must remain missing.
        shape=max(shapes,key=lambda s:s.bbox().width());b=shape.bbox()
        shape.box=k.Box(b.left,b.bottom,b.right+300,b.top)
    x=730+1100*nx;well=[];substrate=[]
    for y in range(700,4000,340):
        box=k.Box(x,y,x+160,y+160);c.shapes(ly.layer(6,0)).insert(box);well.append(box)
    c.shapes(ly.layer(8,0)).insert(k.Box(x-20,650,x+180,4320))
    # Contact the two original parasitic substrate tabs beyond the well/oxide
    # clearance. 300 nm active encloses each 160 nm cut by 70 nm; its 300 nm
    # square metal meets the original 0.09 um2 minimum area.
    stubs=[s.bbox() for s in c.shapes(ly.layer(1,0)).each() if s.bbox().width()==240]
    for b in stubs:
        y=b.bottom-600 if b.bottom<0 else b.top+300;cx=b.center().x
        lower,upper=(y,b.bottom+220) if b.bottom<0 else (b.top-220,y+300)
        c.shapes(ly.layer(1,0)).insert(k.Box(cx-150,lower,cx+150,upper))
        c.shapes(ly.layer(14,0)).insert(k.Box(cx-330,lower-180,cx+330,upper+180))
        box=k.Box(cx-80,y+70,cx+80,y+230);c.shapes(ly.layer(6,0)).insert(box);substrate.append(box)
        c.shapes(ly.layer(8,0)).insert(k.Box(cx-150,y,cx+150,y+300))
    return dict(well=well,substrate=substrate)


def stream(target, size, nx, rotation=0, fault=None, sources=SOURCES, contacted=False):
    import klayout.db as k
    sources=Path(sources)
    if file_digest(sources/'sg13_hv_svaricap.gds')!=SOURCE_HASH or file_digest(sources/'SVaricap_code.py')!=GENERATOR_HASH:
        raise ValueError('Changed public IHP varactor source.')
    if size not in ('small','large') or nx not in range(1,11) or rotation not in (0,90,180,270):
        raise ValueError('Choose one of the public varactor geometries and an orthogonal rotation.')
    if contacted and size!='small':raise ValueError('Additional ties are reviewed only for the small varactor geometries.')
    w,l=(3740,300) if size=='small' else (9740,800)
    name=('SVaricap' if nx==2 else 'SVaricap$'+str(1 if nx==1 else nx-1)) if size=='small' else 'SVaricap$'+str(20-nx)
    old=k.Layout();old.read(str(sources/'sg13_hv_svaricap.gds'));leaf=old.cell(name)
    if leaf is None or any(leaf.each_inst()) or old.dbu!=.001:raise ValueError('Unexpected public varactor fixture.')
    ly=k.Layout();ly.dbu=old.dbu;c=ly.create_cell('varactor_coupon');c.copy_tree(leaf)
    if not c.shapes(ly.layer(44,0)).is_empty():raise ValueError('Public fixture already has oxide; review the correction.')
    oxide=k.Box(-100,-790,1150+nx*(500+2*l),w+1820)
    # Exact dbCreateRect(gateOx, ...) expression in the pinned public PCell,
    # absent from its separate LVS test GDS. Never adjust geometry to a result.
    if fault!='missing-oxide':c.shapes(ly.layer(44,0)).insert(oxide)
    pins=sorted([s.bbox() for s in c.shapes(ly.layer(8,2)).each() if not s.is_text()],key=lambda b:b.center().y)
    if len(pins)!=3:raise ValueError('Unexpected public G1/W/G2 pin masks.')
    for label,box in zip(('G1','W','G2'),pins):c.shapes(ly.layer(8,2)).insert(k.Text(label,k.Trans(box.center())))
    for layer,box in ((1,(-10000,-10000,-8000,-8000)),(14,(-10180,-10180,-7820,-7820)),(8,(-10000,-10000,-8000,-8000))):
        c.shapes(ly.layer(layer,0)).insert(k.Box(*box))
    for x in range(-9800,-8300,400):
        for y in range(-9800,-8300,400):c.shapes(ly.layer(6,0)).insert(k.Box(x,y,x+160,y+160))
    c.shapes(ly.layer(8,2)).insert(k.Text('S',k.Trans(-9000,-9000)))
    additions=contact_ties(ly,c,nx) if contacted else {}
    if fault=='missing-recognition':c.shapes(ly.layer(63,0)).clear()
    elif fault=='duplicate-recognition':
        t=next(s.text for s in c.shapes(ly.layer(63,0)).each() if s.is_text())
        c.shapes(ly.layer(63,0)).insert(k.Text(t.string,k.Trans(t.x+1,t.y)))
    elif fault=='gate-open':
        poly=min(k.Region(c.shapes(ly.layer(5,0))).merged().each(),key=lambda polygon:polygon.bbox().bottom)
        for s in list(c.shapes(ly.layer(6,0)).each()):
            if not (k.Region(s.polygon)&k.Region(poly)).is_empty():s.delete()
    elif fault=='gate-short':
        a,b=pins[0].center(),pins[1].center()
        c.shapes(ly.layer(8,0)).insert(k.Box(b.x-130,a.y-130,a.x+130,b.y+130))
    elif fault in ('missing-well-ties','missing-substrate-ties'):
        if not contacted:raise ValueError('Tie faults require the explicitly contacted coupon.')
        boxes=additions['well' if fault=='missing-well-ties' else 'substrate']
        for s in list(c.shapes(ly.layer(6,0)).each()):
            if s.bbox() in boxes:s.delete()
    elif fault in ('mixed-contact-width','varactor-contact-width'):
        active=k.Region(c.shapes(ly.layer(1,0))).merged();poly=k.Region(c.shapes(ly.layer(5,0))).merged()
        for s in c.shapes(ly.layer(6,0)).each():
            cut=k.Region(s.polygon);overlap=(cut&active).area()
            selected=(0<overlap<cut.area()) if fault=='mixed-contact-width' else overlap==cut.area()
            if selected and (cut&poly).area()==cut.area():
                b=s.bbox();s.box=k.Box(b.left,b.bottom,b.right-5,b.top);break
        else:raise ValueError('No matching contact for the width fault.')
    elif fault not in (None,'missing-oxide'):raise ValueError('Unknown physical varactor fault.')
    if rotation:c.transform(k.Trans(rotation//90,False,0,0))
    ly.write(str(target))
    return dict(source_sha256=SOURCE_HASH,source_cell=name,generator_sha256=GENERATOR_HASH,
                oxide_rectangle_nm=[oxide.left,oxide.bottom,oxide.right,oxide.top],
                correction='Add the exact ThickGateOx rectangle from the pinned public SVaricap generator; the separate LVS fixture omits it.',
                added_geometry='Conductor labels on the original three pin masks; separate 2x2 um contacted p+ substrate tie.',
                w_nm=w,l_nm=l,nx=nx,contacted=contacted,
                contact_additions_nm={key:[[b.left,b.bottom,b.right,b.top] for b in boxes] for key,boxes in additions.items()})


def selected(size,nx,fault=None):
    w,l=(3.74e-6,.3e-6) if size=='small' else (9.74e-6,.8e-6)
    values=dict(w=w,l=l,nx=nx,m=1);nodes=['G1','W','G2','S']
    key={'reference-width':'w','reference-length':'l','reference-fingers':'nx','reference-multiplicity':'m'}.get(fault)
    if key:values[key]*=2
    elif fault=='reference-well':nodes[1]='G1'
    elif fault=='reference-substrate':nodes[3]='W'
    elif fault=='reference-gate':nodes[2]='G1'
    elif fault is not None:raise ValueError('Unknown varactor reference fault.')
    line='C1 '+' '.join(nodes)+' sg13_hv_svaricap '+' '.join(k+'='+str(v) for k,v in values.items())
    return reference('.subckt varactor_coupon G1 W G2 S\n'+line+'\n.ends varactor_coupon\n','varactor_coupon')


def detected(result,folder,fault):
    stages={s['name']:s for s in result['stages']};folder=Path(folder)
    if result['status']!='failed' or any(stages.get(n,{}).get('status')!='passed' for n in ('preflight','layout_export')):return False
    if fault in ('mixed-contact-width','varactor-contact-width','missing-well-ties','missing-substrate-ties'):
        findings=folder/'drc/findings.tsv';width=fault.endswith('contact-width')
        if not (result.get('drc_count',0)>0 and findings.is_file()
                and all(stages.get(n,{}).get('status')=='passed' for n in ('lvs_extraction','lvs','integrity'))):return False
        if width:
            extra=json.loads((folder/'drc/ihp-contact-width.json').read_bytes())
            return 'Cnt.a' in findings.read_text() and extra['violations']>0
        return 'LU.d, LU.d1' in findings.read_text()
    if fault=='missing-oxide':
        findings=folder/'drc/findings.tsv'
        return (isinstance(result.get('drc_count'),int) and result['drc_count']>0
                and findings.is_file() and 'Poly overhang of transistor' in findings.read_text()
                and all(stages.get(n,{}).get('status')=='passed' for n in ('lvs_extraction','lvs','integrity')))
    if fault in ('missing-recognition','duplicate-recognition','gate-open','gate-short'):
        native=folder/'lvs-extraction/native.cir'
        errors={'missing-recognition':'IHP extraction produced no circuit devices; an empty circuit cannot pass LVS.',
                'duplicate-recognition':'IHP extraction did not retain every marked varactor exactly once.',
                'gate-open':'IHP extracted port names differ from the schematic.',
                'gate-short':'IHP extracted port names differ from the schematic.'}
        return stages.get('lvs_extraction',{}).get('error')==errors[fault] and native.is_file()
    log=folder/'lvs/lvs.log'
    return (all(stages.get(n,{}).get('status')=='passed' for n in ('drc','lvs_extraction','integrity'))
            and stages.get('lvs',{}).get('error')=='Netgen did not establish a unique match with equivalent connected pins and no property errors. See lvs/lvs.log.'
            and log.is_file() and re.search(r'Circuits do not match|Property errors|Netlists do not match|disconnected node:|\(no matching pin\)|failed pin matching',log.read_text(),re.I) is not None)


def run_case(job):
    size,nx,rotation,fault,root,sources,contacted,tech,tools=job
    folder=Path(root)/f'{size}-{nx}-{rotation}-{fault}';folder.mkdir();row=dict(size=size,nx=nx,rotation=rotation,fault=fault)
    try:
        write(folder/'source.json',stream(folder/'source.gds',size,nx,rotation,fault if fault and not fault.startswith('reference-') else None,sources,contacted=contacted))
        ref=selected(size,nx,fault if fault and fault.startswith('reference-') else None)
        p,_=read_layout(folder/'source.gds');link_technology(p,tech);p['cells'][0]['ports']=ref['ports']
        save_project(p,folder/'saved.icproj');p=load_project(folder/'saved.icproj')
        export_layout(p,folder/'export.gds');export_layout(p,folder/'export.oas')
        row['exchange']=compare(folder/'export.gds',folder/'export.oas',text_presentation=False)
        result=run(p,p['top'],folder/'verification',tools,ref,lvs_extractor='ihp-klayout')
        row.update(native_status=result['status'],drc_count=result.get('drc_count'),error=result.get('error'),report_sha256=file_digest(folder/'verification/report.json'))
        row['status']='PASS' if (detected(result,folder/'verification',fault) if fault else result['status']=='passed') else 'FAIL'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row)
    return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--sources',type=Path,default=SOURCES);ap.add_argument('--pilot',action='store_true')
    ap.add_argument('--size',choices=('small','large','all'),default='all',help='Explicit physical subset; larger public fixtures currently retain unresolved Magic well findings.')
    ap.add_argument('--contacted',action='store_true',help='Add the explicitly documented well/substrate ties to small coupons; original-source mode stays available.')
    ap.add_argument('--workers',type=int,choices=range(1,5),default=2,help='Independent native cases; completed records are published by the parent.')
    for n in ('magic','netgen','klayout'):ap.add_argument('--'+n,required=True)
    a=ap.parse_args()
    if a.contacted and a.size!='small':ap.error('--contacted requires --size small')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tools={n:str(Path(getattr(a,n)).resolve(strict=True)) for n in ('magic','netgen','klayout')}
    tech,identity=load_technology('ihp-sg13g2');rows=[]
    files=[Path(__file__),*sorted((ROOT/'icstudio').glob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in files};write(out/'source-files.json',before)
    sizes=('small','large') if a.size=='all' else (a.size,)
    cases=[(s,n,r,None) for s in sizes for n in (range(1,2) if a.pilot else range(1,11)) for r in ((0,) if a.pilot else (0,90,180,270))]
    cases += [(s,1,0,f) for s in sizes for f in FAULTS]
    if a.contacted:
        cases += [('small',n,r,f) for n,f in ((4,'mixed-contact-width'),(4,'varactor-contact-width'),(10,'missing-well-ties'),(10,'missing-substrate-ties')) for r in ((0,) if a.pilot else (0,90,180,270))]
    completed={}
    def publish(index,row):
        completed[index]=row;write(out/'progress.json',[completed[i] for i in sorted(completed)])
        print(row['size'],row['nx'],row['rotation'],row['fault'],row['status'],row.get('error',''),flush=True)
    jobs=[(*case,out,a.sources,a.contacted,tech,tools) for case in cases]
    if a.workers==1:
        for index,job in enumerate(jobs):publish(index,run_case(job))
    else:
        with ProcessPoolExecutor(max_workers=a.workers) as executor:
            futures={executor.submit(run_case,job):i for i,job in enumerate(jobs)}
            for future in as_completed(futures):publish(futures[future],future.result())
    rows=[completed[i] for i in range(len(cases))]
    unchanged=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,default_promoted=False,process=identity,
                scope=__doc__,selected_sizes=list(sizes),contacted=a.contacted,workers=a.workers,cases=rows,implementation_unchanged=unchanged,
                status='PASS' if unchanged and all(r['status']=='PASS' for r in rows) else 'FAIL')
    write(out/'qualification.json',report)
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
