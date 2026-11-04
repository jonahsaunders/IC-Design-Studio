"""Selected public-rule GF180 C/D 10 V rectangles and physical fault controls.

This is an original explicit-mask coupon, not the pinned Magic generator (which
loses HV masks on GDS reimport). It exercises both polarities, independent body
nets, full public DRC, strict LVS and exact GDS/OASIS application roundtrips.
"""
import argparse,json,math,re,sys,traceback
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,file_digest,save_project,load_project,scalar
from icstudio.layout_import import read_layout
from icstudio.catalog import link_technology
from icstudio.interchange import export_layout
from icstudio.layout_verification import reference,run
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import load_technology,write
from scripts.qualify_gf180_resistor_layouts import native_layers

SIZES=((4,.6),(4,20),(50,.6),(50,20),(25,.6))
PORTS=['D','G','S','B','SUB','DN','GN','SN']
FAULTS=('p-source-contact','n-source-contact','p-body-contact','n-body-contact',
        'outer-body-contact','substrate-route','p-gate-source-short','n-gate-source-short',
        'p-recognition-mask','n-recognition-mask','hv-marker','reference-width',
        'reference-length','reference-p-drain-source','reference-n-drain-source')


def stream(path,w_um,l_um,angle=0,fault=None):
    import klayout.db as db
    w,l=round(w_um*1000),round(l_um*1000)
    ly=db.Layout();ly.dbu=.001;c=ly.create_cell('coupon')
    def draw(p,ox,names):
        delta=-10 if fault==('p-field-gap-small' if p else 'n-field-gap-small') else 10 if fault==('p-field-gap-large' if p else 'n-field-gap-large') else 0
        def box(layer,x1,y1,x2,y2):c.shapes(ly.layer(*layer)).insert(db.Box(x1+ox,y1,x2+ox,y2))
        def ring(layer,x1,y1,x2,y2,thick):
            r=db.Region(db.Box(x1+ox,y1,x2+ox,y2))-db.Region(db.Box(x1+ox+thick,y1+thick,x2+ox-thick,y2-thick))
            for poly in r.each():c.shapes(ly.layer(*layer)).insert(poly)
        def contact(x,y,pin):
            label=('p-' if p else 'n-')+{'S':'source-contact','B':'body-contact'}.get(pin,'other')
            if pin=='SUB':label='outer-body-contact'
            if fault!=label:box((33,0),x-110,y-110,x+110,y+110)
            box((34,0),x-220,y-220,x+220,y+220)
            c.shapes(ly.layer(34,10)).insert(db.Text(names[pin],db.Trans(x+ox,y)))
        box((22,0),-800,0,l+400,w);box((22,0),l+760+delta,0,l+1760+delta,w)
        box((30,0),0,-800,l+600,w+800)
        if fault!=('p-recognition-mask' if p else 'n-recognition-mask'):
            box((11,39) if p else (210,0),l,-800,l+2560,w+800)
        box((31,0) if p else (32,0),-1100,-300,l+630,w+300)
        box((31,0) if p else (32,0),l+530+delta,-300,l+1990+delta,w+300)
        ring((22,0),-2800,-2800,l+4600,w+2800,600)
        ring((32,0) if p else (31,0),-3100,-3100,l+4900,w+3100,1200)
        ring((34,0),-2910,-2910,l+4710,w+2910,820)
        if p:
            box((12,0),-3500,-3500,l+5300,w+3500)
            ring((22,0),-6600,-6600,l+8400,w+6600,600)
            ring((31,0),-6900,-6900,l+8700,w+6900,1200)
            ring((34,0),-6710,-6710,l+8510,w+6710,820)
            contact(-6300,w//2,'SUB')
        margin=7200 if p else 3400;right=9000 if p else 5200
        box((55,0),-margin,-margin,l+right,w+margin)
        if fault!='hv-marker':box((226,0),-margin,-margin,l+right,w+margin)
        contact(-500,w//2,'S');contact(l+1260,w//2,'D');contact(600,-550,'G');contact(-2500,w//2,'B')
        if fault==('p-gate-source-short' if p else 'n-gate-source-short'):
            c.shapes(ly.layer(34,0)).insert(db.Path([db.Point(-500+ox,w//2),db.Point(-500+ox,-550),db.Point(600+ox,-550)],440))
    draw(True,0,{k:k for k in ('D','G','S','B','SUB')})
    draw(False,60000,dict(D='DN',G='GN',S='SN',B='SUB'))
    c.shapes(ly.layer(34,0)).insert(db.Path([db.Point(-6300,w//2),db.Point(-8000,w//2),db.Point(-8000,-8500),db.Point(57500,-8500),db.Point(57500,-2500)],500))
    if fault=='substrate-route':
        shapes=c.shapes(ly.layer(34,0));r=db.Region(shapes)-db.Region(db.Box(20000,-9000,21000,-8000));shapes.clear();shapes.insert(r)
    if angle:c.transform(db.Trans(angle//90,False,0,0))
    ly.write(str(path))


def selected(w,l,fault=None):
    wp=w*1.1 if fault=='reference-width' else w;lp=l*1.1 if fault=='reference-length' else l
    p='S G D B' if fault=='reference-p-drain-source' else 'D G S B'
    n='SN GN DN SUB' if fault=='reference-n-drain-source' else 'DN GN SN SUB'
    return reference(f'.subckt coupon {" ".join(PORTS)}\nXP {p} pfet_10v0_asym w={wp:g}u l={lp:g}u\nXN {n} nfet_10v0_asym w={w:g}u l={l:g}u\n.ends coupon\n','coupon')


def project(path,tech):
    p,_=read_layout(path);link_technology(p,tech);p['cells'][0]['ports']=list(PORTS)
    return p


def audit_extracted(path,w,l,native=False):
    rows=[s.split() for s in re.sub(r'\n\s*\+\s*',' ',path.read_text()).splitlines() if s.strip() and not s.lstrip().startswith(('*','.'))]
    expected={('pmos_10p0_asym' if native else 'pfet_10v0_asym'):['D','G','S','B'],
              ('nmos_10p0_asym' if native else 'nfet_10v0_asym'):['DN','GN','SN','SUB']}
    if len(rows)!=2 or {r[5] for r in rows}!=set(expected):raise ValueError('Unexpected extracted models/count.')
    for row in rows:
        if row[1:5]!=expected[row[5]]:raise ValueError('Extracted high-voltage terminal roles changed.')
        values=dict(s.split('=',1) for s in row[6:])
        for key,value in [('W',w),('L',l)]:
            if not math.isclose(scalar(values[key])*1e6,value,rel_tol=1e-10,abs_tol=1e-9):raise ValueError('Wrong extracted '+key)
        if not all(math.isfinite(scalar(v)) and scalar(v)>0 for v in values.values()):raise ValueError('Invalid extracted geometry.')
    return dict(models=expected,width_um=w,length_um=l,sha256=file_digest(path))


def detected(result,folder,fault):
    if result['status']!='failed':return False
    stages={s['name']:s for s in result['stages']}
    if any(stages[n]['status']!='passed' for n in ('preflight','layout_export')):return False
    if fault.startswith('reference-'):
        log=folder/'lvs/lvs.log'
        return (stages['lvs_extraction']['status']=='passed' and stages['lvs']['status']=='failed'
                and log.is_file() and bool(re.search(r'netlists do not match|circuits do not match|property errors|disconnected node|no matching pin|pin lists[^\n]*altered|failed pin matching',log.read_text(),re.I)))
    if result.get('drc_count',0)>0:return True
    guard=folder/'lvs-extraction/guard-connections.json'
    if guard.is_file() and json.loads(guard.read_text())['passed'] is False:return True
    error=stages['lvs_extraction'].get('error','')
    return stages['lvs_extraction']['status']=='failed' and bool(re.search(r'Unreviewed device|port names differ|recognition mask',error))


def case(target,w,l,out,tools,pilot):
    folder=out/f'{target}-w{w:g}-l{l:g}';folder.mkdir();row=dict(target=target,width_um=w,length_um=l,status='RUNNING',layouts=[],faults=[])
    try:
        tech,identity=load_technology(target);native_layers(tech);row['package']=identity
        for angle in ((0,) if pilot else (0,90,180,270)):
            gds=folder/f'input-{angle}.gds';stream(gds,w,l,angle);p=project(gds,tech)
            save_project(p,folder/f'input-{angle}.icproj');p=load_project(folder/f'input-{angle}.icproj')
            oasis=folder/f'roundtrip-{angle}.oas';export_layout(p,oasis);p=project(oasis,tech)
            returned=folder/f'roundtrip-{angle}.gds';export_layout(p,returned)
            exchange=compare(gds,returned,text_presentation=False)
            dest=folder/f'physical-{angle}';r=run(p,p['top'],dest,tools,selected(w,l),lvs_extractor='gf180-hv-klayout')
            if r['status']!='passed':raise ValueError(r.get('error','Verification did not pass.'))
            row['layouts'].append(dict(angle=angle,exchange=exchange,report_sha256=file_digest(dest/'report.json'),
                native=audit_extracted(dest/'lvs-extraction/native.cir',w,l,True),converted=audit_extracted(dest/'lvs-extraction/extracted.spice',w,l)))
        for fault in FAULTS:
            gds=folder/(fault+'.gds');stream(gds,w,l,fault=fault);p=project(gds,tech);dest=folder/fault
            r=run(p,p['top'],dest,tools,selected(w,l,fault),lvs_extractor='gf180-hv-klayout');ok=detected(r,dest,fault)
            row['faults'].append(dict(fault=fault,detected=ok,status=r['status'],error=r.get('error'),report_sha256=file_digest(dest/'report.json')))
            if not ok:raise ValueError('Fault was not detected by the required native check: '+fault)
        if (w,l)==SIZES[0]:
            for angle in (0,90,180,270):
                for fault in ('n-field-gap-small','n-field-gap-large','p-field-gap-small','p-field-gap-large'):
                    name=f'{fault}-{angle}';gds=folder/(name+'.gds');stream(gds,w,l,angle,fault)
                    p=project(gds,tech);dest=folder/name
                    r=run(p,p['top'],dest,tools,selected(w,l),lvs_extractor='gf180-hv-klayout')
                    expected='MDN.10d' if fault.startswith('n-') else 'MDP.9d'
                    ok=r['status']=='failed' and r.get('klayout_drc',{}).get('rules',{}).get("'"+expected+"'",0)>0
                    row['faults'].append(dict(fault=name,detected=ok,status=r['status'],expected_rule=expected,report_sha256=file_digest(dest/'report.json')))
                    if not ok:raise ValueError('Native field-gap rule did not detect '+name)
        row['status']='PASS'
    except Exception as exc:row.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--klayout',required=True);ap.add_argument('--netgen',required=True)
    ap.add_argument('--targets',nargs='+',choices=('gf180mcuC','gf180mcuD'),default=['gf180mcuC','gf180mcuD'])
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=(1,2,3,4),default=2)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    paths=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/qualify_gf180_resistor_layouts.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in paths};write(out/'source-files.json',before)
    tools={k:str(Path(getattr(a,k)).resolve(strict=True)) for k in ('klayout','netgen')}
    report=dict(schema=1,status='RUNNING',chunk=7,chunk_complete=False,qualified=False,scope=__doc__,cases=[],source_files_sha256=file_digest(out/'source-files.json'))
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(case,t,w,l,out,tools,a.pilot) for t in a.targets for w,l in (SIZES[:1] if a.pilot else SIZES)]
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['target'],row['width_um'],row['length_um'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in paths}
    report['status']='PASS' if report['implementation_unchanged'] and all(c['status']=='PASS' for c in report['cases']) else 'FAIL'
    write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
