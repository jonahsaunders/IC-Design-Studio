"""Public IHP isolation-box geometry, three-terminal connectivity and fault controls.

Selected rectangles use the pinned PCell's 1.05 um well ring and zero PWellBlock.
Added real ring/body contacts obey the public decks. No voltage, breakdown,
statistical, continuous-geometry or fabrication qualification is inferred.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
from pathlib import Path
import re
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest, load_project, save_project, scalar
from icstudio.catalog import create_device, link_technology
from icstudio.catalog_migration import emit
from icstudio.layout_import import read_layout
from icstudio.interchange import export_layout
from icstudio.layout_verification import reference, run
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import load_technology, write

SOURCES=ROOT/'icstudio/assets/qualification/ihp-isolation'
SIZES=((4060,4060),(6000,6000),(6000,12000),(12000,6000),(12000,12000))
# A 780 nm inner tap needs 1.24 um nBuLay enclosure on both sides. The pinned
# PCell insets nBuLay 400 nm from each outer edge: 780+2*1240+2*400=4060 nm.
# This is the selected contact's boundary, not a universal isolbox minimum.
BOUNDARIES=((4050,4060),(4070,4060))
PHYSICAL=('is-open','well-open','bulk-open','missing-recognition','duplicate-recognition',
          'well-bulk-short','is-well-short','missing-buried','contact-width')
REFERENCE=('reference-is','reference-well','reference-bulk','reference-area','reference-perimeter')
SOURCE_HASHES={
    'LICENSE':'c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4',
    'isolbox_code.py':'2e86ded691d3c6f974dce177d9c6e2b890560b8912103f3eec830b3e35e086b1',
    'isolbox.gds':'33e083e2d1a6e9ab541458c716fb0bd834a4bca883d93ec3b497c4175c956edc',
    'isolbox.cdl':'4866275cdbd08728e8eb9d2caaa28e298be529b96b2e4d4ddc3dfc99fea13cdb',
    'isolbox_sweep_tb.sch':'fd535442a02f9fde0ab34c5afd52359501f4f261c28b9f0d394e9a12baca7946',
}


def sources():
    if file_digest(SOURCES/'source-lock.json')!='5f3c2a19e70b5da5e80ada943d2db970229c1d0111cb453a467d2daadea2e823':
        raise ValueError('Changed public IHP isolation source lock.')
    lock=json.loads((SOURCES/'source-lock.json').read_text())
    if lock['commit']!='5e6d592e4002946a4616f798c357f0f3c06cf3b6' or set(lock['files'])!=set(SOURCE_HASHES):
        raise ValueError('Changed public IHP isolation sources.')
    for name,sha in SOURCE_HASHES.items():
        if file_digest(SOURCES/name)!=sha or lock['files'][name]['sha256']!=sha:
            raise ValueError('Changed public IHP isolation source: '+name)
    return lock


def stream(path,w,l,rotation=0,fault=None):
    import klayout.db as k
    sources()
    if (w,l) not in (*SIZES,*BOUNDARIES) or rotation not in (0,90,180,270): raise ValueError('Unreviewed isolation geometry.')
    ly=k.Layout(); ly.dbu=.001; c=ly.create_cell('isolation')
    def box(layer,b): c.shapes(ly.layer(layer,0)).insert(k.Box(*b))
    def label(layer,dt,text,x,y): c.shapes(ly.layer(layer,dt)).insert(k.Text(text,k.Trans(x,y)))
    outer=k.Box(-1050,-1050,l-1050,w-1050); inner=k.Box(0,0,l-2100,w-2100)
    well=k.Region(outer)-k.Region(inner)
    active=k.Region(k.Box(-810,-810,l-1290,w-1290))-k.Region(k.Box(-240,-240,l-1860,w-1860))
    for layer,dt,region in [(31,0,well),(99,31,well),(1,0,active)]: c.shapes(ly.layer(layer,dt)).insert(region)
    if fault!='missing-buried': box(32,(-650,-650,l-1450,w-1450))
    c.shapes(ly.layer(1,2)).insert(k.Box(-810,-810,-240,w-1290))
    if fault!='missing-recognition': label(63,0,'isolbox',0,-525)
    if fault=='duplicate-recognition': label(63,0,'isolbox',5,-525)
    # Exact mask equivalence to the independent upstream 6x6 um PCell fixture.
    matching=None
    if (w,l)==(6000,6000) and fault is None:
        old=k.Layout();old.read(str(SOURCES/'isolbox.gds'));leaf=old.cell('isolbox$1')
        matching=[]
        for a,b in ((31,0),(99,31),(1,0),(32,0),(1,2)):
            if not (k.Region(leaf.shapes(old.layer(a,b)))^k.Region(c.shapes(ly.layer(a,b)))).is_empty():
                raise ValueError('Generated isolation mask differs from the pinned public fixture.')
            matching.append([a,b])
    # Real n-active ring and four-cut p+ body ties; no direct well-name labels.
    c.shapes(ly.layer(8,0)).insert(active)
    def centers(end):
        span=end+525; intervals=span//400
        return [-525+5*round(i*span/intervals/5) for i in range(intervals+1)]
    ring=set()
    for x in centers(l-1575):
        for y in (-525,w-1575):ring.add((x,y))
    for y in centers(w-1575):
        for x in (-525,l-1575):ring.add((x,y))
    if fault!='well-open':
        for x,y in sorted(ring):box(6,(x-80,y-80,x+80,y+80))
    label(8,2,'NW',(l-2100)//2,-525)
    positions={'IS':((l-2100)//2,(w-2100)//2),'B':(-4000,-4000)}
    for name,(x,y) in positions.items():
        box(1,(x-390,y-390,x+390,y+390));box(14,(x-570,y-570,x+570,y+570));box(8,(x-390,y-390,x+390,y+390))
        if fault!=('is-open' if name=='IS' else 'bulk-open'):
            for a in (-250,90):
                for b in (-250,90):box(6,(x+a,y+b,x+a+160,y+b+160))
        label(8,2,name,x,y)
    if fault=='well-bulk-short':
        box(8,(-4150,-4150,-3850,-375));box(8,(-4150,-675,-375,-375))
    elif fault=='is-well-short':
        x,y=positions['IS'];box(8,(x-150,-675,x+150,y+150))
    elif fault=='contact-width':
        x,y=positions['IS'];needle=k.Box(x-250,y-250,x-90,y-90)
        for s in c.shapes(ly.layer(6,0)).each():
            if s.bbox()==needle:s.box=k.Box(needle.left,needle.bottom,needle.right-5,needle.top);break
        else:raise ValueError('Missing isolation contact for the width control.')
    elif fault not in (None,*PHYSICAL):raise ValueError('Unknown isolation fault.')
    if rotation:c.transform(k.Trans(rotation//90,False,0,0))
    ly.write(str(path))
    return dict(width_nm=w,length_nm=l,rotation=rotation,outer_area_m2=w*l*1e-18,outer_perimeter_m=2*(w+l)*1e-9,
                well_width_nm=1050,pwell_block_nm=0,public_mask_equivalence=matching,ring_contacts=len(ring),
                source_fixture_sha256=SOURCE_HASHES['isolbox.gds'],generator_sha256=SOURCE_HASHES['isolbox_code.py'])


def selected(tech,w,l,fault=None):
    d=create_device(tech,'sg13g2_pr/isolbox.sym','D1');d['nets']={'isosub':'IS','nwell':'NW','sub!':'B'}
    d['model_params'].update(w=w*1e-9,l=l*1e-9)
    if fault is None:line=emit(d,tech)
    else:
        nodes=['IS','NW','B'];area=w*l*1e-18;perimeter=2*(w+l)*1e-9
        if fault in ('reference-is','reference-well','reference-bulk'):
            nodes[['reference-is','reference-well','reference-bulk'].index(fault)]=['NW','B','IS'][['reference-is','reference-well','reference-bulk'].index(fault)]
        elif fault=='reference-area':area*=1.1
        elif fault=='reference-perimeter':perimeter*=1.1
        elif fault!='public-format':raise ValueError('Unknown isolation reference control.')
        line=f'D1 {" ".join(nodes)} isolbox a={area:.15g} p={perimeter:.15g}'
    return reference('.subckt isolation IS NW B\n'+line+'\n.ends isolation\n','isolation')


def audit_native(path,w,l,prefix):
    rows=[line.split() for line in re.sub(r'\n[ \t]*\+[ \t]*',' ',Path(path).read_text()).splitlines() if line and not line.startswith(('*','.'))]
    if len(rows)!=1 or not rows[0][0].startswith(prefix) or rows[0][1:5]!=['IS','NW','B','isolbox']:
        raise ValueError('Native isolation must preserve its only device and all three terminal roles.')
    params=dict(token.lower().split('=',1) for token in rows[0][5:])
    if set(params)!={'a','p'} or len(rows[0])!=7:raise ValueError('Unreviewed isolation native geometry.')
    for key,expected in [('a',w*l*1e-18),('p',2*(w+l)*1e-9)]:
        if not math.isclose(scalar(params[key]),expected,rel_tol=1e-10,abs_tol=0):raise ValueError('Incorrect native isolation '+key)
    return dict(sha256=file_digest(path),terminals=rows[0][1:4],model='isolbox',area_m2=scalar(params['a']),perimeter_m=scalar(params['p']))


def detected(result,folder,fault):
    stages={s['name']:s for s in result['stages']};folder=Path(folder)
    if result['status']!='failed' or any(stages.get(n,{}).get('status')!='passed' for n in ('preflight','layout_export')):return False
    if fault=='contact-width':
        return stages['drc']['status']=='failed' and any("'CntB.a'" in d['message'] for d in result.get('findings',[])) and all(stages[n]['status']=='passed' for n in ('lvs_extraction','lvs','integrity'))
    if stages['lvs_extraction']['status']=='failed' and (folder/'lvs-extraction/native.cir').is_file():
        error=stages['lvs_extraction'].get('error','')
        return bool(re.search('port names differ|no circuit devices|every marked isolation',error))
    if stages['lvs']['status']=='failed' and (folder/'lvs/lvs.log').is_file():
        return bool(re.search('netlists do not match|circuits do not match|property errors|disconnected node|no matching pin|failed pin matching',(folder/'lvs/lvs.log').read_text(),re.I))
    return False


def case(tech,w,l,rotation,out,tools,faults):
    folder=out/f'w{w}-l{l}-r{rotation}';folder.mkdir();row=dict(width_nm=w,length_nm=l,rotation=rotation,status='RUNNING',faults=[])
    try:
        row['geometry']=stream(folder/'input.gds',w,l,rotation)
        p,_=read_layout(folder/'input.gds');link_technology(p,tech);p['cells'][0]['ports']=['IS','NW','B']
        save_project(p,folder/'saved.icproj');p=load_project(folder/'saved.icproj')
        export_layout(p,folder/'export.gds');export_layout(p,folder/'export.oas')
        q,_=read_layout(folder/'export.oas');link_technology(q,tech);q['cells'][0]['ports']=['IS','NW','B'];export_layout(q,folder/'reimported.gds')
        row['exchange']=dict(gds=compare(folder/'input.gds',folder/'export.gds'),oasis=compare(folder/'export.oas',folder/'reimported.gds',text_presentation=False))
        ref=selected(tech,w,l);dest=folder/'physical';r=run(q,q['top'],dest,tools,ref,lvs_extractor='ihp-klayout',drc_engine='ihp-public')
        if r['status']!='passed':raise ValueError(r.get('error','Isolation physical checks failed.'))
        row.update(report_sha256=file_digest(dest/'report.json'),drc_count=r['drc_count'],native=audit_native(dest/'lvs-extraction/native.cir',w,l,'D'),comparison=audit_native(dest/'lvs-extraction/extracted.spice',w,l,'X'))
        if (w,l)==(4060,4060):
            row['boundaries']=[]
            for bw,bl in BOUNDARIES:
                path=folder/f'boundary-{bw}.gds';stream(path,bw,bl,rotation);bp,_=read_layout(path);link_technology(bp,tech);bp['cells'][0]['ports']=['IS','NW','B']
                dest=folder/f'boundary-{bw}';br=run(bp,bp['top'],dest,tools,selected(tech,bw,bl),lvs_extractor='ihp-klayout',drc_engine='ihp-public')
                states={s['name']:s['status'] for s in br['stages']}
                native=audit_native(dest/'lvs-extraction/native.cir',bw,bl,'D')
                if bw<4060:
                    rule_names=[re.match(r"'([^']+)'",f['message'])[1] for f in br['findings'] if f['code']=='KLAYOUT.DRC']
                    ok=(br['status']=='failed' and rule_names and set(rule_names)=={'nmosi.b'} and all(states[n]=='passed' for n in ('preflight','layout_export','lvs_extraction','lvs','integrity')))
                else:ok=br['status']=='passed'
                row['boundaries'].append(dict(width_nm=bw,length_nm=bl,expected='failed' if bw<4060 else 'passed',observed=br['status'],accepted=bool(ok),native=native,report_sha256=file_digest(dest/'report.json')))
                if not ok:raise ValueError('Isolation contact enclosure boundary has an unexpected outcome.')
        if rotation==0 and faults:
            dest=folder/'public-format';r=run(q,q['top'],dest,tools,selected(tech,w,l,'public-format'),lvs_extractor='ihp-klayout',drc_engine='ihp-public')
            if r['status']!='passed':raise ValueError('Public A/P reference did not pass.')
            row['public_reference_sha256']=file_digest(dest/'report.json')
            for fault in (*PHYSICAL,*REFERENCE):
                altered=q
                if fault in PHYSICAL:
                    path=folder/(fault+'.gds');stream(path,w,l,rotation,fault);altered,_=read_layout(path);link_technology(altered,tech);altered['cells'][0]['ports']=['IS','NW','B']
                dest=folder/fault;r=run(altered,altered['top'],dest,tools,selected(tech,w,l,fault) if fault in REFERENCE else ref,lvs_extractor='ihp-klayout',drc_engine='ihp-public')
                ok=detected(r,dest,fault);row['faults'].append(dict(fault=fault,detected=ok,status=r['status'],error=r.get('error'),report_sha256=file_digest(dest/'report.json')))
                if not ok:raise ValueError('Isolation control missed or failed at an unintended stage: '+fault)
        row['status']='PASS'
    except Exception as e:row.update(status='FAIL',error=repr(e),traceback=traceback.format_exc())
    write(folder/'record.json',row);return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    for name in ('magic','netgen','klayout'):ap.add_argument('--'+name,required=True)
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,5),default=2);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source_files=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    before={p.relative_to(ROOT).as_posix():file_digest(p) for p in source_files};write(out/'source-files.json',before)
    (out/'executed-runner.py').write_bytes(Path(__file__).read_bytes());tech,identity=load_technology('ihp-sg13g2')
    tools={n:str(Path(getattr(a,n)).resolve(strict=True)) for n in ('magic','netgen','klayout')}
    report=dict(schema=1,chunk=7,status='RUNNING',chunk_complete=False,qualified=False,pilot=a.pilot,scope=__doc__,sources=sources(),process=identity,cases=[],source_files_sha256=file_digest(out/'source-files.json'))
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(case,tech,w,l,rotation,out,tools,True) for w,l in (((6000,6000),) if a.pilot else SIZES) for rotation in ((0,) if a.pilot else (0,90,180,270))]
        for job in as_completed(jobs):
            row=job.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['width_nm'],row['length_nm'],row['rotation'],row['status'],row.get('error',''),flush=True)
    report['implementation_unchanged']=before=={p.relative_to(ROOT).as_posix():file_digest(p) for p in source_files}
    report['status']='PASS' if report['implementation_unchanged'] and len(report['cases'])==len(jobs) and all(r['status']=='PASS' for r in report['cases']) else 'FAIL'
    report['cases'].sort(key=lambda r:(r['width_nm'],r['length_nm'],r['rotation']));write(out/'qualification.json',report)
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
