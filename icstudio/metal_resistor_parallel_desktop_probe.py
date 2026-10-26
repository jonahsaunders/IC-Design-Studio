"""Additive selected parallel-resistor GUI and fresh queued physical acceptance.

Source execution is a prototype only. Frozen execution requires included tools;
an independent launcher/checker establishes installed provenance and electrical
acceptance. Existing single-unit and historical-binding gates remain separate.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import time
import traceback

from .model import clone,digest,design_digest,file_digest,save_project
from .mim_desktop_probe import STAGES,capture_runtime,generate,queue_layout,require,save_reopen,selected_file,submit_form,verified_package,write
from .metal_resistor_desktop_probe import place_edit,content

MODELS=('l1','m1','m2','m3','m4')
COUNTS=(2,3,16)
CASES=tuple((model,count,angle) for model in MODELS for count in COUNTS for angle in (0,90))
CONTRACT_SHA='f2cf30ea793449d541305b2c10a57c8bbdf5cfadf2ab7b24bb9e99848e309ce9'


def edit_count(app,studio,count):
    from .catalog import binding_for,parameter_values
    device=studio.cell['devices'][0];studio.select([device['id']],'schematic')
    studio.form_fields['modelparam:mult'].setText(str(count))
    require(studio.apply_inspector(True),'The actual inspector rejected parallel multiplicity.')
    app.processEvents()
    device=studio.cell['devices'][0]
    require(parameter_values(binding_for(studio.project['pdk'],device),device)['mult']==count,'Inspector count differs.')


def assigned_ports(app,studio):
    for pin in list(studio.cell['layout_pins']):
        submit_form(app,studio.cell_port_dialog(),dict(name='R1' if pin['pin']=='m' else 'R2',
            layer=pin['layer'],x=pin['point'][0]/1000,y=pin['point'][1]/1000))


def layout_case(app,studio,technology,model,count,angle,folder):
    from .catalog import binding_for,parameter_values
    from .physical import connectivity
    case=f'{model}-m{count}-r{angle}'
    top=f'metal_parallel_{model}_m{count}_r{angle}_{studio.probe_execution_id[:12]}'
    place_edit(app,studio,technology,model,count=1,top=top);generate(app,studio)
    original_shapes=clone(studio.cell['shapes']);pins={v['pin']:v['id'] for v in studio.cell['layout_pins']}
    first={v['generator_role']:v['id'] for v in original_shapes}
    studio.undo();require(not studio.cell.get('pdk_layouts'),'Undo did not remove the initial footprint.')
    studio.redo();require(studio.cell['shapes']==original_shapes,'Redo changed the initial footprint.')
    edit_count(app,studio,count);requested=clone(studio.project);generate(app,studio);applied=clone(studio.project)
    studio.undo();require(studio.project['cells']==requested['cells'],'Undo did not restore the pre-regeneration footprint.')
    studio.redo();require(studio.project['cells']==applied['cells'],'Redo changed the physical array.')
    require(pins=={v['pin']:v['id'] for v in studio.cell['layout_pins']},'Count edit moved terminal identity.')
    require(first=={v['generator_role']:v['id'] for v in studio.cell['shapes'] if v['generator_role'] in first},'Count edit changed first-unit shape identity.')
    require(not connectivity(studio.project,studio.cid)['issues'],'Generated array terminal graph differs.')
    assigned_ports(app,studio)
    if angle:
        studio.select([v['id'] for v in studio.cell['shapes']],'layout')
        submit_form(app,studio.transform_layout_dialog(),dict(rotation=angle,annotations='Yes'))
    row=save_reopen(app,studio,folder)
    for name in ('layout.gds','layout.oas'):
        with selected_file('getSaveFileName',folder/name):studio.export_gds()
    binding=binding_for(studio.project['pdk'],studio.cell['devices'][0]);values=parameter_values(binding,studio.cell['devices'][0])
    require(values==dict(w=2,l=5,mult=count),'Array parameters changed during save/reopen.')
    row.update(case=case,execution_id=studio.probe_execution_id,execution_root=str(folder.parent),top=top,
        model=model,width_um=2,length_um=5,multiplicity=count,rotation=angle,terminals=['R1','R2'],
        binding=dict(model=binding['model'],values=values,model_ref=clone(studio.cell['devices'][0]['model_ref']),emit_parameters=clone(binding['emit_parameters']),terminals=['R1','R2']),
        schematic_sha256=file_digest(folder/'schematic.spice'),reference_sha256=file_digest(folder/'reference.spice'),
        gds=str(folder/'layout.gds'),gds_sha256=file_digest(folder/'layout.gds'),oas=str(folder/'layout.oas'),oas_sha256=file_digest(folder/'layout.oas'),
        generation=clone(studio.cell['pdk_layouts']),editor_checks=dict(initial_count=1,undo_redo=True,count_undo_redo=True,
        initial_shape_hash=digest(original_shapes),initial_shape_roles=first,initial_pin_ids=pins,
        regenerated_pin_ids={v['pin']:v['id'] for v in studio.cell['layout_pins']}))
    return row


def eco_case(app,studio,technology,model,folder):
    from PySide6.QtWidgets import QDialogButtonBox
    from .physical import connectivity
    from .layout_eco import inventory
    from .sky130_metal_resistors import layers
    folder.mkdir(parents=True)
    top=f'metal_parallel_eco_{model}_{studio.probe_execution_id[:12]}'
    place_edit(app,studio,technology,model,count=1,top=top);generate(app,studio);assigned_ports(app,studio)
    did=studio.cell['devices'][0]['id'];pins={v['pin']:v['id'] for v in studio.cell['layout_pins']}
    first={v['generator_role']:v['id'] for v in studio.cell['shapes']};ls=layers(studio.project['pdk'],model)
    routes=[dict(id='parallel-route-a',kind='path',layer=ls['conductor'],points=[[1000,-250],[-2000,-250]],width=400,net='R1',device_id=''),
            dict(id='parallel-route-b',kind='path',layer=ls['conductor'],points=[[1000,5250],[-2000,5250]],width=400,net='R2',device_id='')]
    for route in routes:studio.add_shape(clone(route))
    save_project(studio.project,folder/'before.icproj');events=[]
    def check(count):
        require({v['pin']:v['id'] for v in studio.cell['layout_pins']}==pins,'Routed count edit changed pin identity.')
        require([v for v in studio.cell['shapes'] if v['id'] in ('parallel-route-a','parallel-route-b')]==routes,'Routed count edit changed an attached wire.')
        generated=[v for v in studio.cell['shapes'] if v.get('device_id')==did]
        require(len(generated)==(2 if count==1 else 2*count+2) and sum(v['layer']==ls['marker'] for v in generated)==count,'Obsolete generated units were not removed.')
        require(first=={v['generator_role']:v['id'] for v in generated if v['generator_role'] in first},'First-unit shapes changed identity.')
        require(inventory(studio.project,studio.cid)['devices'][0]['status']=='current' and not connectivity(studio.project,studio.cid)['issues'],'Routed array is stale or disconnected.')
    for count in (3,16,2,1):
        stage=folder/f'm{count}';stage.mkdir();save_project(studio.project,stage/'before.icproj')
        edit_count(app,studio,count);requested=clone(studio.project);save_project(requested,stage/'requested.icproj')
        original_review=studio.review_dialog
        def capture_review(title,build,controls=None,apply_candidate=None):
            def captured_build():
                candidate,description=build();save_project(candidate,stage/'proposed.icproj');return candidate,description
            return original_review(title,captured_build,controls,apply_candidate)
        studio.review_dialog=capture_review
        try:
            form=studio.mos_layout_dialog()
            if form is not None:submit_form(app,form)
        finally:studio.review_dialog=original_review
        require(studio.project==requested,'The count preview changed the active design.')
        review=studio._review_dialog;button=review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
        require(button.isEnabled(),'The actual count review cannot be applied.')
        if count==3:
            studio.layout.locked_layers.add(ls['conductor'])
            try:
                button.click();app.processEvents();require(review.isVisible() and studio.project==requested,'Late layer lock allowed array mutation.')
                save_project(studio.project,stage/'late-locked.icproj')
            finally:studio.layout.locked_layers.discard(ls['conductor'])
        button.click();app.processEvents();require(not review.isVisible(),'Count application did not finish.')
        check(count);applied=clone(studio.project);save_project(applied,stage/'applied.icproj')
        studio.undo();app.processEvents();require(studio.project['cells']==requested['cells'],'Count undo did not restore requested state.')
        save_project(studio.project,stage/'undo.icproj');studio.redo();app.processEvents()
        require(studio.project['cells']==applied['cells'],'Count redo changed the applied state.')
        save_project(studio.project,stage/'restored.icproj');reopened=save_reopen(app,studio,stage/'reopened');check(count)
        save_project(studio.project,stage/'reopened.icproj')
        events.append(dict(multiplicity=count,folder=str(stage),status='passed',late_lock_rejected=count==3,reopened=reopened))
    return dict(model=model,execution_id=studio.probe_execution_id,top=top,folder=str(folder),status='passed',
                before_project=str(folder/'before.icproj'),initial_pin_ids=pins,initial_shape_roles=first,routes=routes,events=events)


def native_array(path,top,model,count,widths=None):
    rows=[line.split() for line in Path(path).read_text().splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(rows)==count+2 and rows[0]==['.subckt',top,'R1','R2'] and rows[-1] in (['.ends'],['.ends',top]),'Native array must contain every separate unit and exact interface.')
    names=set();observed=[]
    for row in rows[1:-1]:
        require(len(row) in (6,7) and re.fullmatch(r'R\S+',row[0],re.I) and row[0].lower() not in names,'Invalid/duplicate native array primitive.')
        names.add(row[0].lower());require(set(row[1:3])=={'R1','R2'} and row[3]=='sky130_fd_pr__res_generic_'+model,'Native array model or shared terminal graph differs.')
        parameters={}
        for token in row[4:]:
            pair=token.split('=');require(len(pair)==2 and pair[0] not in parameters,'Invalid/duplicate native parameter.')
            parameters[pair[0]]=float(pair[1])
        require(set(parameters) in ({'w','l'},{'w','l','m'}) and all(math.isfinite(v) for v in parameters.values()) and parameters['l']==5 and parameters.get('m',1)==1,'Native unit dimensions or multiplicity differ.')
        observed.append(parameters['w'])
    require(sorted(observed)==sorted(widths or [2]*count),'Native unit widths differ.')
    return dict(unit_count=count,widths_um=observed,length_um=5,model='sky130_fd_pr__res_generic_'+model,sha256=file_digest(path))


def queue_case(app,studio,item,case,*,missing=False):
    row=queue_layout(app,studio,item['reference'],case,missing=missing)
    row.update(model=item['model'],width_um=2,length_um=5,rotation=item['rotation'],multiplicity=item['multiplicity'],terminals=['R1','R2'],execution_root=item['execution_root'],source_case=item['case'],reference=item['reference'],reference_sha256=file_digest(item['reference']),project_revision=studio.project['revision'])
    return row


def widened_vertices(points):
    require(len(points) in (2,4) and {v[0] for v in points}=={10000,12000} and len({v[1] for v in points})==2,'Width fault must select the last W2 unit of the nominal three-unit array.')
    return [[13000 if x==12000 else x,y] for x,y in points]


def edit_last_width(app,studio,shape):
    before=clone(shape['points']);after=widened_vertices(before);studio.select([shape['id']],'layout')
    if shape['kind']=='rect':studio.form_fields['Width'].setText('3')
    else:
        require(shape['kind']=='polygon' and studio.vertex_table.rowCount()==len(after),'Expected editable rectangular polygon.')
        for i,point in enumerate(after):
            for axis,value in enumerate(point):studio.vertex_table.item(i,axis).setText(f'{value/1000:g}')
    require(studio.apply_inspector(False),'Actual physical inspector rejected last-unit width edit.');app.processEvents()
    actual=next(v for v in studio.cell['shapes'] if v['id']==shape['id'])
    require(actual['points']==after,'The physical inspector changed unexpected vertices.')
    return dict(shape=shape['id'],layer=shape['layer'],before_points=before,after_points=after)


def width_cycle(app,studio,item,clean,folder):
    from .layout import polygon
    from .sky130_metal_resistors import layers
    folder.mkdir(parents=True);baseline=clone(content(studio.project));before_hash=design_digest(studio.project)
    save_project(studio.project,folder/'before.icproj');ls=layers(studio.project['pdk'],item['model']);shapes=[]
    for shape in studio.cell['shapes']:
        if shape['layer'] not in ls.values():continue
        box=polygon(shape).bbox()
        if box.left==10000 and box.right==12000 and (box.bottom,box.top) in ((0,5000),(-500,5500)):shapes.append(shape)
    require(len(shapes)==2 and {v['layer'] for v in shapes}==set(ls.values()),'Last unit is not independently editable in the exported array.')
    edits=[edit_last_width(app,studio,shape) for shape in shapes];save_project(studio.project,folder/'fault.icproj')
    studio.refresh_silicon();require('STALE' in studio.silicon_status.text(),'A physical array edit did not invalidate prior evidence.')
    faulty=queue_case(app,studio,item,item['model']+'-width-fault');stages={v['name']:v for v in faulty['report']['stages']}
    require(faulty['report']['status']=='failed' and faulty['report']['drc_count']==0 and stages['drc']['status']==stages['lvs_extraction']['status']=='passed' and stages['lvs']['status']=='failed','Last-unit width fault did not reach a clean-DRC/native-LVS mismatch.')
    native_array(Path(faulty['evidence_directory'])/'lvs-extraction/extracted.spice',item['top'],item['model'],3,[2,2,3])
    for _ in edits:studio.undo()
    require(content(studio.project)==baseline and design_digest(studio.project)!=before_hash,'Width undo must restore exact content with a new revision.')
    save_project(studio.project,folder/'repaired.icproj');repair=queue_case(app,studio,item,item['model']+'-width-repaired')
    require(repair['report']['status']=='passed' and len({clean['job_id'],faulty['job_id'],repair['job_id']})==3,'Width repair requires its own fresh passing native job.')
    native_array(Path(repair['evidence_directory'])/'lvs-extraction/extracted.spice',item['top'],item['model'],3)
    return dict(kind='width-cycle',source_case=item['case'],model=item['model'],folder=str(folder),baseline_design_hash=before_hash,before_content_hash=digest(baseline),after_design_hash=faulty['design_hash'],repaired_content_hash=digest(content(studio.project)),displayed=True,edits=edits,fault=faulty,repair=repair,
                projects={name:str(folder/(name+'.icproj')) for name in ('before','fault','repaired')})


def drc_cycle(app,studio,item,folder):
    from .layout import rect
    folder.mkdir(parents=True);baseline=clone(content(studio.project));before_hash=design_digest(studio.project);save_project(studio.project,folder/'before.icproj')
    layer=next(v['name'] for v in studio.project['pdk']['layers'] if (v['gds'],v['datatype'])==(68,20));shape=rect(layer,100000,100000,100,100)
    studio.add_shape(shape);save_project(studio.project,folder/'fault.icproj');studio.refresh_silicon();require('STALE' in studio.silicon_status.text(),'DRC edit did not invalidate previous evidence.')
    faulty=queue_case(app,studio,item,'narrow-metal');stages={v['name']:v for v in faulty['report']['stages']}
    require(faulty['report']['status']=='failed' and stages['drc']['status']=='failed' and faulty['report'].get('drc_count',0)>0,'Narrow metal did not fail actual native DRC.')
    studio.undo();require(content(studio.project)==baseline and design_digest(studio.project)!=before_hash,'DRC undo did not restore exact content with a new revision.')
    save_project(studio.project,folder/'repaired.icproj');repair=queue_case(app,studio,item,'narrow-metal-repaired');require(repair['report']['status']=='passed','Fresh DRC repair did not pass.')
    native_array(Path(repair['evidence_directory'])/'lvs-extraction/extracted.spice',item['top'],item['model'],16)
    return dict(kind='narrow-metal-cycle',source_case=item['case'],folder=str(folder),baseline_design_hash=before_hash,before_content_hash=digest(baseline),after_design_hash=faulty['design_hash'],repaired_content_hash=digest(content(studio.project)),displayed=True,added_shape=shape,fault=faulty,repair=repair,
                projects={name:str(folder/(name+'.icproj')) for name in ('before','fault','repaired')})


def physical_cases(app,studio,lifecycle,technology,arguments,result):
    from .catalog import link_technology
    from .layout_import import read_layout
    from .physical_cells import assign_port,ports
    for item in lifecycle:
        project,_=read_layout(Path(item['gds']));link_technology(project,technology);project['cells'][0]['ports']=['R1','R2']
        labels=ports(project,project['top']);require(len(labels)==2 and {v['name'] for v in labels}=={'R1','R2'},'Actual exported array terminal labels differ.')
        imported_texts=clone(project['cells'][0]['layout_texts'])
        for label in labels:assign_port(project,project['top'],label['name'],label['layer'],label['point'])
        project['cells'][0]['layout_texts']=imported_texts;studio.set_project(project)
        row=queue_case(app,studio,item,item['case']);require(row['report']['status']=='passed' and tuple(v['name'] for v in row['report']['stages'])==STAGES and all(v['status']=='passed' for v in row['report']['stages']),'Selected array did not pass all six native stages.')
        if arguments.managed:
            execution=row['report'].get('execution',{});require(execution.get('runtime',{}).get('kind')==('wsl' if os.name=='nt' else 'linux') and execution.get('received_files'),'Missing included native runtime provenance.')
        native=Path(row['evidence_directory'])/'lvs-extraction/extracted.spice';observed=native_array(native,item['top'],item['model'],item['multiplicity'])
        item.update(native=str(native),native_sha256=file_digest(native),native_job_id=row['job_id'],native_design_hash=row['design_hash'],native_units=observed)
        result['physical'].append(row)
        if (item['multiplicity'],item['rotation'])==(3,0):result['controls'].append(width_cycle(app,studio,item,row,arguments.out/'controls'/item['model']))
        if item is not lifecycle[-1]:continue
        result['controls'].append(drc_cycle(app,studio,item,arguments.out/'controls/narrow-metal'))
        old_mode=studio.settings.value('physical/toolchain','auto');old_magic=studio.settings.value('engine/magic','')
        studio.settings.setValue('physical/toolchain','custom');studio.settings.setValue('engine/magic',str(arguments.out/'missing-magic-executable'))
        try:blocked=queue_case(app,studio,item,'missing-engine',missing=True)
        finally:studio.settings.setValue('physical/toolchain',old_mode);studio.settings.setValue('engine/magic',old_magic)
        require(blocked['report']['status']=='blocked' and 'BLOCKED' in studio.silicon_status.text(),'Missing selected engine did not visibly block preflight.')
        result['controls'].append(dict(kind='missing-engine',source_case=item['case'],job=blocked))


def main(arguments=None):
    started=time.monotonic();parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--execution-id',required=True)
    parser.add_argument('--mode',choices=('lifecycle','physical'),default='physical')
    parser.add_argument('--physical-pdk',type=Path);parser.add_argument('--managed',action='store_true')
    for name in ('magic','netgen'):parser.add_argument('--'+name,default='')
    arguments=parser.parse_args(arguments)
    require(re.fullmatch('[0-9a-f]{32}',arguments.execution_id),'Invalid execution identity.')
    arguments.out=arguments.out.resolve();arguments.out.mkdir(parents=True,exist_ok=False)
    from .build_identity import identity
    from .bundled_pdks import bundle_root
    resources=bundle_root().parents[2]
    result=dict(schema=1,status='failed',mode=arguments.mode,execution_id=arguments.execution_id,
        build=identity(),frozen=bool(getattr(sys,'frozen',False)),execution_root=str(arguments.out),
        executable=str(Path(sys.executable).resolve()),executable_sha256=file_digest(sys.executable),resource_root=str(resources),
        qualified=False,release_ready=False,installed_acceptance=False,full_family=False,native_execution=False,
        acceptance_contract_sha256=CONTRACT_SHA,lifecycle=[],binding_lifecycle=[],eco_lifecycle=[],physical=[],controls=[],
        scope='Additive five-model parallel-array GUI lifecycle and 30 fresh native inputs. '
              'Separate attached-route count edits, five width faults and repairs, DRC fault/repair and missing-engine block. '
              'Historical binding acceptance remains in the unchanged existing gate. '
              'Electrical integration and installed provenance require separate independent acceptance; no full-family or signoff claim.')
    app=studio=None;errors=[]
    try:
        if result['frozen'] and arguments.mode=='physical':
            require(arguments.managed and not arguments.magic and not arguments.netgen,'Frozen physical probe requires included engines.')
        from PySide6.QtCore import QSettings,QStandardPaths
        from PySide6.QtWidgets import QApplication
        from .gui import Studio
        from . import digital_runtime
        if arguments.managed:os.environ.setdefault('ICSTUDIO_DIGITAL_STATE',str(digital_runtime.state_root()))
        os.environ['XDG_DATA_HOME']=str(arguments.out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(arguments.out/'profile/config')
        QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(arguments.out/'profile/settings'))
        QStandardPaths.writableLocation=staticmethod(lambda kind:str(arguments.out/'profile'/str(kind.value)))
        app=QApplication([]);app.setStyle('Fusion');studio=Studio(recover=False);studio.probe_execution_id=arguments.execution_id
        studio.error=lambda error:errors.append(str(error));studio.maybe_save=lambda:True;studio.jobs_dir=arguments.out/'runs with spaces'
        studio.live_check.setChecked(False);studio.resize(1400,960);studio.show()
        root=bundle_root()/'sky130A';collection=bundle_root()/'collection.json'
        entry=next(row for row in json.loads(collection.read_bytes())['packages'] if row['variant']=='sky130A')
        package=verified_package(root,entry['manifest_sha256']);registry=studio.pdk_registry;current_key=registry.install(root/'package.json')
        current=registry.technology(current_key);registry_manifests={current_key:file_digest(registry.root/current_key/'package.json')}
        for model,count,angle in CASES:
            case=f'{model}-m{count}-r{angle}'
            result['lifecycle'].append(layout_case(app,studio,current,model,count,angle,arguments.out/case))
        for model in MODELS:result['eco_lifecycle'].append(eco_case(app,studio,current,model,arguments.out/'eco'/model))
        result['bundled_package']=dict(path=str(root),manifest_sha256=file_digest(root/'package.json'),collection_sha256=file_digest(collection),revision=package['revision'],files=package['files'],current_key=current_key)
        result['registry_manifests']=registry_manifests
        shutil.copyfile(root/'package.json',arguments.out/'bundled-package.json');shutil.copyfile(collection,arguments.out/'bundled-collection.json')
        from .spice_program import find_ngspice
        selected=find_ngspice('');result['simulation_engine_discovery']=dict(path=selected,sha256=file_digest(selected) if selected else None,executed=False)
        if arguments.mode=='physical':
            require(arguments.physical_pdk is not None,'Physical mode requires the explicit locked physical adapter.')
            lock_path=resources/'examples/sky130-qualification-lock.json';lock=json.loads(lock_path.read_bytes())
            physical=verified_package(arguments.physical_pdk,lock['manifest_sha256']);tech=clone(physical['technology'])
            tech.update(package_root=str(arguments.physical_pdk.resolve()),package_lock={key:physical[key] for key in ('id','revision','files')})
            result['physical_package']=dict(path=str(arguments.physical_pdk.resolve()),manifest_sha256=file_digest(arguments.physical_pdk/'package.json'),release_lock_sha256=file_digest(lock_path),revision=physical['revision'],files=physical['files'])
            shutil.copyfile(arguments.physical_pdk/'package.json',arguments.out/'physical-package.json');shutil.copyfile(lock_path,arguments.out/'physical-release-lock.json')
            studio.settings.setValue('physical/toolchain','included' if arguments.managed else 'custom')
            for name in ('magic','netgen'):studio.settings.setValue('engine/'+name,str(arguments.out/('unselected-custom-'+name)) if arguments.managed else getattr(arguments,name))
            if arguments.managed:result['managed_runtime_before']=capture_runtime(arguments.out/'runtime/before',resources,result['frozen'])
            physical_cases(app,studio,result['lifecycle'],tech,arguments,result);result['native_execution']=True
            verified_package(arguments.physical_pdk,lock['manifest_sha256'])
            if arguments.managed:
                result['managed_runtime_after']=capture_runtime(arguments.out/'runtime/after',resources,result['frozen'])
                require(result['managed_runtime_after']==result['managed_runtime_before'],'Included runtime identity changed.')
        registry.verify(current_key)
        require(registry_manifests=={key:file_digest(registry.root/key/'package.json') for key in registry_manifests},'Installed registry manifest changed.')
        verified_package(root,entry['manifest_sha256']);require(file_digest(collection)==result['bundled_package']['collection_sha256'],'Bundled collection changed.')
        require(file_digest(sys.executable)==result['executable_sha256'],'Application executable changed.')
        result['input_guards']=dict(bundled_package_unchanged=True,registry_assets_unchanged=True,executable_unchanged=True,physical_package_unchanged=arguments.mode=='physical')
        require(not errors,'Application errors: '+str(errors));result['status']='passed'
    except Exception:result.update(error=traceback.format_exc(),errors=errors)
    finally:
        if studio:
            if studio.run_manager.busy:studio.run_manager.cancel(studio.run_manager.rows)
            studio.saved_hash=digest(studio.project);studio.close();app.processEvents()
        result['elapsed_seconds']=time.monotonic()-started
        try:
            paths=list(arguments.out.rglob('*'));require(not any(p.is_symlink() or p.is_junction() for p in paths),'Probe evidence must not contain links or junctions.')
            files={p.relative_to(arguments.out).as_posix():file_digest(p) for p in sorted(paths) if p.is_file() and p not in (arguments.out/'files.json',arguments.out/'report.json')}
            write(arguments.out/'files.json',files);result['files_sha256']=file_digest(arguments.out/'files.json')
        except Exception:result.update(status='failed',inventory_error=traceback.format_exc())
        write(arguments.out/'report.json',result)
    print(json.dumps({key:result[key] for key in ('status','mode','execution_id','native_execution','elapsed_seconds')}|dict(report=str(arguments.out/'report.json'),error=result.get('error')),indent=2))
    return int(result['status']!='passed')


if __name__=='__main__':raise SystemExit(main())
