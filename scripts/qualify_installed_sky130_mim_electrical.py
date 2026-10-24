"""Fresh selected MiM electrical checks from independently verified GUI exports.

The installed mode runs the actual packaged simulator against four newly
extracted GUI layouts. A separately labeled source pilot is available for
development. Neither mode establishes silicon accuracy or foundry signoff.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import installed_mim_inputs as inputs
from scripts.qualify_sky130_mim_passive_corners import stage_models, SECTIONS
from scripts.qualify_sky130_mim_bias_boundaries import (selected, case_name, checked_bias,
    domain_controls, faults, applied, measure_op, measure_ac, PROBES, PATHS)

require, sha, load, write = inputs.require, inputs.sha, inputs.load, inputs.write


def normalized(text, old, new):
    require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', old) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', new),
            'Unsafe subcircuit identity.')
    require(re.findall(r'(?m)^\.subckt (\S+) P N[ \t]*$', text) == [old], 'Unexpected exported interface.')
    endings = re.findall(r'(?m)^\.ends(?: (\S+))?[ \t]*$', text)
    require(endings in ([old], ['']), 'Unexpected exported end statement.')
    return re.sub(r'(?m)^(\.subckt|\.ends) '+re.escape(old)+r'\b', lambda m: m[1]+' '+new, text)


def context_title(identity, case, analysis, fault=None):
    data = dict(identity=identity, case=case, analysis=analysis, fault=fault or 'positive')
    return '* icstudio-installed-mim-v1 '+hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def circuit(reference, native, staged, plate, bias, analysis, identity, case, fault=None):
    checked_bias(bias)
    require(analysis in ('op', 'ac') and (fault is None or (analysis == 'op' and fault in faults(bias))), 'Invalid analysis/control.')
    high, low = applied(bias, fault)
    text = context_title(identity, case, analysis, fault)+'\n'+staged+'\n'
    text += '.param mc_mm_switch=0 mc_pr_switch=0\n.option tnom=27\n.temp 27\n'
    text += reference+'\n'
    text += f'.subckt independent P N\nX1 P N sky130_fd_pr__cap_mim_m3_{plate} w=2 l=10 m=1\n.ends independent\n'
    text += '.include '+Path(native).as_posix()+'\n'
    for key in PATHS:
        dc = '' if fault == 'missing-bias' else f'DC {high:g} '
        text += f'VP_{key} p_{key} 0 {dc}AC 1\nVN_{key} n_{key} 0 DC {low:g} AC 0\n'
        text += f'X_{key} p_{key} n_{key} '+('device_coupon' if key == 'extracted' else key)+'\n'
    for key in PROBES:
        text += f'VPAR_{key} par_{key} 0 DC {{{key}}} AC {{{key}}}\n'
    saves = [f'{kind}({prefix}_{key})' for key in PATHS for kind, prefix in (('v','p'), ('v','n'), ('i','vp'), ('i','vn'))]
    saves += [f'v(par_{key})' for key in PROBES]
    return text+('.op\n' if analysis == 'op' else '.ac dec 1 1k 10G\n')+'.save '+' '.join(saves)+'\n.end\n'


def execute_case(context, binding, staged, contract, out, engine, env, identity):
    plate, section, rotation, bias = context
    name = case_name(*context); folder = out/name; folder.mkdir()
    key = f'p{plate}-r{rotation}'
    native = out/'normalized'/key/'extracted.spice'
    reference = (out/'normalized'/key/'schematic.spice').read_text()
    coefficients = contract['passive_sections'][section]['coefficients']
    row = dict(name=name, plate=plate, section=section, rotation=rotation, bias_V=bias,
        gui_case=key, gui_job_id=binding['cases'][key]['job_id'], native_original_sha256=binding['cases'][key]['hashes']['native'],
        native_path=str(native), native_sha256=sha(native), status='RUNNING', analyses={}, controls=[])
    def run(analysis, fault=None):
        dest = folder/('controls/'+fault if fault else analysis); dest.mkdir(parents=True)
        deck, raw = dest/'probe.cir', dest/'probe.raw'
        text = circuit(reference, native, staged[section], plate, bias, analysis, identity, name, fault)
        deck.write_bytes(text.encode())
        command = [str(engine), '-n', '-D', 'filetype=ascii', '-D', 'ngbehavior=hsa', '-b', '-r', str(raw), str(deck)]
        with (dest/'console.log').open('wb') as log:
            process = subprocess.run(command, cwd=dest, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=90)
        require(process.returncode == 0, 'Native engine failed; see '+str(dest/'console.log'))
        require(re.findall(r'^Title:[ \t]*(.*)$', raw.read_text(), re.M) == [context_title(identity, name, analysis, fault)],
                'Native raw context differs.')
        high, low = applied(bias, fault)
        result = measure_op(raw, high, coefficients, low) if analysis == 'op' else measure_ac(raw, plate, coefficients)
        result.update(command=command, cwd=str(dest), environment=env, returncode=process.returncode,
                      deck_sha256=sha(deck), log_sha256=sha(dest/'console.log'))
        if fault:
            try:
                measure_op(raw, bias, coefficients)
            except ValueError as error:
                require('Actual signed OP terminal voltage' in str(error), 'Fault failed for an unrelated reason.')
                result.update(fault=fault, detected=True, intended_bias_V=bias, applied_bias_V=high, applied_ground_V=low, rejection=str(error))
            else:
                raise ValueError('Wrong-bias control was accepted.')
        return result
    try:
        for analysis in ('op', 'ac'):
            row['analyses'][analysis] = run(analysis)
        row['controls'] = [run('op', fault) for fault in faults(bias)]
        row['status'] = 'PASS'
    except Exception:
        row.update(status='FAIL', error=traceback.format_exc())
    write(folder/'record.json', row)
    return row


def run(gui_root, out, expected_commit=None, *, source_pilot=False, source_engine=None, pilot=False, workers=2):
    require(workers in range(1, 5), 'Use one to four electrical workers.')
    out = inputs.gui.unlinked(out).resolve()
    require(not out.exists() and not any(c.isspace() for c in str(out)), 'Use a fresh electrical output path without whitespace.')
    out.mkdir(parents=True)
    report = dict(schema=1, gate='mim-installed-electrical60', status='RUNNING', mode='source-pilot' if source_pilot else 'installed',
        qualified=False, release_ready=False, signoff=False, full_mim_installed=False, installed_electrical_acceptance=False,
        execution_root=str(out), execution_id=uuid.uuid4().hex, cases=[], pilot=pilot,
        scope='Four fresh GUI native inputs and selected source-fixed linear-model electrical contexts; no silicon/leakage/reliability or complete MiM/foundry qualification.')
    started = time.monotonic()
    try:
        binding = inputs.bind_gui(gui_root, expected_commit, source_pilot=source_pilot)
        write(out/'inputs.json', binding)
        contract, mapped = inputs.contracts(binding); write(out/'mapped-sources.json', mapped)
        for name, path in (('contract.json', inputs.CONTRACT_PATH), ('bias-contract.json', inputs.MAP_PATH)):
            (out/name).write_bytes((ROOT/path).read_bytes())
        sources = inputs.source_files()
        if not source_pilot:
            inputs.candidate_sources(sources, expected_commit)
        write(out/'source-files.json', sources)
        for name, digest in sources.items():
            target = out/'source'/name; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT/name).read_bytes()); require(sha(target) == digest, 'Source changed during capture.')
        for key, case in binding['cases'].items():
            for kind, path in case['files'].items():
                target = out/'gui-inputs'/key/(kind+Path(path).suffix); target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(Path(path).read_bytes())
                require(sha(target) == case['hashes'][kind], 'GUI input changed while copying.')
            folder = out/'normalized'/key; folder.mkdir(parents=True)
            for kind, filename, top in (('native', 'extracted.spice', 'device_coupon'), ('reference', 'schematic.spice', 'schematic')):
                (folder/filename).write_bytes(normalized(Path(case['files'][kind]).read_text(), case['top'], top).encode())
        tech = inputs.technology(binding)
        require(tech['simulation'].get('ngspice_compatibility') == 'hsa', 'Unexpected packaged simulator compatibility mode.')
        staged, model_files = stage_models(tech, out); write(out/'model-files.json', model_files)
        (out/'contract-sources').mkdir(); (out/'contract-sources/package').write_bytes((Path(tech['package_root'])/'package.json').read_bytes())
        engine = inputs.select_engine(binding, source_engine)
        env = inputs.native_environment(binding, engine, out)
        before = inputs.runtime(binding, engine, env); write(out/'runtime-before.json', before)
        contexts = selected([1,2], ['tt'] if pilot else list(SECTIONS), [0,90], [0] if pilot else [-5,0,5])
        identity = dict(execution_root=str(out), execution_id=report['execution_id'], gui_execution_id=binding['execution_id'],
                        inputs_sha256=sha(out/'inputs.json'), engine_sha256=sha(engine))
        report.update(inputs_sha256=sha(out/'inputs.json'), expected_commit=expected_commit, context_identity=identity,
            selected_cases=[case_name(*v) for v in contexts], simulation_package=binding['simulation_package'],
            domain_controls=domain_controls(), contract_sha256=inputs.CONTRACT_SHA, source_map_sha256=inputs.MAP_SHA,
            source_files_sha256=sha(out/'source-files.json'), runtime_before_sha256=sha(out/'runtime-before.json'))
        write(out/'qualification.json', report)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            jobs = [pool.submit(execute_case, context, binding, staged, contract, out, engine, env, identity) for context in contexts]
            for job in as_completed(jobs):
                row = job.result(); report['cases'].append(row); write(out/'qualification.json', report)
                print(row['name'], row['status'], row.get('error', ''), flush=True)
        after = inputs.runtime(binding, engine, env); write(out/'runtime-after.json', after)
        require(before == after, 'Simulator runtime changed during execution.')
        require(sources == inputs.source_files(), 'Qualification source changed during execution.')
        require(binding == inputs.bind_gui(gui_root, expected_commit, source_pilot=source_pilot), 'GUI/native/package prerequisite changed.')
        require(mapped == inputs.contracts(binding)[1], 'Reviewed public inputs changed.')
        require(model_files == inputs.inventory(out/'shared-models', ('source-identity.json',)), 'Staged models changed.')
        require(len(report['cases']) == len(contexts) and all(v['status'] == 'PASS' for v in report['cases']), 'Electrical cases failed.')
        report.update(status='PASS', runtime_after_sha256=sha(out/'runtime-after.json'),
            input_guards=dict(runtime=True, sources=True, gui=True, public_contract=True, staged_models=True),
            installed_electrical_acceptance=not source_pilot and not pilot)
    except Exception:
        report.update(status='FAIL', error=traceback.format_exc(), installed_electrical_acceptance=False)
    report['cases'].sort(key=lambda row: row['name']); report['seconds'] = time.monotonic()-started
    write(out/'qualification.json', report)
    write(out/'manifest.json', inputs.inventory(out, ('manifest.json',)))
    if report['status'] == 'PASS':
        from scripts.audit_installed_sky130_mim_electrical import audit
        try:
            audited = audit(out)
            write(out/'audit.json', audited)
        except Exception:
            write(out/'audit.json', dict(status='FAIL', error=traceback.format_exc(), installed_electrical_acceptance=False))
            raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui-root', type=Path, required=True, help='Frozen checker output; direct physical probe output only with --source-pilot.')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--expected-commit')
    parser.add_argument('--source-pilot', action='store_true')
    parser.add_argument('--source-engine', type=Path)
    parser.add_argument('--pilot', action='store_true', help='Four zero-bias tt contexts only; never full installed electrical acceptance.')
    parser.add_argument('--workers', type=int, choices=range(1,5), default=2)
    a = parser.parse_args()
    report = run(a.gui_root, a.out, a.expected_commit, source_pilot=a.source_pilot,
                 source_engine=a.source_engine, pilot=a.pilot, workers=a.workers)
    print(json.dumps({k: report.get(k) for k in ('status', 'mode', 'installed_electrical_acceptance', 'seconds', 'error')}, indent=2))
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
