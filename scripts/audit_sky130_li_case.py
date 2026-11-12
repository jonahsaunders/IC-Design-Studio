"""Independent raw-evidence audit for the selected LI 2 x 5 physical case.

This does not import the producer, its geometry/fault helpers, or its verdict
parsers. It checks the sampled integration contract, not a device envelope.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

CASE = 'l1-w2-l5'
MODEL = 'sky130_fd_pr__res_generic_l1'
FAULTS = ('terminal-open', 'terminal-short', 'reference-width', 'reference-length', 'reference-model')
STAGES = ('preflight', 'layout_export', 'drc', 'lvs_extraction', 'lvs', 'integrity')
EXTRACTION_SETTINGS = {'hierarchy': True, 'blackbox': False, 'merge': 'none', 'scale': False,
                       'capacitance_threshold': 'infinite', 'resistance_threshold': 'infinite',
                       'distributed_resistance': False}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def tcl_literal(value):
    text = str(value)
    for old, new in (('\\', '\\\\'), ('"', '\\"'), ('$', '\\$'), ('[', '\\['), (']', '\\]'), ('\n', '\\n'), ('\r', '\\r')):
        text = text.replace(old, new)
    return '"' + text + '"'


def generator_script(pdk):
    return '''tech load {PDK/libs.tech/magic/sky130A.tech}
scalegrid 1 2
source {PDK/libs.tech/magic/sky130A.tcl}
load coupon -silent
box values 0 0 0 0
set parameters [dict merge [sky130::sky130_fd_pr__res_generic_l1_defaults] [dict create w 2 l 5 m 1 nx 1 snake 0]]
if {[catch {sky130::sky130_fd_pr__res_generic_l1_draw $parameters} err]} {puts stderr "GENERATOR_FAILED $err"; quit -noprompt}
select top cell
box select
save coupon
gds write coupon.gds
puts GENERATOR_COMPLETE
quit -noprompt
'''.replace('PDK', str(pdk))


def native_script(origin, stage):
    prefix = ('gds read ' + tcl_literal(origin / 'layout.gds') + '\nload "coupon"\nselect top cell\nbox values 0 0 0 0\n'
              'if {![port "R1" exists]} {error "Missing layout port R1"}\nport "R1" index 1\n'
              'if {![port "R2" exists]} {error "Missing layout port R2"}\nport "R2" index 2\n')
    if stage == 'drc':
        body = r'''snap internal
select top cell
box values {*}[select bbox]
box grow c 10um
drc style "drc(full)"
drc ignore none
drc check
drc catchup
puts "STUDIO_DRC_COUNT [drc list count total]"
puts "STUDIO_DRC_STYLE [drc list style]"
puts "STUDIO_MAGIC_SCALE [cif scale out]"
set f [open findings.tsv w]
foreach {reason boxes} [drc listall why] {foreach coords $boxes {puts $f "[string map {\t { } \n { }} $reason]\t[join $coords {,}]"}}
close $f
'''
    else:
        require(stage == 'lvs-extraction', 'Unknown native stage.')
        body = '''extract all
ext2spice lvs
ext2spice subcircuit top on
ext2spice renumber off
ext2spice global off
ext2spice hierarchy on
ext2spice blackbox off
ext2spice scale off
ext2spice merge none
ext2spice cthresh infinite
ext2spice rthresh infinite
ext2spice extresist off
ext2spice -o extracted.spice'''
    return 'if {[catch {\n' + prefix + body + '\nputs STUDIO_MAGIC_COMPLETE\n} err]} {puts stderr "STUDIO_MAGIC_ERROR $err"}\nquit -noprompt\n'


def context(identity):
    require(identity.get('suite') == 'sky130-li-physical-development-v1' and
            identity.get('contract', {}).get('case') == CASE, 'Wrong captured execution identity.')
    physical = identity['physical_pdk']
    root = Path(physical['root'])
    files = physical['files']
    assets = {str(root / name): row['sha256'] for name, row in files.items()
              if name.startswith(('libs.tech/magic/', 'libs.tech/netgen/')) and 'sha256' in row}
    require(assets and sha(root / 'package.json') == files['package.json']['sha256'], 'Physical manifest differs from captured identity.')
    for path, expected in assets.items():
        require(sha(path) == expected, 'Native rule/generator/setup asset differs from captured identity.')
    tools = {name: {'path': path, 'sha256': identity['runtime']['files'][path]['sha256']}
             for name, path in identity['tools'].items()}
    return {'pdk': root, 'assets': assets, 'tools': tools}


def check_generator(folder, pdk):
    require((folder / 'generate.tcl').read_text(encoding='utf-8') == generator_script(pdk),
            'Native generator source/parameters differ from captured PDK/fixed case.')
    require((folder / 'empty.magicrc').read_bytes() == b'', 'Unexpected generator startup configuration.')


def check_native_scripts(folder, origin, pdk):
    for stage in ('drc', 'lvs-extraction'):
        script = (folder / stage / 'run.tcl').read_text(encoding='utf-8')
        require(script == native_script(origin, stage), 'Native ' + stage + ' script/source/settings differ from the fixed case.')
        startup = (folder / stage / 'startup.tcl').read_text(encoding='utf-8')
        require(startup == 'tech load ' + tcl_literal(pdk / 'libs.tech/magic/sky130A.tech') + '\ndrc euclidean on\n',
                'Native startup technology/settings differ from captured PDK.')


def check_netgen_inputs(console, origin, pdk):
    require(re.findall(r'^Reading netlist file (.+)$', console, re.M) ==
            [str(origin / 'schematic-lvs.spice'), str(origin / 'lvs-extraction/extracted.spice')],
            'Netgen did not read the retained schematic and extraction.')
    require(re.findall(r'^Reading setup file (.+)$', console, re.M) == [str(pdk / 'libs.tech/netgen/sky130A_setup.tcl')],
            'Netgen setup differs from captured PDK.')
    require(re.findall(r'^Comparison output logged to file (.+)$', console, re.M) ==
            [str(origin / 'lvs/lvs.log')] and console.count('LVS Done.') == 1,
            'Incomplete or redirected native Netgen comparison.')


def stream(path):
    import klayout.db as db
    layout = db.Layout()
    layout.read(str(path))
    require(layout.cells() == 1 and layout.top_cell().name == 'coupon', 'Unexpected stream hierarchy/top.')
    require(layout.dbu == .001, 'Unexpected stream database units.')
    cell = layout.top_cell()
    masks, labels = {}, []
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        pair = (info.layer, info.datatype)
        # Copy polygons out of the layout. A lazy region can otherwise retain
        # borrowed layout storage after this function returns.
        region = db.Region()
        for shape in cell.shapes(index).each():
            if shape.is_box():
                region.insert(db.Polygon(shape.box))
            elif shape.is_polygon():
                region.insert(shape.polygon.dup())
            elif shape.is_path():
                region.insert(shape.path.polygon())
        region.merge()
        if not region.is_empty():
            masks[pair] = region
        for shape in cell.shapes(index).each():
            if shape.is_text():
                labels.append((pair, shape.text.string, shape.text.x, shape.text.y))
    return masks, sorted(labels)


def equal_masks(left, right):
    require(set(left) == set(right), 'Unexpected mask layer set.')
    require(all((left[k] ^ right[k]).is_empty() for k in left), 'Physical mask geometry changed.')


def expected(angle=0, fault=None):
    import klayout.db as db
    conductor = db.Region(db.Box(-1000, -2785, 1000, 2785))
    marker = db.Region(db.Box(-1000, -2500, 1000, 2500))
    if fault == 'terminal-open':
        conductor -= db.Region(db.Box(-1100, -2577, 1100, -2567))
    elif fault == 'terminal-short':
        for box in ((-200, -2843, 2200, -2443), (1800, -2843, 2200, 2842), (-200, 2442, 2200, 2842)):
            conductor.insert(db.Box(*box))
    labels = [((67, 5), 'R1', 0, -2643), ((67, 5), 'R2', 0, 2642)]
    if angle:
        transform = db.Trans(db.Trans.R90)
        conductor = conductor.transformed(transform)
        marker = marker.transformed(transform)
        labels = [(pair, name, -y, x) for pair, name, x, y in labels]
    return {(67, 20): conductor.merged(), (67, 13): marker}, sorted(labels)


def check_stream(path, target, *, labels=True):
    actual = stream(path)
    equal_masks(actual[0], target[0])
    if labels:
        require(actual[1] == target[1], 'Incorrect stream labels, purposes or terminal anchors: ' + str(path))


def check_project(path, target):
    import klayout.db as db
    project = read_json(path)
    require(len(project['cells']) == 1, 'Unexpected saved project hierarchy.')
    cell = project['cells'][0]
    require(cell['name'] == 'coupon' and project['top'] == cell['id'], 'Wrong saved project top.')
    require(cell['ports'] == ['R1', 'R2'], 'Wrong saved project interface.')
    layers = {row['name']: (row['gds'], row['datatype']) for row in project['pdk']['layers']}
    masks = {}
    for shape in cell['shapes']:
        require(shape['kind'] in ('rect', 'polygon'), 'Unexpected saved shape type.')
        poly = (db.Polygon(db.Box(*shape['points'][0], *shape['points'][1])) if shape['kind'] == 'rect'
                else db.Polygon([db.Point(*point) for point in shape['points']]))
        for hole in shape.get('holes', []):
            poly.insert_hole([db.Point(*point) for point in hole])
        masks.setdefault(layers[shape['layer']], db.Region()).insert(poly)
    equal_masks({key: region.merged() for key, region in masks.items()}, target[0])
    if 'layout_ports' in cell:
        ports = sorted(((67, 5), row['name'], *row['point']) for row in cell['layout_ports']
                       if layers[row['layer']] == (67, 20))
        require(len(cell['layout_ports']) == 2 and ports == target[1], 'Incorrect saved project terminal geometry.')
    else:
        # Stream imports preserve this fixture's ordinary-purpose top labels.
        # They are selected explicitly by the recorded two-terminal reference.
        ports = sorted((layers[row['layer']], row['text'], row['x'], row['y'])
                       for row in cell.get('layout_texts', []))
        require(ports == target[1], 'Incorrect imported label-purpose terminals.')


def spice(path, *, width=2, length=5, model=MODEL, fault=None, reference=False):
    lines = [line.strip() for line in Path(path).read_text(encoding='utf-8').splitlines()
             if line.strip() and not line.lstrip().startswith('*')]
    require(len(lines) == 3 and lines[0].lower().startswith('.subckt coupon ') and
            lines[2].lower() in ('.ends', '.ends coupon'), 'Unexpected extracted/reference statements.')
    interface = lines[0].split()[2:]
    row = lines[1].split()
    require(len(row) in (6, 7) and re.fullmatch(r'R\w+', row[0], re.I) and row[3] == model,
            'Wrong resistor count/model or unsupported SPICE syntax.')
    params = {}
    for item in row[4:]:
        key, value = item.split('=')
        require(key not in params, 'Duplicate resistor parameter.')
        params[key] = float(value)
    require(set(params) == ({'w', 'l', 'm'} if reference else {'w', 'l'}), 'Unexpected resistor parameters.')
    require(all(math.isfinite(value) for value in params.values()), 'Nonfinite resistor parameter.')
    if reference:
        require(params['m'] == 1, 'Wrong multiplicity.')
    if fault == 'terminal-short':
        require(interface == ['R2'] and row[1:3] == ['R2', 'R2'], 'Short did not collapse the actual extracted terminals.')
        require(params['w'] > 0 and params['l'] > 0, 'Invalid short extraction.')
    else:
        require(interface == ['R1', 'R2'], 'Incorrect subcircuit interface.')
        if fault == 'terminal-open':
            require(row[1] == 'R2' and row[2] not in ('R1', 'R2', '0'), 'Open was not extracted as disconnected.')
        else:
            require(set(row[1:3]) == {'R1', 'R2'}, 'Incorrect resistor connectivity.')
        require(params['w'] == width and params['l'] == length, 'Incorrect extracted/reference width or length.')


def magic_log(path):
    text = Path(path).read_text(encoding='utf-8')
    require(len(re.findall(r'^STUDIO_MAGIC_COMPLETE$', text, re.M)) == 1, 'Incomplete native Magic execution.')
    require(not re.search(r'STUDIO_MAGIC_ERROR|invalid command name|contained errors|Malformed line|Illegal keyword|could not open|cannot open', text, re.I), 'Native engine error.')
    return text


def native(folder, target, origin, execution, fault=None):
    report = read_json(folder / 'report.json')
    stages = report['stages']
    require([row['name'] for row in stages] == list(STAGES), 'Incomplete or duplicate native stages.')
    statuses = [row['status'] for row in stages]
    expected_statuses = (['passed'] * 6 if fault is None else
                         ['passed', 'passed', 'failed', 'passed', 'failed', 'passed'] if fault == 'terminal-open' else
                         ['passed', 'passed', 'passed', 'failed', 'not_run', 'not_run'] if fault == 'terminal-short' else
                         ['passed', 'passed', 'passed', 'passed', 'failed', 'passed'])
    require(statuses == expected_statuses and report['status'] == ('failed' if fault else 'passed'), 'Wrong native stage outcome.')
    require(report['drc_engine'] == 'magic' and report['lvs_extractor'] == 'magic' and
            report['magic_drc_style'] == 'drc(full)', 'Wrong native engine/style.')
    require(stages[0]['evidence']['assets'] == execution['assets'] and
            stages[0]['evidence']['tools'] == execution['tools'], 'Native preflight does not bind captured assets/tools.')
    for name in ('original.gds', 'layout.gds'):
        check_stream(folder / name, target)
    for name in ('input.icproj', 'original.gds.icstudio.json'):
        check_project(folder / name, target)
    width, length, model = (2.4 if fault == 'reference-width' else 2), (6 if fault == 'reference-length' else 5), ('sky130_fd_pr__res_generic_m1' if fault == 'reference-model' else MODEL)
    for name in ('schematic.spice', 'schematic-lvs.spice'):
        spice(folder / name, width=width, length=length, model=model, reference=True)
    require(report['reference'] == {'top': 'coupon', 'ports': ['R1', 'R2'], 'sha256': sha(folder / 'schematic.spice')},
            'Native reference differs from actual captured schematic.')
    spice(folder / 'lvs-extraction/extracted.spice', fault=fault)
    drc = magic_log(folder / 'drc/console.log')
    magic_log(folder / 'lvs-extraction/console.log')
    counts = re.findall(r'^STUDIO_DRC_COUNT (\d+)$', drc, re.M)
    require(counts == (['2'] if fault == 'terminal-open' else ['0']), 'Unexpected actual native DRC count.')
    require(re.findall(r'^STUDIO_DRC_STYLE (.+)$', drc, re.M) == ['drc(full)'], 'Missing full DRC style.')
    require(report['drc_count'] == int(counts[0]), 'Summary/native DRC disagreement.')
    findings = (folder / 'drc/findings.tsv').read_text(encoding='utf-8').splitlines()
    require(bool(findings) == bool(int(counts[0])), 'Missing or inconsistent actual DRC findings.')
    if fault == 'terminal-open':
        require({line.split('\t')[0] for line in findings} == {
            'Local interconnect spacing < 34 (li.3)', 'Local interconnect width < 34 (li.1)'},
            'Open produced unrelated native DRC failures.')
    for line in findings:
        rule, coordinates = line.split('\t')
        numbers = list(map(float, coordinates.split(',')))
        require(rule and len(numbers) == 4 and all(map(math.isfinite, numbers)), 'Invalid DRC finding.')
    check_native_scripts(folder, origin / folder.name, execution['pdk'])
    if fault != 'terminal-short':
        console = (folder / 'lvs/console.log').read_text(encoding='utf-8')
        check_netgen_inputs(console, origin / folder.name, execution['pdk'])
        text = (folder / 'lvs/lvs.log').read_text(encoding='utf-8')
        require(not re.search(r'invalid command|could not open|cannot open|Error in', text, re.I), 'LVS tool failure cannot detect a fault.')
        if fault is None:
            require('Final result: Circuits match uniquely.' in text and 'Cell pin lists are equivalent.' in text and
                    not re.search(r'property errors|port errors|do not match|disconnected node|no matching pin', text, re.I), 'No strict native LVS match.')
        elif fault in ('reference-width', 'reference-length'):
            parameter = 'w' if fault == 'reference-width' else 'l'
            require('Property errors were found.' in text and re.search(r'^ ' + parameter + r' circuit1:', text, re.M), 'Missing actual parameter fault.')
        elif fault == 'reference-model':
            require('Netlists do not match.' in text and MODEL in text and 'sky130_fd_pr__res_generic_m1' in text, 'Missing actual model fault.')
        else:
            require('disconnected node: R1' in text and 'Top level cell failed pin matching.' in text, 'Missing actual terminal-open failure.')
    # Validate internal evidence hashes as well as the outer complete inventory.
    for row in stages:
        evidence = row.get('evidence', {})
        if row['name'] == 'integrity' and row['status'] == 'passed':
            require(evidence.get('verified') is True, 'Missing integrity completion.')
            require(evidence['assets'] == execution['assets'] and evidence['tools'] == execution['tools'],
                    'Native integrity does not bind captured assets/tools.')
            for relative, digest in evidence['files'].items():
                path = (folder / relative).resolve()
                require(path.is_relative_to(folder.resolve()) and sha(path) == digest, 'Native internal evidence hash mismatch.')
        if row['name'] == 'lvs_extraction' and row['status'] == 'passed':
            require(evidence['deck'] == 'lvs-extraction/extracted.spice' and evidence['sha256'] == sha(folder / evidence['deck']), 'Extraction identity mismatch.')
            require(evidence['settings'] == EXTRACTION_SETTINGS, 'Recorded extraction settings differ from the fixed case.')
    return {'status': 'PASS', 'drc_count': int(counts[0]), 'fault': fault}


def audit(folder, *, origin=None, identity=None):
    folder = Path(folder).resolve()
    origin = Path(origin).resolve() if origin is not None else folder
    if identity is None:
        identity = read_json(origin.parent / 'inputs.json')
    execution = context(identity)
    # Hash inventories cannot prove completeness if somebody removes an output
    # and rewrites the inventory. Require the full native/exchange file set.
    required = {'saved.icproj', 'record.json'}
    required.update('generator/' + name for name in ('coupon.mag', 'coupon.gds', 'empty.magicrc', 'generate.tcl', 'console.log'))
    for angle in (0, 90):
        required.add(f'external-{angle}.oas')
        for name in (f'baseline-{angle}.gds', f'layout-{angle}.oas', f'reimported-{angle}.gds'):
            required.update(name + suffix for suffix in ('', '.exchange.json', '.icstudio.json', '.report.json'))
    for name in ('physical-0', 'physical-90', *FAULTS):
        suffixes = ['report.json', 'input.icproj', 'schematic.spice', 'schematic-lvs.spice',
                    'magic-version.log', 'netgen-version.log', 'original.gds', 'original.gds.exchange.json',
                    'original.gds.icstudio.json', 'original.gds.report.json', 'layout.gds', 'drc/findings.tsv',
                    'lvs-extraction/coupon.ext', 'lvs-extraction/extracted.spice']
        suffixes += [stage + '/' + item for stage in ('drc', 'lvs-extraction')
                     for item in ('console.log', 'run.tcl', 'startup.tcl')]
        if name != 'terminal-short':
            suffixes += ['lvs/console.log', 'lvs/lvs.log', 'lvs/lvs.json']
        required.update(name + '/' + suffix for suffix in suffixes)
    require(all((folder / name).is_file() and not (folder / name).is_symlink() for name in required), 'Missing required native/exchange evidence.')
    row = read_json(folder / 'record.json')
    require((row.get('name'), row.get('model'), row.get('width_um'), row.get('length_um'), row.get('status')) ==
            (CASE, 'l1', 2, 5, 'PASS'), 'Incorrect/incomplete selected case record.')
    require([r['rotation'] for r in row['layouts']] == [0, 90], 'Missing or duplicate orientation.')
    require([r['name'] for r in row['faults']] == list(FAULTS) and all(r.get('detected') is True for r in row['faults']), 'Missing/failed fault control.')
    generator_log = (folder / 'generator/console.log').read_text(encoding='utf-8')
    require(len(re.findall(r'^GENERATOR_COMPLETE$', generator_log, re.M)) == 1 and 'GENERATOR_FAILED' not in generator_log,
            'Incomplete native generator.')
    check_generator(folder / 'generator', execution['pdk'])
    check_stream(folder / 'generator/coupon.gds', expected(), labels=False)
    check_project(folder / 'saved.icproj', expected())
    result = {'schema': 1, 'case': CASE, 'status': 'PASS', 'orientations': [], 'faults': [],
              'scope': 'Selected physical integration only; no electrical/model calibration or full envelope claim.'}
    for angle, summary in zip((0, 90), row['layouts']):
        target = expected(angle)
        for name in (f'baseline-{angle}.gds', f'layout-{angle}.oas', f'external-{angle}.oas', f'reimported-{angle}.gds'):
            check_stream(folder / name, target)
        require(all(summary['exchange'][name]['status'] == 'passed' for name in ('gds', 'oasis')), 'Reported stream exchange failed.')
        sub = folder / f'physical-{angle}'
        require(summary['report_sha256'] == sha(sub / 'report.json'), 'Orientation report hash mismatch.')
        require(summary['extracted']['sha256'] == sha(sub / 'lvs-extraction/extracted.spice'), 'Orientation extraction hash mismatch.')
        result['orientations'].append(native(sub, target, origin, execution))
    for fault, summary in zip(FAULTS, row['faults']):
        sub = folder / fault
        require(summary['report_sha256'] == sha(sub / 'report.json'), 'Fault report hash mismatch.')
        result['faults'].append(native(sub, expected(fault=fault), origin, execution, fault))
    return result
