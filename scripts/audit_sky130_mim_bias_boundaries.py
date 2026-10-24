"""Independent selected MiM DC boundary and linear-model integration readback.

Reads native OP and AC outputs independently of the producer. This is neither
silicon/leakage/reliability accuracy nor full operating-envelope qualification.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import audit_sky130_mim_passive_corners as passive

SOURCE_MAP_SHA = '549bb89580245515b5a7e2b43eb784fcfd3d621a57ff3141c10183da42c87830'
CONTRACT_SHA = 'b324813599a364c83e76e63f583e7b74da50ab8182640a1cb907796a3ce1c209'
BRANCHES = ('schematic', 'extracted', 'independent')
PARAMETERS = (*passive.PARAMETERS, 'mc_mm_switch', 'mc_pr_switch')
BIASES = (-5, 0, 5)
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
load = lambda path: json.loads(Path(path).read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_raw(path, analysis):
    """Parse exactly one real OP or complex AC plot, including native binary."""
    require(analysis in ('op', 'ac'), 'Unknown analysis.')
    data = Path(path).read_bytes()
    markers = list(re.finditer(rb'(?m)^(Values:|Binary:)\r?\n', data))
    require(len(markers) == 1, 'Missing or duplicated native raw plot.')
    marker = markers[0]
    header = data[:marker.start()].decode('utf-8').replace('\r\n', '\n')
    values = data[marker.end():]
    def field(name):
        matches = re.findall(r'^' + re.escape(name) + r':[ \t]*(.*)$', header, re.M)
        require(len(matches) == 1, 'Missing or duplicated raw header: ' + name)
        return matches[0].strip()
    require(field('Plotname') == ('Operating Point' if analysis == 'op' else 'AC Analysis'), 'Wrong raw analysis plot.')
    require(field('Flags') == ('real' if analysis == 'op' else 'complex'), 'Wrong raw value kind.')
    points, count = int(field('No. Points')), int(field('No. Variables'))
    require(points == (1 if analysis == 'op' else 8), 'Unexpected raw point count.')
    require(header.count('Variables:\n') == 1, 'Missing or duplicated raw variable table.')
    variables = [line.split() for line in header.split('Variables:\n')[1].splitlines() if line.strip()]
    require(len(variables) == count and all(row[0] == str(i) and
            (len(row) == 3 or (analysis == 'ac' and i == 0 and row == ['0', 'frequency', 'frequency', 'grid=3']))
            for i, row in enumerate(variables)), 'Malformed native variable table.')
    names = [row[1].lower() for row in variables]
    require(len(set(names)) == count, 'Duplicated native variable.')
    complex_data = analysis == 'ac'
    if marker[1] == b'Binary:':
        width = 16 if complex_data else 8
        require(len(values) == width * points * count, 'Truncated or extra raw binary data.')
        numbers = [complex(*struct.unpack_from('<dd', values, width * i)) if complex_data
                   else complex(struct.unpack_from('<d', values, width * i)[0]) for i in range(points * count)]
    else:
        tokens = [line.split() for line in values.decode('utf-8').splitlines() if line.strip()]
        require(len(tokens) == points * count, 'Truncated or extra raw text data.')
        numbers = []
        for i, row in enumerate(tokens):
            require(len(row) == (2 if i % count == 0 else 1), 'Malformed raw value row.')
            if i % count == 0:
                require(row[0] == str(i // count), 'Wrong raw point index.')
            parts = row[-1].split(',')
            require(len(parts) == (2 if complex_data else 1), 'Wrong raw scalar kind.')
            numbers.append(complex(*map(float, parts)))
    samples = [dict(zip(names, numbers[i * count:(i + 1) * count])) for i in range(points)]
    for row in samples:
        for name, value in row.items():
            # Ngspice does not initialize the unused frequency imaginary slot.
            require(math.isfinite(value.real) and (name == 'frequency' or math.isfinite(value.imag)), 'Nonfinite native value: ' + name)
    return samples


def channels(analysis):
    names = {f'v({terminal}_{name})' for name in BRANCHES for terminal in ('p', 'n')}
    names |= {f'i(v{terminal}_{name})' for name in BRANCHES for terminal in ('p', 'n')}
    names |= {'v(par_' + key + ')' for key in PARAMETERS}
    if analysis == 'ac':
        names.add('frequency')
    return names


def coefficients_match(sample, coefficients):
    for key in PARAMETERS:
        value = coefficients.get(key, 0)
        require(abs(sample['v(par_' + key + ')'] - value) <= 1e-24 + 1e-10 * abs(value), 'Effective passive coefficient differs: ' + key)


def check_op(path, bias, coefficients):
    require(bias in BIASES and not isinstance(bias, bool), 'Unsupported requested bias.')
    samples = read_raw(path, 'op')
    row = samples[0]
    require(set(row) == channels('op'), 'OP terminal/coefficient channels differ.')
    coefficients_match(row, coefficients)
    result = {}
    for name in BRANCHES:
        p, n, current, returning = (row[f'v(p_{name})'].real, row[f'v(n_{name})'].real, row[f'i(vp_{name})'].real, row[f'i(vn_{name})'].real)
        require(abs(p - bias) <= 1e-9 and abs(n) <= 1e-9 and abs((p - n) - bias) <= 1e-9,
                'Actual signed OP terminal bias differs: ' + name)
        require(max(abs(current), abs(returning), abs(current + returning)) <= 1e-12, 'Ideal model OP current differs: ' + name)
        result[name] = {'P_V': p, 'N_V': n, 'differential_V': p - n, 'current_A': current, 'return_current_A': returning}
    return result


def check_ac(path, plate, coefficients):
    require(plate in (1, 2), 'Unknown construction.')
    samples = read_raw(path, 'ac')
    resistance, capacitance = passive.rc(plate, coefficients)
    results = []
    for i, row in enumerate(samples):
        require(set(row) == channels('ac'), 'AC terminal/coefficient channels differ.')
        frequency = row['frequency'].real
        require(math.isclose(frequency, 1000 * 10 ** i, rel_tol=1e-12), 'AC frequencies differ.')
        coefficients_match(row, coefficients)
        target = 1 / complex(resistance, -1 / (2 * math.pi * frequency * capacitance))
        branches = {}
        for name in BRANCHES:
            p, n = row[f'v(p_{name})'], row[f'v(n_{name})']
            require(abs(p - 1) <= 1e-12 and abs(n) <= 1e-12, 'Actual AC terminal source differs: ' + name)
            y = -row[f'i(vp_{name})'] / (p - n)
            require(y.real > 0 and y.imag > 0, 'Nonpassive/noncapacitive native response.')
            require(abs((row[f'i(vp_{name})'] + row[f'i(vn_{name})']) / y) <= 1e-6, 'Native AC terminal currents do not balance.')
            r = (1 / y).real
            c = -1 / (2 * math.pi * frequency * (1 / y).imag)
            require(max(abs(y / target - 1), abs(r / resistance - 1), abs(c / capacitance - 1)) <= 1e-6,
                    'Independent analytical AC response differs: ' + name)
            branches[name] = {'Y_S': [y.real, y.imag], 'R_ohm': r, 'C_F': c}
        reference = complex(*branches['independent']['Y_S'])
        require(all(abs(complex(*value['Y_S']) / reference - 1) <= 1e-6 for value in branches.values()), 'Comparison branches differ.')
        results.append({'frequency_Hz': frequency, 'paths': branches})
    return results


def applied_bias(bias, fault=None):
    require(bias in BIASES and not isinstance(bias, bool), 'Unsupported requested bias.')
    require(fault in (None, 'missing-bias', 'sign-reversed', 'clamped-bias', 'displaced-ground'), 'Unknown bias control.')
    if fault in ('missing-bias', 'sign-reversed', 'clamped-bias'):
        require(bias != 0, 'Nonzero bias control was attached to a zero case.')
    p = 0 if fault == 'missing-bias' else -bias if fault == 'sign-reversed' else math.copysign(4.99, bias) if fault == 'clamped-bias' else bias
    return p, .5 if fault == 'displaced-ground' else 0


def check_deck(path, analysis, section, staged, native, plate, bias, fault=None):
    """Require the three circuits and exact execution directives, not labels."""
    require(analysis in ('op', 'ac') and section in passive.SECTIONS and plate in (1, 2), 'Invalid deck identity.')
    p, n = applied_bias(bias, fault)
    text = Path(path).read_text(encoding='utf-8')
    blocks = re.findall(r'(?ims)^\.subckt (\w+) P N[ \t]*\n(.*?)^\.ends(?: \w+)?[ \t]*$', text)
    require(len(blocks) == 2 and {name for name, _ in blocks} == {'schematic', 'independent'}, 'Substituted comparison circuit definitions.')
    for name, body in blocks:
        model = passive.circuit_rows('.subckt device_coupon P N\n' + body + '.ends\n', schematic=name == 'schematic')
        require(model == f'sky130_fd_pr__cap_mim_m3_{plate}', 'Comparison wrapper differs.')
    outside = re.sub(r'(?ims)^\.subckt .*?^\.ends(?: \w+)?[ \t]*$', '', text)
    lines = [line.strip() for line in outside.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    directives = [line for line in lines if line.startswith('.')]
    save = [line for line in directives if line.startswith('.save ')]
    require(len(save) == 1 and len(save[0].split()[1:]) == len(channels('op')) and set(save[0].split()[1:]) == channels('op'), 'Saved terminal/coefficient directives differ.')
    expected = [line.strip() for line in staged[section].splitlines() if line.strip()]
    expected += ['.param mc_mm_switch=0 mc_pr_switch=0', '.option tnom=27', '.temp 27',
                 '.include ' + native, '.op' if analysis == 'op' else '.ac dec 1 1k 10G', save[0], '.end']
    require(directives == expected, 'Additional/substituted execution directive, native path or passive section.')
    elements = [line.split() for line in lines if not line.startswith('.')]
    names = {prefix + name for name in BRANCHES for prefix in ('VP_', 'VN_', 'X_')}
    names |= {'VPAR_' + name for name in PARAMETERS}
    require(len(elements) == len(names) and {row[0] for row in elements} == names, 'Extra, missing or duplicated circuit element.')
    for row in elements:
        name = row[0]
        if name.startswith('VPAR_'):
            key = name[5:]
            require(row == [name, 'par_' + key, '0', 'DC', '{' + key + '}', 'AC', '{' + key + '}'], 'Parameter probe differs.')
        elif name.startswith('X_'):
            key = name[2:]
            require(row == [name, 'p_' + key, 'n_' + key, 'device_coupon' if key == 'extracted' else key], 'Comparison terminal path differs.')
        else:
            terminal, key = name[1].lower(), name[3:]
            expected_ac = 1 if terminal == 'p' else 0
            expected_dc = p if terminal == 'p' else n
            if terminal == 'p' and fault == 'missing-bias':
                require(row == [name, 'p_' + key, '0', 'AC', '1'], 'Omitted DC control is not actually omitted.')
            else:
                require(len(row) == 7 and row[:4] == [name, terminal + '_' + key, '0', 'DC'] and row[5] == 'AC', 'Stimulus circuit differs.')
                require(float(row[4]) == expected_dc and float(row[6]) == expected_ac, 'Applied deck voltage differs.')


def check_fault_op(path, bias, coefficients, fault):
    p, n = applied_bias(bias, fault)
    require(fault is not None, 'Missing fault identity.')
    samples = read_raw(path, 'op')
    require(set(samples[0]) == channels('op'), 'Fault OP channel coverage differs.')
    coefficients_match(samples[0], coefficients)
    for name in BRANCHES:
        row = samples[0]
        require(abs(row[f'v(p_{name})'] - p) <= 1e-9 and abs(row[f'v(n_{name})'] - n) <= 1e-9, 'Executed fault is not the declared terminal voltage.')
        ip, inn = row[f'i(vp_{name})'], row[f'i(vn_{name})']
        require(max(abs(ip), abs(inn), abs(ip + inn)) <= 1e-12, 'Unexpected fault OP current or KCL imbalance.')
    try:
        check_op(path, bias, coefficients)
    except ValueError as error:
        require('Actual signed OP terminal bias differs' in str(error), 'Fault failed for an unrelated reason.')
    else:
        raise ValueError('Bias fault was not detected independently.')
    return True


def numeric(actual, expected, label):
    require(isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isfinite(actual)
            and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-24), 'Saved numerical value differs: ' + label)


def check_saved_op(path, saved):
    row = read_raw(path, 'op')[0]
    require(saved['status'] == 'PASS' and set(saved['paths']) == set(BRANCHES), 'Saved OP path coverage differs.')
    require(set(saved['coefficients']) == set(PARAMETERS), 'Saved OP coefficient coverage differs.')
    for key in PARAMETERS:
        numeric(saved['coefficients'][key], row[f'v(par_{key})'].real, key)
    for key in BRANCHES:
        p, n = row[f'v(p_{key})'].real, row[f'v(n_{key})'].real
        expected = {'p_V': p, 'n_V': n, 'differential_V': p - n,
                    'i_p_A': row[f'i(vp_{key})'].real, 'i_n_A': row[f'i(vn_{key})'].real}
        require(set(saved['paths'][key]) == set(expected), 'Saved OP observables differ.')
        for name, value in expected.items():
            numeric(saved['paths'][key][name], value, key + '/' + name)


def check_saved_ac(path, plate, coefficients, saved, derived):
    require(saved['status'] == 'PASS' and len(saved['samples']) == 8, 'Saved AC sample coverage differs.')
    r, c = passive.rc(plate, coefficients)
    numeric(saved['expected_R_ohm'], r, 'expected R')
    numeric(saved['expected_C_F'], c, 'expected C')
    require(set(saved['coefficients']) == set(PARAMETERS), 'Saved AC coefficient coverage differs.')
    rows = read_raw(path, 'ac')
    for key in PARAMETERS:
        numeric(saved['coefficients'][key], rows[-1][f'v(par_{key})'].real, key)
    for actual, expected in zip(saved['samples'], derived):
        numeric(actual['frequency_Hz'], expected['frequency_Hz'], 'frequency')
        require(set(actual['paths']) == set(BRANCHES), 'Saved AC path coverage differs.')
        target = 1 / complex(r, -1 / (2 * math.pi * expected['frequency_Hz'] * c))
        for key in BRANCHES:
            value = expected['paths'][key]
            item = actual['paths'][key]
            require(set(item) == {'Y_S', 'R_ohm', 'C_F', 'relative_error'} and len(item['Y_S']) == 2, 'Saved AC observables differ.')
            for component in (0, 1):
                numeric(item['Y_S'][component], value['Y_S'][component], key + '/Y')
            numeric(item['R_ohm'], value['R_ohm'], key + '/R')
            numeric(item['C_F'], value['C_F'], key + '/C')
            error = max(abs(complex(*value['Y_S']) / target - 1), abs(value['R_ohm'] / r - 1), abs(value['C_F'] / c - 1))
            require(isinstance(item['relative_error'], (int, float)) and not isinstance(item['relative_error'], bool) and math.isfinite(item['relative_error'])
                    and math.isclose(item['relative_error'], error, rel_tol=1e-8, abs_tol=1e-12), 'Saved AC error differs.')


NATIVE_ENV = {'PATH': '/opt/icstudio/bin:/usr/bin:/bin', 'HOME': '/__icstudio_mim_bias_no_home__',
              'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC', 'PYTHONNOUSERSITE': '1',
              'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONHASHSEED': '0'}
ENGINE = '/var/tmp/icstudio-ngspice-capacitor-build-20261017-v2/installed/bin/icstudio-ngspice'
INSTALLED = '/var/tmp/icstudio-ngspice-capacitor-build-20261017-v2/installed'
LAUNCHER_SHA = '4c38c46c06cbe65d4111e392b93fd0b4a09250bd7f93bb3eed8f8f0af2bddcc9'


def elf_needed(path):
    """Read direct DT_NEEDED names without executing a native program."""
    data = Path(path).read_bytes()
    require(len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01', 'Unsupported recorded ELF format.')
    offset = struct.unpack_from('<Q', data, 32)[0]
    width, count = struct.unpack_from('<HH', data, 54)
    require(width >= 56 and offset + width * count <= len(data), 'Truncated ELF program table.')
    headers = [struct.unpack_from('<IIQQQQQQ', data, offset + i * width) for i in range(count)]
    dynamic = [entry for entry in headers if entry[0] == 2]
    require(len(dynamic) <= 1, 'Ambiguous ELF dynamic table.')
    if not dynamic:
        return set()
    entry = dynamic[0]; start, size = entry[2], entry[5]
    require(size % 16 == 0 and start + size <= len(data), 'Truncated ELF dynamic table.')
    tags = []
    for i in range(size // 16):
        tag, value = struct.unpack_from('<qQ', data, start + 16 * i)
        if tag == 0:
            break
        tags.append((tag, value))
    else:
        raise ValueError('Unterminated ELF dynamic table.')
    needed = [value for tag, value in tags if tag == 1]
    if not needed:
        return set()
    tables = [value for tag, value in tags if tag == 5]
    require(len(tables) == 1, 'Missing ELF dynamic string table.')
    loads = [entry for entry in headers if entry[0] == 1 and entry[3] <= tables[0] < entry[3] + entry[5]]
    require(len(loads) == 1, 'Unbound ELF dynamic string table.')
    strings = loads[0][2] + tables[0] - loads[0][3]
    result = set()
    for value in needed:
        start = strings + value
        require(start < len(data) and b'\0' in data[start:], 'Truncated ELF dependency name.')
        name = data[start:data.index(b'\0', start)].decode('ascii')
        require(name and '/' not in name, 'Unsupported ELF dependency path.')
        result.add(name)
    return result


def check_runtime(root, report, *, live=True):
    before, after = load(root / 'runtime-before.json'), load(root / 'runtime-after.json')
    require(before == after and sha(root / 'runtime-before.json') == report['runtime_before_sha256']
            and sha(root / 'runtime-after.json') == report['runtime_after_sha256'], 'Native runtime identity changed.')
    require(before['profile'] == 'linux-x86_64-capacitor-ngspice-mim-bias-v1' and before['native_environment'] == NATIVE_ENV
            and before['launcher_environment'] == {'SPICE_LIB_DIR': INSTALLED + '/share/ngspice',
                'SPICE_SCRIPTS': INSTALLED + '/share/ngspice/scripts', 'ICSTUDIO_SPICE_MODELS': INSTALLED + '/lib/ngspice'}, 'Unknown native execution profile.')
    require(before['python_cache_prefix'] == '/__icstudio_mim_bias_no_bytecode__' and
            all(value in before['python_flags'] for value in ('dont_write_bytecode=1', 'no_user_site=1', 'hash_randomization=0')), 'Python startup identity differs.')
    require(before['ngspice_version'].strip() and before['python'].startswith('3.12.'), 'Missing runtime version identity.')
    required = {ENGINE, INSTALLED + '/bin/ngspice', '/bin/sh', '/usr/bin/dirname', '/usr/bin/ldd',
                '/etc/ld.so.cache', '/etc/ld.so.preload', '/etc/os-release'}
    require(required <= set(before['files']), 'Incomplete native runtime files.')
    require(before['files'][ENGINE]['sha256'] == LAUNCHER_SHA, 'Unreviewed simulator launcher.')
    require(INSTALLED in before['trees'] and before['trees'][INSTALLED], 'Incomplete native runtime tree.')
    require({INSTALLED + '/bin/ngspice', '/bin/sh', '/usr/bin/dirname'} <= set(before['elf_dependencies']), 'Missing native ELF dependency closure.')
    def identity(path, saved):
        if saved != {'absent': True}:
            require(set(saved) == {'sha256', 'bytes', 'resolved'} and re.fullmatch('[0-9a-f]{64}', saved['sha256'])
                    and isinstance(saved['bytes'], int) and saved['bytes'] >= 0 and PurePosixPath(saved['resolved']).is_absolute(), 'Malformed runtime identity.')
        if not live:
            return
        path = Path(path)
        if saved == {'absent': True}:
            require(not path.exists() and not path.is_symlink(), 'Absent runtime input now exists: ' + str(path))
        else:
            require(path.is_file() and sha(path) == saved['sha256'] and path.stat().st_size == saved['bytes']
                    and str(path.resolve()) == saved['resolved'], 'Runtime file differs: ' + str(path))
    for name, item in before['files'].items():
        require(name.startswith('/'), 'Relative native runtime path.')
        identity(name, item)
    for name, files in before['trees'].items():
        path = Path(name)
        require(name.startswith('/'), 'Relative native runtime tree.')
        if files == {'$root': {'absent': True}}:
            identity(path, {'absent': True}); continue
        if live:
            require(path.is_dir(), 'Missing native runtime tree.')
            actual = set()
            for directory, dirs, names in os.walk(path, followlinks=False):
                require(not any((Path(directory) / d).is_symlink() for d in dirs), 'Native runtime directory symlink.')
                actual.update((Path(directory) / n).relative_to(path).as_posix() for n in names)
            require(actual == set(files), 'Native runtime tree closure differs.')
        for relative, item in files.items():
            require(not PurePosixPath(relative).is_absolute() and '..' not in PurePosixPath(relative).parts, 'Runtime member path escapes tree.')
            identity(path / relative, item)
    for executable, libraries in before['elf_dependencies'].items():
        require(executable in before['files'], 'Unbound ELF closure.')
        if live:
            check_elf_closure(executable, libraries)
        for name, item in libraries.items():
            identity(name, item)
    source_root = PurePosixPath(report['source_root'])
    for name in before['sys_path']:
        path = PurePosixPath(name)
        require(path.is_absolute(), 'Relative Python import root.')
        require(path.is_relative_to(source_root) or name in before['files'] or
                any(path.is_relative_to(PurePosixPath(tree)) for tree in before['trees']), 'Unbound Python import root: ' + name)
    return before


def check_elf_closure(executable, libraries):
    """Check every captured object's imports, including indirect dependencies."""
    names = {PurePosixPath(name).name for name in libraries}
    for path in (executable, *libraries):
        require(elf_needed(path) <= names, 'Missing actual ELF dependency: ' + str(path))


def execution_title(execution_root, case, analysis, fault=None):
    identity = {'execution_root': execution_root, 'case': case, 'analysis': analysis, 'fault': fault or 'positive'}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return '* icstudio-mim-bias-v1 ' + digest


def check_execution(folder, origin, result, analysis, *, execution_root, case, fault=None):
    command = [ENGINE, '-n', '-D', 'filetype=ascii', '-D', 'ngbehavior=hsa',
               '-b', '-r', origin + '/probe.raw', origin + '/probe.cir']
    require(result['command'] == command and result['cwd'] == origin and result['environment'] == NATIVE_ENV,
            'Native command, working directory or environment differs.')
    require(sha(folder / 'probe.cir') == result['deck_sha256'] and sha(folder / 'probe.raw') == result['raw_sha256'], 'Native deck/raw identity differs.')
    title = execution_title(execution_root, case, analysis, fault)
    require((folder / 'probe.cir').read_text(encoding='utf-8').splitlines()[0] == title, 'Native deck execution title differs.')
    header = (folder / 'probe.raw').read_bytes().split(b'Variables:', 1)[0].decode('utf-8').replace('\r\n', '\n')
    require(re.findall(r'^Title:[ \t]*(.*)$', header, re.M) == [title], 'Native raw execution title differs.')
    text = (folder / 'console.log').read_text(encoding='utf-8')
    require(re.findall(r'^No\. of Data Rows\s*:\s*(\d+)\s*$', text, re.M) == ['1' if analysis == 'op' else '8'], 'Native analysis completion is missing or duplicated.')
    require(not re.search(r'(?im)^\s*(?:fatal|error)\b', text), 'Native simulator reported an error.')
    temperatures = re.findall(r'Doing analysis at TEMP = ([0-9.+-]+) and TNOM = ([0-9.+-]+)', text)
    require(len(temperatures) == 1 and all(float(value) == 27 for value in temperatures[0]), 'Actual native temperature differs.')


def check_sources(root, report, manifest, source_map):
    sources = load(root / 'source-files.json')
    require(sources and sha(root / 'source-files.json') == report['source_files_sha256'], 'Captured source inventory differs.')
    require({'source/' + key for key in sources} == {key for key in manifest if key.startswith('source/')}, 'Captured source closure differs.')
    for name, value in sources.items():
        require(manifest['source/' + name] == value, 'Captured source content differs.')
    for name in ('audit_sky130_mim_bias_boundaries', 'qualify_sky130_mim_bias_boundaries',
                 'audit_sky130_mim_passive_corners', 'audit_sky130_mim_physical_case', 'audit_sky130_mim_orientation'):
        relative = 'scripts/' + name + '.py'
        require(sources[relative] == sha(ROOT / relative), 'Audited source/helper differs from execution: ' + relative)
    require({'contract-sources/' + key for key in source_map['sources']} == {key for key in manifest if key.startswith('contract-sources/')}, 'Reviewed source closure differs.')
    for name, item in source_map['sources'].items():
        require(manifest['contract-sources/' + name] == item['sha256'], 'Reviewed public source differs: ' + name)


def check_retained(root, report, source_map, manifest):
    retained = root / 'retained-native'
    receipt = report['reused_physical']
    expected = {'archive_sha256': '03a75a194d165ed5fad0486f5a9a1fec0a5daa7c751c23f72beb9a17c031d430',
                'original_manifest_sha256': '127e67064cd10d4c4670a5abc7aa47fabc41914ba64682854a59036db110187e',
                'original_qualification_sha256': '3051f4edeb041ee080210e72e86e86985c76c4f70c869e6990ceec2206da5c4c',
                'original_execution_root': '/var/tmp/icstudio-mim-passive-20261023-final-v1/native',
                'physical_execution': 'historical_reuse_no_new_physical_run', 'member_prefix': 'accepted/native/', 'status': 'PASS'}
    require(all(receipt[key] == value for key, value in expected.items()), 'Retained original physical identity differs.')
    require(sha(retained / 'manifest.json') == expected['original_manifest_sha256'] and
            sha(retained / 'qualification.json') == expected['original_qualification_sha256'], 'Rehashed or substituted original physical receipt.')
    require(load(retained / 'qualification.json')['execution_root'] == expected['original_execution_root'], 'Original physical execution root was relabeled.')
    bindings = load(root / 'retained-bindings.json')
    require(sha(root / 'retained-bindings.json') == report['retained_bindings_sha256'], 'Retained input bindings changed.')
    require({'retained-native/' + key for key in bindings} == {key for key in manifest if key.startswith('retained-native/')}, 'Retained input closure differs.')
    for name, item in bindings.items():
        require(item['member'] == 'accepted/native/' + name and item['sha256'] == manifest['retained-native/' + name]
                and (retained / name).stat().st_size == item['bytes'], 'Retained archive member binding differs.')
    for key, item in source_map['retained_native_inputs'].items():
        name = item['member'].removeprefix('accepted/native/')
        require(sha(retained / name) == item['sha256'], 'Original native extraction differs: ' + key)
        require(passive.circuit_rows((retained / name).read_text()) == item['model'], 'Retained native model/geometry differs.')
    result = passive.audit(retained)
    require(result == receipt['audit'], 'Retained strict physical audit differs.')
    return result


def case_inventory(report):
    full = [f'p{p}-{s}-r{r}-b{b}' for p in (1, 2) for s in passive.SECTIONS for r in (0, 90) for b in ('m5', '0', 'p5')]
    selection = report['selected_cases']
    require(report['full_declared_cases'] == full and selection and len(selection) == len(set(selection)) and set(selection) <= set(full), 'Declared case selection differs.')
    require(sorted(row['name'] for row in report['cases']) == sorted(selection), 'Missing or duplicated case receipt.')
    for row in report['cases']:
        plate, section, rotation, bias = row['plate'], row['section'], row['rotation'], row['bias_V']
        require(plate in (1, 2) and section in passive.SECTIONS and rotation in (0, 90) and bias in BIASES and not isinstance(bias, bool), 'Invalid case context.')
        name = f'p{plate}-{section}-r{rotation}-b' + {-5: 'm5', 0: '0', 5: 'p5'}[bias]
        require(row['name'] == name and row['status'] == 'PASS', 'Case name/context differs.')
    return full, selection


def audit(root, *, live_runtime=True):
    root = Path(root).resolve()
    manifest = passive.verify_manifest(root)
    report = load(root / 'qualification.json')
    require(report['status'] == 'PASS' and all(report.get(key) is True for key in
            ('runtime_unchanged', 'source_unchanged', 'models_unchanged', 'retained_unchanged', 'contracts_unchanged')), 'Incomplete or changed execution inputs.')
    require(all(report.get(key) is False for key in ('qualified', 'chunk_complete', 'release')), 'Qualification claim exceeds this selected example.')
    full, selection = case_inventory(report)
    require(report['contract_sha256'] == sha(root / 'contract.json') == CONTRACT_SHA and
            report['source_map_sha256'] == sha(root / 'bias-contract.json') == SOURCE_MAP_SHA, 'Reviewed source contracts differ.')
    source_map, contract = load(root / 'bias-contract.json'), load(root / 'contract.json')
    check_sources(root, report, manifest, source_map)
    check_retained(root, report, source_map, manifest)
    check_runtime(root, report, live=live_runtime)
    staged = passive.verify_models(root, report, manifest)
    domains = report['domain_controls']
    require([row['request'] for row in domains] == ['-5.001', '5.001', 'nan', 'inf', '-inf'] and
            all(row['status'] == 'REJECTED' and row['error'] for row in domains), 'Domain rejection coverage differs.')
    responses = {}; faults = 0
    for row in report['cases']:
        plate, section, rotation, bias = row['plate'], row['section'], row['rotation'], row['bias_V']
        require(plate in (1, 2) and section in passive.SECTIONS and rotation in (0, 90) and bias in BIASES, 'Invalid case context.')
        name = f'p{plate}-{section}-r{rotation}-b' + {-5: 'm5', 0: '0', 5: 'p5'}[bias]
        require(row['name'] == name and row['status'] == 'PASS', 'Case name/context differs.')
        folder = root / name
        require(load(folder / 'record.json') == row, 'Case record differs from aggregate.')
        native_relative = f'retained-native/physical/{plate}/valid-{rotation}-plain/lvs-extraction/extracted.spice'
        native = report['execution_root'] + '/' + native_relative
        require(row['native_path'] == native and row['native_sha256'] == source_map['retained_native_inputs'][f'p{plate}-r{rotation}']['sha256'], 'Native orientation/path identity differs.')
        coefficients = contract['passive_sections'][section]['coefficients']
        require(set(row['analyses']) == {'op', 'ac'}, 'OP/AC analysis coverage differs.')
        for analysis in ('op', 'ac'):
            dest = folder / analysis; result = row['analyses'][analysis]
            check_execution(dest, report['execution_root'] + '/' + name + '/' + analysis, result, analysis,
                            execution_root=report['execution_root'], case=name)
            check_deck(dest / 'probe.cir', analysis, section, staged, native, plate, bias)
            if analysis == 'op':
                check_op(dest / 'probe.raw', bias, coefficients)
                check_saved_op(dest / 'probe.raw', result)
            else:
                derived = check_ac(dest / 'probe.raw', plate, coefficients)
                check_saved_ac(dest / 'probe.raw', plate, coefficients, result, derived)
                responses[(plate, section, rotation, bias)] = derived
        expected_faults = (['missing-bias', 'sign-reversed', 'clamped-bias'] if bias else []) + ['displaced-ground']
        require([control['fault'] for control in row['controls']] == expected_faults, 'Missing or duplicated bias control.')
        for control in row['controls']:
            fault = control['fault']; dest = folder / 'controls' / fault
            p, n = applied_bias(bias, fault)
            require(control['detected'] is True and control['intended_bias_V'] == bias and control['applied_bias_V'] == p
                    and control['applied_ground_V'] == n and control['rejection'], 'Saved fault identity/outcome differs.')
            check_execution(dest, report['execution_root'] + '/' + name + '/controls/' + fault, control, 'op',
                            execution_root=report['execution_root'], case=name, fault=fault)
            check_deck(dest / 'probe.cir', 'op', section, staged, native, plate, bias, fault)
            check_fault_op(dest / 'probe.raw', bias, coefficients, fault)
            check_saved_op(dest / 'probe.raw', control)
            faults += 1
    comparisons = 0
    for (plate, section, rotation, bias), values in responses.items():
        require((plate, section, rotation, 0) in responses, 'Missing matching zero-bias reference.')
        if not bias:
            continue
        for value, baseline in zip(values, responses[(plate, section, rotation, 0)]):
            for branch in BRANCHES:
                current, zero = value['paths'][branch], baseline['paths'][branch]
                require(abs(complex(*current['Y_S']) / complex(*zero['Y_S']) - 1) <= 1e-6 and
                        abs(current['R_ohm'] / zero['R_ohm'] - 1) <= 1e-6 and abs(current['C_F'] / zero['C_F'] - 1) <= 1e-6,
                        'Public linear-model response is not bias invariant.')
        comparisons += 1
    return {'status': 'PASS', 'qualified': False, 'chunk_complete': False, 'release_acceptance': False,
            'runtime_check': 'live_files_and_captured_identity' if live_runtime else 'captured_identity_only_offline',
            'full_declared_selection': set(selection) == set(full),
            'counts': {'contexts': len(selection), 'op_points': len(selection), 'ac_samples': 8 * len(selection),
                       'bias_faults': faults, 'domain_rejections': 5, 'bias_invariance_contexts': comparisons,
                       'retained_native_inputs': 4, 'new_physical_executions': 0},
            'scope': __doc__, 'audit_sha256': sha(__file__)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--offline-runtime', action='store_true', help='Audit retained runtime identity only; explicitly omits live installed-file verification.')
    args = parser.parse_args()
    result = audit(args.root, live_runtime=not args.offline_runtime)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
