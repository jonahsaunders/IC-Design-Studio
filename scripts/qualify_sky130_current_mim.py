"""Source-only Qt MiM current-candidate lifecycle and staging evidence producer."""
import argparse, json, os, re, shutil, sys, traceback
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from icstudio.model import file_digest
from icstudio.mim_desktop_probe import place_edit, save_reopen, selected_file
from scripts.qualify_sky130_mim_passive_corners import stage_models
from scripts.installed_mim_inputs import inventory, write
from scripts import sky130_esd_revision_bridge as bridge
from scripts.installed_mim_inputs import source_files

def sources():
    """Bounded application and relevant script source identities, without a repository scan."""
    files = source_files()
    for name in ("sky130_esd_revision_bridge.py", "qualify_sky130_current_mim.py", "audit_sky130_current_mim.py"):
        path = Path(__file__).resolve().parent/name
        if path.is_symlink() or not path.is_file(): raise ValueError("Missing or linked source: "+name)
        files["scripts/"+name] = file_digest(path)
    extra = Path(bridge.prepare_optional.__code__.co_filename)
    files["scripts/prepare_sky130_esd_nvt.py"] = file_digest(extra)
    return dict(sorted(files.items()))


def produce(package, predecessor_manifest, out, nonce):
    if not re.fullmatch('[0-9a-f]{32}',nonce): raise ValueError('Invalid nonce')
    package=bridge.unlinked(package).resolve(); predecessor_manifest=bridge.unlinked(predecessor_manifest).resolve();out=bridge.unlinked(out).resolve()
    if out.exists(): raise ValueError('Choose new evidence directory')
    initial_sources=sources()
    bridge.compare(package,predecessor_manifest)
    out.mkdir(parents=True)
    os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtWidgets import QApplication
    from icstudio.gui import Studio
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
    QStandardPaths.writableLocation=staticmethod(lambda kind:str(out/'profile'/str(kind.value)))
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    studio=Studio(recover=False);errors=[];studio.error=lambda e:errors.append(str(e));studio.maybe_save=lambda:True
    studio.live_check.setChecked(False);studio.show();studio.probe_execution_id=nonce
    try:
        with bridge.reconstruct(package,predecessor_manifest) as (old,_):
            reg=studio.pdk_registry; oldkey=reg.install(old/'package.json')
            old_binding=place_edit(app,studio,reg.technology(oldkey),1)
            oldrow=save_reopen(app,studio,out/'old-before')
            key=reg.install(package/'package.json'); current=reg.technology(key)
            with selected_file('getOpenFileName',oldrow['project']): studio.open_project()
            after=save_reopen(app,studio,out/'old-after')
            if oldrow['package_lock']!=after['package_lock']: raise ValueError('Old project lock migrated')
            rows=[]
            for plate in (1,2):
                print('place',plate,flush=True); binding=place_edit(app,studio,current,plate)
                print('save',plate,flush=True); row=save_reopen(app,studio,out/f'current-{plate}');row.update(plate=plate,binding=binding,export_sha256={k:file_digest(row[k]) for k in ('schematic','reference')});rows.append(row)
            print('verify',flush=True); reg.verify(key); reg.verify(oldkey)
            if errors:raise ValueError('GUI errors: '+str(errors))
            current_path=Path(current['package_root']).resolve()
            bridge.compare_registry(current_path,package,predecessor_manifest)
            (out/'contract-sources').mkdir(); shutil.copyfile(current_path/'package.json',out/'contract-sources/package')
            shutil.copyfile(predecessor_manifest,out/'contract-sources/predecessor');shutil.copyfile(package/'package.json',out/'contract-sources/candidate')
            print('stage',flush=True); staged, files=stage_models(current,out);write(out/'model-files.json',files)
            if sources()!=initial_sources: raise ValueError('Application or script sources changed during probe')
            report=dict(source_files=initial_sources,schema='mim-current-source-probe-v2',status='PASS',nonce=nonce,mode='source-qt',
                installed_acceptance=False,qualified=False,execution_root=str(out),
                current=dict(path=str(current_path),revision=current['revision'],manifest_sha256=file_digest(current_path/'package.json'),registry_key=key),
                predecessor=dict(manifest_sha256=bridge.BASE,revision='b26f7f28e659ddc1',registry_key=oldkey),
                old_before=oldrow,old_after=after,old_binding=old_binding,current_projects=rows,
                staged_sections=list(staged),source_manifest=file_digest(package/'package.json'),source_candidate_path=str(package))
            write(out/'report.json',report)
    finally:
        studio.close();app.processEvents()
    if sources()!=initial_sources: raise ValueError('Application or script sources changed during probe shutdown')
    # Profile is live mutable app state; evidence reader binds actual registry files and selected records instead.
    return {'report_sha256':file_digest(out/'report.json'),'nonce':nonce,'root':str(out)}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);ap.add_argument('--predecessor',required=True);ap.add_argument('--out',required=True);ap.add_argument('--nonce',required=True)
    a=ap.parse_args(); print(json.dumps(produce(a.package,a.predecessor,a.out,a.nonce),indent=2))



