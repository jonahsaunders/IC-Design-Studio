"""Opt-in corrected ESD GUI lifecycle and native electrical evidence.

An external reader must bind installed provenance and independently compare
native currents. These selected operating points are not ESD ratings or full
device-family qualification. Historical optional evidence is left unchanged.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import traceback

from .model import clone, device, digest, example, file_digest, load_project, save_project
from .mim_desktop_probe import require, write, verified_package, selected_file, save_reopen, place_edit
from .acceptance_runtime import native_environment, runtime

BASE = '840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe'
OPTIONAL = '5315d2d6ad7618047eeeb48a15f81f221e6f42864647208acfb65124ee5c9c7a'
DEFAULT_CANDIDATE = '125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b'
DEFAULT_REVISION = '5dda725c94efe3c2'
KEY = 'sky130_fd_pr/nfet_g5v0d10v5_nvt_esd.sym'
MODEL = 'sky130_fd_pr__esd_nfet_05v0_nvt'
FAULTS = ('wrong-multiplicity', 'wrong-gate', 'wrong-body', 'wrong-length')
CONDITIONS = tuple((c,t,'dc') for c in ('nominal','ss','ff','sf','fs') for t in (0,27,85)) + tuple(('nominal',27,p) for p in 'dgsb')


def source_identity():
    if getattr(sys, 'frozen', False):
        return {}
    from . import model
    root = Path(model.__file__).resolve().parent
    from . import acceptance_runtime
    return {p.name: file_digest(p) for p in sorted(root.glob('*.py'))} | {
        'esd_desktop_probe.py':file_digest(__file__), 'acceptance_runtime.py':file_digest(acceptance_runtime.__file__)}


def install_gui(app, studio, manifest):
    from PySide6.QtWidgets import QPushButton, QLabel
    expected = json.loads(Path(manifest).read_bytes())
    key = expected['id']+'@'+expected['revision']
    studio.pdk_manager()
    setup = studio._pdk_dialog
    manage = next((b for b in setup.findChildren(QPushButton) if b.text() == 'Manage / verify revisions…'),None)
    if manage is not None:
        manage.click()
    dialog = studio._pdk_dialog
    button = next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Install package…')
    with selected_file('getOpenFileName',manifest): button.click()
    app.processEvents()
    require(any(label.text() == 'Installed '+key for label in dialog.findChildren(QLabel)),
            'PDK manager did not confirm selected package installation.')
    dialog.close()
    setup.close()
    app.processEvents()
    studio.pdk_registry.verify(key)
    return key


def prior_mim(app, studio, technology):
    from PySide6.QtCore import Qt
    place_edit(app,studio,technology,1,2)
    item = next(studio.library_list.item(i) for i in range(studio.library_list.count())
                if studio.library_list.item(i).data(Qt.UserRole) == 'sky130_fd_pr/cap_mim_m3_2.sym')
    studio.library_list.setCurrentItem(item)
    studio.place_library_button.click()
    studio.place_device_at(700,250)
    studio.cancel_tool()
    require(len(studio.cell['devices']) == 2,'Historical second MiM was not placed.')
    studio.select([studio.cell['devices'][-1]['id']],'schematic')
    for key,value in {'Name':'C2','net:c0':'P','net:c1':'N','modelparam:w':'3',
                      'modelparam:l':'10','modelparam:mf':'4'}.items():
        studio.form_fields[key].setText(value)
    require(studio.apply_inspector(True),'Historical second MiM edit failed.')
    app.processEvents()


def runtime_identity(engine, destination, frozen):
    folder = Path(engine).resolve().parent
    manifest = folder/'runtime-manifest.json'
    if not manifest.is_file():
        require(not frozen,'Included ngspice runtime manifest missing.')
        return dict(files={Path(engine).name:file_digest(engine)},manifest_sha256=None)
    data = json.loads(manifest.read_bytes())
    require(Path(engine).name in data['files'],'Selected engine absent from runtime manifest.')
    for name, expected in data['files'].items():
        path = folder/name
        require(path.resolve().is_relative_to(folder) and path.is_file() and file_digest(path) == expected,
                'Runtime payload differs: '+name)
    if destination is not None:
        shutil.copyfile(manifest,destination)
    return dict(files=data['files'],manifest_sha256=file_digest(manifest))


def place_esd(app, studio, technology):
    """Build the six specimens through the actual library and inspector."""
    from PySide6.QtCore import Qt
    from .catalog import binding_for, parameter_values
    project = example('empty')
    project['pdk'] = clone(technology)
    project['cells'][0].update(name='esd_selected_devices', ports=[])
    studio.set_project(project)
    bindings = []
    for i in range(6):
        item = next((studio.library_list.item(j) for j in range(studio.library_list.count())
                     if studio.library_list.item(j).data(Qt.UserRole) == KEY), None)
        require(item is not None and not item.data(Qt.UserRole+3), 'Corrected ESD symbol unavailable.')
        studio.library_list.setCurrentItem(item)
        studio.place_library_button.click()
        require(studio.schematic.placement is not None, 'ESD library placement did not start.')
        studio.place_device_at(300+i*300, 250)
        studio.cancel_tool()
        require(len(studio.cell['devices']) == i+1, 'Unexpected ESD placement count.')
        placed = studio.cell['devices'][-1]
        studio.select([placed['id']], 'schematic')
        length, copies = (.9, 2., 4.)[i//2], (1,3)[i%2]
        fields = {'Name': 'Dq'+str(i), 'param:w': '10u', 'param:l': str(length)+'u',
                  'modelparam:nf': '1', 'modelparam:mult': str(copies)}
        fields.update({'net:'+p: 'q'+str(i)+p for p in 'dgsb'})
        for key, value in fields.items():
            require(key in studio.form_fields, 'Missing ESD inspector field: '+key)
            studio.form_fields[key].setText(value)
        require(studio.apply_inspector(True), 'ESD inspector rejected supported bin.')
        app.processEvents()
        placed = studio.cell['devices'][-1]
        binding = binding_for(studio.project['pdk'], placed)
        values = parameter_values(binding, placed)
        require(binding['model'] == MODEL and binding['pin_order'] == list('dgsb')
                and placed['nets'] == {p:'q'+str(i)+p for p in 'dgsb'}
                and all(values[k] == v for k,v in dict(w=10,l=length,nf=1,mult=copies).items()),
                'GUI-selected ESD terminals or parameters differ.')
        bindings.append(dict(device_id=placed['id'], name=placed['name'], values=values,
                             model_ref=clone(placed['model_ref']), model=binding['model']))
    return bindings


def stimulus(selected, drive):
    """Attach only test sources; preserve the six saved GUI devices exactly."""
    project = clone(selected)
    cell = next(c for c in project['cells'] if c['id'] == project['top'])
    require(len(project['cells']) == 1 and cell['id'] == project['cells'][0]['id']
            and len(cell['devices']) == 6 and not cell.get('wires'), 'Unexpected saved GUI circuit.')
    original = clone(cell['devices'])
    vg = device('V','VG',0,0,value='.8',nets={'p':'sweep','n':'0'})
    vg['source']['ac'] = '0'
    cell['devices'].append(vg)
    for i in range(6):
        for pin,value in dict(d=.6,g=0.,s=0.,b=-.15).items():
            source = device('V','Vq'+str(i)+pin,0,0,value=str(value),
                            nets={'p':'q'+str(i)+pin,'n':'sweep' if pin == 'g' else '0'})
            source['source']['ac'] = str(int(pin == drive))
            cell['devices'].append(source)
    for index,source in enumerate(cell['devices'][6:]):
        source.update(x=(index%8)*300,y=1500+(index//8)*300)
        source['net_labels'] = clone(source['nets'])
    require(cell['devices'][:6] == original, 'Stimulus changed a saved GUI device.')
    return project


@contextmanager
def capture_execution(execution_id, case, role, engine, native_env):
    from . import engines
    previous = engines.execute
    calls = []
    def execute(args, cwd, timeout=180, input_text=None, on_line=None, env=None):
        if '-r' not in args:
            return previous(args,cwd,timeout,input_text,on_line,env)
        arguments = list(map(str,args))
        folder = Path(cwd).resolve()
        raw = Path(arguments[arguments.index('-r')+1])
        deck = Path(arguments[-1])
        require(not calls and folder.name == role and raw.parent == deck.parent == folder,
                'Unexpected native execution or output location.')
        require(arguments[0] == engine, 'Unselected ESD engine.')
        record = dict(schema=1,execution_id=execution_id,case=case,role=role,cwd=str(folder),command=arguments,
                      engine_sha256=file_digest(engine),deck_filename=deck.name,deck_sha256=file_digest(deck),
                      raw_filename=raw.name,started_utc=datetime.now(timezone.utc).isoformat(),
                      timeout_seconds=timeout,status='RUNNING',environment=native_env)
        write(folder/'execution-receipt.json',record)
        start = time.monotonic()
        try:
            log = previous(args,cwd,timeout,input_text,on_line,native_env)
            (folder/'engine.log').write_bytes(log.encode('utf-8'))
            require(file_digest(deck) == record['deck_sha256'], 'Executed deck changed.')
            record.update(status='PASS',raw_sha256=file_digest(raw),log_sha256=file_digest(folder/'engine.log'))
            return log
        except Exception as exc:
            record.update(status='FAIL',error=repr(exc))
            raise
        finally:
            record.update(ended_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-start)
            write(folder/'execution-receipt.json',record)
            calls.append(record)
    engines.execute = execute
    try:
        yield
        require(len(calls) == 1 and calls[0]['status'] == 'PASS', 'Native execution missing or failed.')
    finally:
        engines.execute = previous


def electrical(selected, out, engine, execution_id, native_env):
    from .engines import run_ngspice
    records = []
    for corner,temp,drive in CONDITIONS:
        name = f'{corner}-{temp}-{drive}'
        folder = out/name
        folder.mkdir(parents=True,exist_ok=False)
        project = stimulus(selected,drive)
        settings = dict(type='dc' if drive == 'dc' else 'ac',corner=corner,temperature=temp,
                        source='VG',dc_start='0',dc_stop='1.2',dc_step='.03',start='1k',end='1g',points=5)
        roles = ('application',*FAULTS) if drive == 'dc' else ('application',)
        for role in roles:
            candidate = clone(project)
            candidate['name'] = f'icstudio-esd-nvt-v2 {execution_id} {name} {role}'
            for row in candidate['cells'][0]['devices'][:6]:
                if role == 'wrong-multiplicity': row['model_params']['mult'] = str(float(row['model_params']['mult'])*2)
                elif role == 'wrong-gate':
                    row['nets']['g'] = row['nets']['s']
                    row['net_labels']['g'] = row['net_labels']['s']
                elif role == 'wrong-body':
                    row['nets']['b'] = row['nets']['s']
                    row['net_labels']['b'] = row['net_labels']['s']
                elif role == 'wrong-length':
                    from .catalog import binding_for, parameter_values
                    length = parameter_values(binding_for(candidate['pdk'],row),row)['l']
                    row['params']['l'] = '2u' if length == 4 else '4u'
            dest = folder/role
            dest.mkdir()
            save_project(candidate,dest/'input.icproj')
            candidate = load_project(dest/'input.icproj')
            with capture_execution(execution_id,name,role,engine,native_env):
                result = run_ngspice(candidate,candidate['top'],settings,engine,dest)
            write(dest/'comparison-result.json',result)
        records.append(dict(corner=corner,temperature_c=temp,drive=drive,roles=list(roles)))
        print(name,'NATIVE COMPLETE',flush=True)
    return records


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--package',type=Path)
    parser.add_argument('--bundled-default',action='store_true')
    parser.add_argument('--predecessor',type=Path)
    parser.add_argument('--execution-id',required=True)
    parser.add_argument('--development',action='store_true')
    parser.add_argument('--ngspice',default='')
    a = parser.parse_args(arguments)
    require((a.bundled_default and a.predecessor is not None and a.package is None) or
            (not a.bundled_default and a.package is not None),
            'Choose the bundled-default with its exact predecessor, or the optional package.')
    require(re.fullmatch('[0-9a-f]{32}',a.execution_id), 'Invalid execution identity.')
    frozen = bool(getattr(sys,'frozen',False))
    require(a.development != frozen, 'Source runs require --development; frozen runs reject it.')
    require(not frozen or not a.ngspice, 'Frozen runs require the included engine.')
    a.out = a.out.resolve()
    a.out.mkdir(parents=True,exist_ok=False)
    from .build_identity import identity
    from .bundled_pdks import bundle_root
    from .spice_program import find_ngspice
    resources = bundle_root().parents[2]
    root = bundle_root()/'sky130A'
    initial_sources = source_identity()
    selected_sha = DEFAULT_CANDIDATE if a.bundled_default else OPTIONAL
    selected_path = root if a.bundled_default else a.package
    old_path = a.predecessor if a.predecessor is not None else root
    package = verified_package(selected_path,selected_sha)
    base = verified_package(old_path,BASE)
    engine = find_ngspice(a.ngspice)
    require(engine is not None, 'Selected ngspice is unavailable.')
    if frozen:
        require(Path(engine).resolve().is_relative_to(resources/'icstudio/assets/runtime/ngspice'),
                'Frozen probe selected an external simulation engine.')
    report = dict(schema='esd-desktop-probe-v1',status='FAIL',execution_id=a.execution_id,
                  execution_root=str(a.out),frozen=frozen,build=identity(),source_files=initial_sources,
                  executable=str(Path(sys.executable).resolve()),executable_sha256=file_digest(sys.executable),
                  engine=engine,engine_sha256=file_digest(engine),package_sha256=selected_sha,base_sha256=BASE,
                  resource_root=str(resources),qualified=False,default_promoted=False,chunk_complete=False,
                  installed_acceptance=False,conditions=list(CONDITIONS))
    if a.bundled_default: report['selection'] = 'bundled-default'
    report['runtime'] = runtime_identity(engine,a.out/'ngspice-runtime-manifest.json',frozen)
    environment_root = a.out/'native-environment'
    environment_root.mkdir()
    binding = dict(mode='installed' if frozen else 'source-pilot',resource_root=str(resources))
    report['native_environment'] = native_environment(binding,Path(engine),environment_root)
    report['native_runtime_before'] = runtime(binding,Path(engine),report['native_environment'])
    collection = bundle_root()/'collection.json'
    report['collection_sha256'] = file_digest(collection)
    shutil.copyfile(collection,a.out/'bundled-collection.json')
    app = studio = None
    errors = []
    try:
        if frozen:
            require(report['build']['dirty'] is False and re.fullmatch('[0-9a-f]{40}',report['build']['commit']),
                    'Frozen build identity is not a clean candidate.')
        os.environ['XDG_DATA_HOME'] = str(a.out/'profile/data')
        os.environ['XDG_CONFIG_HOME'] = str(a.out/'profile/config')
        from PySide6.QtCore import QSettings, QStandardPaths
        from PySide6.QtWidgets import QApplication
        from .gui import Studio
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(a.out/'profile/settings'))
        QStandardPaths.writableLocation = staticmethod(lambda kind:str(a.out/'profile'/str(kind.value)))
        app = QApplication([])
        app.setStyle('Fusion')
        studio = Studio(recover=False)
        studio.error = lambda error:errors.append(str(error))
        studio.maybe_save = lambda:True
        studio.live_check.setChecked(False)
        studio.show()
        registry = studio.pdk_registry
        oldkey = install_gui(app,studio,old_path/'package.json')
        require(registry.technology(oldkey)['simulation']['catalog'][KEY]['unavailable'], 'Baseline ESD availability changed.')
        prior_mim(app,studio,registry.technology(oldkey))
        report['old_before'] = save_reopen(app,studio,a.out/'old-before')
        if a.bundled_default:
            from .bundled_pdks import packages
            rows = [row for row in packages(verify=True) if row['name'] == 'sky130A']
            require(len(rows)==1 and Path(rows[0]['path']).resolve()==root.resolve() and
                    rows[0]['revision']==DEFAULT_REVISION,'Bundled default discovery differs.')
            hub = studio.project_hub(); app.processEvents()
            key = 'sky130A@'+DEFAULT_REVISION
            require(hub.select_pdk(key) and hub.current_pdk()['status']=='Available offline',
                    'Hub did not select the bundled default.')
            hub.show_page('new'); hub.name.setText('ESD default acceptance'); hub.create_button.click()
            deadline = time.monotonic()+120
            while hub.busy() and time.monotonic()<deadline:
                app.processEvents(); time.sleep(.02)
            app.processEvents()
            require(not hub.busy() and studio.project['pdk']['revision']==DEFAULT_REVISION,
                    'Hub did not create a project with the selected default.')
            report['default_discovery'] = dict(source_of_selection='project-hub-bundled',
                hub_selected=key, source_path=str(root.resolve()), manifest_sha256=selected_sha,
                hub_project=save_reopen(app,studio,a.out/'hub-project'))
        else:
            key = install_gui(app,studio,selected_path/'package.json')
        require(key != oldkey,'Optional revision did not remain separate.')
        current = registry.technology(key)
        with selected_file('getOpenFileName',report['old_before']['project']): studio.open_project()
        report['old_after'] = save_reopen(app,studio,a.out/'old-after')
        require(report['old_before']['package_lock'] == report['old_after']['package_lock'], 'Historical lock migrated.')
        report['bindings'] = place_esd(app,studio,current)
        report['selected'] = save_reopen(app,studio,a.out/'selected')
        selected = load_project(report['selected']['project'])
        report['cases'] = electrical(selected,a.out/'native',engine,a.execution_id,report['native_environment'])
        report['registry'] = dict(old_key=oldkey,current_key=key,current_root=current['package_root'])
        registry.verify(oldkey)
        registry.verify(key)
        shutil.copyfile(old_path/'package.json',a.out/'base-package.json')
        shutil.copyfile(selected_path/'package.json',a.out/('selected-package.json' if a.bundled_default else 'optional-package.json'))
        shutil.copyfile(Path(current['package_root'])/'package.json',a.out/'registry-package.json')
        verified_package(selected_path,selected_sha)
        verified_package(old_path,BASE)
        require(file_digest(engine) == report['engine_sha256'] and file_digest(sys.executable) == report['executable_sha256'],
                'Selected executable changed.')
        require(runtime_identity(engine,None,frozen) == report['runtime'],'Runtime support files changed.')
        report['native_runtime_after'] = runtime(binding,Path(engine),report['native_environment'])
        require(report['native_runtime_after'] == report['native_runtime_before'],'Native runtime identity changed.')
        require(file_digest(collection) == report['collection_sha256'],'Bundled collection changed.')
        require(not errors, 'GUI errors: '+str(errors))
        report['status'] = 'PASS'
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        if studio is not None:
            studio.saved_hash = digest(studio.project)
            studio.close()
            app.processEvents()
        if source_identity() != initial_sources:
            report.update(status='FAIL',source_error='Application sources changed during probe.')
        report['errors'] = errors
        write(a.out/'report.json',report)
        files = {}
        for path in sorted(a.out.rglob('*')):
            require(not path.is_symlink() and not path.is_junction(),'Linked producer evidence.')
            if path.is_file(): files[path.relative_to(a.out).as_posix()] = file_digest(path)
        write(a.out/'producer-manifest.json',dict(schema=1,execution_id=a.execution_id,files=files))
    print(json.dumps({k:report.get(k) for k in ('status','frozen','error','source_error')},indent=2),flush=True)
    return int(report['status'] != 'PASS')
