"""Independently verify the bounded installed LI/M1--M4 editor/native gate.

This gate covers thirty straight layouts and fault/repair behavior. Electrical
corners, public KLayout checks and whole-family qualification are separate.
"""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_frozen_mim import (
    require, sha, digest, load, relative, unlinked, confined, inventory, file_map,
    package, git_environment, git_blob, expected_inputs, backend_binding,
    design_hash, content_hash, registry_binding, check_runtime,
)

MODELS = ('l1', 'm1', 'm2', 'm3', 'm4')
SIZES = ((.5, .5), (2, 5), (5, 2))
CASES = tuple(f'{m}-g{g}-r{r}' for m in MODELS for g in range(3) for r in (0, 90))
STAGES = ('preflight', 'layout_export', 'drc', 'lvs_extraction', 'lvs', 'integrity')
OLD_MANIFEST = '42cafd2b1407783d361cfbb276abe3ba9e97b2c06a716af6c9069c8426852413'
SCOPE = ('Installed Qt LI/M1--M4 straight-resistor lifecycle, thirty fresh queued Magic DRC/Netgen LVS '
         'layouts and fault/repair/block controls only; no electrical90, public KLayout, whole-family or manufacturing qualification.')
EXTRACTION_SETTINGS = dict(hierarchy=True, blackbox=False, merge='none', scale=False,
    capacitance_threshold='infinite', resistance_threshold='infinite', distributed_resistance=False)


def checker_sources(commit):
    names = ('scripts/verify_frozen_metal_resistors.py', 'scripts/verify_frozen_mim.py', 'scripts/audit_sky130_li_case.py')
    expected = {name: hashlib.sha256(git_blob(commit, name)).hexdigest() for name in names}
    require(expected == {name: sha(ROOT/name) for name in names}, 'External checker differs from selected candidate.')
    return expected


def case_identity(name, execution_id):
    require(name in CASES and re.fullmatch('[0-9a-f]{32}', execution_id), 'Unknown case or execution identity.')
    model, geometry, rotation = name.split('-')
    geometry = int(geometry[1:]); rotation = int(rotation[1:])
    width, length = SIZES[geometry]
    return dict(case=name, model=model, geometry_index=geometry, width_um=width, length_um=length,
                rotation=rotation, multiplicity=1, execution_id=execution_id,
                top=f'metal_{model}_g{geometry}_r{rotation}_{execution_id[:12]}')


def circuit(text, top, model, width, length, *, count=1, extracted=False):
    """Literal primitive interface: app ordering is fixed; physical R is reciprocal."""
    require(model in MODELS, 'Unknown resistor model.')
    lines = [s.split() for s in re.sub(r'\n\s*\+\s*', ' ', text).splitlines()
             if s.strip() and not s.lstrip().startswith('*')]
    require(len(lines) == 3 and lines[0] == ['.subckt', top, 'R1', 'R2'] and
            lines[-1] in (['.ends'], ['.ends', top]), 'Resistor interface or element coverage differs.')
    row = lines[1]
    require(len(row) >= 6 and re.fullmatch(r'R\S+', row[0], re.I) and
            (set(row[1:3]) == {'R1', 'R2'} if extracted else row[1:3] == ['R1', 'R2']) and
            row[3] == 'sky130_fd_pr__res_generic_'+model, 'Resistor model or terminal mapping differs.')
    pairs = [token.split('=') for token in row[4:]]
    require(all(len(p) == 2 for p in pairs), 'Malformed resistor parameter.')
    values = {key.lower(): float(value) for key, value in pairs}
    expected = dict(w=width, l=length)
    if not extracted:
        expected['m'] = count
    require(len(values) == len(pairs) and all(math.isfinite(v) for v in values.values()) and
            values == expected, 'Resistor dimensions or multiplicity differ.')
    return dict(model=row[3], terminals=row[1:3], width_um=width, length_um=length, multiplicity=count)


def project_binding(project, model, width, length, count, lock, top):
    require(project['pdk']['package_lock'] == {**{k: lock[k] for k in ('id', 'revision', 'files')},
            'manifest_hash': digest(lock)}, 'Saved project package lock differs.')
    cells = project['cells']
    require(len(cells) == 1 and cells[0]['name'] == top and cells[0]['ports'] == ['R1', 'R2'] and
            project['top'] == cells[0]['id'] and len(cells[0]['devices']) == 1,
            'Saved resistor cell coverage differs.')
    cell = cells[0]; device = cell['devices'][0]
    key = 'sky130_fd_pr/res_generic_'+('li' if model == 'l1' else model)+'.sym'
    require(device['kind'] == 'PDK' and device['model_ref'] == dict(pdk='sky130A', revision=lock['revision'], device=key)
            and device['nets'] == dict(m='R1', p='R2'), 'Saved resistor model reference or terminals differ.')
    values = device['model_params']
    require(set(values) == {'w', 'l', 'mult'} and
            tuple(float(values[k]) for k in ('w', 'l', 'mult')) == (width, length, count),
            'Saved resistor parameters differ.')
    binding = project['pdk']['simulation']['catalog'][key]
    original = lock['technology']['simulation']['catalog'][key]
    for name in ('model', 'prefix', 'emit_parameters', 'parameter_scale', 'pin_order'):
        require(binding[name] == original[name], 'Saved model binding changed: '+name)
    require(binding['model'] == 'sky130_fd_pr__res_generic_'+model and binding['prefix'] == 'R' and
            binding['pin_order'] == ['m', 'p'] and binding['emit_parameters'] == dict(w='w', l='l', m='mult')
            and binding['parameter_scale'] == dict(w=1e6, l=1e6), 'Unexpected resistor model mapping.')
    return cell


def emitted_schematic(root, row, project):
    text = confined(root, row['schematic']).read_text(); reference = confined(root, row['reference']).read_text()
    devices = re.findall(r'(?mi)^R\S+.*$', text)
    require(len(devices) == 1 and devices == re.findall(r'(?mi)^R\S+.*$', reference) and
            not re.search(r'(?im)^\s*[xmcdqjblv]\S+\s', text), 'GUI SPICE export changed primitive coverage.')
    package_root = Path(project['pdk']['package_root']).resolve()
    includes = re.findall(r'(?mi)^\.(lib|include) "([^"]+)"(?: (\S+))?$', text)
    require(bool(includes), 'GUI export lost its model includes.')
    for kind, name, section in includes:
        path = confined(package_root, name); key = path.relative_to(package_root).as_posix()
        require(project['pdk']['package_lock']['files'].get(key) == sha(path) and
                ((kind.lower() == 'lib' and section == 'tt') or (kind.lower() == 'include' and not section)),
                'GUI export references an unbound model or corner.')


def lifecycle(root, report, current, historical):
    rows = report['lifecycle']
    require([r.get('case') for r in rows] == list(CASES), 'Missing, duplicated or reordered resistor layout cases.')
    for row in rows:
        item = case_identity(row['case'], report['execution_id'])
        require(all(row.get(k) == v for k, v in item.items()), 'Stale or substituted lifecycle case identity.')
        path = confined(root, row['project']); project = load(path)
        require(sha(path) == row['project_sha256'] and design_hash(project) == row['design_hash'], 'Saved lifecycle project differs.')
        cell = project_binding(project, item['model'], item['width_um'], item['length_um'], 1, current, item['top'])
        registry_binding(root, report, project, current)
        require(cell.get('pdk_layouts') == row['generation'] and bool(row['generation']), 'Missing linked footprint generation.')
        circuit(confined(root, row['reference']).read_text(), item['top'], item['model'], item['width_um'], item['length_um'])
        emitted_schematic(root, row, project)
        require(sha(confined(root, row['reference'])) == row['reference_sha256'] and
                sha(confined(root, row['schematic'])) == row['schematic_sha256'] and row['terminals'] == ['R1', 'R2'] and
                Path(row['execution_root']).resolve() == root, 'Lifecycle output or execution binding differs.')
        checks = row['editor_checks']; pins = {p['pin']: p['id'] for p in cell['layout_pins']}
        require(set(pins) == {'m', 'p'} and checks['initial_pin_ids'] == checks['resized_pin_ids'] == pins and
                checks['undo_redo'] is True and checks['initial_geometry_um'] ==
                ([5, 2] if (item['width_um'], item['length_um']) == (2, 5) else [2, 5]), 'Editor resize/undo identity differs.')
        if (item['geometry_index'], item['rotation']) == (1, 0):
            late = checks['late_layer_lock']
            require(late['rejected'] is True and late['before_design_hash'] == late['blocked_design_hash'] and
                    re.fullmatch('[0-9a-f]{64}', late['before_design_hash']), 'Late layer lock did not preserve design identity.')
        else: require(checks['late_layer_lock'] is None, 'Unexpected layer-lock control.')
        path = confined(root, row['gds']); require(sha(path) == row['gds_sha256'], 'Written lifecycle GDS differs.')
        target = stream(path, item['top']); resistor_geometry(target, item)
        project_geometry(project, target)
    bindings = report['binding_lifecycle']
    expected = [(model, kind) for model in MODELS for kind in
                ('historical-before', 'historical-after-current-install', 'current')]
    require([(r.get('model'), r.get('kind')) for r in bindings] == expected, 'Historical/current resistor coverage differs.')
    old_projects = {}
    for row in bindings:
        old = row['kind'] != 'current'; lock = historical if old else current
        path = confined(root, row['project']); project = load(path)
        require(sha(path) == row['project_sha256'] and design_hash(project) == row['design_hash'], 'Saved binding lifecycle differs.')
        top = f'metal_{"old" if old else "current"}_{row["model"]}_{report["execution_id"][:12]}'
        project_binding(project, row['model'], 2, 5, 3, lock, top)
        registry_binding(root, report, project, lock)
        circuit(confined(root, row['reference']).read_text(), top, row['model'], 2, 5, count=3)
        emitted_schematic(root, row, project)
        if row['kind'] == 'historical-before': old_projects[row['model']] = project
        elif row['kind'] == 'historical-after-current-install':
            require(project == old_projects[row['model']], 'Installing current models migrated a saved historical resistor.')


def stream(path, top):
    import klayout.db as db
    layout = db.Layout(); layout.read(str(path))
    require(layout.dbu == .001 and layout.cells() == 1 and layout.top_cell().name == top, 'GDS units, top or hierarchy differs.')
    cell = layout.top_cell(); masks = {}; labels = []
    for index in layout.layer_indexes():
        info = layout.get_info(index); pair = (info.layer, info.datatype); region = db.Region()
        for shape in cell.shapes(index).each():
            if shape.is_box(): region.insert(db.Polygon(shape.box))
            elif shape.is_polygon(): region.insert(shape.polygon.dup())
            elif shape.is_path(): region.insert(shape.path.polygon())
            elif shape.is_text(): labels.append((pair, shape.text.string, shape.text.x, shape.text.y))
            else: raise ValueError('Unsupported GDS primitive.')
        region.merge()
        if not region.is_empty(): masks[pair] = region
    return masks, sorted(labels)


def same_stream(left, right):
    require(set(left[0]) == set(right[0]) and left[1] == right[1] and
            all((left[0][k] ^ right[0][k]).is_empty() for k in left[0]), 'Written masks or terminal labels differ.')


def resistor_geometry(target, item, width_factor=1):
    import klayout.db as db
    masks, labels = target; layer = 67+MODELS.index(item['model'])
    require(set(masks) == {(layer, 20), (layer, 13)}, 'Unexpected resistor masks.')
    conductor, marker = masks[layer, 20], masks[layer, 13]; box = marker.bbox()
    dimensions = (round(item['width_um']*width_factor*1000), round(item['length_um']*1000))
    if item['rotation']: dimensions = dimensions[::-1]
    require(marker.count() == 1 and marker.area() == box.area() and (box.width(), box.height()) == dimensions,
            'Marker width, length, rectangularity or orientation differs.')
    require(conductor.count() == 1 and conductor.area() == conductor.bbox().area() and
            (marker-conductor).is_empty(), 'Interrupted or nonrectangular conductor.')
    cb = conductor.bbox()
    expected = db.Box(box.left, box.bottom-500, box.right, box.top+500) if not item['rotation'] else \
        db.Box(box.left-500, box.bottom, box.right+500, box.top)
    require(cb == expected, 'Terminal landing lengths differ.')
    ends = list((conductor-marker).merged().each())
    require(len(ends) == 2 and len(labels) == 2 and {r[1] for r in labels} == {'R1', 'R2'} and
            all(r[0] == (layer, 5) for r in labels), 'Terminal names, purposes or conductor islands differ.')
    assigned = []
    for _, name, x, y in labels:
        found = [i for i, polygon in enumerate(ends) if polygon.inside(db.Point(x, y))]
        require(len(found) == 1, 'Terminal lies outside its conductor landing.'); assigned.extend(found)
        require((y < box.bottom if name == 'R1' else y > box.top) if not item['rotation'] else
                (x > box.right if name == 'R1' else x < box.left), 'Terminal order/orientation differs.')
    require(len(set(assigned)) == 2, 'Terminals share a conductor island.')


def project_geometry(project, target):
    import klayout.db as db
    cells = project['cells']; require(len(cells) == 1, 'Unexpected physical project hierarchy.')
    cell = cells[0]; layers = {v['name']: (v['gds'], v['datatype']) for v in project['pdk']['layers']}
    masks = {}
    for shape in cell.get('shapes', []):
        require(shape['layer'] in layers and shape['kind'] in ('rect', 'polygon'), 'Unknown physical project shape.')
        pair = layers[shape['layer']]
        polygon = db.Polygon(db.Box(*shape['points'][0], *shape['points'][1])) if shape['kind'] == 'rect' else \
            db.Polygon([db.Point(*p) for p in shape['points']])
        for hole in shape.get('holes', []): polygon.insert_hole([db.Point(*p) for p in hole])
        masks.setdefault(pair, db.Region()).insert(polygon)
    masks = {key: value.merged() for key, value in masks.items() if not value.is_empty()}
    # The normal stream importer retains purpose-5 text; app projects have ports.
    if cell.get('layout_ports'):
        labels = sorted(((layers[r['layer']][0], 5), r['name'], *r['point']) for r in cell['layout_ports'])
    else:
        labels = sorted((layers[r['layer']], r['text'], r['x'], r['y']) for r in cell.get('layout_texts', []))
    same_stream((masks, labels), target)


def geometry(folder, source_gds, item, fault=None):
    import klayout.db as db
    source = stream(source_gds, item['top']); expected = ({k: v.dup() for k, v in source[0].items()}, list(source[1]))
    if fault == 'width':
        require(item['rotation'] == 0 and item['width_um'] == 2 and item['length_um'] == 5, 'Wrong width-control case.')
        layer = 67+MODELS.index(item['model'])
        for purpose in (20, 13):
            box = expected[0][layer, purpose].bbox()
            expected[0][layer, purpose] = db.Region(db.Box(box.left, box.bottom, box.right+400, box.top))
    elif fault == 'drc':
        expected[0][68, 20] = expected[0].get((68, 20), db.Region()) + db.Region(db.Box(100000, 100000, 100100, 100100))
    else: require(fault is None, 'Unknown geometry fault.')
    original = stream(folder/'original.gds', item['top']); written = stream(folder/'layout.gds', item['top'])
    same_stream(original, expected); same_stream(written, expected)
    if fault != 'drc': resistor_geometry(written, item, 1.2 if fault == 'width' else 1)
    project_geometry(load(folder/'input.icproj'), written)
    return written


def native_scripts(folder, origin, pdk, top):
    from scripts.audit_sky130_li_case import native_script, tcl_literal
    expected = {}
    for stage in ('drc', 'lvs-extraction'):
        expected[stage+'/run.tcl'] = native_script(PurePosixPath(origin), stage).replace('load "coupon"', 'load "'+top+'"')
        expected[stage+'/startup.tcl'] = 'tech load '+tcl_literal(PurePosixPath(pdk)/'libs.tech/magic/sky130A.tech')+'\ndrc euclidean on\n'
    require({p.relative_to(folder).as_posix() for stage in ('drc', 'lvs-extraction')
             for p in (folder/stage).glob('*.tcl')} == set(expected), 'Native script coverage differs.')
    for name, text in expected.items(): require((folder/name).read_text() == text, 'Native script/settings/source differs: '+name)


def native_output(folder, native, item, fault=None):
    stages = native['stages']
    require(tuple(row['name'] for row in stages) == STAGES, 'Native stage coverage differs.')
    states = ['passed']*6
    if fault == 'width': states[4] = 'failed'
    elif fault == 'drc': states[2] = 'failed'
    else: require(fault is None, 'Unknown native fault.')
    require([r['status'] for r in stages] == states and native['status'] == ('failed' if fault else 'passed') and
            native['drc_engine'] == native['lvs_extractor'] == 'magic' and native['magic_drc_style'] == 'drc(full)',
            'Native stage outcome or engine differs.')
    stages = {row['name']: row for row in stages}
    for name in ('drc/console.log', 'lvs-extraction/console.log'):
        text = (folder/name).read_text()
        require(re.findall(r'^(STUDIO_MAGIC_COMPLETE)[ \t]*$', text, re.M) == ['STUDIO_MAGIC_COMPLETE'] and
                not re.search(r'STUDIO_MAGIC_ERROR|contained errors|Malformed line|Illegal keyword|invalid command name', text, re.I),
                'Native engine did not complete: '+name)
    log = (folder/'drc/console.log').read_text(); counts = re.findall(r'^STUDIO_DRC_COUNT (\d+)[ \t]*$', log, re.M)
    require(len(counts) == 1 and int(counts[0]) == native['drc_count'] == native['magic_drc_count'] and
            ((int(counts[0]) > 0) if fault == 'drc' else counts == ['0']) and
            re.findall(r'^STUDIO_DRC_STYLE (.+)$', log, re.M) == ['drc(full)'], 'Raw full DRC outcome differs.')
    findings = (folder/'drc/findings.tsv').read_text().splitlines()
    require(bool(findings) == (fault == 'drc'), 'Raw DRC findings differ.')
    for line in findings:
        rule, coords = line.split('\t'); values = list(map(float, coords.split(',')))
        require(bool(rule) and len(values) == 4 and all(map(math.isfinite, values)), 'Malformed DRC finding.')
    circuit((folder/'lvs-extraction/extracted.spice').read_text(), item['top'], item['model'],
            item['width_um']*(1.2 if fault == 'width' else 1), item['length_um'], extracted=True)
    text = (folder/'lvs/lvs.log').read_text()
    require(not re.search('invalid command|could not open|cannot open|Error in', text, re.I), 'Native fault was an infrastructure error.')
    if fault == 'width':
        require('Property errors were found.' in text and re.search(r'^ w circuit1:', text, re.M) and
                'Cell pin lists are equivalent.' in text, 'Width fault lacks a connected native width mismatch.')
    else:
        require(re.findall(r'^Final result: (.+)$', text, re.M) == ['Circuits match uniquely.'] and
                'Cell pin lists are equivalent.' in text and not re.search(
                    r'Property errors|Circuits do not match|Netlists do not match|disconnected node:|\(no matching pin\)|pin lists[^\n]*altered', text, re.I),
                'Raw Netgen report does not establish a unique connected match.')
    require(stages['lvs_extraction']['evidence'] == dict(deck='lvs-extraction/extracted.spice',
            sha256=sha(folder/'lvs-extraction/extracted.spice'), settings=EXTRACTION_SETTINGS), 'Native extraction settings/output differ.')
    if fault == 'width':
        require(stages['lvs'] == dict(name='lvs', status='failed', error=
            'Netgen did not establish a unique match with equivalent connected pins and no property errors. See lvs/lvs.log.'),
            'Width-fault stage did not retain the native matching failure.')
    else:
        require(stages['lvs']['evidence'] == dict(unique_match=True, log='lvs/lvs.log'), 'LVS receipt differs.')
    integrity = stages['integrity']['evidence']; file_map(folder, integrity['files'])
    require(integrity.get('verified') is True and {'layout.gds', 'input.icproj', 'schematic.spice', 'schematic-lvs.spice',
            'drc/console.log', 'lvs-extraction/extracted.spice', 'lvs/lvs.log'} <= integrity['files'].keys(), 'Native integrity coverage incomplete.')
    return stages


def physical_job(root, row, item, report, physical, runtime, runtime_files, fault=None):
    require(row['execution_id'] == report['execution_id'] and row['top'] == item['top'] and
            row['native_execution'] is True and row['state'] == 'Complete', 'Native case is stale or incomplete.')
    job_root = confined(root, row['job_directory']); folder = confined(root, row['evidence_directory'])
    require(folder == job_root/'physical-flow' and job_root.name == row['job_id'], 'Queued job directory identity differs.')
    require(sha(job_root/'input.json') == row['input_sha256'] and sha(job_root/'result.json') == row['result_sha256'], 'Queued input/result changed.')
    job = load(job_root/'input.json'); result = load(job_root/'result.json')
    require(all(row[k] == item[k] for k in ('model', 'geometry_index', 'width_um', 'length_um', 'rotation', 'multiplicity', 'top', 'terminals')) and
            row['source_case'] == item['case'] and Path(row['execution_root']).resolve() == root and
            row['reference'] == item['reference'] and row['reference_sha256'] == item['reference_sha256'] and
            row['project_revision'] == job['project']['revision'], 'Queued case metadata differs from actual GUI inputs.')
    require(not result.get('reused_from') and result['silicon_report'] == row['report'] and result['settings'] == row['settings'] and
            design_hash(job['project']) == row['design_hash'] == result['design_hash'], 'Queued input/result binding differs.')
    settings = job['settings']
    require(settings['verification_mode'] == 'drc_lvs' and settings['drc_engine'] == settings['lvs_extractor'] == 'magic',
            'Queued physical settings differ.')
    if runtime is not None:
        require(settings['physical_toolchain'] == 'included' and settings['physical_runtime'] == runtime,
                'Queued job did not select shipped physical runtime.')
    else:
        require(report['frozen'] is False and settings['physical_toolchain'] == 'custom' and
                not row['report'].get('execution'), 'Source pilot must explicitly use local custom tools.')
    text = confined(root, item['reference']).read_text()
    require(settings['reference'] == dict(text=text, top=item['top'], ports=['R1', 'R2'], sha256=hashlib.sha256(text.encode()).hexdigest()),
            'Queued schematic differs from GUI export.')
    native = load(folder/'report.json')
    if runtime is not None:
        execution = row['report']['execution']; native_job = load(job_root/'physical-backend-input.json')
        require(execution['runtime'] == runtime and sha(job_root/'physical-backend-input.json') == execution['native_input_sha256'],
                'Managed native input identity differs.')
        received = load(job_root/'physical-artifacts.json')
        require(execution['received_files'] == received, 'Received artifact inventory differs.'); file_map(job_root, received)
        actual = {'physical-flow/'+name: value for name, value in inventory(folder).items()}
        actual['physical-backend-result.json'] = sha(job_root/'physical-backend-result.json')
        require(received == actual, 'Native transfer inventory omitted or added an artifact.')
        backend_result = load(job_root/'physical-backend-result.json')
        require(backend_result['silicon_report'] == native, 'Backend report differs.')
        expected_project = copy.deepcopy(job['project']); native_dir = execution['native_directory']
        expected_project['pdk']['package_root'] = native_dir+'/pdk'
        require(native_job['project'] == expected_project and native_job['cell'] == job['cell'], 'Managed transfer changed project data.')
        origin = native_dir+'/output/physical-flow'; pdk = native_dir+'/pdk'
        prefix = '/' if runtime['kind'] == 'wsl' else runtime['root'].rstrip('/')+'/'
        tools = {name: dict(path=prefix+'opt/icstudio/bin/'+name, sha256=runtime_files['opt/icstudio/bin/'+name]) for name in ('magic', 'netgen')}
    else:
        native_job = job; origin = folder.as_posix(); pdk = Path(job['project']['pdk']['package_root']).as_posix()
        require(Path(pdk).resolve() == Path(report['physical_package']['path']).resolve(), 'Source physical adapter differs.')
        tools = {name: dict(path=settings['tools'][name], sha256=sha(unlinked(settings['tools'][name]))) for name in ('magic', 'netgen')}
    require(native['design_hash'] == design_hash(native_job['project']) and load(folder/'input.icproj') == native_job['project'] and
            native['cell_name'] == item['top'], 'Native project/result belongs to another case.')
    require(native_job['project']['pdk']['package_lock'] == {k: physical[k] for k in ('id', 'revision', 'files')}, 'Native physical lock differs.')
    stages = native_output(folder, native, item, fault)
    for key in ('status', 'stages', 'reference', 'drc_count'):
        require(row['report'][key] == native[key], 'Host/native report differs: '+key)
    native_scripts(folder, origin, pdk, item['top'])
    assets = {pdk+'/'+name: value for name, value in physical['files'].items() if name.startswith(('libs.tech/magic/', 'libs.tech/netgen/'))}
    for name in ('preflight', 'integrity'):
        require(stages[name]['evidence']['assets'] == assets and stages[name]['evidence']['tools'] == tools,
                'Native PDK/tool identity differs from installed runtime.')
    require((folder/'schematic.spice').read_text() == text, 'Native reference was substituted.')
    circuit((folder/'schematic-lvs.spice').read_text(), item['top'], item['model'], item['width_um'], item['length_um'])
    console = (folder/'lvs/console.log').read_text()
    from scripts.audit_sky130_li_case import check_netgen_inputs
    check_netgen_inputs(console, PurePosixPath(origin), PurePosixPath(pdk))
    geometry(folder, confined(root, item['gds']), item, fault)
    if fault is None and row['case'] == item['case']:
        require(confined(root, item['native']) == folder/'lvs-extraction/extracted.spice' and
                item['native_sha256'] == sha(folder/'lvs-extraction/extracted.spice') and item['native_job_id'] == row['job_id'] and
                item['native_design_hash'] == row['design_hash'], 'Lifecycle extraction does not bind the fresh clean queued job.')
    return job_root


def header(report, executable, expected_commit, execution_id):
    require(report.get('schema') == 1 and report.get('status') == 'passed' and report.get('mode') == 'physical' and
            report.get('frozen') is True and report.get('native_execution') is True, 'Installed resistor evidence is incomplete or source-only.')
    build = report.get('build', {})
    require(re.fullmatch('[0-9a-f]{40}', expected_commit) and build.get('commit') == expected_commit and
            build.get('dirty') is False and build.get('frozen') is True, 'Installed evidence belongs to another or dirty build.')
    require(report.get('execution_id') == execution_id and re.fullmatch('[0-9a-f]{32}', execution_id), 'Stale execution identity.')
    require(Path(report['executable']).resolve() == Path(executable).resolve() and report['executable_sha256'] == sha(executable),
            'Installed executable identity differs.')
    require(all(report.get(key) is False for key in ('qualified', 'release_ready', 'full_family', 'installed_acceptance')),
            'Bounded app probe must not self-claim installed or whole-family qualification.')
    require(not report.get('errors') and not report.get('error'), 'Application reported errors.')


def control_edit(original, changed, control, width):
    """Reconstruct the intended project edit independently of the producer."""
    expected = copy.deepcopy(original); cell = expected['cells'][0]
    if width:
        edits = control['edits']; require(len(edits) == 2 and len({r['shape'] for r in edits}) == 2, 'Incomplete width edits.')
        for edit in edits:
            shapes = [r for r in cell['shapes'] if r['id'] == edit['shape']]
            require(len(shapes) == 1, 'Width edit references unknown shape.')
            shape = shapes[0]; before = shape['points']
            require(shape['layer'] == edit['layer'] and before == edit['before_points'] and
                    len(before) in (2, 4) and len({p[1] for p in before}) == 2, 'Width edit initial identity differs.')
            xs = {p[0] for p in before}; require(len(xs) == 2 and max(xs)-min(xs) == 2000, 'Width control initial dimensions differ.')
            after = [[x+400 if x == max(xs) else x, y] for x, y in before]
            require(after == edit['after_points'], 'Width control did not change exactly the right edge.')
            shape['points'] = after
    else:
        shape = control['added_shape']; require(shape['id'] not in {r['id'] for r in cell['shapes']}, 'DRC control reused an existing shape.')
        layers = {r['name']: (r['gds'], r['datatype']) for r in expected['pdk']['layers']}
        require(layers[shape['layer']] == (68, 20) and shape['kind'] == 'rect' and
                shape['points'] == [[100000, 100000], [100100, 100100]], 'DRC control did not add the selected narrow metal.')
        cell['shapes'].append(shape)
    # The real shape actions normalize absent schematic labels to an empty
    # list. No actual label may be added during either physical edit.
    if 'labels' not in cell and changed['cells'][0].get('labels') == []:
        cell['labels'] = []
    require(content_hash(expected) == content_hash(changed), 'Fault project changed more than the intended physical edit.')


def controls(root, report, physical, runtime, runtime_files, jobs):
    rows = report['controls']
    require(len(rows) == 7 and [r.get('kind') for r in rows] == ['width-cycle']*5+['narrow-metal-cycle', 'missing-engine'],
            'Missing width/repair/DRC/block controls.')
    items = {r['case']: r for r in report['lifecycle']}; clean = {r['case']: r for r in report['physical']}
    for index, control in enumerate(rows[:6]):
        name = MODELS[index]+'-g1-r0' if index < 5 else 'm4-g2-r90'
        require(control['source_case'] == name, 'Control belongs to another case.')
        item = items[name]; baseline = clean[name]; fault = control['fault']; repair = control['repair']
        require(control['baseline_design_hash'] == baseline['design_hash'] != repair['design_hash'] and
                control['after_design_hash'] == fault['design_hash'] != baseline['design_hash'] and control['displayed'] is True,
                'Edit invalidation/repair identity differs.')
        fault_root = physical_job(root, fault, item, report, physical, runtime, runtime_files, 'width' if index < 5 else 'drc')
        repaired_root = physical_job(root, repair, item, report, physical, runtime, runtime_files)
        original = load(confined(root, baseline['job_directory'])/'input.json')['project']
        control_edit(original, load(fault_root/'input.json')['project'], control, index < 5)
        repaired = load(repaired_root/'input.json')['project']
        require(content_hash(original) == content_hash(repaired) == control['before_content_hash'] == control['repaired_content_hash'],
                'Repair changed design content beyond revision/modified.')
        jobs.extend((fault_root, repaired_root))
    blocked = rows[-1]['job']; item = items['m4-g2-r90']; repaired = rows[-2]['repair']
    require(rows[-1]['source_case'] == item['case'], 'Missing-engine case differs.')
    folder = confined(root, blocked['job_directory']); result = load(folder/'result.json'); job = load(folder/'input.json')
    require(folder.name == blocked['job_id'] and blocked['execution_id'] == report['execution_id'] and blocked['top'] == item['top'] and
            blocked['state'] == 'Complete' and blocked['native_execution'] is False and
            sha(folder/'input.json') == blocked['input_sha256'] and sha(folder/'result.json') == blocked['result_sha256'] and
            result['silicon_report'] == blocked['report'] and not result.get('reused_from') and
            blocked['report']['status'] == 'blocked' and [(s['name'], s['status']) for s in blocked['report']['stages']] ==
            [(name, 'failed' if name == 'preflight' else 'not_run') for name in STAGES] and
            not blocked['report'].get('execution') and not (folder/'physical-artifacts.json').exists(), 'Missing engine did not block before native execution.')
    require(job['settings']['physical_toolchain'] == 'custom' and
            Path(job['settings']['tools']['magic']).resolve() == root/'missing-magic-executable' and
            not (root/'missing-magic-executable').exists() and
            design_hash(job['project']) == blocked['design_hash'] == result['design_hash'] == repaired['design_hash'],
            'Missing-engine control selected another executable/project.')
    jobs.append(folder)
    require(len(jobs) == len(set(jobs)) == 43, 'Physical cases reused a job directory.')


def source_audit(root, reviewed_source=None):
    """Explicit development readback; its result cannot satisfy installed audit."""
    root = unlinked(root).resolve(); report = load(root/'report.json')
    source = unlinked(reviewed_source).resolve() if reviewed_source is not None else ROOT
    require(report.get('schema') == 1 and report.get('status') == 'passed' and report.get('mode') == 'physical' and
            report.get('frozen') is False and report.get('native_execution') is True and
            all(report.get(k) is False for k in ('qualified', 'release_ready', 'full_family', 'installed_acceptance')) and
            not report.get('error') and not report.get('errors'), 'Source pilot is incomplete or overclaims installation.')
    require(Path(report['execution_root']).resolve() == root and Path(report['resource_root']).resolve() == source and
            re.fullmatch('[0-9a-f]{32}', report['execution_id']), 'Source pilot execution/resource identity differs.')
    require(sha(root/'files.json') == report['files_sha256'] and load(root/'files.json') == inventory(root, ('files.json', 'report.json')),
            'Source pilot inventory incomplete or changed.')
    current_path = source/'icstudio/assets/pdks/sky130A'; lock_path = source/'examples/sky130-qualification-lock.json'
    current = package(current_path, sha(root/'bundled-package.json'))
    require(sha(root/'bundled-collection.json') == sha(source/'icstudio/assets/pdks/collection.json') and
            sha(root/'physical-release-lock.json') == sha(lock_path), 'Source package collection/physical lock differs.')
    physical_path = unlinked(report['physical_package']['path']).resolve()
    physical = package(physical_path, load(lock_path)['manifest_sha256'])
    require(sha(root/'physical-package.json') == sha(physical_path/'package.json') and
            report['physical_package']['files'] == physical['files'] and
            report['bundled_package']['files'] == current['files'], 'Source reported package inputs differ.')
    historical = package(root/'historical-package', OLD_MANIFEST); lifecycle(root, report, current, historical)
    require([r.get('case') for r in report['physical']] == list(CASES), 'Incomplete source native layout cases.')
    jobs = [physical_job(root, row, item, report, physical, None, None)
            for row, item in zip(report['physical'], report['lifecycle'])]
    controls(root, report, physical, None, None, jobs)
    return dict(schema=1, status='PASS', gate='metal-resistor-source-gui-queued-layout', scope=SCOPE.replace('Installed Qt', 'Source Qt'),
        qualified=False, release_ready=False, full_family=False, installed_acceptance=False,
        execution_id=report['execution_id'], report_sha256=sha(root/'report.json'), files_sha256=sha(root/'files.json'),
        counts=dict(lifecycle=30, binding_lifecycle=15, native_layouts=30, fresh_native_jobs=42, queued_jobs=43,
                    width_faults=5, drc_faults=1, repairs=6, blocked=1))


def audit(root, executable, physical_root, expected_commit, execution_id, inputs, backend, payload_hash):
    root = unlinked(root).resolve(); report = load(root/'report.json'); header(report, executable, expected_commit, execution_id)
    sources = checker_sources(expected_commit)
    bundle = Path(executable).resolve().parent/'_internal'
    require(Path(report['resource_root']).resolve() == bundle and Path(report['execution_root']).resolve() == root, 'App used external resources or evidence.')
    require(sha(root/'files.json') == report['files_sha256'] and load(root/'files.json') == inventory(root, ('files.json', 'report.json')),
            'Probe inventory incomplete or changed.')
    current = package(bundle/'icstudio/assets/pdks/sky130A', inputs['package_sha256'])
    physical = package(physical_root, inputs['physical_sha256']); historical = package(root/'historical-package', OLD_MANIFEST)
    for name, expected in (('bundled-package.json', inputs['package_sha256']), ('bundled-collection.json', inputs['collection_sha256']),
                          ('physical-package.json', inputs['physical_sha256']), ('physical-release-lock.json', inputs['physical_lock_sha256'])):
        require(sha(root/name) == expected, 'Captured package/lock differs: '+name)
    require(report['bundled_package']['manifest_sha256'] == inputs['package_sha256'] and report['bundled_package']['files'] == current['files'] and
            report['physical_package']['files'] == physical['files'] and report['physical_package']['manifest_sha256'] == inputs['physical_sha256'] and
            Path(report['physical_package']['path']).resolve() == Path(physical_root).resolve(), 'Reported package inputs differ.')
    lifecycle(root, report, current, historical)
    runtime, runtime_files = check_runtime(root, report, bundle, backend, payload_hash)
    require([r.get('case') for r in report['physical']] == list(CASES), 'Incomplete or duplicated native layout cases.')
    jobs = [physical_job(root, row, item, report, physical, runtime, runtime_files)
            for row, item in zip(report['physical'], report['lifecycle'])]
    controls(root, report, physical, runtime, runtime_files, jobs)
    return dict(schema=1, status='PASS', gate='metal-resistor-installed-gui-queued-layout', scope=SCOPE,
        qualified=False, release_ready=False, full_family=False, expected_commit=expected_commit, execution_id=execution_id,
        report_sha256=sha(root/'report.json'), files_sha256=sha(root/'files.json'), executable_sha256=sha(executable),
        package_inputs=inputs, counts=dict(lifecycle=30, binding_lifecycle=15, native_layouts=30, fresh_native_jobs=42,
        queued_jobs=43, width_faults=5, drc_faults=1, repairs=6, blocked=1), runtime=runtime,
        backend_files_sha256=digest(backend), checker_sources=sources)


def verify(executable, physical_pdk, out, expected_commit, timeout=2400):
    executable = unlinked(executable).resolve(); physical_pdk = unlinked(physical_pdk).resolve(); out = unlinked(out).resolve()
    require(re.fullmatch('[0-9a-f]{40}', expected_commit) and math.isfinite(timeout) and timeout > 0, 'Choose exact candidate and finite positive deadline.')
    require(not out.exists(), 'Use a new output directory; existing evidence cannot qualify as fresh.')
    out.mkdir(parents=True); started = time.monotonic(); execution_id = uuid.uuid4().hex
    try:
        inputs = expected_inputs(expected_commit); bundle = executable.parent/'_internal'
        package(bundle/'icstudio/assets/pdks/sky130A', inputs['package_sha256']); package(physical_pdk, inputs['physical_sha256'])
        require(sha(bundle/'icstudio/assets/pdks/collection.json') == inputs['collection_sha256'], 'Bundled collection differs.')
        payload = bundle/'icstudio/assets/runtime/digital'; payload_hash = sha(payload/'manifest.json'); manifest = load(payload/'manifest.json')
        require(manifest.get('schema') == 1 and manifest.get('archive') == 'runtime.tar.gz' and
                sha(payload/'runtime.tar.gz') == manifest['sha256'], 'Bundled runtime archive missing or changed.')
        backend = backend_binding(payload/'backend/icstudio', expected_commit); exe_hash = sha(executable)
        env = git_environment()
        for key in list(env):
            if key.upper() in ('PYTHONPATH', 'PYTHONHOME', 'ICSTUDIO_DIGITAL_PAYLOAD', 'ICSTUDIO_DIGITAL_NATIVE',
                              'ICSTUDIO_BUNDLED_NGSPICE', 'ICSTUDIO_NGSPICE', 'LD_LIBRARY_PATH', 'LD_PRELOAD'):
                env.pop(key)
        env['QT_QPA_PLATFORM'] = 'offscreen'
        if not env.get('ICSTUDIO_DIGITAL_STATE'):
            base = Path(env['LOCALAPPDATA']) if os.name == 'nt' else Path(env.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
            env['ICSTUDIO_DIGITAL_STATE'] = str(base/'ICDesignStudio/digital')
        command = [str(executable), '--metal-resistor-acceptance', '--mode', 'physical', '--managed',
                   '--physical-pdk', str(physical_pdk), '--execution-id', execution_id, '--out', str(out/'probe')]
        (out/'invocation.json').write_text(json.dumps(dict(command=command, expected_commit=expected_commit,
            execution_id=execution_id, executable_sha256=exe_hash, inputs=inputs, payload_manifest_sha256=payload_hash), indent=2))
        with (out/'launcher.log').open('wb') as log:
            subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=True)
        require(sha(executable) == exe_hash and sha(payload/'manifest.json') == payload_hash and
                backend_binding(payload/'backend/icstudio', expected_commit) == backend, 'Installed executable/backend/payload changed during acceptance.')
        result = audit(out/'probe', executable, physical_pdk, expected_commit, execution_id, inputs, backend, payload_hash)
        result.update(seconds=time.monotonic()-started, timeout_seconds=timeout)
        (out/'verification.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n'); return result
    except Exception as exc:
        if isinstance(exc, subprocess.TimeoutExpired):
            for path in (out/'probe/runs with spaces').glob('*/*/input.json'):
                if load(path).get('settings', {}).get('physical_runtime'): (path.parent/'digital-cancel').write_text('cancel\n')
        (out/'verification.json').write_text(json.dumps(dict(schema=1, status='FAIL', scope=SCOPE,
            qualified=False, release_ready=False, full_family=False, expected_commit=expected_commit,
            execution_id=execution_id, error=str(exc), seconds=time.monotonic()-started), indent=2)+'\n')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('executable', 'physical-pdk', 'out'): parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--expected-commit', required=True); parser.add_argument('--timeout', type=float, default=2400)
    args = parser.parse_args(); print(json.dumps(verify(args.executable, args.physical_pdk, args.out, args.expected_commit, args.timeout), indent=2))


if __name__ == '__main__':
    main()
