"""Selected IHP resistor desktop lifecycle producer; independent verifier establishes acceptance."""
import argparse,json,os,re,sys,time,traceback,shutil
from pathlib import Path
from .model import clone,digest,file_digest
from .mim_desktop_probe import require,selected_file,submit_form,save_reopen,write,capture_runtime

MODELS=('rsil','rppd','rhigh')
SIZES=((.5,.5),(.5,20),(20,.5),(2,7),(7,2))
CASES=tuple((model,index,via,angle) for model in MODELS for index in range(5) for via in (0,1) for angle in (0,90))
LEGACY={'mos.icproj':'ba0247caf910c00aa6ac fcb8c2ac1948fe1242cd6c64f0aa44e8bf7d26537498'.replace(' ',''),'resistor.icproj':'b4a0bcd9458031cb51ace185411c7fc8e23afc4fc636d5d6279fecf0fe51b01f'}
PACKAGE='da58ba2de122d67d232ab20ca4fb353b70bdc68c00ef4279f9be7da640a68ae0'

def placement(app,studio,tech,model,w,l,top):
    from PySide6.QtCore import Qt
    from .model import example
    from .catalog import binding_for,parameter_values
    p=example('empty');p['pdk']=clone(tech);p['cells'][0].update(name=top,ports=['R1','R2','B']);studio.set_project(p)
    key='sg13g2_pr/'+model+'.sym'
    item=next((studio.library_list.item(i) for i in range(studio.library_list.count()) if studio.library_list.item(i).data(Qt.UserRole)==key),None)
    require(item is not None and not item.data(Qt.UserRole+3),'Required IHP resistor catalog entry is unavailable.')
    studio.library_list.setCurrentItem(item);studio.place_library_button.click();require(studio.schematic.placement is not None,'Library placement failed.')
    studio.place_device_at(300,250);studio.cancel_tool();require(len(studio.cell['devices'])==1,'Expected one placed resistor.')
    d=studio.cell['devices'][0];studio.select([d['id']],'schematic')
    for key,value in {'Name':'R1','net:p':'R1','net:m':'R2','net:body':'B','modelparam:w':f'{w:g}u','modelparam:l':f'{l:g}u','modelparam:m':'1'}.items():studio.form_fields[key].setText(value)
    require(studio.apply_inspector(True),'Inspector rejected IHP resistor parameters.');app.processEvents();d=studio.cell['devices'][0]
    b=binding_for(studio.project['pdk'],d);v=parameter_values(b,d)
    require(b['model']==model and b['pin_order']==['p','m','body'] and d['nets']=={'p':'R1','m':'R2','body':'B'},'IHP resistor binding or nets differ.')
    require(abs(v['w']*1e6-w)<1e-9 and abs(v['l']*1e6-l)<1e-9 and v['m']==1 and v.get('b',0)==0,'IHP resistor W/L or multiplicity differs.')
    return clone(d)

def generate(app,studio,via):
    from PySide6.QtWidgets import QDialogButtonBox
    form=studio.mos_layout_dialog();require(form.fields['terminal_access'].currentText()=='Metal1','Default access must be Metal1.')
    submit_form(app,form,{'terminal_access':'Metal2' if via else 'Metal1'})
    review=studio._review_dialog;apply=review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
    require(apply.isEnabled(),'Generation preview was rejected.');apply.click();app.processEvents()
    require(not review.isVisible() and len(studio.cell.get('pdk_layouts',[]))==1,'Generation was not applied.')

def case(app,studio,tech,model,index,via,angle,folder,execution):
    from .physical import connectivity
    w,l=SIZES[index];name=f'{model}-g{index}-v{via}-r{angle}';top=f'ihp_{model}_g{index}_v{via}_r{angle}_{execution[:12]}'
    d=placement(app,studio,tech,model,w,l,top);generate(app,studio,via)
    shapes=clone(studio.cell['shapes']);pins=clone(studio.cell['layout_pins']);records=clone(studio.cell['pdk_layouts']);studio.undo();require(not studio.cell.get('pdk_layouts'),'Undo did not remove generated device.');studio.redo();require(studio.cell['shapes']==shapes and studio.cell['layout_pins']==pins and studio.cell['pdk_layouts']==records,'Redo changed generated shapes, terminals or footprint identity.')
    require(not connectivity(studio.project,studio.cid)['issues'],'Generated device connectivity failed.')
    expected={'p':'Metal2.drawing' if via else 'Metal1.drawing','m':'Metal2.drawing' if via else 'Metal1.drawing','body':'Metal1.drawing'}
    require({p['pin']:p['layer'] for p in studio.cell['layout_pins']}==expected,'Generated terminal layers differ.')
    for pin in list(studio.cell['layout_pins']):
        submit_form(app,studio.cell_port_dialog(),{'name':{'p':'R1','m':'R2','body':'B'}[pin['pin']],'layer':pin['layer'],'x':pin['point'][0]/1000,'y':pin['point'][1]/1000})
    if angle:
        studio.select([s['id'] for s in studio.cell['shapes']],'layout');submit_form(app,studio.transform_layout_dialog(),{'rotation':angle,'annotations':'Yes'})
    row=save_reopen(app,studio,folder)
    # Save and reopen once more through actual file actions so the verifier has two independent persisted inputs.
    first=folder/'project.icproj';second=folder/'reopened.icproj'
    with selected_file('getSaveFileName',second):require(studio.save(as_new=True),'Reopened project save failed.')
    with selected_file('getOpenFileName',second):studio.open_project()
    app.processEvents()
    from .model import load_project
    require(load_project(first)==load_project(second)==studio.project,'Second saved project changed content.')
    for ext in ('gds','oas'):
        with selected_file('getSaveFileName',folder/('layout.'+ext)):studio.export_gds()
    row.update(case=name,model=model,geometry_index=index,width_um=w,length_um=l,terminal_vias=bool(via),rotation=angle,
               cell_id=studio.cid,top=top,instance_id=d['id'],nets={'p':'R1','m':'R2','body':'B'},
               top_port_assignment='application cell-port dialog',layout_pins=clone(studio.cell['layout_pins']),layout_ports=clone(studio.cell['layout_ports']),
               generation=clone(studio.cell['pdk_layouts']),model_ref=clone(studio.cell['devices'][0]['model_ref']),
               reopened_project=str(second),reopened_project_sha256=file_digest(second),reference_sha256=file_digest(folder/'reference.spice'),
               schematic_sha256=file_digest(folder/'schematic.spice'),gds=str(folder/'layout.gds'),gds_sha256=file_digest(folder/'layout.gds'),
               oasis=str(folder/'layout.oas'),oasis_sha256=file_digest(folder/'layout.oas'),undo_redo=True)
    return row

def legacy_content(project):
    cells=[]
    for c in project['cells']:
        devices=clone(c['devices'])
        for device in devices:device.pop('net_labels',None)  # ordinary wiring migration
        cells.append({'name':c['name'],'ports':clone(c['ports']),'parameters':clone(c.get('parameters',{})),
                      'devices':devices,'shapes':clone(c['shapes']),'layout_pins':clone(c.get('layout_pins',[])),
                      'layout_ports':clone(c.get('layout_ports',[])),'layout_texts':clone(c.get('layout_texts',[])),
                      'pdk_layouts':clone(c.get('pdk_layouts',[]))})
    return {'parameters':clone(project.get('parameters',{})),'cells':cells}

def legacy(app,studio,folder):
    from .model import load_project
    root=Path(__file__).parent/'assets/qualification/ihp-resistor-legacy';rows=[]
    for name,expected in LEGACY.items():
        source=root/name;require(file_digest(source)==expected,'Changed legacy fixture: '+name);before=load_project(source)
        require(all('physical_terminal_vias' not in d for c in before['cells'] for d in c['devices']),'Legacy fixture contains the new field.')
        with selected_file('getOpenFileName',source):studio.open_project()
        app.processEvents();require(legacy_content(studio.project)==legacy_content(before),'Legacy open changed geometry, ports, model or nets.')
        output=folder/name;output.parent.mkdir(parents=True,exist_ok=True)
        with selected_file('getSaveFileName',output):require(studio.save(as_new=True),'Legacy save failed.')
        require(legacy_content(load_project(output))==legacy_content(before) and file_digest(source)==expected,'Legacy recovery changed geometry, ports, model, nets or source.')
        rows.append({'source':str(source),'source_sha256':expected,'saved':str(output),'saved_sha256':file_digest(output),'normalization':'ordinary schematic wiring migration allowed; geometry, ports, model and nets unchanged','origin':'pre-feature linked MOS from verified source snapshot' if name.startswith('mos') else 'pre-feature native imported resistor proof coupon'})
    return rows

def unsupported(app,studio,tech,execution,folder):
    from PySide6.QtWidgets import QDialogButtonBox,QLabel
    d=placement(app,studio,tech,'rsil',.5,.5,'ihp_unsupported_'+execution[:12]);studio.form_fields['modelparam:w'].setText('1u');require(studio.apply_inspector(True),'Inspector rejected valid schematic parameter.')
    before=digest(studio.project);form=studio.mos_layout_dialog();submit_form(app,form,{'terminal_access':'Metal2'});review=studio._review_dialog
    apply=review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply);errors=[v.text() for v in review.findChildren(QLabel) if v.text()]
    require(not apply.isEnabled() and digest(studio.project)==before and not studio.cell.get('pdk_layouts'),'Unsupported preset did not fail closed.')
    require(any('W/L' in e for e in errors),'Unsupported preset explanation missing: '+str(errors));review.reject();after=digest(studio.project);folder.mkdir(parents=True,exist_ok=True);path=folder/'blocked.icproj'
    with selected_file('getSaveFileName',path):require(studio.save(as_new=True),'Blocked project save failed.')
    return {'kind':'unsupported-preset','error':errors,'before_hash':before,'after_hash':after,'project':str(path),'project_sha256':file_digest(path),'cell_id':studio.cid,'no_footprint':True}

def regeneration_control(app,studio,tech,execution,folder):
    from PySide6.QtWidgets import QDialogButtonBox
    from .ihp_layout import audit
    d=placement(app,studio,tech,'rsil',.5,.5,'ihp_eco_'+execution[:12]);generate(app,studio,1)
    altered=clone(studio.project);changed=next(c for c in altered['cells'] if c['id']==studio.cid)['devices'][0];changed['physical_terminal_vias']=False
    require(any(row['code']=='PDK.STALE' for row in audit(altered,studio.cid)),'Changed access option did not mark the footprint stale.')
    studio.select([s['id'] for s in studio.cell['shapes']],'layout');submit_form(app,studio.transform_layout_dialog(),{'rotation':90,'annotations':'Yes'})
    prior=clone(studio.cell['pdk_layouts'][0].get('orientation'));require(prior and prior['rotation']==90,'Rotation was not retained by the generated footprint.')
    studio.select([d['id']],'schematic');studio.form_fields['modelparam:w'].setText('2u');studio.form_fields['modelparam:l'].setText('7u');require(studio.apply_inspector(True),'ECO resize failed.')
    require(any(row['code']=='PDK.STALE' for row in audit(studio.project,studio.cid)),'Changed schematic did not mark footprint stale.')
    form=studio.mos_layout_dialog();require(form.fields['terminal_access'].currentText()=='Metal2','Saved terminal selection was not restored.')
    submit_form(app,form,{'terminal_access':'Metal1'});review=studio._review_dialog;apply=review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply);require(apply.isEnabled(),'ECO preview failed.');apply.click();app.processEvents()
    record=studio.cell['pdk_layouts'][0];require(not record['spec']['terminal_vias'] and record.get('orientation')==prior,'ECO lost access choice or rotation.');require(not audit(studio.project,studio.cid),'ECO left stale footprint.')
    require(all(pin['layer']=='Metal1.drawing' for pin in studio.cell['layout_pins']),'ECO terminal layers differ.');saved=save_reopen(app,studio,folder)
    return {'kind':'rotated-m2-to-m1-eco','saved':saved['project'],'saved_sha256':saved['project_sha256'],'orientation':prior,'stale_detected':True,'option_stale_detected':True,'terminal_vias':False}

def main(arguments=None):
    started=time.monotonic()
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--execution-id',required=True);parser.add_argument('--managed',action='store_true');a=parser.parse_args(arguments)
    require(re.fullmatch('[0-9a-f]{32}',a.execution_id),'Invalid execution identity.');a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    from .build_identity import identity
    from .bundled_pdks import bundle_root
    from .ihp_resistors import TEMPLATE_HASH,SOURCE_HASHES,MANIFEST_SEMANTIC_HASH
    root=bundle_root()/'ihp-sg13g2';resources=bundle_root().parents[2]
    result={'schema':1,'status':'failed','mode':'lifecycle','execution_id':a.execution_id,'build':identity(),'frozen':bool(getattr(sys,'frozen',False)),'execution_root':str(a.out),'resource_root':str(resources),'template_path':str(Path(__file__).parent/'assets/qualification/ihp-resistor-templates/templates.json'),'executable':str(Path(sys.executable).resolve()),'executable_sha256':file_digest(sys.executable),'qualified':False,'installed_acceptance':False,'full_family':False,'release_ready':False,'native_execution':False,'lifecycle':[],'legacy':[],'controls':[],'package_manifest_sha256':PACKAGE,'package_manifest_semantic_sha256':MANIFEST_SEMANTIC_HASH,'template_sha256':TEMPLATE_HASH,'source_hashes':SOURCE_HASHES}
    app=studio=None;errors=[]
    try:
        require(file_digest(root/'package.json')==PACKAGE,'Changed bundled IHP package.')
        collection=bundle_root()/'collection.json';result['bundle_collection_sha256']=file_digest(collection);shutil.copyfile(root/'package.json',a.out/'bundled-package.json');shutil.copyfile(collection,a.out/'bundled-collection.json')
        from PySide6.QtCore import QSettings,QStandardPaths
        from PySide6.QtWidgets import QApplication
        from .gui import Studio
        os.environ['XDG_DATA_HOME']=str(a.out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(a.out/'profile/config');QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(a.out/'profile/settings'));QStandardPaths.writableLocation=staticmethod(lambda kind:str(a.out/'profile'/str(kind.value)))
        app=QApplication([]);app.setStyle('Fusion');studio=Studio(recover=False);studio.error=lambda e:errors.append(str(e));studio.maybe_save=lambda:True;studio.live_check.setChecked(False);studio.resize(1400,960);studio.show()
        key=studio.pdk_registry.install(root/'package.json');tech=studio.pdk_registry.technology(key);result['registry_manifest_sha256']=file_digest(Path(tech['package_root'])/'package.json');result['registry_key']=key;shutil.copyfile(Path(tech['package_root'])/'package.json',a.out/'registry-package.json')
        result['source_actual_hashes']={name:file_digest(Path(tech['package_root'])/'libs.tech/magic'/name) for name in SOURCE_HASHES};require(result['source_actual_hashes']==SOURCE_HASHES,'Changed reviewed source files.')
        template=Path(__file__).parent/'assets/qualification/ihp-resistor-templates/templates.json';require(file_digest(template)==TEMPLATE_HASH,'Changed template asset.');shutil.copyfile(template,a.out/'templates.json')
        if a.managed:result['managed_runtime_before']=capture_runtime(a.out/'runtime/before',resources,result['frozen'])
        result['legacy']=legacy(app,studio,a.out/'legacy');result['controls'].append(unsupported(app,studio,tech,a.execution_id,a.out/'unsupported'));result['controls'].append(regeneration_control(app,studio,tech,a.execution_id,a.out/'eco'))
        for model,index,via,angle in CASES:
            name=f'{model}-g{index}-v{via}-r{angle}';result['lifecycle'].append(case(app,studio,tech,model,index,via,angle,a.out/name,a.execution_id))
        if a.managed:
            result['managed_runtime_after']=capture_runtime(a.out/'runtime/after',resources,result['frozen']);require(result['managed_runtime_before']==result['managed_runtime_after'],'Included runtime identity changed.')
        studio.pdk_registry.verify(key);require(file_digest(root/'package.json')==PACKAGE and file_digest(sys.executable)==result['executable_sha256'],'Input identity changed.');require(not errors,'Application errors: '+str(errors));result['status']='passed'
    except Exception:result.update(error=traceback.format_exc(),errors=errors)
    finally:
        if studio:
            if studio.run_manager.busy:studio.run_manager.cancel(studio.run_manager.rows)
            studio.saved_hash=digest(studio.project);studio.settings.sync();studio.close();app.processEvents()
        result['elapsed_seconds']=time.monotonic()-started
        try:
            paths=list(a.out.rglob('*'));require(not any(p.is_symlink() for p in paths),'Evidence contains a symlink.')
            files={p.relative_to(a.out).as_posix():file_digest(p) for p in sorted(paths) if p.is_file() and p not in (a.out/'files.json',a.out/'report.json')}
            write(a.out/'files.json',files);result['files_sha256']=file_digest(a.out/'files.json')
        except Exception:result.update(status='failed',inventory_error=traceback.format_exc())
        write(a.out/'report.json',result)
    print(json.dumps({'status':result['status'],'execution_id':a.execution_id,'report':str(a.out/'report.json'),'error':result.get('error')}));return int(result['status']!='passed')

