"""Check three-terminal RF p-well planar geometry, contacts and native faults.

The reference records are geometry-only and cannot be used as SPICE models.
"""
import argparse
import json
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest,save_project,load_project
from icstudio.catalog import link_technology
from icstudio.layout_import import read_layout
from icstudio.interchange import export_layout
from icstudio.layout_verification import reference,run
from icstudio.sky130_rf_isolation import MODELS,circuit
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos_layout import technology

SIZES=((1.28,4),(2,2),(4,2),(2,4),(4,4),(10,10))
PHYSICAL_FAULTS=('anode-licon','anode-mcon','cathode-licon','cathode-mcon',
    'substrate-licon','substrate-mcon','anode-cathode-short','substrate-cathode-short',
    'cathode-ring-open','substrate-ring-open','cathode-metal-split','substrate-metal-split',
    'missing-marker','shifted-marker','missing-dnwell','dnwell-gap','missing-nwell',
    'extra-device-mask','floating-metal','duplicate-port','uncontacted-tap','nwell-hole-spacing')
REFERENCE_FAULTS=('reference-rf-area','reference-rf-perimeter','reference-dnw-area',
    'reference-dnw-perimeter','reference-skirt-area','reference-skirt-perimeter',
    'reference-polarity','reference-missing-isolation','reference-electrical-model')


def stream(path,w_um,l_um,angle=0,fault=None):
    import klayout.db as k
    w,l=round(w_um*1000),round(l_um*1000)
    if w%10 or l%10 or min(w,l)<1000 or angle not in (0,90,180,270):raise ValueError('Unsupported coupon dimensions or rotation.')
    if fault=='nwell-hole-spacing':w=1000
    ly=k.Layout();ly.dbu=.001;c=ly.create_cell('rf_isolation')
    def rect(pair,x1,y1,x2,y2):c.shapes(ly.layer(*pair)).insert(k.Box(x1,y1,x2,y2))
    def ring(pair,outer,inner):
        r=k.Region(k.Box(-outer,-outer,w+outer,l+outer))-k.Region(k.Box(-inner,-inner,w+inner,l+inner))
        c.shapes(ly.layer(*pair)).insert(r)
    if fault!='missing-dnwell':rect((64,18),-1100,-1100,w+1100,l+1100)
    if fault!='missing-nwell':ring((64,20),1500,0)
    if fault!='missing-marker':
        shift=5 if fault=='shifted-marker' else 0;rect((81,125),shift,0,w+shift,l)
    cx,cy=w//2,l//2
    for pair,half in (((65,44),250),((94,20),380),((66,44),85),((67,20),250),((67,44),85),((68,20),250)):
        if (fault=='anode-licon' and pair==(66,44)) or (fault=='anode-mcon' and pair==(67,44)):continue
        rect(pair,cx-half,cy-half,cx+half,cy+half)
    for pair in ((65,44),(67,20),(68,20)):ring(pair,1250,750)
    ring((93,44),1380,620)
    for pair in ((65,44),(67,20),(68,20)):ring(pair,2800,2000)
    ring((94,20),2930,1870)
    for domain,offset in (('cathode',1000),('substrate',2400)):
        points=set()
        # Keep the final cut at least 400 nm from its corner neighbor even
        # when the junction dimensions are not multiples of the contact pitch.
        for x in [-offset,*range(-offset+400,w+offset-399,400),w+offset]:points.update(((x,-offset),(x,l+offset)))
        for y in [-offset,*range(-offset+400,l+offset-399,400),l+offset]:points.update(((-offset,y),(w+offset,y)))
        for x,y in sorted(points):
            for pair,kind in (((66,44),'licon'),((67,44),'mcon')):
                if fault!=domain+'-'+kind:rect(pair,x-85,y-85,x+85,y+85)
    if fault in ('anode-cathode-short','substrate-cathode-short'):
        points=[k.Point(-1000,-1000),k.Point(cx,-1000),k.Point(cx,cy)] if fault.startswith('anode') else [k.Point(-2400,-2400),k.Point(-1000,-2400),k.Point(-1000,-1000)]
        c.shapes(ly.layer(68,20)).insert(k.Path(points,340))
    if fault in ('cathode-ring-open','substrate-ring-open','cathode-metal-split','substrate-metal-split'):
        # Two cuts remove both alternate paths; do not touch the other ring.
        offset=1000 if fault.startswith('cathode') else 2400
        cut=k.Region(k.Box(-offset-500,cy-100,-offset+500,cy+100))|k.Region(k.Box(w+offset-500,cy-100,w+offset+500,cy+100))
        for pair in (((65,44),) if 'ring-open' in fault else ((67,20),(68,20))):
            shapes=c.shapes(ly.layer(*pair));region=k.Region(shapes)-cut;shapes.clear();shapes.insert(region)
    if fault=='dnwell-gap':
        shapes=c.shapes(ly.layer(64,18));region=k.Region(shapes)-k.Region(k.Box(cx-50,-2000,cx+50,l+2000));shapes.clear();shapes.insert(region)
    if fault=='extra-device-mask':rect((65,20),500,500,1000,1000)
    if fault=='floating-metal':rect((68,20),w+4000,0,w+4500,500)
    if fault=='uncontacted-tap':
        rect((65,44),cx-150,-600,cx+150,-300);rect((94,20),cx-280,-730,cx+280,-170)
    for name,x,y in [('A',cx,cy),('K',-1000,-1000),('S',-2400,-2400)]:
        c.shapes(ly.layer(68,5)).insert(k.Text(name,k.Trans(x,y)))
    if fault=='duplicate-port':c.shapes(ly.layer(68,5)).insert(k.Text('S',k.Trans(cx,cy)))
    if angle:c.transform(k.Trans(angle//90,False,0,0))
    ly.write(str(path))


def selected(w,l,fault=None):
    # Independent analytic dimensions, not values read from the generated GDS.
    geometries=[(w*l,2*(w+l)),((w+2.2)*(l+2.2),2*(w+l+4.4)),
                ((w+3)*(l+3)-(w+2.2)*(l+2.2),2*(w+l+6)+2*(w+l+4.4))]
    rows=[]
    for i,(model,(area,perimeter)) in enumerate(zip(MODELS,geometries)):
        tag=('rf','dnw','skirt')[i]
        if fault=='reference-'+tag+'-area':area*=1.1
        if fault=='reference-'+tag+'-perimeter':perimeter*=1.1
        pins='A K' if i==0 else 'S K'
        if fault=='reference-polarity' and i==0:pins='S K'
        if fault=='reference-electrical-model' and i==0:model='sky130_fd_pr__model__parasitic__rf_diode_pw2dn'
        if fault=='reference-missing-isolation' and i==2:continue
        rows.append(f'D{i+1} {pins} {model} area={area:.17g} perim={perimeter:.17g}')
    return reference('* Geometry-only reference, NOT simulation models.\n.subckt rf_isolation A K S\n'+'\n'.join(rows)+'\n.ends rf_isolation\n','rf_isolation')


def project(path,tech):
    p,_=read_layout(path);link_technology(p,tech);p['cells'][0]['ports']=['A','K','S'];return p


def write(path,data):path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--sky130',type=Path,required=True)
    ap.add_argument('--klayout',type=Path,required=True);ap.add_argument('--pilot',action='store_true')
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tech,identity=technology('sky130A',a.sky130)
    files=[Path(__file__),ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    hashes={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    report=dict(schema=1,status='RUNNING',qualified=False,simulation_models=False,pdk=identity,source_sha256=hashes,layouts=[],faults=[])
    tools=dict(klayout=str(a.klayout.resolve()))
    try:
        for w,l in SIZES[:1] if a.pilot else SIZES:
            for angle in (0,90,180,270):
                name=f'w{w}-l{l}-r{angle}';folder=out/name;folder.mkdir()
                gds=folder/'input.gds';stream(gds,w,l,angle);p=project(gds,tech)
                save_project(p,folder/'project.icproj');p=load_project(folder/'project.icproj')
                exchange={}
                for suffix in ('gds','oas'):
                    target=folder/('roundtrip.'+suffix);export_layout(p,target)
                    # OASIS text does not carry GDS text presentation. Keep the
                    # exact label strings/anchors and explicitly record this.
                    exchange[suffix]=compare(gds,target,text_presentation=suffix=='gds')
                p=project(folder/'roundtrip.oas',tech)
                result=run(p,p['top'],folder/'verification',tools,selected(w,l),lvs_extractor='sky130-rf-isolation-klayout')
                if result['status']!='passed':raise ValueError(name+': '+result.get('error','No pass.'))
                native=circuit((folder/'verification/lvs-extraction/native.cir').read_text(),'rf_isolation',native=True)
                report['layouts'].append(dict(name=name,width_um=w,length_um=l,angle=angle,exchange=exchange,native=native,report_sha256=file_digest(folder/'verification/report.json')))
                write(out/'record.json',report);print(name,'PASS',flush=True)
            for fault in (*PHYSICAL_FAULTS,*REFERENCE_FAULTS):
                name=f'w{w}-l{l}-{fault}';folder=out/name;folder.mkdir()
                gds=folder/'input.gds';stream(gds,w,l,fault=fault);p=project(gds,tech)
                result=run(p,p['top'],folder/'verification',tools,selected(w,l,fault),lvs_extractor='sky130-rf-isolation-klayout')
                stages={s['name']:s['status'] for s in result['stages']};proof=folder/'verification/lvs-extraction/contacts.json'
                if fault=='nwell-hole-spacing':
                    ok=(stages['drc']=='failed' and stages['lvs_extraction']=='passed'
                        and result.get('klayout_drc',{}).get('rules',{}).get('MR_nwell.SP.1',0)>0)
                elif fault in ('reference-polarity','reference-missing-isolation','reference-electrical-model'):
                    ok=stages['preflight']=='failed' and 'RF isolation' in result.get('error','')
                elif fault.startswith('reference-'):
                    ok=stages['lvs_extraction']=='passed' and stages['lvs']=='failed' and 'RF isolation strict comparison' in result.get('error','')
                else:ok=stages['preflight']=='passed' and proof.is_file() and not json.loads(proof.read_text())['passed']
                if not ok:raise ValueError(name+': fault missed its required stage: '+result.get('error',''))
                report['faults'].append(dict(name=name,detected=True,error=result.get('error'),report_sha256=file_digest(folder/'verification/report.json')))
                write(out/'record.json',report);print(name,'DETECTED',flush=True)
        if any(file_digest(ROOT/p)!=sha for p,sha in hashes.items()):raise ValueError('Source changed during qualification.')
        report['status']='PASS'
    except Exception as exc:report.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
    write(out/'record.json',report);print(json.dumps({k:report.get(k) for k in ('status','error')}),flush=True)
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
