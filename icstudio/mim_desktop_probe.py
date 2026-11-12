"""Bounded MiM Qt lifecycle and queued DRC/LVS acceptance evidence.

This built-in probe is also executable from source for development. Neither
mode establishes installation provenance or full MiM electrical qualification;
an external checker must bind a frozen run to its installed artifact.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import traceback

from .model import clone, digest, design_digest, example, file_digest

OLD_MANIFEST = '42cafd2b1407783d361cfbb276abe3ba9e97b2c06a716af6c9069c8426852413'
CASES = tuple((plate, angle) for plate in (1, 2) for angle in (0, 90))
STAGES = ('preflight', 'layout_export', 'drc', 'lvs_extraction', 'lvs', 'integrity')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def verified_package(root, expected=None):
    root = Path(root)
    require(not root.is_symlink() and not root.is_junction(), 'Linked package root is unsupported.')
    root = root.resolve()
    manifest = root/'package.json'
    if expected:
        require(file_digest(manifest) == expected, 'Unexpected package manifest.')
    data = json.loads(manifest.read_bytes())
    require(data.get('id') == 'sky130A' and bool(data.get('files')), 'Expected a locked SKY130 package.')
    for name, sha in data['files'].items():
        original = root/name
        path = original.resolve()
        require(path.is_relative_to(root) and path.is_file()
                and file_digest(path) == sha, 'Changed package asset: '+name)
        require(original.is_relative_to(root) and not any(p.is_symlink() or p.is_junction()
                for p in (original, *original.parents) if p == root or p.is_relative_to(root)),
                'Linked package asset is unsupported: '+name)
    return data


def historical_package(current_root, resource_root, destination):
    """Reconstruct only the retained manifest, using its exact original assets."""
    manifest = Path(resource_root)/'icstudio/assets/qualification/sky130-mim-base-v1/package.json'
    require(file_digest(manifest) == OLD_MANIFEST, 'Changed retained pre-MiM manifest.')
    data = json.loads(manifest.read_bytes())
    source = Path(current_root).resolve()
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name, sha in {'package.json': OLD_MANIFEST, **data['files']}.items():
        original = manifest if name == 'package.json' else (source/name).resolve()
        require(name == 'package.json' or original.is_relative_to(source), 'Unsafe historical asset.')
        require(file_digest(original) == sha, 'Historical asset unavailable: '+name)
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        require(file_digest(target) == sha, 'Historical asset changed during reconstruction.')
    verified_package(destination, OLD_MANIFEST)
    return destination


def capture_runtime(destination, resources, frozen):
    """Capture installed runtime locks without copying the runtime payload."""
    from . import digital_runtime
    runtime = digital_runtime.installed()
    require(runtime is not None, 'The included physical runtime is not ready.')
    digital_runtime.identity(runtime)
    payload = digital_runtime.payload_root().resolve()
    if frozen:
        require(payload.is_relative_to(resources), 'Frozen acceptance cannot use an external payload.')
    backend = payload/'backend/icstudio'
    require(backend.is_dir(), 'Included physical backend is missing.')
    files = {p.name: file_digest(p) for p in sorted(backend.glob('*.py'))}
    require(bool(files), 'Included physical backend has no Python inputs.')
    sources = {'payload-manifest.json': payload/'manifest.json',
               'runtime.json': Path(runtime['root'])/'opt/icstudio/runtime.json',
               'files.json': Path(runtime['root'])/'opt/icstudio/files.json'}
    destination.mkdir(parents=True, exist_ok=False)
    for name, source in sources.items():
        shutil.copyfile(source, destination/name)
    write(destination/'backend-files.json', files)
    return dict(runtime=runtime, payload_root=str(payload), backend_root=str(backend),
                backend_files=files, state_root=str(digital_runtime.state_root()),
                files={name: file_digest(source) for name, source in sources.items()})


@contextmanager
def selected_file(method, path):
    """Supply the selected path only; execute the application's real action."""
    from PySide6.QtWidgets import QFileDialog
    original = getattr(QFileDialog, method)
    setattr(QFileDialog, method, staticmethod(lambda *args, **kwargs: (str(path), '')))
    try:
        yield
    finally:
        setattr(QFileDialog, method, original)


def submit_form(app, dialog, values=None):
    from PySide6.QtWidgets import QComboBox, QDialogButtonBox
    require(dialog is not None, 'Expected an editable application form.')
    for key, value in (values or {}).items():
        widget = dialog.fields[key]
        if isinstance(widget, QComboBox):
            require(widget.findText(str(value)) >= 0, 'Unknown form choice: '+key)
            widget.setCurrentText(str(value))
        else:
            widget.setText(str(value))
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
    require(not dialog.error.text(), 'Application form rejected: '+dialog.error.text())
    app.processEvents()


def generate(app, studio):
    from PySide6.QtWidgets import QDialogButtonBox
    form = studio.mos_layout_dialog()
    if form is not None:
        submit_form(app, form)
    review = studio._review_dialog
    apply = review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
    require(apply.isEnabled(), 'Generation review did not allow application.')
    apply.click()
    app.processEvents()
    require(not review.isVisible() and bool(studio.cell.get('pdk_layouts')), 'Generation was not applied.')


def save_reopen(app, studio, folder):
    from .model import load_project
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/'project.icproj'
    before = clone(studio.project)
    with selected_file('getSaveFileName', path):
        require(studio.save(as_new=True), 'Application save failed.')
    studio.close_project()
    require(studio.project['id'] != before['id'], 'Application did not close the saved project.')
    with selected_file('getOpenFileName', path):
        studio.open_project()
    app.processEvents()
    reopened = load_project(path)
    require(studio.project == reopened and reopened == before, 'Saved/reopened application state differs.')
    with selected_file('getSaveFileName', folder/'schematic.spice'):
        studio.export_spice()
    from .testbenches import native_subcircuit
    (folder/'reference.spice').write_text(native_subcircuit(studio.project, studio.cid), encoding='utf-8')
    return dict(project=str(path), project_sha256=file_digest(path), design_hash=design_digest(reopened),
                package_lock=clone(reopened['pdk']['package_lock']),
                schematic=str(folder/'schematic.spice'), reference=str(folder/'reference.spice'))


def place_edit(app, studio, technology, plate, count=1, top='device_coupon'):
    from PySide6.QtCore import Qt
    from .catalog import binding_for, parameter_values
    p = example('empty')
    p['pdk'] = clone(technology)
    p['cells'][0].update(name=top, ports=['P', 'N'])
    studio.set_project(p)
    key = f'sky130_fd_pr/cap_mim_m3_{plate}.sym'
    item = next((studio.library_list.item(i) for i in range(studio.library_list.count())
                 if studio.library_list.item(i).data(Qt.UserRole) == key), None)
    require(item is not None and not item.data(Qt.UserRole+3), 'Required MiM catalog entry is unavailable.')
    studio.library_list.setCurrentItem(item)
    studio.place_library_button.click()
    require(studio.schematic.placement is not None, 'Library placement did not start.')
    studio.place_device_at(300, 250)
    studio.cancel_tool()
    require(len(studio.cell['devices']) == 1, 'Expected exactly one placed device.')
    device = studio.cell['devices'][0]
    studio.select([device['id']], 'schematic')
    for key, value in {'Name': 'C1', 'net:c0': 'P', 'net:c1': 'N',
                       'modelparam:w': '2', 'modelparam:l': '10', 'modelparam:mf': str(count)}.items():
        studio.form_fields[key].setText(value)
    require(studio.apply_inspector(True), 'Inspector could not apply MiM parameters.')
    app.processEvents()
    device = studio.cell['devices'][0]
    binding = binding_for(studio.project['pdk'], device)
    values = parameter_values(binding, device)
    require(binding['model'] == f'sky130_fd_pr__cap_mim_m3_{plate}'
            and binding['pin_order'] == ['c0', 'c1'] and device['nets'] == {'c0': 'P', 'c1': 'N'}
            and all(values[k] == v for k, v in dict(w=2, l=10, mf=count).items()),
            'Placed model, terminal order or resolved parameters differ.')
    return dict(model=binding['model'], values=values, model_ref=clone(device['model_ref']),
                emit_parameters=clone(binding['emit_parameters']), terminals=['P', 'N'])


def layout_case(app, studio, technology, plate, angle, folder):
    case = f'p{plate}-r{angle}'
    top = f'mim_p{plate}_r{angle}_{studio.probe_execution_id[:12]}'
    binding = place_edit(app, studio, technology, plate, top=top)
    generate(app, studio)
    generated = clone(studio.cell['shapes'])
    studio.undo()
    require(not studio.cell.get('pdk_layouts'), 'Undo did not remove generated footprint.')
    studio.redo()
    require(studio.cell['shapes'] == generated, 'Redo did not restore generated footprint.')
    for pin in list(studio.cell['layout_pins']):
        submit_form(app, studio.cell_port_dialog(), dict(name='P' if pin['pin'] == 'c0' else 'N',
                    layer=pin['layer'], x=pin['point'][0]/1000, y=pin['point'][1]/1000))
    if angle:
        studio.select([s['id'] for s in studio.cell['shapes']], 'layout')
        submit_form(app, studio.transform_layout_dialog(), dict(rotation=angle, annotations='Yes'))
    row = save_reopen(app, studio, folder)
    with selected_file('getSaveFileName', folder/'layout.gds'):
        studio.export_gds()
    row.update(case=case, execution_id=studio.probe_execution_id, top=top,
               plate=plate, rotation=angle, binding=binding,
               gds=str(folder/'layout.gds'), gds_sha256=file_digest(folder/'layout.gds'),
               generation=clone(studio.cell['pdk_layouts']))
    return row


def wait_job(app, studio, row, timeout=300):
    from PySide6.QtTest import QTest
    deadline = time.monotonic()+timeout
    while row['state'] in ('Queued', 'Running', 'Stopping') and time.monotonic() < deadline:
        QTest.qWait(40)
    require(row['state'] == 'Complete' and 'result' in row, 'Queued physical worker did not complete: '+row['state'])
    result = row['result']
    require(not result.get('reused_from'), 'Acceptance requires a fresh queued result.')
    require(result.get('silicon_report'), 'Physical worker returned no report.')
    require(result['design_hash'] == design_digest(row['job']['project']), 'Worker input identity changed.')
    app.processEvents()
    return result


def queue_layout(app, studio, reference_path, case, *, missing=False):
    previous = studio.simple_form
    studio.simple_form = lambda *args, **kwargs: {'Schematic SPICE file': str(reference_path), 'Schematic cell': studio.cell['name']}
    before = len(studio.run_manager.rows)
    try:
        studio.run_layout_verification()
    finally:
        studio.simple_form = previous
    require(len(studio.run_manager.rows) == before+1, 'Application did not enqueue exactly one layout job.')
    row = studio.run_manager.rows[-1]
    result = wait_job(app, studio, row)
    report = result['silicon_report']
    return dict(case=case, execution_id=studio.probe_execution_id, top=studio.cell['name'],
                job_id=row['id'], job_directory=str(row['path']),
                input_sha256=file_digest(row['path']/'input.json'),
                result_sha256=file_digest(row['path']/'result.json'),
                evidence_directory=result['evidence_directory'], report=report,
                settings=clone(result['settings']), state=row['state'],
                design_hash=result['design_hash'], native_execution=not missing)


def physical_cases(app, studio, lifecycle, technology, arguments):
    from .layout_import import read_layout
    from .catalog import link_technology
    from .layout import rect
    results = []
    controls = []
    for item in lifecycle:
        # Use only the written masks, not the simulation package's saved objects.
        p, _ = read_layout(Path(item['gds']))
        link_technology(p, technology)
        p['cells'][0]['ports'] = ['P', 'N']
        studio.set_project(p)
        row = queue_layout(app, studio, item['reference'], item['case'])
        require(row['report']['status'] == 'passed' and
                tuple(s['name'] for s in row['report']['stages']) == STAGES and
                all(s['status'] == 'passed' for s in row['report']['stages']), 'Current native layout did not pass all six stages.')
        if arguments.managed:
            execution = row['report'].get('execution', {})
            require(execution.get('runtime', {}).get('kind') == ('wsl' if os.name == 'nt' else 'linux')
                    and bool(execution.get('received_files')), 'Selected included runtime provenance is missing.')
        results.append(row)
        if item['case'] != 'p2-r90':
            continue
        baseline = design_digest(studio.project)
        content = lambda p: {k: v for k, v in p.items() if k not in ('revision', 'modified')}
        baseline_content = clone(content(studio.project))
        layer = next(v['name'] for v in technology['layers'] if (v['gds'], v['datatype']) == (68, 20))
        studio.add_shape(rect(layer, 100000, 100000, 100, 100))
        studio.refresh_silicon()
        require('STALE' in studio.silicon_status.text(), 'Layout edit did not invalidate prior passing evidence.')
        faulty = queue_layout(app, studio, item['reference'], 'narrow-metal')
        stages = {s['name']: s for s in faulty['report']['stages']}
        require(faulty['report']['status'] == 'failed' and stages['drc']['status'] == 'failed'
                and faulty['report'].get('drc_count', 0) > 0, 'Narrow-metal control did not fail actual DRC.')
        controls.append(dict(name='stale-edit', before_design_hash=baseline,
                             before_content_hash=digest(baseline_content),
                             after_design_hash=faulty['design_hash'], displayed=True))
        controls.append(faulty)
        studio.undo()
        require(content(studio.project) == baseline_content, 'Undo did not restore the original design content.')
        # Undo advances document revision; a repaired run must have its own
        # current design identity, never reuse the earlier passing receipt.
        require(design_digest(studio.project) != baseline, 'Undo failed to advance document identity.')
        controls[0]['repaired_content_hash'] = digest(content(studio.project))
        repaired = queue_layout(app, studio, item['reference'], 'repaired')
        require(repaired['report']['status'] == 'passed', 'Fresh repaired layout did not pass.')
        controls.append(repaired)
        old_mode = studio.settings.value('physical/toolchain', 'auto')
        old_magic = studio.settings.value('engine/magic', '')
        studio.settings.setValue('physical/toolchain', 'custom')
        studio.settings.setValue('engine/magic', str(arguments.out/'missing-magic-executable'))
        try:
            blocked = queue_layout(app, studio, item['reference'], 'missing-engine', missing=True)
        finally:
            studio.settings.setValue('physical/toolchain', old_mode)
            studio.settings.setValue('engine/magic', old_magic)
        require(blocked['report']['status'] == 'blocked' and 'BLOCKED' in studio.silicon_status.text(),
                'Missing selected engine was not shown as blocked.')
        controls.append(blocked)
    return results, controls


def main(arguments=None):
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--execution-id', required=True,
                        help='Launcher-generated 32 lowercase hexadecimal characters.')
    parser.add_argument('--mode', choices=('lifecycle', 'physical'), default='physical')
    parser.add_argument('--physical-pdk', type=Path)
    parser.add_argument('--managed', action='store_true')
    for name in ('magic', 'netgen'):
        parser.add_argument('--'+name, default='')
    a = parser.parse_args(arguments)
    require(re.fullmatch('[0-9a-f]{32}', a.execution_id), 'Invalid execution identity.')
    a.out = a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=False)
    from .build_identity import identity
    from .bundled_pdks import bundle_root
    resources = bundle_root().parents[2]
    result = dict(schema=1, status='failed', mode=a.mode, execution_id=a.execution_id, build=identity(),
                  frozen=bool(getattr(sys, 'frozen', False)), executable=str(Path(sys.executable).resolve()),
                  executable_sha256=file_digest(sys.executable), resource_root=str(resources),
                  qualified=False, release_ready=False, full_mim_installed=False,
                  native_execution=False, lifecycle=[], binding_lifecycle=[], physical=[], controls=[],
                  scope='Qt lifecycle and optional four fresh queued Magic DRC/Netgen LVS inputs only. '
                        'Frozen status alone does not prove installation. No public KLayout, electrical60, '
                        'complete MiM family or manufacturing acceptance.')
    app = studio = None
    errors = []
    try:
        if result['frozen'] and a.mode == 'physical':
            require(a.managed and not a.magic and not a.netgen, 'Frozen physical probe requires included engines.')
        from PySide6.QtCore import QSettings, QStandardPaths
        from PySide6.QtWidgets import QApplication
        from .gui import Studio
        from . import digital_runtime
        # GUI profiles are isolated; an already installed included runtime keeps
        # the launcher's selected state directory on both Windows and Linux.
        if a.managed:
            os.environ.setdefault('ICSTUDIO_DIGITAL_STATE', str(digital_runtime.state_root()))
        os.environ['XDG_DATA_HOME'] = str(a.out/'profile/data')
        os.environ['XDG_CONFIG_HOME'] = str(a.out/'profile/config')
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(a.out/'profile/settings'))
        QStandardPaths.writableLocation = staticmethod(lambda kind: str(a.out/'profile'/str(kind.value)))
        app = QApplication([])
        app.setStyle('Fusion')
        studio = Studio(recover=False)
        studio.probe_execution_id = a.execution_id
        studio.error = lambda error: errors.append(str(error))
        studio.maybe_save = lambda: True
        studio.jobs_dir = a.out/'runs with spaces'
        studio.live_check.setChecked(False)
        studio.resize(1400, 960)
        studio.show()
        root = bundle_root()/'sky130A'
        collection = bundle_root()/'collection.json'
        entry = next(row for row in json.loads(collection.read_bytes())['packages'] if row['variant'] == 'sky130A')
        package = verified_package(root, entry['manifest_sha256'])
        original = historical_package(root, resources, a.out/'historical-package')
        registry = studio.pdk_registry
        old_key = registry.install(original/'package.json')
        # Save historical state before installing today's package in the same registry.
        old_binding = place_edit(app, studio, registry.technology(old_key), 2, 4)
        old_row = save_reopen(app, studio, a.out/'binding-old')
        current_key = registry.install(root/'package.json')
        require(current_key != old_key, 'Current and historical revisions unexpectedly coincide.')
        with selected_file('getOpenFileName', old_row['project']):
            studio.open_project()
        old_again = save_reopen(app, studio, a.out/'binding-old-after-install')
        require(old_again['package_lock'] == old_row['package_lock'], 'Installing current package changed a saved lock.')
        require(old_binding['emit_parameters'] == dict(w='w', l='l', vm='mf', m='mf'), 'Historical mapping changed.')
        current = registry.technology(current_key)
        registry_manifests = {key: file_digest(registry.root/key/'package.json') for key in (old_key, current_key)}
        new_binding = place_edit(app, studio, current, 2, 4)
        new_row = save_reopen(app, studio, a.out/'binding-current')
        require(new_binding['emit_parameters'] == dict(w='w', l='l', mf='mf', m='mf'), 'Current mapping differs.')
        result['binding_lifecycle'] = [dict(kind='historical-before', binding=old_binding, **old_row),
            dict(kind='historical-after-current-install', binding=old_binding, **old_again),
            dict(kind='current', binding=new_binding, **new_row)]
        for plate, angle in CASES:
            result['lifecycle'].append(layout_case(app, studio, current, plate, angle, a.out/f'p{plate}-r{angle}'))
        result['bundled_package'] = dict(path=str(root), manifest_sha256=file_digest(root/'package.json'),
            collection_sha256=file_digest(collection), revision=package['revision'], files=package['files'],
            current_key=current_key, historical_key=old_key, historical_original_manifest_sha256=OLD_MANIFEST)
        result['registry_manifests'] = registry_manifests
        shutil.copyfile(root/'package.json', a.out/'bundled-package.json')
        shutil.copyfile(collection, a.out/'bundled-collection.json')
        from .spice_program import find_ngspice
        selected = find_ngspice('')
        result['simulation_engine_discovery'] = dict(path=selected,
            sha256=file_digest(selected) if selected else None, executed=False)
        if a.mode == 'physical':
            require(a.physical_pdk is not None, 'Physical mode requires the explicit locked physical adapter.')
            lock_path = resources/'examples/sky130-qualification-lock.json'
            lock = json.loads(lock_path.read_bytes())
            physical = verified_package(a.physical_pdk, lock['manifest_sha256'])
            tech = clone(physical['technology'])
            tech.update(package_root=str(a.physical_pdk.resolve()),
                        package_lock={k: physical[k] for k in ('id', 'revision', 'files')})
            result['physical_package'] = dict(path=str(a.physical_pdk.resolve()),
                manifest_sha256=file_digest(a.physical_pdk/'package.json'), release_lock_sha256=file_digest(lock_path),
                revision=physical['revision'], files=physical['files'])
            shutil.copyfile(a.physical_pdk/'package.json', a.out/'physical-package.json')
            shutil.copyfile(lock_path, a.out/'physical-release-lock.json')
            studio.settings.setValue('physical/toolchain', 'included' if a.managed else 'custom')
            for name in ('magic', 'netgen'):
                studio.settings.setValue('engine/'+name, str(a.out/('unselected-custom-'+name)) if a.managed else getattr(a, name))
            if a.managed:
                result['managed_runtime_before'] = capture_runtime(a.out/'runtime/before', resources, result['frozen'])
            result['physical'], result['controls'] = physical_cases(app, studio, result['lifecycle'], tech, a)
            result['native_execution'] = True
            verified_package(a.physical_pdk, lock['manifest_sha256'])
            if a.managed:
                result['managed_runtime_after'] = capture_runtime(a.out/'runtime/after', resources, result['frozen'])
                require(result['managed_runtime_after'] == result['managed_runtime_before'], 'Included runtime identity changed.')
        registry.verify(old_key)
        registry.verify(current_key)
        require(registry_manifests == {key: file_digest(registry.root/key/'package.json') for key in registry_manifests},
                'Installed registry manifests changed.')
        verified_package(root, entry['manifest_sha256'])
        require(file_digest(collection) == result['bundled_package']['collection_sha256'], 'Bundled collection changed.')
        require(file_digest(sys.executable) == result['executable_sha256'], 'Application executable changed.')
        result['input_guards'] = dict(bundled_package_unchanged=True, registry_assets_unchanged=True,
                                     executable_unchanged=True, physical_package_unchanged=a.mode == 'physical')
        require(not errors, 'Application errors: '+str(errors))
        result['status'] = 'passed'
    except Exception:
        result.update(error=traceback.format_exc(), errors=errors)
    finally:
        if studio:
            if studio.run_manager.busy:
                studio.run_manager.cancel(studio.run_manager.rows)
            studio.saved_hash = digest(studio.project)
            studio.close()
            app.processEvents()
        result['elapsed_seconds'] = time.monotonic()-started
        try:
            paths = list(a.out.rglob('*'))
            require(not any(path.is_symlink() for path in paths), 'Probe evidence must not contain symlinks.')
            files = {path.relative_to(a.out).as_posix(): file_digest(path) for path in sorted(paths)
                     if path.is_file() and path not in (a.out/'files.json', a.out/'report.json')}
            write(a.out/'files.json', files)
            result['files_sha256'] = file_digest(a.out/'files.json')
        except Exception:
            result.update(status='failed', inventory_error=traceback.format_exc())
        write(a.out/'report.json', result)
    print(json.dumps({key: result[key] for key in ('status', 'mode', 'execution_id', 'native_execution', 'elapsed_seconds')}
                     | {'report': str(a.out/'report.json'), 'error': result.get('error')}, indent=2))
    return int(result['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
