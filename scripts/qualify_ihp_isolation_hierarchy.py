"""Check repeated isolated-transistor cells without merging their internal bodies.

Two instances reuse one hierarchical cell. The second is rotated and reflected;
the whole circuit is checked in four orientations. Both share the physical
substrate but retain separate NWell, source, gate, drain and internal tap/body
connections. This is selected physical connectivity, not full qualification.
"""
import argparse
import math
from pathlib import Path
import re
import sys
import traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.catalog import link_technology
from icstudio.interchange import export_layout
from icstudio.layout_import import read_layout
from icstudio.layout_verification import reference,run
from icstudio.model import file_digest,load_project,save_project,scalar
from icstudio.stream_contract import compare
from scripts.qualify_ihp_isolation_context import stream as single_stream
from scripts.qualify_standard_mos import load_technology,write

PORTS=('D1','G1','S1','NW1','D2','G2','S2','NW2','B')
FAULTS=('merged-body','crossed-tap','crossed-well','crossed-gate','second-tap-area','second-isolation-area')


def stream(path,rotation=0):
    import klayout.db as k
    if rotation not in (0,90,180,270):raise ValueError('Unreviewed circuit orientation.')
    path=Path(path);source=path.with_name(path.stem+'-single.gds');proof=single_stream(source)
    ly=k.Layout();ly.read(str(source));child=ly.top_cell();top=ly.create_cell('pair')
    labels=[s.text for s in child.shapes(ly.layer(8,2)).each() if s.is_text()]
    if {t.string for t in labels}!={'D','G','S','NW','B'}:raise ValueError('Changed child conductor labels.')
    for i,trans in ((1,k.Trans()),(2,k.Trans(1,True,40000,0))):
        top.insert(k.CellInstArray(child.cell_index(),trans))
        for text in labels:
            placed=text.transformed(trans);placed.string=text.string+str(i) if text.string!='B' else 'B'
            top.shapes(ly.layer(8,2)).insert(placed)
    top.transform(k.Trans(rotation//90,False,0,0));ly.write(str(path))
    return dict(single=proof,rotation=rotation,instances=2,reuses_same_child=True,
                second_transform='R90 reflected about x, translated (40000,0) nm',
                substrate='Shared physical bulk; each contacted region is named B.')


def selected(fault=None):
    if fault not in (None,*FAULTS):raise ValueError('Unknown hierarchy fault.')
    lines=['.subckt pair '+' '.join(PORTS)]
    for i in (1,2):
        body='IS1' if fault=='merged-body' else 'IS'+str(i)
        tap='IS1' if i==2 and fault=='crossed-tap' else body
        well='NW1' if i==2 and fault=='crossed-well' else 'NW'+str(i)
        gate='G1' if i==2 and fault=='crossed-gate' else 'G'+str(i)
        area='7e-13' if i==2 and fault=='second-tap-area' else '6.084e-13'
        length='7u' if i==2 and fault=='second-isolation-area' else '6u'
        lines.extend([f'M{i} D{i} {gate} S{i} {body} sg13_lv_nmos w=.15u l=.13u ng=1 m=1',
                      f'R{i} S{i} {tap} ptap1 A={area} P=3.12e-6',
                      f'D{i} {body} {well} B isolbox w=6u l={length}'])
    return reference('\n'.join([*lines,'.ends pair','']),'pair')


def audit(path):
    text=re.sub(r'\n[ \t]*\+[ \t]*',' ',Path(path).read_text())
    rows=[line.split() for line in text.splitlines() if line and not line.startswith(('*','.'))]
    if len(rows)!=6:raise ValueError('Both complete MOS/tap/isolation circuits must survive extraction.')
    devices=[]
    for row in rows:
        j=next(i for i,t in enumerate(row) if '=' in t)-1
        pairs=[t.lower().split('=',1) for t in row[j+1:]];params={n:scalar(v) for n,v in pairs}
        if len(params)!=len(pairs):raise ValueError('Duplicate native geometry parameter.')
        devices.append(dict(model=row[j],nets=row[1:j],params=params))
    expected={'isolbox':dict(a=36e-12,p=24e-6),'ptap1':dict(a=.6084e-12,p=3.12e-6),
        'sg13_lv_nmos':{'l':.13e-6,'w':.15e-6,'as':.1005e-12,'ad':.1005e-12,'ps':1.34e-6,'pd':1.34e-6,'rfmode':0}}
    if any(sum(d['model']==m for d in devices)!=2 for m in expected):raise ValueError('Changed native device inventory.')
    for d in devices:
        values=expected[d['model']]
        if set(d['params'])!=set(values) or any(not math.isclose(d['params'][n],v,rel_tol=1e-10,abs_tol=0) for n,v in values.items()):
            raise ValueError('Changed native hierarchy geometry.')
    bodies=[]
    for i in (1,2):
        iso=[d for d in devices if d['model']=='isolbox' and d['nets'][1:]==['NW'+str(i),'B']]
        if len(iso)!=1 or len(iso[0]['nets'])!=3:raise ValueError('NWell/bulk roles or isolation count changed.')
        body=iso[0]['nets'][0];bodies.append(body)
        if body in PORTS:raise ValueError('Internal body collapsed into a public terminal.')
        tap=[d for d in devices if d['model']=='ptap1' and d['nets']==['S'+str(i),body]]
        mos=[d for d in devices if d['model']=='sg13_lv_nmos' and len(d['nets'])==4 and
             d['nets'][1]=='G'+str(i) and d['nets'][3]==body and {d['nets'][0],d['nets'][2]}=={'D'+str(i),'S'+str(i)}]
        if len(tap)!=1 or len(mos)!=1:raise ValueError('Crossed instance terminals or lost internal tap.')
    if len(set(bodies))!=2:raise ValueError('Repeated child instances merged their isolated bodies.')
    return dict(sha256=file_digest(path),device_count=6,independent_bodies=bodies,devices=devices)


def case(tech,rotation,out,tools):
    folder=out/f'r{rotation}';folder.mkdir();row=dict(rotation=rotation,status='RUNNING',faults=[])
    try:
        row['geometry']=stream(folder/'input.gds',rotation);p,_=read_layout(folder/'input.gds');link_technology(p,tech)
        next(c for c in p['cells'] if c['id']==p['top'])['ports']=list(PORTS)
        save_project(p,folder/'saved.icproj');p=load_project(folder/'saved.icproj')
        export_layout(p,folder/'export.gds');export_layout(p,folder/'export.oas')
        q,_=read_layout(folder/'export.oas');link_technology(q,tech);next(c for c in q['cells'] if c['id']==q['top'])['ports']=list(PORTS)
        export_layout(q,folder/'reimported.gds')
        row['exchange']=dict(gds=compare(folder/'input.gds',folder/'export.gds'),oasis=compare(folder/'export.oas',folder/'reimported.gds',text_presentation=False))
        dest=folder/'physical';r=run(q,q['top'],dest,tools,selected(),lvs_extractor='ihp-klayout',drc_engine='ihp-public')
        if r['status']!='passed':raise ValueError(r.get('error','Hierarchical isolation check failed.'))
        row.update(native=audit(dest/'lvs-extraction/native.cir'),report_sha256=file_digest(dest/'report.json'))
        if rotation==0:
            for fault in FAULTS:
                dest=folder/fault;r=run(q,q['top'],dest,tools,selected(fault),lvs_extractor='ihp-klayout',drc_engine='ihp-public')
                states={s['name']:s['status'] for s in r['stages']};log=dest/'lvs/lvs.log'
                ok=(r['status']=='failed' and all(states[n]=='passed' for n in ('preflight','layout_export','drc','lvs_extraction','integrity')) and
                    states['lvs']=='failed' and log.is_file() and bool(re.search('netlists do not match|circuits do not match|property errors|disconnected node|no matching pin|failed pin matching',log.read_text(),re.I)))
                row['faults'].append(dict(fault=fault,detected=ok,report_sha256=file_digest(dest/'report.json')))
                if not ok:raise ValueError('Cross-instance control missed or failed at the wrong stage: '+fault)
        row['status']='PASS'
    except Exception as e:row.update(status='FAIL',error=repr(e),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    for name in ('magic','netgen','klayout'):ap.add_argument('--'+name,required=True)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=[Path(__file__),ROOT/'scripts/qualify_ihp_isolation_context.py',ROOT/'scripts/qualify_ihp_isolation_layouts.py',ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in source};write(out/'source-files.json',before)
    (out/'executed-runner.py').write_bytes(Path(__file__).read_bytes());tech,identity=load_technology('ihp-sg13g2')
    tools={n:str(Path(getattr(a,n)).resolve(strict=True)) for n in ('magic','netgen','klayout')}
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,process=identity,cases=[])
    for angle in (0,90,180,270):
        row=case(tech,angle,out,tools);report['cases'].append(row);write(out/'qualification.json',report);print(angle,row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=all(file_digest(ROOT/n)==value for n,value in before.items())
    report['status']='PASS' if report['implementation_unchanged'] and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
