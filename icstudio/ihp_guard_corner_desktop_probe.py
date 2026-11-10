"""Additive Qt lifecycle producer for the opt-in IHP corner-safe body guard.

Source execution is development feedback. A frozen producer is not itself
installed acceptance: an independent parent verifier must bind its identity
and outputs and run fresh managed native checks. The original sixty-case
IHP resistor producer is unchanged.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]

from .model import clone, digest, file_digest, load_project
from .ihp_resistor_desktop_probe import PACKAGE, legacy, placement
from .mim_desktop_probe import capture_runtime, require, save_reopen, selected_file, submit_form, write


MODELS = ('rsil', 'rppd', 'rhigh')
CASES = tuple((model, angle) for model in MODELS for angle in (0, 90))
NATIVE = 'Native Metal1 body'
CORNER = 'Corner-safe Metal2 body (2/7 um only)'
OPTION = 'corner-safe-m2-v1'
RECIPE = 'ihp-resistor-guard-corner-safe-v1'
LEGACY_RECIPE = 'ihp-resistor-selected-v1'


def source_inventory():
    paths = set((ROOT/'icstudio').rglob('*.py')) | {ROOT/'tests/gui_ihp_guard_corner.py'}
    paths.add(ROOT/'icstudio/assets/pdks/ihp-sg13g2/package.json')
    for name in ('ihp-resistor-templates', 'ihp-resistor-legacy', 'ihp-guard-corner-safe'):
        paths.update(p for p in (ROOT/'icstudio/assets/qualification'/name).rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix(): file_digest(p) for p in sorted(paths)}


def content(studio):
    return {key: clone(studio.cell.get(key, [])) for key in
            ('devices', 'shapes', 'layout_pins', 'pdk_layouts', 'layout_ports', 'layout_texts')}


def select_device(studio):
    studio.select([studio.cell['devices'][0]['id']], 'schematic')


def form_for(studio, guard=NATIVE, access='Metal1'):
    select_device(studio)
    form = studio.mos_layout_dialog()
    require(form is not None and 'guard_routing' in form.fields, 'Guard routing form is unavailable.')
    widget = form.fields['guard_routing']
    require({widget.itemText(i) for i in range(widget.count())} == {NATIVE, CORNER},
            'Unexpected guard routing choices.')
    require(widget.currentText() == guard, 'Saved guard routing choice was not restored.')
    require(form.fields['terminal_access'].currentText() == access,
            'Saved terminal access choice was not restored.')
    return form


def review_labels(review):
    from PySide6.QtWidgets import QLabel
    return [label.text() for label in review.findChildren(QLabel) if label.text()]


def apply_review(app, studio):
    from PySide6.QtWidgets import QDialogButtonBox
    review = studio._review_dialog
    button = review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
    require(button.isEnabled(), 'Generation preview rejected: '+str(review_labels(review)))
    button.click()
    app.processEvents()
    require(not review.isVisible(), 'Generation Apply failed: '+str(review_labels(review)))
    require(len(studio.cell.get('pdk_layouts', [])) == 1, 'Expected exactly one linked footprint.')


def generate(app, studio, guard, *, previous=NATIVE, access='Metal1', previous_access='Metal1', capture=None):
    form = form_for(studio, previous, previous_access)
    if capture:
        app.processEvents()
        require(form.grab().save(str(capture/'regeneration-form.png')),
                'Could not capture the source regeneration form.')
    submit_form(app, form, {'guard_routing': guard, 'terminal_access': access})
    if capture:
        require(studio._review_dialog.grab().save(str(capture/'regeneration-preview.png')),
                'Could not capture the source regeneration preview.')
    apply_review(app, studio)


def check_state(studio, corner=True, access='Metal1', angle=0):
    from icstudio.ihp_layout import audit
    from icstudio.physical import connectivity
    device = studio.cell['devices'][0]
    record = studio.cell['pdk_layouts'][0]
    spec = record['spec']
    require(spec['recipe'] == (RECIPE if corner else LEGACY_RECIPE), 'Unexpected generation recipe.')
    if corner:
        require(device.get('physical_guard_routing') == OPTION and spec.get('guard_routing') == OPTION,
                'Corner-safe option was not retained in device and specification.')
        require(spec.get('guard_native_equivalence') is False, 'Opt-in geometry must not claim native equivalence.')
        require(spec['dimensions_nm'] == {'w': 2000, 'l': 7000}, 'Corner-safe dimensions differ.')
    else:
        require('physical_guard_routing' not in device and 'guard_routing' not in spec,
                'Returning to native must remove the option and preserve the legacy specification.')
    require(spec['terminal_vias'] is (access == 'Metal2'), 'Terminal access option differs.')
    expected = {'p': access+'.drawing', 'm': access+'.drawing',
                'body': 'Metal2.drawing' if corner else 'Metal1.drawing'}
    require({pin['pin']: pin['layer'] for pin in studio.cell['layout_pins']} == expected,
            'Body or resistor terminal layer contract differs.')
    orientation = record.get('orientation', {'rotation': 0, 'mirror': False})
    require(orientation == {'rotation': angle, 'mirror': False}, 'Saved orientation differs.')
    require(not audit(studio.project, studio.cid), 'Generated footprint is stale.')
    require(not connectivity(studio.project, studio.cid)['issues'], 'Generated terminal connectivity failed.')


def undo_redo(app, studio, before, after):
    studio.undo()
    app.processEvents()
    require(content(studio) == before, 'Undo changed the prior device, geometry, pins or record.')
    studio.redo()
    app.processEvents()
    require(content(studio) == after, 'Redo did not restore the exact applied state.')


def blocked_review(app, studio, *, guard=CORNER, access='Metal1', previous=NATIVE,
                   previous_access='Metal1', explanation=('2/7', '2 / 7', 'W/L'), folder=None):
    from PySide6.QtWidgets import QDialogButtonBox
    before = digest(studio.project)
    form = form_for(studio, previous, previous_access)
    submit_form(app, form, {'guard_routing': guard, 'terminal_access': access})
    review = studio._review_dialog
    button = review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
    messages = review_labels(review)
    require(not button.isEnabled() and digest(studio.project) == before,
            'Unsupported option mutated the project or enabled Apply.')
    require(any(token.lower() in ' '.join(messages).lower() for token in explanation),
            'Unsupported option explanation missing: '+str(messages))
    review.reject()
    app.processEvents()
    require(digest(studio.project) == before, 'Dismissing an invalid preview changed the project.')
    result = {'messages': messages, 'before_hash': before, 'after_hash': digest(studio.project),
              'apply_disabled': True, 'unchanged': True, 'requested_guard': guard,
              'requested_terminal_access': access}
    if folder is not None:
        folder.mkdir(parents=True, exist_ok=False)
        path = folder/'blocked.icproj'
        with selected_file('getSaveFileName', path):
            require(studio.save(as_new=True), 'Could not save the rejected control project.')
        require(digest(load_project(path)) == before, 'Saved rejected control differs from the unchanged design.')
        result.update(project=str(path), project_sha256=file_digest(path), cell_id=studio.cid)
    return result


def interruption_controls(app, studio, screenshot=None):
    before = digest(studio.project)
    form = form_for(studio)
    form.fields['guard_routing'].setCurrentText(CORNER)
    if screenshot:
        app.processEvents()
        require(form.grab().save(str(screenshot)), 'Could not capture the source form.')
    form.reject()
    app.processEvents()
    require(digest(studio.project) == before, 'Canceling the edited form changed the project.')
    form = form_for(studio)
    submit_form(app, form, {'guard_routing': CORNER, 'terminal_access': 'Metal1'})
    studio._review_dialog.reject()
    app.processEvents()
    require(digest(studio.project) == before, 'Canceling generation review changed the project.')
    return {'form_cancel': True, 'review_cancel': True, 'selection_not_persisted': True}


def lifecycle_case(app, studio, tech, model, angle, folder, execution, screenshots=False):
    from icstudio.ihp_layout import audit
    folder.mkdir(parents=True, exist_ok=False)
    device = placement(app, studio, tech, model, 2, 7, f'guard_{model}_r{angle}_{execution[:12]}')
    require('physical_guard_routing' not in device, 'New device must default to the legacy recipe.')
    controls = interruption_controls(app, studio, folder/'generation-form.png' if screenshots else None)
    before = content(studio)
    generate(app, studio, CORNER)
    undo_redo(app, studio, before, content(studio))
    if angle:
        studio.select([shape['id'] for shape in studio.cell['shapes']], 'layout')
        submit_form(app, studio.transform_layout_dialog(), {'rotation': angle, 'annotations': 'Yes'})
    check_state(studio, angle=angle)

    altered = clone(studio.project)
    next(c for c in altered['cells'] if c['id'] == studio.cid)['devices'][0].pop('physical_guard_routing')
    require(any(row['code'] == 'PDK.STALE' for row in audit(altered, studio.cid)),
            'Removing only the guard option did not mark the footprint stale.')

    # Regeneration preserves geometry and orientation without a second footprint.
    geometry_before = {key: clone(studio.cell[key]) for key in ('shapes', 'layout_pins')}
    generate(app, studio, CORNER, previous=CORNER, capture=folder if screenshots else None)
    require(all(studio.cell[key] == value for key, value in geometry_before.items()),
            'Unchanged regeneration moved geometry or terminals.')
    check_state(studio, angle=angle)

    transitions = []
    for iteration in range(2):
        for target, previous in ((NATIVE, CORNER), (CORNER, NATIVE)):
            before = content(studio)
            generate(app, studio, target, previous=previous)
            after = content(studio)
            undo_redo(app, studio, before, after)
            check_state(studio, corner=target == CORNER, angle=angle)
            transitions.append({'iteration': iteration, 'guard_routing': target, 'undo_redo': True})

    # The schematic inspector accepts a legacy size, but the opt-in corner
    # footprint must become stale and reject regeneration at that size.
    select_device(studio)
    studio.form_fields['modelparam:w'].setText('7u')
    studio.form_fields['modelparam:l'].setText('2u')
    require(studio.apply_inspector(True), 'Could not edit schematic dimensions for the stale control.')
    require(any(row['code'] == 'PDK.STALE' for row in audit(studio.project, studio.cid)),
            'Changed dimensions did not mark the corner footprint stale.')
    blocked = blocked_review(app, studio, previous=CORNER, folder=folder/'invalid-regeneration')
    studio.undo()
    app.processEvents()
    check_state(studio, angle=angle)

    # A valid candidate must not apply over a newer schematic edit.
    form = form_for(studio, CORNER)
    submit_form(app, form, {'guard_routing': NATIVE, 'terminal_access': 'Metal1'})
    select_device(studio)
    studio.form_fields['Name'].setText('R1_newer')
    require(studio.apply_inspector(True), 'Could not create an intervening inspector edit.')
    changed = digest(studio.project)
    from PySide6.QtWidgets import QDialogButtonBox
    review = studio._review_dialog
    review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click()
    app.processEvents()
    require(review.isVisible() and digest(studio.project) == changed,
            'Stale preview applied over the newer project.')
    require(any('Project changed' in text for text in review_labels(review)),
            'Stale preview rejection explanation missing.')
    review.reject()
    studio.undo()
    app.processEvents()
    check_state(studio, angle=angle)

    # Save through real file actions, reopen, then check the restored controls.
    saved = save_reopen(app, studio, folder/'saved')
    check_state(studio, angle=angle)
    form = form_for(studio, CORNER)
    form.reject()
    for pin in list(studio.cell['layout_pins']):
        submit_form(app, studio.cell_port_dialog(), {'name': {'p': 'R1', 'm': 'R2', 'body': 'B'}[pin['pin']],
                    'layer': pin['layer'], 'x': pin['point'][0]/1000, 'y': pin['point'][1]/1000})
    exported = save_reopen(app, studio, folder/'with-ports')
    for extension in ('gds', 'oas'):
        with selected_file('getSaveFileName', folder/('layout.'+extension)):
            studio.export_gds()
        require((folder/('layout.'+extension)).is_file(), 'Application layout export missing.')
    if screenshots:
        from PySide6.QtTest import QTest
        # Reopening restores window state. Leave maximized offscreen geometry
        # before capture so the inspector does not squeeze the layout canvas.
        studio.showNormal()
        studio.resize(1440, 960)
        studio.mode_combo.setCurrentIndex(1)
        QTest.qWait(30)
        studio.layout.fit()
        app.processEvents()
        require(studio.grab().save(str(folder/'layout.png')), 'Could not capture the source layout.')
    return {'case': f'{model}-r{angle}', 'model': model, 'width_um': 2, 'length_um': 7,
            'rotation': angle, 'terminal_access': 'Metal1', 'guard_routing': OPTION,
            'saved': saved, 'with_ports': exported, 'generation': clone(studio.cell['pdk_layouts']),
            'layout_pins': clone(studio.cell['layout_pins']), 'layout_ports': clone(studio.cell['layout_ports']),
            'generation_undo_redo': True, 'same_option_regeneration': True, 'switches': transitions,
            'guard_option_stale': True, 'dimensions_stale': True, 'invalid_regeneration': blocked,
            'stale_preview_rejected': True, 'interruption_controls': controls}


def unsupported_controls(app, studio, tech, execution, folder):
    rows = []
    for model in MODELS:
        for index, (width, length) in enumerate(((7, 2), (.5, .5), (1, 7), (2, 7.000001))):
            # The shared placement helper uses six-significant-digit display
            # formatting; set the sub-nanometre negative control explicitly.
            placement(app, studio, tech, model, width, 7 if index == 3 else length,
                      f'guard_invalid_{model}_{index}_{execution[:12]}')
            if index == 3:
                studio.form_fields['modelparam:l'].setText('7.000001u')
                require(studio.apply_inspector(True), 'Could not enter the exact off-grid schematic dimension.')
            result = blocked_review(app, studio, folder=folder/f'{model}-invalid-size-{index}')
            require(not studio.cell.get('pdk_layouts'), 'Invalid size produced a footprint.')
            rows.append({'kind': 'invalid-size', 'case': f'{model}-invalid-size-{index}',
                         'model': model, 'width_um': width, 'length_um': length, **result})
        placement(app, studio, tech, model, 2, 7, f'guard_m2_{model}_{execution[:12]}')
        result = blocked_review(app, studio, access='Metal2', explanation=('Metal1', 'terminal', 'via'),
                                folder=folder/f'{model}-corner-metal2')
        rows.append({'kind': 'unsupported-corner-metal2', 'case': f'{model}-corner-metal2',
                     'model': model, 'unsupported_corner_terminal_access': 'Metal2', **result})
        # The old Metal2 terminal option still works when the guard stays native.
        generate(app, studio, NATIVE, access='Metal2')
        check_state(studio, corner=False, access='Metal2')
        saved = save_reopen(app, studio, folder/model)
        form = form_for(studio, NATIVE, 'Metal2')
        form.reject()
        rows.append({'kind': 'legacy-metal2-preserved', 'case': f'{model}-legacy-metal2',
                     'model': model, 'legacy_metal2_access_preserved': True, 'saved': saved})
    return rows


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--execution-id', required=True)
    parser.add_argument('--managed', action='store_true', help='Capture the shipped managed runtime before and after GUI work.')
    parser.add_argument('--screenshots', action='store_true', help='Capture Qt images; visual inspection is separate.')
    args = parser.parse_args(arguments)
    import re
    require(re.fullmatch('[0-9a-f]{32}', args.execution_id), 'Use a unique 32-character lowercase hex execution ID.')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    from .build_identity import identity
    from .bundled_pdks import bundle_root
    from .ihp_resistors import MANIFEST_SEMANTIC_HASH, SOURCE_HASHES, TEMPLATE_HASH as LEGACY_TEMPLATE_HASH
    from .ihp_guard_routing import CIFOUT_HASH, TEMPLATE_HASH
    frozen = bool(getattr(sys, 'frozen', False))
    resources = bundle_root().parents[2]
    package = bundle_root()/'ihp-sg13g2'
    template = Path(__file__).parent/'assets/qualification/ihp-guard-corner-safe/templates.json'
    executable = Path(sys.executable).resolve()
    result = {'schema': 1, 'status': 'failed', 'mode': 'guard-corner-safe-lifecycle',
              'scope': 'bounded Qt GUI lifecycle producer; independent verifier owns installed acceptance',
              'execution_id': args.execution_id, 'execution_root': str(out),
              'build': identity(), 'frozen': frozen, 'resource_root': str(resources),
              'template_path': str(template), 'executable': str(executable),
              'executable_sha256': file_digest(executable),
              'package_manifest_sha256': PACKAGE, 'package_manifest_semantic_sha256': MANIFEST_SEMANTIC_HASH,
              'template_sha256': TEMPLATE_HASH, 'legacy_template_sha256': LEGACY_TEMPLATE_HASH,
              'source_hashes': clone(SOURCE_HASHES), 'guard_cifout_sha256': CIFOUT_HASH,
              'installed_acceptance': False, 'native_execution': False, 'qualified': False,
              'full_family': False, 'release_ready': False, 'screenshots_inspected': False,
              'lifecycle': [], 'controls': [], 'legacy': []}
    app = studio = None
    before = None
    errors = []
    old_excepthook = sys.excepthook
    try:
        if frozen:
            require(args.managed, 'Frozen guard lifecycle requires managed runtime capture.')
            require(result['build'].get('frozen') is True and result['build'].get('dirty') is False
                    and re.fullmatch('[0-9a-f]{40}', result['build'].get('commit', '')),
                    'Frozen guard lifecycle requires an exact clean build identity.')
        else:
            before = source_inventory()
            write(out/'source-before.json', before)
            result['source_root'] = str(ROOT)
            result['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
            result['source_dirty'] = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True))
        require(file_digest(package/'package.json') == PACKAGE, 'Changed bundled IHP package.')
        collection = bundle_root()/'collection.json'
        result['bundle_collection_sha256'] = file_digest(collection)
        shutil.copyfile(package/'package.json', out/'bundled-package.json')
        shutil.copyfile(collection, out/'bundled-collection.json')
        require(file_digest(template) == TEMPLATE_HASH, 'Changed corner-safe guard templates.')
        shutil.copyfile(template, out/'templates.json')
        legacy_template = Path(__file__).parent/'assets/qualification/ihp-resistor-templates/templates.json'
        require(file_digest(legacy_template) == LEGACY_TEMPLATE_HASH, 'Changed legacy resistor templates.')
        shutil.copyfile(legacy_template, out/'legacy-templates.json')
        for key in ('XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'APPDATA', 'LOCALAPPDATA'):
            os.environ[key] = str(out/'profile'/key)
        from PySide6.QtCore import QSettings, QStandardPaths
        from PySide6.QtWidgets import QApplication
        from .gui import Studio
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(out/'profile/settings'))
        QStandardPaths.writableLocation = staticmethod(lambda kind: str(out/'profile'/str(kind.value)))
        def exception(kind, value, tb):
            errors.append(''.join(traceback.format_exception(kind, value, tb)))
        sys.excepthook = exception
        app = QApplication.instance() or QApplication([])
        app.setStyle('Fusion')
        studio = Studio(recover=False)
        studio.error = lambda error: errors.append(str(error))
        studio.maybe_save = lambda: True
        studio.live_check.setChecked(False)
        studio.resize(1400, 960)
        studio.show()
        key = studio.pdk_registry.install(package/'package.json')
        tech = studio.pdk_registry.technology(key)
        result['registry_key'] = key
        registry_manifest = Path(tech['package_root'])/'package.json'
        result['registry_manifest_sha256'] = file_digest(registry_manifest)
        shutil.copyfile(registry_manifest, out/'registry-package.json')
        result['source_actual_hashes'] = {name: file_digest(Path(tech['package_root'])/'libs.tech/magic'/name)
                                          for name in SOURCE_HASHES}
        require(result['source_actual_hashes'] == SOURCE_HASHES, 'Changed reviewed resistor source files.')
        result['guard_source_actual_sha256'] = file_digest(Path(tech['package_root'])/'libs.tech/magic/ihp-sg13g2-cifout.tech')
        require(result['guard_source_actual_sha256'] == CIFOUT_HASH, 'Changed reviewed guard cut-array source.')
        if args.managed:
            result['managed_runtime_before'] = capture_runtime(out/'runtime/before', resources, frozen)
        result['legacy'] = legacy(app, studio, out/'legacy')
        for row in result['legacy']:
            saved = load_project(row['saved'])
            require(all('physical_guard_routing' not in device for cell in saved['cells'] for device in cell['devices']),
                    'Opening/saving a legacy project introduced the guard option.')
        result['controls'] = unsupported_controls(app, studio, tech, args.execution_id, out/'controls')
        for model, angle in CASES:
            result['lifecycle'].append(lifecycle_case(app, studio, tech, model, angle,
                out/f'{model}-r{angle}', args.execution_id, screenshots=args.screenshots))
        require(len(result['lifecycle']) == len(CASES) and len(result['controls']) == 18,
                'Incomplete six-case/eighteen-control GUI matrix.')
        if args.managed:
            result['managed_runtime_after'] = capture_runtime(out/'runtime/after', resources, frozen)
            require(result['managed_runtime_before'] == result['managed_runtime_after'],
                    'Included managed runtime identity changed.')
        studio.pdk_registry.verify(key)
        require(file_digest(package/'package.json') == PACKAGE and file_digest(collection) == result['bundle_collection_sha256']
                and file_digest(template) == TEMPLATE_HASH and file_digest(legacy_template) == LEGACY_TEMPLATE_HASH,
                'Bundled package, collection or template changed.')
        require(not errors, 'Application errors: '+str(errors))
        result['status'] = 'passed'
    except Exception:
        result['error'] = traceback.format_exc()
    finally:
        if studio is not None:
            if studio.run_manager.busy:
                studio.run_manager.cancel(studio.run_manager.rows)
            studio.saved_hash = digest(studio.project)
            studio.settings.sync()
            studio.close()
            app.processEvents()
        sys.excepthook = old_excepthook
        result['errors'] = errors
        result['elapsed_seconds'] = time.monotonic()-started
        try:
            if not frozen:
                after = source_inventory()
                write(out/'source-after.json', after)
                require(after == before, 'Probe inputs changed during this source GUI run.')
                result['source_unchanged'] = True
                result['source_commit_after'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
                require(result['source_commit_after'] == result['source_commit'], 'Source commit changed during GUI execution.')
            require(file_digest(executable) == result['executable_sha256'], 'Producer executable changed during execution.')
            require(not errors, 'Application errors: '+str(errors))
            paths = list(out.rglob('*'))
            require(not any(path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()) for path in paths),
                    'Producer evidence contains a linked file or directory.')
        except Exception:
            result.update(status='failed', identity_error=traceback.format_exc())
        files = {path.relative_to(out).as_posix(): file_digest(path) for path in sorted(out.rglob('*'))
                 if path.is_file() and path not in (out/'report.json', out/'files.json')}
        write(out/'files.json', files)
        result['files_sha256'] = file_digest(out/'files.json')
        write(out/'report.json', result)
    print(json.dumps({'status': result['status'], 'report': str(out/'report.json'),
                      'cases': len(result['lifecycle']), 'error': result.get('error'),
                      'identity_error': result.get('identity_error')}), flush=True)
    return int(result['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
