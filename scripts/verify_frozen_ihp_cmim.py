"""Two installed ordinary-catalog IHP CMIM reference routes, independently read back.

The frozen GUI captures the schematic; the same frozen executable runs both
managed workers. This finite default-layout gate makes no family, electrical,
operating-envelope or manufacturing qualification claim.
"""
import argparse
import ast
import copy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.verify_frozen_mim import require,sha,digest,load as load_json,git_environment,git_blob,backend_binding,design_hash
from scripts.verify_frozen_ihp_resistors import build_metadata,runtime_files,native_tool_paths,execute_job,stream,same_stream

PDK='icstudio/assets/pdks/ihp-sg13g2'
FIXTURE='icstudio/assets/qualification/ihp-cmim-reference'
PUBLIC=('icstudio/assets/physical/ihp_klayout_lvs','icstudio/assets/physical/ihp_klayout_drc')
HELPERS=('scripts/verify_frozen_ihp_cmim.py','scripts/verify_frozen_ihp_resistors.py','scripts/verify_frozen_mim.py')
STAGES=('preflight','layout_export','drc','lvs_extraction','lvs','integrity')
ROUTES=('magic','ihp-klayout')
FIELDS=('shapes','layout_instances','layout_texts','external_properties','layout_ports','layout_label_mode')
FORBIDDEN='tmpuxoell2b'
SCOPE='Two fresh installed ordinary-catalog 7 um cap_cmim references on the shipped imported-mask fixture, Magic and public KLayout; no full-family, electrical, operating-envelope or manufacturing qualification.'


def load(path):
    value=load_json(path)
    def finite(item):
        if isinstance(item,float):require(math.isfinite(item),'Nonfinite JSON number.')
        elif isinstance(item,dict):
            for child in item.values():finite(child)
        elif isinstance(item,list):
            for child in item:finite(child)
    finite(value);return value


def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def host_path(launch,*parts):
    """Interpret recorded installation paths on their original operating system."""
    cls=PureWindowsPath if launch['platform']=='Windows' else PurePosixPath
    return str(cls(*parts))


def member(name):
    require(isinstance(name,str) and name and '\\' not in name and ':' not in name and
            not name.startswith('/') and all(p not in ('','.','..',FORBIDDEN) for p in name.split('/')),'Unsafe evidence member.')
    return name


def safe(path):
    path=Path(path).absolute()
    require(FORBIDDEN not in path.parts,'Forbidden input basename.')
    for part in (*reversed(path.parents),path):
        require(not part.is_symlink() and not (hasattr(part,'is_junction') and part.is_junction()),'Linked evidence/input path.')
    return path


def confined(root,name):
    root=safe(root).resolve();path=Path(name)
    require(FORBIDDEN not in path.parts,'Forbidden input basename.')
    path=safe(path if path.is_absolute() else root/member(name))
    require(path.resolve().is_relative_to(root) and path.resolve()!=root,'Evidence escaped root.')
    return path.resolve()


def inventory(root,exclusions=()):
    root=safe(root).resolve();result={}
    for folder,dirs,files in os.walk(root,topdown=True,followlinks=False):
        dirs[:]=sorted(n for n in dirs if n!=FORBIDDEN)
        for name in dirs:safe(Path(folder)/name)
        for name in sorted(files):
            if name==FORBIDDEN:continue
            path=safe(Path(folder)/name);name=path.relative_to(root).as_posix()
            if name not in exclusions:result[name]=sha(path)
    return result


def file_map(root,records):
    require(isinstance(records,dict) and bool(records),'Missing complete file inventory.')
    for name,value in records.items():
        path=confined(root,member(name))
        require(isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) and path.is_file() and sha(path)==value,'File inventory differs: '+name)


def link_endpoint(name,target,files,links):
    """Resolve only recorded relative file links, never the current filesystem."""
    seen=set()
    while True:
        require(name not in seen and isinstance(target,str) and target and '\\' not in target and ':' not in target and not target.startswith('/'),'Unsafe or cyclic distribution link.')
        seen.add(name);parts=list(PurePosixPath(member(name)).parent.parts)
        for part in target.split('/'):
            require(part!=FORBIDDEN,'Forbidden link target.')
            if part in ('','.'):continue
            if part=='..':require(bool(parts),'Distribution link escaped installation.');parts.pop()
            else:parts.append(part)
        endpoint='/'.join(parts);member(endpoint)
        if endpoint in files:return endpoint
        require(endpoint in links,'Distribution link does not resolve to a retained regular file.');name,target=endpoint,links[endpoint]


def distribution_tree(root,platform):
    root=safe(root).resolve();files={};links={};installer={}
    for folder,dirs,names in os.walk(root,topdown=True,followlinks=False):
        dirs[:]=sorted(n for n in dirs if n!=FORBIDDEN)
        for name in list(dirs):
            path=Path(folder)/name
            require(not path.is_symlink() and not (hasattr(path,'is_junction') and path.is_junction()),'Distribution directory link is unsupported.')
        for name in sorted(names):
            if name==FORBIDDEN:continue
            path=Path(folder)/name;relative=member(path.relative_to(root).as_posix())
            if path.is_symlink():
                require(platform=='Linux','Unexpected Windows distribution symlink.');links[relative]=os.readlink(path)
            else:
                safe(path);require(path.is_file(),'Nonregular distribution member.')
                if platform=='Windows' and relative in ('unins000.exe','unins000.dat','unins000.msg'):installer[relative]=sha(path)
                else:files[relative]=sha(path)
    for name,target in links.items():link_endpoint(name,target,files,links)
    return dict(files=files,links=links,installer_metadata=installer)


def candidate(commit):
    require(isinstance(commit,str) and re.fullmatch('[0-9a-f]{40}',commit),'Exact candidate commit required.')
    listing=subprocess.check_output(['git','ls-tree','-rz',commit,'--','icstudio',*HELPERS,'.github/workflows/build-desktop.yml'],cwd=ROOT,env=git_environment())
    selected=[]
    for entry in listing.split(b'\0'):
        if not entry:continue
        meta,name=entry.split(b'\t');name=name.decode();member(name)
        if (name.startswith('icstudio/') and name.count('/')==1 and name.endswith('.py') and name!='icstudio/build_info.py') or name.startswith((FIXTURE+'/',*(p+'/' for p in PUBLIC))) or name in (*HELPERS,PDK+'/package.json','icstudio/assets/pdks/collection.json','.github/workflows/build-desktop.yml'):
            require(meta.split()[0]==b'100644' and meta.split()[1]==b'blob','Nonregular candidate source.');selected.append((name,meta.split()[2]))
    require(selected,'Missing candidate sources.')
    raw=subprocess.check_output(['git','cat-file','--batch'],cwd=ROOT,env=git_environment(),input=b'\n'.join(v for _,v in selected)+b'\n')
    values={};offset=0
    for name,oid in selected:
        end=raw.index(b'\n',offset);header=raw[offset:end].split();size=int(header[2]);require(header[:2]==[oid,b'blob'],'Git candidate blob differs.')
        values[name]=raw[end+1:end+1+size];offset=end+size+2
    for name in HELPERS:require(name in values and hashlib.sha256(values[name]).hexdigest()==sha(ROOT/name),'Parent checker differs from candidate: '+name)
    mandatory=(*HELPERS,PDK+'/package.json','icstudio/assets/pdks/collection.json',FIXTURE+'/mask-only.json',FIXTURE+'/SOURCE.json',FIXTURE+'/LICENSE',*(p+'/SOURCE.json' for p in PUBLIC),'icstudio/ihp_cmim_desktop_probe.py','.github/workflows/build-desktop.yml')
    require(all(name in values for name in mandatory),'Incomplete CMIM candidate closure.')
    modules=sorted(name for name in values if name.startswith('icstudio/') and name.count('/')==1 and name.endswith('.py'))
    return dict(files={name:hashlib.sha256(value).hexdigest() for name,value in values.items()},
        workflow_hash=hashlib.sha256(b''.join(Path(name).name.encode()+values[name] for name in modules)).hexdigest(),
        engine_hash=hashlib.sha256(values['icstudio/simulation.py']).hexdigest(),
        package_sha256=hashlib.sha256(values[PDK+'/package.json']).hexdigest(),
        collection_sha256=hashlib.sha256(values['icstudio/assets/pdks/collection.json']).hexdigest())


def literal(value):
    match=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([munp]?)',str(value))
    require(match is not None and len(match[1])<=100,'Invalid finite literal capacitor parameter.')
    try:
        number=Decimal(match[1]);sign,digits,exponent=number.as_tuple()
        require(type(exponent) is int and abs(exponent)<=1000,'Unsupported capacitor exponent.')
        out=Decimal((sign,digits,exponent+{'':0,'m':-3,'u':-6,'n':-9,'p':-12}[match[2]]))
    except InvalidOperation as error:raise ValueError('Invalid capacitor number.') from error
    require(out.is_finite(),'Nonfinite capacitor parameter.');return out


def circuit(text,mode,*,raw_top_order=False):
    """Independently fixed default dimensions; no values come from extraction."""
    lines=[v.split() for v in re.sub(r'\n[ \t]*\+[ \t]*',' ',text).splitlines() if v.strip() and not v.lstrip().startswith('*')]
    require(len(lines)==3 and [v.lower() for v in lines[0][:2]]==['.subckt','coupon'] and
        (len(lines[0][2:])==2 and set(lines[0][2:])=={'C1','C2'} if raw_top_order else lines[0][2:]==['C1','C2']) and
        [v.lower() for v in lines[-1]] in (['.ends'],['.ends','coupon']),'Capacitor circuit closure or ordered top ports differ.')
    row=lines[1];require(len(row)>=6 and row[1:4]==['C1','C2','cap_cmim'] and
        re.fullmatch(('[cC]' if mode=='public' else '[xX]')+r'\S+',row[0]),'Ordered capacitor device pins/model/prefix differ.')
    pairs=[v.split('=') for v in row[4:]];require(all(len(v)==2 for v in pairs),'Malformed capacitor properties.')
    params={}
    for key,value in pairs:
        key=key.lower();require(key not in params,'Duplicated capacitor property.');params[key]=literal(value)
    required={'w','l','m','mm_ok'} if mode=='original' else {'w','l','a','p','m'} if mode=='public' else {'w','l'}
    allowed=required if mode!='magic' else required|{'m'}
    require(required<=set(params)<=allowed,'Unknown or missing capacitor properties.')
    require(params['w']==params['l']==Decimal('7e-6') and params.get('m',Decimal(1))==1,'Default W/L/m differ.')
    if mode=='original':require(params['mm_ok']==1,'Original simulation selector differs.')
    if mode=='public':require(params['a']==Decimal('49e-12') and params['p']==Decimal('28e-6'),'Per-unit area/perimeter differ.')
    return dict(instance=row[0],ordered_nodes=row[1:3],parameters={k:str(v) for k,v in params.items()})


def header(report,launch,inputs):
    require(report.get('schema')==1 and report.get('status')=='passed' and report.get('mode')=='lifecycle' and
        report.get('frozen') is True and report.get('native_execution') is False and report.get('managed') is True,'Producer must be frozen GUI-only managed lifecycle evidence.')
    require(report.get('execution_id')==launch['execution_id'] and re.fullmatch('[0-9a-f]{32}',report['execution_id']),'Stale producer nonce.')
    build=report.get('build',{});require(build.get('commit')==launch['expected_commit'] and build.get('dirty') is False and build.get('frozen') is True,'Dirty or wrong producer build.')
    require(report.get('executable')==launch['command'][0] and report.get('executable_sha256')==launch['executable_sha256'],'Frozen executable identity differs.')
    require(all(report.get(k) is False for k in ('qualified','release_ready','full_family','installed_acceptance')) and not report.get('error') and not report.get('errors'),'Producer overclaims or contains errors.')
    require(report['resource_root']==launch['resource_root'] and report['fixture_root']==host_path(launch,launch['resource_root'],FIXTURE),'External producer resources.')
    require(report['package_manifest_sha256']==inputs['package_sha256'] and report['bundle_collection_sha256']==inputs['collection_sha256'] and
        report['fixture_sha256']==inputs['files'][FIXTURE+'/mask-only.json'] and report['fixture_source_sha256']==inputs['files'][FIXTURE+'/SOURCE.json'] and
        report['fixture_license_sha256']==inputs['files'][FIXTURE+'/LICENSE'],'Producer source/package inputs differ.')


def project_stream(project):
    """Read literal project masks and port labels without application generation."""
    import klayout.db as db
    cell=project['cells'][0];layers={v['name']:(v['gds'],v['datatype']) for v in project['pdk']['layers']};regions={};labels=[]
    for shape in cell['shapes']:
        pair=layers[shape['layer']];require(shape['kind'] in ('rect','polygon'),'Unexpected fixture shape kind.')
        polygon=db.Polygon(db.Box(*shape['points'][0],*shape['points'][1])) if shape['kind']=='rect' else db.Polygon([db.Point(*p) for p in shape['points']])
        for hole in shape.get('holes',[]):polygon.insert_hole([db.Point(*v) for v in hole])
        regions.setdefault(pair,db.Region()).insert(polygon)
    labels=[((layers[v['layer']][0],2),v['name'],*v['point'],0) for v in cell['layout_ports']]
    texts={v['text']:v for v in cell.get('layout_texts',[])}
    labels=[(*v[:4],int(texts.get(v[1],{}).get('rotation',0))//90) for v in labels]
    return {pair:region.merged() for pair,region in regions.items()},sorted(labels)


def lifecycle(root,report,inputs,lock):
    row=report['lifecycle'];paths={}
    for key in ('project','reopened_project','reference','schematic','gds','oasis'):
        paths[key]=confined(root,member(row[key]));require(sha(paths[key])==row[key+'_sha256'],'Producer lifecycle file differs: '+key)
    project=load(paths['project']);require(project==load(paths['reopened_project']) and design_hash(project)==row['design_hash'],'Saved/reopened catalog project differs.')
    require(len(project['cells'])==1 and project['top']==row['cell_id']==project['cells'][0]['id'],'Saved top/cell identity differs.')
    cell=project['cells'][0];require(cell['name']==row['top']=='coupon' and cell['ports']==['C1','C2'] and len(cell['devices'])==1 and not cell.get('wires') and not cell.get('junctions'),'Unexpected saved catalog topology.')
    device=cell['devices'][0];require('native_spice' not in device and device['id']==row['instance_id'] and device['nets']==row['nets']=={'c0':'C1','c1':'C2'},'Catalog device is imported or pins differ.')
    require(project['pdk']['package_lock']==dict(id=lock['id'],revision=lock['revision'],files=lock['files'],manifest_hash=digest(lock)),'Saved registry PDK lock differs.')
    require(all(project['pdk'].get(k)==v for k,v in lock['technology'].items()),'Saved technology differs from the locked package.')
    catalog=project['pdk']['simulation']['catalog'];key='sg13g2_pr/cap_cmim.sym';entry=lock['technology']['simulation']['catalog'][key]
    require(catalog[key]==entry and device['model_ref']==dict(pdk=lock['id'],revision=lock['revision'],device=key) and device.get('symbol')==entry['symbol'],'Actual saved catalog binding differs.')
    params={key:row['default'] for key,row in entry['parameters'].items()};params.update(device.get('model_params',{}))
    require(set(params)=={'w','l','m','mm_ok'} and literal(params['w'])==literal(params['l'])==Decimal('7e-6') and literal(params['m'])==literal(params['mm_ok'])==1,'Saved schematic default parameters differ.')
    fixture=load(root/'fixture-mask.json');source=load(root/'fixture-source.json')
    require(all(cell.get(key)==fixture[key] for key in FIELDS) and fixture['source_project_sha256']==source['original_project_sha256']==report['source_project_sha256'] and
        source['mask_only_sha256']==inputs['files'][FIXTURE+'/mask-only.json'] and source['license_sha256']==inputs['files'][FIXTURE+'/LICENSE'] and source['pdk_manifest_sha256']==inputs['package_sha256'],'Saved physical masks/ports or source provenance differ.')
    raw=paths['reference'].read_text(encoding='utf-8');parsed=circuit(raw,'original')
    actual_statements=[v for v in raw.splitlines() if re.match(r'^[xX]\S+\s',v)]
    require(parsed['instance']=='X_'+device['name'] and actual_statements==[row['simulation_statement']] and row['simulation_statement'] in paths['schematic'].read_text(encoding='utf-8'),'Captured application simulation reference differs.')
    require(project['name']==row['project_name']=='IHP CMIM '+report['execution_id'] and project['name'] in raw,'Saved project/reference lacks fresh execution identity.')
    require(row['reference_capture']==dict(text=raw,top='coupon',ports=['C1','C2'],sha256=sha(paths['reference'])),'Producer captured original reference differs.')
    require(all(type(row[k]) is int and row[k]==value for k,value in dict(default_width_um=7,default_length_um=7,multiplicity=1,mm_ok=1,edit_width_um=8,restored_width_um=7).items()),'GUI default/edit lifecycle differs.')
    expected=project_stream(project);same_stream(stream(paths['gds'],'coupon'),expected,text_presentation=False);same_stream(stream(paths['oasis'],'coupon'),expected,text_presentation=False)
    return project,raw


def runtime_evidence(root,report,launch,inputs):
    before=report['managed_runtime_before'];require(before==report['managed_runtime_after'],'Producer runtime changed.')
    require(before['payload_root']==host_path(launch,launch['resource_root'],'icstudio/assets/runtime/digital') and before['backend_root']==host_path(launch,before['payload_root'],'backend/icstudio'),'External managed payload/backend.')
    backend={name.split('/')[-1]:value for name,value in inputs['files'].items() if name.startswith('icstudio/') and name.count('/')==1 and name.endswith('.py')}
    backend['build_info.py']=launch['backend_build_info_sha256'];require(before['backend_files']==backend,'Producer backend differs from candidate.')
    for phase in ('before','after'):
        folder=root/'runtime'/phase;file_map(folder,before['files']);require(load(folder/'backend-files.json')==backend and sha(folder/'payload-manifest.json')==launch['payload_manifest_sha256'],'Runtime capture differs.')
    manifest=load(root/'runtime/before/payload-manifest.json');records=load(root/'runtime/before/files.json');runtime=before['runtime']
    for name in records:member(name)
    require(manifest['schema']==1 and manifest['archive']=='runtime.tar.gz' and runtime['kind']==('wsl' if launch['platform']=='Windows' else 'linux') and
        runtime['sha256']==manifest['sha256'] and sha(root/'runtime/before/files.json')==manifest['files_sha256'] and
        load(root/'runtime/before/runtime.json')['files_sha256']==manifest['files_sha256'],'Runtime archive/file lock differs.')
    require({'magic','netgen','ngspice','klayout'}<=set(manifest['tools']),'Missing locked native tools.')
    require(report['ready_status_before']==report['ready_status_after'],'Normal runtime readiness changed.')
    ready=load(root/'runtime/before/ready.json');require(ready==load(root/'runtime/after/ready.json'),'Normal ready record changed.')
    ready_binding(ready,report['ready_status_before'],backend,manifest,runtime)
    require(FORBIDDEN not in PureWindowsPath(runtime['root']).parts and FORBIDDEN not in PurePosixPath(runtime['root']).parts,'Forbidden runtime root.')
    return runtime,records


def ready_binding(ready,status,backend,manifest,runtime):
    require(status['state']=='ready' and status['runtime']==runtime,'Installed runtime was not normally ready.')
    require(ready['runtime']==runtime and ready['manifest']==digest(manifest) and ready['backend']==digest(backend) and
        status['evidence']==ready['evidence'] and all(ready.get(key)==manifest[key] for key in ('platforms','platform_corners') if key in manifest),'Normal ready record differs from candidate backend/runtime.')


def projection(report,original,comparison,route,lock,inputs):
    parsed=circuit(comparison,'magic' if route=='magic' else 'public');source=circuit(original,'original')['instance']
    require(parsed['instance']==(source if route=='magic' else 'C'+source),'Projected instance identity differs.')
    rows=report.get('reference_defaults');require(isinstance(rows,list) and len(rows)==1,'Missing/duplicate source projection proof.')
    row=rows[0];proof=row.get('proof',{});symbol='libs.tech/xschem/sg13g2_pr/cap_cmim.sym';model='libs.tech/ngspice/models/capacitors_mod.lib'
    expected=dict(source=symbol,sha256=lock['files'][symbol],model_source=model,model_sha256=lock['files'][model])
    if route=='ihp-klayout':expected.update(geometry_reader='rule_decks/custom_reader.lvs',geometry_reader_sha256=inputs['files'][PUBLIC[0]+'/rule_decks/custom_reader.lvs'],geometry_formula='A=w*l; P=2*(w+l), per unit; m retained separately')
    require(row.get('instance')==source and row.get('physical_instance')==parsed['instance'] and row.get('changed') is True and proof==expected,'Projection source/geometry provenance differs.')
    return row


def public_drc(folder,native,inputs,native_origin,tool):
    record=native['klayout_drc'];source=inputs['files'][PUBLIC[1]+'/SOURCE.json'];layout=sha(folder/'original.gds')
    require(record['source_lock_sha256']==source and record['input_sha256']==layout and record['top']=='coupon' and type(record['violations']) is int and record['violations']==0,'Public DRC source/input/count differs.')
    require([r['name'] for r in record['decks']]==['main','maximal'],'Missing/duplicate public DRC deck.')
    for row,entry in zip(record['decks'],('ihp-sg13g2.drc','rule_decks/sg13g2_maximal.drc')):
        name=row['name'];path=folder/'drc'/name/'findings.lyrdb';xml=ET.parse(path).getroot()
        require(xml.tag=='report-database' and xml.findtext('top-cell')=='coupon' and len(xml.findall('./items/item'))==0 and
            row['entry']==entry and type(row['violations']) is int and row['violations']==0 and not row['categories'] and row['report']==name+'/findings.lyrdb' and sha(path)==row['report_sha256'],'Raw public DRC report differs.')
        command=load(folder/'drc'/name/'command.json');expected=[tool,'-b','-r',native_origin+'/drc/rules/'+entry]
        for key,value in dict(input=native_origin+'/original.gds',topcell='coupon',report=native_origin+'/drc/'+name+'/findings.lyrdb',log=native_origin+'/drc/'+name+'/native.log',run_mode='flat',threads=1,drc_json=native_origin+'/drc/rules/sg13g2_tech_mod.json',drc_json_default=native_origin+'/drc/rules/rule_decks/sg13g2_tech_default.json').items():expected+=['-rd',str(key)+'='+str(value)]
        require(command==expected,'Public deck command/default switches differ.')
        log=(folder/'drc'/name/'console.log').read_text();marker="KLayout DRC run for tables 'main' completed in" if name=='main' else 'KLayout DRC run for maximum ruleSet completed in'
        require(marker in log and (name!='main' or all(s+' enabled: true' in log for s in ('FEOL','BEOL','OFFGRID','ANGLE','PIN','FORBIDDEN','RECOMMENDED'))),'Public DRC did not complete all selected checks.')
    expected=dict(status='EXECUTED',checker='ihp-public',deck='maximal',source_lock_sha256=source,input_sha256=layout,report='drc/maximal/findings.lyrdb',report_sha256=record['decks'][1]['report_sha256'])
    require(native['drc_coverage']=={'MIM.g':expected},'Public MIM.g execution binding differs.')
    for name,value in inputs['files'].items():
        if name.startswith(PUBLIC[1]+'/'):require(sha(confined(folder/'drc/rules',name[len(PUBLIC[1])+1:]))==value,'Executed public DRC asset differs.')


def native_sources(flow,stages,route,native_dir,lock,inputs,commit):
    """Bind original source closure and written comparison recipe independently."""
    assets=stages[0]['evidence']['assets'];expected={native_dir+'/pdk/'+name:value for name,value in lock['files'].items() if name.startswith(('libs.tech/magic/','libs.tech/netgen/'))}
    if route=='ihp-klayout':
        for prefix in PUBLIC:
            source_path=flow/('lvs-extraction/deck/SOURCE.json' if prefix==PUBLIC[0] else 'drc/rules/SOURCE.json')
            require(sha(source_path)==inputs['files'][prefix+'/SOURCE.json'],'Public source lock differs.')
            declared=set(load(source_path)['files'])|{'SOURCE.json'}
            for name,value in inputs['files'].items():
                if name.startswith(prefix+'/') and name[len(prefix)+1:] in declared:expected[native_dir+'/backend/'+name]=value
        # The public route explicitly prepares private contact-rule files;
        # their original sources remain in the complete preflight closure.
        for name,value in lock['files'].items():
            if not name.startswith('libs.tech/magic/'):continue
            suffix=name[len('libs.tech/magic/'):];path=confined(flow/'ihp-magic-rules',suffix)
            if suffix=='ihp-sg13g2-drc.tech':
                original=git_blob(commit,PDK+'/'+name);before=b' width pc/m1   160 "poly contact width        < %d (Cnt.a)"'
                after=b' # IC Design Studio: pc and varc can be fragments of one written cut.\n # Measure their union; preserve the original Cnt.a minimum and full DRC.\n width (pc,varc)/m1 160 "poly/varactor contact width < %d (Cnt.a)"'
                require(native_hash(original)==value and original.count(before)==1 and path.read_bytes()==original.replace(before,after),'Private contact-rule correction differs.')
                value=sha(path)
            else:require(sha(path)==value,'Private Magic source copy differs.')
            expected[native_dir+'/output/physical-flow/ihp-magic-rules/'+suffix]=value
    require(assets==expected,'Native preflight source closure differs from locked shipped inputs.')
    if route=='ihp-klayout':
        original=git_blob(commit,PDK+'/libs.tech/netgen/ihp-sg13g2_setup.tcl')
        require(hashlib.sha256(original).hexdigest()==lock['files']['libs.tech/netgen/ihp-sg13g2_setup.tcl'],'Comparison source differs from candidate package.')
        expected=original
        for side in (1,2):
            before=f'property "-circuit{side} $dev" delete Nx Ny'.encode();require(expected.count(before)==1,'Unknown strict comparison source.')
            expected=expected.replace(before,b'# IC Design Studio: retain Nx/Ny; public KLayout extracts emitter count.')
        for model in ('ntap1','ptap1'):
            before=('lappend devices '+model+'\n').encode();require(expected.count(before)==1,'Unknown tap comparison source.')
            expected=expected.replace(before,b'# IC Design Studio: taps retain terminal roles and A/P; no generic resistor permutation or reduction.\n')
        require((flow/'ihp-strict-lvs.tcl').read_bytes()==expected,'Written strict native comparison recipe differs.')
        for suffix in ('rule_decks/custom_reader.lvs','rule_decks/custom_writer.lvs','rule_decks/cap_derivations.lvs'):
            require(sha(flow/'lvs-extraction/deck'/suffix)==inputs['files'][PUBLIC[0]+'/'+suffix],'Executed CMIM extractor source differs.')
        suffix='rule_decks/cap_connections.lvs';source=git_blob(commit,PUBLIC[0]+'/'+suffix)
        old=b'connect(varicap_ports, text_drw)';new=b'# IC Design Studio: SVaricap is device recognition, not an electrical net.\n# Actual conductor labels and contact/metal connectivity establish the ports.'
        require(native_hash(source)==inputs['files'][PUBLIC[0]+'/'+suffix] and source.count(old)==1 and
            (flow/'lvs-extraction/deck'/suffix).read_bytes()==source.replace(old,new),'Written capacitor connection recipe differs.')


def native_hash(value):return hashlib.sha256(value).hexdigest()


def completed_stages(native,route):
    stages=native['stages'];checker='magic' if route=='magic' else 'ihp-public'
    require([v['name'] for v in stages]==list(STAGES) and all(v['status']=='passed' for v in stages) and native['status']=='passed' and
        native['drc_engine']==checker and native['lvs_extractor']==route and type(native['drc_count']) is int and native['drc_count']==0 and not native.get('findings'),'Native stages/count/findings differ.')
    return stages


def strict_lvs(text):
    require(text.count('Final result: Circuits match uniquely.')==1 and not re.search(r'Property errors were found|\*\*Mismatch\*\*|do not match|failed pin matching',text,re.I),'Raw strict native LVS did not match uniquely.')


def native_directory(value,runtime,launch):
    path=PurePosixPath(value)
    require(path.is_absolute() and FORBIDDEN not in path.parts and '..' not in path.parts,'Unsafe native job directory.')
    if runtime['kind']=='wsl':valid=path.parent==PurePosixPath('/var/tmp/icstudio-physical') and re.fullmatch('[0-9a-f]{32}',path.name)
    else:valid=launch['native_temp_root']=='/tmp' and path.parent==PurePosixPath('/tmp') and re.fullmatch('icstudio-physical-[a-z0-9_]{8}',path.name)
    require(valid,'Native directory is not a fresh managed job directory.')
    return path


def magic_scripts(flow,native_dir):
    origin=native_dir+'/output/physical-flow'
    prefix='if {[catch {\ngds read "'+origin+'/layout.gds"\nload "coupon"\nselect top cell\nbox values 0 0 0 0\n'
    for index,name in enumerate(('C1','C2'),1):prefix+='if {![port "'+name+'" exists]} {error "Missing layout port '+name+'"}\nport "'+name+'" index '+str(index)+'\n'
    suffix='\nputs STUDIO_MAGIC_COMPLETE\n} err]} {puts stderr "STUDIO_MAGIC_ERROR $err"}\nquit -noprompt\n'
    extract='extract all\next2spice lvs\next2spice subcircuit top on\next2spice renumber off\next2spice global off\next2spice hierarchy on\next2spice blackbox off\next2spice scale off\next2spice merge none\next2spice cthresh infinite\next2spice rthresh infinite\next2spice extresist off\next2spice -o extracted.spice'
    drc='snap internal\nselect top cell\nbox values {*}[select bbox]\nbox grow c 10um\ndrc style "drc(full)"\ndrc ignore none\ndrc check\ndrc catchup\nputs "STUDIO_DRC_COUNT [drc list count total]"\nputs "STUDIO_DRC_STYLE [drc list style]"\nputs "STUDIO_MAGIC_SCALE [cif scale out]"\nset f [open findings.tsv w]\nforeach {reason boxes} [drc listall why] {foreach coords $boxes {puts $f "[string map {\\t { } \\n { }} $reason]\\t[join $coords {,}]"}}\nclose $f\n'
    startup='tech load "'+native_dir+'/pdk/libs.tech/magic/icstudio-ihp-sg13g2.tech"\ndrc euclidean on\n'
    for name,commands in (('drc',drc),('lvs-extraction',extract)):
        require((flow/name/'startup.tcl').read_text()==startup and (flow/name/'run.tcl').read_text()==prefix+commands+suffix,'Native Magic full DRC/extraction script differs.')


def netgen_json(path):
    rows=load(path);require(isinstance(rows,list) and bool(rows),'Missing raw native Netgen JSON.')
    tops=[r for r in rows if 'name' in r]
    require(len(tops)==1 and tops[0]['name']==['coupon','coupon'],'Unexpected native comparison circuit coverage.')
    row=tops[0];require(row['nets']==[2,2] and row['pins']==[['C1','C2'],['C1','C2']] and not row['badnets'] and not row['badelements'] and not row.get('properties'),'Raw native comparison connectivity/properties differ.')
    require(row['devices']==[[['cap_cmim',1]],[['cap_cmim',1]]] and all(type(side[0][1]) is int for side in row['devices']),'Raw native comparison device counts differ.')


def audit_job(folder,project,raw,route,runtime,records,inputs,lock,launch):
    inventory(folder)  # Reject linked output members before reading any raw file.
    job=load(folder/'input.json');attempt=load(folder/'invocation.json');result=load(folder/'result.json');report=result['silicon_report'];execution=report['execution']
    checker='magic' if route=='magic' else 'ihp-public';expected_project=copy.deepcopy(project);expected_project['pdk']['package_root']=launch['resource_root']+'/'+PDK
    # Path spelling follows the actual host on which the candidate ran.
    if launch['platform']=='Windows':expected_project['pdk']['package_root']=launch['physical_package_root']
    ref=dict(text=raw,top='coupon',ports=['C1','C2'],sha256=hashlib.sha256(raw.encode()).hexdigest())
    expected=dict(project=expected_project,cell=project['top'],engine='builtin',environment=dict(workflow_hash=inputs['workflow_hash'],engine='builtin'),settings=dict(type='silicon',verification_mode='drc_lvs',drc_engine=checker,lvs_extractor=route,physical_toolchain='included',physical_runtime=runtime,tools={},reference=ref))
    require(job==expected,'Parent worker input substituted source project/reference/settings.')
    require(attempt['command']==[launch['command'][0],'--worker',host_path(launch,launch['execution_root'],'native',route,'input.json'),host_path(launch,launch['execution_root'],'native',route,'result.json')] and attempt['executable_sha256']==launch['executable_sha256'] and attempt['input_sha256']==sha(folder/'input.json') and attempt['status']=='complete' and type(attempt['returncode']) is int and attempt['returncode']==0 and attempt['log_sha256']==sha(folder/'worker.log'),'Frozen worker invocation differs or did not finish.')
    native_dir=execution['native_directory'];native_directory(native_dir,runtime,launch)
    require(execution['runtime']==runtime and execution['native_input_sha256']==sha(folder/'physical-backend-input.json'),'Managed runtime/input identity differs.')
    native_job=load(folder/'physical-backend-input.json');translated=copy.deepcopy(job);translated['project']['pdk']['package_root']=native_dir+'/pdk';translated.pop('environment');translated['settings'].pop('physical_runtime');translated['settings']['tools']=native_tool_paths(runtime)
    require(native_job==translated,'Host-to-native transfer changed unrelated inputs.')
    artifacts=load(folder/'physical-artifacts.json');file_map(folder,artifacts)
    expected_files={'physical-flow/'+name:value for name,value in inventory(folder/'physical-flow').items()};expected_files['physical-backend-result.json']=sha(folder/'physical-backend-result.json')
    require(artifacts==expected_files==execution['received_files'],'Complete native transfer inventory differs.')
    native=load(folder/'physical-flow/report.json');native_result=load(folder/'physical-backend-result.json');flow=folder/'physical-flow';origin=native_dir+'/output/physical-flow'
    require(native_result['silicon_report']==native and native_result['design_hash']==native['design_hash']==design_hash(native_job['project']) and
        result['design_hash']==report['design_hash']==design_hash(expected_project) and result['settings']==job['settings'] and report['native_design_hash']==native['design_hash'] and load(flow/'input.icproj')==native_job['project'],'Raw native/host result identity differs.')
    for key,value in native.items():
        if key not in ('design_hash','stages'):require(report.get(key)==value,'Host report changed native result: '+key)
    stages=completed_stages(native,route)
    require([(v['name'],v['status']) for v in completed_stages(report,route)]==[(v['name'],v['status']) for v in stages],'Host/native stage ordering or status differs.')
    file_map(flow,stages[-1]['evidence']['files'])
    require((flow/'schematic.spice').read_bytes()==raw.encode() and native['reference']=={k:v for k,v in ref.items() if k!='text'},'Original catalog reference was substituted.')
    projected=projection(native,raw,(flow/'schematic-lvs.spice').read_text(),route,lock,inputs)
    same_stream(stream(flow/'original.gds','coupon'),project_stream(project),text_presentation=False);same_stream(stream(flow/'layout.gds','coupon'),project_stream(project),text_presentation=False)
    comparison=(flow/'lvs/lvs.log').read_text();strict_lvs(comparison)
    netgen_json(flow/'lvs/lvs.json')
    console=(flow/'lvs/console.log').read_text();setup=origin+'/ihp-strict-lvs.tcl' if route=='ihp-klayout' else native_dir+'/pdk/libs.tech/netgen/ihp-sg13g2_setup.tcl'
    require(re.findall(r'^Reading netlist file (.+)$',console,re.M)==[origin+'/schematic-lvs.spice',origin+'/lvs-extraction/extracted.spice'] and re.findall(r'^Reading setup file (.+)$',console,re.M)==[setup],'Native strict comparison used other inputs/setup.')
    observed=circuit((flow/'lvs-extraction/extracted.spice').read_text(),'magic' if route=='magic' else 'public')
    if route=='magic':
        magic_scripts(flow,native_dir)
        require(native['drc_coverage']['MIM.g'].get('status')=='NOT_CHECKED' and native['drc_coverage']['MIM.g'].get('reason')=='unsupported_by_selected_checker','Magic falsely claims maximum-area coverage.')
        for name in ('drc','lvs-extraction'):
            log=(flow/name/'console.log').read_text();require(log.count('STUDIO_MAGIC_COMPLETE')==1 and not re.search(r'STUDIO_MAGIC_ERROR|invalid command|contained errors|Malformed line',log,re.I),'Native Magic did not complete.')
        log=(flow/'drc/console.log').read_text();require(re.findall(r'^STUDIO_DRC_COUNT (\d+)$',log,re.M)==['0'] and 'STUDIO_DRC_STYLE drc(full)' in log and native['magic_drc_style']=='drc(full)' and not (flow/'drc/findings.tsv').read_bytes(),'Raw Magic full DRC differs.')
    else:
        public_drc(flow,native,inputs,origin,native_tool_paths(runtime)['klayout'])
        observed_native=circuit((flow/'lvs-extraction/native.cir').read_text(),'public',raw_top_order=True)
        require(observed_native['parameters']==observed['parameters'] and observed_native['ordered_nodes']==observed['ordered_nodes'],'Native extraction was altered before LVS.')
        log=(flow/'lvs-extraction/console.log').read_text();require('LVS Total Run time ' in log and 'NET_ONLY enabled: apply extraction netlist options and skip comparison.' in log,'Unfiltered public extraction did not complete.')
        command=load(flow/'lvs-extraction/command.json');require(command[:4]==[native_tool_paths(runtime)['klayout'],'-b','-r',origin+'/lvs-extraction/deck/sg13g2.lvs'],'Public extraction used another tool/deck.')
        expected_command=command[:4]
        for key,value in dict(input=origin+'/lvs-extraction/labels.gds',topcell='coupon',report=origin+'/lvs-extraction/extraction.lvsdb',target_netlist=origin+'/lvs-extraction/native.cir',log=origin+'/lvs-extraction/native.log',run_mode='flat',net_only='true',top_lvl_pins='true',no_simplify='true',combine_devices='false',purge='false',purge_nets='false',purge_devices='false',implicit_nets='',disable_tap_extraction='false').items():expected_command+=['-rd',key+'='+value]
        require(command==expected_command,'Public extraction filters/settings differ.')
    tools={name:dict(path=native_tool_paths(runtime)[name],sha256=records['opt/icstudio/bin/'+name]) for name in (('magic','netgen') if route=='magic' else ('magic','netgen','klayout'))}
    require(stages[0]['evidence']['tools']==tools,'Native tool identity differs from full runtime lock.')
    native_sources(flow,stages,route,native_dir,lock,inputs,launch['expected_commit'])
    if route=='magic':
        extraction=dict(hierarchy=True,blackbox=False,merge='none',scale=False,capacitance_threshold='infinite',resistance_threshold='infinite',distributed_resistance=False)
        require(stages[3]['evidence']['settings']==extraction,'Magic extraction filters/settings differ.')
    return dict(route=route,input_sha256=sha(folder/'input.json'),result_sha256=sha(folder/'result.json'),native_report_sha256=sha(flow/'report.json'),execution=execution,projection=projected,netlist=observed,coverage=native['drc_coverage'])


def verify_evidence(directory,expected_commit):
    """Revalidate retained raw evidence, with no process launch or installed path read."""
    root=safe(directory).resolve();inventory(root)  # A standalone reader must preflight all links before loading raw evidence.
    inputs=candidate(expected_commit);launch=load(root/'invocation.json')
    require(launch['expected_commit']==expected_commit and launch['expected_inputs']==inputs and launch['status']=='complete' and type(launch['returncode']) is int and launch['returncode']==0 and launch['log_sha256']==sha(root/'launcher.log'),'Producer invocation/candidate binding differs.')
    require(launch['command']==[launch['command'][0],'--ihp-cmim-acceptance','--managed','--execution-id',launch['execution_id'],'--out',host_path(launch,launch['execution_root'],'probe')],'Wrong frozen producer invocation.')
    require(launch['platform'] in ('Windows','Linux') and re.fullmatch('[0-9a-f]{64}',launch['executable_sha256']),'Invalid target/executable binding.')
    require(launch['physical_package_root']==host_path(launch,launch['resource_root'],PDK),'External physical package binding.')
    producer=root/'probe';report=load(producer/'report.json');header(report,launch,inputs)
    require(report['execution_root']==host_path(launch,launch['execution_root'],'probe'),'Producer execution root differs from the fresh parent invocation.')
    require(sha(producer/'files.json')==report['files_sha256'] and load(producer/'files.json')==inventory(producer,('report.json','files.json')) and load(root/'producer-receipt.json')==inventory(producer),'Producer complete inventory differs.')
    files=inputs['files']
    for src,dst in ((PDK+'/package.json','bundled-package.json'),('icstudio/assets/pdks/collection.json','bundled-collection.json'),(FIXTURE+'/mask-only.json','fixture-mask.json'),(FIXTURE+'/SOURCE.json','fixture-source.json'),(FIXTURE+'/LICENSE','fixture-LICENSE')):
        require(sha(producer/dst)==files[src],'Retained bundled source differs from immutable candidate.')
    lock=load(producer/'bundled-package.json');require(lock['id']=='ihp-sg13g2' and load(producer/'registry-package.json')==lock and report['registry_manifest_sha256']==sha(producer/'registry-package.json'),'Registry package differs from bundled candidate.')
    project,raw=lifecycle(producer,report,inputs,lock);runtime,records=runtime_evidence(producer,report,launch,inputs)
    for phase in ('before','after'):
        full=load(root/('runtime-'+phase+'.json'));require(full['files']==records or all(full['files'].get(k)==v for k,v in records.items()) and set(full['files'])<=set(records)|{'init','etc/wsl.conf'},'Parent full runtime readback differs from the lock.')
        require(all(member(k) and isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for k,v in full['files'].items()),'Invalid full runtime file identity.')
    require(load(root/'runtime-before.json')==load(root/'runtime-after.json'),'Full runtime changed during installed jobs.')
    jobs=[audit_job(root/'native'/route,project,raw,route,runtime,records,inputs,lock,launch) for route in ROUTES]
    require(len({row['execution']['native_directory'] for row in jobs})==2,'Native jobs reused a directory.')
    distribution=load(root/'distribution-files.json');require(distribution==launch['distribution_files'],'Distribution identity receipt changed.')
    require(all(member(k) and isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for k,v in distribution.items()),'Invalid distribution identity member.')
    links=load(root/'distribution-links.json');installer=load(root/'installer-metadata.json')
    require(links==launch['distribution_links'] and installer==launch['installer_metadata'] and not set(links)&set(distribution),'Distribution link/installer identity changed.')
    require(all(name in ('unins000.exe','unins000.dat','unins000.msg') and isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) for name,value in installer.items()) and (launch['platform']=='Windows' or not installer),'Invalid installer metadata exclusion.')
    for name,target in links.items():link_endpoint(name,target,distribution,links)
    expected_exe='ICDesignStudio.exe' if launch['platform']=='Windows' else 'ICDesignStudio'
    require(distribution.get(expected_exe)==launch['executable_sha256'],'Distribution executable binding differs.')
    for name,value in files.items():
        if name.startswith((FIXTURE+'/',*PUBLIC)) or name in (PDK+'/package.json','icstudio/assets/pdks/collection.json'):
            require(distribution.get('_internal/'+name)==value,'Distribution asset differs from candidate.')
    for name,value in lock['files'].items():require(distribution.get('_internal/'+PDK+'/'+member(name))==value,'Distribution PDK closure differs.')
    for name,value in report['managed_runtime_before']['backend_files'].items():require(distribution.get('_internal/icstudio/assets/runtime/digital/backend/icstudio/'+member(name))==value,'Distribution backend differs.')
    for prefix in PUBLIC:
        for name,value in files.items():
            if name.startswith(prefix+'/'):require(distribution.get('_internal/icstudio/assets/runtime/digital/backend/'+name)==value,'Native backend public assets differ.')
    payload=load(producer/'runtime/before/payload-manifest.json');require(distribution.get('_internal/icstudio/assets/runtime/digital/manifest.json')==launch['payload_manifest_sha256'] and distribution.get('_internal/icstudio/assets/runtime/digital/runtime.tar.gz')==payload['sha256'],'Distribution runtime payload differs.')
    metadata=root/'backend-build-info.py';require(sha(metadata)==launch['backend_build_info_sha256'],'Retained build metadata changed.')
    check_metadata(metadata,expected_commit,inputs)
    require(load(root/'files.json')==inventory(root,('verification.json','files.json')),'Complete parent evidence inventory differs.')
    return dict(schema=1,status='PASS',gate='ihp-cmim-installed-reference',scope=SCOPE,qualified=False,release_ready=False,full_family=False,installed_acceptance=True,
        expected_commit=expected_commit,execution_id=launch['execution_id'],platform=launch['platform'],executable_sha256=launch['executable_sha256'],distribution_files=distribution,distribution_links=links,installer_metadata=installer,
        expected_inputs=inputs,runtime=runtime,runtime_identity_sha256=digest(load(root/'runtime-before.json')),producer_report_sha256=sha(producer/'report.json'),
        files_sha256=sha(root/'files.json'),counts=dict(gui_layouts=1,fresh_managed_jobs=2),jobs=jobs)


def check_metadata(path,commit,inputs):
    values={}
    for node in ast.parse(Path(path).read_text()).body:
        require(isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name),'Unexpected retained build metadata.')
        key=node.targets[0].id;require(key not in values,'Duplicate build metadata.');values[key]=ast.literal_eval(node.value)
    require(values.get('BUILD_COMMIT')==commit and values.get('BUILD_DIRTY') is False and values.get('WORKFLOW_SOURCE_HASH')==inputs['workflow_hash'] and values.get('ENGINE_SOURCE_HASH')==inputs['engine_hash'],'Candidate build/workflow metadata differs.')


def verify(executable,out,commit,timeout=900):
    executable=safe(executable).resolve();out=safe(out).resolve();require(math.isfinite(timeout) and timeout>0 and not out.exists(),'Fresh output and finite deadline required.')
    require(not out.is_relative_to(executable.parent) and not executable.is_relative_to(out),'Output overlaps installed deliverable.')
    inputs=candidate(commit);out.mkdir(parents=True);started=time.monotonic();nonce=uuid.uuid4().hex
    try:
        bundle=executable.parent/'_internal';payload=bundle/'icstudio/assets/runtime/digital';lock=load(bundle/PDK/'package.json')
        require(lock['id']=='ihp-sg13g2' and sha(bundle/PDK/'package.json')==inputs['package_sha256'],'Installed IHP package differs.');file_map(bundle/PDK,lock['files'])
        platform='Windows' if os.name=='nt' else 'Linux';tree=distribution_tree(executable.parent,platform);distribution=tree['files']
        for name,value in inputs['files'].items():
            if name.startswith((FIXTURE+'/',*PUBLIC)) or name in (PDK+'/package.json','icstudio/assets/pdks/collection.json'):
                require(sha(safe(bundle/name))==value,'Installed source resource differs: '+name);distribution['_internal/'+name]=value
        for name,value in lock['files'].items():distribution['_internal/'+PDK+'/'+member(name)]=value
        backend=backend_binding(payload/'backend/icstudio',commit);build_metadata(payload/'backend/icstudio',commit,inputs)
        shutil.copyfile(payload/'backend/icstudio/build_info.py',out/'backend-build-info.py')
        for name,value in backend.items():distribution['_internal/icstudio/assets/runtime/digital/backend/icstudio/'+name]=value
        for prefix in PUBLIC:
            for name,value in inputs['files'].items():
                if name.startswith(prefix+'/'):
                    require(sha(safe(payload/'backend'/name))==value,'Shipped native checker asset differs.');distribution['_internal/icstudio/assets/runtime/digital/backend/'+name]=value
        manifest=load(payload/'manifest.json');require(manifest['archive']=='runtime.tar.gz' and sha(payload/'runtime.tar.gz')==manifest['sha256'],'Installed native archive changed.')
        distribution['_internal/icstudio/assets/runtime/digital/manifest.json']=sha(payload/'manifest.json');distribution['_internal/icstudio/assets/runtime/digital/runtime.tar.gz']=manifest['sha256']
        env=git_environment()
        for key in list(env):
            if key.upper() in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','ICSTUDIO_DIGITAL_PAYLOAD','ICSTUDIO_DIGITAL_NATIVE','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH'):env.pop(key)
        env['QT_QPA_PLATFORM']='offscreen'
        if platform=='Linux':safe('/tmp');env['TMPDIR']='/tmp'
        launch=dict(command=[str(executable),'--ihp-cmim-acceptance','--managed','--execution-id',nonce,'--out',str(out/'probe')],expected_commit=commit,execution_id=nonce,
            executable_sha256=sha(executable),resource_root=str(bundle),execution_root=str(out),platform=platform,native_temp_root='/tmp' if platform=='Linux' else None,physical_package_root=str(bundle/PDK),expected_inputs=inputs,
            distribution_files=distribution,distribution_links=tree['links'],installer_metadata=tree['installer_metadata'],payload_manifest_sha256=sha(payload/'manifest.json'),backend_build_info_sha256=sha(out/'backend-build-info.py'),status='RUNNING')
        write(out/'invocation.json',launch);write(out/'distribution-files.json',distribution);write(out/'distribution-links.json',tree['links']);write(out/'installer-metadata.json',tree['installer_metadata'])
        with (out/'launcher.log').open('wb') as log:
            completed=subprocess.run(launch['command'],env=env,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,check=True)
        launch.update(status='complete',returncode=completed.returncode,log_sha256=sha(out/'launcher.log'));write(out/'invocation.json',launch)
        producer=out/'probe';producer_files=inventory(producer);report=load(producer/'report.json');header(report,launch,inputs);write(out/'producer-receipt.json',producer_files)
        project,raw=lifecycle(producer,report,inputs,lock);runtime,records=runtime_evidence(producer,report,launch,inputs)
        safe(runtime['root']);write(out/'runtime-before.json',dict(files=runtime_files(runtime,records)))
        for route in ROUTES:
            folder=out/'native'/route;folder.mkdir(parents=True);job_project=copy.deepcopy(project);job_project['pdk']['package_root']=str(bundle/PDK)
            ref=report['lifecycle']['reference_capture']
            job=dict(project=job_project,cell=project['top'],engine='builtin',environment=dict(workflow_hash=inputs['workflow_hash'],engine='builtin'),settings=dict(type='silicon',verification_mode='drc_lvs',drc_engine='magic' if route=='magic' else 'ihp-public',lvs_extractor=route,physical_toolchain='included',physical_runtime=runtime,tools={},reference=ref))
            write(folder/'input.json',job);command=[str(executable),'--worker',str(folder/'input.json'),str(folder/'result.json')]
            attempt=dict(command=command,executable_sha256=sha(executable),input_sha256=sha(folder/'input.json'),status='RUNNING');write(folder/'invocation.json',attempt)
            execute_job(folder,command,attempt,time.monotonic(),env,deadline=started+timeout,runtime=runtime)
            audit_job(folder,project,raw,route,runtime,records,inputs,lock,launch)
        write(out/'runtime-after.json',dict(files=runtime_files(runtime,records)))
        require(sha(executable)==launch['executable_sha256'] and backend_binding(payload/'backend/icstudio',commit)==backend,'Installed executable/backend changed during acceptance.')
        require(distribution_tree(executable.parent,platform)==tree,'Installed distribution changed during acceptance.')
        write(out/'files.json',inventory(out,('verification.json','files.json')));result=verify_evidence(out,commit);write(out/'verification.json',result);return result
    except BaseException as error:
        write(out/'failure.json',dict(status='FAIL',installed_acceptance=False,error=str(error),execution_id=nonce,expected_commit=commit,seconds=time.monotonic()-started));raise


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--executable',type=Path);parser.add_argument('--out',type=Path);parser.add_argument('--expected-commit',required=True);parser.add_argument('--timeout',type=float,default=900);parser.add_argument('--readback',type=Path)
    args=parser.parse_args()
    if args.readback:result=verify_evidence(args.readback,args.expected_commit)
    else:
        require(args.executable is not None and args.out is not None,'Live verification requires executable and out.');result=verify(args.executable,args.out,args.expected_commit,args.timeout)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
