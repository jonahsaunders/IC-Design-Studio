"""Selected +/-5 V MiM integration with retained physical inputs and fresh OP/AC.

Linear public-model agreement is not leakage, breakdown, reliability, silicon,
full operating-envelope or release qualification. Native geometry is reused
under its original identity; this runner executes only fresh electrical cases.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import sysconfig
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.engines import execute, ngspice_command, parse_raw
from icstudio.model import atomic_write, file_digest
from icstudio.testbenches import native_subcircuit
from scripts.qualify_standard_mos import load_technology, write
from scripts.qualify_sky130_mim2 import fixture, independent, audit_native
from scripts.qualify_sky130_mim_passive_corners import PARAMETERS, SECTIONS, SIZE, renamed, stage_models, expected_rc
from scripts.audit_sky130_mim_passive_corners import audit as audit_retained

MAP_PATH = 'docs/qualification/sky130-mim-bias-source-map-v1.json'
MAP_SHA = '549bb89580245515b5a7e2b43eb784fcfd3d621a57ff3141c10183da42c87830'
CONTRACT_PATH = 'docs/qualification/sky130-mim-contract-v1.json'
CONTRACT_SHA = 'b324813599a364c83e76e63f583e7b74da50ab8182640a1cb907796a3ce1c209'
ARCHIVE_SHA = '03a75a194d165ed5fad0486f5a9a1fec0a5daa7c751c23f72beb9a17c031d430'
ENGINE = '/var/tmp/icstudio-ngspice-capacitor-build-20261017-v2/installed/bin/icstudio-ngspice'
LAUNCHER_SHA = '4c38c46c06cbe65d4111e392b93fd0b4a09250bd7f93bb3eed8f8f0af2bddcc9'
PATHS = ('schematic', 'extracted', 'independent')
PROBES = (*PARAMETERS, 'mc_mm_switch', 'mc_pr_switch')
BIAS_NAMES = {-5: 'm5', 0: '0', 5: 'p5'}
EMPTY_HOME = '/__icstudio_mim_bias_no_home__'
EMPTY_CACHE = '/__icstudio_mim_bias_no_bytecode__'
ENV = {'PATH': '/opt/icstudio/bin:/usr/bin:/bin', 'HOME': EMPTY_HOME,
       'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC', 'PYTHONNOUSERSITE': '1',
       'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONHASHSEED': '0'}


def checked_bias(value):
    value = float(value)
    if not math.isfinite(value) or abs(value) > 5:
        raise ValueError('Bias outside the declared finite +/-5 V integration domain.')
    return value


def selected(plates, sections, rotations, biases):
    for values, allowed in ((plates, (1, 2)), (sections, SECTIONS), (rotations, (0, 90)), (biases, tuple(BIAS_NAMES))):
        if not values or len(set(values)) != len(values) or any(v not in allowed for v in values):
            raise ValueError('Selections must be distinct, nonempty declared cases.')
    return [(p, s, r, checked_bias(b)) for p in plates for s in sections for r in rotations for b in biases]


def case_name(plate, section, rotation, bias):
    return f'p{plate}-{section}-r{rotation}-b{BIAS_NAMES[bias]}'


def domain_controls():
    result = []
    for value in ('-5.001', '5.001', 'nan', 'inf', '-inf'):
        try: checked_bias(value)
        except ValueError as error: result.append(dict(request=value, status='REJECTED', error=str(error)))
        else: raise ValueError('Out-of-domain bias accepted: ' + value)
    return result


def faults(bias):
    return (('missing-bias', 'sign-reversed', 'clamped-bias') if bias else ()) + ('displaced-ground',)


def applied(bias, fault=None):
    if fault == 'missing-bias': return 0.0, 0.0
    if fault == 'sign-reversed': return -bias, 0.0
    if fault == 'clamped-bias': return math.copysign(4.99, bias), 0.0
    if fault == 'displaced-ground': return bias, .5
    if fault is not None: raise ValueError('Unknown bias fault.')
    return bias, 0.0


def context_title(execution_root, case, analysis, fault=None):
    identity = dict(execution_root=str(execution_root), case=case, analysis=analysis, fault=fault or 'positive')
    token = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    return '* icstudio-mim-bias-v1 ' + token


def require_raw_title(path, expected):
    if re.findall(r'^Title:[ \t]*(.*)$', Path(path).read_text(encoding='utf-8'), re.M) != [expected]:
        raise ValueError('Native raw context identity differs from the executed case.')


def circuit(tech, plate, native, staged, bias, analysis, fault=None, *, execution_root, case):
    checked_bias(bias)
    if analysis not in ('op', 'ac') or (fault and (analysis != 'op' or fault not in faults(bias))):
        raise ValueError('Unknown analysis or inapplicable bias fault.')
    audit_native(native, SIZE, plate)
    project = fixture(tech, SIZE, plate)
    high, low = applied(bias, fault)
    text = context_title(execution_root, case, analysis, fault) + '\n' + staged + '\n'
    text += '.param mc_mm_switch=0 mc_pr_switch=0\n.option tnom=27\n.temp 27\n'
    text += renamed(native_subcircuit(project, project['top']), 'schematic') + '\n'
    text += renamed(independent(SIZE, plate=plate), 'independent') + '\n'
    text += f'.include {native.as_posix()}\n'
    for key in PATHS:
        dc = '' if fault == 'missing-bias' else f'DC {high:g} '
        text += f'VP_{key} p_{key} 0 {dc}AC 1\nVN_{key} n_{key} 0 DC {low:g} AC 0\n'
        text += f'X_{key} p_{key} n_{key} ' + ('device_coupon' if key == 'extracted' else key) + '\n'
    for key in PROBES:
        text += f'VPAR_{key} par_{key} 0 DC {{{key}}} AC {{{key}}}\n'
    saves = [f'{kind}({prefix}_{key})' for key in PATHS for kind, prefix in (('v','p'), ('v','n'), ('i','vp'), ('i','vn'))]
    saves += [f'v(par_{key})' for key in PROBES]
    text += ('.op\n' if analysis == 'op' else '.ac dec 1 1k 10G\n')
    text += '.save ' + ' '.join(saves) + '\n.end\n'
    return project, text


def raw_values(path, analysis):
    text = Path(path).read_text(encoding='utf-8')
    if re.findall(r'^Plotname:\s*(.+)$', text, re.M) != ['Operating Point' if analysis == 'op' else 'AC Analysis']:
        raise ValueError('Expected exactly one declared native plot.')
    names, rows, is_complex = parse_raw(path)
    names = [name.lower() for name in names]
    channels = {f'{kind}({prefix}_{key})' for key in PATHS for kind, prefix in (('v','p'), ('v','n'), ('i','vp'), ('i','vn'))}
    channels |= {f'v(par_{key})' for key in PROBES}
    if analysis == 'ac': channels.add('frequency')
    if len(names) != len(channels) or set(names) != channels or is_complex != (analysis == 'ac') or len(rows) != (8 if is_complex else 1):
        raise ValueError('Incomplete, duplicated or unexpected raw analysis channels/points.')
    for row in rows:
        if len(row) != len(names) or any(not math.isfinite(complex(value).real) or
                (name != 'frequency' and not math.isfinite(complex(value).imag)) for name, value in zip(names, row)):
            raise ValueError('Nonfinite or incomplete raw sample.')
    return [dict(zip(names, row)) for row in rows]


def coefficients_read(values, coefficients):
    saved = {}
    for key in PROBES:
        value = complex(values[f'v(par_{key})']); expected = coefficients.get(key, 0.0)
        if abs(value - expected) > 1e-24 + 1e-10 * abs(expected):
            raise ValueError('Wrong effective coefficient/switch: ' + key)
        saved[key] = value.real
    return saved


def measure_op(path, bias, coefficients, ground=0.0):
    values = raw_values(path, 'op')[0]
    params = coefficients_read(values, coefficients)
    paths = {}
    for key in PATHS:
        high, low = values[f'v(p_{key})'], values[f'v(n_{key})']
        top_current, bottom_current = values[f'i(vp_{key})'], values[f'i(vn_{key})']
        if max(abs(high - bias), abs(low - ground), abs((high - low) - (bias - ground))) > 1e-9:
            raise ValueError('Actual signed OP terminal voltage differs from the intended bias: ' + key)
        if max(abs(top_current), abs(bottom_current), abs(top_current + bottom_current)) > 1e-12:
            raise ValueError('Ideal compact-model DC current/KCL differs; this is not a leakage specification.')
        paths[key] = dict(p_V=high, n_V=low, differential_V=high-low, i_p_A=top_current, i_n_A=bottom_current)
    return dict(status='PASS', coefficients=params, paths=paths, raw_sha256=file_digest(path))


def measure_ac(path, plate, coefficients):
    resistance, capacitance = expected_rc(plate, coefficients)
    samples = []
    for index, values in enumerate(raw_values(path, 'ac')):
        frequency = values['frequency'].real
        if not math.isclose(frequency, 1e3 * 10 ** index, rel_tol=1e-12): raise ValueError('Wrong AC frequency.')
        params = coefficients_read(values, coefficients)
        target = 1 / (resistance + 1 / (2j * math.pi * frequency * capacitance))
        paths = {}
        for key in PATHS:
            high, low = values[f'v(p_{key})'], values[f'v(n_{key})']
            ip, inn = values[f'i(vp_{key})'], values[f'i(vn_{key})']
            if abs(high - 1) > 1e-12 or abs(low) > 1e-12 or abs(ip + inn) > 1e-24 + 1e-9 * abs(ip):
                raise ValueError('AC source normalization or KCL differs.')
            value = -ip / (high - low)
            if value.real <= 0 or value.imag <= 0: raise ValueError('Nonpassive or noncapacitive response.')
            measured_r = (1 / value).real
            measured_c = -1 / (2 * math.pi * frequency * (1 / value).imag)
            error = max(abs(value / target - 1), abs(measured_r / resistance - 1), abs(measured_c / capacitance - 1))
            if error > 1e-6: raise ValueError('Source-fixed analytical RC differs: ' + key)
            paths[key] = dict(Y_S=[value.real, value.imag], R_ohm=measured_r, C_F=measured_c, relative_error=error)
        samples.append(dict(frequency_Hz=frequency, paths=paths))
    return dict(status='PASS', coefficients=params, expected_R_ohm=resistance, expected_C_F=capacitance,
                samples=samples, raw_sha256=file_digest(path))


def execute_case(tech, plate, section, rotation, bias, native, staged, coefficients, out, engine):
    folder = out / case_name(plate, section, rotation, bias); folder.mkdir()
    row = dict(name=folder.name, plate=plate, section=section, rotation=rotation, bias_V=bias,
               status='RUNNING', native_path=str(native), native_sha256=file_digest(native), analyses={}, controls=[])
    def run(analysis, fault=None):
        dest = folder / ('controls/' + fault if fault else analysis); dest.mkdir(parents=True)
        project, text = circuit(tech, plate, native, staged[section], bias, analysis, fault,
                                execution_root=out, case=folder.name)
        deck, raw = dest / 'probe.cir', dest / 'probe.raw'
        atomic_write(deck, text)
        command = ngspice_command(project, engine, raw, deck)
        log = execute(command, dest, timeout=90, env=ENV)
        atomic_write(dest / 'console.log', log)
        require_raw_title(raw, context_title(out, folder.name, analysis, fault))
        high, low = applied(bias, fault)
        result = measure_op(raw, high, coefficients, low) if analysis == 'op' else measure_ac(raw, plate, coefficients)
        result.update(deck_sha256=file_digest(deck), command=command, cwd=str(dest), environment=ENV)
        if fault:
            try: measure_op(raw, bias, coefficients)
            except ValueError as error: result.update(fault=fault, detected=True, intended_bias_V=bias, applied_bias_V=high, applied_ground_V=low, rejection=str(error))
            else: raise ValueError('Wrong bias was not detected: ' + fault)
        return result
    try:
        for analysis in ('op', 'ac'): row['analyses'][analysis] = run(analysis)
        for fault in faults(bias): row['controls'].append(run('op', fault))
        row['status'] = 'PASS'
    except Exception as error:
        row.update(status='FAIL', error=repr(error), traceback=traceback.format_exc())
    write(folder / 'record.json', row)
    return row


def restore_physical(archive, out, source_map):
    if file_digest(archive) != ARCHIVE_SHA: raise ValueError('Unexpected immutable physical archive.')
    dest = out / 'retained-native'; dest.mkdir()
    bindings = {}
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            if not item.filename.startswith('accepted/native/') or item.is_dir(): continue
            relative = item.filename.removeprefix('accepted/native/')
            path = dest / relative
            if not path.resolve().is_relative_to(dest.resolve()) or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Unsafe archived native member.')
            data = z.read(item); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            bindings[relative] = dict(member=item.filename, sha256=file_digest(path), bytes=len(data))
    result = audit_retained(dest)
    if result['status'] != 'PASS' or result['counts']['cases'] != 20: raise ValueError('Original physical/electrical receipt did not re-audit.')
    for item in source_map['retained_native_inputs'].values():
        relative = item['member'].removeprefix('accepted/native/')
        if bindings[relative]['sha256'] != item['sha256']: raise ValueError('Retained native extraction differs from reviewed mapping.')
    original = json.loads((dest / 'qualification.json').read_bytes())
    return dict(status='PASS', physical_execution='historical_reuse_no_new_physical_run', archive_sha256=ARCHIVE_SHA,
                member_prefix='accepted/native/', original_execution_root=original['execution_root'],
                original_qualification_sha256=file_digest(dest / 'qualification.json'), original_manifest_sha256=file_digest(dest / 'manifest.json'),
                audit=result, bindings=bindings)


def file_identity(path):
    path = Path(path)
    if not path.exists(): return dict(absent=True)
    return dict(sha256=file_digest(path), bytes=path.stat().st_size, resolved=str(path.resolve()))


def tree_identity(root):
    root = Path(root)
    if not root.exists(): return {'$root': dict(absent=True)}
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            if (Path(directory) / name).is_symlink(): raise ValueError('Unreviewed runtime directory symlink.')
        for name in files:
            path = Path(directory) / name
            result[path.relative_to(root).as_posix()] = file_identity(path)
    return result


def runtime(engine):
    if sys.platform != 'linux' or platform.machine() != 'x86_64' or str(engine) != ENGINE or file_digest(engine) != LAUNCHER_SHA:
        raise ValueError('Use the reviewed Linux x86_64 ngspice launcher for this bounded milestone.')
    if not sys.dont_write_bytecode or sys.pycache_prefix != EMPTY_CACHE or Path(EMPTY_CACHE).exists() or Path(EMPTY_HOME).exists():
        raise ValueError('Use -B and an absent -X pycache_prefix=' + EMPTY_CACHE + '; keep the empty-home sentinel absent.')
    if sys.flags.hash_randomization or not sys.flags.no_user_site:
        raise ValueError('Start with PYTHONHASHSEED=0 and PYTHONNOUSERSITE=1.')
    installed=Path(ENGINE).parent.parent
    fixed = [Path(engine), installed/'bin/ngspice', Path('/bin/sh'), Path('/usr/bin/dirname'), Path('/usr/bin/ldd'),
             Path(sys.executable), Path('/etc/ld.so.cache'), Path('/etc/ld.so.preload'), Path('/etc/os-release'), Path(sys.prefix) / 'pyvenv.cfg']
    if Path('/etc/ld.so.preload').exists() and Path('/etc/ld.so.preload').read_text().strip(): raise ValueError('Unreviewed preloaded runtime.')
    roots = [installed, Path(sysconfig.get_path('stdlib')), Path(sysconfig.get_path('purelib'))]
    for value in sys.path:
        path=Path(value or os.getcwd()).absolute()
        if path.is_relative_to(ROOT): continue
        if not (path.is_relative_to('/usr') or path.is_relative_to(sys.prefix)):
            raise ValueError('Unreviewed Python import root: '+str(path))
        if path.is_dir(): roots.append(path)
        else: fixed.append(path)
    roots = sorted(set(roots)); roots = [p for p in roots if not any(p != q and p.is_relative_to(q) for q in roots)]
    for module in tuple(sys.modules.values()):
        value = getattr(module, '__file__', None)
        if value and Path(value).is_file() and not Path(value).resolve().is_relative_to(ROOT): fixed.append(Path(value))
    dependencies = {}
    for path in sorted(set(fixed)):
        if not path.is_file() or path.read_bytes()[:4] != b'\x7fELF': continue
        proc = subprocess.run(['/usr/bin/ldd', str(path)], env=ENV, capture_output=True, text=True, timeout=30)
        if proc.returncode or 'not found' in proc.stdout + proc.stderr: raise ValueError('Unresolved runtime library: ' + str(path))
        libraries = re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(', proc.stdout, re.M)
        dependencies[str(path)] = {p: file_identity(p) for p in sorted(set(libraries))}
    version = subprocess.run([str(engine), '--version'], env=ENV, capture_output=True, text=True, timeout=30)
    if version.returncode: raise ValueError('Simulator version query failed.')
    return dict(profile='linux-x86_64-capacitor-ngspice-mim-bias-v1', native_environment=ENV,
                launcher_environment=dict(SPICE_LIB_DIR=str(installed/'share/ngspice'),
                    SPICE_SCRIPTS=str(installed/'share/ngspice/scripts'), ICSTUDIO_SPICE_MODELS=str(installed/'lib/ngspice')),
                python=sys.version, python_flags=repr(sys.flags), python_cache_prefix=sys.pycache_prefix,
                sys_path=sys.path, platform=platform.platform(), ngspice_version=version.stdout + version.stderr,
                files={str(path):file_identity(path) for path in sorted(set(fixed))},
                trees={str(path):tree_identity(path) for path in roots}, elf_dependencies=dependencies)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ngspice', type=Path, default=Path(ENGINE))
    parser.add_argument('--plates', nargs='+', type=int, default=[1,2])
    parser.add_argument('--sections', nargs='+', default=list(SECTIONS))
    parser.add_argument('--rotations', nargs='+', type=int, default=[0,90])
    parser.add_argument('--biases', nargs='+', type=float, default=[-5,0,5])
    parser.add_argument('--workers', type=int, choices=range(1,5), default=2)
    a = parser.parse_args(); cases = selected(a.plates,a.sections,a.rotations,a.biases)
    if file_digest(ROOT / MAP_PATH) != MAP_SHA or file_digest(ROOT / CONTRACT_PATH) != CONTRACT_SHA: raise ValueError('Reviewed contracts changed.')
    source_map = json.loads((ROOT / MAP_PATH).read_bytes()); contract = json.loads((ROOT / CONTRACT_PATH).read_bytes())
    out = a.output.resolve()
    if any(c.isspace() for c in str(out)): raise ValueError('Use an evidence path without whitespace.')
    out.mkdir(parents=True, exist_ok=False)
    for relative, name in ((MAP_PATH,'bias-contract.json'),(CONTRACT_PATH,'contract.json')): (out/name).write_bytes((ROOT/relative).read_bytes())
    paths = [*sorted((ROOT/'icstudio').rglob('*.py')), *sorted((ROOT/'scripts').glob('*.py'))]
    sources = {p.relative_to(ROOT).as_posix():file_digest(p) for p in paths}
    write(out/'source-files.json', sources)
    for name, digest in sources.items():
        dest = out/'source'/name; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes((ROOT/name).read_bytes())
        if file_digest(dest) != digest: raise ValueError('Source changed during capture.')
    report = dict(schema=1, chunk=7, qualified=False, chunk_complete=False, release=False, status='RUNNING', scope=__doc__,
        execution_root=str(out), source_root=str(ROOT), selected_cases=[case_name(*v) for v in cases],
        full_declared_cases=[case_name(*v) for v in selected([1,2],list(SECTIONS),[0,90],[-5,0,5])],
        source_map_sha256=MAP_SHA, contract_sha256=CONTRACT_SHA, source_files_sha256=file_digest(out/'source-files.json'),
        domain_controls=domain_controls(), cases=[], timings_seconds={})
    write(out/'qualification.json', report)
    try:
        start=time.monotonic(); print('Reading retained physical evidence and locked runtime',flush=True)
        report['reused_physical']=restore_physical(a.archive,out,source_map)
        write(out/'retained-bindings.json',report['reused_physical']['bindings'])
        report['reused_physical'].pop('bindings')
        report['retained_bindings_sha256']=file_digest(out/'retained-bindings.json')
        sim,simid=load_technology('sky130A'); report['simulation_package']=simid
        for name, item in source_map['sources'].items():
            src = ROOT/item['path'] if 'path' in item else out/'retained-native'/item['member'].removeprefix('accepted/native/')
            if file_digest(src)!=item['sha256']: raise ValueError('Mapped source changed: '+name)
            dest=out/'contract-sources'/name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(src.read_bytes())
        staged,models=stage_models(sim,out); write(out/'model-files.json',models)
        # Exercise lazy imports before capturing the Python/runtime closure.
        # This prepares decks only; no electrical result is reused or executed.
        for plate in a.plates:
            native=out/'retained-native/physical'/str(plate)/'valid-0-plain/lvs-extraction/extracted.spice'
            project,_=circuit(sim,plate,native,staged['tt'],0,'op',execution_root=out,case=case_name(plate,'tt',0,0))
            ngspice_command(project,str(a.ngspice),out/'unused.raw',out/'unused.cir')
        before_runtime=runtime(a.ngspice); write(out/'runtime-before.json',before_runtime)
        report['runtime_before_sha256']=file_digest(out/'runtime-before.json')
        report['timings_seconds']['setup']=time.monotonic()-start;write(out/'qualification.json',report)
        start=time.monotonic()
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            jobs=[pool.submit(execute_case,sim,p,s,r,b,
                out/'retained-native/physical'/str(p)/f'valid-{r}-plain/lvs-extraction/extracted.spice',
                staged,contract['passive_sections'][s]['coefficients'],out,str(a.ngspice)) for p,s,r,b in cases]
            for job in as_completed(jobs):
                row=job.result();report['cases'].append(row);write(out/'qualification.json',report)
                print(row['name'],row['status'],row.get('error',''),flush=True)
        report['timings_seconds']['electrical']=time.monotonic()-start
        after_runtime=runtime(a.ngspice);write(out/'runtime-after.json',after_runtime)
        report['runtime_after_sha256']=file_digest(out/'runtime-after.json')
        report['runtime_unchanged']=before_runtime==after_runtime
        report['source_unchanged']=sources=={p.relative_to(ROOT).as_posix():file_digest(p) for p in paths}
        report['models_unchanged']=models=={p.relative_to(out/'shared-models').as_posix():file_digest(p) for p in (out/'shared-models').rglob('*') if p.is_file() and p.name!='source-identity.json'}
        bindings=json.loads((out/'retained-bindings.json').read_bytes())
        report['retained_unchanged']=all(file_digest(out/'retained-native'/name)==item['sha256'] for name,item in bindings.items())
        report['contracts_unchanged']=file_digest(ROOT/MAP_PATH)==MAP_SHA and file_digest(ROOT/CONTRACT_PATH)==CONTRACT_SHA
        guards=('runtime_unchanged','source_unchanged','models_unchanged','retained_unchanged','contracts_unchanged')
        report['status']='PASS' if all(report[k] for k in guards) and len(report['cases'])==len(cases) and all(row['status']=='PASS' for row in report['cases']) else 'FAIL'
    except Exception as error:
        report.update(status='FAIL',error=repr(error),traceback=traceback.format_exc())
    report['cases'].sort(key=lambda row:row['name']);write(out/'qualification.json',report)
    write(out/'manifest.json',{p.relative_to(out).as_posix():file_digest(p) for p in out.rglob('*') if p.is_file() and p!=out/'manifest.json'})
    return int(report['status']!='PASS')


if __name__ == '__main__': raise SystemExit(main())
