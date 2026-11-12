"""Frozen GUI lifecycle for selected new device classes; parent audits workers.

The producer never claims installed acceptance. The external reader authenticates
the candidate, captured projects, included runtime and native evidence independently.
"""
import argparse,json,os,re,shutil,sys,time,traceback
from pathlib import Path
from .model import clone,digest,file_digest,load_project,save_project
from .mim_desktop_probe import require,selected_file,write
from .ihp_cmim_desktop_probe import capture_ready,output_directory

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def confined(root,name):
    require(isinstance(name,str) and name and '\\' not in name and not Path(name).is_absolute() and '..' not in Path(name).parts,'Unsafe relative input.')
    path=output_directory(Path(root)/name);require(path.is_relative_to(root),'Input escaped fixture root.');return path

def main(arguments=None):
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--inputs',type=Path,required=True);ap.add_argument('--inputs-sha256',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--execution-id',required=True);ap.add_argument('--physical-pdk',type=Path);ap.add_argument('--managed',action='store_true')
    a=ap.parse_args(arguments);require(re.fullmatch('[0-9a-f]{32}',a.execution_id),'Execution nonce required.');a.inputs=output_directory(a.inputs).resolve();a.out=output_directory(a.out).resolve();require(file_digest(a.inputs)==a.inputs_sha256,'Changed input manifest.');a.out.mkdir(parents=True,exist_ok=False)
    manifest=read(a.inputs);require(manifest['schema']==1 and manifest['qualified'] is False and manifest['installed_acceptance'] is False and manifest['cases'],'Invalid finite input contract.')
    from .bundled_pdks import bundle_root
    frozen=bool(getattr(sys,'frozen',False));bundles=bundle_root();resources=bundles.parents[2]
    if frozen:
        from .build_identity import identity
        build=identity()
    else:build=dict(commit='unknown',dirty=None,frozen=False)
    result=dict(schema=1,status='failed',frozen=frozen,build=build,execution_id=a.execution_id,executable=str(Path(sys.executable).resolve()),executable_sha256=file_digest(sys.executable),resource_root=str(resources),input_manifest_sha256=a.inputs_sha256,execution_root=str(a.out),cases=[],managed=a.managed,native_execution=False,qualified=False,installed_acceptance=False,full_family=False,release_ready=False)
    app=studio=None;errors=[];started=time.monotonic();before={str(a.inputs):a.inputs_sha256}
    try:
        require(not frozen or a.managed,'Frozen class acceptance requires included managed runtime.')
        from PySide6.QtCore import QSettings,QStandardPaths
        from PySide6.QtWidgets import QApplication
        from unittest.mock import patch
        from . import gui
        from .testbenches import native_subcircuit
        os.environ['XDG_DATA_HOME']=str(a.out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(a.out/'profile/config')
        settings=QSettings(str(a.out/'profile/settings.ini'),QSettings.IniFormat);settings.setFallbacksEnabled(False);QStandardPaths.writableLocation=staticmethod(lambda kind:str(a.out/'profile'/str(kind.value)))
        app=QApplication([]);app.setStyle('Fusion')
        with patch.object(gui,'QSettings',return_value=settings):studio=gui.Studio(recover=False)
        studio.error=lambda e:errors.append(str(e));studio.maybe_save=lambda:True;studio.live_check.setChecked(False);studio.resize(1400,960);studio.show();technologies={}
        if a.managed:result['managed_runtime_before'],result['ready_status_before']=capture_ready(a.out/'runtime/before',resources,frozen)
        for row in manifest['cases']:
            require(re.fullmatch('[A-Za-z0-9_-]+',row['name']),'Invalid case identity.');path=confined(a.inputs.parent,row['project']);require(file_digest(path)==row['project_sha256'],'Changed fixture project.');before[str(path)]=row['project_sha256'];p=load_project(path);target=p['pdk']['package_lock']['id']
            original=confined(a.inputs.parent,row['captured']);require(file_digest(original)==row['captured_sha256'] and native_subcircuit(p,p['top'])==original.read_text(encoding='utf-8'),'Prepared model/source differs.');before[str(original)]=row['captured_sha256']
            package=output_directory(a.physical_pdk).resolve() if row['family']=='shared-mim' else bundles/target
            key=str(package)
            if key not in technologies:
                installed=studio.pdk_registry.install(package/'package.json');technologies[key]=studio.pdk_registry.technology(installed)
            tech=technologies[key];require(p['pdk']['package_lock']=={k:tech['package_lock'][k] for k in ('id','revision','files')},'Input package differs from installed package.');p['pdk']['package_root']=tech['package_root'];expected_source=native_subcircuit(p,p['top'])
            folder=a.out/row['name'];folder.mkdir();save_project(p,folder/'opened.icproj');shutil.copyfile(Path(tech['package_root'])/'package.json',folder/'registry-package.json')
            with selected_file('getOpenFileName',folder/'opened.icproj'):studio.open_project()
            app.processEvents();write(folder/'observed-opened.json',studio.project);require(studio.project==p,'GUI did not open exact selected project.');require(studio.cid==p['top'],'GUI opened wrong top cell.')
            with selected_file('getSaveFileName',folder/'saved.icproj'):require(studio.save(as_new=True),'GUI save failed.')
            studio.close_project()
            with selected_file('getOpenFileName',folder/'saved.icproj'):studio.open_project()
            app.processEvents();require(studio.project==p==load_project(folder/'saved.icproj'),'GUI save/reopen changed input.')
            with selected_file('getSaveFileName',folder/'reopened.icproj'):require(studio.save(as_new=True),'GUI repeated save failed.')
            captured=native_subcircuit(studio.project,p['top']);require(captured==expected_source,'GUI model/source differs after explicit package-root relocation.')
            (folder/'captured.spice').write_text(captured,encoding='utf-8',newline='\n')
            for ext in ('gds','oas'):
                with selected_file('getSaveFileName',folder/('layout.'+ext)):studio.export_gds()
            require((folder/'layout.gds').is_file() and (folder/'layout.oas').is_file() and not errors,'GUI layout export failed: '+str(errors))
            result['cases'].append(dict(name=row['name'],family=row['family'],project=row['name']+'/saved.icproj',reopened_project=row['name']+'/reopened.icproj',project_sha256=file_digest(folder/'saved.icproj'),reopened_sha256=file_digest(folder/'reopened.icproj'),captured_sha256=file_digest(folder/'captured.spice'),registry_package_sha256=file_digest(Path(tech['package_root'])/'package.json'),package_root=tech['package_root'],settings=clone(row['settings']),expected=row['expected']))
            write(a.out/'progress.json',dict(execution_id=a.execution_id,cases=result['cases']))
        if a.managed:
            result['managed_runtime_after'],result['ready_status_after']=capture_ready(a.out/'runtime/after',resources,frozen);require(result['managed_runtime_after']==result['managed_runtime_before'] and result['ready_status_after']==result['ready_status_before'],'Managed readiness changed.')
        require(all(file_digest(Path(p))==v for p,v in before.items()),'Input changed during GUI lifecycle.');require(file_digest(sys.executable)==result['executable_sha256'] and not errors,'Executable or GUI failure.');result['status']='passed'
    except Exception:result.update(error=traceback.format_exc(),errors=errors)
    finally:
        if studio:
            if studio.run_manager.busy:studio.run_manager.cancel(studio.run_manager.rows)
            studio.saved_hash=digest(studio.project);studio.settings.sync();studio.close();app.processEvents()
        result['elapsed_seconds']=time.monotonic()-started
        files={}
        for folder,dirs,names in os.walk(a.out,followlinks=False):
            require('tmpuxoell2b' not in (*dirs,*names),'Forbidden member.')
            for n in (*dirs,*names):
                p=Path(folder)/n;require(not p.is_symlink() and not getattr(p,'is_junction',lambda:False)(),'Linked evidence member.')
                if n in names and p not in (a.out/'files.json',a.out/'report.json'):files[p.relative_to(a.out).as_posix()]=file_digest(p)
        write(a.out/'files.json',files);result['files_sha256']=file_digest(a.out/'files.json');write(a.out/'report.json',result)
    print(json.dumps(dict(status=result['status'],cases=len(result['cases']),error=result.get('error'))));return int(result['status']!='passed')
