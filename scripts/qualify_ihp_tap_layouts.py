"""Selected public IHP tap geometry through application export, full DRC and strict LVS.

Two tap types, five rectangles and two rotations. A real separate substrate
contact supplies the ptap body terminal. This checks physical interfaces at
these points, not continuous ranges, antenna/density or foundry signoff.
"""
import argparse,json,math,re,sys,traceback
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,file_digest,load_project,save_project,scalar
from icstudio.catalog import create_device,link_technology
from icstudio.catalog_migration import emit
from icstudio.layout import kdb,polygon
from icstudio.layout_import import read_layout
from icstudio.layout_verification import reference,run
from icstudio.interchange import export_layout
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import load_technology,write

SIZES=((780,780),(780,5000),(5000,780),(2000,2000),(10000,10000))
MODELS=('ntap1','ptap1')


def geometry(tech,model,w,l,rotation,folder):
    if model not in MODELS or (w,l) not in SIZES or rotation not in (0,90):raise ValueError('Unreviewed tap fixture.')
    db=kdb();ly=db.Layout();ly.dbu=.001;c=ly.create_cell('coupon');well='well' if model=='ntap1' else 'sub!'
    def box(layer,x1,y1,x2,y2):c.shapes(ly.layer(layer,0)).insert(db.Box(x1,y1,x2,y2))
    def text(layer,dt,name,x,y):c.shapes(ly.layer(layer,dt)).insert(db.Text(name,db.Trans(x,y)))
    def contact(x0,y0,width,length):
        box(1,x0,y0,x0+width,y0+length);box(8,x0,y0,x0+width,y0+length)
        if model=='ptap1':box(14,x0-180,y0-180,x0+width+180,y0+length+180)
        nx=1+(width-300)//360;ny=1+(length-300)//360
        dx=(width-(160+(nx-1)*360))//2;dy=(length-(160+(ny-1)*360))//2
        for i in range(nx):
            for j in range(ny):box(6,x0+dx+i*360,y0+dy+j*360,x0+dx+i*360+160,y0+dy+j*360+160)
    contact(0,0,w,l);text(8,2,'TIE',w//2,l//2)
    if model=='ntap1':box(31,-500,-500,w+500,l+500);text(31,2,well,w+250,l//2)
    else:
        box(40,-500,-500,w+500,l+500);contact(w+2000,0,2000,2000);text(8,2,well,w+3000,1000)
    text(63,0,well,w+250,l//2)
    if rotation:c.transform(db.Trans(db.Trans.R90))
    ly.write(str(folder/'source.gds'));p,_=read_layout(folder/'source.gds');link_technology(p,tech)
    p['cells'][0]['ports']=['TIE',well];save_project(p,folder/'saved.icproj');p=load_project(folder/'saved.icproj')
    export_layout(p,folder/'export.gds');export_layout(p,folder/'export.oas')
    external=db.Layout();external.read(str(folder/'export.oas'));external.write(str(folder/'external.oas'))
    q,_=read_layout(folder/'external.oas');link_technology(q,tech);q['cells'][0]['ports']=['TIE',well]
    export_layout(q,folder/'reimported.gds')
    exchange=dict(gds=compare(folder/'source.gds',folder/'export.gds'),
                  reopened=compare(folder/'export.gds',folder/'reimported.gds'),
                  oasis=compare(folder/'external.oas',folder/'reimported.gds',text_presentation=False))
    return q,well,exchange


def selected_reference(tech,model,w,l,well,fault=None):
    d=create_device(tech,'sg13g2_pr/'+model+'.sym','TAP');d['nets']={'p':'TIE','m':well}
    d['model_params'].update(w=w*1e-9,l=l*1e-9);line=emit(d,tech)
    if fault in ('public-format','area','perimeter'):
        a=w*l*1e-18*(1.2 if fault=='area' else 1);p=2*(w+l)*1e-9*(1.2 if fault=='perimeter' else 1)
        line=f'R1 TIE {well} {model} A={a:.15g} P={p:.15g}'
    elif fault=='terminal-swap':
        tokens=line.split();tokens[1],tokens[2]=tokens[2],tokens[1];line=' '.join(tokens)
    elif fault=='model':line=line.replace(' '+model+' ',' '+MODELS[1-MODELS.index(model)]+' ')
    elif fault is not None:raise ValueError('Unknown tap reference control.')
    return reference(f'.subckt coupon TIE {well}\n{line}\n.ends coupon\n','coupon')


def alter(p,w,l,rotation,fault):
    db=kdb();q=clone(p);c=q['cells'][0];layer=next(v['name'] for v in q['pdk']['layers'] if (v['gds'],v['datatype'])==(6,0))
    region=db.Region(db.Box(0,0,w,l));region.transform(db.Trans(db.Trans.R90) if rotation else db.Trans())
    selected=[s for s in c['shapes'] if s['layer']==layer and not (db.Region(polygon(s))&region).is_empty()]
    if not selected:raise ValueError('No primary contacts selected for fault.')
    if fault=='contact-open':c['shapes']=[s for s in c['shapes'] if s not in selected]
    elif fault=='contact-size':
        s=selected[0];xs,ys=zip(*s['points']);cx=(max(xs)+min(xs))//2;cy=(max(ys)+min(ys))//2
        s['points']=[[cx+(x-cx)//2,cy+(y-cy)//2] for x,y in s['points']]
    else:raise ValueError('Unknown tap physical control.')
    return q


def audit_native(path,model,w,l,well,prefix):
    rows=[line.split() for line in path.read_text().splitlines() if line and not line.startswith(('*','.'))]
    if len(rows)!=1:raise ValueError('Expected exactly one native tap.')
    row=rows[0]
    if not row[0].startswith(prefix) or row[1:4]!=['TIE',well,model]:raise ValueError('Native tap model or terminal roles changed.')
    params=dict(token.split('=',1) for token in row[4:])
    if {k.lower() for k in params}!={'a','p'}:raise ValueError('Unreviewed native tap parameters.')
    actual={k.lower():scalar(v) for k,v in params.items()}
    for key,value in [('a',w*l*1e-18),('p',2*(w+l)*1e-9)]:
        if not math.isclose(actual[key],value,rel_tol=1e-10,abs_tol=0):raise ValueError('Native tap geometry differs: '+key)
    return dict(sha256=file_digest(path),terminals=row[1:3],model=row[3],area_m2=actual['a'],perimeter_m=actual['p'])


def detected(result,dest,kind):
    stages={s['name']:s for s in result['stages']}
    if result['status']!='failed' or any(stages[n]['status']!='passed' for n in ('preflight','layout_export')):return False
    if kind=='contact-size':return stages['drc']['status']=='failed' and result.get('drc_count',0)>0
    if stages['lvs']['status']=='failed' and (dest/'lvs/lvs.log').is_file():
        return bool(re.search(r'netlists do not match|circuits do not match|property errors|disconnected node|no matching pin|failed pin matching',(dest/'lvs/lvs.log').read_text(),re.I))
    if kind=='contact-open' and stages['lvs_extraction']['status']=='failed' and (dest/'lvs-extraction/native.cir').is_file():
        return bool(re.search(r'port names differ|no circuit devices|terminal|interface',stages['lvs_extraction'].get('error',''),re.I))
    return False


def case(tech,model,w,l,rotation,out,tools):
    name=f'{model}-{w}-{l}-{rotation}';folder=out/name;folder.mkdir();row=dict(name=name,model=model,width_nm=w,length_nm=l,rotation=rotation,status='RUNNING',faults=[])
    try:
        p,well,exchange=geometry(tech,model,w,l,rotation,folder);ref=selected_reference(tech,model,w,l,well)
        dest=folder/'physical';r=run(p,p['top'],dest,tools,ref,lvs_extractor='ihp-klayout')
        if r['status']!='passed':raise ValueError(r.get('error','Tap physical check failed.'))
        row.update(exchange=exchange,report_sha256=file_digest(dest/'report.json'),drc_count=r['drc_count'],
            native=audit_native(dest/'lvs-extraction/native.cir',model,w,l,well,'R'),
            comparison=audit_native(dest/'lvs-extraction/extracted.spice',model,w,l,well,'X'))
        faults=['contact-open','contact-size']
        if (w,l,rotation)==(2000,2000,0):
            extra=folder/'public-format';r=run(p,p['top'],extra,tools,selected_reference(tech,model,w,l,well,'public-format'),lvs_extractor='ihp-klayout')
            if r['status']!='passed':raise ValueError('Public A/P reference rejected: '+str(r.get('error')))
            row['public_reference']=dict(status='PASS',report_sha256=file_digest(extra/'report.json'))
            faults+=['terminal-swap','area','perimeter','model']
        for fault in faults:
            q=alter(p,w,l,rotation,fault) if fault.startswith('contact-') else p
            selected=ref if fault.startswith('contact-') else selected_reference(tech,model,w,l,well,fault)
            dest=folder/fault;r=run(q,q['top'],dest,tools,selected,lvs_extractor='ihp-klayout');ok=detected(r,dest,fault)
            row['faults'].append(dict(name=fault,detected=ok,status=r['status'],error=r.get('error'),report_sha256=file_digest(dest/'report.json')))
            if not ok:raise ValueError('Tap fault was not detected by its native gate: '+fault)
        row['status']='PASS'
    except Exception as error:row.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    for name in ('magic','netgen','klayout'):ap.add_argument('--'+name,required=True)
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,5),default=2);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sources=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources};write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    tech,identity=load_technology('ihp-sg13g2');tools={n:str(Path(getattr(a,n)).resolve(strict=True)) for n in ('magic','netgen','klayout')}
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,process=identity,source_files_sha256=file_digest(out/'source-files.json'),cases=[])
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(case,tech,model,w,l,rotation,out,tools) for model in MODELS for w,l in (((2000,2000),) if a.pilot else SIZES) for rotation in (0,90)]
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in sources}
    report['status']='PASS' if report['implementation_unchanged'] and len(report['cases'])==len(jobs) and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r:r['name']);write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
