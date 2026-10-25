"""Fresh GUI/native bindings for selected installed metal-resistor acceptance.

No numerical acceptance decision lives here. Source pilots cannot claim an
installed candidate, and installed runs cannot select a host/PATH simulator.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import installed_mim_inputs as common

require, sha, load, inventory, write = common.require, common.sha, common.load, common.inventory, common.write
checked_path, native_environment, runtime = common.checked_path, common.native_environment, common.runtime
candidate_sources = common.candidate_sources
CONTRACT = 'docs/qualification/sky130-metal-installed-v1.json'
CONTRACT_SHA = '9245943194baf0fca698b9487b962390d2dc2af07983e19d0b493ae21f952fa2'


def contracts(binding=None):
    require(sha(ROOT/CONTRACT) == CONTRACT_SHA, 'Installed resistor contract changed.')
    installed = load(ROOT/CONTRACT); source = installed['source_contract']
    require(sha(ROOT/source['path']) == source['sha256'], 'Original formula contract changed.')
    spec = load(ROOT/source['path']); checked = {}
    for name, row in spec['sources'].items():
        path = ROOT/name
        if binding is not None:
            prefix = spec['package']['path']+'/'
            path = (Path(binding['simulation_package']['path'])/name[len(prefix):]
                    if name.startswith(prefix) else Path(binding['resource_root'])/name)
        require(sha(checked_path(path)) == row['sha256'], 'Reviewed source/model changed: '+name)
        checked[name] = dict(path=str(path.resolve()), sha256=row['sha256'])
    if binding is not None:
        require(binding['simulation_package']['manifest_sha256'] == spec['package']['manifest_sha256'],
                'Selected simulation package is outside the reviewed contract.')
    return installed, spec, checked


def expected_cases(installed):
    gui = installed['gui']
    return [f'{m}-g{g}-r{r}' for m in gui['models'] for g in range(len(gui['geometries_um'])) for r in gui['rotations']]


def bind_gui(path, expected_commit=None, *, source_pilot=False):
    from scripts import verify_frozen_metal_resistors as gui
    supplied = gui.unlinked(path).resolve(); root = supplied if source_pilot else supplied/'probe'
    report = load(root/'report.json'); installed, spec, _ = contracts()
    require(report.get('schema') == 1 and report.get('status') == 'passed' and report.get('mode') == 'physical'
            and report.get('native_execution') is True and not report.get('error') and not report.get('errors'),
            'Completed fresh physical GUI acceptance is required.')
    require(all(report.get(k) is False for k in ('qualified','release_ready','installed_acceptance','full_family')),
            'GUI prerequisite overstates its scope.')
    nonce = report.get('execution_id', '')
    require(isinstance(nonce,str) and re.fullmatch('[0-9a-f]{32}',nonce), 'GUI nonce missing.')
    cases = expected_cases(installed)
    require([v.get('case') for v in report['lifecycle']] == cases and [v.get('case') for v in report['physical']] == cases,
            'All thirty current GUI/native cases are required.')
    require(sha(root/'files.json') == report['files_sha256'] and
            load(root/'files.json') == inventory(root, ('files.json','report.json')), 'GUI evidence inventory changed.')
    package_root = gui.unlinked(report['bundled_package']['path']).resolve()
    current = gui.package(package_root, spec['package']['manifest_sha256'])
    if source_pilot:
        require(expected_commit is None and report.get('frozen') is False and report['build'].get('frozen') is False,
                'Source pilot cannot relabel installed acceptance.')
        gui.source_audit(root)
    else:
        require(re.fullmatch('[0-9a-f]{40}',expected_commit or ''), 'Select an exact installed candidate.')
        receipt, invocation = load(supplied/'verification.json'), load(supplied/'invocation.json')
        require(receipt.get('status') == 'PASS' and receipt.get('gate') == 'metal-resistor-installed-gui-queued-layout'
                and receipt.get('expected_commit') == invocation.get('expected_commit') == expected_commit
                and receipt.get('execution_id') == invocation.get('execution_id') == nonce,
                'Frozen GUI verification is missing or stale.')
        executable = checked_path(report['executable']); bundle = executable.parent/'_internal'
        require(package_root == bundle/'icstudio/assets/pdks/sky130A', 'Package lies outside installation.')
        inputs = gui.expected_inputs(expected_commit); payload = bundle/'icstudio/assets/runtime/digital'
        backend = gui.backend_binding(payload/'backend/icstudio', expected_commit)
        actual = gui.audit(root, executable, Path(report['physical_package']['path']), expected_commit,
                           nonce, inputs, backend, sha(payload/'manifest.json'))
        require(all(receipt.get(k) == v for k,v in actual.items()), 'Frozen verification no longer re-audits.')
        require(invocation['payload_manifest_sha256'] == sha(payload/'manifest.json') and invocation['inputs'] == inputs
                and invocation['executable_sha256'] == sha(executable), 'Original frozen invocation changed.')
    require(sha(package_root.parent/'collection.json') == report['bundled_package']['collection_sha256'], 'Collection changed.')
    records = {}
    for item, physical in zip(report['lifecycle'],report['physical']):
        require(physical['case'] == item['case'] and physical['top'] == item['top'] and physical['execution_id'] == nonce,
                'GUI/native case identity changed.')
        native = gui.confined(root,physical['evidence_directory'])/'lvs-extraction/extracted.spice'
        files = {name:str(gui.confined(root,item[name])) for name in ('project','reference','schematic','gds')}
        files['native'] = str(checked_path(native))
        require(item['native'] == str(native) and item['native_sha256'] == sha(native)
                and item['native_job_id'] == physical['job_id'], 'Fresh extraction binding differs.')
        records[item['case']] = {k:item[k] for k in ('model','geometry_index','width_um','length_um','rotation','multiplicity','top')}
        records[item['case']].update(job_id=physical['job_id'],job_directory=physical['job_directory'],
            input_sha256=physical['input_sha256'],result_sha256=physical['result_sha256'],design_hash=physical['design_hash'],
            files=files,hashes={name:sha(value) for name,value in files.items()})
    return dict(schema=1,mode='source-pilot' if source_pilot else 'installed',gui_root=str(root),supplied_root=str(supplied),
        expected_commit=expected_commit,execution_id=nonce,report_sha256=sha(root/'report.json'),files_sha256=sha(root/'files.json'),
        verification_sha256=None if source_pilot else sha(supplied/'verification.json'),
        invocation_sha256=None if source_pilot else sha(supplied/'invocation.json'),
        application=dict(path=report['executable'],sha256=report['executable_sha256'],build=report['build']),
        resource_root=report['resource_root'],simulation_package=dict(path=str(package_root),revision=current['revision'],
            manifest_sha256=sha(package_root/'package.json'),collection_sha256=sha(package_root.parent/'collection.json')),
        engine_discovery=report['simulation_engine_discovery'],cases=records)


def select_engine(binding, source_engine=None):
    engine = common.select_engine(binding, source_engine)
    installed, _, _ = contracts(binding)
    require(sys.platform in installed['runtime_profiles'] and sha(engine) == installed['runtime_profiles'][sys.platform]['sha256'],
            'Unreviewed selected native simulator.')
    return engine


def technology(binding):
    return common.technology(binding)


def apply_edits(data, edits):
    result = data
    for item in reversed(sorted(edits,key=lambda v:v['start'])):
        require(data[item['start']:item['stop']] == item['before'].encode(), 'Mutation span changed.')
        result = result[:item['start']]+item['after'].encode()+result[item['stop']:]
    return result


def normalize_top(data, top):
    """Change only the unique .subckt and optional named .ends tokens."""
    require(re.fullmatch('[A-Za-z][A-Za-z0-9_]*',top or '') is not None, 'Invalid exported top name.')
    text = data.decode('utf-8')
    header = list(re.finditer(r'(?im)^[ \t]*\.subckt[ \t]+(\S+)[ \t]+R1[ \t]+R2[ \t]*\r?$',text))
    ending = list(re.finditer(r'(?im)^[ \t]*\.ends(?:[ \t]+(\S+))?[ \t]*\r?$',text))
    directives = re.findall(r'(?im)^[ \t]*(\.[^ \t\r\n]+)',text)
    require(len(header)==len(ending)==1 and header[0].group(1)==top and ending[0].group(1) in (None,top)
            and [v.lower() for v in directives]==['.subckt','.ends'], 'Unexpected original subcircuit interface/directives.')
    edits=[]
    for match in (header[0],ending[0]):
        if match.group(1) is not None:
            edits.append(dict(start=len(text[:match.start(1)].encode()),stop=len(text[:match.end(1)].encode()),before=top,after='coupon'))
    result=apply_edits(data,edits)
    return result,dict(kind='top-subcircuit-name-only',original_top=top,normalized_top='coupon',edits=edits,
        original_sha256=hashlib.sha256(data).hexdigest(),normalized_sha256=hashlib.sha256(result).hexdigest())


def resistor_tokens(data, row, *, application):
    text=data.decode('utf-8'); devices=[m for m in re.finditer(r'(?m)^([^\r\n]*)',text)
        if m[1].strip() and not m[1].lstrip().startswith(('*','.'))]
    require(len(devices)==1, 'Expected one original resistor and no other devices.')
    line=devices[0]; tokens=list(re.finditer(r'\S+',line[1])); values=[m[0] for m in tokens]
    require(len(values)==(7 if application else 6) and re.fullmatch(r'R\S+',values[0],re.I)
            and set(values[1:3])=={'R1','R2'} and values[3]=='sky130_fd_pr__res_generic_'+row['model'],
            'Unexpected original resistor model/terminals.')
    parameters={}
    for value in values[4:]:
        require(re.fullmatch(r'[wlm]=[0-9.eE+-]+',value) is not None, 'Unreviewed resistor parameter grammar.')
        key,value=value.split('=');require(key not in parameters, 'Duplicate resistor parameter.')
        parameters[key]=float(value);require(math.isfinite(parameters[key]), 'Nonfinite resistor parameter.')
    require(parameters==dict(w=row['width_um'],l=row['length_um'],**({'m':1.0} if application else {})), 'Original dimensions/multiplicity differ.')
    spans=[]
    for m in tokens:
        start=line.start(1)+m.start();stop=line.start(1)+m.end()
        spans.append(dict(start=len(text[:start].encode()),stop=len(text[:stop].encode()),before=m[0]))
    return values,spans


def fault_copy(data, row, fault):
    values,spans=resistor_tokens(data,row,application=True)
    require(fault in ('wrong-width','wrong-length','wrong-model','wrong-multiplicity','disconnected-terminal'), 'Unknown electrical fault.')
    if fault=='wrong-model': index=3; replacement='sky130_fd_pr__res_generic_'+('m3' if row['model'] in ('m1','m2') else 'm1')
    elif fault=='disconnected-terminal': index=values.index('R1');replacement='0'
    else:
        key={'wrong-width':'w','wrong-length':'l','wrong-multiplicity':'m'}[fault]
        index=next(i for i,v in enumerate(values) if v.startswith(key+'='))
        replacement=key+'='+format(float(values[index].split('=')[1])*(2 if key=='m' else 1.2),'.17g')
    edit={**spans[index],'after':replacement};result=apply_edits(data,[edit])
    return result,dict(kind=fault,edits=[edit],original_sha256=hashlib.sha256(data).hexdigest(),mutated_sha256=hashlib.sha256(result).hexdigest())


def source_files():
    paths={ROOT/CONTRACT,ROOT/load(ROOT/CONTRACT)['source_contract']['path'],ROOT/'docs/SKY130_METAL_INSTALLED_ACCEPTANCE.md'}
    paths.update(ROOT/name for name in load(ROOT/load(ROOT/CONTRACT)['source_contract']['path'])['sources'])
    paths.update(p for p in (ROOT/'docs/qualification/ngspice42-metal-reference').rglob('*') if p.is_file())
    # Runtime staging can add a generated nested backend under assets; its
    # identity is already checked by the GUI/runtime binding, not Git sources.
    paths.update(p for p in (ROOT/'icstudio').glob('*.py') if p.name!='build_info.py')
    paths.update((ROOT/'scripts').glob('*.py'))
    paths.update(ROOT/'tests'/n for n in ('test_installed_metal_resistor_inputs.py','test_installed_metal_resistors.py',
        'test_installed_metal_resistors_audit.py','test_installed_metal_resistors_aggregate.py','test_frozen_metal_resistors.py',
        'test_metal_resistor_desktop_probe.py'))
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)}
