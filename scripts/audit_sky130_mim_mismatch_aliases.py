"""Independent offline readback of the finite Windows46/Linux42 MiM experiment.

This checks retained source integration, not statistical calibration, installed
acceptance or manufacturing. It never calls the producer's acceptance helpers.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import posixpath
import re

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = 'docs/qualification/sky130-mim-mismatch-aliases-v1.json'
CONTRACT_SHA = 'b31cff4a8fbbd844a759f16ec7a61c34c590a76ed330c31f325a0d182259a400'
ENGINE_SHA = '86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453'
WINDOWS_MANIFEST_SHA = 'cbab1800c150230ca734815a95a6a6023481031cbf98ed2a9d3c07dcef444c77'
LINUX_ENGINE_SHA = '820658317b0b54035208da41936fd6871ce924036e5ea4113a4168b821b7fc45'
# Exact previously reviewed apt42 files and resolved ELF closure, including
# loader cache and ngspice configuration; deliberately no generic Linux fallback.
# Original runtime-before.json SHA8464420accfda9882f2835ba2e22da7d99c618b83d3b4f1dc24dd767db1896c6.
LINUX_CLOSURE_SHA = 'f4d85587f132b7773158f11fcfb3d074c072fb9a9db7b8b6f047e9062409fc6b'
SECTIONS = ('tt', 'll', 'hh', 'hl', 'lh')
PARAMETERS = ('rm3', 'rm4', 'rcvia3', 'rcvia4', 'tol_m3', 'tol_m4', 'camimc', 'cpmimc', 'm3_dw', 'm4_dw', 'mc_mm_switch', 'mc_pr_switch')
TAGS = tuple(f'p{plate}t{trial}' for plate in (1, 2) for trial in range(4))
FLAGS = ('qualified', 'installed_acceptance', 'full_mim_installed', 'chunk_complete', 'release_ready', 'signoff')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'Duplicated JSON key: ' + key)
        result[key] = value
    return result


def load(path):
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + value)))


def relative(name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name and
            not PurePosixPath(name).is_absolute() and all(p not in ('', '.', '..') for p in name.split('/')),
            'Unsafe evidence member.')
    return name


def inventory(root):
    root = Path(root)
    for path in (root, *root.parents):
        require(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(), 'Linked evidence root.')
    result = {}
    for folder, directories, names in os.walk(root, followlinks=False):
        for name in directories + names:
            path = Path(folder) / name
            require(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(), 'Linked evidence member.')
        for name in names:
            path = Path(folder) / name
            require(path.is_file(), 'Nonregular evidence member.')
            result[relative(path.relative_to(root).as_posix())] = sha(path)
    return result


def cases(pilot):
    require(type(pilot) is bool, 'Invalid pilot flag.')
    result = {}
    for section in SECTIONS[:1] if pilot else SECTIONS:
        items = [(m, v) for m in (1, 4) for v in ('application-alias', 'literal-alias', 'application-base')]
        items += [(1, 'wrong-alias'), (4, 'wrong-mf'), (4, 'missing-m')]
        for m, variant in items:
            actual = SECTIONS[(SECTIONS.index(section) + 1) % 5] if variant == 'wrong-alias' else section
            actual += '' if variant == 'application-base' else '_mm'
            name = f'{section}-m{m}-{variant}'
            result[name] = dict(name=name, section=section, multiplier=m, variant=variant, actual_section=actual)
    return result


def native_path(value):
    return PurePosixPath(value) if value.startswith('/') else PureWindowsPath(value)


def context_title(execution, name):
    require(set(execution) == {'root', 'nonce'} and native_path(execution['root']).is_absolute() and
            re.fullmatch('[0-9a-f]{32}', execution['nonce']), 'Invalid original execution identity.')
    token = hashlib.sha256(json.dumps({'execution': execution, 'case': name}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return '* icstudio-mim-mismatch-v1 ' + token


def coefficients(section, spec):
    base = section.removesuffix('_mm')
    require(base in SECTIONS and section in (base, base + '_mm'), 'Unknown selected alias.')
    return {**spec['sections'][base]['coefficients'], 'mc_mm_switch': int(section.endswith('_mm')), 'mc_pr_switch': 0}


def rc(plate, values):
    metal = plate + 2
    correction = 1e6 * (values[f'm{metal}_dw'] + values[f'tol_m{metal}'])
    width, length = 2 + correction, 10 + correction
    c = values['camimc'] * width * length + 2 * values['cpmimc'] * (width + length)
    pitch = {1: .56, 2: .73}[plate]
    r = values[f'rm{metal}'] * length / width + values[f'rcvia{metal}'] * pitch ** 2 / (width * length)
    return r, c


def calls(text, multiplier, variant='application-alias'):
    lines = [line.split() for line in text.splitlines() if line.strip()]
    require(len(lines) == 8, 'Instance coverage differs.')
    for tag, row in zip(TAGS, lines):
        require(row[:4] == ['X_' + tag, tag, '0', f'sky130_fd_pr__cap_mim_m3_{tag[1]}'], 'Model, terminal or replica order differs.')
        params = pairs([tuple(token.split('=', 1)) for token in row[4:]])
        require(set(params) == ({'w', 'l', 'mf'} if variant == 'missing-m' else {'w', 'l', 'mf', 'm'}), 'Parameter identity differs.')
        values = {k: float(v) for k, v in params.items()}
        expected = dict(w=2, l=10, mf=1 if variant == 'wrong-mf' else multiplier)
        if variant != 'missing-m':
            expected['m'] = multiplier
        require(values == expected, 'Width, length, MF or simulator m differs.')


def check_deck(text, case, selected, execution, application):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    require(lines[0] == context_title(execution, case['name']), 'Deck execution title differs.')
    prefix = [lines[0], *selected[case['actual_section']].splitlines(), '.option seed=20261024 tnom=27', '.temp 27']
    prefix += [f'V{tag} {tag} 0 DC 0 AC 1' for tag in TAGS]
    suffix = [f'Vpar_{key} par_{key} 0 DC {{{key}}} AC {{{key}}}' for key in PARAMETERS]
    channels = [v for tag in TAGS for v in (f'v({tag})', f'i(v{tag})')] + [f'v(par_{key})' for key in PARAMETERS]
    suffix += ['.save ' + ' '.join(channels), '.ac dec 1 1k 100k', '.end']
    require(len(lines) == len(prefix) + 8 + len(suffix) and lines[:len(prefix)] == prefix and lines[-len(suffix):] == suffix,
            'Deck alias, stimulus, seed, temperature, probes or extra statements differ.')
    instance_lines = lines[len(prefix):len(prefix) + 8]
    calls('\n'.join(instance_lines), case['multiplier'], case['variant'])
    if case['variant'].startswith('application') or case['variant'] == 'wrong-alias':
        require(instance_lines == application[case['multiplier']].splitlines(), 'Native application calls differ from saved application export.')


def read_raw(path, title):
    text = Path(path).read_bytes().decode('ascii').replace('\r\n', '\n')
    require(text.count('\nVariables:\n') == 1 and text.count('\nValues:\n') == 1, 'Missing or duplicated native raw plot.')
    header, body = text.split('\nVariables:\n')
    variables, data = body.split('\nValues:\n')
    def field(name):
        found = re.findall(r'^' + re.escape(name) + r':\s*(.*)$', header, re.M)
        require(len(found) == 1, 'Missing or duplicated raw header: ' + name)
        return found[0].strip()
    require(field('Title') == title.lower() and field('Plotname') == 'AC Analysis' and field('Flags') == 'complex', 'Raw title, analysis or value kind differs.')
    require(field('No. Variables') == '29' and field('No. Points') == '3', 'Raw channel or sample count differs.')
    expected = ['frequency'] + [v for tag in TAGS for v in (f'v({tag})', f'i(v{tag})')] + [f'v(par_{key})' for key in PARAMETERS]
    table = [line.split() for line in variables.splitlines() if line.strip()]
    require(len(table) == 29, 'Incomplete raw variable table.')
    for i, (row, name) in enumerate(zip(table, expected)):
        kind = 'frequency' if i == 0 else ('current' if name.startswith('i(') else 'voltage')
        require(row == [str(i), name, kind] or (i == 0 and row == ['0', 'frequency', 'frequency', 'grid=3']), 'Raw variable identity/order differs.')
    rows = [line.split() for line in data.splitlines() if line.strip()]
    require(len(rows) == 87, 'Truncated or extra raw samples.')
    numbers = []
    for i, row in enumerate(rows):
        require(len(row) == (2 if i % 29 == 0 else 1) and (i % 29 != 0 or row[0] == str(i // 29)), 'Raw sample index differs.')
        values = row[-1].split(','); require(len(values) == 2, 'Malformed complex sample.')
        value = complex(*map(float, values))
        require(math.isfinite(value.real) and (i % 29 == 0 or math.isfinite(value.imag)), 'Nonfinite physical sample.')
        numbers.append(value)
    return [dict(zip(expected, numbers[i:i + 29])) for i in range(0, 87, 29)]


def observe(path, case, execution, spec):
    samples = read_raw(path, context_title(execution, case['name']))
    expected = coefficients(case['actual_section'], spec)
    output = {tag: [] for tag in TAGS}
    measured = {tag: [] for tag in TAGS}
    actual_coefficients = None
    for sample, frequency in zip(samples, (1000, 10000, 100000)):
        require(abs(sample['frequency'].real / frequency - 1) <= 1e-12, 'Actual frequency differs.')
        for key, value in expected.items():
            require(abs(sample['v(par_' + key + ')'] - value) <= 1e-24 + abs(value) * 1e-10, 'Effective alias coefficient/switch differs: ' + key)
            require(sample['v(par_' + key + ')'].imag == 0, 'Effective coefficient has a phase.')
        actual = {key: sample['v(par_' + key + ')'].real for key in expected}
        require(actual_coefficients is None or actual_coefficients == actual, 'Effective coefficients changed with frequency.')
        actual_coefficients = actual
        m = 1 if case['variant'] == 'missing-m' else case['multiplier']
        for tag in TAGS:
            voltage, current = sample[f'v({tag})'], sample[f'i(v{tag})']
            require(abs(voltage - 1) <= 1e-12 and current != 0, 'Applied voltage or branch current differs.')
            z = -voltage / current
            require(z.real > 0 and z.imag < 0, 'Nonpassive or noncapacitive branch.')
            resistance, capacitance = z.real, -1 / (2 * math.pi * frequency * z.imag)
            r, c = rc(int(tag[1]), expected)
            require(abs(resistance / (r / m) - 1) <= 1e-6, 'Actual series resistance differs from source law.')
            if not case['actual_section'].endswith('_mm'):
                require(abs(capacitance / (c * m) - 1) <= 1e-6, 'Actual base capacitance differs from source law.')
            require(math.isfinite(capacitance) and capacitance > 0, 'Invalid capacitance.')
            output[tag].append(capacitance)
            measured[tag].append(dict(frequency_Hz=frequency, resistance_ohm=resistance, capacitance_F=capacitance))
    require(all(max(values) / min(values) - 1 <= 1e-8 for values in output.values()), 'Capacitance changes across selected frequencies.')
    caps = {tag: values[0] for tag, values in output.items()}
    return dict(coefficients=actual_coefficients, capacitances=caps,
                raw_summary=dict(coefficients=actual_coefficients, samples=measured, capacitances_F=caps))


def compare(observations, sections):
    results = []
    for section in sections:
        def cap(m, variant): return observations[f'{section}-m{m}-{variant}']['capacitances']
        baseline, alias = cap(1, 'application-base'), cap(1, 'application-alias')
        delta = {tag: alias[tag] / baseline[tag] - 1 for tag in TAGS}
        for plate in (1, 2):
            require(max(abs(delta[tag]) for tag in TAGS if tag.startswith(f'p{plate}')) > 1e-5, 'Mismatch alias produced no observable variation.')
        mapping = scaling = base_scaling = 0
        for m in (1, 4):
            actual, literal, base = cap(m, 'application-alias'), cap(m, 'literal-alias'), cap(m, 'application-base')
            for tag in TAGS:
                mapping = max(mapping, abs(actual[tag] / literal[tag] - 1))
                scaling = max(scaling, abs(actual[tag] / (m * baseline[tag]) - 1 - delta[tag] / math.sqrt(m)))
                base_scaling = max(base_scaling, abs(base[tag] / (m * baseline[tag]) - 1))
        require(max(mapping, scaling, base_scaling) <= 1e-9, 'Literal/application mapping or paired seeded MF/m scaling differs.')
        intended = observations[f'{section}-m1-application-alias']['coefficients']
        for name in ('wrong-alias', 'application-base'):
            require(observations[f'{section}-m1-{name}']['coefficients'] != intended, 'Wrong/disabled alias control escaped selection check.')
        for variant in ('wrong-mf', 'missing-m'):
            wrong, correct = cap(4, variant), cap(4, 'application-alias')
            require(all(abs(wrong[tag] / correct[tag] - 1) > 1e-9 for tag in TAGS), 'Wrong MF/m control escaped detection.')
        results.append(dict(section=section, max_relative_mapping=mapping, max_absolute_fractional_mf_scaling=scaling,
                            max_relative_base_scaling=base_scaling, unit_fractional_deltas=delta,
                            detected_controls=['wrong-alias', 'disabled-mismatch', 'wrong-mf', 'missing-m']))
    return results


def models(root, spec, manifest):
    package_root = root / 'original-package'
    require(sha(package_root / 'package.json') == spec['package']['manifest_sha256'], 'Original package identity differs.')
    package = load(package_root / 'package.json')
    require(package['revision'] == spec['package']['revision'], 'Package revision differs.')
    files = {'package.json': spec['package']['manifest_sha256'], **package['files']}
    require(load(root / 'package-files.json') == files, 'Package inventory differs.')
    require({n[len('original-package/'):] for n in manifest if n.startswith('original-package/')} == set(files), 'Original package closure differs.')
    for name, digest in files.items():
        require(sha(package_root / relative(name)) == digest, 'Original model/package asset changed.')
    mapping = load(root / 'pdk-model-files.json')
    require(mapping and len(set(mapping.values())) == len(mapping), 'Staged dependency mapping is duplicated.')
    reverse = {value: key for key, value in mapping.items()}
    require(set(mapping) == {n for n in manifest if n.startswith('pdk-models/')}, 'Staged model closure differs.')
    require(load(root / 'staged-model-files.json') == {n[len('pdk-models/'):]: manifest[n] for n in mapping}, 'Staged model inventory differs.')
    pattern = re.compile(r'(?im)^[^\S\n]*(\.include|\.inc|\.lib)[^\S\n]+("[^"\n]+"|\'[^\'\n]+\'|[^\s]+)([^\n]*)')
    for staged, original in mapping.items():
        require(original in package['files'], 'Unbound model dependency.')
        expected = 'pdk-models/' + hashlib.sha256((original + '\0' + package['files'][original]).encode()).hexdigest()[:24] + '.spice'
        require(staged == expected, 'Staged model name differs from original lock.')
        source = (package_root / relative(original)).read_bytes().decode('utf-8')
        def rewrite(match):
            if match[1].lower() == '.lib' and not match[3].strip():
                return match[0]
            dependency = posixpath.normpath(posixpath.join(posixpath.dirname(original), match[2].strip('"\'')))
            require(dependency in reverse, 'Missing actual model dependency.')
            return match[1] + ' ' + reverse[dependency] + match[3]
        require((root / relative(staged)).read_bytes() == pattern.sub(rewrite, source).encode(), 'Staged model was changed beyond dependency relocation.')
    selected = {}
    for section in (v for s in SECTIONS for v in (s, s + '_mm')):
        lines = []
        for include in package['technology']['simulation']['includes']:
            name = reverse[include['path']]
            lines.append('.lib ' + name + ' ' + include['sections'][section] if 'sections' in include else '.include ' + name)
        selected[section] = '\n'.join(lines)
    require(load(root / 'selected-model-lines.json') == selected, 'Actual application library selection differs.')
    return package, selected


def runtime_profile(root, before, execution):
    engine = native_path(before['engine']); origin = native_path(execution['root'])
    require(engine.is_absolute() and origin.is_absolute(), 'Runtime or execution path is relative.')
    env = before['environment']
    expected = dict(LANG='C', LC_ALL='C', TZ='UTC', HOME=str(origin/'empty-home'), USERPROFILE=str(origin/'empty-home'),
                    TMP=str(origin/'temporary'), TEMP=str(origin/'temporary'))
    assets = load(root/'runtime-assets.json')
    if before['platform'] == 'win32':
        require(before['machine'] == 'AMD64' and before['sha256'] == ENGINE_SHA and engine.name == 'ngspice.exe'
                and isinstance(origin, PureWindowsPath), 'Unsupported reviewed Windows simulator profile.')
        system = PureWindowsPath(env['SystemRoot'])
        expected.update(SystemRoot=str(system), WINDIR=str(system), PATH=str(engine.parent)+';'+str(system/'System32'), SPICE_SCRIPTS=str(engine.parent))
        require(system.is_absolute() and not before['elf_dependencies'] and before['dependency_listing'] is None, 'Unexpected Windows loader profile.')
        manifest_path = str(engine.parent/'runtime-manifest.json')
        require(assets.get(manifest_path) == WINDOWS_MANIFEST_SHA, 'Unreviewed Windows companion manifest.')
        manifest = load(root/'runtime-assets'/WINDOWS_MANIFEST_SHA)
        locked = {str(engine.parent/relative(n)): d for n,d in manifest['files'].items()}
        locked[manifest_path] = WINDOWS_MANIFEST_SHA
        require(assets == locked == before['files'] and assets.get(str(engine)) == ENGINE_SHA, 'Windows runtime companion closure differs.')
    elif before['platform'] == 'linux':
        require(before['machine'] == 'x86_64' and str(engine) == '/usr/bin/ngspice' and before['sha256'] == LINUX_ENGINE_SHA
                and isinstance(origin, PurePosixPath), 'Unsupported reviewed Linux simulator profile.')
        expected.update(PATH='/usr/bin:/usr/bin:/bin', SPICE_SCRIPTS='/usr/share/ngspice/scripts')
        closure = {k:before[k] for k in ('files','elf_dependencies')}
        digest = hashlib.sha256(json.dumps(closure,sort_keys=True,separators=(',', ':')).encode()).hexdigest()
        require(digest == LINUX_CLOSURE_SHA, 'Linux configuration or complete resolved library closure differs.')
        require(assets == {**before['files'], **{v['resolved']:v['sha256'] for v in before['elf_dependencies'].values()}}, 'Incomplete retained Linux runtime assets.')
        listed = re.findall(r'(?:=>\s+)?(/[^\s]+)\s+\(address\)', before['dependency_listing'])
        require(len(listed) == len(set(listed)) and set(listed) == set(before['elf_dependencies']), 'Loader listing differs from resolved library closure.')
    else:
        raise ValueError('Unsupported reviewed simulator profile.')
    require(env == expected, 'Native execution environment differs.')
    for digest in assets.values():
        require(re.fullmatch('[0-9a-f]{64}', digest) and sha(root/'runtime-assets'/digest) == digest, 'Unbound retained runtime asset.')
    require({p.name for p in (root/'runtime-assets').iterdir()} == set(assets.values()), 'Retained runtime object closure differs.')
    return before


def runtime(root, report):
    before, after = load(root / 'runtime-before.json'), load(root / 'runtime-after.json')
    require(before == after and sha(root / 'runtime-before.json') == report['runtime_before_sha256'] and
            sha(root / 'runtime-after.json') == report['runtime_after_sha256'], 'Runtime changed or receipt differs.')
    return runtime_profile(root, before, report['execution'])


def audit(root):
    root = Path(root)
    manifest = load(root/'manifest.json'); actual = inventory(root); actual.pop('manifest.json')
    require(manifest == actual, 'Evidence inventory is incomplete, changed or has unexpected files.')
    report = load(root/'qualification.json')
    require(report['status'] == 'PASS' and report['mode'] == 'source-integration' and report['source_integration_acceptance'] is True and
            all(report.get(k) is False for k in FLAGS), 'Evidence scope or completion differs.')
    require(report['schema'] == 1 and report['gate'] == 'sky130-mim-mismatch-aliases-v1' and
            report['guards'] == dict(source=True,package=True,staged_models=True,runtime=True) and
            report['python']['dont_write_bytecode'] is True and report['python']['pycache_prefix'], 'Missing completion or execution guards.')
    require(report['contract_sha256'] == CONTRACT_SHA == sha(root/'contract.json'), 'Versioned contract differs.')
    spec = load(root/'contract.json')
    sources = load(root/'source-files.json')
    require(sha(root/'source-files.json') == report['source_files_sha256'] and
            {'source/'+n for n in sources} == {n for n in manifest if n.startswith('source/')}, 'Captured source closure differs.')
    for name, digest in sources.items():
        require(sha(root/'source'/relative(name)) == digest, 'Captured source changed.')
    for name in ('scripts/audit_sky130_mim_mismatch_aliases.py', 'tests/test_sky130_mim_mismatch_alias_audit.py'):
        require(sources.get(name) == sha(ROOT/name), 'Independent audit source was not bound to execution.')
    original = spec['original_contract']
    require(sources.get(original['path']) == original['sha256'], 'Original analytical contract not retained.')
    require(sources.get(CONTRACT) == CONTRACT_SHA and sources.get('scripts/qualify_sky130_mim_mismatch_aliases.py'), 'Missing producer/contract source.')
    package, selected = models(root, spec, manifest)
    rt = runtime(root, report)
    application = {}
    for m in (1, 4):
        project = load(root/f'project-m{m}.icproj')
        require(len(project['cells']) == 1 and len(project['cells'][0]['devices']) == 8, 'Saved project instance coverage differs.')
        require(project['pdk']['package_lock'] == {k: package[k] for k in ('id', 'revision', 'files')}, 'Saved package lock differs.')
        require({k:v for k,v in project['pdk'].items() if k not in ('package_root','package_lock')} == package['technology'], 'Saved package technology differs.')
        for tag, device in zip(TAGS, project['cells'][0]['devices']):
            require(device['name'] == tag and device['nets'] == dict(c0=tag, c1='0') and device['model_params'] == dict(w=2,l=10,mf=m) and
                    device['model_ref'] == dict(pdk='sky130A',revision=package['revision'],device=f'sky130_fd_pr/cap_mim_m3_{tag[1]}.sym'), 'Saved application device differs.')
        application[m] = (root/f'application-m{m}.spice').read_text(encoding='utf-8').strip()
        calls(application[m], m)
    expected = cases(report['pilot'])
    require(set(report['selected_cases']) == set(expected) and len(report['selected_cases']) == len(expected) and
            len(report['cases']) == len(expected) and {r['name'] for r in report['cases']} == set(expected), 'Native case selection is incomplete or duplicated.')
    observations = {}
    for record in report['cases']:
        case = expected[record['name']]; folder = root/case['name']; origin = native_path(report['execution']['root'])
        require(all(record[k] == v for k,v in case.items()) and record['status'] == 'PASS' and record['returncode'] == 0 and
                load(folder/'record.json') == record, 'Native case or completion identity differs.')
        command = [rt['engine'],'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(origin/case['name']/'result.raw'),str(origin/case['name']/'input.cir')]
        require(record['command'] == command and record['cwd'] == str(origin) and record['environment'] == rt['environment'], 'Native command or environment differs.')
        for name,key in (('input.cir','deck_sha256'),('result.raw','raw_sha256'),('console.log','log_sha256')):
            require(sha(folder/name) == record[key], 'Native artifact identity differs.')
        check_deck((folder/'input.cir').read_text(encoding='utf-8'), case, selected, report['execution'], application)
        log = (folder/'console.log').read_text(encoding='utf-8')
        require(re.findall(r'^No\. of Data Rows\s*:\s*(\d+)\s*$', log, re.M) == ['3'] and
                re.findall(r'Doing analysis at TEMP = ([0-9.+-]+) and TNOM = ([0-9.+-]+)', log) == [('27.000000','27.000000')] and
                'error' not in log.lower() and 'unknown parameter' not in log.lower(), 'Native completion/temperature differs.')
        observations[case['name']] = observe(folder/'result.raw', case, report['execution'], spec)
        require(record['raw'] == observations[case['name']]['raw_summary'], 'Saved numerical summary differs from actual raw output.')
    comparisons = compare(observations, SECTIONS[:1] if report['pilot'] else SECTIONS)
    require(report['comparisons'] == comparisons, 'Reported paired results differ from independent raw readback.')
    return dict(schema=1,status='PASS',mode='source-integration',qualified=False,installed_acceptance=False,full_mim_installed=False,
                chunk_complete=False,release_ready=False,signoff=False,qualification_sha256=sha(root/'qualification.json'),
                manifest_sha256=sha(root/'manifest.json'),auditor_sha256=sha(Path(__file__)),pilot=report['pilot'],
                counts=dict(native_runs=len(expected),replica_AC_observations=len(expected)*8*3,sections=len(comparisons),detected_control_conditions=len(comparisons)*4),
                comparisons=comparisons,runtime_platform=rt['platform'],runtime_check='Exact reviewed Windows46 or Linux42 retained engine/configuration/library bytes; not live host or hermetic OS',
                scope='Finite seeded alias/MF/m source integration only; literal calls share public compact models. No distribution/correlation, calibrated variation, installed, family or manufacturing qualification.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--out',type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    text = json.dumps(result,indent=2)+'\n'
    if args.out:
        require(not args.out.resolve().is_relative_to(args.root.resolve()) and not args.out.exists(), 'Use a new audit receipt outside immutable evidence.')
        args.out.write_text(text,encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
