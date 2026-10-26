"""Selected whole-network MiM hierarchy integration; no family/signoff claim.

The historical imported project has geometry only. The application path is a
new, explicitly bound two-occurrence schematic counterpart. Historical native
extraction and the explicit hierarchical verification reference stay unchanged.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
import uuid
import zipfile

# An outside-repository candidate must explicitly select its reviewed base.
if '--source' in sys.argv:
    sys.path.insert(0, str(Path(sys.argv[sys.argv.index('--source')+1]).resolve()))
import icstudio
ROOT = Path(icstudio.__file__).resolve().parent.parent
CANDIDATE = Path(__file__).resolve().parents[1]
from icstudio.catalog import binding_for, create_device, parameter_values
from icstudio.engines import parse_raw
from icstudio.interchange import spice
from icstudio.model import clone, device, example, file_digest, load_project, save_project
from icstudio.testbenches import native_subcircuit
from scripts import installed_mim_inputs as identity
from scripts.qualify_standard_mos import load_technology, write
from scripts.qualify_sky130_mim_passive_corners import stage_models

SPEC = 'docs/qualification/sky130-mim-hierarchy-electrical-v2.json'
SECTIONS = ('tt', 'll', 'hh', 'hl', 'lh')
PORTS = ('p1', 'n1', 'p2', 'n2')
DELTA = 2**-16
PROFILES = {'e1': (1+DELTA, DELTA, -DELTA, -DELTA), 'e2': (DELTA, DELTA, 1-DELTA, -DELTA)}
PATHS = ('app', 'reference', 'native', 'cross', 'missing', 'width')
PARAMETERS = ('rm3', 'rm4', 'rcvia3', 'rcvia4', 'tol_m3', 'tol_m4',
              'camimc', 'cpmimc', 'm3_dw', 'm4_dw', 'mc_mm_switch', 'mc_pr_switch')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return file_digest(Path(path))


def load(path):
    return json.loads(Path(path).read_bytes())


def read_contract():
    spec = load(CANDIDATE / SPEC)
    require(spec['id'] == 'sky130-mim-hierarchy-electrical-v2', 'Wrong finite contract.')
    require(spec['profiles'] == {k: list(v) for k, v in PROFILES.items()}, 'Excitation contract differs.')
    for item in spec['base_contracts'].values():
        require(sha(ROOT/item['path']) == item['sha256'], 'Source contract changed.')
    require(sha(CANDIDATE/spec['predecessor']['path']) == spec['predecessor']['sha256'], 'Original failed-profile contract changed.')
    return spec


def selected(pilot=False):
    sections = ('tt',) if pilot else SECTIONS
    rotations = (0,) if pilot else (0, 90)
    return [dict(name=f'p{p}-r{r}-{s}', plate=p, rotation=r, section=s)
            for p in (1, 2) for r in rotations for s in sections]


def title(execution_root, nonce, case, profile):
    value = dict(execution_root=execution_root, nonce=nonce, case=case, profile=profile, analysis='ac')
    token = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return '* icstudio-mim-hierarchy-electrical-v2 ' + token


def original_members(archive):
    spec = read_contract()['physical_dependency']
    require(sha(archive) == spec['archive_sha256'], 'Unreviewed physical archive.')
    with zipfile.ZipFile(archive) as z:
        raw = z.read('manifest.json')
        require(hashlib.sha256(raw).hexdigest() == spec['manifest_sha256'], 'Archive manifest differs.')
        files = json.loads(raw)['files']
        selected_files = {k.removeprefix(spec['prefix']): v for k, v in files.items() if k.startswith(spec['prefix'])}
        require(len(selected_files) == spec['files'], 'Physical dependency coverage differs.')
        return selected_files


def restore_physical(archive, destination):
    """One complete historical readback dependency, never fresh physical output."""
    dest = Path(destination).resolve()
    require(not dest.exists(), 'Physical restore requires a fresh directory.')
    members = original_members(archive)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        for name, entry in members.items():
            require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Unsafe archive member.')
            data = z.read('objects/'+entry['sha256'])
            require(len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256'], 'Archive object mismatch.')
            target = dest/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    require(identity.inventory(dest) == {n: e['sha256'] for n, e in members.items()}, 'Incomplete physical restore.')
    return dict(path=str(dest), files=len(members), bytes=sum(e['bytes'] for e in members.values()),
                archive_sha256=sha(archive), prefix=read_contract()['physical_dependency']['prefix'])


def application(leaf, tech, folder):
    """Create a current-package schematic; retain and compare old binding explicitly."""
    old = load(leaf)
    old_cell = next(c for c in old['cells'] if c['id'] == old['top'])
    require(len(old_cell['devices']) == 1, 'Historical leaf is not one device.')
    original = old_cell['devices'][0]
    old_binding = binding_for(old['pdk'], original)
    p = example('empty'); p['pdk'] = clone(tech)
    child = p['cells'][0]; child.update(name='mim_leaf', ports=['P', 'N'])
    d = create_device(tech, original['model_ref']['device'], 'C1')
    d['nets'] = dict(c0='P', c1='N'); d['model_params'].update(w=2, l=10, mf=1)
    new_binding = binding_for(tech, d)
    for key in ('model', 'pin_order'):
        require(old_binding[key] == new_binding[key], 'Historical/current selected ABI differs: '+key)
    counterpart = read_contract()['counterpart']; plate = old_binding['model'][-1]
    require(old_binding['emit_parameters'] == counterpart['old_emit_parameters'][plate] and
            new_binding['emit_parameters'] == counterpart['new_emit_parameters'], 'Undeclared binding revision difference.')
    require(parameter_values(old_binding, original) == parameter_values(new_binding, d), 'Selected parameters changed.')
    require(original['nets'] == d['nets'] and original['symbol']['pin_order'] == d['symbol']['pin_order'], 'Original ordered interface changed.')
    child['devices'] = [d]
    parent = dict(id=uuid.uuid4().hex[:16], name='mim_pair', ports=[x.upper() for x in PORTS], shapes=[],
                  devices=[device('X', f'X{i}', cell=child['id'], nets={'P': f'P{i}', 'N': f'N{i}'}) for i in (1, 2)])
    p['cells'].append(parent); p['top'] = parent['id']
    folder.mkdir(parents=True)
    save_project(p, folder/'schematic.icproj')
    reopened = load_project(folder/'schematic.icproj')
    require(reopened == p, 'Schematic save/reopen changed project.')
    # Keep the actual hierarchical export as evidence of the two child calls.
    (folder/'hierarchical-export.spice').write_text(spice(reopened), encoding='utf-8', newline='\n')
    (folder/'application.spice').write_text(native_subcircuit(reopened, reopened['top']), encoding='utf-8', newline='\n')
    return dict(original_leaf_sha256=sha(leaf), old_model_ref=original['model_ref'], new_model_ref=d['model_ref'],
                old_binding=old_binding, current_binding=new_binding,
                project_sha256=sha(folder/'schematic.icproj'), application_sha256=sha(folder/'application.spice'),
                hierarchical_export_sha256=sha(folder/'hierarchical-export.spice'))


def native_graph(text, plate, fault=None):
    """Strict graph before any positive inclusion or deliberately mutated control."""
    rows = [s.split() for s in text.splitlines() if s.strip() and not s.lstrip().startswith('*')]
    require(rows[0] == ['.subckt', 'mim_pair', 'P1', 'N1', 'P2', 'N2'] and
            rows[-1] in (['.ends'], ['.ends', 'mim_pair']), 'Native four-port interface differs.')
    devices = rows[1:-1]
    require(len(devices) == (1 if fault == 'missing' else 2), 'Native occurrence count differs.')
    require(len({r[0].casefold() for r in devices}) == len(devices), 'Duplicate native instance.')
    expected = [('P1', 'N1', 2)]
    if fault != 'missing': expected.append(('P1' if fault == 'cross' else 'P2', 'N2', 3 if fault == 'width' else 2))
    actual = []
    for row in devices:
        require(row[0].lower().startswith('x') and row[3] == f'sky130_fd_pr__cap_mim_m3_{plate}', 'Native model changed.')
        pairs = [token.split('=') for token in row[4:]]
        require(all(len(a) == 2 for a in pairs) and len({a[0].lower() for a in pairs}) == len(pairs), 'Malformed native parameters.')
        values = {k.lower(): float(v) for k, v in pairs}
        require(set(values) in ({'w', 'l'}, {'w', 'l', 'm'}) and values['l'] == 10 and values.get('m', 1) == 1,
                'Native length/multiplicity differs.')
        actual.append((row[1], row[2], values['w']))
    require(sorted(actual) == sorted(expected), 'Native ordered occurrence graph/dimensions differ.')
    return devices


def mutated_native(text, plate, fault):
    require(fault in ('cross', 'missing', 'width'), 'Unknown negative control.')
    native_graph(text, plate)
    lines = text.splitlines(keepends=True)
    index = next(i for i, line in enumerate(lines) if re.match(r'^X\S+\s+P2\s+N2\s+', line))
    if fault == 'cross': lines[index] = re.sub(r'^(X\S+\s+)P2(\s+N2\s+)', r'\1P1\2', lines[index])
    elif fault == 'missing': del lines[index]
    else:
        lines[index], count = re.subn(r'(?i)(\bw\s*=\s*)2(?=\s|$)', r'\g<1>3', lines[index])
        require(count == 1, 'Ambiguous width mutation.')
    result = ''.join(lines); native_graph(result, plate, fault)
    return result


def deck(case, profile, networks, staged, execution_root, nonce):
    require(profile in PROFILES and set(networks) == set(PATHS), 'Unreviewed deck selection.')
    rows = [title(execution_root, nonce, case['name'], profile), staged,
            '.param mc_mm_switch=0 mc_pr_switch=0', '.option tnom=27', '.temp 27']
    saves = []
    for tag in PATHS:
        rows += [f'.subckt whole_{tag} P1 N1 P2 N2', f'.include "{Path(networks[tag]).as_posix()}"',
                 'Xwhole P1 N1 P2 N2 mim_pair', f'.ends whole_{tag}']
        for port, amplitude in zip(PORTS, PROFILES[profile]):
            rows.append(f'V_{tag}_{port} {tag}_{port} 0 DC 0 AC {amplitude:.17g}')
            saves += [f'v({tag}_{port})', f'i(v_{tag}_{port})']
        rows.append('X_'+tag+' '+' '.join(tag+'_'+p for p in PORTS)+' whole_'+tag)
    for name in PARAMETERS:
        rows.append(f'VPAR_{name} par_{name} 0 DC {{{name}}} AC {{{name}}}')
        saves.append(f'v(par_{name})')
    return '\n'.join(rows+['.ac dec 1 1k 10G', '.save '+' '.join(saves), '.end', ''])


def expected_rc(plate, coefficients, width=2):
    metal = plate+2; delta = 1e6*(coefficients[f'm{metal}_dw']+coefficients[f'tol_m{metal}'])
    w, l = width+delta, 10+delta
    capacitance = coefficients['camimc']*w*l+2*coefficients['cpmimc']*(w+l)
    resistance = coefficients[f'rm{metal}']*l/w+coefficients[f'rcvia{metal}']*(.56 if plate == 1 else .73)**2/(w*l)
    require(min(w, l, capacitance, resistance) > 0, 'Nonphysical source-defined RC.')
    return resistance, capacitance


def expected_currents(tag, voltages, frequency, plate, coefficients):
    """Current INTO complete network terminals, including each specified fault."""
    def y(w):
        r, c = expected_rc(plate, coefficients, w)
        return 1/(r+1/(2j*math.pi*frequency*c))
    p1, n1, p2, n2 = voltages
    first = (p1-n1)*y(2)
    if tag == 'missing': return (first, -first, 0j, 0j)
    second = ((p1 if tag == 'cross' else p2)-n2)*y(3 if tag == 'width' else 2)
    return (first+second, -first, 0j, -second) if tag == 'cross' else (first, -first, second, -second)


def observe(path, case, profile, coefficients, expected_title):
    raw = Path(path).read_bytes()
    titles = re.findall(rb'(?mi)^Title: *([^\r\n]*)', raw)
    require(titles == [expected_title.encode()], 'Raw execution/context identity differs.')
    names, rows, complex_data = parse_raw(path); names = [n.lower() for n in names]
    expected_names = {'frequency', *(f'{kind}({tag+"_"+port if kind == "v" else "v_"+tag+"_"+port})'
                       for tag in PATHS for port in PORTS for kind in ('v', 'i')),
                      *('v(par_'+name+')' for name in PARAMETERS)}
    require(complex_data and len(rows) == 8 and len(names) == len(expected_names) and set(names) == expected_names,
            'Raw channel/analysis/coverage differs.')
    expected_coeff = {**coefficients, 'mc_mm_switch': 0, 'mc_pr_switch': 0}
    observations = []; max_normalized = 0.0; detections = {k: False for k in ('cross', 'missing', 'width')}
    for index, row in enumerate(rows):
        values = dict(zip(names, row)); frequency = float(complex(values['frequency']).real)
        require(math.isfinite(frequency) and math.isclose(frequency, 10**(index+3), rel_tol=1e-10), 'Frequency grid differs.')
        for name, value in values.items():
            if name != 'frequency':
                z = complex(value); require(math.isfinite(z.real) and math.isfinite(z.imag), 'Nonfinite physical raw value.')
        for name in PARAMETERS:
            z = complex(values['v(par_'+name+')'])
            require(abs(z-expected_coeff[name]) <= 1e-24+abs(expected_coeff[name])*1e-10, 'Effective public coefficient differs: '+name)
        r, c = expected_rc(case['plate'], coefficients); admittance = 1/(r+1/(2j*math.pi*frequency*c))
        by_path = {}
        for tag in PATHS:
            volts = tuple(complex(values[f'v({tag}_{p})']) for p in PORTS)
            currents = tuple(-complex(values[f'i(v_{tag}_{p})']) for p in PORTS)
            require(all(abs(v-w) <= 1e-12 for v,w in zip(volts, PROFILES[profile])), 'Applied terminal stimulus differs.')
            expected = expected_currents(tag, volts, frequency, case['plate'], coefficients)
            bound = abs(admittance)*1e-6
            require(bound > 0, 'Zero comparison scale.')
            error = max(abs(a-b)/bound for a,b in zip(currents, expected)); max_normalized = max(max_normalized, error)
            require(error <= 1, 'Whole-network terminal response differs from source RC.')
            require(abs(sum(currents)) <= bound, 'Four-terminal KCL differs.')
            if tag in ('app', 'reference', 'native'):
                for occurrence in (0, 1):
                    a,b = 2*occurrence, 2*occurrence+1
                    require(abs(currents[a]+currents[b]) <= bound, 'Independent pair KCL differs.')
                    dv = volts[a]-volts[b]
                    if dv:
                        y = currents[a]/dv; impedance = 1/y
                        require(abs(y-admittance) <= abs(admittance)*1e-6 and
                                abs(impedance.real-r) <= r*1e-6 and
                                abs(-1/(2*math.pi*frequency*impedance.imag)-c) <= c*1e-6, 'Active pair Y/R/C differs.')
                    else: require(abs(currents[a]) <= bound, 'Off-diagonal pair response differs.')
            else:
                clean = expected_currents('native', volts, frequency, case['plate'], coefficients)
                detections[tag] |= any(abs(a-b) > bound for a,b in zip(currents, clean))
            by_path[tag] = dict(voltages=[[z.real,z.imag] for z in volts], currents=[[z.real,z.imag] for z in currents])
        observations.append(dict(frequency_hz=frequency, paths=by_path))
    return dict(samples=8, max_normalized_current_error=max_normalized, detections=detections, observations=observations)


def scope_check(report):
    require(report.get('mode') == 'source-integration' and all(report.get(k) is False for k in
        ('qualified', 'installed', 'release_ready', 'signoff', 'chunk_complete', 'full_family')),
        'Finite source integration cannot claim installed/family/signoff acceptance.')


def source_files():
    paths = [p for folder in ('icstudio', 'scripts') for p in (ROOT/folder).glob('*.py')]
    paths += [ROOT/p for p in ('docs/qualification/sky130-mim-contract-v1.json',
        'docs/qualification/sky130-mim-hierarchy-v1.json')]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}


def run(out, engine, physical, archive, auditor_source, *, pilot=False, workers=2):
    require(workers in (1,2,3,4), 'Select one to four workers.')
    require(sys.dont_write_bytecode and sys.pycache_prefix and not Path(sys.pycache_prefix).exists(),
            'Use -B with a nonexistent pycache prefix.')
    out = identity.gui.unlinked(out).resolve(); physical = identity.gui.unlinked(physical).resolve()
    require(not out.exists() and not any(c.isspace() for c in str(out)), 'Use a fresh, whitespace-free output path.')
    out.mkdir(parents=True); started=time.monotonic(); spec=read_contract()
    execution_root=out.as_posix(); nonce=uuid.uuid4().hex
    report=dict(schema=1, gate=spec['id'], mode='source-integration', status='RUNNING', execution_root=execution_root,
                nonce=nonce, qualified=False, installed=False, release_ready=False, signoff=False,
                chunk_complete=False, full_family=False, cases=[], scope=spec['scope'], pilot=pilot)
    scope_check(report)
    try:
        members=original_members(archive)
        require(identity.inventory(physical) == {n:e['sha256'] for n,e in members.items()}, 'Historical physical restore differs.')
        from scripts import audit_sky130_mim_hierarchy as physical_reader
        require(sha(physical_reader.__file__) == spec['physical_dependency']['physical_auditor_sha256'],
                'Historical physical reader changed.')
        proof=physical_reader.audit(physical, reviewed_source=physical/'source'); write(out/'physical-readback.json',proof)
        report['physical_dependency']={**spec['physical_dependency'], 'restored_root':str(physical),
            'readback_sha256':sha(out/'physical-readback.json'), 'original_execution_root':load(physical/'qualification.json')['execution_root']}
        (out/'contract.json').write_bytes((CANDIDATE/SPEC).read_bytes())
        sources=source_files(); write(out/'source-files.json',sources)
        for name,digest in sources.items():
            p=out/'source'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
            require(sha(p)==digest,'Source changed during capture.')
        candidate_paths=[Path(__file__), CANDIDATE/SPEC, CANDIDATE/spec['predecessor']['path'], CANDIDATE/'tests/test_sky130_mim_hierarchy_electrical.py']
        candidate_paths += [Path(auditor_source)/p for p in
            ('scripts/audit_sky130_mim_hierarchy_electrical.py','tests/test_sky130_mim_hierarchy_electrical_audit.py')]
        candidate_sources={}
        for p in candidate_paths:
            require(p.is_file(),'Missing reviewed candidate source: '+str(p)); data=p.read_bytes()
            relative=p.parent.name+'/'+p.name
            if p.suffix=='.json': relative='docs/qualification/'+p.name
            dest=out/'candidate'/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
            candidate_sources[relative]=dict(path=str(p),sha256=sha(p))
        write(out/'candidate-files.json',candidate_sources)
        tech,process=load_technology('sky130A'); package=Path(tech['package_root']); package_files={'package.json':sha(package/'package.json'),**tech['package_lock']['files']}
        require(package_files['package.json']==spec['simulation_package']['manifest_sha256'],'Unreviewed simulation package.')
        staged,model_files=stage_models(tech,out);write(out/'model-files.json',model_files)
        (out/'contract-sources').mkdir();(out/'contract-sources/package').write_bytes((package/'package.json').read_bytes())
        report['simulation_package']=dict(revision=tech['package_lock']['revision'],manifest_sha256=package_files['package.json'])
        report['applications']={}
        for p in (1,2):report['applications'][str(p)]=application(physical/f'p{p}/leaf.icproj',tech,out/f'applications/p{p}')
        cases=selected(pilot);report['selected_cases']=[c['name'] for c in cases];report['full_declared_cases']=[c['name'] for c in selected()]
        bindings={}
        for case in cases:
            key=f'p{case["plate"]}-r{case["rotation"]}'
            if key in bindings:continue
            native=physical/f'p{case["plate"]}/r{case["rotation"]}/physical/lvs-extraction/extracted.spice'
            reference=physical/f'p{case["plate"]}/r{case["rotation"]}/physical/schematic.spice'
            native_graph(native.read_text(),case['plate']); folder=out/'networks'/key;folder.mkdir(parents=True)
            networks=dict(app=out/f'applications/p{case["plate"]}/application.spice',native=native,reference=reference)
            for fault in ('cross','missing','width'):
                networks[fault]=folder/(fault+'.spice');networks[fault].write_text(mutated_native(native.read_text(),case['plate'],fault),encoding='utf-8',newline='\n')
            bindings[key]={tag:dict(path=str(path),sha256=sha(path)) for tag,path in networks.items()}
        report['network_bindings']=bindings
        engine=identity.checked_path(engine);binding=dict(mode='source-pilot');env=identity.native_environment(binding,engine,out)
        before=identity.runtime(binding,engine,env);write(out/'runtime-before.json',before);assets={}
        for name,digest in {**before['files'],**{v['resolved']:v['sha256'] for v in before['elf_dependencies'].values()}}.items():
            target=out/'runtime-assets'/digest;target.parent.mkdir(exist_ok=True)
            if not target.exists():target.write_bytes(Path(name).read_bytes())
            require(sha(target)==digest,'Runtime capture differs.');assets[name]=digest
        write(out/'runtime-assets.json',assets)
        report.update(contract_sha256=sha(out/'contract.json'),source_root=str(ROOT),source_files_sha256=sha(out/'source-files.json'),
            candidate_files_sha256=sha(out/'candidate-files.json'),runtime_before_sha256=sha(out/'runtime-before.json'),
            python=dict(executable=sys.executable,sha256=sha(sys.executable),version=sys.version,dont_write_bytecode=sys.dont_write_bytecode,pycache_prefix=sys.pycache_prefix))
        original=load(ROOT/spec['base_contracts']['electrical']['path'])
        def one(case):
            row={**case,'status':'RUNNING','profiles':{}};folder=out/case['name'];folder.mkdir()
            try:
                networks={k:Path(v['path']) for k,v in bindings[f'p{case["plate"]}-r{case["rotation"]}'].items()}
                for profile in PROFILES:
                    dest=folder/profile;dest.mkdir();text=deck(case,profile,networks,staged[case['section']],execution_root,nonce)
                    (dest/'input.cir').write_text(text,encoding='utf-8',newline='\n')
                    command=[str(engine),'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(dest/'result.raw'),str(dest/'input.cir')]
                    result=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=90)
                    log=result.stdout+result.stderr;(dest/'console.log').write_text(log,encoding='utf-8')
                    invocation=dict(command=command,cwd=str(out),environment=env,returncode=result.returncode)
                    write(dest/'invocation.json',invocation)
                    require(result.returncode==0 and 'error' not in log.lower() and 'unknown parameter' not in log.lower(),'Native simulation failed.')
                    raw=observe(dest/'result.raw',case,profile,original['passive_sections'][case['section']]['coefficients'],title(execution_root,nonce,case['name'],profile))
                    row['profiles'][profile]=dict(raw=raw,deck_sha256=sha(dest/'input.cir'),raw_sha256=sha(dest/'result.raw'),
                        log_sha256=sha(dest/'console.log'),invocation_sha256=sha(dest/'invocation.json'))
                require(all(any(row['profiles'][p]['raw']['detections'][f] for p in PROFILES) for f in ('cross','missing','width')),
                        'Required fault was not detected across independent excitations.')
                row['status']='PASS'
            except Exception:row.update(status='FAIL',error=traceback.format_exc())
            write(folder/'record.json',row);return row
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for task in as_completed([pool.submit(one,c) for c in cases]):
                row=task.result();report['cases'].append(row);write(out/'qualification.json',report);print(row['name'],row['status'],flush=True)
        require(len(report['cases'])==len(cases) and all(c['status']=='PASS' for c in report['cases']),'Native cases failed.')
        after=identity.runtime(binding,engine,env);write(out/'runtime-after.json',after)
        require(before==after,'Runtime changed during execution.')
        require(identity.inventory(physical)=={n:e['sha256'] for n,e in members.items()},'Retained original physical evidence changed.')
        require(all(sha(ROOT/n)==d for n,d in sources.items()),'Reviewed base source changed.')
        require(all(sha(e['path'])==e['sha256'] for e in candidate_sources.values()),'Candidate source changed.')
        require(all(sha(package/n)==d for n,d in package_files.items()),'Simulation package changed.')
        require(all(sha(out/'shared-models'/n)==d for n,d in model_files.items()),'Staged model changed.')
        require(all(sha(v['path'])==v['sha256'] for b in bindings.values() for v in b.values()),'Positive or fault network changed.')
        report.update(status='PASS',source_integration_acceptance=True,runtime_after_sha256=sha(out/'runtime-after.json'),
                      guards=dict(source=True,candidate=True,package=True,models=True,runtime=True,physical=True,networks=True))
    except Exception:report.update(status='FAIL',error=traceback.format_exc())
    report['cases'].sort(key=lambda c:c['name']);report['seconds']=time.monotonic()-started
    scope_check(report);write(out/'qualification.json',report);write(out/'manifest.json',identity.inventory(out,('manifest.json',)))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--physical',type=Path,required=True);p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--auditor-source',type=Path,required=True)
    p.add_argument('--ngspice',type=Path,required=True);p.add_argument('--pilot',action='store_true');p.add_argument('--workers',type=int,default=2)
    a=p.parse_args();require(a.source.resolve()==ROOT,'Reviewed source import root differs.')
    result=run(a.out,a.ngspice,a.physical,a.archive,a.auditor_source,pilot=a.pilot,workers=a.workers)
    print(json.dumps(dict(status=result['status'],seconds=result['seconds']),indent=2))
    if result['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()
