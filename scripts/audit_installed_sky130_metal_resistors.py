"""Independent live audit of fresh GUI-linked metal-resistor electrical evidence.

The producer is not imported. Existing independent raw parsing and analytical
math are reused, while wrappers, original-input mutations and provenance are
checked here. Source pilots never qualify an installed application.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import installed_metal_resistor_inputs as inputs
from scripts import verify_frozen_metal_resistors as gui
from scripts import audit_sky130_metal_resistors_linked as raw

require, sha, load = gui.require, gui.sha, gui.load
FAULTS = ('wrong-width', 'wrong-length', 'wrong-model', 'wrong-multiplicity', 'disconnected-terminal')


def normalized_original(data, top):
    """Independently locate the only legal byte edits; no primitive rewriting."""
    require(re.fullmatch('[A-Za-z][A-Za-z0-9_]*', top or ''), 'Invalid original subcircuit name.')
    headers = list(re.finditer(rb'(?im)^[ \t]*\.subckt[ \t]+(\S+)[ \t]+R1[ \t]+R2[ \t]*\r?$', data))
    endings = list(re.finditer(rb'(?im)^[ \t]*\.ends(?:[ \t]+(\S+))?[ \t]*\r?$', data))
    directives = re.findall(rb'(?im)^[ \t]*(\.[^ \t\r\n]+)', data)
    require(len(headers) == len(endings) == 1 and headers[0][1] == top.encode() and
            endings[0][1] in (None, top.encode()) and [v.lower() for v in directives] == [b'.subckt', b'.ends'],
            'Original subcircuit interface/directives differ.')
    changes = [dict(start=m.start(1), stop=m.end(1), before=top, after='coupon')
               for m in (headers[0], endings[0]) if m[1] is not None]
    value = data
    for change in reversed(changes): value = value[:change['start']]+b'coupon'+value[change['stop']:]
    proof = dict(kind='top-subcircuit-name-only', original_top=top, normalized_top='coupon', edits=changes,
        original_sha256=hashlib.sha256(data).hexdigest(), normalized_sha256=hashlib.sha256(value).hexdigest())
    return value, proof


def fault_original(data, row, fault):
    """Reconstruct exactly one parameter/model/terminal change from original bytes."""
    require(fault in FAULTS, 'Unknown electrical fault.')
    matches = [m for m in re.finditer(rb'(?m)^[^\r\n]+', data) if m[0].strip() and not m[0].lstrip().startswith((b'*', b'.'))]
    require(len(matches) == 1, 'Fault input must have one primitive.')
    line = matches[0]; tokens = list(re.finditer(rb'\S+', line[0])); values = [m[0].decode() for m in tokens]
    gui.circuit(data.decode(), 'coupon', row['model'], row['width_um'], row['length_um'])
    if fault == 'wrong-model':
        index = 3; value = 'sky130_fd_pr__res_generic_'+('m3' if row['model'] in ('m1', 'm2') else 'm1')
    elif fault == 'disconnected-terminal': index = 1; value = '0'
    else:
        key = {'wrong-width':'w', 'wrong-length':'l', 'wrong-multiplicity':'m'}[fault]
        found = [i for i, token in enumerate(values) if token.startswith(key+'=')]
        require(len(found) == 1, 'Fault parameter is ambiguous.'); index = found[0]
        value = key+'='+format(float(values[index].split('=')[1])*(2 if key == 'm' else 1.2), '.17g')
    start, stop = line.start()+tokens[index].start(), line.start()+tokens[index].end()
    altered = data[:start]+value.encode()+data[stop:]
    proof = dict(kind=fault, edits=[dict(start=start, stop=stop, before=values[index], after=value)],
        original_sha256=hashlib.sha256(data).hexdigest(), mutated_sha256=hashlib.sha256(altered).hexdigest())
    return altered, proof


def input_copies(root, binding):
    normalized = load(root/'normalized-inputs.json'); faults = load(root/'fault-inputs.json')
    expected = {name for name, row in binding['cases'].items() if row['model'] in raw.MODELS}
    require(len(expected) == 24 and set(normalized) == set(faults) == expected, 'Original GUI/native input coverage differs.')
    inventories = {name:{} for name in ('original-inputs', 'normalized-inputs', 'fault-inputs')}
    for name in sorted(expected):
        row = binding['cases'][name]
        require(set(normalized[name]) == {'application', 'native'} and set(faults[name]) == set(FAULTS), 'Input path/fault coverage differs.')
        for kind, source_key in (('application', 'reference'), ('native', 'native')):
            path = gui.unlinked(row['files'][source_key]).resolve(); data = path.read_bytes()
            require(sha(path) == row['hashes'][source_key], 'Current GUI/native file changed.')
            gui.circuit(data.decode(), row['top'], row['model'], row['width_um'], row['length_um'], extracted=kind == 'native')
            retained = root/'original-inputs'/name/(kind+'.spice')
            target = root/'normalized-inputs'/name/(kind+'.spice')
            require(retained.read_bytes() == data, 'Retained original GUI/native bytes differ.')
            value, proof = normalized_original(data, row['top'])
            require(target.read_bytes() == value, 'Normalized input changed beyond top-name tokens.')
            expected_row = dict(original_path=str(path), original_sha256=sha(path), retained_path=str(retained),
                normalized_path=str(target), normalized_sha256=sha(target), proof=proof)
            require(normalized[name][kind] == expected_row, 'Original/normalized provenance differs.')
            inventories['original-inputs'][f'{name}/{kind}.spice'] = sha(retained)
            inventories['normalized-inputs'][f'{name}/{kind}.spice'] = sha(target)
            if kind == 'application':
                for fault in FAULTS:
                    fault_path = root/'fault-inputs'/name/(fault+'.spice'); changed, mutation = fault_original(value, row, fault)
                    require(fault_path.read_bytes() == changed, 'Fault changed more than its declared single token.')
                    require(faults[name][fault] == dict(path=str(fault_path), sha256=sha(fault_path),
                        source_sha256=sha(target), proof=mutation), 'Fault mutation provenance differs.')
                    inventories['fault-inputs'][f'{name}/{fault}.spice'] = sha(fault_path)
    for name, expected_files in inventories.items():
        require(gui.inventory(root/name) == expected_files, 'Unexpected retained or derived input files: '+name)
    return normalized, faults


def execution_identity(root, report):
    require(report['execution_directory'] == str(root) and not any(c.isspace() for c in str(root)), 'Execution directory differs or contains unsupported whitespace.')
    # Path.as_uri encodes a Windows drive as /C:/...; URI decoding removes no
    # path components. Check that mapping independently of the producer helper.
    portable = root.as_posix()
    if os.name == 'nt':
        drive = PureWindowsPath(str(root)).drive
        require(re.fullmatch('[A-Za-z]:', drive), 'Network drive execution is outside this profile.')
        portable = '/'+portable
    expected = dict(root=portable, nonce=report['execution']['nonce'])
    require(re.fullmatch('[0-9a-f]{32}', expected['nonce']) and report['execution'] == expected, 'Electrical context URI/root identity differs.')
    return expected


def check_deck(root, spec, case, rows, selected, normalized, faults, execution):
    section = case['section']; temperature = case['temperature_c']; analysis = case['analysis']
    if case['control'] == 'wrong-section': section = raw.SECTIONS[(raw.SECTIONS.index(section)+1)%5]
    if case['control'] == 'wrong-temperature': temperature += 17
    options = '.option reltol=1e-7 abstol=1e-15 vntol=1e-12 method=gear'
    if analysis == 'tran': options += ' chgtol=1e-24 trtol=1'
    lines = [raw.context_title(execution, case['name']), *selected[section].splitlines(), options, f'.temp {temperature}']
    e = spec['experiment']
    pulse = ' '.join(format(e[k], '.17g') for k in ('pulse_low_v', 'pulse_high_v', 'pulse_delay_s',
        'pulse_edge_s', 'pulse_edge_s', 'pulse_width_s', 'pulse_period_s'))
    lines.append('VDRIVE input 0 '+('PULSE('+pulse+')' if analysis == 'tran' else 'DC .0005')+' AC 1')
    used = set()
    for row in rows:
        tag = row['branch']; lines.append(f'VS_{tag} input in_{tag} DC 0 AC 0')
        if row['kind'] == 'analytic':
            value = raw.resistance(spec, row, case['section'], case['temperature_c'])
            lines.append(f'RC_{tag} in_{tag} out_{tag} {value:.17g}')
        else:
            key = f'{row["model"]}-g{row["geometry_index"]}-r{row["rotation"]}'; fault = row['fault']
            wrapper = row['kind']+'_'+key.replace('-', '_')+('_'+fault.replace('-', '_') if fault else '')
            path = Path(faults[key][fault]['path'] if fault else normalized[key][row['kind']]['normalized_path'])
            require(path.is_relative_to(root) and not any(c.isspace() for c in str(path)), 'Wrapper input escapes its execution root.')
            if wrapper not in used:
                lines += [f'.subckt {wrapper} a b', '.include '+path.as_posix(), 'X_COUPON a b coupon', f'.ends {wrapper}']; used.add(wrapper)
            lines += [f'X_{tag}_{n} in_{tag} out_{tag} {wrapper}' for n in range(row['multiplicity'])]
        lines += [f'RL_{tag} out_{tag} 0 1', f'CL_{tag} out_{tag} 0 1n']
    coefficients = spec['sections'][section]['coefficients']
    lines += [f'VP_{name} par_{name} 0 DC {{{name}}} AC {{{name}}}' for name in coefficients]
    if analysis == 'noise':
        lines += ['.control', 'set filetype=ascii']
        for index, row in enumerate(rows):
            tag = row['branch']; path = (root/case['name']/f'noise_{tag}.raw').as_posix()
            lines += [f'echo BEGIN_NOISE_{tag}', f'noise v(out_{tag}) VDRIVE dec 3 1k 10g', f'setplot noise{index*2+1}',
                f'let noise_{tag} = onoise_spectrum', f'write {path} frequency noise_{tag}', f'echo END_NOISE_{tag}']
        lines += ['quit 0', '.endc']
    else:
        names = ['v(input)', *[v for row in rows for v in (f'v(in_{row["branch"]})', f'v(out_{row["branch"]})', f'i(vs_{row["branch"]})')],
                 *[f'v(par_{name})' for name in coefficients]]
        lines += ['.save '+' '.join(names), dict(dc='.dc VDRIVE -.001 .001 .0001', ac='.ac dec 3 1k 10g', tran='.tran 20p 21n')[analysis]]
    raw.same_lines((root/case['name']/'input.cir').read_text(), [*lines, '.end'])
    return section, temperature


def check_execution(root, case, runtime):
    folder = root/case['name']; command = [runtime['engine'], '-n', '-D', 'filetype=ascii', '-D', 'ngbehavior=hsa', '-b']
    if case['analysis'] != 'noise': command += ['-r', str(folder/'result.raw')]
    command += [str(folder/'input.cir')]
    require(case.get('status') == 'PASS' and type(case.get('returncode')) is int and case['returncode'] == 0 and
            case['command'] == command and case['cwd'] == str(root) and case['environment'] == runtime['environment'] and
            not case.get('error'), 'Electrical command/engine/environment/outcome differs.')
    require(case['deck_sha256'] == sha(folder/'input.cir') and case['log_sha256'] == sha(folder/'console.log'), 'Native deck/console digest differs.')
    console = (folder/'console.log').read_text(errors='replace')
    require(not re.search(r'error|unknown parameter|unknown subckt|singular matrix|timestep too small', console, re.I), 'Native engine reported a failure.')
    if case['analysis'] != 'noise':
        require(case['raw_sha256'] == sha(folder/'result.raw'), 'Native raw digest differs.')
    else:
        expected = [r['branch'] for r in case['branches']]
        require(re.findall(r'^BEGIN_NOISE_(\S+)\s*$', console, re.M) == expected and
                re.findall(r'^END_NOISE_(\S+)\s*$', console, re.M) == expected, 'Noise analyses did not complete in order.')


def runtime_binding(root, report, binding, installed):
    before = load(root/'runtime-before.json')
    require(before == load(root/'runtime-after.json') and sha(root/'runtime-before.json') == report['runtime_before_sha256'] and
            sha(root/'runtime-after.json') == report['runtime_after_sha256'], 'Simulator runtime changed.')
    require(before['platform'] in installed['runtime_profiles'] and before['platform'] == sys.platform and
            before['sha256'] == installed['runtime_profiles'][before['platform']]['sha256'], 'Unreviewed simulator profile.')
    engine = inputs.select_engine(binding, Path(before['engine']) if binding['mode'] == 'source-pilot' else None)
    environment = inputs.native_environment(binding, engine, root)
    require(before['environment'] == environment and inputs.runtime(binding, engine, environment) == before,
            'Live engine/configuration/dependency identity differs.')
    assets = {**before['files'], **{r['resolved']: r['sha256'] for r in before['elf_dependencies'].values()}}
    require(load(root/'runtime-assets.json') == assets and
            gui.inventory(root/'runtime-assets') == {value:value for value in set(assets.values())},
            'Retained runtime closure is incomplete or changed.')
    return before


def audit(root, reviewed_source=None):
    root = gui.unlinked(root).resolve(); manifest = load(root/'manifest.json')
    require(manifest == gui.inventory(root, ('manifest.json', 'audit.json')), 'Complete electrical evidence inventory differs.')
    report = load(root/'qualification.json')
    require(report.get('schema') == 1 and report.get('gate') == 'sky130-metal-installed-electrical-v1' and
            report.get('status') == 'PASS' and report.get('mode') in ('source-pilot', 'installed') and
            type(report.get('pilot')) is bool and not report.get('error') and
            all(report.get(name) is False for name in ('qualified', 'installed_acceptance', 'full_family', 'chunk_complete', 'release_ready', 'signoff')),
            'Incomplete or overclaimed electrical report.')
    require(report.get('input_guards') == dict(runtime=True, sources=True, gui=True, public_contract=True,
            simulation_package=True, staged_models=True, retained_inputs=True), 'Missing final input guards.')
    require(report['installed_electrical_acceptance'] is (report['mode'] == 'installed' and not report['pilot']), 'Source/pilot installed claim differs.')
    execution = execution_identity(root, report); binding = load(root/'inputs.json')
    require(sha(root/'inputs.json') == report['inputs_sha256'] and binding['mode'] == report['mode'] and
            binding['expected_commit'] == report['expected_commit'] and binding['execution_id'] == report['gui_execution_id'], 'GUI input receipt differs.')
    require(inputs.bind_gui(binding['supplied_root'], binding['expected_commit'], source_pilot=binding['mode'] == 'source-pilot') == binding,
            'Fresh GUI/native prerequisites no longer re-audit.')
    installed, spec, mapped = inputs.contracts(binding)
    require(sha(root/'installed-contract.json') == report['installed_contract_sha256'] == inputs.CONTRACT_SHA and
            sha(root/'contract.json') == report['contract_sha256'] == installed['source_contract']['sha256'] == raw.CONTRACT_SHA and
            load(root/'contract-sources.json') == mapped and sha(root/'contract-sources.json') == report['contract_sources_sha256'],
            'Reviewed contract/source bindings differ.')
    sources = load(root/'source-files.json')
    require(sha(root/'source-files.json') == report['source_files_sha256'] and gui.inventory(root/'source') == sources and
            sources == inputs.source_files(), 'Captured/executing source closure differs.')
    for name, digest in sources.items():
        if reviewed_source is not None:
            require(sha(gui.confined(reviewed_source, name)) == digest, 'Captured source differs from independently reviewed source.')
    if binding['mode'] == 'installed': inputs.candidate_sources(sources, binding['expected_commit'])
    for name, row in spec['engine_sources'].items():
        require(sha(gui.confined(root/'engine-reference', name)) == row['sha256'], 'Primitive reference source differs.')
    require(report['simulation_package'] == binding['simulation_package'], 'Simulation package claim differs.')
    package, selected = raw.model_closure(root, spec, manifest)
    require(sha(root/'original-package/package.json') == binding['simulation_package']['manifest_sha256'], 'Copied simulation package differs.')
    require(report['normalized_inputs_sha256'] == sha(root/'normalized-inputs.json') and
            report['fault_inputs_sha256'] == sha(root/'fault-inputs.json'), 'Retained input receipt differs.')
    normalized, faults = input_copies(root, binding); runtime = runtime_binding(root, report, binding, installed)
    logical, contexts = raw.selection(spec, report['pilot'])
    require(report['logical_rows'] == logical and report['selected_cases'] == [v['name'] for v in contexts], 'Electrical selection differs.')
    cases = {v['name']:v for v in report['cases']}
    require(len(cases) == len(report['cases']) == len(contexts) and set(cases) == {v['name'] for v in contexts}, 'Missing/duplicated electrical cases.')
    samples = rejected = 0; maximum = {name:0.0 for name in ('dc', 'ac', 'tran', 'noise')}
    conditions = {name:0 for name in maximum}
    for case in contexts:
        row = cases[case['name']]; folder = root/case['name']
        require(load(folder/'record.json') == row and all(row[k] == v for k, v in case.items()), 'Case context/receipt differs.')
        branches = raw.branches(logical, case); require(row['branches'] == branches, 'Electrical branch coverage differs.')
        section, temperature = check_deck(root, spec, case, branches, selected, normalized, faults, execution)
        require(row['actual_section'] == section and row['actual_temperature_c'] == temperature, 'Actual operating context differs.')
        check_execution(root, row, runtime)
        observed, count = raw.check_observation(root, spec, case, branches, execution)
        samples += observed['samples']; rejected += count
        if case['control'] == 'positive':
            raw.compare_summary(row['observation'], observed)
            conditions[case['analysis']] += sum(r['kind'] == 'analytic' for r in branches)
        else:
            require(isinstance(row.get('detected'), str) and row['detected'] and count == 2*len(logical), 'Wrong-context control is incomplete.')
        maximum[case['analysis']] = max(maximum[case['analysis']], max(v['maximum_normalized_error'] for v in observed['branches'].values()))
    counts = dict(contexts=len(contexts), logical_variants=len(logical), fresh_gui_native_inputs=24,
        dc_conditions=conditions['dc'], ac_conditions=conditions['ac'], transient_conditions=conditions['tran'],
        noise_conditions=conditions['noise'], detected_branch_controls=rejected)
    expected = (dict(contexts=6, logical_variants=4, fresh_gui_native_inputs=24, dc_conditions=4, ac_conditions=4,
        transient_conditions=4, noise_conditions=2, detected_branch_controls=26) if report['pilot'] else
        dict(contexts=90, logical_variants=48, fresh_gui_native_inputs=24, dc_conditions=720, ac_conditions=720,
        transient_conditions=720, noise_conditions=120, detected_branch_controls=4680))
    require(counts == expected, 'Acceptance totals differ.')
    return dict(schema=1, status='PASS', mode=report['mode'], expected_commit=report['expected_commit'],
        gui_execution_id=binding['execution_id'], installed_electrical_acceptance=report['installed_electrical_acceptance'],
        qualified=False, signoff=False, full_family=False, chunk_complete=False, release_ready=False,
        qualification_sha256=sha(root/'qualification.json'), inputs_sha256=sha(root/'inputs.json'), manifest_sha256=sha(root/'manifest.json'),
        counts=counts, branch_samples=samples, maximum_normalized_errors=maximum,
        runtime_check='live actual engine/configuration/dependencies and retained bytes',
        source_binding='all captured files compared to reviewed source' if reviewed_source is not None else 'captured and current source closure')


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--reviewed-source', type=Path); parser.add_argument('--out', type=Path)
    args = parser.parse_args(); result = audit(args.root, args.reviewed_source)
    if args.out: inputs.write(args.out, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()

