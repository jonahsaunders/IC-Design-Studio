"""Finite ordinary-catalog cap_cmim references through actual physical jobs.

Reuse the complete imported 7 um and MIM.g boundary masks. The saved ordinary
catalog device supplies the original simulation X reference; the application,
using the selected extractor, supplies its independently audited physical view.
This is source integration evidence, not family or installed qualification.
"""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
KEY='sg13g2_pr/cap_cmim.sym'
BOUNDARIES=(('below',Decimal('74.98')),('at',Decimal('75')),('above',Decimal('75.02')))
STAGES=('preflight','layout_export','drc','lvs_extraction','lvs','integrity')


def require(condition,message):
    if not condition:raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def sources():
    names={path.relative_to(ROOT).as_posix() for path in (ROOT/'icstudio').glob('*.py')}
    names.update('scripts/'+name for name in ('qualify_standard_mos.py','qualify_ihp_mim_layout.py','ihp_cmim_boundary_audit.py'))
    return {name:sha(ROOT/name) for name in sorted(names)}


def inventory(root):
    result={}
    for folder,dirs,files in os.walk(root,topdown=True,followlinks=False):
        dirs[:]=sorted(name for name in dirs if name!='tmpuxoell2b')
        for name in sorted(files):
            if name=='tmpuxoell2b':continue
            path=Path(folder)/name
            require(not path.is_symlink() and not path.is_junction(),'Linked reference evidence.')
            result[path.relative_to(root).as_posix()]=sha(path)
    return result


def geometry(project,w_um,l_um,*,contacts=True):
    from icstudio.layout import kdb
    from scripts.qualify_ihp_mim_layout import regions
    db=kdb();masks=regions(project);cap=masks.get((36,0),db.Region());pieces=list(cap.each())
    require(len(pieces)==1 and pieces[0].is_box(),'Expected one complete rectangular MIM mask.')
    box=pieces[0].bbox();expected=sorted((int(Decimal(str(w_um))*1000),int(Decimal(str(l_um))*1000)))
    require(sorted((box.width(),box.height()))==expected and cap.area()==expected[0]*expected[1],'Written MIM geometry differs from the selected complete device.')
    cell=project['cells'][0];layers={row['name']:(row['gds'],row['datatype']) for row in project['pdk']['layers']}
    pins=cell.get('layout_ports',[])
    require(len(pins)==2 and {pin['name'] for pin in pins}=={'C1','C2'},'Expected exactly two physical terminals.')
    for pin in pins:
        pair=layers[pin['layer']];require(pair=={'C1':(126,0),'C2':(67,0)}[pin['name']],'Physical electrode mapping differs.')
        require(any(poly.inside(db.Point(*pin['point'])) for poly in masks[pair].each()),'Physical terminal is outside its conductor.')
    cut_area=(masks.get((129,0),db.Region()) & cap).area()
    if contacts:require(cut_area>0,'Missing MIM contact mask.')
    return dict(width_nm=box.width(),height_nm=box.height(),area_nm2=cap.area(),contact_area_nm2=cut_area,ports=pins,
                masks={f'{a}/{b}':dict(area_nm2=region.area(),components=len(list(region.each()))) for (a,b),region in sorted(masks.items())})


def catalog_project(layout,technology,w_um,l_um):
    from icstudio.catalog import create_device
    from icstudio.model import clone,load_project,validate
    from scripts.qualify_ihp_mim_layout import regions
    project=load_project(layout);before=regions(project);old=project['pdk']
    require(old['package_lock']==technology['package_lock'],'Reused mask package identity differs from the current locked model package.')
    project['pdk']=clone(technology);require(len(project['cells'])==1,'Use the retained one-cell capacitor layout.')
    cell=project['cells'][0];require(cell['name']=='coupon' and cell['ports']==['C1','C2'],'Retained physical interface differs.')
    device=create_device(technology,KEY,'C1');device['nets']={'c0':'C1','c1':'C2'};device['net_labels']=dict(device['nets'])
    device['model_params'].update(w=str(Decimal(str(w_um))*Decimal('1e-6')),l=str(Decimal(str(l_um))*Decimal('1e-6')),m=1,mm_ok=1)
    require('native_spice' not in device,'A fresh ordinary catalog device must not contain imported physical tokens.')
    cell.update(devices=[device],wires=[],junctions=[]);validate(project)
    after=regions(project);require(set(before)==set(after) and all((before[key]^after[key]).is_empty() for key in before),'Attaching the actual catalog reference changed a mask.')
    return project,dict(layout=str(Path(layout).resolve()),layout_sha256=sha(layout),old_package_root=old['package_root'],
        selected_package_root=technology['package_root'],masks_unchanged=True,catalog_device=device)


def projection_proof(report,technology,original,comparison,extractor):
    from icstudio.native_spice import lvs_defaults
    symbol='libs.tech/xschem/sg13g2_pr/cap_cmim.sym';model='libs.tech/ngspice/models/capacitors_mod.lib'
    records=[row for row in report.get('reference_defaults',[]) if row.get('proof',{}).get('source')==symbol]
    require(len(records)==1,'Missing or duplicated actual source-bound capacitor projection receipt.')
    record=records[0];proof=record['proof'];instance=next(line.split()[0] for line in original.splitlines() if re.match(r'^X\S+\s',line))
    require(record['instance']==instance and record['physical_instance']==(instance if extractor=='magic' else 'C'+instance) and
            record.get('changed') is True,'The actual original-instance projection receipt differs.')
    require(proof['sha256']==technology['package_lock']['files'][symbol]==sha(Path(technology['package_root'])/symbol) and
            proof['model_source']==model and proof['model_sha256']==technology['package_lock']['files'][model]==sha(Path(technology['package_root'])/model),
            'Projection symbol/model identity differs from the locked original sources.')
    if extractor=='ihp-klayout':
        require(proof['geometry_reader']=='rule_decks/custom_reader.lvs' and
                proof['geometry_reader_sha256']==sha(ROOT/'icstudio/assets/physical/ihp_klayout_lvs'/proof['geometry_reader']),
                'Projection geometry-reader identity differs.')
    else:require('geometry_reader' not in proof,'Magic must not depend on an unstaged KLayout reader.')
    unchanged,checked=lvs_defaults(comparison,technology,lvs_extractor=extractor)
    require(unchanged==comparison and len(checked)==1 and checked[0].get('changed') is False and checked[0]['proof']==proof,
            'Canonical physical reference was not idempotently source-validated.')
    return dict(projection=record,idempotent_validation=checked[0],canonical_bytes_unchanged=True)


def magic_netlist(text,w_um,l_um):
    from scripts.ihp_cmim_boundary_audit import scalar
    lines=[line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(lines)==3 and [part.lower() for part in lines[0].split()[:2]]==['.subckt','coupon'] and set(lines[0].split()[2:])=={'C1','C2'} and
            lines[-1].lower() in ('.ends','.ends coupon'),'Magic capacitor interface differs.')
    row=lines[1].split();require(row[0].upper().startswith('X') and row[1:4]==['C1','C2','cap_cmim'],'Magic must retain one ordered extracted X capacitor.')
    parameters={}
    for part in row[4:]:
        require(part.count('=')==1,'Malformed Magic capacitor property.')
        key,value=part.split('=');require(key.lower() not in parameters,'Duplicate Magic capacitor property.');parameters[key.lower()]=scalar(value)
    require({'w','l'}<=set(parameters)<= {'w','l','m'},'Magic capacitor property set differs.')
    require(sorted((parameters['w'],parameters['l']))==sorted((Decimal(str(w_um))*Decimal('1e-6'),Decimal(str(l_um))*Decimal('1e-6'))) and
            parameters.get('m',1)==1,'Magic extracted dimensions or unit multiplicity differs.')
    return dict(model='cap_cmim',prefix='X',ordered_terminals=['C1','C2'],parameters={key:str(value) for key,value in parameters.items()},
                scope='Magic reports per-unit W/L; no A/P output is invented.')


def open_or_short(folder,kind):
    """Require the actual completed raw extractor's specific physical defect."""
    from scripts.ihp_cmim_boundary_audit import scalar
    root=folder/'job/physical-flow/lvs-extraction';native=root/'native.cir';text=native.read_text()
    log=(root/'console.log').read_text()
    require('LVS Total Run time ' in log and 'NET_ONLY enabled: apply extraction netlist options and skip comparison.' in log,
            'The physical fault lacks healthy, unfiltered native extraction completion.')
    lines=[line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(lines)==3 and lines[0].split()[:2]==['.SUBCKT','coupon'] and lines[-1].upper()=='.ENDS COUPON','Unexpected raw faulty circuit closure.')
    row=lines[1].split();require(len(row)==9 and row[0].startswith('C') and row[3]=='cap_cmim','Expected one raw extracted capacitor in the fault control.')
    values={}
    for part in row[4:]:
        key,value=part.split('=');require(key.lower() not in values,'Duplicate raw faulty device property.');values[key.lower()]=scalar(value)
    require(set(values)=={'w','l','a','p','m'} and sorted((values['w'],values['l']))==[Decimal('74.98e-6'),Decimal('75e-6')] and
            values['a']==Decimal('5623.5e-12') and values['p']==Decimal('299.96e-6') and values['m']==1,'A faulty native device changed unrelated geometry/model properties.')
    pins=lines[0].split()[2:]
    if kind=='missing-contacts':
        require(pins==['C2'] and row[2]=='C2' and row[1] not in ('C1','C2') and row[1]!=row[2],
                'The contact control did not expose the missing physical top terminal in raw extraction.')
    else:
        require(pins==['C1|C2'] and row[1]==row[2]=='C1|C2','The short control did not merge the two physical electrodes in raw extraction.')
    return dict(kind=kind,raw_ports=pins,raw_device_nodes=row[1:3],native_sha256=sha(native),console_sha256=sha(root/'console.log'),
                raw_geometry_preserved=True,native_completion=True)


def physical(project,folder,tools,w_um,l_um,*,extractor='ihp-klayout',baseline=False,audit_order=True):
    from icstudio.catalog_migration import emit
    from icstudio.interchange import spice,export_layout
    from icstudio.model import digest,save_project,load_project
    from icstudio.testbenches import native_subcircuit
    from icstudio.layout_verification import reference
    from icstudio.silicon_flow import job
    from icstudio.stream_contract import compare
    from scripts.ihp_cmim_boundary_audit import circuit
    folder.mkdir(parents=True,exist_ok=False);save_project(project,folder/'catalog.icproj');saved=load_project(folder/'catalog.icproj')
    require(digest(project)==digest(saved),'Catalog save/reopen changed the selected project.')
    device=saved['cells'][0]['devices'][0];sim=emit(device,saved['pdk'],'simulation');lvs=emit(device,saved['pdk'],'lvs')
    require(sim.startswith('X') and ' mm_ok=1' in sim,'The original ordinary simulation X statement or statistical selector differs.')
    original=spice(saved,saved['top'],hierarchical=False);(folder/'simulation-before.spice').write_bytes(original.encode())
    (folder/'catalog-simulation.txt').write_bytes((sim+'\n').encode());(folder/'catalog-requested-lvs.txt').write_bytes((lvs+'\n').encode())
    raw=native_subcircuit(saved,saved['top']);require(sim in raw,'The actual application reference did not preserve the saved catalog simulation statement.')
    selected=reference(raw,'coupon');(folder/'captured-reference.spice').write_bytes(raw.encode())
    export_layout(saved,folder/'selected.oas')
    settings=dict(type='silicon',verification_mode='drc_lvs',tools=tools,reference=selected,lvs_extractor=extractor,
                  drc_engine='ihp-public' if extractor=='ihp-klayout' else 'magic')
    result=job(saved,saved['top'],settings,folder/'job',lambda *_:None);write(folder/'result.json',result)
    report=result['silicon_report'];root=folder/'job/physical-flow'
    require((root/'schematic.spice').read_bytes()==raw.encode(),'The job substituted the captured original schematic reference.')
    require(spice(saved,saved['top'],hierarchical=False)==original and emit(device,saved['pdk'],'simulation')==sim,'Physical projection changed simulation bytes.')
    comparison=(root/'schematic-lvs.spice').read_text();stages={row['name']:row['status'] for row in report['stages']}
    row=dict(status=report['status'],stages=stages,error=report.get('error'),drc_count=report.get('drc_count'),
        report_sha256=sha(root/'report.json'),result_sha256=sha(folder/'result.json'),catalog_project_sha256=sha(folder/'catalog.icproj'),
        original_simulation=sim,requested_lvs=lvs,comparison=comparison,reference_defaults=report.get('reference_defaults',[]),
        original_reference_sha256=sha(root/'schematic.spice'),physical_reference_sha256=sha(root/'schematic-lvs.spice'),
        simulation_bytes_unchanged=True,coverage=report.get('drc_coverage'),
        exchange=compare(root/'original.gds',folder/'selected.oas',text_presentation=False))
    if not baseline:
        row['source_projection']=projection_proof(report,saved['pdk'],raw,comparison,extractor)
        require('mm_ok' not in comparison.lower(),'The statistical selector leaked into physical comparison.')
        if extractor=='magic':require(sim.split()[0] in comparison and not re.search(r'(?im)^C\S+\s',comparison),'The ordinary Magic reference changed representation.')
        if extractor=='magic':
            row['independent_magic_netlist']=magic_netlist((root/'lvs-extraction/extracted.spice').read_text(),w_um,l_um)
    if extractor=='ihp-klayout':
        from icstudio.ihp_klayout_drc import read_report
        row['decks']={}
        for name in ('main','maximal'):
            path=root/'drc'/name/'findings.lyrdb';native=read_report(path);categories={}
            for finding in native['findings']:categories[finding['rule']]=categories.get(finding['rule'],0)+1
            row['decks'][name]=dict(count=native['count'],categories=categories,sha256=sha(path))
        if not baseline:
            row['independent_netlists']={}
            for kind,path in (('native','lvs-extraction/native.cir'),('extracted','lvs-extraction/extracted.spice'),('reference','schematic-lvs.spice')):
                if not (root/path).is_file():continue
                try:row['independent_netlists'][kind]=circuit((root/path).read_text(),l_um,w_um)
                except ValueError as error:
                    if audit_order:raise
                    row['independent_netlists'][kind]=dict(rejected=True,error=str(error))
    write(folder/'observation.json',row);return row,result,saved


def bad_reference(project,folder,tools,kind):
    from icstudio.testbenches import native_subcircuit
    from icstudio.native_spice import lvs_defaults
    from icstudio.layout_verification import reference
    from icstudio.silicon_flow import job
    folder.mkdir();original=native_subcircuit(project,project['top']);changed=original
    if kind=='unknown-property':changed=original.replace('mm_ok=1','mm_ok=1 unknown_cmim_property=1')
    elif kind=='duplicate-selector':changed=original.replace('mm_ok=1','mm_ok=1 mm_ok=0')
    elif kind=='contradictory-area':
        changed,_=lvs_defaults(original,project['pdk'],lvs_extractor='ihp-klayout')
        changed,count=re.subn(r'(?i)\bA=\S+','A=0',changed);require(count==1,'Missing derived area for the deliberate contradiction.')
    else:raise ValueError('Unknown reference control.')
    require(changed!=original,'The intended reference corruption was not applied.')
    selected=reference(changed,'coupon');(folder/'original.spice').write_bytes(original.encode());(folder/'corrupted.spice').write_bytes(changed.encode())
    settings=dict(type='silicon',verification_mode='drc_lvs',reference=selected,tools=tools,lvs_extractor='ihp-klayout',drc_engine='ihp-public')
    result=job(project,project['top'],settings,folder/'job',lambda *_:None);write(folder/'result.json',result)
    native=result['silicon_report'];require(native['status']=='blocked' and native['stages'][0]['name']=='preflight' and native['stages'][0]['status']=='failed' and
        all(row['status']=='not_run' for row in native['stages'][1:]),'Malformed reference reached native layout verification.')
    expected='contradicts dimensions' if kind=='contradictory-area' else 'Unsupported or duplicated'
    require(expected in native.get('error',''),'The malformed reference failed for an unrelated reason.')
    return dict(control=kind,detected=True,detector='actual application preflight',native_status=native['status'],error=native['error'],
                result_sha256=sha(folder/'result.json'),original_reference_sha256=sha(folder/'original.spice'),corrupted_reference_sha256=sha(folder/'corrupted.spice'))


def display(project,result,folder):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import digest,design_digest
    errors=[]
    def exception(kind,error,tb):errors.append(str(error));traceback.print_exception(kind,error,tb)
    previous=sys.excepthook;sys.excepthook=exception
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    window=Studio(recover=False);window.error=lambda error:errors.append(str(error));window.show()
    try:
        window.set_project(project,folder/'catalog.icproj');window.cid=project['top'];window.mode_combo.setCurrentIndex(1)
        window.refresh(True);window.setMinimumSize(1640,1080);window.resize(1640,1080);app.processEvents()
        require(design_digest(window.project)==result['design_hash'],'The displayed ordinary catalog project differs from its actual physical job.')
        window.add_result(result);window.open_silicon();QTest.qWait(100)
        require(design_digest(window.project)==result['design_hash'] and 'STALE' not in window.silicon_status.text() and not errors,
                'The actual ordinary-catalog result view is stale or reports a UI error.')
        require('MIM.g' in window.silicon_status.text() and 'executed' in window.silicon_status.text(),'The selected public rule execution is missing from the result view.')
        image=folder/'actual-catalog-desktop.png';require(window.grab().save(str(image)),'Could not retain the actual catalog result view.')
        return dict(status=window.silicon_status.text(),current_design_sha256=design_digest(window.project),result_design_sha256=result['design_hash'],
                    rows=[[window.silicon_table.item(i,j).text() for j in range(3)] for i in range(window.silicon_table.rowCount())],
                    screenshot_sha256=sha(image),window_size=[window.width(),window.height()],errors=errors)
    finally:
        window.saved_hash=digest(window.project);window.close();app.processEvents();sys.excepthook=previous


def main():
    global ROOT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=ROOT)
    parser.add_argument('--default-layout',type=Path,required=True)
    parser.add_argument('--boundary-root',type=Path)
    parser.add_argument('--layout-manifest',type=Path,help='Caller-bound absolute saved-layout file hashes and retained provenance records; required for repaired acceptance.')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--baseline',action='store_true',help='Observe the prior source default X reference through both native routes; never a repaired acceptance pass.')
    parser.add_argument('--gui',action='store_true',help='Also display the genuine default ordinary-catalog public result; use a readable Qt screen configuration.')
    for name in ('magic','netgen','klayout'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();ROOT=args.source_root.resolve();sys.path.insert(0,str(ROOT))
    from scripts.qualify_standard_mos import load_technology
    from scripts.qualify_ihp_mim_layout import rotate
    from icstudio.model import save_project
    out=args.out.resolve();require(not out.exists(),'Fresh qualification output required.');out.mkdir(parents=True)
    before=sources();runner=sha(__file__);write(out/'source-files.json',before)
    tools={name:str(Path(getattr(args,name)).resolve(strict=True)) for name in ('magic','netgen','klayout')}
    tools_before={name:sha(path) for name,path in tools.items()}
    report=dict(schema=1,status='RUNNING',scope=__doc__,baseline=args.baseline,qualified=False,installed_acceptance=False,chunk_complete=False,
        source_root=str(ROOT),source_files_sha256=sha(out/'source-files.json'),runner_sha256=runner,tools=tools,tool_sha256=tools_before,cases=[],faults=[])
    write(out/'report.json',report)
    try:
        layout_manifest=None
        if not args.baseline:
            require(args.layout_manifest is not None,'Retained complete-layout input identities are required.')
            layout_manifest=json.loads(args.layout_manifest.read_bytes())
            require(layout_manifest.get('schema')==1 and bool(layout_manifest.get('files')) and bool(layout_manifest.get('provenance')),'Incomplete retained-layout input manifest.')
            for name,value in layout_manifest['files'].items():
                path=Path(name);require(path.is_absolute() and 'tmpuxoell2b' not in path.parts,'Unsafe retained-layout manifest path.')
                require(sha(path)==value,'Reused complete-layout input differs from its captured identity.')
            provenance=[item for item in layout_manifest['provenance'].values() if isinstance(item,dict) and 'path' in item and 'sha256' in item]
            require(len(provenance)>=2,'Both original complete-boundary and default-layout inventories are required.')
            inventories=[]
            for item in provenance:
                require('tmpuxoell2b' not in Path(item['path']).parts and sha(item['path'])==item['sha256'],'Retained complete-layout provenance record differs.')
                inventories.append(json.loads(Path(item['path']).read_bytes()))
            for name,value in layout_manifest['files'].items():
                path=Path(name);matches=[]
                for prior in inventories:
                    if 'root' in prior and path.is_relative_to(Path(prior['root'])):
                        matches.append(prior['files'].get(path.relative_to(prior['root']).as_posix()))
                    else:matches.extend(row.get('sha256') for row in prior.values() if isinstance(row,dict) and row.get('resolved')==name)
                require(value in matches,'Selected geometry is absent from its original retained complete-device inventory.')
            report['retained_layout_manifest']=dict(path=str(args.layout_manifest.resolve()),sha256=sha(args.layout_manifest),record=layout_manifest)
        tech,package=load_technology('ihp-sg13g2');report['package']=package
        if layout_manifest:require(str(args.default_layout.resolve()) in layout_manifest['files'],'Default geometry is not in the captured complete-layout inventory.')
        default,binding=catalog_project(args.default_layout,tech,7,7);report['default_layout']=binding
        row,_,_=physical(default,out/'default-7-magic',tools,7,7,extractor='magic',baseline=args.baseline)
        row.update(case='default-7',rotation=0,extractor='magic');report['cases'].append(row);write(out/'report.json',report)
        selection=[('default-7',default,Decimal(7),Decimal(7),angle) for angle in ((0,) if args.baseline else (0,90))]
        if not args.baseline:
            require(args.boundary_root is not None,'Complete retained boundary input is required.')
            for name,length in BOUNDARIES:
                for angle in (0,90):
                    source=args.boundary_root/(name+'-'+str(angle))/'input.icproj'
                    require(str(source.resolve()) in layout_manifest['files'],'Boundary geometry is not in the captured complete-layout inventory.')
                    project,origin=catalog_project(source,tech,75,length)
                    selection.append((name,project,Decimal(75),length,angle))
        for name,project,w,l,angle in selection:
            selected=rotate(project) if name=='default-7' and angle else project
            folder=out/(name+'-'+str(angle));measured=geometry(selected,w,l)
            row,result,saved=physical(selected,folder,tools,w,l,baseline=args.baseline)
            if args.gui and not args.baseline and name=='default-7' and angle==0:row['actual_catalog_gui']=display(saved,result,folder)
            row.update(case=name,rotation=angle,extractor='ihp-klayout',geometry=measured);report['cases'].append(row);write(out/'report.json',report)
        if args.baseline:
            public=report['cases'][-1]
            require(public['stages']['lvs']=='failed' and public['drc_count']==0 and
                all(public['stages'][name]=='passed' for name in STAGES if name!='lvs'),'The baseline did not isolate the expected ordinary-reference LVS failure.')
            report['status']='OBSERVED_PRE_REPAIR_REFERENCE_FAILURE'
        else:
            for row in report['cases']:
                expected_bad=row['case']=='above'
                require(row['stages']['lvs']=='passed' and all(row['stages'][name]=='passed' for name in STAGES if name!='drc'),'Native source reference did not reach strict matching LVS.')
                require(row['stages']['drc']==('failed' if expected_bad else 'passed'),'Unexpected retained physical-rule outcome.')
                if expected_bad:require(row['decks']['main']['count']==0 and row['decks']['maximal']['categories']=={"'MIM.g'":1},'Above-limit geometry must fail only the actual maximum-area rule.')
                require(row['coverage']['MIM.g']['status']==('NOT_CHECKED' if row['extractor']=='magic' else 'EXECUTED'),'Selected-checker rule coverage differs.')
            for name in ('wrong-width','missing-contacts','plate-short','swapped-reference'):
                source=args.boundary_root/(('below-0' if name=='swapped-reference' else 'fault-'+name))/'input.icproj'
                require(str(source.resolve()) in layout_manifest['files'],'Fault geometry is not in the captured complete-layout inventory.')
                project,binding=catalog_project(source,tech,75,Decimal('74.98'))
                if name=='swapped-reference':
                    device=project['cells'][0]['devices'][0];device['nets']={'c0':'C2','c1':'C1'};device['net_labels']=dict(device['nets'])
                measured=geometry(project,73 if name=='wrong-width' else 75,Decimal('74.98'),contacts=name!='missing-contacts')
                folder=out/('fault-'+name);row,_,_=physical(project,folder,tools,75,Decimal('74.98'),audit_order=False)
                row.update(fault=name,geometry=measured,layout_binding=binding)
                if name=='wrong-width':
                    require(row['drc_count']==0 and row['stages']['lvs_extraction']=='passed' and row['stages']['lvs']=='failed','Complete width control did not isolate strict native property LVS.')
                    require(row['independent_netlists'].get('native',{}).get('rejected') is True,'Independent written-native dimensions missed the width fault.')
                    log=(folder/'job/physical-flow/lvs/lvs.log').read_text()
                    require('Final result:' in log and 'Property errors' in log,'The width control lacks completed native property-error comparison.')
                    row['detector']='strict native property LVS and independent written geometry'
                elif name=='swapped-reference':
                    require(row['independent_netlists'].get('reference',{}).get('rejected') is True,'Independent ordered-electrode check missed the swapped reference.')
                    require(row['drc_count']==0 and row['stages']['lvs']=='failed' and all(row['stages'][stage]=='passed' for stage in STAGES if stage!='lvs'),
                            'The swapped reference did not isolate strict native top-level pin matching.')
                    log=(folder/'job/physical-flow/lvs/lvs.log').read_text()
                    require('Final result: Top level cell failed pin matching.' in log and '**Mismatch**' in log,'The swapped reference lacks genuine native pin-mismatch diagnostics.')
                    row['detector']='strict native top-level pin matching and independent ordered-electrode audit'
                else:
                    require(row['stages']['preflight']==row['stages']['layout_export']=='passed' and row['stages']['lvs_extraction']=='failed' and
                            'IHP extracted port names differ from the schematic.' in row.get('error',''),'The physical fault did not fail for the expected native interface cause.')
                    row['raw_semantic_failure']=open_or_short(folder,name)
                    row['detector']='completed unfiltered native extraction: missing top port' if name=='missing-contacts' else 'completed unfiltered native extraction: merged physical electrode net'
                row['detected']=True;report['faults'].append(row);write(out/'report.json',report)
            report['preflight_controls']=[bad_reference(default,out/('bad-'+kind),tools,kind) for kind in
                ('unknown-property','duplicate-selector','contradictory-area')]
            report['status']='PASS_SOURCE_ORDINARY_REFERENCE'
        require(sources()==before and sha(__file__)==runner and {name:sha(path) for name,path in tools.items()}==tools_before,'Source, runner or tool changed during qualification.')
        if layout_manifest:
            require(sha(args.layout_manifest)==report['retained_layout_manifest']['sha256'] and
                    all(sha(name)==value for name,value in layout_manifest['files'].items()) and
                    all(sha(item['path'])==item['sha256'] for item in provenance),'Retained complete-layout identities changed during reference qualification.')
        report['sources_and_tools_unchanged']=True
    except BaseException as error:
        report.update(status='FAIL',error=repr(error),traceback=traceback.format_exc());raise
    finally:
        write(out/'report.json',report);write(out/'files.json',inventory(out))
    print(json.dumps(dict(status=report['status'],cases=len(report['cases']),baseline=args.baseline),indent=2))


if __name__=='__main__':main()
