"""The pinned IHP transistor/tap/isolation circuit through full DRC and strict LVS.

The public masks are preserved except for an explicitly recorded gate-contact
landing, an inward tap translation and added well/bulk contacts. Device channel,
tap dimensions and isolation well geometry are unchanged. This is not electrical
operating-envelope or fabrication qualification.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
import math
from pathlib import Path
import re
import sys
import traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest,scalar,save_project,load_project
from icstudio.catalog import link_technology
from icstudio.layout_import import read_layout
from icstudio.interchange import export_layout
from icstudio.layout_verification import reference,run
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import load_technology,write
from scripts.qualify_ihp_isolation_layouts import sources,SOURCES

FAULTS=('missing-tap-recognition','missing-isolation-recognition','tap-open','gate-open',
        'well-open','bulk-open','reference-tap-area','reference-isolation-area','reference-body','reference-gate')


def stream(path,rotation=0,mirror=False,fault=None):
    import klayout.db as k
    sources()
    if rotation not in (0,90,180,270) or fault not in (None,*FAULTS):raise ValueError('Unreviewed mixed isolation control.')
    old=k.Layout();old.read(str(SOURCES/'isolbox.gds'));ly=k.Layout();ly.dbu=.001;c=ly.create_cell('inmos');c.copy_tree(old.top_cell())
    def box(layer,x1,y1,x2,y2):c.shapes(ly.layer(layer,0)).insert(k.Box(x1,y1,x2,y2))
    for name,x,y in [('D',1180,1950),('G',1190,1480),('S',1160,550),('NW',1200,-160),('B',-5000,-5000)]:
        c.shapes(ly.layer(8,2)).insert(k.Text(name,k.Trans(x,y)))
    box(1,-5500,-5500,-4500,-4500);box(14,-5680,-5680,-4320,-4320);box(8,-5500,-5500,-4500,-4500)
    if fault!='bulk-open':
        for x in (-5300,-4900):
            for y in (-5300,-4900):box(6,x,y,x+160,y+160)
    for v in range(-605,4346,450):
        for x,y in ((v+2500,4615),(6845,v+270)):box(6,x,y,x+160,y+160)
    box(8,1690,4410,7210,4980);box(8,6640,-540,7210,4980)
    for instance in c.each_inst():
        if instance.cell.name=='ptap1':instance.trans=k.Trans(4980,1570)
    for layer in (5,6,8):
        for s in list(c.shapes(ly.layer(layer,0)).each()):
            b=s.bbox()
            if (layer in (5,6) and b.left>3600 and b.top<1800) or (layer==8 and ((b.left>3600 and b.top<1800) or (b.left<1300 and 1200<b.bottom<1400))):s.delete()
    box(5,3675,1330,3975,1630);box(5,3760,1630,3890,1720)
    if fault!='gate-open':box(6,3745,1400,3905,1560)
    box(8,3675,1330,3975,1630);box(8,1110,1400,3825,1560)
    if fault in ('missing-tap-recognition','missing-isolation-recognition'):
        wanted='sub!' if fault=='missing-tap-recognition' else 'isolbox'
        for cell in ly.each_cell():
            for s in list(cell.shapes(ly.layer(63,0)).each()):
                if s.is_text() and s.text.string==wanted:s.delete()
    elif fault=='tap-open':ly.cell('ptap1').shapes(ly.layer(6,0)).clear()
    elif fault=='well-open':
        nactive=k.Region(k.Box(1450,-780,7450,5220))-k.Region(k.Box(2500,270,6400,4170))
        for s in list(c.shapes(ly.layer(6,0)).each()):
            if not (k.Region(s.polygon)&nactive).is_empty():s.delete()
    # Keep hierarchy until the application's private verification stream. The
    # original child-local tap annotation must survive without naming a net.
    if rotation or mirror:c.transform(k.Trans(rotation//90,mirror,0,0))
    ly.write(str(path))
    return dict(source_sha256=file_digest(SOURCES/'isolbox.gds'),rotation=rotation,mirror=mirror,
                unchanged='MOS channel 0.15x0.13 um; tap 0.78x0.78 um; outer isolation 6x6 um.',
                changes=['Tap instance moved from (5130,1570) to (4980,1570) nm for nBuLay enclosure.',
                         'Gate landing replaced by 300x300 nm poly/metal, 160x160 nm contact and a lower gate escape; channel unchanged.',
                         'Top/right isolation ring contacts and a separate 1x1 um contacted substrate tie added.'])


def selected(fault=None):
    text='.subckt inmos D G S NW B\nM1 D G S IS sg13_lv_nmos w=0.15u l=0.13u ng=1 m=1\nR1 S IS ptap1 A=6.084e-13 P=3.12e-06\nD1 IS NW B isolbox l=6u w=6u\n.ends inmos\n'
    if fault=='reference-tap-area':text=text.replace('6.084e-13','7e-13')
    elif fault=='reference-isolation-area':text=text.replace('l=6u w=6u','l=7u w=6u')
    elif fault=='reference-body':text=text.replace('M1 D G S IS','M1 D G S B')
    elif fault=='reference-gate':text=text.replace('M1 D G S IS','M1 D S S IS')
    elif fault is not None:raise ValueError('Unknown mixed reference fault.')
    return reference(text,'inmos')


def audit(path):
    lines=re.sub(r'\n[ \t]*\+[ \t]*',' ',Path(path).read_text()).splitlines()
    rows=[line.split() for line in lines if line and not line.startswith(('*','.'))]
    if len(rows)!=3:raise ValueError('The native mixed circuit must retain exactly MOS, tap and isolation devices.')
    by_model={};params={}
    for row in rows:
        j=next(i for i,t in enumerate(row) if '=' in t)-1;name=row[j].lower()
        if name in by_model:raise ValueError('Duplicate mixed device model.')
        by_model[name]=row[1:j];pairs=[t.lower().split('=',1) for t in row[j+1:]];params[name]={key:scalar(value) for key,value in pairs}
        if len(params[name])!=len(pairs):raise ValueError('Duplicate native mixed device parameter.')
    if set(by_model)!={'sg13_lv_nmos','ptap1','isolbox'}:raise ValueError('Changed mixed device set.')
    mos,tap,iso=(by_model[n] for n in ('sg13_lv_nmos','ptap1','isolbox'))
    internal=iso[0]
    if internal in ('D','G','S','NW','B') or iso[1:]!=['NW','B'] or tap!=['S',internal] or len(mos)!=4 or mos[1]!='G' or mos[3]!=internal or {mos[0],mos[2]}!={'D','S'}:
        raise ValueError('Native mixed terminal roles or internal tap connectivity changed.')
    expected={'sg13_lv_nmos':dict(l=.13e-6,w=.15e-6,as_= .1005e-12,ad=.1005e-12,ps=1.34e-6,pd=1.34e-6,rfmode=0),'ptap1':dict(a=.6084e-12,p=3.12e-6),'isolbox':dict(a=36e-12,p=24e-6)}
    expected['sg13_lv_nmos']['as']=expected['sg13_lv_nmos'].pop('as_')
    for model,values in expected.items():
        if set(params[model])!=set(values) or any(not math.isclose(params[model][n],v,rel_tol=1e-10,abs_tol=0) for n,v in values.items()):
            raise ValueError('Native mixed geometry changed: '+model)
    return dict(sha256=file_digest(path),models=by_model,parameters=params)


def case(rotation,mirror,out,tech,tools):
    folder=out/f'r{rotation}-m{int(mirror)}';folder.mkdir();row=dict(rotation=rotation,mirror=mirror,status='RUNNING',faults=[])
    try:
        row['geometry']=stream(folder/'input.gds',rotation,mirror)
        p,_=read_layout(folder/'input.gds');link_technology(p,tech);p['cells'][0]['ports']=['D','G','S','NW','B']
        save_project(p,folder/'saved.icproj');p=load_project(folder/'saved.icproj');export_layout(p,folder/'export.gds');export_layout(p,folder/'export.oas')
        row['exchange']=dict(gds=compare(folder/'input.gds',folder/'export.gds'),oasis=compare(folder/'export.gds',folder/'export.oas',text_presentation=False))
        dest=folder/'physical';r=run(p,p['top'],dest,tools,selected(),lvs_extractor='ihp-klayout',drc_engine='ihp-public')
        if r['status']!='passed':raise ValueError(r.get('error','Mixed isolation verification failed.'))
        row.update(report_sha256=file_digest(dest/'report.json'),native=audit(dest/'lvs-extraction/native.cir'))
        if (rotation,mirror)==(0,False):
            for fault in FAULTS:
                q=p
                if not fault.startswith('reference-'):
                    path=folder/(fault+'.gds');stream(path,rotation,mirror,fault);q,_=read_layout(path);link_technology(q,tech);q['cells'][0]['ports']=['D','G','S','NW','B']
                dest=folder/fault;r=run(q,q['top'],dest,tools,selected(fault) if fault.startswith('reference-') else selected(),lvs_extractor='ihp-klayout',drc_engine='ihp-public')
                stages={s['name']:s for s in r['stages']};native=dest/'lvs-extraction/native.cir'
                specific=(stages['lvs_extraction']['status']=='failed' and native.is_file() and re.search('port names differ|no circuit devices|every marked isolation',stages['lvs_extraction'].get('error','')))
                if stages['lvs']['status']=='failed' and (dest/'lvs/lvs.log').is_file():
                    specific=bool(re.search('netlists do not match|circuits do not match|property errors|disconnected node|no matching pin|failed pin matching',(dest/'lvs/lvs.log').read_text(),re.I))
                ok=r['status']=='failed' and all(stages[n]['status']=='passed' for n in ('preflight','layout_export','drc')) and bool(specific)
                row['faults'].append(dict(fault=fault,detected=ok,report_sha256=file_digest(dest/'report.json'),error=r.get('error')))
                if not ok:raise ValueError('Mixed control did not fail at native connectivity/geometry comparison: '+fault)
        row['status']='PASS'
    except Exception as e:row.update(status='FAIL',error=repr(e),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    for name in ('magic','netgen','klayout'):ap.add_argument('--'+name,required=True)
    ap.add_argument('--workers',type=int,choices=range(1,5),default=2);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);tech,identity=load_technology('ihp-sg13g2')
    source=[Path(__file__),ROOT/'scripts/qualify_ihp_isolation_layouts.py',ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in source};write(out/'source-files.json',before);(out/'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    tools={n:str(Path(getattr(a,n)).resolve(strict=True)) for n in ('magic','netgen','klayout')}
    report=dict(schema=1,chunk=7,status='RUNNING',qualified=False,chunk_complete=False,scope=__doc__,process=identity,sources=sources(),cases=[],source_files_sha256=file_digest(out/'source-files.json'))
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(case,angle,mirror,out,tech,tools) for angle in (0,90,180,270) for mirror in (False,True)]
        for future in as_completed(jobs):
            row=future.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['rotation'],row['mirror'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in source}
    report['status']='PASS' if report['implementation_unchanged'] and len(report['cases'])==8 and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    write(out/'qualification.json',report);return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
