"""Independent selected installed parallel-array GUI and queued-native gate.

Thirty actual arrays, attached-route editing, fault/repair and blocked-engine
behavior are checked here. Electrical DC/AC is a separate linked gate.
"""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path,PurePosixPath
import re
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.verify_frozen_mim import (require,sha,digest,load,relative,unlinked,confined,inventory,file_map,
    package,git_environment,git_blob,expected_inputs,backend_binding,design_hash,content_hash,registry_binding,check_runtime)
from scripts import verify_frozen_metal_resistors as straight
from scripts import audit_sky130_metal_resistor_parallel as source
from scripts import installed_metal_parallel_inputs as inputs
from scripts.audit_sky130_li_case import check_netgen_inputs

MODELS=inputs.MODELS
COUNTS=inputs.COUNTS
CASES=inputs.CASES
STAGES=straight.STAGES
EXTRACTION_SETTINGS=straight.EXTRACTION_SETTINGS
SCOPE=__doc__
stream,same_stream,project_geometry,native_scripts=straight.stream,straight.same_stream,straight.project_geometry,straight.native_scripts
GUI_COUNTS=dict(lifecycle=30,native_layouts=30,fresh_native_jobs=42,queued_jobs=43,width_faults=5,drc_faults=1,repairs=6,blocked=1,
                eco_models=5,eco_transitions=20,late_lock_rejections=5)


def checker_sources(commit):
    names=('scripts/verify_frozen_metal_parallel.py','scripts/installed_metal_parallel_inputs.py',
        'scripts/verify_frozen_mim.py','scripts/verify_frozen_metal_resistors.py','scripts/audit_sky130_metal_resistor_parallel.py',
        'scripts/audit_sky130_metal_resistors_linked.py','scripts/audit_sky130_li_case.py',inputs.CONTRACT)
    files={name:sha(ROOT/name) for name in names};inputs.candidate_sources(files,commit);return files


def case_identity(name,execution_id):
    require(name in CASES and re.fullmatch('[0-9a-f]{32}',execution_id),'Unknown installed array case/nonce.')
    model,count,angle=name.split('-');count=int(count[1:]);angle=int(angle[1:])
    return dict(case=name,model=model,width_um=2,length_um=5,multiplicity=count,rotation=angle,execution_id=execution_id,
                top=f'metal_parallel_{model}_m{count}_r{angle}_{execution_id[:12]}')


def circuit(text,top,model,count,*,extracted=False,width_fault=False):
    require(model in MODELS and type(count) is int and count in (1,2,3,16),'Unknown array circuit selection.')
    rows=[v.split() for v in re.sub(r'\n[ \t]*\+[ \t]*',' ',text).splitlines() if v.strip() and not v.lstrip().startswith('*')]
    require(len(rows)==(count+2 if extracted else 3) and rows[0]==['.subckt',top,'R1','R2'] and
            rows[-1] in (['.ends'],['.ends',top]),'Actual array primitive count/interface/directives differ.')
    names=set();units=[]
    for row in rows[1:-1]:
        require(len(row) in (6,7) and re.fullmatch(r'R\S+',row[0],re.I) and row[0].lower() not in names and
                (set(row[1:3])=={'R1','R2'} if extracted else row[1:3]==['R1','R2']) and
                row[3]=='sky130_fd_pr__res_generic_'+model,'Array primitive model/name/two-net graph differs.')
        names.add(row[0].lower());parameters={}
        for token in row[4:]:
            pair=token.split('=');require(len(pair)==2 and pair[0] not in parameters,'Duplicate or malformed native parameter.')
            parameters[pair[0]]=float(pair[1])
        require(all(math.isfinite(v) for v in parameters.values()) and
                set(parameters) in (({'w','l'},{'w','l','m'}) if extracted else ({'w','l','m'},)) and
                parameters['l']==5 and parameters.get('m',1)==(1 if extracted else count),'Array unit parameters/multiplicity differ.')
        units.append(dict(name=row[0],terminals=row[1:3],model=row[3],width_um=parameters['w'],length_um=parameters['l'],multiplicity=parameters.get('m',1)))
    expected=[2,2,3] if width_fault else [2]*(count if extracted else 1)
    require(sorted(v['width_um'] for v in units)==expected and (not width_fault or extracted and count==3),
            'Actual array unit widths differ.')
    return units


def geometry(folder,source_gds,item,fault=None):
    import klayout.db as db
    target=source.expected_geometry(item['model'],2,5,item['multiplicity'],item['rotation'])
    same_stream(stream(source_gds,item['top']),target)
    if fault=='width':
        require(item['multiplicity']==3 and item['rotation']==0,'Width control selected another array.')
        target=source.fault_geometry(item['model'],'one-unit-width')
    elif fault=='drc':
        masks,labels=target;masks={k:v.dup() for k,v in masks.items()}
        masks.setdefault((68,20),db.Region()).insert(db.Box(100000,100000,100100,100100));target=masks,labels
    else:require(fault is None,'Unknown installed array fault.')
    for name in ('original.gds','layout.gds'):same_stream(stream(folder/name,item['top']),target)
    for name in ('input.icproj','original.gds.icstudio.json'):project_geometry(load(folder/name),target)


def native_output(folder,native,item,fault=None):
    require(fault in (None,'width','drc'),'Unknown installed array native control.')
    rows=native['stages'];states=['passed']*6
    if fault=='width':states[4]='failed'
    elif fault=='drc':states[2]='failed'
    require([v['name'] for v in rows]==list(STAGES) and [v['status'] for v in rows]==states and
            native['status']==('failed' if fault else 'passed') and native['drc_engine']==native['lvs_extractor']=='magic' and
            native['magic_drc_style']=='drc(full)','Native array stage/tool/outcome differs.')
    stages={v['name']:v for v in rows}
    for name in ('drc/console.log','lvs-extraction/console.log'):
        text=(folder/name).read_text();require(re.findall(r'^STUDIO_MAGIC_COMPLETE[ \t]*$',text,re.M)==['STUDIO_MAGIC_COMPLETE'] and
            not re.search(r'STUDIO_MAGIC_ERROR|contained errors|Malformed line|Illegal keyword|invalid command name',text,re.I),
            'Native array engine did not complete: '+name)
    text=(folder/'drc/console.log').read_text();counts=re.findall(r'^STUDIO_DRC_COUNT (\d+)[ \t]*$',text,re.M)
    require(len(counts)==1 and int(counts[0])==native['drc_count']==native['magic_drc_count'] and
            (int(counts[0])>0 if fault=='drc' else counts==['0']) and re.findall(r'^STUDIO_DRC_STYLE (.+)$',text,re.M)==['drc(full)'],
            'Actual native full array DRC differs.')
    findings=(folder/'drc/findings.tsv').read_text().splitlines();require(bool(findings)==(fault=='drc'),'Native array DRC findings differ.')
    for line in findings:
        rule,coords=line.split('\t');values=list(map(float,coords.split(',')))
        require(rule and len(values)==4 and all(map(math.isfinite,values)),'Malformed array DRC finding.')
    circuit((folder/'lvs-extraction/extracted.spice').read_text(),item['top'],item['model'],item['multiplicity'],
            extracted=True,width_fault=fault=='width')
    require((folder/'lvs-extraction'/(item['top']+'.ext')).is_file(),'Actual original array extraction database missing.')
    log=(folder/'lvs/lvs.log').read_text();require(not re.search(r'invalid command|could not open|cannot open|Error in',log,re.I),
            'Array native comparison failed for infrastructure reasons.')
    if fault=='width':
        # The actual unique top remains bound below; normalize just the report's
        # exact top name for the previously reviewed property-log grammar.
        require(re.findall(r'^The following cells had property errors:\n ([^\n]+)$',log,re.M)==[item['top']],
                'Property comparison belongs to another native top.')
        source.parallel_property_mismatch(log.replace(item['top'],'coupon'),item['model'],'one-unit-width')
    else:
        require(re.findall(r'^Final result: (.+)$',log,re.M)==['Circuits match uniquely.'] and 'Cell pin lists are equivalent.' in log and
                not re.search(r'Property errors|Circuits do not match|Netlists do not match|disconnected node:|\(no matching pin\)|pin lists[^\n]*altered',log,re.I),
                'Actual native arrays do not match uniquely without property errors.')
    require(stages['lvs_extraction']['evidence']==dict(deck='lvs-extraction/extracted.spice',sha256=sha(folder/'lvs-extraction/extracted.spice'),
                settings=EXTRACTION_SETTINGS),'Array extraction settings/file binding differ.')
    if fault=='width':
        require(stages['lvs']==dict(name='lvs',status='failed',error='Netgen did not establish a unique match with equivalent connected pins and no property errors. See lvs/lvs.log.'),
                'Width control lacks actual native property failure.')
    else:require(stages['lvs']['evidence']==dict(unique_match=True,log='lvs/lvs.log'),'Array LVS receipt differs.')
    integrity=stages['integrity']['evidence'];file_map(folder,integrity['files'])
    require(integrity['verified'] is True and {'layout.gds','input.icproj','schematic.spice','schematic-lvs.spice',
            'drc/console.log','lvs-extraction/extracted.spice','lvs/lvs.log'}<=integrity['files'].keys(),
            'Native array integrity coverage is incomplete.')
    return stages


def editor_binding(project,item,current,*,routes=None):
    cell=straight.project_binding(project,item['model'],2,5,item['multiplicity'],current,item['top'])
    # Top identity is checked against the actual nonce-bound artifact above.
    # Only checked top metadata and the already-validated numeric expression
    # values are adapted for the literal-mask validator. Actual project bytes,
    # shapes, devices, pins and generation records remain unchanged.
    adapted=copy.deepcopy(project);adapted['cells'][0]['name']='coupon'
    values=adapted['cells'][0]['devices'][0]['model_params']
    adapted['cells'][0]['devices'][0]['model_params']={key:float(value) for key,value in values.items()}
    source.editor_project(adapted,current,item,item.get('rotation',0),routes=routes)
    return cell


def lifecycle(root,report,current):
    require(report['binding_lifecycle']==[],'Historical qualification must remain in its existing separate gate.')
    rows=report['lifecycle'];require([v.get('case') for v in rows]==list(CASES),'Incomplete/duplicated GUI array cases.')
    for row in rows:
        item=case_identity(row['case'],report['execution_id'])
        require(all(row.get(k)==v for k,v in item.items()) and row['terminals']==['R1','R2'] and
                Path(row['execution_root']).resolve()==root,'Stale or substituted array lifecycle identity.')
        path=confined(root,row['project']);project=load(path)
        require(sha(path)==row['project_sha256'] and design_hash(project)==row['design_hash'],'Saved array project differs.')
        cell=editor_binding(project,item,current);registry_binding(root,report,project,current)
        require(cell['pdk_layouts']==row['generation'],'Array linked generation record differs.')
        reference=confined(root,row['reference']);circuit(reference.read_text(),item['top'],item['model'],item['multiplicity'])
        straight.emitted_schematic(root,row,project)
        require(sha(reference)==row['reference_sha256'] and sha(confined(root,row['schematic']))==row['schematic_sha256'],
                'Actual array SPICE export differs.')
        for key in ('gds','oas'):
            path=confined(root,row[key]);require(sha(path)==row[key+'_sha256'],'Array written stream identity differs.')
            same_stream(stream(path,item['top']),source.expected_geometry(item['model'],2,5,item['multiplicity'],item['rotation']))
        checks=row['editor_checks'];pins={v['pin']:v['id'] for v in cell['layout_pins']}
        roles={v['generator_role']:v['id'] for v in cell['shapes'] if v['generator_role'] in ('metal_resistor:conductor','metal_resistor:marker')}
        require(checks['initial_count']==1 and checks['undo_redo'] is checks['count_undo_redo'] is True and
                checks['initial_pin_ids']==checks['regenerated_pin_ids']==pins and checks['initial_shape_roles']==roles and
                re.fullmatch('[0-9a-f]{64}',checks['initial_shape_hash']),'Array count-edit identity differs.')


def eco_lifecycle(root,report,current):
    require([v.get('model') for v in report['eco_lifecycle']]==list(MODELS),'Missing attached-route model coverage.')
    def content(value):
        result=copy.deepcopy({k:v for k,v in value.items() if k not in ('revision','modified')})
        for cell in result['cells']:cell.setdefault('labels',[])
        return result
    for model,row in zip(MODELS,report['eco_lifecycle']):
        folder=confined(root,row['folder']);top=f'metal_parallel_eco_{model}_{report["execution_id"][:12]}'
        require(folder==root/'eco'/model and row['top']==top and row['execution_id']==report['execution_id'] and row['status']=='passed',
                'Attached-route lifecycle belongs to another case.')
        before=load(confined(root,row['before_project']));require(confined(root,row['before_project'])==folder/'before.icproj','ECO initial project path differs.')
        item=dict(model=model,width_um=2,length_um=5,multiplicity=1,rotation=0,top=top)
        routes=row['routes'];cell=editor_binding(before,item,current,routes=routes)
        layer=next(v['name'] for v in before['pdk']['layers'] if (v['gds'],v['datatype'])==(source.LAYERS[model],20))
        expected_routes=[dict(id='parallel-route-a',kind='path',layer=layer,points=[[1000,-250],[-2000,-250]],width=400,net='R1',device_id=''),
                         dict(id='parallel-route-b',kind='path',layer=layer,points=[[1000,5250],[-2000,5250]],width=400,net='R2',device_id='')]
        pins={v['pin']:v['id'] for v in cell['layout_pins']};first={v['generator_role']:v['id'] for v in cell['shapes'] if v.get('generator_role')}
        require(routes==expected_routes and row['initial_pin_ids']==pins and row['initial_shape_roles']==first and
                [v['multiplicity'] for v in row['events']]==[3,16,2,1],'ECO initial route/unit identity differs.')
        previous=before
        for count,event in zip((3,16,2,1),row['events']):
            dest=confined(root,event['folder']);require(dest==folder/f'm{count}' and event['status']=='passed' and
                event['late_lock_rejected'] is (count==3),'ECO count folder/outcome differs.')
            states={k:load(dest/(k+'.icproj')) for k in ('before','requested','proposed','applied','undo','restored','reopened')}
            require(content(states['before'])==content(previous),'ECO sequence substituted another design.')
            wanted=copy.deepcopy(states['before']);wanted['cells'][0]['devices'][0]['model_params']['mult']=str(count)
            require(content(wanted)==content(states['requested']) and content(states['requested'])==content(states['undo']),
                    'ECO schematic request or actual undo differs.')
            require(states['proposed']['cells']==states['applied']['cells']==states['restored']['cells']==states['reopened']['cells'],
                    'Actual preview/apply/redo/reopen states differ.')
            for name in ('proposed','applied','restored','reopened'):
                state=states[name];cell=editor_binding(state,{**item,'multiplicity':count},current,routes=routes)
                require({v['pin']:v['id'] for v in cell['layout_pins']}==pins and
                        {v['generator_role']:v['id'] for v in cell['shapes'] if v.get('generator_role') in first}==first,
                        'ECO regeneration moved first-unit pin/shape identity.')
                registry_binding(root,report,state,current)
            if count==3:require(content(load(dest/'late-locked.icproj'))==content(states['requested']),'Late lock allowed partial ECO mutation.')
            reopened=event['reopened'];saved=confined(root,reopened['project'])
            require(saved==dest/'reopened/project.icproj' and sha(saved)==reopened['project_sha256'] and
                    design_hash(load(saved))==reopened['design_hash'] and content(load(saved))==content(states['reopened']),
                    'ECO actual saved/reopened project differs.')
            circuit(confined(root,reopened['reference']).read_text(),top,model,count);straight.emitted_schematic(root,reopened,states['reopened'])
            previous=states['reopened']


def envelope(root,report,current):
    require(report['acceptance_contract_sha256']==inputs.CONTRACT_SHA and report['input_guards']==dict(
        bundled_package_unchanged=True,registry_assets_unchanged=True,executable_unchanged=True,physical_package_unchanged=True),
        'Missing exact installed-array contract or before/after input guards.')
    require(sha(root/'files.json')==report['files_sha256'] and load(root/'files.json')==inventory(root,('files.json','report.json')),
            'Array probe complete inventory differs.')
    lifecycle(root,report,current);eco_lifecycle(root,report,current)


def source_audit(root,reviewed_source=None):
    root=unlinked(root).resolve();report=load(root/'report.json');reviewed=unlinked(reviewed_source or ROOT).resolve()
    require(report.get('schema')==1 and report.get('status')=='passed' and report.get('mode')=='physical' and
            report.get('frozen') is False and report.get('native_execution') is True and
            all(report.get(k) is False for k in ('qualified','release_ready','full_family','installed_acceptance')) and
            not report.get('error') and not report.get('errors'),'Source array pilot is incomplete or overclaims installation.')
    require(Path(report['execution_root']).resolve()==root and Path(report['resource_root']).resolve()==reviewed and
            re.fullmatch('[0-9a-f]{32}',report['execution_id']),'Source array execution/resource identity differs.')
    _,spec,_=inputs.contracts();current=package(reviewed/'icstudio/assets/pdks/sky130A',spec['package']['manifest_sha256'])
    lock=reviewed/'examples/sky130-qualification-lock.json';physical_path=unlinked(report['physical_package']['path']).resolve()
    physical=package(physical_path,load(lock)['manifest_sha256'])
    require(sha(root/'bundled-package.json')==spec['package']['manifest_sha256'] and
            sha(root/'bundled-collection.json')==sha(reviewed/'icstudio/assets/pdks/collection.json') and
            sha(root/'physical-release-lock.json')==sha(lock) and sha(root/'physical-package.json')==sha(physical_path/'package.json') and
            report['physical_package']['files']==physical['files'] and report['bundled_package']['files']==current['files'],
            'Source array package/collection/physical lock differs.')
    envelope(root,report,current);require([v.get('case') for v in report['physical']]==list(CASES),'Incomplete source native array cases.')
    jobs=[physical_job(root,row,item,report,physical,None,None) for row,item in zip(report['physical'],report['lifecycle'])]
    controls(root,report,physical,None,None,jobs)
    return dict(schema=1,status='PASS',gate='metal-parallel-source-gui-queued-layout',scope=SCOPE,qualified=False,
        release_ready=False,full_family=False,installed_acceptance=False,execution_id=report['execution_id'],
        report_sha256=sha(root/'report.json'),files_sha256=sha(root/'files.json'),counts=GUI_COUNTS)


def audit(root,executable,physical_root,expected_commit,execution_id,inputs,backend,payload_hash):
    root=unlinked(root).resolve();report=load(root/'report.json');header(report,executable,expected_commit,execution_id)
    sources=checker_sources(expected_commit);bundle=Path(executable).resolve().parent/'_internal'
    require(Path(report['resource_root']).resolve()==bundle and Path(report['execution_root']).resolve()==root,
            'Installed arrays used external resources/evidence.')
    current=package(bundle/'icstudio/assets/pdks/sky130A',inputs['package_sha256']);physical=package(physical_root,inputs['physical_sha256'])
    for name,expected in (('bundled-package.json',inputs['package_sha256']),('bundled-collection.json',inputs['collection_sha256']),
                         ('physical-package.json',inputs['physical_sha256']),('physical-release-lock.json',inputs['physical_lock_sha256'])):
        require(sha(root/name)==expected,'Captured installed array package/lock differs: '+name)
    require(report['bundled_package']['manifest_sha256']==inputs['package_sha256'] and report['bundled_package']['files']==current['files'] and
            report['physical_package']['files']==physical['files'] and report['physical_package']['manifest_sha256']==inputs['physical_sha256'] and
            Path(report['physical_package']['path']).resolve()==Path(physical_root).resolve(),'Reported array package input differs.')
    envelope(root,report,current);runtime,runtime_files=check_runtime(root,report,bundle,backend,payload_hash)
    require([v.get('case') for v in report['physical']]==list(CASES),'Incomplete installed native array cases.')
    jobs=[physical_job(root,row,item,report,physical,runtime,runtime_files) for row,item in zip(report['physical'],report['lifecycle'])]
    controls(root,report,physical,runtime,runtime_files,jobs)
    return dict(schema=1,status='PASS',gate='metal-parallel-installed-gui-queued-layout',scope=SCOPE,qualified=False,
        release_ready=False,full_family=False,expected_commit=expected_commit,execution_id=execution_id,
        report_sha256=sha(root/'report.json'),files_sha256=sha(root/'files.json'),executable_sha256=sha(executable),
        package_inputs=inputs,counts=GUI_COUNTS,runtime=runtime,backend_files_sha256=digest(backend),checker_sources=sources)


def physical_job(root, row, item, report, physical, runtime, runtime_files, fault=None):
    require(row['execution_id'] == report['execution_id'] and row['top'] == item['top'] and
            row['native_execution'] is True and row['state'] == 'Complete', 'Native case is stale or incomplete.')
    job_root = confined(root, row['job_directory']); folder = confined(root, row['evidence_directory'])
    require(folder == job_root/'physical-flow' and job_root.name == row['job_id'], 'Queued job directory identity differs.')
    require(sha(job_root/'input.json') == row['input_sha256'] and sha(job_root/'result.json') == row['result_sha256'], 'Queued input/result changed.')
    job = load(job_root/'input.json'); result = load(job_root/'result.json')
    require(all(row[k] == item[k] for k in ('model', 'width_um', 'length_um', 'rotation', 'multiplicity', 'top', 'terminals')) and
            row['source_case'] == item['case'] and Path(row['execution_root']).resolve() == root and
            row['reference'] == item['reference'] and row['reference_sha256'] == item['reference_sha256'] and
            row['project_revision'] == job['project']['revision'], 'Queued case metadata differs from actual GUI inputs.')
    require(not result.get('reused_from') and result['silicon_report'] == row['report'] and result['settings'] == row['settings'] and
            design_hash(job['project']) == row['design_hash'] == result['design_hash'], 'Queued input/result binding differs.')
    settings = job['settings']
    require(settings['verification_mode'] == 'drc_lvs' and settings['drc_engine'] == settings['lvs_extractor'] == 'magic',
            'Queued physical settings differ.')
    if runtime is not None:
        require(settings['physical_toolchain'] == 'included' and settings['physical_runtime'] == runtime,
                'Queued job did not select shipped physical runtime.')
    else:
        require(report['frozen'] is False and settings['physical_toolchain'] == 'custom' and
                not row['report'].get('execution'), 'Source pilot must explicitly use local custom tools.')
    text = confined(root, item['reference']).read_text()
    require(settings['reference'] == dict(text=text, top=item['top'], ports=['R1', 'R2'], sha256=hashlib.sha256(text.encode()).hexdigest()),
            'Queued schematic differs from GUI export.')
    native = load(folder/'report.json')
    if runtime is not None:
        execution = row['report']['execution']; native_job = load(job_root/'physical-backend-input.json')
        require(execution['runtime'] == runtime and sha(job_root/'physical-backend-input.json') == execution['native_input_sha256'],
                'Managed native input identity differs.')
        received = load(job_root/'physical-artifacts.json')
        require(execution['received_files'] == received, 'Received artifact inventory differs.'); file_map(job_root, received)
        actual = {'physical-flow/'+name: value for name, value in inventory(folder).items()}
        actual['physical-backend-result.json'] = sha(job_root/'physical-backend-result.json')
        require(received == actual, 'Native transfer inventory omitted or added an artifact.')
        backend_result = load(job_root/'physical-backend-result.json')
        require(backend_result['silicon_report'] == native, 'Backend report differs.')
        expected_project = copy.deepcopy(job['project']); native_dir = execution['native_directory']
        expected_project['pdk']['package_root'] = native_dir+'/pdk'
        require(native_job['project'] == expected_project and native_job['cell'] == job['cell'], 'Managed transfer changed project data.')
        origin = native_dir+'/output/physical-flow'; pdk = native_dir+'/pdk'
        prefix = '/' if runtime['kind'] == 'wsl' else runtime['root'].rstrip('/')+'/'
        tools = {name: dict(path=prefix+'opt/icstudio/bin/'+name, sha256=runtime_files['opt/icstudio/bin/'+name]) for name in ('magic', 'netgen')}
    else:
        native_job = job; origin = folder.as_posix(); pdk = Path(job['project']['pdk']['package_root']).as_posix()
        require(Path(pdk).resolve() == Path(report['physical_package']['path']).resolve(), 'Source physical adapter differs.')
        tools = {name: dict(path=settings['tools'][name], sha256=sha(unlinked(settings['tools'][name]))) for name in ('magic', 'netgen')}
    require(native['design_hash'] == design_hash(native_job['project']) and load(folder/'input.icproj') == native_job['project'] and
            native['cell_name'] == item['top'], 'Native project/result belongs to another case.')
    require(native_job['project']['pdk']['package_lock'] == {k: physical[k] for k in ('id', 'revision', 'files')}, 'Native physical lock differs.')
    stages = native_output(folder, native, item, fault)
    for key in ('status', 'stages', 'reference', 'drc_count'):
        require(row['report'][key] == native[key], 'Host/native report differs: '+key)
    native_scripts(folder, origin, pdk, item['top'])
    assets = {pdk+'/'+name: value for name, value in physical['files'].items() if name.startswith(('libs.tech/magic/', 'libs.tech/netgen/'))}
    for name in ('preflight', 'integrity'):
        require(stages[name]['evidence']['assets'] == assets and stages[name]['evidence']['tools'] == tools,
                'Native PDK/tool identity differs from installed runtime.')
    require((folder/'schematic.spice').read_text() == text, 'Native reference was substituted.')
    circuit((folder/'schematic-lvs.spice').read_text(), item['top'], item['model'], item['multiplicity'])
    console = (folder/'lvs/console.log').read_text()
    from scripts.audit_sky130_li_case import check_netgen_inputs
    check_netgen_inputs(console, PurePosixPath(origin), PurePosixPath(pdk))
    geometry(folder, confined(root, item['gds']), item, fault)
    if fault is None and row['case'] == item['case']:
        require(confined(root, item['native']) == folder/'lvs-extraction/extracted.spice' and
                item['native_sha256'] == sha(folder/'lvs-extraction/extracted.spice') and item['native_job_id'] == row['job_id'] and
                item['native_design_hash'] == row['design_hash'], 'Lifecycle extraction does not bind the fresh clean queued job.')
    return job_root


def header(report, executable, expected_commit, execution_id):
    require(report.get('schema') == 1 and report.get('status') == 'passed' and report.get('mode') == 'physical' and
            report.get('frozen') is True and report.get('native_execution') is True, 'Installed parallel-array evidence is incomplete or source-only.')
    build = report.get('build', {})
    require(re.fullmatch('[0-9a-f]{40}', expected_commit) and build.get('commit') == expected_commit and
            build.get('dirty') is False and build.get('frozen') is True, 'Installed evidence belongs to another or dirty build.')
    require(report.get('execution_id') == execution_id and re.fullmatch('[0-9a-f]{32}', execution_id), 'Stale execution identity.')
    require(Path(report['executable']).resolve() == Path(executable).resolve() and report['executable_sha256'] == sha(executable),
            'Installed executable identity differs.')
    require(all(report.get(key) is False for key in ('qualified', 'release_ready', 'full_family', 'installed_acceptance')),
            'Bounded app probe must not self-claim installed or whole-family qualification.')
    require(not report.get('errors') and not report.get('error'), 'Application reported errors.')


def control_edit(original, changed, control, width):
    """Reconstruct the intended project edit independently of the producer."""
    expected = copy.deepcopy(original); cell = expected['cells'][0]
    if width:
        edits = control['edits']; require(len(edits) == 2 and len({r['shape'] for r in edits}) == 2, 'Incomplete width edits.')
        for edit in edits:
            shapes = [r for r in cell['shapes'] if r['id'] == edit['shape']]
            require(len(shapes) == 1, 'Width edit references unknown shape.')
            shape = shapes[0]; before = shape['points']
            require(shape['layer'] == edit['layer'] and before == edit['before_points'] and
                    len(before) in (2, 4) and len({p[1] for p in before}) == 2, 'Width edit initial identity differs.')
            xs = {p[0] for p in before}; require(len(xs) == 2 and min(xs) == 10000 and max(xs)-min(xs) == 2000, 'Width control initial dimensions differ.')
            after = [[x+1000 if x == max(xs) else x, y] for x, y in before]
            require(after == edit['after_points'], 'Width control did not change exactly the right edge.')
            shape['points'] = after
    else:
        shape = control['added_shape']; require(shape['id'] not in {r['id'] for r in cell['shapes']}, 'DRC control reused an existing shape.')
        layers = {r['name']: (r['gds'], r['datatype']) for r in expected['pdk']['layers']}
        require(layers[shape['layer']] == (68, 20) and shape['kind'] == 'rect' and
                shape['points'] == [[100000, 100000], [100100, 100100]], 'DRC control did not add the selected narrow metal.')
        cell['shapes'].append(shape)
    # The real shape actions normalize absent schematic labels to an empty
    # list. No actual label may be added during either physical edit.
    if 'labels' not in cell and changed['cells'][0].get('labels') == []:
        cell['labels'] = []
    require(content_hash(expected) == content_hash(changed), 'Fault project changed more than the intended physical edit.')


def controls(root, report, physical, runtime, runtime_files, jobs):
    rows = report['controls']
    require(len(rows) == 7 and [r.get('kind') for r in rows] == ['width-cycle']*5+['narrow-metal-cycle', 'missing-engine'],
            'Missing width/repair/DRC/block controls.')
    items = {r['case']: r for r in report['lifecycle']}; clean = {r['case']: r for r in report['physical']}
    for index, control in enumerate(rows[:6]):
        name = MODELS[index]+'-m3-r0' if index < 5 else 'm4-m16-r90'
        require(control['source_case'] == name, 'Control belongs to another case.')
        item = items[name]; baseline = clean[name]; fault = control['fault']; repair = control['repair']
        require(control['baseline_design_hash'] == baseline['design_hash'] != repair['design_hash'] and
                control['after_design_hash'] == fault['design_hash'] != baseline['design_hash'] and control['displayed'] is True,
                'Edit invalidation/repair identity differs.')
        fault_root = physical_job(root, fault, item, report, physical, runtime, runtime_files, 'width' if index < 5 else 'drc')
        repaired_root = physical_job(root, repair, item, report, physical, runtime, runtime_files)
        original = load(confined(root, baseline['job_directory'])/'input.json')['project']
        control_edit(original, load(fault_root/'input.json')['project'], control, index < 5)
        repaired = load(repaired_root/'input.json')['project']
        require(set(control['projects'])=={'before','fault','repaired'},'Missing actual saved control states.')
        for name,value in (('before',original),('fault',load(fault_root/'input.json')['project']),('repaired',repaired)):
            require(load(confined(root,control['projects'][name]))==value,'Saved control state differs from queued native input.')
        require(content_hash(original) == content_hash(repaired) == control['before_content_hash'] == control['repaired_content_hash'],
                'Repair changed design content beyond revision/modified.')
        jobs.extend((fault_root, repaired_root))
    blocked = rows[-1]['job']; item = items['m4-m16-r90']; repaired = rows[-2]['repair']
    require(rows[-1]['source_case'] == item['case'], 'Missing-engine case differs.')
    folder = confined(root, blocked['job_directory']); result = load(folder/'result.json'); job = load(folder/'input.json')
    require(folder.name == blocked['job_id'] and blocked['execution_id'] == report['execution_id'] and blocked['top'] == item['top'] and
            blocked['state'] == 'Complete' and blocked['native_execution'] is False and
            sha(folder/'input.json') == blocked['input_sha256'] and sha(folder/'result.json') == blocked['result_sha256'] and
            result['silicon_report'] == blocked['report'] and not result.get('reused_from') and
            blocked['report']['status'] == 'blocked' and [(s['name'], s['status']) for s in blocked['report']['stages']] ==
            [(name, 'failed' if name == 'preflight' else 'not_run') for name in STAGES] and
            not blocked['report'].get('execution') and not (folder/'physical-artifacts.json').exists(), 'Missing engine did not block before native execution.')
    require(job['settings']['physical_toolchain'] == 'custom' and
            Path(job['settings']['tools']['magic']).resolve() == root/'missing-magic-executable' and
            not (root/'missing-magic-executable').exists() and
            design_hash(job['project']) == blocked['design_hash'] == result['design_hash'] == repaired['design_hash'],
            'Missing-engine control selected another executable/project.')
    jobs.append(folder)
    require(len(jobs) == len(set(jobs)) == 43, 'Physical cases reused a job directory.')


def verify(executable, physical_pdk, out, expected_commit, timeout=2400):
    executable = unlinked(executable).resolve(); physical_pdk = unlinked(physical_pdk).resolve(); out = unlinked(out).resolve()
    require(re.fullmatch('[0-9a-f]{40}', expected_commit) and math.isfinite(timeout) and timeout > 0, 'Choose exact candidate and finite positive deadline.')
    require(not out.exists(), 'Use a new output directory; existing evidence cannot qualify as fresh.')
    out.mkdir(parents=True); started = time.monotonic(); execution_id = uuid.uuid4().hex
    try:
        inputs = expected_inputs(expected_commit); bundle = executable.parent/'_internal'
        package(bundle/'icstudio/assets/pdks/sky130A', inputs['package_sha256']); package(physical_pdk, inputs['physical_sha256'])
        require(sha(bundle/'icstudio/assets/pdks/collection.json') == inputs['collection_sha256'], 'Bundled collection differs.')
        payload = bundle/'icstudio/assets/runtime/digital'; payload_hash = sha(payload/'manifest.json'); manifest = load(payload/'manifest.json')
        require(manifest.get('schema') == 1 and manifest.get('archive') == 'runtime.tar.gz' and
                sha(payload/'runtime.tar.gz') == manifest['sha256'], 'Bundled runtime archive missing or changed.')
        backend = backend_binding(payload/'backend/icstudio', expected_commit); exe_hash = sha(executable)
        env = git_environment()
        for key in list(env):
            if key.upper() in ('PYTHONPATH', 'PYTHONHOME', 'ICSTUDIO_DIGITAL_PAYLOAD', 'ICSTUDIO_DIGITAL_NATIVE',
                              'ICSTUDIO_BUNDLED_NGSPICE', 'ICSTUDIO_NGSPICE', 'LD_LIBRARY_PATH', 'LD_PRELOAD'):
                env.pop(key)
        env['QT_QPA_PLATFORM'] = 'offscreen'
        if not env.get('ICSTUDIO_DIGITAL_STATE'):
            base = Path(env['LOCALAPPDATA']) if os.name == 'nt' else Path(env.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
            env['ICSTUDIO_DIGITAL_STATE'] = str(base/'ICDesignStudio/digital')
        command = [str(executable), '--metal-parallel-acceptance', '--mode', 'physical', '--managed',
                   '--physical-pdk', str(physical_pdk), '--execution-id', execution_id, '--out', str(out/'probe')]
        (out/'invocation.json').write_text(json.dumps(dict(command=command, expected_commit=expected_commit,
            execution_id=execution_id, executable_sha256=exe_hash, inputs=inputs, payload_manifest_sha256=payload_hash), indent=2))
        with (out/'launcher.log').open('wb') as log:
            subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=True)
        require(sha(executable) == exe_hash and sha(payload/'manifest.json') == payload_hash and
                backend_binding(payload/'backend/icstudio', expected_commit) == backend, 'Installed executable/backend/payload changed during acceptance.')
        result = audit(out/'probe', executable, physical_pdk, expected_commit, execution_id, inputs, backend, payload_hash)
        result.update(seconds=time.monotonic()-started, timeout_seconds=timeout)
        (out/'verification.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n'); return result
    except Exception as exc:
        if isinstance(exc, subprocess.TimeoutExpired):
            for path in (out/'probe/runs with spaces').glob('*/*/input.json'):
                if load(path).get('settings', {}).get('physical_runtime'): (path.parent/'digital-cancel').write_text('cancel\n')
        (out/'verification.json').write_text(json.dumps(dict(schema=1, status='FAIL', scope=SCOPE,
            qualified=False, release_ready=False, full_family=False, expected_commit=expected_commit,
            execution_id=execution_id, error=str(exc), seconds=time.monotonic()-started), indent=2)+'\n')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('executable', 'physical-pdk', 'out'): parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--expected-commit', required=True); parser.add_argument('--timeout', type=float, default=2400)
    args = parser.parse_args(); print(json.dumps(verify(args.executable, args.physical_pdk, args.out, args.expected_commit, args.timeout), indent=2))


if __name__=='__main__':main()


