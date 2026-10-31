"""Selected resistor Qt lifecycle and fresh queued native physical evidence.

The source form is a development probe. A frozen run must use the included
physical runtime; an external checker still establishes installed provenance.
LI electrical behavior and the M1--M4 electrical suite are separate gates.
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

from .model import clone, digest, design_digest, example, file_digest
from .mim_desktop_probe import (
    OLD_MANIFEST, STAGES, capture_runtime, generate, historical_package,
    queue_layout, require, save_reopen, selected_file, submit_form,
    verified_package, write,
)

MODELS = ('l1', 'm1', 'm2', 'm3', 'm4')
SIZES = ((.5, .5), (2, 5), (5, 2))
CASES = tuple((model, geometry, angle) for model in MODELS
              for geometry in range(len(SIZES)) for angle in (0, 90))


def place_edit(app, studio, technology, model, width=2, length=5, count=1,
               top='resistor_coupon'):
    from PySide6.QtCore import Qt
    from .catalog import binding_for, parameter_values
    project = example('empty')
    project['pdk'] = clone(technology)
    project['cells'][0].update(name=top, ports=['R1', 'R2'])
    studio.set_project(project)
    symbol = 'li' if model == 'l1' else model
    key = 'sky130_fd_pr/res_generic_'+symbol+'.sym'
    item = next((studio.library_list.item(i) for i in range(studio.library_list.count())
                 if studio.library_list.item(i).data(Qt.UserRole) == key), None)
    require(item is not None and not item.data(Qt.UserRole+3), 'Required resistor is unavailable.')
    studio.library_list.setCurrentItem(item)
    studio.place_library_button.click()
    require(studio.schematic.placement is not None, 'Library placement did not start.')
    studio.place_device_at(300, 250)
    studio.cancel_tool()
    require(len(studio.cell['devices']) == 1, 'Expected one placed resistor.')
    device = studio.cell['devices'][0]
    studio.select([device['id']], 'schematic')
    for name, value in {'Name': 'R1', 'net:m': 'R1', 'net:p': 'R2',
                        'modelparam:w': width, 'modelparam:l': length,
                        'modelparam:mult': count}.items():
        studio.form_fields[name].setText(str(value))
    require(studio.apply_inspector(True), 'Inspector could not apply resistor parameters.')
    app.processEvents()
    device = studio.cell['devices'][0]
    binding = binding_for(studio.project['pdk'], device)
    values = parameter_values(binding, device)
    require(binding['model'] == 'sky130_fd_pr__res_generic_'+model
            and binding['pin_order'] == ['m', 'p'] and device['nets'] == {'m': 'R1', 'p': 'R2'}
            and binding['emit_parameters'] == dict(w='w', l='l', m='mult')
            and binding['parameter_scale'] == dict(w=1e6, l=1e6)
            and values == dict(w=width, l=length, mult=count), 'Resistor binding or parameters differ.')
    return dict(model=binding['model'], values=values, model_ref=clone(device['model_ref']),
                emit_parameters=clone(binding['emit_parameters']), terminals=['R1', 'R2'])


def generate_with_late_lock(app, studio, model):
    from PySide6.QtWidgets import QDialogButtonBox
    from .sky130_metal_resistors import layers
    before = clone(studio.project)
    form = studio.mos_layout_dialog()
    if form is not None:
        submit_form(app, form)
    require(studio.project == before, 'Preview changed the design before application.')
    review = studio._review_dialog
    button = review.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
    layer = layers(studio.project['pdk'], model)['conductor']
    studio.layout.locked_layers.add(layer)
    try:
        button.click()
        app.processEvents()
        require(review.isVisible() and studio.project == before, 'Late layer lock failed to block generation.')
    finally:
        studio.layout.locked_layers.discard(layer)
    button.click()
    app.processEvents()
    require(not review.isVisible() and studio.cell.get('pdk_layouts'), 'Unlocked generation did not apply.')
    return dict(layer=layer, before_design_hash=design_digest(before),
                blocked_design_hash=design_digest(before), rejected=True)


def layout_case(app, studio, technology, model, geometry, angle, folder):
    from .catalog import binding_for, parameter_values
    from .physical import connectivity
    width, length = SIZES[geometry]
    case = f'{model}-g{geometry}-r{angle}'
    top = f'metal_{model}_g{geometry}_r{angle}_{studio.probe_execution_id[:12]}'
    initial = (5, 2) if (width, length) == (2, 5) else (2, 5)
    place_edit(app, studio, technology, model, *initial, top=top)
    late_lock = generate_with_late_lock(app, studio, model) if (geometry, angle) == (1, 0) else None
    if late_lock is None:
        generate(app, studio)
    initial_shapes = clone(studio.cell['shapes'])
    initial_pins = {pin['pin']: pin['id'] for pin in studio.cell['layout_pins']}
    studio.undo()
    require(not studio.cell.get('pdk_layouts'), 'Undo did not remove the generated resistor.')
    studio.redo()
    require(studio.cell['shapes'] == initial_shapes, 'Redo did not restore the exact generated resistor.')
    device = studio.cell['devices'][0]
    studio.select([device['id']], 'schematic')
    for key, value in (('w', width), ('l', length)):
        studio.form_fields['modelparam:'+key].setText(str(value))
    require(studio.apply_inspector(True), 'Inspector rejected the selected resize.')
    generate(app, studio)
    require(initial_pins == {pin['pin']: pin['id'] for pin in studio.cell['layout_pins']},
            'Resizing lost stable terminal identities.')
    require(not connectivity(studio.project, studio.cid)['issues'], 'Generated resistor connectivity failed.')
    binding = binding_for(studio.project['pdk'], studio.cell['devices'][0])
    values = parameter_values(binding, studio.cell['devices'][0])
    require(values == dict(w=width, l=length, mult=1), 'Resized parameters differ.')
    for pin in list(studio.cell['layout_pins']):
        submit_form(app, studio.cell_port_dialog(),
                    dict(name='R1' if pin['pin'] == 'm' else 'R2', layer=pin['layer'],
                         x=pin['point'][0]/1000, y=pin['point'][1]/1000))
    if angle:
        studio.select([shape['id'] for shape in studio.cell['shapes']], 'layout')
        submit_form(app, studio.transform_layout_dialog(), dict(rotation=angle, annotations='Yes'))
    row = save_reopen(app, studio, folder)
    with selected_file('getSaveFileName', folder/'layout.gds'):
        studio.export_gds()
    row.update(case=case, execution_id=studio.probe_execution_id, top=top,
               model=model, geometry_index=geometry, width_um=width, length_um=length,
               rotation=angle, multiplicity=1, terminals=['R1', 'R2'], execution_root=str(folder.parent),
               binding=dict(model=binding['model'], values=values,
                            model_ref=clone(studio.cell['devices'][0]['model_ref']),
                            emit_parameters=clone(binding['emit_parameters']), terminals=['R1', 'R2']),
               schematic_sha256=file_digest(folder/'schematic.spice'),
               reference_sha256=file_digest(folder/'reference.spice'),
               gds=str(folder/'layout.gds'), gds_sha256=file_digest(folder/'layout.gds'),
               generation=clone(studio.cell['pdk_layouts']),
               editor_checks=dict(initial_geometry_um=list(initial), undo_redo=True,
                                  initial_shape_hash=digest(initial_shapes), initial_pin_ids=initial_pins,
                                  resized_pin_ids={pin['pin']: pin['id'] for pin in studio.cell['layout_pins']},
                                  late_layer_lock=late_lock))
    return row


def content(project):
    return {key: value for key, value in project.items() if key not in ('revision', 'modified')}


def queue_case(app, studio, item, case, *, missing=False):
    row = queue_layout(app, studio, item['reference'], case, missing=missing)
    row.update(model=item['model'], geometry_index=item['geometry_index'], width_um=item['width_um'],
               length_um=item['length_um'], rotation=item['rotation'], multiplicity=1,
               terminals=['R1', 'R2'], execution_root=item['execution_root'], source_case=item['case'],
               reference=item['reference'], reference_sha256=file_digest(item['reference']),
               project_revision=studio.project['revision'])
    return row


def widened_vertices(points, left, width):
    """Change only the right edge of a rectangular selected resistor mask."""
    right = left+width
    require(width == 2000 and len(points) in (2, 4)
            and {point[0] for point in points} == {left, right}
            and len({point[1] for point in points}) == 2,
            'Width control requires the selected two-micrometre rectangle.')
    return [[x+400 if x == right else x, y] for x, y in points]


def edit_width(app, studio, shape, left, width):
    before = clone(shape['points'])
    after = widened_vertices(before, left, width)
    studio.select([shape['id']], 'layout')
    if shape['kind'] == 'rect':
        studio.form_fields['Width'].setText(f'{(width+400)/1000:g}')
    else:
        require(shape['kind'] == 'polygon' and studio.vertex_table.rowCount() == len(after),
                'Width control requires the actual polygon vertex editor.')
        for index, point in enumerate(after):
            for axis, value in enumerate(point):
                studio.vertex_table.item(index, axis).setText(f'{value/1000:g}')
    require(studio.apply_inspector(False), 'The shape inspector rejected the width control.')
    app.processEvents()
    actual = next(row for row in studio.cell['shapes'] if row['id'] == shape['id'])
    require(actual['points'] == after, 'The real shape inspector did not apply the exact width control.')
    return dict(shape=shape['id'], layer=shape['layer'], before_points=before, after_points=after)


def width_cycle(app, studio, item, clean):
    from .layout import polygon
    from .sky130_metal_resistors import layers
    baseline = clone(content(studio.project))
    baseline_hash = design_digest(studio.project)
    selected = layers(studio.project['pdk'], item['model'])
    shapes = [shape for shape in studio.cell['shapes'] if shape['layer'] in selected.values()]
    require(len(shapes) == 2 and {shape['layer'] for shape in shapes} == set(selected.values()),
            'Width control requires exactly conductor and resistor-marker shapes.')
    marker = next(shape for shape in shapes if shape['layer'] == selected['marker'])
    box = polygon(marker).bbox()
    edits = []
    for shape in shapes:
        edits.append(edit_width(app, studio, shape, box.left, box.width()))
    studio.refresh_silicon()
    require('STALE' in studio.silicon_status.text(), 'Width edit did not invalidate passing evidence.')
    faulty = queue_case(app, studio, item, item['model']+'-width-fault')
    stages = {stage['name']: stage for stage in faulty['report']['stages']}
    require(faulty['report']['status'] == 'failed' and faulty['report']['drc_count'] == 0
            and stages['drc']['status'] == stages['lvs_extraction']['status'] == 'passed'
            and stages['lvs']['status'] == 'failed', 'Actual width mismatch did not fail native LVS.')
    for _ in edits:
        studio.undo()
    require(content(studio.project) == baseline and design_digest(studio.project) != baseline_hash,
            'Undo must restore the exact content with a new design revision.')
    repaired = queue_case(app, studio, item, item['model']+'-width-repaired')
    require(repaired['report']['status'] == 'passed', 'Fresh width repair did not pass native checks.')
    require(len({clean['job_id'], faulty['job_id'], repaired['job_id']}) == 3, 'Width control reused a job.')
    return dict(kind='width-cycle', source_case=item['case'], model=item['model'],
                baseline_design_hash=baseline_hash, before_content_hash=digest(baseline),
                after_design_hash=faulty['design_hash'], repaired_content_hash=digest(content(studio.project)),
                displayed=True, edits=edits, fault=faulty, repair=repaired)


def drc_cycle(app, studio, item):
    from .layout import rect
    baseline = clone(content(studio.project))
    baseline_hash = design_digest(studio.project)
    layer = next(row['name'] for row in studio.project['pdk']['layers']
                 if (row['gds'], row['datatype']) == (68, 20))
    shape = rect(layer, 100000, 100000, 100, 100)
    studio.add_shape(shape)
    studio.refresh_silicon()
    require('STALE' in studio.silicon_status.text(), 'Narrow-metal edit did not invalidate passing evidence.')
    faulty = queue_case(app, studio, item, 'narrow-metal')
    stages = {stage['name']: stage for stage in faulty['report']['stages']}
    require(faulty['report']['status'] == 'failed' and stages['drc']['status'] == 'failed'
            and faulty['report'].get('drc_count', 0) > 0, 'Narrow-metal control did not fail actual DRC.')
    studio.undo()
    require(content(studio.project) == baseline and design_digest(studio.project) != baseline_hash,
            'Narrow-metal undo did not restore content with a new revision.')
    repaired = queue_case(app, studio, item, 'narrow-metal-repaired')
    require(repaired['report']['status'] == 'passed', 'Fresh narrow-metal repair did not pass.')
    return dict(kind='narrow-metal-cycle', source_case=item['case'],
                baseline_design_hash=baseline_hash, before_content_hash=digest(baseline),
                after_design_hash=faulty['design_hash'], repaired_content_hash=digest(content(studio.project)),
                displayed=True, added_shape=shape, fault=faulty, repair=repaired)


def physical_cases(app, studio, lifecycle, technology, arguments, evidence):
    from .catalog import link_technology
    from .layout_import import read_layout
    from .physical_cells import assign_port, ports
    results, controls = evidence['physical'], evidence['controls']
    for item in lifecycle:
        project, _ = read_layout(Path(item['gds']))
        link_technology(project, technology)
        project['cells'][0]['ports'] = ['R1', 'R2']
        labels = ports(project, project['top'])
        require(len(labels) == 2 and {row['name'] for row in labels} == {'R1', 'R2'},
                'Exported GDS must supply both actual terminal labels.')
        for label in labels:
            assign_port(project, project['top'], label['name'], label['layer'], label['point'])
        studio.set_project(project)
        row = queue_case(app, studio, item, item['case'])
        require(row['report']['status'] == 'passed'
                and tuple(stage['name'] for stage in row['report']['stages']) == STAGES
                and all(stage['status'] == 'passed' for stage in row['report']['stages']),
                'Current resistor did not pass all six native stages.')
        if arguments.managed:
            execution = row['report'].get('execution', {})
            require(execution.get('runtime', {}).get('kind') == ('wsl' if os.name == 'nt' else 'linux')
                    and execution.get('received_files'), 'Included physical runtime provenance is missing.')
        native = Path(row['evidence_directory'])/'lvs-extraction/extracted.spice'
        item['native'] = str(native)
        item['native_sha256'] = file_digest(native)
        item['native_job_id'] = row['job_id']
        item['native_design_hash'] = row['design_hash']
        results.append(row)
        if (item['geometry_index'], item['rotation']) == (1, 0):
            controls.append(width_cycle(app, studio, item, row))
        if item is not lifecycle[-1]:
            continue
        controls.append(drc_cycle(app, studio, item))
        old_mode = studio.settings.value('physical/toolchain', 'auto')
        old_magic = studio.settings.value('engine/magic', '')
        studio.settings.setValue('physical/toolchain', 'custom')
        studio.settings.setValue('engine/magic', str(arguments.out/'missing-magic-executable'))
        try:
            blocked = queue_case(app, studio, item, 'missing-engine', missing=True)
        finally:
            studio.settings.setValue('physical/toolchain', old_mode)
            studio.settings.setValue('engine/magic', old_magic)
        require(blocked['report']['status'] == 'blocked' and 'BLOCKED' in studio.silicon_status.text(),
                'Missing selected engine was not visibly blocked.')
        controls.append(dict(kind='missing-engine', source_case=item['case'], job=blocked))
    return results, controls


def main(arguments=None):
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--execution-id', required=True)
    parser.add_argument('--mode', choices=('lifecycle', 'physical'), default='physical')
    parser.add_argument('--physical-pdk', type=Path)
    parser.add_argument('--managed', action='store_true')
    for name in ('magic', 'netgen'):
        parser.add_argument('--'+name, default='')
    arguments = parser.parse_args(arguments)
    require(re.fullmatch('[0-9a-f]{32}', arguments.execution_id), 'Invalid execution identity.')
    arguments.out = arguments.out.resolve()
    arguments.out.mkdir(parents=True, exist_ok=False)
    from .build_identity import identity
    from .bundled_pdks import bundle_root
    resources = bundle_root().parents[2]
    result = dict(schema=1, status='failed', mode=arguments.mode, execution_id=arguments.execution_id,
                  build=identity(), frozen=bool(getattr(sys, 'frozen', False)), execution_root=str(arguments.out),
                  executable=str(Path(sys.executable).resolve()), executable_sha256=file_digest(sys.executable),
                  resource_root=str(resources), qualified=False, release_ready=False,
                  installed_acceptance=False, full_family=False, native_execution=False,
                  lifecycle=[], binding_lifecycle=[], physical=[], controls=[],
                  scope='Selected five-model Qt lifecycle and optional 30 fresh queued Magic DRC/Netgen LVS inputs. '
                        'Frozen status alone does not prove installation. M1-M4 electrical qualification uses 24 inputs '
                        'in a separate gate; LI electrical, public KLayout, full operating envelopes and signoff are excluded.')
    app = studio = None
    errors = []
    try:
        if result['frozen'] and arguments.mode == 'physical':
            require(arguments.managed and not arguments.magic and not arguments.netgen,
                    'Frozen physical probe requires included engines.')
        from PySide6.QtCore import QSettings, QStandardPaths
        from PySide6.QtWidgets import QApplication
        from .gui import Studio
        from . import digital_runtime
        if arguments.managed:
            os.environ.setdefault('ICSTUDIO_DIGITAL_STATE', str(digital_runtime.state_root()))
        os.environ['XDG_DATA_HOME'] = str(arguments.out/'profile/data')
        os.environ['XDG_CONFIG_HOME'] = str(arguments.out/'profile/config')
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(arguments.out/'profile/settings'))
        QStandardPaths.writableLocation = staticmethod(lambda kind: str(arguments.out/'profile'/str(kind.value)))
        app = QApplication([])
        app.setStyle('Fusion')
        studio = Studio(recover=False)
        studio.probe_execution_id = arguments.execution_id
        studio.error = lambda error: errors.append(str(error))
        studio.maybe_save = lambda: True
        studio.jobs_dir = arguments.out/'runs with spaces'
        studio.live_check.setChecked(False)
        studio.resize(1400, 960)
        studio.show()
        root = bundle_root()/'sky130A'
        collection = bundle_root()/'collection.json'
        entry = next(row for row in json.loads(collection.read_bytes())['packages'] if row['variant'] == 'sky130A')
        package = verified_package(root, entry['manifest_sha256'])
        historical = historical_package(root, resources, arguments.out/'historical-package')
        registry = studio.pdk_registry
        old_key = registry.install(historical/'package.json')
        old_rows = {}
        for model in MODELS:
            binding = place_edit(app, studio, registry.technology(old_key), model, count=3,
                                 top=f'metal_old_{model}_{arguments.execution_id[:12]}')
            row = save_reopen(app, studio, arguments.out/'bindings'/model/'old')
            old_rows[model] = dict(kind='historical-before', model=model, binding=binding, **row)
            result['binding_lifecycle'].append(old_rows[model])
        current_key = registry.install(root/'package.json')
        require(current_key != old_key, 'Current and historical revisions unexpectedly coincide.')
        for model in MODELS:
            old = old_rows[model]
            with selected_file('getOpenFileName', old['project']):
                studio.open_project()
            reopened = save_reopen(app, studio, arguments.out/'bindings'/model/'old-after-install')
            require(reopened['package_lock'] == old['package_lock']
                    and studio.cell['devices'][0]['model_ref'] == old['binding']['model_ref']
                    and Path(reopened['reference']).read_bytes() == Path(old['reference']).read_bytes(),
                    'Installing the current package changed a saved resistor binding.')
            result['binding_lifecycle'].append(dict(kind='historical-after-current-install', model=model,
                                                   binding=old['binding'], **reopened))
            binding = place_edit(app, studio, registry.technology(current_key), model, count=3,
                                 top=f'metal_current_{model}_{arguments.execution_id[:12]}')
            current_row = save_reopen(app, studio, arguments.out/'bindings'/model/'current')
            result['binding_lifecycle'].append(dict(kind='current', model=model, binding=binding, **current_row))
        order = ('historical-before', 'historical-after-current-install', 'current')
        result['binding_lifecycle'].sort(key=lambda row: (MODELS.index(row['model']), order.index(row['kind'])))
        registry_manifests = {key: file_digest(registry.root/key/'package.json') for key in (old_key, current_key)}
        current = registry.technology(current_key)
        for model, geometry, angle in CASES:
            case = f'{model}-g{geometry}-r{angle}'
            result['lifecycle'].append(layout_case(app, studio, current, model, geometry, angle, arguments.out/case))
        result['bundled_package'] = dict(path=str(root), manifest_sha256=file_digest(root/'package.json'),
            collection_sha256=file_digest(collection), revision=package['revision'], files=package['files'],
            current_key=current_key, historical_key=old_key, historical_original_manifest_sha256=OLD_MANIFEST)
        result['registry_manifests'] = registry_manifests
        shutil.copyfile(root/'package.json', arguments.out/'bundled-package.json')
        shutil.copyfile(collection, arguments.out/'bundled-collection.json')
        from .spice_program import find_ngspice
        selected = find_ngspice('')
        result['simulation_engine_discovery'] = dict(path=selected, sha256=file_digest(selected) if selected else None,
                                                     executed=False)
        if arguments.mode == 'physical':
            require(arguments.physical_pdk is not None, 'Physical mode requires the explicit locked physical adapter.')
            lock_path = resources/'examples/sky130-qualification-lock.json'
            lock = json.loads(lock_path.read_bytes())
            physical = verified_package(arguments.physical_pdk, lock['manifest_sha256'])
            tech = clone(physical['technology'])
            tech.update(package_root=str(arguments.physical_pdk.resolve()),
                        package_lock={key: physical[key] for key in ('id', 'revision', 'files')})
            result['physical_package'] = dict(path=str(arguments.physical_pdk.resolve()),
                manifest_sha256=file_digest(arguments.physical_pdk/'package.json'), release_lock_sha256=file_digest(lock_path),
                revision=physical['revision'], files=physical['files'])
            shutil.copyfile(arguments.physical_pdk/'package.json', arguments.out/'physical-package.json')
            shutil.copyfile(lock_path, arguments.out/'physical-release-lock.json')
            studio.settings.setValue('physical/toolchain', 'included' if arguments.managed else 'custom')
            for name in ('magic', 'netgen'):
                studio.settings.setValue('engine/'+name, str(arguments.out/('unselected-custom-'+name))
                                         if arguments.managed else getattr(arguments, name))
            if arguments.managed:
                result['managed_runtime_before'] = capture_runtime(arguments.out/'runtime/before', resources, result['frozen'])
            physical_cases(app, studio, result['lifecycle'], tech, arguments, result)
            result['native_execution'] = True
            verified_package(arguments.physical_pdk, lock['manifest_sha256'])
            if arguments.managed:
                result['managed_runtime_after'] = capture_runtime(arguments.out/'runtime/after', resources, result['frozen'])
                require(result['managed_runtime_after'] == result['managed_runtime_before'], 'Included runtime identity changed.')
        registry.verify(old_key)
        registry.verify(current_key)
        require(registry_manifests == {key: file_digest(registry.root/key/'package.json') for key in registry_manifests},
                'Installed registry manifests changed.')
        verified_package(root, entry['manifest_sha256'])
        require(file_digest(collection) == result['bundled_package']['collection_sha256'], 'Bundled collection changed.')
        require(file_digest(sys.executable) == result['executable_sha256'], 'Application executable changed.')
        result['input_guards'] = dict(bundled_package_unchanged=True, registry_assets_unchanged=True,
                                     executable_unchanged=True, physical_package_unchanged=arguments.mode == 'physical')
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
            paths = list(arguments.out.rglob('*'))
            require(not any(path.is_symlink() or path.is_junction() for path in paths),
                    'Probe evidence must not contain links or junctions.')
            files = {path.relative_to(arguments.out).as_posix(): file_digest(path) for path in sorted(paths)
                     if path.is_file() and path not in (arguments.out/'files.json', arguments.out/'report.json')}
            write(arguments.out/'files.json', files)
            result['files_sha256'] = file_digest(arguments.out/'files.json')
        except Exception:
            result.update(status='failed', inventory_error=traceback.format_exc())
        write(arguments.out/'report.json', result)
    print(json.dumps({key: result[key] for key in ('status', 'mode', 'execution_id', 'native_execution', 'elapsed_seconds')}
                     | {'report': str(arguments.out/'report.json'), 'error': result.get('error')}, indent=2))
    return int(result['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
