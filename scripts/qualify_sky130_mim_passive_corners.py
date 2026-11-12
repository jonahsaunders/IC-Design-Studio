"""Selected MiM passive sections with native extraction and analytical RC checks.

Fresh bounded model-integration evidence, not calibrated RF accuracy, full
operating-envelope, statistical, installed-release or foundry qualification.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
from pathlib import Path
import re
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.engines import execute, ngspice_command, parse_raw
from icstudio.model import atomic_write, file_digest
from icstudio.pdks import model_lines, stage_model_deck
from icstudio.testbenches import native_subcircuit
from scripts.qualify_standard_mos import load_technology, write
from scripts.qualify_standard_mos_layout import technology
from scripts.qualify_sky130_mim2 import fixture, independent, audit_native
from scripts.qualify_sky130_mim_orientation import execute_case as physical_case

SECTIONS = ('tt', 'll', 'hh', 'hl', 'lh')
SIZE = (2, 10, 1)
CONTRACT = 'docs/qualification/sky130-mim-contract-v1.json'
CONTRACT_SHA = 'b324813599a364c83e76e63f583e7b74da50ab8182640a1cb907796a3ce1c209'
PARAMETERS = ('rm3', 'rm4', 'rcvia3', 'rcvia4', 'tol_m3', 'tol_m4',
              'camimc', 'cpmimc', 'm3_dw', 'm4_dw')
FAULTS = ('wrong-width', 'wrong-length', 'wrong-count', 'swapped', 'wrong-model')
PATHS = ('schematic', 'extracted', 'independent', *FAULTS)
REL_TOL = 1e-6


def contract_sources(value, physical_root):
    paths = {}
    for name, source in value['sources'].items():
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', name): raise ValueError('Unsafe source identifier.')
        base = ROOT if 'path' in source else physical_root.resolve()
        relative = source.get('path')
        if relative is None:
            asset = Path(source['asset_path'])
            if asset.parts[0] != 'sky130A': raise ValueError('Unexpected public physical asset prefix.')
            relative = Path(*asset.parts[1:])
        candidate = base / relative
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(base.resolve()) or not candidate.is_file() or file_digest(candidate) != source['sha256']:
            raise ValueError('MiM contract source changed: ' + name)
        paths[name] = candidate
    return paths


def review(physical_root):
    path = ROOT / CONTRACT
    if file_digest(path) != CONTRACT_SHA: raise ValueError('MiM contract changed; review before execution.')
    value = json.loads(path.read_bytes())
    contract_sources(value, physical_root)
    return value


def selected(plates, sections, rotations):
    for values, allowed in ((plates, (1, 2)), (sections, SECTIONS), (rotations, (0, 90))):
        if not values or len(values) != len(set(values)) or any(v not in allowed for v in values):
            raise ValueError('Selections must contain distinct supported cases.')
    return [(p, s, a) for p in plates for s in sections for a in rotations]


def renamed(text, name):
    if len(re.findall(r'(?im)^\.subckt\s+device_coupon\s+P\s+N\s*$', text)) != 1:
        raise ValueError('Unexpected schematic/reference interface.')
    return re.sub(r'(?im)^(\.subckt|\.ends)\s+device_coupon\b',
                  lambda m: m[1] + ' ' + name, text)


def stage_models(tech, out):
    folder = out / 'shared-models'
    folder.mkdir()
    def absolute(text):
        return re.sub(r'(?im)^(\s*\.(?:lib|include|inc)) +(pdk-models/\S+)',
                      lambda m: m[1] + ' ' + (folder / m[2]).as_posix(), text)
    staged = {s: absolute(stage_model_deck(tech, '\n'.join(model_lines(tech, s)), folder)) for s in SECTIONS}
    for p in (folder / 'pdk-models').glob('*.spice'):
        p.write_bytes(absolute(p.read_text(encoding='utf-8')).encode())
    for original in json.loads((folder / 'pdk-model-files.json').read_bytes()).values():
        source = Path(tech['package_root']) / original
        dest = out / 'model-sources' / original
        if not dest.resolve().is_relative_to((out / 'model-sources').resolve()): raise ValueError('Unsafe staged source path.')
        dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(source.read_bytes())
        if file_digest(dest) != tech['package_lock']['files'][original]: raise ValueError('Staged source changed.')
    files = {p.relative_to(folder).as_posix(): file_digest(p) for p in folder.rglob('*') if p.is_file()}
    write(folder / 'source-identity.json', dict(staged=staged, files=files))
    return staged, files


def circuit(tech, plate, native, staged):
    audit_native(native, SIZE, plate)
    project = fixture(tech, SIZE, plate)
    model = f'sky130_fd_pr__cap_mim_m3_{plate}'
    text = '* Distinct passive-section MiM integration, not measured accuracy\n' + staged + '\n'
    text += '.param mc_mm_switch=0 mc_pr_switch=0\n.option tnom=27\n.temp 27\n'
    text += renamed(native_subcircuit(project, project['top']), 'schematic') + '\n'
    text += renamed(independent(SIZE, plate=plate), 'independent') + '\n'
    text += f'.include {native.as_posix()}\n'
    for name in PATHS:
        node = 'p_' + name.replace('-', '_')
        key = name.replace('-', '_')
        text += f'VP_{key} {node} 0 DC 0 AC 1\n'
        if name in ('schematic', 'independent', 'extracted'):
            text += f'X_{key} {node} 0 ' + ('device_coupon' if name == 'extracted' else name) + '\n'
        else:
            width, length, count = SIZE
            if name == 'wrong-width': width *= 1.2
            if name == 'wrong-length': length *= 1.2
            if name == 'wrong-count': count = 2
            if name == 'swapped': width, length = length, width
            chosen = f'sky130_fd_pr__cap_mim_m3_{3 - plate}' if name == 'wrong-model' else model
            text += f'X_{key} {node} 0 {chosen} w={width:g} l={length:g} m={count}\n'
    for parameter in (*PARAMETERS, 'mc_mm_switch', 'mc_pr_switch'):
        text += f'VPAR_{parameter} par_{parameter} 0 DC {{{parameter}}} AC {{{parameter}}}\n'
    saves = ['i(vp_' + k.replace('-', '_') + ')' for k in PATHS]
    saves += ['v(p_' + k.replace('-', '_') + ')' for k in PATHS]
    saves += ['v(par_' + k + ')' for k in (*PARAMETERS, 'mc_mm_switch', 'mc_pr_switch')]
    text += '.ac dec 1 1k 10G\n.save ' + ' '.join(saves) + '\n.end\n'
    return project, text


def expected_rc(plate, coefficients):
    metal = plate + 2
    width = 2 + 1e6 * (coefficients[f'm{metal}_dw'] + coefficients[f'tol_m{metal}'])
    length = 10 + 1e6 * (coefficients[f'm{metal}_dw'] + coefficients[f'tol_m{metal}'])
    capacitance = coefficients['camimc'] * width * length + 2 * coefficients['cpmimc'] * (width + length)
    resistance = coefficients[f'rm{metal}'] * length / width
    resistance += coefficients[f'rcvia{metal}'] * (.56 if plate == 1 else .73) ** 2 / (width * length)
    if not all(math.isfinite(x) and x > 0 for x in (width, length, capacitance, resistance)):
        raise ValueError('Nonphysical effective RC dimensions/coefficients.')
    return resistance, capacitance


def measure(path, plate, coefficients, require_match=True):
    names, rows, complex_data = parse_raw(path)
    names = [n.lower() for n in names]
    expected = {'frequency', *('i(vp_' + k.replace('-', '_') + ')' for k in PATHS),
                *('v(p_' + k.replace('-', '_') + ')' for k in PATHS),
                *('v(par_' + k + ')' for k in (*PARAMETERS, 'mc_mm_switch', 'mc_pr_switch'))}
    if not complex_data or len(rows) != 8 or len(names) != len(expected) or set(names) != expected:
        raise ValueError('Incomplete or unexpected native AC channels.')
    resistance, capacitance = expected_rc(plate, coefficients)
    samples = []
    worst = {k: 0.0 for k in PATHS}
    params = {}
    coefficient_error = 0.0
    for i, row in enumerate(rows):
        values = dict(zip(names, row))
        if len(row) != len(names) or any(not math.isfinite(v.real) or not math.isfinite(v.imag)
                                       for k, v in values.items() if k != 'frequency'):
            raise ValueError('Nonfinite or incomplete native sample.')
        frequency = values['frequency'].real
        if not math.isclose(frequency, 1000 * 10 ** i, rel_tol=1e-12):
            raise ValueError('Incorrect frequency sweep.')
        for key in (*PARAMETERS, 'mc_mm_switch', 'mc_pr_switch'):
            value = values['v(par_' + key + ')']
            expected_value = coefficients[key] if key in coefficients else 0.0
            error = abs(value - expected_value) / (1e-24 + 1e-10 * abs(expected_value))
            coefficient_error = max(coefficient_error, error)
            if key in params and value.real != params[key]: raise ValueError('Nonconstant parameter probe.')
            params[key] = value.real
        target = 1 / (resistance + 1 / (2j * math.pi * frequency * capacitance))
        saved = {}
        for key in PATHS:
            if abs(values['v(p_' + key.replace('-', '_') + ')'] - 1) > 1e-12:
                raise ValueError('Incorrect native applied AC source.')
            value = -values['i(vp_' + key.replace('-', '_') + ')']
            if not value.imag > 0 or not value.real > 0: raise ValueError('Noncapacitive or nonpassive response.')
            measured_r = (1 / value).real
            measured_c = -1 / (2 * math.pi * frequency * (1 / value).imag)
            error = max(abs(value / target - 1), abs(measured_r / resistance - 1), abs(measured_c / capacitance - 1))
            worst[key] = max(worst[key], error)
            saved[key] = dict(Y_S=[value.real, value.imag], R_ohm=measured_r, C_F=measured_c, relative_error=error)
        samples.append(dict(frequency_Hz=frequency, paths=saved))
    matched = coefficient_error <= 1 and all(worst[k] <= REL_TOL for k in ('schematic', 'extracted', 'independent'))
    if require_match and (not matched or any(worst[k] <= (.05 if k == 'swapped' else REL_TOL) for k in FAULTS)):
        raise ValueError('Expected response or fault sensitivity differs: ' + str(worst) + '; coefficients=' + str(coefficient_error))
    return dict(status='PASS' if matched else 'MISMATCH', coefficients=params,
                maximum_coefficient_normalized_error=coefficient_error, maximum_relative_errors=worst,
                expected_R_ohm=resistance, expected_C_F=capacitance, samples=samples, raw_sha256=file_digest(path))


def execute_case(tech, plate, section, rotation, native, staged, coefficients, out, engine):
    folder = out / f'p{plate}-{section}-r{rotation}'
    folder.mkdir()
    row = dict(name=folder.name, plate=plate, section=section, rotation=rotation, status='RUNNING',
               native_path=str(native), native_sha256=file_digest(native))
    try:
        for fault, choice in ((False, section), (True, 'hh' if section != 'hh' else 'll')):
            dest = folder / ('wrong-section' if fault else 'selected')
            dest.mkdir()
            project, text = circuit(tech, plate, native, staged[choice])
            deck = dest / 'probe.cir'; raw = dest / 'probe.raw'
            atomic_write(deck, text)
            log = execute(ngspice_command(project, engine, raw, deck), dest, timeout=90)
            atomic_write(dest / 'console.log', log)
            result = measure(raw, plate, coefficients[section], require_match=not fault)
            if fault and (result['status'] != 'MISMATCH' or result['maximum_coefficient_normalized_error'] <= 1):
                raise ValueError('Wrong passive section was not detected.')
            result.update(executed_section=choice, deck_sha256=file_digest(deck))
            row['wrong_section' if fault else 'selected'] = result
        row['status'] = 'PASS'
    except Exception as error:
        row.update(status='FAIL', error=repr(error), traceback=traceback.format_exc())
    write(folder / 'record.json', row)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('sky130', 'magic', 'netgen', 'klayout', 'ngspice', 'output'):
        ap.add_argument('--' + name, required=True, type=Path)
    ap.add_argument('--plates', nargs='+', type=int, default=[1, 2])
    ap.add_argument('--sections', nargs='+', default=list(SECTIONS))
    ap.add_argument('--rotations', nargs='+', type=int, default=[0, 90])
    ap.add_argument('--workers', type=int, choices=range(1, 5), default=2)
    a = ap.parse_args(); cases = selected(a.plates, a.sections, a.rotations)
    contract_path = ROOT / CONTRACT
    contract = review(a.sky130)
    coefficients = {s: contract['passive_sections'][s]['coefficients'] for s in SECTIONS}
    out = a.output.resolve()
    if any(c.isspace() for c in str(out)): raise ValueError('Use an evidence path without whitespace.')
    out.mkdir(parents=True, exist_ok=False)
    source_paths = [*sorted((ROOT / 'icstudio').rglob('*.py')), *sorted((ROOT / 'scripts').glob('*.py'))]
    before = {p.relative_to(ROOT).as_posix(): file_digest(p) for p in source_paths}
    write(out / 'source-files.json', before)
    for name, digest in before.items():
        data = (ROOT / name).read_bytes()
        dest = out / 'source' / name; dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if file_digest(dest) != digest: raise ValueError('Source changed during capture: ' + name)
    for name, path in contract_sources(contract, a.sky130).items():
        dest = out / 'contract-sources' / name; dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())
        if file_digest(dest) != contract['sources'][name]['sha256']: raise ValueError('Contract source changed during capture.')
    (out / 'executed-runner.py').write_bytes(Path(__file__).read_bytes())
    (out / 'contract.json').write_bytes(contract_path.read_bytes())
    tools = {k: str(getattr(a, k).resolve(strict=True)) for k in ('magic', 'netgen', 'klayout', 'ngspice')}
    report = dict(schema=1, chunk=7, qualified=False, chunk_complete=False, status='RUNNING', scope=__doc__,
                  execution_root=str(out), selected_cases=[f'p{p}-{s}-r{v}' for p, s, v in cases],
                  full_declared_cases=[f'p{p}-{s}-r{v}' for p in (1, 2) for s in SECTIONS for v in (0, 90)],
                  contract_sha256=file_digest(contract_path), source_files_sha256=file_digest(out / 'source-files.json'),
                  tools={k: dict(path=v, sha256=file_digest(v)) for k, v in tools.items()}, cases=[], physical=[], timings_seconds={})
    write(out / 'qualification.json', report)
    try:
        phase = time.monotonic()
        print('Preparing locked simulation models and physical adapter', flush=True)
        sim, simid = load_technology('sky130A'); phys, physid = technology('sky130A', a.sky130)
        report.update(simulation_package=simid, physical_package=physid)
        staged, model_files = stage_models(sim, out)
        write(out / 'model-files.json', model_files)
        report['timings_seconds']['model_setup'] = time.monotonic() - phase
        write(out / 'qualification.json', report)
        physical_root = out / 'physical'; physical_root.mkdir()
        for plate in a.plates:
            phase = time.monotonic()
            print(f'Checking native physical plate {plate}', flush=True)
            item = physical_case(phys, SIZE, plate, physical_root, tools, pilot=True, plate=plate)
            report['physical'].append(item)
            report['timings_seconds'][f'physical_plate_{plate}'] = time.monotonic() - phase
            write(out / 'qualification.json', report)
            if item['status'] != 'PASS': raise ValueError('Fresh native physical case failed: ' + str(item.get('error')))
        phase = time.monotonic()
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            jobs = [pool.submit(execute_case, sim, p, s, v,
                                physical_root / str(p) / f'valid-{v}-plain/lvs-extraction/extracted.spice',
                                staged, coefficients, out, tools['ngspice']) for p, s, v in cases]
            for job in as_completed(jobs):
                row = job.result(); report['cases'].append(row)
                write(out / 'qualification.json', report)
                print(row['name'], row['status'], row.get('error', ''), flush=True)
        report['timings_seconds']['selected_electrical'] = time.monotonic() - phase
        report['source_unchanged'] = before == {p.relative_to(ROOT).as_posix(): file_digest(p) for p in source_paths}
        report['models_unchanged'] = model_files == {p.relative_to(out / 'shared-models').as_posix(): file_digest(p)
            for p in (out / 'shared-models').rglob('*') if p.is_file() and p.name != 'source-identity.json'}
        report['tools_unchanged'] = all(file_digest(v) == report['tools'][k]['sha256'] for k, v in tools.items())
        report['contract_unchanged'] = review(a.sky130) == contract and file_digest(contract_path) == report['contract_sha256']
        report['status'] = 'PASS' if all(report[k] for k in ('source_unchanged', 'models_unchanged', 'tools_unchanged', 'contract_unchanged')) and all(x['status'] == 'PASS' for x in report['cases']) and len(report['cases']) == len(cases) else 'FAIL'
    except Exception as error:
        report.update(status='FAIL', error=repr(error), traceback=traceback.format_exc())
    report['cases'].sort(key=lambda r: r['name'])
    write(out / 'qualification.json', report)
    write(out / 'manifest.json', {p.relative_to(out).as_posix(): file_digest(p) for p in out.rglob('*') if p.is_file() and p != out / 'manifest.json'})
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
