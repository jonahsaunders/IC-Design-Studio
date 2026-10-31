"""Sampled IHP 3.3 V MOS geometry through Magic and public KLayout DRC/LVS.

Read native channels and exported diffusion groups independently of LVS merges.
This does not qualify electrical operating envelopes, RC or foundry signoff.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from decimal import Decimal
import json
from pathlib import Path
import re
import sys
import traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.catalog import create_device,link_technology
from icstudio.ihp_layout import install_mos,layers
from icstudio.interchange import export_layout
from icstudio.layout_import import read_layout
from icstudio.layout_verification import reference,run,STAGES
from icstudio.model import clone,example,file_digest,save_project,load_project
from icstudio.physical_cells import assign_port
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import load_technology
from scripts.qualify_mos_parallel_layouts import rejected


def sizes(polarity):
    minimum=.45 if polarity=='n' else .4
    return ((.3,minimum,1,1),(.6,minimum,2,3),(3,1,3,3),(10,10,8,16),(10,10,1,16))


def fixture(tech,polarity,size):
    width,length,fingers,copies=size;p=example('empty');p['pdk']=clone(tech)
    c=p['cells'][0];c.update(name='parallel_coupon',ports=['D','G','S','B'])
    d=create_device(p['pdk'],'sg13g2_pr/sg13_hv_'+polarity+'mos.sym','M1')
    d['params'].update(w=f'{width:g}u',l=f'{length:g}u');d['model_params'].update(ng=str(fingers),m=str(copies))
    d['nets']=dict(d='D',g='G',s='S',b='B');c['devices']=[d];install_mos(p,c['id'],d['id'])
    for pin in c['layout_pins']:assign_port(p,c['id'],d['nets'][pin['pin']],pin['layer'],pin['point'])
    return p


def selected(polarity,size,fault=None):
    width,length,fingers,copies=size;model='sg13_hv_'+polarity+'mos'
    if fault=='reference-width':width*=1.2
    if fault=='reference-copies':copies+=1
    if fault=='reference-fingers':fingers+=1
    if fault=='reference-grouping':width=float(Decimal(str(width))/fingers);copies*=fingers;fingers=1
    if fault=='reference-low-voltage':model=model.replace('_hv_','_lv_')
    nodes='D B S G' if fault=='reference-gate-body' else 'D G S B'
    return reference(f'.subckt parallel_coupon D G S B\nX1 {nodes} {model} w={width:g}u l={length:g}u ng={fingers} m={copies}\n.ends parallel_coupon\n','parallel_coupon')


def channel_parameters(tokens,required=('w','l')):
    """Reject duplicate, omitted, nonnumeric or unreviewed native fields."""
    allowed={'w','l','as','ad','ps','pd','m','rfmode'};params={}
    number=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?(?:meg|[tgkmunpf])?'
    for token in tokens:
        if token.count('=')!=1:raise ValueError('Ambiguous native channel parameter.')
        key,value=token.lower().split('=')
        if key not in allowed or key in params or re.fullmatch(number,value) is None:
            raise ValueError('Unexpected or duplicate native channel parameter.')
        params[key]=value
    if not set(required)<=params.keys():raise ValueError('Missing native channel parameters.')
    return params


def fault_stages(report):
    rows=report['stages']
    if (report['status']!='failed' or not isinstance(rows,list) or len(rows)!=len(STAGES)
            or {r['name'] for r in rows}!=set(STAGES)):
        raise ValueError('Malformed native fault stages.')
    result={r['name']:r for r in rows}
    if any(r['status'] not in ('passed','failed','not_run') or
           (r['status']=='passed' and 'error' in r) for r in rows):
        raise ValueError('Unexpected native fault stage status.')
    return result


def checked_file(path,expected):
    if not isinstance(expected,str) or re.fullmatch('[0-9a-f]{64}',expected) is None:
        raise ValueError('Missing native evidence checksum.')
    path=Path(path)
    if not path.is_file() or file_digest(path)!=expected:
        raise ValueError('Native evidence changed or is missing.')


def ordinary_fault(report,folder):
    """Only a completed, integrity-checked native mismatch is a control pass."""
    try:
        stages=fault_stages(report);folder=Path(folder)
        if (any(stages[n]['status']!='passed' for n in
                ('preflight','layout_export','lvs_extraction','integrity'))
                or stages['lvs']['status']!='failed' or stages['drc']['status'] not in ('passed','failed')):
            return False
        integrity=stages['integrity']['evidence']
        if (integrity['verified'] is not True or any(not isinstance(integrity[k],dict) or not integrity[k]
                for k in ('assets','tools','files'))):
            return False
        for name in ('lvs/lvs.log','lvs-extraction/extracted.spice'):
            checked_file(folder/name,integrity['files'][name])
        return rejected(report,folder)
    except (KeyError,TypeError,ValueError,OSError,AttributeError):return False


def aborted_extraction_integrity(stages,folder):
    """Recheck inputs normally checked after LVS, which this fault never reaches."""
    preflight=stages['preflight']['evidence'];assets=preflight['assets'];tools=preflight['tools']
    if not isinstance(assets,dict) or not assets or not isinstance(tools,dict) or set(tools)!={'magic','netgen','klayout'}:
        raise ValueError('Incomplete aborted-extraction input evidence.')
    for path,sha in assets.items():
        if not Path(path).is_absolute():raise ValueError('Expected an absolute native asset path.')
        checked_file(path,sha)
    for tool in tools.values():
        if not Path(tool['path']).is_absolute():raise ValueError('Expected an absolute native tool path.')
        checked_file(tool['path'],tool['sha256'])
    export=stages['layout_export']['evidence']
    checked_file(folder/'layout.gds',export['sha256'])
    checked_file(folder/'original.gds',export['source_sha256'])


def channels(path,polarity,size,*,primitive=False):
    """Read every raw device; do not infer width/fingers from total current."""
    width,length,fingers,copies=size;expected='sg13_hv_'+polarity+'mos'
    text=re.sub(r'\n\s*\+',' ',Path(path).read_text(encoding='utf-8'))
    lines=[s.split() for s in text.splitlines() if s.strip() and not s.lstrip().startswith('*')]
    if (len(lines)<3 or [s.lower() for s in lines[0][:2]]!=['.subckt','parallel_coupon']
            or set(lines[0][2:])!={'D','G','S','B'} or len(lines[0])!=6
            or [s.lower() for s in lines[-1]] not in (['.ends'],['.ends','parallel_coupon'])):
        raise ValueError('Unexpected native circuit interface.')
    units=lines[1:-1]
    if len(units)!=fingers*copies or len({s[0].lower() for s in units})!=len(units):
        raise ValueError('Native channel count differs.')
    def microns(value):return Decimal(value[:-1]) if value.endswith('u') else Decimal(value)*1000000
    for row in units:
        if (len(row)<8 or row[0][0].upper()!=('M' if primitive else 'X') or row[5]!=expected
                or row[2]!='G' or row[4]!='B' or set((row[1],row[3]))!={'D','S'}):
            raise ValueError('Native model or four-terminal connectivity differs.')
        params=channel_parameters(row[6:])
        if (microns(params['w'])!=Decimal(str(width))/fingers or microns(params['l'])!=Decimal(str(length))
                or Decimal(params.get('m','1'))!=1 or Decimal(params.get('rfmode','0'))!=0):
            raise ValueError('Native channel dimensions, multiplicity or RF mode differ.')
    return dict(channels=len(units),model=expected,sha256=file_digest(path))


def masks(path,polarity,size):
    """Independently inspect process masks, including implicit N+ and HV oxide."""
    import klayout.db as db
    width,length,fingers,copies=size;ly=db.Layout();ly.read(str(path));cell=ly.top_cell();scale=Decimal(str(ly.dbu))*1000
    def region(layer):
        i=ly.find_layer(layer,0)
        return db.Region(cell.begin_shapes_rec(i)).merged() if i is not None else db.Region()
    active,poly,psd,well,oxide=(region(i) for i in (1,5,14,31,44))
    primary=((active&psd)&well if polarity=='p' else (active-psd)-well).merged()
    groups=list(primary.each())
    if len(groups)!=copies:raise ValueError('Physical shared-diffusion group count differs.')
    if not (primary&region(7)).is_empty():raise ValueError('Explicit nSD excludes ordinary MOS in the public deck.')
    margin=int(Decimal(270)/scale)
    if not (primary.sized(margin)-oxide).is_empty():raise ValueError('Missing HV oxide or active enclosure.')
    expected=sorted((Decimal(str(width))*1000/fingers,Decimal(str(length))*1000));count=0
    for group in groups:
        gates=(db.Region(group)&poly).merged()
        if gates.count()!=fingers:raise ValueError('Physical gate-finger count differs.')
        for gate in gates.each():
            b=gate.bbox()
            if sorted((Decimal(b.width())*scale,Decimal(b.height())*scale))!=expected or Decimal(gate.area())*scale*scale!=expected[0]*expected[1]:
                raise ValueError('Physical channel dimensions differ.')
            count+=1
    return dict(groups=len(groups),fingers_per_group=fingers,channels=count,sha256=file_digest(path))


def altered(project,fault):
    p=clone(project);c=p['cells'][0];ls=layers(p['pdk'])
    if fault.startswith('reference-'):return p
    if fault=='missing-oxide':
        c['shapes']=[s for s in c['shapes'] if s['layer']!=ls['thickox']]
    elif fault=='oxide-enclosure':
        shape=next(s for s in c['shapes'] if s['layer']==ls['thickox']);shape['points'][0][0]+=100
    elif fault=='well-enclosure':
        shape=next(s for s in c['shapes'] if s['layer']==ls['nwell']);shape['points'][1][0]-=100
    elif fault=='body-open':
        from icstudio.layout import polygon,kdb
        body=next(pin['point'] for pin in c['layout_pins'] if pin['pin']=='b')
        # Only the single-copy fixture uses this control; all its body cuts.
        cuts=[s for s in c['shapes'] if s['layer']==ls['contact'] and polygon(s).inside(kdb().Point(*body))]
        if len(cuts)!=1:raise ValueError('Body control did not select exactly one contact.')
        c['shapes']=[s for s in c['shapes'] if s not in cuts]
    else:raise ValueError('Unknown HV control.')
    return p


def verify(p,folder,tools,ref,engine):
    return run(p,p['top'],folder,tools,ref,lvs_extractor=engine,drc_engine='magic' if engine=='magic' else 'ihp-public')


def disconnected_body(report,folder,polarity,size):
    """Require completed extraction of the actual transistor with only B lost."""
    try:
        stages=fault_stages(report);folder=Path(folder)
        if (tuple(size[2:])!=(1,1) or report['lvs_extractor']!='ihp-klayout' or report['drc_engine']!='ihp-public'
                or any(stages[n]['status']!='passed' for n in ('preflight','layout_export'))
                or stages['lvs_extraction']['status']!='failed'
                or stages['lvs_extraction'].get('error')!='IHP extracted port names differ from the schematic.'
                or any(stages[n]['status']!='not_run' for n in ('lvs','integrity'))):return False
        aborted_extraction_integrity(stages,folder)
        drc=report['klayout_drc'];decks=drc['decks']
        if (not isinstance(decks,list) or len(decks)!=2 or {d['name'] for d in decks}!={'main','maximal'}
                or any(not isinstance(d['categories'],list) or type(d['violations']) is not int or d['violations']<0 for d in decks)
                or type(report['drc_count']) is not int or report['drc_count']!=sum(d['violations'] for d in decks)):
            return False
        checked_file(folder/'original.gds',drc['input_sha256'])
        for deck in decks:
            path=(folder/'drc'/deck['report']).resolve()
            if not path.is_relative_to((folder/'drc').resolve()):return False
            checked_file(path,deck['report_sha256'])
        rules={r.strip("'") for d in decks for r in d['categories']}
        if stages['drc']['status']=='passed':
            if report['drc_count']!=0 or rules:return False
        else:
            # A missing PMOS body contact also violates precisely this well-tap rule.
            if polarity!='p' or stages['drc']['status']!='failed' or rules!={'LU.a'} or report['drc_count']<1:return False
        path=folder/'lvs-extraction/native.cir';log=folder/'lvs-extraction/console.log'
        if not path.is_file() or not log.is_file():return False
        console=log.read_text(encoding='utf-8')
        if any(marker not in console for marker in ('LVS Total Run time ','NET_ONLY enabled: apply extraction netlist options and skip comparison.')):return False
        lines=[s.split() for s in re.sub(r'\n\s*\+',' ',path.read_text(encoding='utf-8')).splitlines() if s.strip() and not s.lstrip().startswith('*')]
        if len(lines)!=3 or [s.lower() for s in lines[0][:2]]!=['.subckt','parallel_coupon'] or len(lines[0])!=5 or set(lines[0][2:])!={'D','G','S'}:return False
        unit=lines[1]
        if len(unit)<9 or unit[0][0]!='M' or unit[2]!='G' or set((unit[1],unit[3]))!={'D','S'} or re.fullmatch(r'\\?\$\d+',unit[4]) is None or unit[5]!='sg13_hv_'+polarity+'mos':return False
        params=channel_parameters(unit[6:],required=('w','l','rfmode'))
        return (params['w']==f'{size[0]:g}u' and params['l']==f'{size[1]:g}u'
                and params['rfmode']=='0' and params.get('m','1')=='1'
                and [s.lower() for s in lines[2]]==['.ends','parallel_coupon'])
    except (KeyError,TypeError,ValueError,OSError,AttributeError):return False


def execute(polarity,size,output,tools,pilot):
    folder=Path(output)/(polarity+'-'+('-'.join(map(str,size))));folder.mkdir()
    row=dict(polarity=polarity,size=size,status='RUNNING',layouts=[],faults=[])
    try:
        tech,identity=load_technology('ihp-sg13g2');row['package']=identity
        p=fixture(tech,polarity,size);save_project(p,folder/'original.icproj');p=load_project(folder/'original.icproj');export_layout(p,folder/'original.gds')
        import klayout.db as db
        for angle,mirror in ([(0,False)] if pilot else [(a,m) for m in (False,True) for a in (0,90,180,270)]):
            tag=str(angle)+('-mirror' if mirror else '');ly=db.Layout();ly.read(str(folder/'original.gds'))
            ly.top_cell().transform(db.Trans(angle//90,mirror,0,0));ly.write(str(folder/(tag+'.gds')))
            q,_=read_layout(folder/(tag+'.gds'));link_technology(q,tech);q['cells'][0]['ports']=['D','G','S','B']
            export_layout(q,folder/(tag+'.oas'));q,_=read_layout(folder/(tag+'.oas'));link_technology(q,tech);q['cells'][0]['ports']=['D','G','S','B']
            export_layout(q,folder/(tag+'-roundtrip.gds'));exchange=compare(folder/(tag+'.gds'),folder/(tag+'-roundtrip.gds'),text_presentation=False)
            for engine in ('magic','ihp-klayout'):
                dest=folder/(tag+'-'+engine);report=verify(q,dest,tools,selected(polarity,size),engine)
                if report['status']!='passed':raise ValueError(engine+': '+report.get('error','Native check failed.'))
                proof=channels(dest/'lvs-extraction/extracted.spice',polarity,size)
                raw=channels(dest/'lvs-extraction/native.cir',polarity,size,primitive=True) if engine=='ihp-klayout' else proof
                row['layouts'].append(dict(angle=angle,mirror=mirror,engine=engine,exchange=exchange,native=proof,raw=raw,physical=masks(dest/'layout.gds',polarity,size),report_sha256=file_digest(dest/'report.json')))
        faults=['missing-oxide','oxide-enclosure','reference-low-voltage','reference-width','reference-copies','reference-gate-body']
        if size[2]>1:faults+=['reference-fingers','reference-grouping']
        if polarity=='p':faults+=['well-enclosure']
        if size[2:]==(1,1):faults+=['body-open']
        for fault in faults:
            for engine in ('magic','ihp-klayout'):
                dest=folder/(fault+'-'+engine);report=verify(altered(p,fault),dest,tools,selected(polarity,size,fault),engine);method='native_lvs'
                if fault in ('reference-fingers','reference-grouping'):
                    if report['status']!='passed':raise ValueError('Inspect changed native finger/grouping behavior.')
                    width,length,fingers,copies=size
                    wrong=(width,length,fingers+1,copies) if fault=='reference-fingers' else (float(Decimal(str(width))/fingers),length,1,fingers*copies)
                    checker=channels if fault=='reference-fingers' else masks
                    path=dest/'lvs-extraction/extracted.spice' if fault=='reference-fingers' else dest/'layout.gds'
                    try:checker(path,polarity,wrong)
                    except ValueError:method='independent_native_channels' if fault=='reference-fingers' else 'independent_mask_groups'
                    else:raise ValueError('Independent checker missed '+fault)
                elif fault in ('oxide-enclosure','well-enclosure'):
                    if fault=='oxide-enclosure' and engine=='magic':
                        # Magic reconstructs its HV type from oxide overlap and
                        # cannot observe this enclosure loss after conversion.
                        # Require its known outcome plus independent original-
                        # mask rejection. The public deck must reject it below.
                        if report['status']!='passed':raise ValueError('Inspect changed Magic oxide-enclosure behavior.')
                        try:masks(dest/'layout.gds',polarity,size)
                        except ValueError:method='independent_oxide_enclosure'
                        else:raise ValueError('Independent mask check missed oxide enclosure.')
                        row['faults'].append(dict(fault=fault,engine=engine,detected=True,method=method,native_status=report['status'],report_sha256=file_digest(dest/'report.json')))
                        continue
                    stages={s['name']:s['status'] for s in report['stages']}
                    if report['status']!='failed' or report.get('drc_count',0)<1 or any(stages.get(n)!='passed' for n in ('preflight','layout_export','lvs_extraction','lvs','integrity')):
                        raise ValueError('Expected a completed DRC-only failure for '+fault)
                    if engine=='ihp-klayout':
                        rules={r.strip("'") for deck in report['klayout_drc']['decks'] for r in deck['categories']}
                        if ('TGO.a' if fault=='oxide-enclosure' else 'NW.c1') not in rules:raise ValueError('Wrong public rule rejected '+fault)
                    else:
                        findings=(dest/'drc/findings.tsv').read_text(encoding='utf-8')
                        if ('TGO.a' if fault=='oxide-enclosure' else 'NW.c1') not in findings:raise ValueError('Wrong native rule rejected '+fault)
                    method='native_geometry_rules'
                elif fault=='body-open' and engine=='ihp-klayout':
                    if not disconnected_body(report,dest,polarity,size):raise ValueError('Expected completed extraction with only body connectivity lost.')
                    method='native_disconnected_body_and_port'
                elif not ordinary_fault(report,dest):raise ValueError('Native comparison missed '+fault+': '+str(report.get('error')))
                row['faults'].append(dict(fault=fault,engine=engine,detected=True,method=method,native_status=report['status'],report_sha256=file_digest(dest/'report.json')))
        row['status']='PASS'
    except Exception as e:row.update(status='FAIL',error=str(e),traceback=traceback.format_exc())
    (folder/'record.json').write_bytes((json.dumps(row,indent=2)+'\n').encode());return row


def inverter(counts,output,tools):
    from icstudio.ihp_layout import generate_inverter
    nf,pf,nm,pm=counts;folder=Path(output)/('inverter-'+'-'.join(map(str,counts)));folder.mkdir()
    row=dict(counts=counts,status='RUNNING',layouts=[])
    try:
        tech,_=load_technology('ihp-sg13g2');p=fixture(tech,'n',(nf,.5,nf,nm));q=fixture(tech,'p',(pf,.5,pf,pm))
        c=p['cells'][0];other=q['cells'][0]['devices'][0];other['name']='M2';c['devices'].append(other)
        c.update(name='hv_inverter',ports=['A','Y','VPWR','VGND'])
        for d in c['devices']:
            supply='VGND' if d['kind']=='NMOS' else 'VPWR';d['nets']=dict(d='Y',g='A',s=supply,b=supply)
        for key in ('shapes','layout_pins','layout_ports','pdk_layouts'):c[key]=[]
        generate_inverter(p,c['id']);save_project(p,folder/'original.icproj')
        text=f'.subckt hv_inverter A Y VPWR VGND\nX1 Y A VGND VGND sg13_hv_nmos w={nf}u l=.5u ng={nf} m={nm}\nX2 Y A VPWR VPWR sg13_hv_pmos w={pf}u l=.5u ng={pf} m={pm}\n.ends hv_inverter\n'
        for engine in ('magic','ihp-klayout'):
            dest=folder/engine;report=verify(p,dest,tools,reference(text,'hv_inverter'),engine)
            if report['status']!='passed':raise ValueError(engine+': '+report.get('error','Inverter check failed.'))
            extracted=dest/'lvs-extraction/extracted.spice';units=[s.split() for s in re.sub(r'\n\s*\+',' ',extracted.read_text(encoding='utf-8')).splitlines() if re.match(r'^\s*X\S+\s',s)]
            counts_found=dict(sg13_hv_nmos=0,sg13_hv_pmos=0)
            for unit in units:
                model=unit[5];supply='VGND' if model=='sg13_hv_nmos' else 'VPWR'
                if model not in counts_found or unit[2]!='A' or unit[4]!=supply or set((unit[1],unit[3]))!={'Y',supply}:raise ValueError('Inverter native model/terminal mismatch.')
                params=channel_parameters(unit[6:])
                if Decimal(params['w'][:-1])!=1 or not params['w'].endswith('u') or Decimal(params['l'][:-1])!=Decimal('.5') or not params['l'].endswith('u') or Decimal(params.get('m','1'))!=1 or Decimal(params.get('rfmode','0'))!=0:raise ValueError('Inverter native channel dimensions differ.')
                counts_found[model]+=1
            if counts_found!=dict(sg13_hv_nmos=nf*nm,sg13_hv_pmos=pf*pm):raise ValueError('Inverter native channel count differs.')
            physical={pol:masks(dest/'layout.gds',pol,size) for pol,size in (('n',(nf,.5,nf,nm)),('p',(pf,.5,pf,pm)))}
            row['layouts'].append(dict(engine=engine,channels=counts_found,physical=physical,extracted_sha256=file_digest(extracted),report_sha256=file_digest(dest/'report.json')))
        row['status']='PASS'
    except Exception as e:row.update(status='FAIL',error=str(e),traceback=traceback.format_exc())
    (folder/'record.json').write_bytes((json.dumps(row,indent=2)+'\n').encode());return row


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('output','magic','netgen','klayout'):ap.add_argument('--'+n,type=Path,required=True)
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,5),default=2)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    files=[Path(__file__),ROOT/'scripts/qualify_mos_parallel_layouts.py',ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').glob('*.py'))]
    hashes={p.relative_to(ROOT).as_posix():file_digest(p) for p in files};(out/'source-files.json').write_bytes((json.dumps(hashes,indent=2)+'\n').encode())
    tools={n:str(getattr(a,n).resolve(strict=True)) for n in ('magic','netgen','klayout')}
    record=dict(status='RUNNING',chunk=7,chunk_complete=False,qualified=False,scope=__doc__,pilot=a.pilot,cases=[],inverters=[],engines={n:dict(path=p,sha256=file_digest(p)) for n,p in tools.items()},source_files_sha256=file_digest(out/'source-files.json'))
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(execute,p,s,out,tools,a.pilot) for p in ('n','p') for s in (sizes(p)[:2] if a.pilot else sizes(p))]
        for job in as_completed(jobs):
            row=job.result();record['cases'].append(row);print(row['polarity'],row['size'],row['status'],row.get('error',''),flush=True)
            (out/'record.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
        contexts=[pool.submit(inverter,counts,out,tools) for counts in (((1,1,1,1),) if a.pilot else ((1,1,1,1),(2,3,1,1),(3,2,3,1),(8,1,16,1)))]
        for job in as_completed(contexts):
            row=job.result();record['inverters'].append(row);print('inverter',row['counts'],row['status'],row.get('error',''),flush=True)
            (out/'record.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
    record['source_unchanged']=hashes=={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    record['status']='PASS' if record['source_unchanged'] and len(record['cases'])==len(jobs) and len(record['inverters'])==len(contexts) and all(r['status']=='PASS' for r in record['cases']+record['inverters']) else 'FAIL'
    (out/'record.json').write_bytes((json.dumps(record,indent=2)+'\n').encode());return int(record['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
