"""Exercise candidate bundled discovery and actual GUI lifecycle in a subprocess."""
import argparse,hashlib,json,os,platform,sys,time
from pathlib import Path
from icstudio.model import file_digest,load_project
from icstudio.mim_desktop_probe import require,save_reopen,selected_file
from icstudio.esd_desktop_probe import install_gui
from icstudio.project_hub import inventory,build_project
from icstudio.catalog import parameter_values
from icstudio.pdks import stage_model_deck

REV='47dbd4fe43bfa7e4';BASE='5dda725c94efe3c2'
MANIFEST='0c19e0ea5718a841045b597022d13f2dcb57e35cf8be9757b254fb465f2a35c4'
COLLECTION='4472d7255a991ef8a0be1d4580dc8a3e09bb4b02e6f7354954513382462e6592'
PREFIX='libs.tech/ngspice/icstudio-rf-pw2dn/'
KEY='sky130_fd_pr/diode__sky130_fd_pr__model__parasitic__rf_diode_pw2dn.sym'
MODEL='sky130_fd_pr__model__parasitic__rf_diode_pw2dn'

def place(app,studio,key,name,w,l,nets):
    from PySide6.QtCore import Qt
    item=next((studio.library_list.item(i) for i in range(studio.library_list.count())
               if studio.library_list.item(i).data(Qt.UserRole)==key),None)
    require(item is not None and not item.data(Qt.UserRole+3),'RF library item is unavailable.')
    studio.library_list.setCurrentItem(item);studio.place_library_button.click()
    require(studio.schematic.placement is not None,'RF placement did not start.')
    studio.place_device_at(300,250);studio.cancel_tool();require(len(studio.cell['devices'])==1,'RF placement count differs.')
    studio.select([studio.cell['devices'][0]['id']],'schematic')
    fields={'Name':name,'modelparam:w':str(w),'modelparam:l':str(l)}
    fields.update({'net:'+k:v for k,v in nets.items()})
    for key,value in fields.items():
        require(key in studio.form_fields,'Missing inspector field '+key);studio.form_fields[key].setText(value)
    require(studio.apply_inspector(True),'RF inspector rejected fields.');app.processEvents()

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--predecessor',type=Path,required=True)
    parser.add_argument('--execution-id',required=True)
    parser.add_argument('--engine',type=Path)
    parser.add_argument('--native-out',type=Path)
    parser.add_argument('--native-pilot',action='store_true')
    args=parser.parse_args(argv);OUT=args.out.resolve();old_source=args.predecessor.resolve()
    require((args.engine is None)==(args.native_out is None),'Engine and native output must be supplied together.')
    require(not getattr(sys,'frozen',False) or args.engine is not None,'Frozen acceptance requires native production.')
    require(not args.native_pilot or (args.engine is not None and not getattr(sys,'frozen',False)),'Native pilot is only available in source mode.')
    if OUT.exists():raise ValueError('Choose a fresh GUI output directory.')
    OUT.mkdir();os.environ['XDG_DATA_HOME']=str(OUT/'profile/data');os.environ['XDG_CONFIG_HOME']=str(OUT/'profile/config')
    from PySide6.QtCore import QSettings,QStandardPaths,qVersion
    from PySide6.QtWidgets import QApplication
    import PySide6,PySide6.QtCore
    from icstudio.gui import Studio
    from icstudio.bundled_pdks import packages
    from icstudio.bundled_pdks import bundle_root
    from icstudio.build_identity import identity
    root=bundle_root().resolve()
    require(file_digest(old_source/'package.json')=='125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b','Predecessor manifest differs.')
    report={'execution_id':args.execution_id,'frozen':bool(getattr(sys,'frozen',False)), 'build':identity(),
            'executable_sha256':file_digest(sys.executable),'python_version':sys.version,
            'pyside_version':PySide6.__version__,'qtcore_sha256':file_digest(PySide6.QtCore.__file__),
            'qt_version':qVersion(),'platform':platform.platform(),
            'candidate_manifest_sha256':MANIFEST,'collection_sha256':COLLECTION,'scope':'GUI lifecycle only; native electrical verification is separate and no family qualification is asserted.'}
    (OUT/'prelaunch.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    require(file_digest(root/'collection.json')==COLLECTION,'Collection identity changed.')
    rows=[r for r in packages(verify=True) if r['name']=='sky130A']
    require(len(rows)==1 and rows[0]['revision']==REV and file_digest(Path(rows[0]['path'])/'package.json')==MANIFEST,'Bundled candidate identity differs.')
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(OUT/'profile/settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(OUT/'profile'/str(kind.value)))
    app=QApplication([]);app.setStyle('Fusion');studio=Studio(recover=False);errors=[]
    studio.error=lambda error:errors.append(str(error));studio.maybe_save=lambda:True;studio.live_check.setChecked(False);studio.show()
    registry=studio.pdk_registry
    oldkey=install_gui(app,studio,old_source/'package.json')
    require(oldkey=='sky130A@'+BASE,'Predecessor identity differs.')
    oldrow=next(r for r in inventory(registry)[0] if r['key']==oldkey)
    old=build_project(registry,oldrow,'Previous project','empty')['project'];studio.set_project(old)
    place(app,studio,KEY.replace('pw2dn','ps2nw'),'OLD',3,2,{'d0':'OA','d1':'OK'})
    report['old_before']=save_reopen(app,studio,OUT/'old-before')
    hub=studio.project_hub();app.processEvents();key='sky130A@'+REV
    require(hub.select_pdk(key) and hub.current_pdk()['status']=='Available offline','Hub did not discover bundled candidate.')
    hub.show_page('new');hub.name.setText('PW2DN default candidate');hub.create_button.click()
    deadline=time.monotonic()+120
    while (hub.busy() or studio.project['pdk']['revision']!=REV) and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    app.processEvents();require(not hub.busy() and studio.project['pdk']['revision']==REV,'Hub project did not select candidate.')
    report['hub_selected']=key;report['hub_source_path']=rows[0]['path']
    place(app,studio,KEY,'D1',4,2,{'d0':'A','d1':'K'})
    report['new']=save_reopen(app,studio,OUT/'new')
    project=load_project(report['new']['project']);dev=project['cells'][0]['devices'][0]
    require(parameter_values(project['pdk']['simulation']['catalog'][KEY],dev)=={'w':4,'l':2,'area':8,'perim':12},'Reopened geometry differs.')
    deck=Path(report['new']['schematic']).read_text(encoding='utf-8')
    require('X_D1 A K '+MODEL+' area=8 perim=12' in deck,'Export terminal/model mapping differs.')
    stage=OUT/'staged';stage.mkdir();staged=stage_model_deck(project['pdk'],deck,stage)
    (stage/'schematic.spice').write_text(staged,encoding='utf-8')
    derivative=Path(project['pdk']['package_root'])/(PREFIX+MODEL+'.model.spice')
    mapping=json.loads((stage/'pdk-model-files.json').read_bytes())
    staged_models=[stage/name for name,source in mapping.items() if source==PREFIX+MODEL+'.model.spice']
    require(len(staged_models)==1 and staged_models[0].read_bytes()==derivative.read_bytes(),'Staged derivative identity differs.')
    with selected_file('getOpenFileName',report['old_before']['project']):studio.open_project()
    report['old_after']=save_reopen(app,studio,OUT/'old-after')
    require(report['old_before']['package_lock']==report['old_after']['package_lock'],'Historical project lock migrated.')
    require(Path(report['old_before']['schematic']).read_bytes()==Path(report['old_after']['schematic']).read_bytes(),'Historical export changed.')
    registry.verify(oldkey);registry.verify(key);require(not errors,'GUI errors: '+str(errors))
    report['registry']={'old_key':oldkey,'current_key':key,'current_root':project['pdk']['package_root']}
    require(file_digest(root/'collection.json')==COLLECTION,'Collection changed during GUI run.')
    report['staged_derivative_sha256']=file_digest(derivative);report['status']='PASS_GUI_LIFECYCLE'
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');studio.close();app.quit()
    if args.engine is not None:
        from .pw2dn_native_probe import produce
        produce(OUT/'new/project.icproj',args.native_out,args.engine,args.execution_id,pilot=args.native_pilot)
    print(json.dumps({'status':report['status'],'report_sha256':file_digest(OUT/'report.json')},indent=2))
if __name__=='__main__':main()
