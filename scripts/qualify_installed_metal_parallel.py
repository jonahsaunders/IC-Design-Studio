"""DC/AC acceptance of thirty fresh GUI-exported and extracted physical arrays.

No device is regenerated here. Source pilots and installed execution have
separate identities; this finite integration is not device or foundry signoff.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import traceback
from urllib.parse import unquote, urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.pdks import model_lines, stage_model_deck
from scripts import installed_metal_parallel_inputs as inputs
from scripts import qualify_sky130_metal_resistor_parallel as original
from scripts import qualify_sky130_metal_resistors_linked as electrical

sha, write, require = inputs.sha, inputs.write, inputs.require
ENGINE_SOURCES = 'docs/qualification/ngspice42-metal-reference'


def title(execution, gui_nonce, case, analysis):
    context = dict(execution_root=execution['root'], execution_nonce=execution['nonce'],
                   gui_execution_id=gui_nonce, case=case, analysis=analysis)
    return '* icstudio-installed-metal-parallel-v1 ' + hashlib.sha256(
        json.dumps(context, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def retain_inputs(binding, out):
    normalized = {}
    require(len(binding['cases']) == 30, 'All thirty fresh GUI/native array inputs are required.')
    for key, row in binding['cases'].items():
        normalized[key] = {}
        for kind, source_kind in (('application', 'reference'), ('native', 'native')):
            source = Path(row['files'][source_kind]); raw = source.read_bytes()
            require(sha(source) == row['hashes'][source_kind], 'Actual GUI/native input changed.')
            inputs.circuit(raw, row, application=kind == 'application', top=row['top'])
            retained = out/'original-inputs'/key/(kind+'.spice')
            retained.parent.mkdir(parents=True, exist_ok=True); retained.write_bytes(raw)
            data, proof = inputs.normalize_top(raw, row['top'])
            inputs.circuit(data, row, application=kind == 'application', top='coupon')
            target = out/'normalized-inputs'/key/(kind+'.spice')
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
            normalized[key][kind] = dict(original_path=str(source), original_sha256=sha(source),
                retained_path=str(retained), normalized_path=str(target),
                normalized_sha256=sha(target), proof=proof)
    write(out/'normalized-inputs.json', normalized)
    return normalized


def deck(spec, row, case, analysis, staged, normalized, execution, gui_nonce):
    require(analysis in ('dc', 'ac'), 'Only the frozen DC/AC selection is supported.')
    lines = [title(execution, gui_nonce, case, analysis), staged['tt'],
        '.option reltol=1e-7 abstol=1e-15 vntol=1e-12 method=gear', '.temp 27',
        'VDRIVE input 0 DC .0005 AC 1']
    for kind, wrapper in (('application', 'app_wrapper'), ('native', 'native_wrapper')):
        path = Path(normalized[kind]['normalized_path'])
        require(not any(c.isspace() for c in str(path)), 'Use an output path without whitespace.')
        lines += [f'.subckt {wrapper} a b', f'.include {path.as_posix()}',
                  'X_BODY a b coupon', f'.ends {wrapper}']
    resistance = original.resistance(spec, row)
    for tag, body in (('a', 'XA in_a out_a app_wrapper'), ('n', 'XN in_n out_n native_wrapper'),
                      ('c', f'RC in_c out_c {resistance:.17g}')):
        lines += [f'VS_{tag} input in_{tag} DC 0 AC 0', body,
                  f'RL_{tag} out_{tag} 0 1', f'CL_{tag} out_{tag} 0 1n']
    parameters = original.coefficients(spec)
    lines += [f'VP_{key} par_{key} 0 DC {{{key}}} AC {{{key}}}' for key in parameters]
    channels = ['v(input)', *[v for tag in ('a', 'n', 'c') for v in
        (f'v(in_{tag})', f'v(out_{tag})', f'i(vs_{tag})')], *['v(par_'+key+')' for key in parameters]]
    lines += ['.save '+' '.join(channels),
              '.dc VDRIVE -.001 .001 .0001' if analysis == 'dc' else '.ac dec 3 1k 10g', '.end']
    return '\n'.join(lines)+'\n'


def observe(spec, row, case, analysis, folder, execution, gui_nonce):
    parameters = original.coefficients(spec); axis = 'v(v-sweep)' if analysis == 'dc' else 'frequency'
    channels = [axis, 'v(input)', *[v for tag in ('a', 'n', 'c') for v in
        (f'v(in_{tag})', f'v(out_{tag})', f'i(vs_{tag})')], *['v(par_'+key+')' for key in parameters]]
    x, data, complex_values = electrical.read_raw(folder/'result.raw',
        title(execution, gui_nonce, case, analysis),
        'DC transfer characteristic' if analysis == 'dc' else 'AC Analysis', channels)
    require(complex_values == (analysis == 'ac'), 'Wrong native raw value format.')
    grid = [-.001+i*.0001 for i in range(21)] if analysis == 'dc' else [1000*10**(i/3) for i in range(22)]
    require(len(x) == len(grid) and all(math.isclose(a, b, rel_tol=1e-10,
        abs_tol=1e-12 if analysis == 'dc' else 0) for a, b in zip(x, grid)), 'Wrong electrical sample grid.')
    def error(actual, expected, absolute=1e-10, relative=1e-6):
        value = electrical.normalized(actual, expected, relative, absolute)
        require(math.isfinite(value) and value <= 1, 'Array response exceeds the fixed analytical tolerance.')
        return value
    for key, value in parameters.items(): error(data['v(par_'+key+')'], [value]*len(x), 1e-24, 1e-10)
    drive = x if analysis == 'dc' else [1]*len(x); error(data['v(input)'], drive)
    resistance = original.resistance(spec, row)
    expected = [v/(1+resistance) for v in x] if analysis == 'dc' else [
        1/(1+resistance*(1+2j*math.pi*f*1e-9)) for f in x]
    branches = {}
    for tag in ('a', 'n', 'c'):
        vin, vout, current = (data[key] for key in (f'v(in_{tag})', f'v(out_{tag})', f'i(vs_{tag})'))
        error(vin, drive)
        branches[tag] = dict(resistance_ohm=resistance, maximum_normalized_error=error(vout, expected),
            current_normalized_error=error(current, [(a-b)/resistance for a, b in zip(vin, vout)], 1e-12),
            kcl_normalized_error=error(current, [v*(1+(2j*math.pi*f*1e-9 if analysis == 'ac' else 0))
                                                for f, v in zip(x, vout)], 1e-12))
    return dict(raw_sha256=sha(folder/'result.raw'), analysis=analysis, samples=len(x),
                parameters=parameters, branches=branches)


def execute_case(spec, row, key, analysis, staged, normalized, execution, gui_nonce, out, engine, env):
    name = key+'-'+analysis; folder = out/'electrical'/name; folder.mkdir()
    (folder/'input.cir').write_text(deck(spec, row, key, analysis, staged, normalized[key], execution, gui_nonce),
                                  encoding='utf-8', newline='\n')
    command = [str(engine), '-n', '-D', 'filetype=ascii', '-D', 'ngbehavior=hsa', '-b',
               '-r', str(folder/'result.raw'), str(folder/'input.cir')]
    record = dict(name=name, case=key, model=row['model'], width_um=row['width_um'], length_um=row['length_um'],
        multiplicity=row['multiplicity'], rotation=row['rotation'], analysis=analysis, status='RUNNING',
        command=command, cwd=str(out), environment=env)
    try:
        result = subprocess.run(command, cwd=out, env=env, capture_output=True, text=True, timeout=90)
        log = result.stdout+result.stderr; (folder/'console.log').write_text(log, encoding='utf-8')
        require(result.returncode == 0 and 'error' not in log.lower() and 'unknown parameter' not in log.lower(),
                'Native simulator failed; inspect its original log.')
        record.update(observation=observe(spec, row, key, analysis, folder, execution, gui_nonce), status='PASS',
            returncode=result.returncode, deck_sha256=sha(folder/'input.cir'), raw_sha256=sha(folder/'result.raw'),
            log_sha256=sha(folder/'console.log'))
    except subprocess.TimeoutExpired as exc:
        def decoded(value):
            return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')
        (folder/'console.log').write_text(decoded(exc.stdout)+decoded(exc.stderr), encoding='utf-8')
        record.update(status='FAIL', error=traceback.format_exc(), timed_out=True,
                      log_sha256=sha(folder/'console.log'))
    except Exception: record.update(status='FAIL', error=traceback.format_exc())
    write(folder/'record.json', record)
    return record


def run(gui_root, out, expected_commit=None, *, source_pilot=False, source_engine=None, workers=2):
    require(workers in range(1, 5), 'Select one to four workers.')
    out = inputs.common.gui.unlinked(out).resolve()
    supplied = inputs.common.gui.unlinked(gui_root).resolve()
    require(out != supplied and out not in supplied.parents and supplied not in out.parents,
            'Keep output and received GUI evidence in disjoint directories.')
    require(not out.exists() and not any(c.isspace() for c in str(out)), 'Use a fresh output directory without whitespace.')
    out.mkdir(parents=True); started = time.monotonic()
    execution = dict(root=unquote(urlsplit(out.as_uri()).path), nonce=uuid.uuid4().hex)
    report = dict(schema=1, gate='sky130-metal-parallel-installed-electrical-v1', status='RUNNING',
        mode='source-pilot' if source_pilot else 'installed', execution=execution, execution_directory=str(out),
        expected_commit=expected_commit, pilot=False, cases=[], scope=__doc__, qualified=False,
        installed_acceptance=False, installed_electrical_acceptance=False, full_family=False,
        chunk_complete=False, release_ready=False, signoff=False)
    write(out/'qualification.json', report)
    try:
        binding = inputs.bind_gui(gui_root, expected_commit, source_pilot=source_pilot); write(out/'inputs.json', binding)
        installed, spec, mapped = inputs.contracts(binding); write(out/'contract-sources.json', mapped)
        (out/'contract.json').write_bytes((ROOT/installed['source_contract']['path']).read_bytes())
        (out/'installed-contract.json').write_bytes((ROOT/inputs.CONTRACT).read_bytes())
        for name, row in spec['engine_sources'].items():
            path = ROOT/ENGINE_SOURCES/name; require(sha(path) == row['sha256'], 'Primitive reference source changed.')
            target = out/'engine-reference'/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(path.read_bytes())
        sources = inputs.source_files()
        if not source_pilot: inputs.candidate_sources(sources, expected_commit)
        write(out/'source-files.json', sources)
        for name, value in sources.items():
            target = out/'source'/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes((ROOT/name).read_bytes())
            require(sha(target) == value, 'Source changed during capture.')
        package_root = Path(binding['simulation_package']['path']); package = inputs.load(package_root/'package.json')
        package_files = {'package.json': sha(package_root/'package.json'), **package['files']}
        for name, value in package_files.items():
            path = inputs.common.gui.unlinked(package_root/name); require(sha(path) == value, 'Simulation package changed.')
            target = out/'original-package'/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(path.read_bytes())
        write(out/'package-files.json', package_files)
        normalized = retain_inputs(binding, out)
        originals = inputs.inventory(out/'original-inputs'); normalized_files = inputs.inventory(out/'normalized-inputs')
        tech = inputs.technology(binding)
        require(tech['simulation'].get('ngspice_compatibility') == 'hsa', 'Unexpected simulator compatibility mode.')
        staged = {'tt': stage_model_deck(tech, '\n'.join(model_lines(tech, 'tt')), out)}
        write(out/'selected-model-lines.json', staged)
        staged_files = inputs.inventory(out/'pdk-models'); write(out/'staged-model-files.json', staged_files)
        engine = inputs.select_engine(binding, source_engine); env = inputs.native_environment(binding, engine, out)
        before = inputs.runtime(binding, engine, env); write(out/'runtime-before.json', before)
        runtime_files = {**before['files'], **{v['resolved']: v['sha256'] for v in before['elf_dependencies'].values()}}
        electrical.retain_files(runtime_files, out/'runtime-assets'); write(out/'runtime-assets.json', runtime_files)
        selected = [(key, analysis) for key in binding['cases'] for analysis in ('dc', 'ac')]
        report.update(inputs_sha256=sha(out/'inputs.json'), gui_execution_id=binding['execution_id'],
            contract_sha256=installed['source_contract']['sha256'], installed_contract_sha256=inputs.CONTRACT_SHA,
            contract_sources_sha256=sha(out/'contract-sources.json'), source_files_sha256=sha(out/'source-files.json'),
            source_root=str(ROOT), simulation_package=binding['simulation_package'],
            selected_cases=[key+'-'+analysis for key, analysis in selected],
            normalized_inputs_sha256=sha(out/'normalized-inputs.json'), runtime_before_sha256=sha(out/'runtime-before.json'))
        (out/'electrical').mkdir(); write(out/'qualification.json', report)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            jobs = [pool.submit(execute_case, spec, binding['cases'][key], key, analysis, staged, normalized,
                                execution, binding['execution_id'], out, engine, env) for key, analysis in selected]
            for future in as_completed(jobs):
                row = future.result(); report['cases'].append(row); write(out/'qualification.json', report)
                print(row['name'], row['status'], flush=True)
        after = inputs.runtime(binding, engine, env); write(out/'runtime-after.json', after)
        require(before == after and sources == inputs.source_files(), 'Runtime or source changed during execution.')
        require(binding == inputs.bind_gui(gui_root, expected_commit, source_pilot=source_pilot), 'Fresh GUI/native prerequisite changed.')
        require(mapped == inputs.contracts(binding)[2], 'Public contract/package source changed.')
        require(all(sha(package_root/name) == value for name, value in package_files.items()), 'Original package changed.')
        require(staged_files == inputs.inventory(out/'pdk-models'), 'Staged model files changed.')
        require(originals == inputs.inventory(out/'original-inputs') and normalized_files == inputs.inventory(out/'normalized-inputs'),
                'Retained actual application/native inputs changed.')
        require(len(report['cases']) == 60 and all(row['status'] == 'PASS' for row in report['cases']), 'Electrical acceptance failed.')
        report.update(status='PASS', installed_electrical_acceptance=not source_pilot,
            runtime_after_sha256=sha(out/'runtime-after.json'),
            input_guards=dict(runtime=True, sources=True, gui=True, public_contract=True,
                              simulation_package=True, staged_models=True, retained_inputs=True))
    except Exception: report.update(status='FAIL', error=traceback.format_exc(), installed_electrical_acceptance=False)
    report['cases'].sort(key=lambda row: row['name']); report['seconds'] = time.monotonic()-started
    write(out/'qualification.json', report); write(out/'manifest.json', inputs.inventory(out, ('manifest.json',)))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui-root', type=Path, required=True); parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--expected-commit'); parser.add_argument('--source-pilot', action='store_true')
    parser.add_argument('--source-engine', type=Path); parser.add_argument('--workers', type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    report = run(args.gui_root, args.out, args.expected_commit, source_pilot=args.source_pilot,
                 source_engine=args.source_engine, workers=args.workers)
    if report['status'] == 'PASS':
        from scripts.audit_installed_metal_parallel import audit
        try: write(args.out/'audit.json', audit(args.out, ROOT))
        except Exception:
            write(args.out/'audit.json', dict(status='FAIL', error=traceback.format_exc(), installed_electrical_acceptance=False))
            raise
    print(json.dumps({k: report.get(k) for k in ('status', 'mode', 'installed_electrical_acceptance', 'seconds', 'error')}, indent=2))
    return int(report['status'] != 'PASS')


if __name__ == '__main__': raise SystemExit(main())
