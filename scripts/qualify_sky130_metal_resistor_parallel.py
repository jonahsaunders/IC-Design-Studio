"""Finite app-generated LI/M1--M4 parallel arrays and actual-array DC/AC.

The application exports the positive circuit and complete physical array. No
synthetic expanded reference replaces either input. This is source integration,
not installed acceptance, calibrated matching or full device qualification.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.catalog import create_device,link_technology
from icstudio.interchange import export_layout
from icstudio.layout import rect,shape_from_polygon
from icstudio.layout_eco import regenerate
from icstudio.layout_import import read_layout
from icstudio.layout_verification import run as native_run,reference as captured_reference
from icstudio.model import clone,example,save_project,load_project
from icstudio.pdks import model_lines,stage_model_deck
from icstudio.physical import connectivity
from icstudio.physical_cells import assign_port,ports,transform_selection
from icstudio.sky130_devices import install
from icstudio.sky130_metal_resistors import layers
from icstudio.stream_contract import compare
from icstudio.testbenches import native_subcircuit
from scripts import installed_mim_inputs as identity
from scripts import sky130_li_resume as physical_identity
from scripts import qualify_sky130_metal_resistors_linked as linked
from scripts.qualification_geometry import regions,same_masks
from scripts.qualify_standard_mos_layout import technology

HISTORICAL_CONTRACT='docs/qualification/sky130-metal-resistor-parallel-v1.json'
HISTORICAL_CONTRACT_SHA='66b905bcde6cc53fd94a5408fd5ae76f71387ae41d8c7a0c5357961c6bc64472'
from scripts import sky130_contract_versions as versions
CURRENT_CONTRACT=versions.selected('parallel')
CONTRACT,CONTRACT_SHA=CURRENT_CONTRACT['path'],CURRENT_CONTRACT['sha256']
sha,write,require=identity.sha,identity.write,identity.require


def contract():
    require(sha(ROOT/CONTRACT)==CONTRACT_SHA,'Review a changed array acceptance contract.')
    spec=json.loads((ROOT/CONTRACT).read_bytes())
    for name,value in spec['sources'].items():
        require(sha(ROOT/name)==value['sha256'],'Changed public reference: '+name)
    return spec


def selection(spec,pilot=False):
    result=[];models=spec['pilot']['models'] if pilot else list(spec['models'])
    dimensions=[(2,5,spec['pilot']['multiplicities'] if pilot else range(1,17))]
    if not pilot: dimensions += [(w,l,(2,3,16)) for w,l in spec['physical']['boundary_dimensions_um']]
    for model in models:
        for w,l,counts in dimensions:
            for count in counts:
                result.append(dict(name=f'{model}-w{w:g}-l{l:g}-m{count}',model=model,
                    width_um=w,length_um=l,multiplicity=count))
    return result


def coefficients(spec):
    result={}
    for model,p in spec['models'].items():
        layer='li' if model=='l1' else model
        result.update({'r'+model:p['rsh'],'tol_'+layer:p['tol'],layer+'_dw':p['dw'],
                       'tc1r'+model:p['tc1'],'tc2r'+model:p['tc2']})
    result.update(mc_mm_switch=0.,mc_pr_switch=0.)
    return result


def resistance(spec,row):
    p=spec['models'][row['model']];delta=-3
    return p['rsh']*row['length_um']*1e-6/(row['width_um']*1e-6+p['tol']+p['dw'])*(1+p['tc1']*delta+p['tc2']*delta**2)/row['multiplicity']


def editor_project(tech,row):
    p=example('empty');p['pdk']=clone(tech);c=p['cells'][0];c['name']='coupon';c['ports']=['R1','R2']
    key='li' if row['model']=='l1' else row['model']
    d=create_device(tech,'sky130_fd_pr/res_generic_'+key+'.sym','RES')
    d['nets']={'m':'R1','p':'R2'};d['model_params'].update(w=2,l=5,mult=1);c['devices']=[d]
    install(p,c['id'],d['id']);pins={v['pin']:v['id'] for v in c['layout_pins']}
    d['model_params'].update(w=row['width_um'],l=row['length_um'],mult=row['multiplicity'])
    regenerate(p,c['id'],d['id'])
    require(pins=={v['pin']:v['id'] for v in c['layout_pins']},'Array regeneration changed first-unit pin IDs.')
    for pin in c['layout_pins']: assign_port(p,c['id'],d['nets'][pin['pin']],pin['layer'],pin['point'])
    require(not connectivity(p,c['id'])['issues'],'Editor array has incorrect terminal topology.')
    return p


def application_reference(p,row):
    text=native_subcircuit(p,p['top']);devices=[line.split() for line in text.splitlines() if line.startswith('R_')]
    require(len(devices)==1 and devices[0][1:4]==['R1','R2','sky130_fd_pr__res_generic_'+row['model']], 'Actual app reference model/ports differ.')
    require(dict(v.split('=',1) for v in devices[0][4:])==dict(w=f'{row["width_um"]:g}',l=f'{row["length_um"]:g}',m=str(row['multiplicity'])), 'Actual app reference count/dimensions differ.')
    return text


def native_rows(path):
    text=path.read_text();header=re.findall(r'(?im)^\.subckt\s+(\S+)\s+([^\n]+)',text)
    require(len(header)==1 and header[0][0]=='coupon','Wrong native array top.')
    rows=[]
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(('*','.')):continue
        fields=line.split();require(len(fields)>=6 and re.fullmatch(r'R\S+',fields[0],re.I),'Unexpected native primitive.')
        params=dict(v.split('=',1) for v in fields[4:]);require(set(params)<= {'w','l','m'} and {'w','l'}<=set(params),'Unexpected native parameters.')
        require(float(params.get('m',1))==1,'Merged native multiplicity is not proof of physical units.')
        rows.append(dict(name=fields[0],terminals=fields[1:3],model=fields[3],width_um=float(params['w']),length_um=float(params['l'])))
    require(len({r['name'].lower() for r in rows})==len(rows),'Duplicate native instance names.')
    return header[0][1].split(),rows


def check_native(path,row,*,count=None,widths=None,floating=False):
    header,values=native_rows(path);count=row['multiplicity'] if count is None else count
    require(header==['R1','R2'] and len(values)==count,'Incorrect native array interface/count.')
    expected=sorted(widths or [row['width_um']]*count)
    require(sorted(r['width_um'] for r in values)==expected and all(r['length_um']==row['length_um'] and r['model']=='sky130_fd_pr__res_generic_'+row['model'] for r in values),'Incorrect native unit model/dimensions.')
    connected=sum(set(r['terminals'])=={'R1','R2'} for r in values)
    require(connected==(count-1 if floating else count),'Incorrect native parallel graph.')
    if floating:
        other=next(r for r in values if set(r['terminals'])!={'R1','R2'})
        require(len(set(other['terminals'])&{'R1','R2'})==1,'Broken branch must have exactly one floating unit terminal.')
    return dict(sha256=sha(path),units=values)


def transfer(p,physical_tech,folder):
    import klayout.db as db
    save_project(p,folder/'editor.icproj');reopened=load_project(folder/'editor.icproj')
    require(reopened['cells']==p['cells'],'Save/reopen changed the array.')
    export_layout(reopened,folder/'editor.gds');export_layout(reopened,folder/'editor.oas')
    stream=db.Layout();stream.read(str(folder/'editor.oas'));stream.write(str(folder/'external.oas'))
    def imported_stream(source,target):
        imported,_=read_layout(folder/source);same_masks(reopened,imported)
        link_technology(imported,physical_tech);imported['cells'][0]['ports']=['R1','R2']
        labels=ports(imported,imported['top']);require(len(labels)==2 and {v['name'] for v in labels}=={'R1','R2'},'Array stream port labels differ.')
        original_texts=clone(imported['cells'][0]['layout_texts'])
        for label in labels:assign_port(imported,imported['top'],label['name'],label['layer'],label['point'])
        # Port assignment adds electrical metadata and deliberately resets label
        # presentation. This transfer retains the exact imported text records.
        imported['cells'][0]['layout_texts']=original_texts
        same_masks(reopened,imported);export_layout(imported,folder/target);return imported
    imported=imported_stream('editor.gds','gds-reimported.gds')
    imported_stream('external.oas','reimported.gds')
    # OASIS does not represent GDS text presentation. Strict GDS preservation is
    # checked on its own roundtrip; all formats retain actual labels and masks.
    write(folder/'exchange.json',dict(gds=compare(folder/'editor.gds',folder/'gds-reimported.gds'),
        oasis=compare(folder/'external.oas',folder/'reimported.gds',text_presentation=False),
        cross_format=compare(folder/'editor.gds',folder/'reimported.gds',text_presentation=False)))
    return imported


def fault_project(p,row,fault):
    import klayout.db as db
    q=clone(p);c=q['cells'][0];ls=layers(q['pdk'],row['model']);w=round(row['width_um']*1000);l=round(row['length_um']*1000)
    count=row['multiplicity'];pitch=w+3000;last=(count-1)*pitch;cx=5*(w//10)
    # Only conductor/marker polygons change. Port labels/locations are intact.
    masks=regions(q);layer_number={'l1':67,'m1':68,'m2':69,'m3':70,'m4':71}[row['model']]
    conductor=masks[(layer_number,20)];marker=masks[(layer_number,13)]
    buses=db.Region(db.Box(cx-200,-450,last+cx+200,-50))+db.Region(db.Box(cx-200,l+50,last+cx+200,l+450))
    unit=db.Region(db.Box(last,-500,last+w,l+500));body=db.Region(db.Box(last,0,last+w,l))
    if fault=='missing-unit':conductor=conductor-(unit-buses);marker=marker-body
    elif fault=='broken-branch':conductor=conductor-db.Region(db.Box(last,-30,last+w,-20))
    elif fault=='bus-short':
        for box in [db.Box(-1200,-450,cx+200,-50),db.Box(-1200,-450,-800,l+450),db.Box(-1200,l+50,cx+200,l+450)]:conductor+=db.Region(box)
    elif fault=='one-unit-width':
        conductor+=db.Region(db.Box(last+w,-500,last+3000,l+500));marker+=db.Region(db.Box(last+w,0,last+3000,l))
    else:raise ValueError('Unknown native geometry fault.')
    c['shapes']=[s for s in c['shapes'] if s['layer'] not in (ls['conductor'],ls['marker'])]
    for name,value in ((ls['conductor'],conductor),(ls['marker'],marker)):
        c['shapes'] += [shape_from_polygon(poly,name) for poly in value.merged().each()]
    return q


def netgen_mismatch(log,model,fault):
    require('sky130_fd_pr__res_generic_'+model in log,'Fault LVS log lacks the actual resistor model.')
    if fault in ('missing-unit','reference-count','one-unit-width'):
        # Netgen reduces these parallel units to their summed width. Physical
        # unit count/dimensions are checked independently before that reduction.
        expected=[6.,7.] if fault=='one-unit-width' else [4.,6.]
        pairs=re.findall(r'^[ \t]+w circuit1: (\S+)[ \t]+circuit2: (\S+)[ \t]+\(delta=.*\)$',log,re.M)
        require('property errors' in log.lower() and any(sorted(map(float,p))==expected for p in pairs),'Wrong or missing reduced-array property mismatch.')
    else:
        require('Circuits match uniquely.' not in log and re.search(r'do not match|disconnected node|no matching pin|failed pin matching',log,re.I),'Missing native broken-branch topology rejection.')


def check_fault(folder,result,row,fault):
    stages={v['name']:v for v in result['stages']};path=folder/'lvs-extraction/extracted.spice'
    require(result['status']=='failed' and stages['preflight']['status']=='passed' and stages['layout_export']['status']=='passed','Fault did not reach native checks.')
    if fault=='bus-short':
        header,values=native_rows(path)
        require(len(header)==1 and header[0] in ('R1','R2'),'Bus short did not collapse the native terminal interface.')
        require(len(values)==3 and len({n for v in values for n in v['terminals']})==1 and all(v['model']=='sky130_fd_pr__res_generic_'+row['model'] and v['width_um']==2 and v['length_um']==5 for v in values),'Bus-short extraction must preserve three unchanged units on one common net.')
        require(stages['lvs_extraction']['status']=='failed' and 'Extracted port order differs from the schematic:' in stages['lvs_extraction'].get('error',''),'Bus short failed for an unrelated reason.')
        require(stages['lvs']['status']=='not_run' and stages['integrity']['status']=='not_run','Bus short did not stop at interface validation.')
        evidence=dict(native_header=header,native_units=values)
    else:
        require(stages['lvs_extraction']['status']=='passed' and stages['lvs']['status']=='failed' and stages['integrity']['status']=='passed','Fault did not reach a complete native LVS rejection.')
        if fault=='missing-unit': evidence=check_native(path,row,count=row['multiplicity']-1)
        elif fault=='broken-branch':evidence=check_native(path,row,floating=True)
        elif fault=='one-unit-width':evidence=check_native(path,row,widths=[2,2,3])
        else:evidence=check_native(path,row)
        require((result['drc_count']>0) if fault=='broken-branch' else result['drc_count']==0,'Unexpected fault DRC outcome.')
        netgen_mismatch((folder/'lvs/lvs.log').read_text(),row['model'],fault)
    return dict(name=fault,detected=True,drc_count=result['drc_count'],report_sha256=sha(folder/'report.json'),native=evidence)


def physical_case(simtech,phystech,row,out,tools):
    folder=out/row['name'];folder.mkdir();record={**row,'status':'RUNNING','layouts':[],'faults':[]}
    try:
        base=editor_project(simtech,row)
        for angle in (0,90):
            p=clone(base);c=p['cells'][0]
            if angle:transform_selection(p,c['id'],[s['id'] for s in c['shapes']],rotation=angle,pivot=(0,0),include_annotations=True)
            dest=folder/f'r{angle}';dest.mkdir();reference=application_reference(p,row);(dest/'editor.spice').write_text(reference,encoding='utf-8',newline='\n')
            transferred=transfer(p,phystech,dest);result=native_run(transferred,transferred['top'],dest/'physical',tools,captured_reference(reference,'coupon'))
            require(result['status']=='passed' and result['drc_count']==0,'Clean array failed native DRC/LVS.')
            native=check_native(dest/'physical/lvs-extraction/extracted.spice',row)
            record['layouts'].append(dict(rotation=angle,folder=dest.name,project_sha256=sha(dest/'editor.icproj'),reference_sha256=sha(dest/'editor.spice'),gds_sha256=sha(dest/'editor.gds'),oasis_sha256=sha(dest/'editor.oas'),external_oasis_sha256=sha(dest/'external.oas'),gds_reimported_sha256=sha(dest/'gds-reimported.gds'),reimported_gds_sha256=sha(dest/'reimported.gds'),exchange_sha256=sha(dest/'exchange.json'),report_sha256=sha(dest/'physical/report.json'),native_sha256=native['sha256'],native=native))
        if (row['width_um'],row['length_um'],row['multiplicity'])==(2,5,3):
            transferred=load_project(folder/'r0/physical/input.icproj');reference=(folder/'r0/editor.spice').read_text()
            for fault in contract()['physical']['faults']:
                changed=transferred if fault=='reference-count' else fault_project(transferred,row,fault)
                dest=folder/fault;selected=reference
                if fault=='reference-count':
                    cp=clone(base);cp['cells'][0]['devices'][0]['model_params']['mult']=2
                    dest.mkdir();save_project(cp,dest/'reference-editor.icproj')
                    selected=application_reference(cp,{**row,'multiplicity':2});(dest/'reference-editor.spice').write_text(selected,encoding='utf-8',newline='\n')
                result=native_run(changed,changed['top'],dest/'physical',tools,captured_reference(selected,'coupon'))
                try:record['faults'].append(check_fault(dest/'physical',result,row,fault))
                except Exception:record['faults'].append(dict(name=fault,detected=False,error=traceback.format_exc(),report_sha256=sha(dest/'physical/report.json')))
            require(all(v['detected'] for v in record['faults']),'One or more predefined native fault checks failed; all outcomes retained.')
        record['status']='PASS'
    except Exception:record.update(status='FAIL',error=traceback.format_exc())
    write(folder/'record.json',record);return record


def title(execution_root,case,analysis):
    value=dict(execution_root=execution_root,case=case,analysis=analysis)
    return '* icstudio-metal-parallel-v1 '+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def deck(spec,row,angle,analysis,staged,out):
    case=row['name']+'-r'+str(angle);folder=out/'physical'/row['name']/f'r{angle}'
    app=folder/'editor.spice';native=folder/'physical/lvs-extraction/extracted.spice';r=resistance(spec,row)
    lines=[title(str(out),case,analysis),staged['tt'],'.option reltol=1e-7 abstol=1e-15 vntol=1e-12 method=gear','.temp 27','VDRIVE input 0 DC .0005 AC 1',
      '.subckt app_wrapper a b',f'.include {app.as_posix()}','X_BODY a b coupon','.ends app_wrapper',
      '.subckt native_wrapper a b',f'.include {native.as_posix()}','X_BODY a b coupon','.ends native_wrapper']
    for tag,body in [('a','XA in_a out_a app_wrapper'),('n','XN in_n out_n native_wrapper'),('c',f'RC in_c out_c {r:.17g}')]:
        lines += [f'VS_{tag} input in_{tag} DC 0 AC 0',body,f'RL_{tag} out_{tag} 0 1',f'CL_{tag} out_{tag} 0 1n']
    values=coefficients(spec);lines += [f'VP_{key} par_{key} 0 DC {{{key}}} AC {{{key}}}' for key in values]
    channels=['v(input)',*[v for tag in ('a','n','c') for v in (f'v(in_{tag})',f'v(out_{tag})',f'i(vs_{tag})')],*['v(par_'+key+')' for key in values]]
    lines += ['.save '+' '.join(channels),'.dc VDRIVE -.001 .001 .0001' if analysis=='dc' else '.ac dec 3 1k 10g','.end']
    return '\n'.join(lines)+'\n'


def observe(spec,row,angle,analysis,folder,out):
    # The separate auditor rederives the same requirements without this code.
    axis='v(v-sweep)' if analysis=='dc' else 'frequency';parameters=coefficients(spec)
    expected=[axis,'v(input)',*[v for tag in ('a','n','c') for v in (f'v(in_{tag})',f'v(out_{tag})',f'i(vs_{tag})')],*['v(par_'+key+')' for key in parameters]]
    x,data,is_complex=linked.read_raw(folder/'result.raw',title(str(out),row['name']+'-r'+str(angle),analysis),'DC transfer characteristic' if analysis=='dc' else 'AC Analysis',expected)
    require(is_complex==(analysis=='ac'),'Wrong native raw value format.')
    grid=[-.001+i*.0001 for i in range(21)] if analysis=='dc' else [1000*10**(i/3) for i in range(22)]
    require(len(x)==len(grid) and all(math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-12 if analysis=='dc' else 0) for a,b in zip(x,grid)),'Wrong native electrical grid.')
    def error(a,b,absolute=1e-10,relative=1e-6):
        value=linked.normalized(a,b,relative,absolute);require(math.isfinite(value) and value<=1,'Array response exceeds fixed analytical tolerance.');return value
    for key,wanted in parameters.items():error(data['v(par_'+key+')'],[wanted]*len(x),1e-24,1e-10)
    drive=x if analysis=='dc' else [1]*len(x);error(data['v(input)'],drive);r=resistance(spec,row)
    wanted=[v/(1+r) for v in x] if analysis=='dc' else [1/(1+r*(1+2j*math.pi*f*1e-9)) for f in x]
    result={}
    for tag in ('a','n','c'):
        vin=data[f'v(in_{tag})'];vout=data[f'v(out_{tag})'];current=data[f'i(vs_{tag})'];error(vin,drive)
        result[tag]=dict(resistance_ohm=r,maximum_normalized_error=error(vout,wanted),current_normalized_error=error(current,[(a-b)/r for a,b in zip(vin,vout)],1e-12),kcl_normalized_error=error(current,[v*(1+(2j*math.pi*f*1e-9 if analysis=='ac' else 0)) for f,v in zip(x,vout)],1e-12))
    return dict(raw_sha256=sha(folder/'result.raw'),analysis=analysis,samples=len(x),parameters=parameters,branches=result)


def source_files(spec):
    paths={ROOT/CONTRACT,ROOT/'examples/sky130-qualification-lock.json',ROOT/'tests/test_sky130_metal_resistor_parallel.py',ROOT/'tests/test_sky130_metal_resistor_parallel_audit.py',ROOT/'tests/gui_sky130_metal_resistor_parallel.py'}
    paths.update(ROOT/name for name in spec['sources']);paths.update((ROOT/'icstudio').rglob('*.py'));paths.update((ROOT/'scripts').glob('*.py'))
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)}


def run(args):
    spec=contract();require(sys.platform=='linux','The reviewed physical runtime is Linux.')
    out=identity.gui.unlinked(args.out).resolve();require(not out.exists() and not any(c.isspace() for c in str(out)),'Use a fresh native output directory without whitespace.')
    out.mkdir(parents=True);started=time.monotonic();report=dict(schema=1,gate=spec['id'],status='RUNNING',mode='source-integration',qualified=False,installed_acceptance=False,full_family=False,chunk_complete=False,release_ready=False,signoff=False,pilot=args.pilot,execution=dict(root=str(out),nonce=uuid.uuid4().hex),physical=[],electrical=[],scope=__doc__)
    write(out/'qualification.json',report)
    try:
        (out/'contract.json').write_bytes((ROOT/CONTRACT).read_bytes())
        for name,value in spec['engine_sources'].items():
            path=args.engine_source/name;require(sha(path)==value['sha256'],'Changed primitive reference.')
            target=out/'engine-reference'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
        package_root=ROOT/spec['package']['path'];package=json.loads((package_root/'package.json').read_bytes())
        require(sha(package_root/'package.json')==spec['package']['manifest_sha256'],'Changed simulation package.')
        tech=clone(package['technology']);tech.update(package_root=str(package_root),package_lock={key:package[key] for key in ('id','revision','files')})
        package_files={'package.json':sha(package_root/'package.json'),**package['files']}
        for name,digest in package_files.items():
            path=identity.gui.unlinked(package_root/name);require(sha(path)==digest,'Changed simulation asset.')
            target=out/'original-package'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
        write(out/'package-files.json',package_files)
        staged={'tt':stage_model_deck(tech,'\n'.join(model_lines(tech,'tt')),out)};write(out/'selected-model-lines.json',staged)
        staged_files=identity.inventory(out/'pdk-models');write(out/'staged-model-files.json',staged_files)
        tools={key:str(getattr(args,key).resolve(strict=True)) for key in ('magic','netgen')};phystech,physid=technology('sky130A',args.sky130)
        physical_files=physical_identity.tree(args.sky130);write(out/'physical-package-files.json',physical_files)
        # Retain only the small selected adapter, never another installed toolchain.
        for name,item in physical_files.items():
            if name.startswith('$') or not isinstance(item,dict) or 'sha256' not in item:continue
            path=args.sky130/name
            if path.is_file():
                target=out/'original-physical-package'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
        before_physical=physical_identity.runtime(tools);write(out/'physical-runtime-before.json',before_physical)
        sources=source_files(spec);write(out/'source-files.json',sources)
        for name,digest in sources.items():
            target=out/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes());require(sha(target)==digest,'Source changed during capture.')
        engine=identity.checked_path(args.ngspice);require(sha(engine)==spec['runtime']['ngspice_sha256'],'Unreviewed electrical engine.')
        env=identity.native_environment(dict(mode='source-pilot'),engine,out);before=identity.runtime(dict(mode='source-pilot'),engine,env);write(out/'runtime-before.json',before)
        runtime_files={**before['files'],**{v['resolved']:v['sha256'] for v in before['elf_dependencies'].values()}};linked.retain_files(runtime_files,out/'runtime-assets');write(out/'runtime-assets.json',runtime_files)
        selected=selection(spec,args.pilot);report.update(contract_sha256=CONTRACT_SHA,source_root=str(ROOT),source_files_sha256=sha(out/'source-files.json'),simulation_package=spec['package'],physical_package=physid,selected_cases=[r['name'] for r in selected],tools=tools,runtime_before_sha256=sha(out/'runtime-before.json'),physical_runtime_before_sha256=sha(out/'physical-runtime-before.json'))
        (out/'physical').mkdir()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for task in as_completed([pool.submit(physical_case,tech,phystech,row,out/'physical',tools) for row in selected]):
                value=task.result();report['physical'].append(value);write(out/'qualification.json',report);print(value['name'],value['status'],flush=True)
        require(len(report['physical'])==len(selected) and all(r['status']=='PASS' for r in report['physical']),'Physical array acceptance failed.')
        electrical=[(r,a,k) for r in selected if (r['width_um'],r['length_um'])==(2,5) and r['multiplicity'] in (2,3,16) for a in (0,90) for k in ('dc','ac')]
        (out/'electrical').mkdir()
        def execute(row,angle,analysis):
            name=row['name']+f'-r{angle}-{analysis}';folder=out/'electrical'/name;folder.mkdir();text=deck(spec,row,angle,analysis,staged,out);(folder/'input.cir').write_text(text,encoding='utf-8',newline='\n')
            reference=out/'physical'/row['name']/f'r{angle}'/'editor.spice';native=reference.parent/'physical/lvs-extraction/extracted.spice'
            argv=[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(folder/'result.raw'),str(folder/'input.cir')]
            value={**row,'name':name,'physical_case':row['name'],'rotation':angle,'analysis':analysis,'status':'RUNNING','command':argv,'cwd':str(out),'environment':env,'application':dict(path=str(reference),sha256=sha(reference)),'native':dict(path=str(native),sha256=sha(native))}
            try:
                proc=subprocess.run(argv,cwd=out,env=env,capture_output=True,text=True,timeout=90);log=proc.stdout+proc.stderr;(folder/'console.log').write_text(log,encoding='utf-8')
                require(proc.returncode==0 and 'error' not in log.lower() and 'unknown parameter' not in log.lower(),'Native electrical run failed.')
                value.update(observation=observe(spec,row,angle,analysis,folder,out),status='PASS',returncode=proc.returncode,deck_sha256=sha(folder/'input.cir'),raw_sha256=sha(folder/'result.raw'),log_sha256=sha(folder/'console.log'))
            except Exception:value.update(status='FAIL',error=traceback.format_exc())
            write(folder/'record.json',value);return value
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for task in as_completed([pool.submit(execute,*v) for v in electrical]):
                value=task.result();report['electrical'].append(value);write(out/'qualification.json',report);print(value['name'],value['status'],flush=True)
        require(len(report['electrical'])==len(electrical) and all(v['status']=='PASS' for v in report['electrical']),'Actual array electrical acceptance failed.')
        after=identity.runtime(dict(mode='source-pilot'),engine,env);write(out/'runtime-after.json',after)
        after_physical=physical_identity.runtime(tools);write(out/'physical-runtime-after.json',after_physical)
        require(before==after and before_physical==after_physical,'Native runtime changed.')
        require(all(sha(ROOT/n)==d for n,d in sources.items()),'Source changed during execution.')
        require(all(sha(package_root/n)==d for n,d in package_files.items()),'Simulation package changed.')
        require(staged_files==identity.inventory(out/'pdk-models'),'Staged models changed.')
        require(physical_files==physical_identity.tree(args.sky130),'Physical adapter changed.')
        report.update(status='PASS',runtime_after_sha256=sha(out/'runtime-after.json'),physical_runtime_after_sha256=sha(out/'physical-runtime-after.json'),guards=dict(source=True,simulation_package=True,staged_models=True,physical_package=True,runtime=True))
    except Exception:report.update(status='FAIL',error=traceback.format_exc())
    report['physical'].sort(key=lambda r:r['name']);report['electrical'].sort(key=lambda r:r['name']);report['seconds']=time.monotonic()-started
    write(out/'qualification.json',report);write(out/'manifest.json',identity.inventory(out,('manifest.json',)));return report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('sky130','magic','netgen','ngspice','engine-source','out'):ap.add_argument('--'+key,type=Path,required=True)
    ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,choices=range(1,5),default=2)
    args=ap.parse_args()
    with physical_identity.controlled_environment():report=run(args)
    print(json.dumps(dict(status=report['status'],seconds=report['seconds']),indent=2));return int(report['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
