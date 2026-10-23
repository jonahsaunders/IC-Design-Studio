"""Check shared GF180/IHP MOS fingers against native geometry and model intent.

Native LVS merges equal-terminal devices and ignores nf/ng. Independent native
channel readback is therefore mandatory for this qualification batch. These
sampled geometric/terminal checks do not qualify RC, mismatch or operating limits.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from decimal import Decimal
import json
from pathlib import Path
import re
import sys
import traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.catalog import create_device,link_technology
from icstudio.interchange import export_layout
from icstudio.layout_import import read_layout
from icstudio.layout_verification import reference,run
from icstudio.model import clone,example,file_digest,load_project,save_project
from icstudio.physical_cells import assign_port
from icstudio.process_adapters import ADAPTERS
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import PROFILES,load_technology
from scripts.qualify_mos_parallel_layouts import TARGETS,audit_native,rejected

FAULTS=('missing-finger','gate-contact-open','source-contact-open','drain-contact-open',
        'all-body-contacts-open','gate-source-short','reference-width','reference-copies','reference-fingers','reference-grouping','reference-gate-body')


def sizes(target):
    return ((.3,.13,2,1) if target=='ihp-sg13g2' else (.44,.28,2,1), (3,1,3,3), (10,10,8,16))


def fixture(technology,target,polarity,size):
    width,length,fingers,copies=size;profile=PROFILES[target]
    p=example('empty');p['pdk']=clone(technology);c=p['cells'][0];c.update(name='parallel_coupon',ports=['D','G','S','B'])
    d=create_device(p['pdk'],profile['prefix']+profile['symbols'][polarity=='p']+'.sym','M1')
    d['params'].update(w=f'{width:g}u',l=f'{length:g}u')
    d['model_params'].update({('ng' if target=='ihp-sg13g2' else 'nf'):str(fingers),'m':str(copies)})
    d['nets']=dict(d='D',g='G',s='S',b='B');c['devices']=[d]
    ADAPTERS[target].implementation().install_mos(p,c['id'],d['id'])
    for pin in c['layout_pins']:assign_port(p,c['id'],d['nets'][pin['pin']],pin['layer'],pin['point'])
    return p


def selected(target,polarity,size,fault=None):
    width,length,fingers,copies=size
    if fault=='reference-width':width*=1.2
    if fault=='reference-copies':copies+=1
    if fault=='reference-fingers':fingers+=1
    if fault=='reference-grouping':width=float(Decimal(str(width))/fingers);copies*=fingers;fingers=1
    pins='D B S G' if fault=='reference-gate-body' else 'D G S B'
    model=PROFILES[target]['models'][polarity=='p'];key='ng' if target=='ihp-sg13g2' else 'nf'
    return reference(f'.subckt parallel_coupon D G S B\nX1 {pins} {model} w={width:g}u l={length:g}u {key}={fingers} m={copies}\n.ends parallel_coupon\n','parallel_coupon')


def channel_audit(path,target,polarity,size):
    width,length,fingers,copies=size
    per_width=float(Decimal(str(width))/Decimal(fingers))
    result=audit_native(path,target,polarity,(per_width,length,fingers*copies))
    result.update(total_width_um=width,fingers_per_copy=fingers,parallel_copies=copies)
    return result


def shared_diffusion_audit(stream,target,polarity,size):
    """Read actual masks, without relying on generated shape roles or metadata."""
    import klayout.db as db
    width,length,fingers,copies=size;ly=db.Layout();ly.read(str(stream));cell=ly.top_cell()
    scale=Decimal(str(ly.dbu))*1000
    masks=(1,5,14 if polarity=='p' else 7) if target=='ihp-sg13g2' else (22,30,31 if polarity=='p' else 32)
    def region(layer):
        index=ly.find_layer(layer,0)
        if index is None:raise ValueError('Missing native MOS mask.')
        return db.Region(cell.begin_shapes_rec(index)).merged()
    primary=(region(masks[0])&region(masks[2])).merged();gates=region(masks[1])
    well_layer=31 if target=='ihp-sg13g2' else 21
    index=ly.find_layer(well_layer,0);well=db.Region(cell.begin_shapes_rec(index)).merged() if index is not None else db.Region()
    # Standard NMOS is outside NWell; PMOS is inside. This excludes the
    # opposite transistor's body taps in a mixed-polarity inverter context.
    primary=(primary&well if polarity=='p' else primary-well).merged()
    groups=list(primary.each())
    if len(groups)!=copies:raise ValueError('Physical shared-diffusion groups differ from parallel-copy count.')
    expected=sorted((Decimal(str(width))*1000/fingers,Decimal(str(length))*1000));channels=0
    for group in groups:
        pieces=(db.Region(group)&gates).merged()
        if pieces.count()!=fingers:raise ValueError('Physical gate-finger count differs within a shared diffusion group.')
        for piece in pieces.each():
            box=piece.bbox()
            if (sorted((Decimal(box.width())*scale,Decimal(box.height())*scale))!=expected
                    or Decimal(piece.area())*scale*scale!=expected[0]*expected[1]):
                raise ValueError('Exported channel dimensions differ from W/fingers and L.')
            channels+=1
    return dict(groups=len(groups),fingers_per_group=fingers,channels=channels,stream_sha256=file_digest(stream))


def altered(project,target,fault):
    p=clone(project);c=p['cells'][0]
    if fault.startswith('reference-'):return p
    record=c['pdk_layouts'][0];fingers=record['fingers']['count'];remove=[]
    if fault=='missing-finger':
        wanted={f'fingers:gate:{fingers-1}:poly',f'fingers:gate:{fingers-1}:pad'}
        remove=[s for s in c['shapes'] if s.get('generator_role') in wanted]
        if len(remove)!=2:raise ValueError('The missing-finger control did not select one physical gate.')
    elif fault in ('gate-contact-open','source-contact-open','drain-contact-open'):
        wanted={'gate-contact-open':'fingers:gate:0:cut','source-contact-open':'fingers:diffusion:0:cut','drain-contact-open':'fingers:diffusion:1:cut'}[fault]
        remove=[s for s in c['shapes'] if s.get('generator_role')==wanted]
        if len(remove)!=1:raise ValueError('The contact control must remove one actual cut.')
    elif fault=='all-body-contacts-open':
        remove=[s for s in c['shapes'] if re.search(r'fingers:body:\d+:cut$',s.get('generator_role',''))]
        copies=record.get('parallel_units',{}).get('count',1)
        if len(remove)!=(fingers+1)*copies:raise ValueError('Incomplete body-contact control.')
    elif fault=='gate-source-short':
        from icstudio.model import uid
        pins={pin['pin']:pin for pin in c['layout_pins']};gx,gy=pins['g']['point'];sx,sy=pins['s']['point']
        c['shapes'].append(dict(id=uid(),kind='path',layer=pins['g']['layer'],width=440,points=[[gx,gy],[sx,gy],[sx,sy]],net=''))
        return p
    else:raise ValueError('Unknown finger fault.')
    c['shapes']=[s for s in c['shapes'] if s not in remove];return p


def execute(target,polarity,size,out,tools,pilot):
    folder=Path(out)/(target+'-'+polarity+'-f'+str(size[2]));folder.mkdir()
    row=dict(target=target,polarity=polarity,size=size,status='RUNNING',layouts=[],faults=[])
    try:
        tech,identity=load_technology(target);row['package']=identity
        original=fixture(tech,target,polarity,size);save_project(original,folder/'original.icproj');original=load_project(folder/'original.icproj')
        export_layout(original,folder/'original.gds');import klayout.db as db
        for rotation,mirror in ([(0,False)] if pilot else [(r,m) for m in (False,True) for r in (0,90,180,270)]):
            tag=str(rotation)+('-mirror' if mirror else '');ly=db.Layout();ly.read(str(folder/'original.gds'))
            ly.top_cell().transform(db.Trans(rotation//90,mirror,0,0));ly.write(str(folder/(tag+'.gds')))
            p,_=read_layout(folder/(tag+'.gds'));link_technology(p,original['pdk']);p['cells'][0]['ports']=['D','G','S','B']
            export_layout(p,folder/(tag+'.oas'));p,_=read_layout(folder/(tag+'.oas'));link_technology(p,original['pdk']);p['cells'][0]['ports']=['D','G','S','B']
            export_layout(p,folder/(tag+'-roundtrip.gds'));exchange=compare(folder/(tag+'.gds'),folder/(tag+'-roundtrip.gds'),text_presentation=False)
            dest=folder/('valid-'+tag);report=run(p,p['top'],dest,tools,selected(target,polarity,size))
            if report['status']!='passed':raise ValueError(report.get('error','Native check failed.'))
            checked=channel_audit(dest/'lvs-extraction/extracted.spice',target,polarity,size)
            physical=shared_diffusion_audit(dest/'layout.gds',target,polarity,size)
            row['layouts'].append(dict(rotation=rotation,mirror=mirror,native=checked,physical=physical,exchange=exchange,report_sha256=file_digest(dest/'report.json')))
        for fault in FAULTS:
            dest=folder/fault;report=run(altered(original,target,fault),original['top'],dest,tools,selected(target,polarity,size,fault))
            method='native_lvs'
            if fault=='reference-fingers':
                # Document the native comparator's known omission. Independent
                # readback must reject the same-W but wrong-finger reference.
                if report['status']!='passed':raise ValueError('Finger-control native result changed; inspect before claiming independent rejection.')
                wrong=list(size);wrong[2]+=1
                try:channel_audit(dest/'lvs-extraction/extracted.spice',target,polarity,wrong)
                except ValueError:method='independent_native_channel_count_and_dimensions'
                else:raise ValueError('Wrong finger count was not detected by native channel readback.')
            elif fault=='reference-grouping':
                if report['status']!='passed':raise ValueError('Inspect changed native grouping-control result.')
                width,length,fingers,copies=size;wrong=(float(Decimal(str(width))/fingers),length,1,fingers*copies)
                channel_audit(dest/'lvs-extraction/extracted.spice',target,polarity,wrong)
                try:shared_diffusion_audit(dest/'layout.gds',target,polarity,wrong)
                except ValueError:method='independent_exported_diffusion_groups'
                else:raise ValueError('Wrong physical copy/finger grouping was not detected.')
            elif not rejected(report,dest):raise ValueError('Native connectivity/size checking did not detect '+fault)
            row['faults'].append(dict(fault=fault,detected=True,method=method,native_status=report['status'],report_sha256=file_digest(dest/'report.json')))
        row['status']='PASS'
    except Exception as exc:row.update(status='FAIL',error=str(exc),traceback=traceback.format_exc())
    (folder/'result.json').write_bytes((json.dumps(row,indent=2)+'\n').encode());return row


def inverter_audit(path,target,counts):
    nf,pf,nm,pm=counts;models=PROFILES[target]['models'];expected={models[0]:nf*nm,models[1]:pf*pm}
    lines=re.sub(r'\n\s*\+',' ',Path(path).read_text(encoding='utf-8')).splitlines()
    units=[line.split() for line in lines if re.match(r'^\s*X\S+\s',line)];observed={model:0 for model in models}
    for unit in units:
        model=unit[5];supply='VGND' if model==models[0] else 'VPWR'
        if model not in observed or unit[2]!='A' or unit[4]!=supply or set((unit[1],unit[3]))!={'Y',supply}:
            raise ValueError('Inverter channel model or terminals differ.')
        params=dict(item.lower().split('=') for item in unit[6:])
        if params['w']!='1u' or params['l']!='0.5u' or params.get('m','1')!='1':
            raise ValueError('Inverter channel dimensions differ.')
        observed[model]+=1
    if observed!=expected or len(units)!=sum(expected.values()):raise ValueError('Inverter native channel count differs.')
    return dict(channels=observed,sha256=file_digest(path))


def inverter(target,counts,out,tools):
    nf,pf,nm,pm=counts;folder=Path(out)/(target+'-inverter-'+'-'.join(map(str,counts)));folder.mkdir()
    row=dict(target=target,counts=counts,status='RUNNING')
    try:
        tech,_=load_technology(target);p=fixture(tech,target,'n',(nf,.5,nf,nm));q=fixture(tech,target,'p',(pf,.5,pf,pm))
        c=p['cells'][0];other=q['cells'][0]['devices'][0];other['name']='M2';c['devices'].append(other)
        c.update(name='finger_inverter',ports=['A','Y','VPWR','VGND'])
        for d in c['devices']:
            supply='VGND' if d['kind']=='NMOS' else 'VPWR';d['nets']=dict(d='Y',g='A',s=supply,b=supply)
        for key in ('shapes','layout_pins','layout_ports','pdk_layouts'):c[key]=[]
        ADAPTERS[target].implementation().generate_inverter(p,c['id']);save_project(p,folder/'original.icproj')
        key='ng' if target=='ihp-sg13g2' else 'nf';nmodel,pmodel=PROFILES[target]['models']
        text=f'.subckt finger_inverter A Y VPWR VGND\nX1 Y A VGND VGND {nmodel} w={nf}u l=.5u {key}={nf} m={nm}\nX2 Y A VPWR VPWR {pmodel} w={pf}u l=.5u {key}={pf} m={pm}\n.ends finger_inverter\n'
        result=run(p,c['id'],folder/'valid',tools,reference(text,'finger_inverter'))
        if result['status']!='passed':raise ValueError(result.get('error','Native inverter failure.'))
        proof=inverter_audit(folder/'valid/lvs-extraction/extracted.spice',target,counts)
        masks={pol:shared_diffusion_audit(folder/'valid/layout.gds',target,pol,size) for pol,size in
               (('n',(nf,.5,nf,nm)),('p',(pf,.5,pf,pm)))}
        wrong=text.replace(f'{key}={nf} m={nm}',f'{key}={nf+1} m={nm}',1)
        result=run(p,c['id'],folder/'wrong-fingers',tools,reference(wrong,'finger_inverter'))
        if result['status']!='passed':raise ValueError('Inspect changed native finger-control behavior.')
        try:inverter_audit(folder/'wrong-fingers/lvs-extraction/extracted.spice',target,(nf+1,pf,nm,pm))
        except ValueError:pass
        else:raise ValueError('Inverter finger fault escaped independent native channel checking.')
        check_pol,fingers,copies,model=('n',nf,nm,nmodel) if nf>1 else ('p',pf,pm,pmodel)
        grouped=text.replace(f'{model} w={fingers}u l=.5u {key}={fingers} m={copies}',f'{model} w=1u l=.5u {key}=1 m={fingers*copies}')
        group_result=run(p,c['id'],folder/'wrong-grouping',tools,reference(grouped,'finger_inverter'))
        if group_result['status']!='passed':raise ValueError('Inspect changed native grouping-control behavior.')
        inverter_audit(folder/'wrong-grouping/lvs-extraction/extracted.spice',target,counts)
        try:shared_diffusion_audit(folder/'wrong-grouping/layout.gds',target,check_pol,(1,.5,1,fingers*copies))
        except ValueError:pass
        else:raise ValueError('Inverter wrong physical grouping escaped exported-mask checking.')
        row.update(status='PASS',native=proof,report_sha256=file_digest(folder/'valid/report.json'),fault_detected=True,
            physical=masks,fault_method='independent_native_channel_count_and_dimensions',fault_native_status=result['status'],fault_report_sha256=file_digest(folder/'wrong-fingers/report.json'),
            grouping_fault_detected=True,grouping_fault_method='independent_exported_diffusion_groups',grouping_fault_native_status=group_result['status'],grouping_fault_report_sha256=file_digest(folder/'wrong-grouping/report.json'))
    except Exception as exc:row.update(status='FAIL',error=str(exc),traceback=traceback.format_exc())
    (folder/'result.json').write_bytes((json.dumps(row,indent=2)+'\n').encode());return row


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('output','magic','netgen'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,5),default=2)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    files=[Path(__file__),ROOT/'scripts/qualify_standard_mos.py',ROOT/'scripts/qualify_mos_parallel_layouts.py',ROOT/'scripts/qualify_standard_mos_layout.py',*sorted((ROOT/'icstudio').rglob('*.py'))]
    hashes={p.relative_to(ROOT).as_posix():file_digest(p) for p in files};(out/'source-files.json').write_bytes((json.dumps(hashes,indent=2)+'\n').encode())
    tools={n:str(getattr(a,n).resolve(strict=True)) for n in ('magic','netgen')}
    record=dict(status='RUNNING',chunk=7,chunk_complete=False,qualified=False,scope=__doc__,pilot=a.pilot,cases=[],inverters=[],source_files_sha256=file_digest(out/'source-files.json'),engines={n:dict(path=p,sha256=file_digest(p)) for n,p in tools.items()})
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs=[pool.submit(execute,t,p,s,out,tools,a.pilot) for t in TARGETS for p in ('n','p') for s in (sizes(t)[:1] if a.pilot else sizes(t))]
        for job in as_completed(jobs):
            row=job.result();record['cases'].append(row);print(row['target'],row['polarity'],row['size'],row['status'],row.get('error',''),flush=True)
            (out/'record.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
        contexts=[pool.submit(inverter,t,counts,out,tools) for t in TARGETS for counts in
                  (((2,3,1,1),) if a.pilot else ((2,3,1,1),(3,2,3,1),(1,8,1,3),(8,1,16,1)))]
        for job in as_completed(contexts):
            row=job.result();record['inverters'].append(row);print(row['target'],'inverter',row['counts'],row['status'],row.get('error',''),flush=True)
            (out/'record.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
    record['source_unchanged']=hashes=={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    record['status']='PASS' if record['source_unchanged'] and len(record['cases'])==len(jobs) and len(record['inverters'])==len(contexts) and all(row['status']=='PASS' for row in record['cases']+record['inverters']) else 'FAIL'
    (out/'record.json').write_bytes((json.dumps(record,indent=2)+'\n').encode());return int(record['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
