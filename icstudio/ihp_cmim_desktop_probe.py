"""GUI-only installed IHP CMIM reference producer; parent audits native jobs.

The bounded public-source mask is not a device or operating-envelope claim.
The source-mode lifecycle is for development and cannot establish installation.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import traceback

from .model import clone,design_digest,digest,example,file_digest,load_project
from .mim_desktop_probe import capture_runtime,require,selected_file,write

KEY='sg13g2_pr/cap_cmim.sym'
PACKAGE='da58ba2de122d67d232ab20ca4fb353b70bdc68c00ef4279f9be7da640a68ae0'
FIXTURE='e228d35180cb12fa72b1dd0b119a17db7dadac02b3204146d150b45392a3c1a3'
ORIGINAL='4935eab2169f74c058def21cd00f509712c930b71eb78b026cd814dccaceebeb'
LICENSE='c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4'
SOURCE='b8eee6f5c73fb3e700967095b89c2ce9cbce60343fa1ce6a4aec4de639c51982'
FIELDS=('shapes','layout_instances','layout_texts','external_properties','layout_ports','layout_label_mode')


def output_directory(path):
    """Reject links and forbidden names before resolving or creating output."""
    path=Path(path);require('tmpuxoell2b' not in path.parts and '..' not in path.parts,'Unsafe output path.')
    absolute=path.absolute();require('tmpuxoell2b' not in absolute.parts,'Unsafe output path.')
    for member in (*reversed(absolute.parents),absolute):
        require(not member.is_symlink() and not getattr(member,'is_junction',lambda:False)(),'Linked output path.')
    resolved=absolute.resolve();require('tmpuxoell2b' not in resolved.parts,'Unsafe resolved output path.')
    return resolved


def fixture(root):
    """Load only locked mask/terminal data, never a source project's model."""
    root=Path(root);path=root/'mask-only.json';source=root/'SOURCE.json'
    require(file_digest(path)==FIXTURE and file_digest(source)==SOURCE and file_digest(root/'LICENSE')==LICENSE,'Changed IHP CMIM fixture, source or license.')
    spec=json.loads(source.read_bytes());data=json.loads(path.read_bytes())
    require(set(data)=={'schema','source_project_sha256',*FIELDS} and data['schema']==1 and
        data['source_project_sha256']==ORIGINAL and spec['original_project_sha256']==ORIGINAL and
        spec['mask_only_sha256']==FIXTURE and spec['license_sha256']==LICENSE and spec['pdk_manifest_sha256']==PACKAGE and
        spec['selected_fields']==list(FIELDS),'CMIM fixture provenance or scope differs.')
    require(not data['layout_instances'] and len(data['layout_ports'])==2 and
        {p['name'] for p in data['layout_ports']}=={'C1','C2'},'Invalid retained CMIM physical interface.')
    return data,spec


def capture_ready(destination,resources,frozen):
    """Retain the real installed readiness record alongside runtime locks."""
    from . import digital_runtime
    before=digital_runtime.status();require(before.get('state')=='ready','Included physical runtime is not ready.')
    manifest=digital_runtime.manifest();key=manifest.get('sha256','')
    require(isinstance(key,str) and re.fullmatch('[0-9a-f]{64}',key),'Invalid included runtime identity.')
    path=digital_runtime.state_root()/('ready-'+key+'.json')
    require(not path.is_symlink() and not getattr(path,'is_junction',lambda:False)() and path.is_file(),'Missing or linked included runtime readiness receipt.')
    expected=file_digest(path);ready=json.loads(path.read_bytes())
    require(ready.get('runtime')==before.get('runtime') and ready.get('evidence')==before.get('evidence'),
            'Readiness receipt differs from the live runtime status.')
    captured=capture_runtime(destination,resources,frozen)
    require(captured['runtime']==before['runtime'],'Captured runtime differs from readiness status.')
    shutil.copyfile(path,Path(destination)/'ready.json')
    require(file_digest(path)==expected==file_digest(Path(destination)/'ready.json') and digital_runtime.status()==before,
            'Runtime readiness changed while it was captured.')
    captured['files']['ready.json']=expected
    return captured,before


def place(app,studio,tech,data,execution_id):
    from PySide6.QtCore import Qt
    from .catalog import binding_for,parameter_values
    p=example('empty');p['name']='IHP CMIM '+execution_id;p['pdk']=clone(tech);cell=p['cells'][0]
    cell.update(name='coupon',ports=['C1','C2'])
    for name in FIELDS:cell[name]=clone(data[name])
    studio.set_project(p)
    item=next((studio.library_list.item(i) for i in range(studio.library_list.count())
               if studio.library_list.item(i).data(Qt.UserRole)==KEY),None)
    require(item is not None and not item.data(Qt.UserRole+3),'Current IHP CMIM catalog entry unavailable.')
    studio.library_list.setCurrentItem(item);studio.place_library_button.click()
    require(studio.schematic.placement is not None,'CMIM catalog placement did not start.')
    studio.place_device_at(300,250);studio.cancel_tool();require(len(studio.cell['devices'])==1,'Expected one fresh CMIM device.')
    device=studio.cell['devices'][0];require('native_spice' not in device and not device.get('model_ref',{}).get('lvs'),
        'Expected a fresh ordinary catalog reference, not imported LVS tokens.')
    studio.select([device['id']],'schematic')
    for name,value in {'Name':'C1','net:c0':'C1','net:c1':'C2'}.items():studio.form_fields[name].setText(value)
    require(studio.apply_inspector(True),'CMIM interface edit failed.');app.processEvents()
    device=studio.cell['devices'][0];binding=binding_for(studio.project['pdk'],device);values=parameter_values(binding,device)
    require(binding['model']=='cap_cmim' and binding['pin_order']==['c0','c1'] and
        device['nets']=={'c0':'C1','c1':'C2'} and abs(values['w']-7e-6)<1e-15 and abs(values['l']-7e-6)<1e-15 and
        values['m']==1 and values['mm_ok']==1,'CMIM default binding, dimensions, multiplier or pins differ.')
    # Exercise the actual inspector, then restore the source-backed defaults.
    studio.form_fields['modelparam:w'].setText('8u');require(studio.apply_inspector(True),'CMIM width edit failed.');app.processEvents()
    require(abs(parameter_values(binding,studio.cell['devices'][0])['w']-8e-6)<1e-15,'CMIM width edit did not apply.')
    studio.form_fields['modelparam:w'].setText('7u');require(studio.apply_inspector(True),'CMIM default restoration failed.');app.processEvents()
    require(abs(parameter_values(binding,studio.cell['devices'][0])['w']-7e-6)<1e-15,'CMIM default was not restored.')
    for name in FIELDS:require(studio.cell[name]==data[name],'Catalog editing changed retained physical data: '+name)
    return clone(studio.cell['devices'][0])


def lifecycle(app,studio,out,device):
    from .catalog_migration import emit
    from .testbenches import native_subcircuit
    from .layout_verification import reference
    before=clone(studio.project);top=studio.cell['name'];cid=studio.cid
    simulation=emit(studio.cell['devices'][0],studio.project['pdk'],'simulation')
    require(simulation.startswith('X') and ' cap_cmim ' in simulation and 'mm_ok=1' in simulation,'Fresh simulation reference differs.')
    path=out/'catalog.icproj'
    with selected_file('getSaveFileName',path):require(studio.save(as_new=True),'CMIM project save failed.')
    studio.close_project();require(studio.project['id']!=before['id'],'The saved project did not close.')
    with selected_file('getOpenFileName',path):studio.open_project()
    app.processEvents();reopened=load_project(path)
    require(studio.project==reopened==before and studio.cid==cid,'CMIM save/reopen changed project or cell.')
    second=out/'catalog-reopened.icproj'
    with selected_file('getSaveFileName',second):require(studio.save(as_new=True),'Reopened CMIM project save failed.')
    require(load_project(second)==reopened,'Second CMIM save changed project.')
    require(emit(studio.cell['devices'][0],studio.project['pdk'],'simulation')==simulation,'Save/reopen changed CMIM simulation.')
    with selected_file('getSaveFileName',out/'schematic.spice'):studio.export_spice()
    for ext in ('gds','oas'):
        with selected_file('getSaveFileName',out/('layout.'+ext)):studio.export_gds()
    raw=native_subcircuit(studio.project,studio.cid);require(simulation in raw,'Application reference does not contain the placed simulation instance.')
    captured=reference(raw,top);(out/'captured-reference.spice').write_text(raw,encoding='utf-8',newline='\n')
    require(simulation in (out/'schematic.spice').read_text(encoding='utf-8'),'Application SPICE export lost the original simulation instance.')
    return dict(top=top,cell_id=cid,project_name=reopened['name'],instance_id=device['id'],nets=clone(device['nets']),default_width_um=7,default_length_um=7,
        multiplicity=1,mm_ok=1,edit_width_um=8,restored_width_um=7,simulation_statement=simulation,
        project='catalog.icproj',project_sha256=file_digest(path),design_hash=design_digest(reopened),
        reopened_project='catalog-reopened.icproj',reopened_project_sha256=file_digest(second),
        reference='captured-reference.spice',reference_sha256=file_digest(out/'captured-reference.spice'),reference_capture=captured,
        schematic='schematic.spice',schematic_sha256=file_digest(out/'schematic.spice'),
        gds='layout.gds',gds_sha256=file_digest(out/'layout.gds'),oasis='layout.oas',oasis_sha256=file_digest(out/'layout.oas'))


def main(arguments=None):
    started=time.monotonic();parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--execution-id',required=True);parser.add_argument('--managed',action='store_true')
    args=parser.parse_args(arguments);require(re.fullmatch('[0-9a-f]{32}',args.execution_id),'Invalid execution identity.')
    args.out=output_directory(args.out);args.out.mkdir(parents=True,exist_ok=False)
    from .bundled_pdks import bundle_root
    frozen=bool(getattr(sys,'frozen',False))
    if frozen:
        from .build_identity import identity
        build=identity()
    else:
        from . import __version__
        build=dict(version=__version__,commit='unknown',branch='unknown',dirty=None,frozen=False)
    bundle=bundle_root();package=bundle/'ihp-sg13g2';resources=bundle.parents[2];asset=Path(__file__).parent/'assets/qualification/ihp-cmim-reference'
    result=dict(schema=1,status='failed',mode='lifecycle',execution_id=args.execution_id,build=build,frozen=frozen,
        execution_root=str(args.out),resource_root=str(resources),executable=str(Path(sys.executable).resolve()),executable_sha256=file_digest(sys.executable),
        fixture_root=str(asset),fixture_sha256=FIXTURE,source_project_sha256=ORIGINAL,package_manifest_sha256=PACKAGE,
        managed=args.managed,native_execution=False,qualified=False,installed_acceptance=False,full_family=False,release_ready=False)
    app=studio=None;errors=[]
    try:
        require(not frozen or args.managed,'Frozen CMIM producer requires the included managed runtime.')
        data,spec=fixture(asset);result['fixture_source_sha256']=file_digest(asset/'SOURCE.json');result['fixture_license_sha256']=file_digest(asset/'LICENSE')
        require(file_digest(package/'package.json')==PACKAGE,'Changed bundled IHP package.')
        result['bundle_collection_sha256']=file_digest(bundle/'collection.json')
        for source,name in ((package/'package.json','bundled-package.json'),(bundle/'collection.json','bundled-collection.json'),
                            (asset/'SOURCE.json','fixture-source.json'),(asset/'mask-only.json','fixture-mask.json'),(asset/'LICENSE','fixture-LICENSE')):
            shutil.copyfile(source,args.out/name)
        from PySide6.QtCore import QSettings,QStandardPaths
        from PySide6.QtWidgets import QApplication
        from unittest.mock import patch
        from . import gui
        os.environ['XDG_DATA_HOME']=str(args.out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(args.out/'profile/config')
        # The organization/application constructor still selects the registry on Windows.
        settings=QSettings(str(args.out/'profile/settings.ini'),QSettings.IniFormat);settings.setFallbacksEnabled(False)
        QStandardPaths.writableLocation=staticmethod(lambda kind:str(args.out/'profile'/str(kind.value)))
        app=QApplication([]);app.setStyle('Fusion')
        with patch.object(gui,'QSettings',return_value=settings):
            studio=gui.Studio(recover=False)
        studio.error=lambda e:errors.append(str(e))
        studio.maybe_save=lambda:True;studio.live_check.setChecked(False);studio.resize(1400,960);studio.show()
        key=studio.pdk_registry.install(package/'package.json');tech=studio.pdk_registry.technology(key)
        result['registry_key']=key;result['registry_manifest_sha256']=file_digest(Path(tech['package_root'])/'package.json')
        require(json.loads((Path(tech['package_root'])/'package.json').read_bytes())==json.loads((package/'package.json').read_bytes()),
                'Registry package metadata differs from bundled source.')
        shutil.copyfile(Path(tech['package_root'])/'package.json',args.out/'registry-package.json')
        require(file_digest(Path(tech['package_root'])/spec['public_magic_generator'])==spec['public_magic_generator_sha256'],
                'CMIM public source generator differs from fixture provenance.')
        if args.managed:result['managed_runtime_before'],result['ready_status_before']=capture_ready(args.out/'runtime/before',resources,frozen)
        device=place(app,studio,tech,data,args.execution_id);result['lifecycle']=lifecycle(app,studio,args.out,device)
        if args.managed:
            result['managed_runtime_after'],result['ready_status_after']=capture_ready(args.out/'runtime/after',resources,frozen)
            require(result['managed_runtime_before']==result['managed_runtime_after'] and result['ready_status_before']==result['ready_status_after'],'Included runtime readiness changed.')
        studio.pdk_registry.verify(key)
        require(file_digest(package/'package.json')==PACKAGE and file_digest(asset/'mask-only.json')==FIXTURE and
                file_digest(sys.executable)==result['executable_sha256'] and not errors,'Application, fixture or package changed: '+str(errors))
        result['status']='passed'
    except Exception:result.update(error=traceback.format_exc(),errors=errors)
    finally:
        if studio:
            if studio.run_manager.busy:studio.run_manager.cancel(studio.run_manager.rows)
            studio.saved_hash=digest(studio.project);studio.settings.sync();studio.close();app.processEvents()
        result['elapsed_seconds']=time.monotonic()-started
        try:
            files={}
            for folder,dirs,names in os.walk(args.out,topdown=True,followlinks=False):
                dirs[:]=sorted(n for n in dirs if n!='tmpuxoell2b')
                for name in dirs:
                    directory=Path(folder)/name;require(not directory.is_symlink() and not directory.is_junction(),'Linked evidence directory.')
                for name in sorted(names):
                    if name=='tmpuxoell2b':continue
                    path=Path(folder)/name;require(not path.is_symlink() and not path.is_junction(),'Linked evidence member.')
                    if path not in (args.out/'files.json',args.out/'report.json'):files[path.relative_to(args.out).as_posix()]=file_digest(path)
            write(args.out/'files.json',files);result['files_sha256']=file_digest(args.out/'files.json')
        except Exception:result.update(status='failed',inventory_error=traceback.format_exc())
        write(args.out/'report.json',result)
    print(json.dumps({'status':result['status'],'execution_id':args.execution_id,'report':str(args.out/'report.json'),'error':result.get('error')}))
    return int(result['status']!='passed')
