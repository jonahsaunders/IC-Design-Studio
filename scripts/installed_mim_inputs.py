"""Input/runtime bindings for the bounded installed MiM electrical check.

This module supplies no electrical acceptance decision. Source pilots remain
explicitly distinct from frozen GUI acceptance; no historical runtime is reused.
"""
import hashlib
import json
import copy
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import verify_frozen_mim as gui

require, sha, load, inventory = gui.require, gui.sha, gui.load, gui.inventory
CONTRACT_PATH = 'docs/qualification/sky130-mim-contract-v1.json'
CONTRACT_SHA = 'b324813599a364c83e76e63f583e7b74da50ab8182640a1cb907796a3ce1c209'
MAP_PATH = 'docs/qualification/sky130-mim-bias-source-map-v1.json'
MAP_SHA = '549bb89580245515b5a7e2b43eb784fcfd3d621a57ff3141c10183da42c87830'
CURRENT_PACKAGE = '125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b'
PREVIOUS_PACKAGE = '840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe'
CURRENT_CONTRACT_PATH = 'docs/qualification/sky130-mim-contract-v2.json'
CURRENT_CONTRACT_SHA = '81ab3c10b2b12aa89c0b69cc92787a4ea4144215a6f0875ffca2c18aa39b4454'
CURRENT_MAP_PATH = 'docs/qualification/sky130-mim-bias-source-map-v2.json'
CURRENT_MAP_SHA = '188ca9fe7dd57bf823ded56910a0b840f6ab239f6c7f1070703329fe3cb2e6d3'


def write(path, value):
    from icstudio.model import atomic_write
    atomic_write(path, json.dumps(value, indent=2, allow_nan=False)+'\n')


def checked_path(path):
    path = gui.unlinked(path).resolve()
    require(path.is_file(), 'Missing ordinary input file: '+str(path))
    return path


def _source_gui(root, report, current):
    require(report.get('frozen') is False and report['build'].get('frozen') is False,
            'Source pilot must not relabel frozen acceptance.')
    historical = gui.package(root/'historical-package', gui.OLD_MANIFEST)
    gui.lifecycle(root, report, current, historical)
    for item, row in zip(report['lifecycle'], report['physical']):
        require(row['case'] == item['case'] and row['top'] == item['top'] and row['execution_id'] == report['execution_id'] and
                row['state'] == 'Complete' and row['native_execution'] is True, 'Source native case identity differs.')
        job = gui.confined(root, row['job_directory']); folder = gui.confined(root, row['evidence_directory'])
        require(folder == job/'physical-flow' and sha(job/'input.json') == row['input_sha256'] and
                sha(job/'result.json') == row['result_sha256'], 'Source native job differs.')
        result = load(job/'result.json'); native = load(folder/'report.json')
        require(not result.get('reused_from') and result['silicon_report'] == row['report'] == native and
                native['cell_name'] == item['top'], 'Source native result differs.')
        gui.native_output(folder, native, item['plate'], item['top'])
        gui.geometry(folder, gui.confined(root, item['gds']), item['top'], item['plate'], item['rotation'])
        require((folder/'schematic.spice').read_bytes() == gui.confined(root, item['reference']).read_bytes(),
                'Source native reference differs from fresh GUI export.')


def bind_gui(path, expected_commit=None, *, source_pilot=False):
    """Re-audit live GUI prerequisites and retain original paths and identities."""
    supplied = gui.unlinked(path).resolve()
    root = supplied if source_pilot else supplied/'probe'
    report = load(root/'report.json')
    require(report.get('schema') == 1 and report.get('status') == 'passed' and report.get('mode') == 'physical' and
            report.get('native_execution') is True and not report.get('error') and not report.get('errors'),
            'A completed physical GUI probe is required.')
    require(all(report.get(k) is False for k in ('qualified', 'release_ready', 'full_mim_installed')),
            'GUI prerequisite overstates its scope.')
    nonce = report.get('execution_id', '')
    require(isinstance(nonce, str) and re.fullmatch('[0-9a-f]{32}', nonce), 'Missing GUI execution identity.')
    require([r.get('case') for r in report['lifecycle']] == list(gui.CASES) and
            [r.get('case') for r in report['physical']] == list(gui.CASES), 'Four fresh GUI/native inputs are required.')
    require(sha(root/'files.json') == report['files_sha256'] and
            load(root/'files.json') == inventory(root, ('files.json', 'report.json')), 'GUI evidence inventory changed.')
    package_root = gui.unlinked(report['bundled_package']['path']).resolve()
    current = gui.package(package_root, report['bundled_package']['manifest_sha256'])
    receipt = None
    if source_pilot:
        require(expected_commit is None, 'Source pilots cannot claim an installed candidate.')
        _source_gui(root, report, current)
    else:
        require(isinstance(expected_commit, str) and re.fullmatch('[0-9a-f]{40}', expected_commit), 'Select an exact installed candidate.')
        receipt = load(supplied/'verification.json'); invocation = load(supplied/'invocation.json')
        require(receipt.get('status') == 'PASS' and receipt.get('gate') == 'mim-installed-gui-queued-layout' and
                receipt.get('expected_commit') == expected_commit and invocation.get('expected_commit') == expected_commit and
                receipt.get('execution_id') == nonce == invocation.get('execution_id'), 'Frozen GUI verification is missing or stale.')
        executable = checked_path(report['executable']); bundle = executable.parent/'_internal'
        require(package_root == bundle/'icstudio/assets/pdks/sky130A', 'Simulation package is outside the selected installation.')
        inputs = gui.expected_inputs(expected_commit)
        payload = bundle/'icstudio/assets/runtime/digital'
        backend = gui.backend_binding(payload/'backend/icstudio', expected_commit)
        actual = gui.audit(root, executable, Path(report['physical_package']['path']), expected_commit, nonce,
                           inputs, backend, sha(payload/'manifest.json'))
        require(all(receipt.get(k) == v for k, v in actual.items()), 'Frozen GUI verification no longer re-audits.')
        require(invocation['payload_manifest_sha256'] == sha(payload/'manifest.json') and invocation['inputs'] == inputs and
                invocation['executable_sha256'] == sha(executable), 'Original frozen invocation differs.')
    require(sha(package_root.parent/'collection.json') == report['bundled_package']['collection_sha256'], 'Collection changed.')
    records = {}
    for item, row in zip(report['lifecycle'], report['physical']):
        native = gui.confined(root, row['evidence_directory'])/'lvs-extraction/extracted.spice'
        files = {name: str(gui.confined(root, item[name])) for name in ('project', 'reference', 'schematic', 'gds')}
        files['native'] = str(checked_path(native))
        for kind in ('native', 'reference'):
            gui.circuit(Path(files[kind]).read_text(), item['top'], item['plate'], extracted=kind == 'native')
        records[item['case']] = dict(plate=item['plate'], rotation=item['rotation'], top=item['top'],
            job_id=row['job_id'], job_directory=row['job_directory'], input_sha256=row['input_sha256'],
            result_sha256=row['result_sha256'], design_hash=row['design_hash'], files=files,
            hashes={name: sha(value) for name, value in files.items()})
    return dict(schema=1, mode='source-pilot' if source_pilot else 'installed', gui_root=str(root), supplied_root=str(supplied),
        expected_commit=expected_commit, execution_id=nonce, report_sha256=sha(root/'report.json'),
        files_sha256=sha(root/'files.json'), verification_sha256=None if source_pilot else sha(supplied/'verification.json'),
        invocation_sha256=None if source_pilot else sha(supplied/'invocation.json'),
        application=dict(path=report['executable'], sha256=report['executable_sha256'], build=report['build']),
        resource_root=report['resource_root'], simulation_package=dict(path=str(package_root), revision=current['revision'],
            manifest_sha256=sha(package_root/'package.json'), collection_sha256=sha(package_root.parent/'collection.json')),
        engine_discovery=report['simulation_engine_discovery'], cases=records)


def selected_contracts(binding):
    """Select only an explicit reviewed package/contract tuple."""
    selected=binding['simulation_package']['manifest_sha256']
    if selected==PREVIOUS_PACKAGE:return CONTRACT_PATH,CONTRACT_SHA,MAP_PATH,MAP_SHA
    if selected==CURRENT_PACKAGE:return CURRENT_CONTRACT_PATH,CURRENT_CONTRACT_SHA,CURRENT_MAP_PATH,CURRENT_MAP_SHA
    raise ValueError('Installed package is outside the reviewed electrical contract.')


def current_derivation(contract,mapping,package_root):
    """Prove v2 changes only package provenance, preserving all v1 criteria."""
    require(sha(ROOT/CONTRACT_PATH)==CONTRACT_SHA and sha(ROOT/MAP_PATH)==MAP_SHA,'Historical MiM contracts changed.')
    original,old_map=load(ROOT/CONTRACT_PATH),load(ROOT/MAP_PATH)
    package=checked_path(package_root/'package.json');manifest=load(package)
    require(sha(package)==CURRENT_PACKAGE and manifest['revision']=='5dda725c94efe3c2','Current MiM package identity differs.')
    require(contract['id']=='sky130-mim-contract-v2' and contract['package']=={'revision':'5dda725c94efe3c2','manifest_sha256':CURRENT_PACKAGE},'Current contract package differs.')
    require(contract['derivation']=={'predecessor_contract':CONTRACT_PATH,'predecessor_contract_sha256':CONTRACT_SHA,'change':'Only selected package identity and manifest byte count change; MiM catalog entries and mapped package assets remain byte-identical. Historical source baseline and scientific criteria are unchanged.','new_execution':False,'qualified':False},'Current contract provenance differs.')
    expected_package=copy.deepcopy(original['sources']['package']);expected_package.update(sha256=CURRENT_PACKAGE,bytes=package.stat().st_size)
    require(contract['sources']['package']==expected_package,'Current contract package source differs.')
    c=copy.deepcopy(contract);c.pop('derivation');c['id']=original['id'];c['package']=original['package'];c['sources']['package']=original['sources']['package']
    require(c==original,'Current MiM scientific contract differs from history.')
    require(mapping['id']=='sky130-mim-voltage-source-review-20261029-v2' and mapping['immutable_contract']=={'path':CURRENT_CONTRACT_PATH,'sha256':CURRENT_CONTRACT_SHA,'unchanged':True},'Current source-map contract differs.')
    require(mapping['derivation']=={'predecessor_map':MAP_PATH,'predecessor_map_sha256':MAP_SHA,'change':'Update only selected contract, exact package metadata, and manifest line coordinates; original source evidence and scientific criteria remain unchanged.','new_execution':False,'qualified':False},'Current source-map provenance differs.')
    expected_row=copy.deepcopy(old_map['sources']['package']);expected_row.update(sha256=CURRENT_PACKAGE,bytes=package.stat().st_size,lines=[[3757,3801],[3961,4006]])
    require(mapping['sources']['package']==expected_row,'Current source-map package differs.')
    m=copy.deepcopy(mapping);m.pop('derivation');m['id']=old_map['id'];m['immutable_contract']=old_map['immutable_contract'];m['sources']['package']=old_map['sources']['package']
    require(m==old_map,'Current MiM source map differs from history.')


def contracts(binding):
    contract_path,contract_sha,map_path,map_sha=selected_contracts(binding)
    require(sha(ROOT/contract_path) == contract_sha and sha(ROOT/map_path) == map_sha, 'Reviewed MiM contracts changed.')
    contract, mapping = load(ROOT/contract_path), load(ROOT/map_path)
    resources = Path(binding['resource_root']); package_root = Path(binding['simulation_package']['path'])
    if contract_path==CURRENT_CONTRACT_PATH:current_derivation(contract,mapping,package_root)
    prefix = 'icstudio/assets/pdks/sky130A/'
    checked = {}
    for name, item in mapping['sources'].items():
        if 'path' not in item:
            continue  # Historical extraction identities remain historical; fresh GUI outputs are bound separately.
        relative = item['path']
        if name == 'orientation_adapter':
            # The immutable map records historical application corroboration.
            # Current shape support is bound to the candidate's shipped backend
            # and independently checked fresh native inputs, not that old hash.
            require(relative == 'icstudio/sky130_mim2_extract.py' and item.get('scope', '').startswith('Application corroboration only;'),
                    'Unexpected historical application source classification.')
            path = (resources/'icstudio/assets/runtime/digital/backend'/relative if binding['mode']=='installed' else ROOT/relative)
            checked[name] = dict(path=str(checked_path(path)), sha256=sha(path), historical_sha256=item['sha256'],
                                 role='current_candidate_application_with_historical_corroboration_recorded_separately')
            continue
        path = package_root/relative[len(prefix):] if relative.startswith(prefix) else resources/relative
        if not path.is_file() and binding['mode'] == 'source-pilot':
            path = ROOT/relative
        require(sha(checked_path(path)) == item['sha256'], 'Reviewed model/source identity changed: '+name)
        checked[name] = dict(path=str(path.resolve()), sha256=item['sha256'])
    require(binding['simulation_package']['manifest_sha256'] == contract['sources']['package']['sha256'],
            'Installed package is outside the reviewed electrical contract.')
    return contract, checked


def technology(binding):
    path = Path(binding['simulation_package']['path'])
    package = gui.package(path, binding['simulation_package']['manifest_sha256'])
    tech = json.loads(json.dumps(package['technology']))
    tech.update(package_root=str(path), package_lock={k: package[k] for k in ('id', 'revision', 'files')})
    return tech


def select_engine(binding, source_engine=None):
    if binding['mode'] == 'source-pilot':
        require(source_engine is not None, 'Source pilot requires an explicit native engine.')
        return checked_path(source_engine)
    require(source_engine is None, 'Installed acceptance forbids a source/custom simulator override.')
    name = 'ngspice.exe' if os.name == 'nt' else 'ngspice'
    engine = checked_path(Path(binding['resource_root'])/'icstudio/assets/runtime/ngspice'/name)
    discovery = binding['engine_discovery']
    require(Path(discovery['path']).resolve() == engine and discovery['sha256'] == sha(engine) and
            discovery.get('executed') is False, 'Selected engine differs from the installed application discovery.')
    return engine


def native_environment(binding, engine, output):
    """Allowlisted child environment, matching packaged scalar initializer/loader."""
    engine, output = Path(engine), Path(output)
    env = dict(LANG='C', LC_ALL='C', TZ='UTC', HOME=str(output/'empty-home'), USERPROFILE=str(output/'empty-home'),
               TMP=str(output/'temporary'), TEMP=str(output/'temporary'))
    for folder in ('empty-home', 'temporary'):
        (output/folder).mkdir(exist_ok=True)
    if os.name == 'nt':
        system = os.environ.get('SystemRoot', r'C:\Windows')
        env.update(SystemRoot=system, WINDIR=system, PATH=str(engine.parent)+os.pathsep+str(Path(system)/'System32'))
    else:
        env['PATH'] = str(engine.parent)+':/usr/bin:/bin'
        if binding['mode'] == 'installed':
            env['LD_LIBRARY_PATH'] = binding['resource_root']
    if (engine.parent/'spinit').is_file():
        env['SPICE_SCRIPTS'] = str(engine.parent)
    elif binding['mode'] == 'source-pilot' and Path('/usr/share/ngspice/scripts/spinit').is_file():
        env['SPICE_SCRIPTS'] = '/usr/share/ngspice/scripts'
    else:
        raise ValueError('No explicit simulator initializer is available.')
    require(not any(k.upper().startswith('GIT_') or k.upper() in ('ICSTUDIO_NGSPICE', 'ICSTUDIO_BUNDLED_NGSPICE',
            'PYTHONPATH', 'PYTHONHOME', 'LD_PRELOAD') for k in env), 'Forbidden native environment override.')
    return env


def runtime(binding, engine, env):
    """Capture actual engine/config/bundle and ELF libraries; not a hermetic OS claim."""
    engine = checked_path(engine)
    files = {str(engine): sha(engine)}
    roots = [engine.parent] if binding['mode'] == 'installed' or os.name == 'nt' else []
    if binding['mode'] == 'source-pilot' and os.name != 'nt':
        roots += [p for p in (Path('/usr/share/ngspice'), Path('/usr/lib/x86_64-linux-gnu/ngspice')) if p.is_dir()]
    for root in roots:
        for name, digest in inventory(root).items():
            files[str(root/name)] = digest
    initializer = Path(env['SPICE_SCRIPTS'])/'spinit'
    files[str(initializer)] = sha(initializer)
    if os.name == 'nt':
        from icstudio.runtime_setup import verify_runtime_files
        verify_runtime_files(engine.parent)
    libraries = {}; ldd_output = None
    if sys.platform == 'linux':
        require(engine.read_bytes()[:4] == b'\x7fELF', 'Linux acceptance requires the actual ELF engine, not a wrapper.')
        preload = Path('/etc/ld.so.preload')
        require(not preload.exists() or not preload.read_text().strip(), 'Unreviewed system preload is present.')
        result = subprocess.run(['/usr/bin/ldd', str(engine)], env=env, capture_output=True, text=True, timeout=30)
        require(result.returncode == 0 and 'not found' not in result.stdout+result.stderr, 'Native library resolution failed.')
        ldd_output = re.sub(r'\(0x[0-9a-fA-F]+\)', '(address)', result.stdout+result.stderr)
        for value in sorted(set(re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(', ldd_output, re.M))):
            path = Path(value)
            libraries[value] = dict(resolved=str(path.resolve()), sha256=sha(path))
        require(bool(libraries), 'Native ELF dependency closure is missing.')
        for path in (Path('/usr/bin/ldd'), Path('/etc/ld.so.cache')):
            files[str(path)] = sha(path)
    version = subprocess.run([str(engine), '--version'], env=env, capture_output=True, text=True, timeout=30)
    require(version.returncode == 0 and 'ngspice' in (version.stdout+version.stderr).lower(), 'Simulator version probe failed.')
    return dict(engine=str(engine), sha256=sha(engine), platform=sys.platform, machine=platform.machine(),
        environment=env, files=files, elf_dependencies=libraries, ngspice_version=version.stdout+version.stderr,
        dependency_listing=ldd_output, scope='Engine, adjacent packaged runtime/configuration and resolved ELF dependencies when Linux; not a hermetic full-OS closure.')


def source_files(binding=None):
    scripts = ('installed_mim_inputs.py', 'qualify_installed_sky130_mim_electrical.py',
        'audit_installed_sky130_mim_electrical.py', 'verify_frozen_mim.py', 'qualify_standard_mos.py',
        'qualify_standard_mos_layout.py', 'qualify_sky130_mim2.py', 'qualify_sky130_mim_orientation.py',
        'qualify_sky130_mim_passive_corners.py', 'qualify_sky130_mim_bias_boundaries.py',
        'audit_sky130_mim_bias_boundaries.py', 'audit_sky130_mim_passive_corners.py',
        'audit_sky130_mim_orientation.py', 'audit_sky130_mim_physical_case.py')
    paths = [p for p in (ROOT/'icstudio').glob('*.py') if p.name != 'build_info.py']
    paths += [ROOT/'scripts'/name for name in scripts]
    if binding is not None and selected_contracts(binding)[0] == CURRENT_CONTRACT_PATH:
        paths += [ROOT/CONTRACT_PATH,ROOT/MAP_PATH,ROOT/CURRENT_CONTRACT_PATH,ROOT/CURRENT_MAP_PATH]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}


def candidate_sources(files, commit):
    require(re.fullmatch('[0-9a-f]{40}', commit or ''), 'Missing immutable source candidate.')
    requests = [commit+':'+gui.relative(name) for name in files]
    result = subprocess.run(['git', 'cat-file', '--batch'], cwd=ROOT, env=gui.git_environment(),
                            input=('\n'.join(requests)+'\n').encode(), stdout=subprocess.PIPE, check=True).stdout
    offset = 0
    for name, expected in files.items():
        end = result.index(b'\n', offset); header = result[offset:end].split()
        require(len(header) == 3 and header[1] == b'blob', 'Missing candidate source: '+name)
        size = int(header[2]); data = result[end+1:end+1+size]; offset = end+size+2
        require(hashlib.sha256(data).hexdigest() == expected, 'External checker source differs from candidate: '+name)
