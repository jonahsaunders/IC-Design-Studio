"""Sampled RF ps2nw masks, rotations, strict extraction and physical fault controls.

The original coupon is a single n-well junction, not a foundry PCell. The public
RF marker is retained. This does not qualify pw2dn or the complete RF family.
"""
import argparse
import json
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest, save_project, load_project
from icstudio.layout_import import read_layout
from icstudio.catalog import link_technology
from icstudio.interchange import export_layout
from icstudio.layout_verification import reference, run
from icstudio.sky130_rf_verification import MODEL, contacts, circuit
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos_layout import technology

SIZES=((2,2),(4,2),(2,4),(1,4),(4,4),(10,10))
FAULTS=('anode-licon','cathode-licon','anode-mcon','cathode-mcon','short',
        'guard-open','split-guard-metal','missing-marker','shifted-marker',
        'missing-nwell','extra-device-mask','floating-metal','duplicate-port',
        'reference-area','reference-perimeter','reference-polarity','reference-model')


def stream(path,w_um,l_um,angle=0,fault=None):
    import klayout.db as k
    w,l=round(w_um*1000),round(l_um*1000)
    if w%10 or l%10 or min(w,l)<1000:raise ValueError('Coupon dimensions must be at least 1 um on a 10 nm grid.')
    ly=k.Layout();ly.dbu=.001;c=ly.create_cell('rf_coupon')
    def box(pair,x1,y1,x2,y2):c.shapes(ly.layer(*pair)).insert(k.Box(x1,y1,x2,y2))
    def ring(pair,offset,thickness):
        r=k.Region(k.Box(-1800-offset,-1800-offset,w+1800+offset,l+1800+offset))-k.Region(k.Box(-1800-offset+thickness,-1800-offset+thickness,w+1800+offset-thickness,l+1800+offset-thickness))
        c.shapes(ly.layer(*pair)).insert(r)
    if fault!='missing-nwell':box((64,20),0,0,w,l)
    if fault!='missing-marker':
        shift=5 if fault=='shifted-marker' else 0
        box((81,125),shift,0,w+shift,l)
    cx,cy=w//2,l//2
    for pair,half in (((65,44),250),((93,44),380),((66,44),85),((67,20),170),((67,44),85),((68,20),170)):
        if fault=='cathode-licon' and pair==(66,44):continue
        if fault=='cathode-mcon' and pair==(67,44):continue
        box(pair,cx-half,cy-half,cx+half,cy+half)
    for pair,offset,thick in (((65,44),0,800),((94,20),130,1060),((67,20),0,800),((68,20),0,800)):
        ring(pair,offset,thick)
    points=[];gw,gh=w+3600,l+3600
    for x in [400,*range(800,gw-799,400),gw-400]:points.extend(((x,400),(x,gh-400)))
    for y in range(800,gh-799,400):points.extend(((400,y),(gw-400,y)))
    for x,y in dict.fromkeys(points):
        for pair,kind in (((66,44),'anode-licon'),((67,44),'anode-mcon')):
            if fault!=kind:box(pair,x-1885,y-1885,x-1715,y-1715)
    if fault=='short':
        c.shapes(ly.layer(68,20)).insert(k.Path([k.Point(-1400,-1400),k.Point(cx,-1400),k.Point(cx,cy)],340))
    if fault in ('guard-open','split-guard-metal'):
        # Cut both left and right sides: a single gap leaves an alternate ring path.
        cut=k.Region(k.Box(-2100,cy-100,w+2100,cy+100))
        for pair in (((65,44),) if fault=='guard-open' else ((67,20),(68,20))):
            shapes=c.shapes(ly.layer(*pair));r=k.Region(shapes)-cut;shapes.clear();shapes.insert(r)
    if fault=='extra-device-mask':box((65,20),500,500,1000,1000)
    if fault=='floating-metal':box((68,20),w+4000,0,w+4500,500)
    for name,x,y in [('A',-1400,-1400),('K',cx,cy)]:
        c.shapes(ly.layer(68,5)).insert(k.Text(name,k.Trans(x,y)))
    if fault=='duplicate-port':c.shapes(ly.layer(68,5)).insert(k.Text('K',k.Trans(-1400,-1400)))
    if angle:c.transform(k.Trans(angle//90,False,0,0))
    ly.write(str(path))


def selected(w,l,fault=None):
    area=w*l*(1.1 if fault=='reference-area' else 1)
    perimeter=2*(w+l)*(1.1 if fault=='reference-perimeter' else 1)
    nodes='K A' if fault=='reference-polarity' else 'A K'
    model=MODEL.replace('ps2nw','pw2dn') if fault=='reference-model' else MODEL
    return reference(f'.subckt rf_coupon A K\nXD {nodes} {model} area={area:g} perim={perimeter:g}\n.ends rf_coupon\n','rf_coupon')


def project(path,tech):
    p,_=read_layout(path);link_technology(p,tech);p['cells'][0]['ports']=['A','K'];return p


def write(path,data):path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--sky130',type=Path,required=True)
    ap.add_argument('--klayout',type=Path,required=True);ap.add_argument('--pilot',action='store_true')
    ap.add_argument('--geometry',choices=[f'{w}x{l}' for w,l in SIZES],help='Run one selected geometry; omission runs the full matrix.')
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tech,identity=technology('sky130A',a.sky130)
    files=[Path(__file__),ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    hashes={p.relative_to(ROOT).as_posix():file_digest(p) for p in files};write(out/'source-files.json',hashes)
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',package=identity,
                scope=__doc__,layouts=[],faults=[],source_files_sha256=file_digest(out/'source-files.json'))
    tools=dict(klayout=str(a.klayout.resolve(strict=True)))
    try:
        sizes=[tuple(map(int,a.geometry.split('x')))] if a.geometry else SIZES[:1] if a.pilot else SIZES
        for w,l in sizes:
            for angle in ((0,) if a.pilot else (0,90,180,270)):
                name=f'w{w:g}-l{l:g}-r{angle}';folder=out/name;folder.mkdir()
                gds=folder/'input.gds';stream(gds,w,l,angle)
                p=project(gds,tech);save_project(p,folder/'project.icproj');p=load_project(folder/'project.icproj')
                export_layout(p,folder/'roundtrip.oas');p=project(folder/'roundtrip.oas',tech)
                export_layout(p,folder/'roundtrip.gds');exchange=compare(gds,folder/'roundtrip.gds',text_presentation=False)
                r=run(p,p['top'],folder/'verification',tools,selected(w,l),lvs_extractor='sky130-rf-nwell-klayout')
                if r['status']!='passed':raise ValueError(name+': '+r.get('error','No pass.'))
                extracted=circuit((folder/'verification/lvs-extraction/native.cir').read_text(),'rf_coupon',native=True)
                if extracted['terminals']!=['A','K'] or abs(extracted['area_um2']-w*l)>1e-9 or abs(extracted['perimeter_um']-2*(w+l))>1e-9:
                    raise ValueError('Independent dimension/terminal audit failed.')
                report['layouts'].append(dict(name=name,width_um=w,length_um=l,angle=angle,exchange=exchange,native=extracted,report_sha256=file_digest(folder/'verification/report.json')))
                write(out/'record.json',report);print(name,'PASS',flush=True)
            for fault in FAULTS:
                name=f'w{w:g}-l{l:g}-{fault}';folder=out/name;folder.mkdir()
                gds=folder/'input.gds';stream(gds,w,l,fault=fault);p=project(gds,tech)
                r=run(p,p['top'],folder/'verification',tools,selected(w,l,fault),lvs_extractor='sky130-rf-nwell-klayout')
                stages={s['name']:s['status'] for s in r['stages']}
                proof=folder/'verification/lvs-extraction/contacts.json'
                if fault=='reference-model':ok=stages['preflight']=='failed' and 'Unexpected RF device' in r.get('error','')
                elif fault.startswith('reference-'):ok=stages['lvs_extraction']=='passed' and stages['lvs']=='failed' and 'RF strict LVS' in r.get('error','')
                else:ok=stages['preflight']=='passed' and proof.is_file() and not json.loads(proof.read_text())['passed']
                if not ok:raise ValueError(name+': intended fault was not caught by its required check: '+r.get('error',''))
                report['faults'].append(dict(name=name,detected=True,error=r.get('error'),report_sha256=file_digest(folder/'verification/report.json')))
                write(out/'record.json',report);print(name,'DETECTED',flush=True)
        if any(file_digest(ROOT/p)!=sha for p,sha in hashes.items()):raise ValueError('Source changed during qualification.')
        report['status']='PASS'
    except Exception as exc:report.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
    write(out/'record.json',report)
    print(json.dumps({k:report.get(k) for k in ('status','error')}),flush=True)
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
