"""Check a bounded installed MiM GUI/queued-layout subgate, not full MiM qualification.

The application produces evidence; this separate process verifies the selected
candidate, shipped inputs and raw native outputs. No electrical or public
KLayout qualification is inferred from this subgate.
"""
import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shlex
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASES = ('p1-r0', 'p1-r90', 'p2-r0', 'p2-r90')
STAGES = ('preflight', 'layout_export', 'drc', 'lvs_extraction', 'lvs', 'integrity')
OLD_MANIFEST = '42cafd2b1407783d361cfbb276abe3ba9e97b2c06a716af6c9069c8426852413'
SCOPE = 'Installed Qt MiM lifecycle and four fresh queued Magic DRC/Netgen LVS layouts only; no public KLayout, electrical60, full MiM family or manufacturing qualification.'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: '+key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Nonfinite JSON value: '+value)
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs, parse_constant=constant)


def relative(name):
    require(isinstance(name, str) and bool(name) and '\\' not in name and ':' not in name and
            not PureWindowsPath(name).drive and not PurePosixPath(name).is_absolute() and
            all(p not in ('', '.', '..') for p in name.split('/')), 'Unsafe evidence path: '+str(name))
    return name


def unlinked(path):
    path = Path(path).absolute()
    for component in (path, *path.parents):
        require(not component.is_symlink() and not (hasattr(component, 'is_junction') and component.is_junction()),
                'Selected input contains a symlink or junction.')
    return path


def confined(root, name):
    root = Path(root).resolve()
    path = Path(name)
    path = path if path.is_absolute() else root/relative(name)
    require(path.resolve().is_relative_to(root) and path.resolve() != root, 'Evidence escaped its root.')
    for component in (path, *path.parents):
        if component == root:
            break
        require(not component.is_symlink() and not (hasattr(component, 'is_junction') and component.is_junction()),
                'Evidence contains a symlink or junction.')
    return path.resolve()


def inventory(root, exclusions=()):
    root = Path(root).resolve()
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink() and not (hasattr(path, 'is_junction') and path.is_junction()),
                'Evidence contains a symlink or junction.')
        if path.is_file() and path.relative_to(root).as_posix() not in exclusions:
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


def file_map(root, records):
    require(isinstance(records, dict) and bool(records), 'Missing file inventory.')
    for name, expected in records.items():
        path = confined(root, relative(name))
        require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected) and
                path.is_file() and sha(path) == expected, 'File inventory mismatch: '+name)


def package(root, expected):
    unlinked(root)
    data = load(Path(root)/'package.json')
    require(sha(Path(root)/'package.json') == expected and data.get('id') == 'sky130A', 'Package identity differs.')
    file_map(root, data['files'])
    return data


def git_environment():
    return {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}


def git_blob(commit, name):
    require(re.fullmatch('[0-9a-f]{40}', commit), 'Expected an exact forty-character candidate commit.')
    return subprocess.run(['git', 'cat-file', 'blob', commit+':'+name], cwd=ROOT,
                          env=git_environment(), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def expected_inputs(commit):
    names = ('icstudio/assets/pdks/sky130A/package.json', 'icstudio/assets/pdks/collection.json',
             'examples/sky130-qualification-lock.json')
    values = {name: git_blob(commit, name) for name in names}
    return dict(package_sha256=hashlib.sha256(values[names[0]]).hexdigest(),
                collection_sha256=hashlib.sha256(values[names[1]]).hexdigest(),
                physical_lock_sha256=hashlib.sha256(values[names[2]]).hexdigest(),
                physical_sha256=json.loads(values[names[2]])['manifest_sha256'])


def backend_binding(folder, commit):
    # Batch binary-safe Git readback avoids trusting a dirty external checkout.
    listing = subprocess.run(['git', 'ls-tree', '-rz', commit, '--', 'icstudio'], cwd=ROOT,
                             env=git_environment(), check=True, stdout=subprocess.PIPE).stdout
    objects = []
    for entry in listing.split(b'\0'):
        if not entry:
            continue
        meta, name = entry.split(b'\t')
        name = name.decode()
        if name.count('/') == 1 and name.endswith('.py') and name != 'icstudio/build_info.py':
            objects.append((name.split('/')[-1], meta.split()[-1]))
    require(objects, 'Candidate has no Python backend sources.')
    result = subprocess.run(['git', 'cat-file', '--batch'], cwd=ROOT,
        env=git_environment(), input=b'\n'.join(oid for _, oid in objects)+b'\n', stdout=subprocess.PIPE, check=True).stdout
    expected = {}; offset = 0
    for name, oid in objects:
        end = result.index(b'\n', offset); header = result[offset:end].split(); size = int(header[2])
        require(header[:2] == [oid, b'blob'], 'Candidate backend blob identity differs.')
        value = result[end+1:end+1+size]; offset = end+size+2
        expected[name] = hashlib.sha256(value).hexdigest()
    actual = {p.name: sha(p) for p in Path(folder).glob('*.py') if p.name != 'build_info.py'}
    require(actual == expected, 'Shipped backend source differs from selected candidate.')
    metadata = {}
    for node in ast.parse((Path(folder)/'build_info.py').read_text()).body:
        require(isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name),
                'Unexpected shipped build metadata.')
        metadata[node.targets[0].id] = ast.literal_eval(node.value)
    require(metadata.get('BUILD_COMMIT') == commit and metadata.get('BUILD_DIRTY') is False,
            'Shipped backend metadata belongs to another or dirty candidate.')
    return {**expected, 'build_info.py': sha(Path(folder)/'build_info.py')}


def circuit(text, top, plate, count=1, historical=False, extracted=False):
    text = re.sub(r'\n\s*\+\s*', ' ', text)
    rows = [s.split() for s in text.splitlines() if s.strip() and not s.lstrip().startswith('*')]
    require(len(rows) == 3 and rows[0] == ['.subckt', top, 'P', 'N'] and
            rows[-1] in (['.ends'], ['.ends', top]), 'MiM circuit interface or element count differs.')
    fields = rows[1]
    require(len(fields) >= 6 and fields[0].startswith('X') and
            fields[1:4] == ['P', 'N', f'sky130_fd_pr__cap_mim_m3_{plate}'], 'MiM model or P/N terminals differ.')
    pairs = [v.split('=') for v in fields[4:]]
    require(all(len(v) == 2 for v in pairs), 'Malformed MiM parameter.')
    values = {k.lower(): float(v) for k, v in pairs}
    allowed = {'w', 'l', 'm'} if extracted else {'w', 'l', 'm', 'vm' if historical else 'mf'}
    require(len(values) == len(pairs) and set(values) <= allowed and {'w', 'l'} <= values.keys() and
            all(math.isfinite(v) for v in values.values()) and values['w'] == 2 and values['l'] == 10 and
            values.get('m', 1) == count, 'MiM dimensions or multiplicity differ.')
    if not extracted:
        require(set(values) == allowed and values['vm' if historical else 'mf'] == count,
                'Current/historical multiplier binding differs.')


def design_hash(project):
    return digest({k: v for k, v in project.items() if k not in ('waivers', 'modified', 'native_migration')})


def content_hash(project):
    return digest({k: v for k, v in project.items() if k not in ('revision', 'modified')})


def project_binding(project, plate, count, lock, top):
    require(project['pdk']['package_lock'] == {**{k: lock[k] for k in ('id', 'revision', 'files')}, 'manifest_hash': digest(lock)},
            'Saved project package lock differs.')
    cells = project['cells']
    require(len(cells) == 1 and cells[0]['name'] == top and cells[0]['ports'] == ['P', 'N'] and
            project['top'] == cells[0]['id'] and len(cells[0]['devices']) == 1, 'Saved MiM cell coverage differs.')
    dev = cells[0]['devices'][0]
    key = f'sky130_fd_pr/cap_mim_m3_{plate}.sym'
    require(dev['model_ref'] == dict(pdk='sky130A', revision=lock['revision'], device=key) and
            dev['nets'] == dict(c0='P', c1='N'), 'Saved model reference or terminals differ.')
    params = dev['model_params']
    require(set(params) == {'w', 'l', 'mf'} and tuple(float(params[k]) for k in ('w', 'l', 'mf')) == (2, 10, count),
            'Saved model parameters differ.')
    binding = project['pdk']['simulation']['catalog'][key]
    original = lock['technology']['simulation']['catalog'][key]
    for name in ('model', 'emit_parameters', 'parameter_scale', 'pin_order'):
        require(binding[name] == original[name], 'Saved model binding changed: '+name)
    return cells[0]


def lifecycle(root, report, current, historical):
    rows = report['lifecycle']
    require([v.get('case') for v in rows] == list(CASES), 'Missing, duplicated or reordered MiM layout cases.')
    for row in rows:
        plate, rotation = int(row['case'][1]), int(row['case'].split('-r')[1])
        top = f'mim_p{plate}_r{rotation}_{report["execution_id"][:12]}'
        require(row['plate'] == plate and row['rotation'] == rotation and row['top'] == top and
                row['execution_id'] == report['execution_id'], 'Stale or substituted lifecycle case identity.')
        project = confined(root, row['project']); data = load(project)
        require(sha(project) == row['project_sha256'] and design_hash(data) == row['design_hash'], 'Saved lifecycle project differs.')
        cell = project_binding(data, plate, 1, current, top)
        registry_binding(root, report, data, current)
        require(cell.get('pdk_layouts') == row['generation'] and bool(row['generation']), 'Missing linked footprint generation.')
        reference = confined(root, row['reference'])
        circuit(reference.read_text(), top, plate)
        emitted_schematic(root, row, data)
        require(sha(confined(root, row['gds'])) == row['gds_sha256'], 'Written lifecycle GDS differs.')
    binding_rows = report['binding_lifecycle']
    require([v.get('kind') for v in binding_rows] == ['historical-before', 'historical-after-current-install', 'current'],
            'Historical/current lifecycle coverage differs.')
    projects = []
    for row in binding_rows:
        old = row['kind'] != 'current'; data = load(confined(root, row['project']))
        require(sha(confined(root, row['project'])) == row['project_sha256'] and design_hash(data) == row['design_hash'],
                'Saved multiplier lifecycle differs.')
        project_binding(data, 2, 4, historical if old else current, 'device_coupon')
        registry_binding(root, report, data, historical if old else current)
        circuit(confined(root, row['reference']).read_text(), 'device_coupon', 2, 4, historical=old)
        emitted_schematic(root, row, data)
        projects.append(data)
    require(projects[0] == projects[1], 'Installing current models silently migrated a saved historical project.')


def registry_binding(root, report, project, expected):
    folder = confined(root, project['pdk']['package_root'])
    key = expected['id']+'@'+expected['revision']
    require(folder.name == key and load(folder/'package.json') == expected and
            sha(folder/'package.json') == report['registry_manifests'][key], 'Installed registry metadata differs.')
    file_map(folder, expected['files'])


def emitted_schematic(root, row, project):
    text = confined(root, row['schematic']).read_text()
    reference = confined(root, row['reference']).read_text()
    devices = re.findall(r'(?m)^X\S+.*$', text)
    require(len(devices) == 1 and devices == re.findall(r'(?m)^X\S+.*$', reference),
            'GUI SPICE export differs from its captured device reference.')
    require(not re.search(r'(?im)^\s*[mrcdqjblv]\S+\s', text), 'GUI export contains an additional primitive.')
    package_root = Path(project['pdk']['package_root']).resolve()
    includes = re.findall(r'(?mi)^\.(lib|include) "([^"]+)"(?: (\S+))?$', text)
    require(bool(includes), 'GUI export lost its model includes.')
    for kind, name, section in includes:
        path = confined(package_root, name)
        relative_name = path.relative_to(package_root).as_posix()
        require(project['pdk']['package_lock']['files'].get(relative_name) == sha(path) and
                ((kind.lower() == 'lib' and section == 'tt') or (kind.lower() == 'include' and not section)),
                'GUI export references an unbound model or corner.')


def header(report, executable, expected_commit, execution_id):
    require(report.get('schema') == 1 and report.get('status') == 'passed' and report.get('mode') == 'physical' and
            report.get('frozen') is True and report.get('native_execution') is True, 'Installed MiM physical evidence is incomplete or source-only.')
    build = report.get('build', {})
    require(re.fullmatch('[0-9a-f]{40}', expected_commit) and build.get('commit') == expected_commit and
            build.get('dirty') is False and build.get('frozen') is True, 'Installed MiM evidence belongs to another or dirty build.')
    require(report.get('execution_id') == execution_id and re.fullmatch('[0-9a-f]{32}', execution_id), 'Stale MiM execution identity.')
    require(Path(report['executable']).resolve() == Path(executable).resolve() and report['executable_sha256'] == sha(executable),
            'Installed executable identity differs.')
    require(all(report.get(key) is False for key in ('qualified', 'release_ready', 'full_mim_installed')),
            'Bounded MiM subgate must not claim full qualification.')
    require(not report.get('errors') and not report.get('error'), 'Application reported errors.')


def check_runtime(root, report, bundle, backend, payload_hash):
    before = report['managed_runtime_before']; after = report['managed_runtime_after']
    require(before == after, 'Managed runtime changed during the probe.')
    payload = bundle/'icstudio/assets/runtime/digital'
    require(Path(before['payload_root']).resolve() == payload and
            Path(before['backend_root']).resolve() == payload/'backend/icstudio' and
            before['backend_files'] == backend, 'Managed backend is external or belongs to another candidate.')
    for phase in ('before', 'after'):
        folder = root/'runtime'/phase
        file_map(folder, before['files'])
        require(load(folder/'backend-files.json') == backend and sha(folder/'payload-manifest.json') == payload_hash,
                'Captured runtime payload/backend differs.')
    manifest = load(root/'runtime/before/payload-manifest.json')
    runtime = before['runtime']; records = load(root/'runtime/before/files.json')
    require(runtime['kind'] == ('wsl' if os.name == 'nt' else 'linux') and runtime['sha256'] == manifest['sha256'] and
            sha(root/'runtime/before/files.json') == manifest['files_sha256'] and
            load(root/'runtime/before/runtime.json')['files_sha256'] == manifest['files_sha256'], 'Runtime lock identity differs.')
    require({'magic', 'netgen', 'ngspice', 'klayout'} <= set(manifest['tools']), 'Included native tools are incomplete.')
    for name in ('magic', 'netgen'):
        key = 'opt/icstudio/bin/'+name
        require(key in records and re.fullmatch('[0-9a-f]{64}', records[key]), 'Runtime engine is not locked.')
        require(sha(Path(runtime['root'])/key) == records[key], 'Installed native engine differs from runtime lock.')
    return runtime, records


def mask_read(path, top):
    import klayout.db as db
    layout = db.Layout(); layout.read(str(path)); cell = layout.cell(top)
    require(layout.dbu == .001 and cell is not None and len(layout.top_cells()) == 1,
            'Written GDS units/top differ.')
    # Detach polygons before the owning Layout leaves scope; recursive regions
    # otherwise retain native references to a destroyed layout.
    masks = {}
    for i in layout.layer_indexes():
        region = db.Region(cell.begin_shapes_rec(i)).merged()
        masks[(layout.get_info(i).layer, layout.get_info(i).datatype)] = db.Region([p.dup() for p in region.each()])
    return masks


def same_masks(first, second):
    import klayout.db as db
    return all((first.get(k, db.Region()) ^ second.get(k, db.Region())).is_empty() for k in first.keys() | second.keys())


def geometry(folder, source_gds, top, plate, rotation, fault=False):
    """Read written masks and EXT tokens independently of the app normalizer."""
    import klayout.db as db
    source = mask_read(source_gds, top); original = mask_read(folder/'original.gds', top)
    written = mask_read(folder/'layout.gds', top)
    require(same_masks(original, written), 'Native verification changed physical masks.')
    if fault:
        expected = {k: v.dup() for k, v in source.items()}
        expected[(68, 20)] = expected.get((68, 20), db.Region()) + db.Region(db.Box(100000, 100000, 100100, 100100))
        require(same_masks(expected, written), 'Deliberate DRC defect differs from its declared narrow-metal edit.')
    else:
        require(same_masks(source, written), 'Queued native layout differs from saved GUI export.')
    cap, bottom, extension = ((89, 44), (70, 20), 3000) if plate == 1 else ((97, 44), (71, 20), 4500)
    other = (97, 44) if plate == 1 else (89, 44)
    caps = list(written.get(cap, db.Region()).each())
    require(len(caps) == 1 and caps[0].is_box() and written.get(other, db.Region()).is_empty(), 'Wrong MiM plate or electrode geometry.')
    box = caps[0].bbox()
    bottoms = [p for p in written.get(bottom, db.Region()).each() if (db.Region(caps[0])-db.Region(p)).is_empty()]
    require(len(bottoms) == 1, 'Ambiguous MiM bottom electrode.')
    extra = (bottoms[0].bbox().width()-box.width(), bottoms[0].bbox().height()-box.height())
    axis = 0 if extra[0] > extra[1] else 1
    require(sorted(extra) == [1000, extension] and axis == rotation//90 and
            (box.width(), box.height()) == ((2000, 10000) if rotation == 0 else (10000, 2000)),
            'Written electrode dimensions or orientation differ.')
    extraction = folder/'lvs-extraction'; proof = load(extraction/'mim-orientation.json')
    before = extraction/'native-original.ext'; after = extraction/(top+'.ext')
    require(proof['native_sha256'] == sha(before) and proof['corrected_sha256'] == sha(after) and
            proof['gds_sha256'] == sha(folder/'layout.gds') and proof['native_coordinate_nm'] in (5, 10),
            'Native orientation proof hashes/scale differ.')
    expected = []; seen = 0
    for line in before.read_text().splitlines(keepends=True):
        if line.startswith('device '):
            fields = shlex.split(line)
            require(fields[:3] == ['device', 'csubckt', f'sky130_fd_pr__cap_mim_m3_{plate}'], 'Unexpected native device record.')
            scale = proof['native_coordinate_nm']; site = db.Box(*(int(v)*scale for v in fields[3:7]))
            require(box.contains(site.p1) and box.contains(site.p2) and
                    [float(v.split('=')[1])*scale for v in fields[7:9]] == [box.width(), box.height()],
                    'Native EXT geometry differs from written electrode.')
            seen += 1
            if axis:
                line, n = re.subn(r'\bw=(\S+)(\s+)l=(\S+)', lambda m: 'w='+m[3]+m[2]+'l='+m[1], line)
                require(n == 1, 'Ambiguous native W/L swap.')
        expected.append(line)
    require(seen == 1 and ''.join(expected) == after.read_text(), 'Native normalization changed more than required W/L tokens.')


def native_scripts(folder, origin, technology, top):
    # Reuse the independent literal script contract, not the application's writer.
    # Import is lazy: the early unit lane does not require KLayout.
    from scripts.audit_sky130_mim_physical_case import execution_scripts
    expected = {name: text.replace('"device_coupon"', '"'+top+'"')
                for name, text in execution_scripts(origin, technology).items()}
    actual = {p.relative_to(folder).as_posix() for part in ('drc', 'lvs-extraction') for p in (folder/part).glob('*.tcl')}
    require(actual == set(expected), 'Native script coverage differs.')
    for name, text in expected.items():
        require((folder/name).read_text() == text, 'Native execution script differs: '+name)


def native_output(folder, native, plate, top, defect=False):
    stages = native['stages']
    require(tuple(s['name'] for s in stages) == STAGES, 'Native stages are missing, duplicated or reordered.')
    states = tuple(s['status'] for s in stages)
    require(states == ('passed', 'passed', 'failed' if defect else 'passed', 'passed', 'passed', 'passed') and
            native['status'] == ('failed' if defect else 'passed'), 'Native stage outcome differs.')
    stages = {s['name']: s for s in stages}
    require(native['drc_engine'] == native['lvs_extractor'] == 'magic' and native['magic_drc_style'] == 'drc(full)',
            'Native verification engine or full DRC style differs.')
    log = (folder/'drc/console.log').read_text()
    counts = re.findall(r'^STUDIO_DRC_COUNT (\d+)[ \t]*$', log, re.M)
    require(len(counts) == 1 and int(counts[0]) == native['drc_count'] == native['magic_drc_count'] and
            ((int(counts[0]) > 0) if defect else counts == ['0']) and
            re.findall(r'^STUDIO_DRC_STYLE (.+)$', log, re.M) == ['drc(full)'], 'Raw full DRC outcome differs.')
    require(bool((folder/'drc/findings.tsv').read_text().strip()) == defect, 'Raw DRC findings differ.')
    for name in ('drc/console.log', 'lvs-extraction/native-extraction.log', 'lvs-extraction/console.log'):
        text = (folder/name).read_text()
        require(re.findall(r'^(STUDIO_MAGIC_COMPLETE)[ \t]*$', text, re.M) == ['STUDIO_MAGIC_COMPLETE'] and
                not re.search(r'STUDIO_MAGIC_ERROR|contained errors|Malformed line|Illegal keyword|invalid command name', text, re.I),
                'Native engine did not complete: '+name)
    circuit((folder/'lvs-extraction/extracted.spice').read_text(), top, plate, extracted=True)
    lvs = (folder/'lvs/lvs.log').read_text()
    require(re.findall(r'^Final result: (.+)$', lvs, re.M) == ['Circuits match uniquely.'] and
            'Cell pin lists are equivalent.' in lvs and not re.search(
                r'Property errors|Circuits do not match|Netlists do not match|disconnected node:|\(no matching pin\)|pin lists[^\n]*altered', lvs, re.I),
            'Raw Netgen report does not establish a unique connected match.')
    extraction = stages['lvs_extraction']['evidence']
    require(extraction['deck'] == 'lvs-extraction/extracted.spice' and extraction['sha256'] == sha(folder/extraction['deck']) and
            extraction['settings'] == dict(hierarchy=True, blackbox=False, merge='none', scale=False,
                capacitance_threshold='infinite', resistance_threshold='infinite', distributed_resistance=False),
            'Native extraction settings or output binding differ.')
    require(stages['lvs']['evidence'] == dict(unique_match=True, log='lvs/lvs.log'), 'LVS receipt differs.')
    integrity = stages['integrity']['evidence']; file_map(folder, integrity['files'])
    require(integrity.get('verified') is True and {'layout.gds', 'input.icproj', 'schematic.spice', 'schematic-lvs.spice',
            'drc/console.log', 'lvs-extraction/extracted.spice', 'lvs/lvs.log'} <= integrity['files'].keys(),
            'Native integrity coverage is incomplete.')
    return stages


def physical_job(root, row, item, report, physical, runtime, runtime_files, defect=False):
    require(row['execution_id'] == report['execution_id'] and row['top'] == item['top'] and
            row['native_execution'] is True and row['state'] == 'Complete', 'Native case is stale or incomplete.')
    job_root = confined(root, row['job_directory']); folder = confined(root, row['evidence_directory'])
    require(folder == job_root/'physical-flow' and job_root.name == row['job_id'], 'Queued job directory identity differs.')
    require(sha(job_root/'input.json') == row['input_sha256'] and sha(job_root/'result.json') == row['result_sha256'],
            'Queued input/result changed.')
    job = load(job_root/'input.json'); result = load(job_root/'result.json')
    require(not result.get('reused_from') and result['silicon_report'] == row['report'] and result['settings'] == row['settings'] and
            design_hash(job['project']) == row['design_hash'] == result['design_hash'], 'Queued input/result binding differs.')
    settings = job['settings']
    require(settings['physical_toolchain'] == 'included' and settings['physical_runtime'] == runtime and
            settings['verification_mode'] == 'drc_lvs' and settings['drc_engine'] == settings['lvs_extractor'] == 'magic',
            'Queued job did not select the shipped physical runtime.')
    ref = settings['reference']; text = confined(root, item['reference']).read_text()
    require(ref == dict(text=text, top=item['top'], ports=['P', 'N'], sha256=hashlib.sha256(text.encode()).hexdigest()),
            'Queued schematic differs from GUI export.')
    execution = row['report']['execution']; native_job = load(job_root/'physical-backend-input.json')
    require(execution['runtime'] == runtime and sha(job_root/'physical-backend-input.json') == execution['native_input_sha256'],
            'Managed native input identity differs.')
    received = load(job_root/'physical-artifacts.json')
    require(execution['received_files'] == received, 'Received artifact inventory differs.')
    file_map(job_root, received)
    actual_received = {'physical-flow/'+name: value for name, value in inventory(folder).items()}
    actual_received['physical-backend-result.json'] = sha(job_root/'physical-backend-result.json')
    require(received == actual_received, 'Native transfer inventory omitted or added an artifact.')
    require({'physical-flow/report.json', 'physical-backend-result.json'} <= received.keys(), 'Missing native raw reports.')
    native = load(folder/'report.json'); backend_result = load(job_root/'physical-backend-result.json')
    require(backend_result['silicon_report'] == native and native['design_hash'] == design_hash(native_job['project']) and
            load(folder/'input.icproj') == native_job['project'] and native['cell_name'] == item['top'],
            'Native project/result belongs to another case.')
    expected_project = json.loads(json.dumps(job['project']))
    native_dir = execution['native_directory']; expected_project['pdk']['package_root'] = native_dir+'/pdk'
    require(native_job['project'] == expected_project and native_job['cell'] == job['cell'], 'Managed transfer changed project data.')
    lock = native_job['project']['pdk']['package_lock']
    require(lock == {k: physical[k] for k in ('id', 'revision', 'files')}, 'Native physical package lock differs.')
    stages = native_output(folder, native, item['plate'], item['top'], defect)
    for key in ('status', 'stages', 'reference', 'drc_count', 'mim_orientation'):
        require(row['report'][key] == native[key], 'Host report differs from raw native report: '+key)
    origin = native_dir+'/output/physical-flow'; technology = native_dir+'/pdk/libs.tech/magic/sky130A.tech'
    setup = native_dir+'/pdk/libs.tech/netgen/sky130A_setup.tcl'
    native_scripts(folder, origin, technology, item['top'])
    assets = {native_dir+'/pdk/'+name: value for name, value in physical['files'].items()
              if name.startswith(('libs.tech/magic/', 'libs.tech/netgen/'))}
    prefix = '/' if runtime['kind'] == 'wsl' else runtime['root'].rstrip('/')+'/'
    tools = {name: dict(path=prefix+'opt/icstudio/bin/'+name, sha256=runtime_files['opt/icstudio/bin/'+name])
             for name in ('magic', 'netgen')}
    for name in ('preflight', 'integrity'):
        require(stages[name]['evidence']['assets'] == assets and stages[name]['evidence']['tools'] == tools,
                'Native PDK/tool identity differs from selected installed runtime.')
    require((folder/'schematic.spice').read_text() == text, 'Native schematic reference was substituted.')
    circuit((folder/'schematic-lvs.spice').read_text(), item['top'], item['plate'])
    console = (folder/'lvs/console.log').read_text()
    require(re.findall(r'^Reading netlist file (.+)$', console, re.M) == [origin+'/schematic-lvs.spice', origin+'/lvs-extraction/extracted.spice'] and
            re.findall(r'^Reading setup file (.+)$', console, re.M) == [setup], 'Netgen used different native inputs/setup.')
    geometry(folder, confined(root, item['gds']), item['top'], item['plate'], item['rotation'], defect)
    proof = load(folder/'lvs-extraction/mim-orientation.json')
    require(native['mim_orientation'] == proof and proof['technology_sha256'] == physical['files']['libs.tech/magic/sky130A.tech'] and
            proof['pcell_sha256'] == physical['files']['libs.tech/magic/sky130A.tcl'], 'Orientation proof source binding differs.')
    return job_root


def audit(root, executable, physical_root, expected_commit, execution_id, inputs, backend, payload_hash):
    root = Path(root).resolve(); report = load(root/'report.json')
    header(report, executable, expected_commit, execution_id)
    bundle = Path(executable).resolve().parent/'_internal'
    require(Path(report['resource_root']).resolve() == bundle, 'App used external source resources.')
    require(sha(root/'files.json') == report['files_sha256'] and
            load(root/'files.json') == inventory(root, ('files.json', 'report.json')), 'Probe inventory is incomplete or changed.')
    current = package(bundle/'icstudio/assets/pdks/sky130A', inputs['package_sha256'])
    physical = package(physical_root, inputs['physical_sha256'])
    historical = package(root/'historical-package', OLD_MANIFEST)
    for name, expected in (('bundled-package.json', inputs['package_sha256']), ('bundled-collection.json', inputs['collection_sha256']),
                           ('physical-package.json', inputs['physical_sha256']), ('physical-release-lock.json', inputs['physical_lock_sha256'])):
        require(sha(root/name) == expected, 'Captured package/lock differs: '+name)
    require(report['bundled_package']['manifest_sha256'] == inputs['package_sha256'] and
            report['bundled_package']['files'] == current['files'] and report['physical_package']['files'] == physical['files'] and
            report['physical_package']['manifest_sha256'] == inputs['physical_sha256'] and
            Path(report['physical_package']['path']).resolve() == Path(physical_root).resolve(), 'Reported package inputs differ.')
    lifecycle(root, report, current, historical)
    runtime, runtime_files = check_runtime(root, report, bundle, backend, payload_hash)
    require([row.get('case') for row in report['physical']] == list(CASES), 'Incomplete or duplicated native layout cases.')
    jobs = []
    for row, item in zip(report['physical'], report['lifecycle']):
        jobs.append(physical_job(root, row, item, report, physical, runtime, runtime_files))
    controls = report['controls']
    require(len(controls) == 4 and controls[0].get('name') == 'stale-edit' and
            [v.get('case') for v in controls[1:]] == ['narrow-metal', 'repaired', 'missing-engine'], 'Missing fault/repair/block controls.')
    stale, defect, repaired, blocked = controls
    baseline = report['physical'][-1]['design_hash']
    require(stale['before_design_hash'] == baseline != repaired['design_hash'] == blocked['design_hash'] and
            stale['after_design_hash'] == defect['design_hash'] != baseline and stale['displayed'] is True,
            'Edit invalidation/undo identity differs.')
    jobs.append(physical_job(root, defect, report['lifecycle'][-1], report, physical, runtime, runtime_files, True))
    jobs.append(physical_job(root, repaired, report['lifecycle'][-1], report, physical, runtime, runtime_files))
    original_project = load(jobs[3]/'input.json')['project']; repaired_project = load(jobs[-1]/'input.json')['project']
    require(content_hash(original_project) == content_hash(repaired_project) == stale['before_content_hash'] == stale['repaired_content_hash'],
            'Undo changed design content beyond its new revision.')
    blocked_root = confined(root, blocked['job_directory']); blocked_result = load(blocked_root/'result.json')
    require(blocked['execution_id'] == execution_id and blocked['native_execution'] is False and
            sha(blocked_root/'input.json') == blocked['input_sha256'] and sha(blocked_root/'result.json') == blocked['result_sha256'] and
            blocked_result['silicon_report'] == blocked['report'] and blocked['report']['status'] == 'blocked' and
            [(s['name'], s['status']) for s in blocked['report']['stages']] ==
            [(name, 'failed' if name == 'preflight' else 'not_run') for name in STAGES] and
            not blocked['report'].get('execution') and not (blocked_root/'physical-artifacts.json').exists(),
            'Missing-engine control did not block before native execution.')
    blocked_job = load(blocked_root/'input.json')
    require(blocked_job['settings']['physical_toolchain'] == 'custom' and
            Path(blocked_job['settings']['tools']['magic']).resolve() == root/'missing-magic-executable' and
            not (root/'missing-magic-executable').exists() and design_hash(blocked_job['project']) == repaired['design_hash'],
            'Missing-engine control selected another executable/project.')
    require(len(set(jobs+[blocked_root])) == 7, 'Physical results reused a job directory.')
    return dict(schema=1, status='PASS', gate='mim-installed-gui-queued-layout', scope=SCOPE,
                qualified=False, release_ready=False, full_mim_installed=False, expected_commit=expected_commit,
                execution_id=execution_id, report_sha256=sha(root/'report.json'), files_sha256=sha(root/'files.json'),
                executable_sha256=sha(executable), package_inputs=inputs,
                counts=dict(lifecycle=4, binding_lifecycle=3, native_layouts=4, fresh_native_jobs=6, controls=4),
                runtime=runtime, backend_files_sha256=digest(backend))


def verify(executable, physical_pdk, out, expected_commit, timeout=2400):
    executable = unlinked(executable).resolve(); physical_pdk = unlinked(physical_pdk).resolve(); out = unlinked(out).resolve()
    require(re.fullmatch('[0-9a-f]{40}', expected_commit) and math.isfinite(timeout) and timeout > 0,
            'Choose an exact candidate and a positive finite deadline.')
    require(not out.exists(), 'Use a new output directory; existing evidence cannot qualify as fresh.')
    out.mkdir(parents=True); started = time.monotonic(); execution_id = uuid.uuid4().hex
    try:
        inputs = expected_inputs(expected_commit); bundle = executable.parent/'_internal'
        package(bundle/'icstudio/assets/pdks/sky130A', inputs['package_sha256'])
        package(physical_pdk, inputs['physical_sha256'])
        require(sha(bundle/'icstudio/assets/pdks/collection.json') == inputs['collection_sha256'], 'Bundled collection differs from candidate.')
        payload = bundle/'icstudio/assets/runtime/digital'
        payload_hash = sha(payload/'manifest.json'); manifest = load(payload/'manifest.json')
        require(manifest.get('schema') == 1 and manifest.get('archive') == 'runtime.tar.gz' and
                sha(payload/'runtime.tar.gz') == manifest['sha256'], 'Bundled runtime archive is missing or changed.')
        backend = backend_binding(payload/'backend/icstudio', expected_commit); exe_hash = sha(executable)
        env = git_environment()
        for key in ('PYTHONPATH', 'PYTHONHOME', 'ICSTUDIO_DIGITAL_PAYLOAD', 'ICSTUDIO_DIGITAL_NATIVE',
                    'ICSTUDIO_BUNDLED_NGSPICE', 'ICSTUDIO_NGSPICE', 'LD_LIBRARY_PATH'):
            env.pop(key, None)
        env['QT_QPA_PLATFORM'] = 'offscreen'
        if not env.get('ICSTUDIO_DIGITAL_STATE'):
            base = Path(env['LOCALAPPDATA']) if os.name == 'nt' else Path(env.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
            env['ICSTUDIO_DIGITAL_STATE'] = str(base/'ICDesignStudio/digital')
        command = [str(executable), '--mim-acceptance', '--mode', 'physical', '--managed',
                   '--physical-pdk', str(physical_pdk), '--execution-id', execution_id, '--out', str(out/'probe')]
        (out/'invocation.json').write_text(json.dumps(dict(command=command, expected_commit=expected_commit,
            execution_id=execution_id, executable_sha256=exe_hash, inputs=inputs, payload_manifest_sha256=payload_hash), indent=2))
        with (out/'launcher.log').open('wb') as log:
            subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=True)
        require(sha(executable) == exe_hash and sha(payload/'manifest.json') == payload_hash and
                backend_binding(payload/'backend/icstudio', expected_commit) == backend,
                'Installed executable/backend/payload changed during acceptance.')
        result = audit(out/'probe', executable, physical_pdk, expected_commit, execution_id, inputs, backend, payload_hash)
        result.update(seconds=time.monotonic()-started, timeout_seconds=timeout)
        (out/'verification.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
        return result
    except Exception as exc:
        if isinstance(exc, subprocess.TimeoutExpired):
            # Only the new probe's owned jobs may receive cooperative cancellation.
            for path in (out/'probe/runs with spaces').glob('*/*/input.json'):
                job = load(path)
                if job.get('settings', {}).get('physical_runtime'):
                    (path.parent/'digital-cancel').write_text('cancel\n')
        (out/'verification.json').write_text(json.dumps(dict(schema=1, status='FAIL', scope=SCOPE,
            qualified=False, release_ready=False, full_mim_installed=False, expected_commit=expected_commit,
            execution_id=execution_id, error=str(exc), seconds=time.monotonic()-started), indent=2)+'\n')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('executable', 'physical-pdk', 'out'):
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--timeout', type=float, default=2400)
    args = parser.parse_args()
    result = verify(args.executable, args.physical_pdk, args.out, args.expected_commit, args.timeout)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
