"""Independent native-mask, circuit, coefficient and raw-AC MiM readback.

No application, generator, simulation runner or application parser is imported.
Public model equations are integration references, not silicon measurements.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import posixpath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_sky130_mim_orientation import raw
from scripts.audit_sky130_mim_physical_case import audit_physical

SECTIONS = ('tt', 'll', 'hh', 'hl', 'lh')
PARAMETERS = ('rm3', 'rm4', 'rcvia3', 'rcvia4', 'tol_m3', 'tol_m4', 'camimc', 'cpmimc', 'm3_dw', 'm4_dw')
PATHS = ('schematic', 'extracted', 'independent', 'wrong-width', 'wrong-length', 'wrong-count', 'swapped', 'wrong-model')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
load = lambda p: json.loads(Path(p).read_bytes())


def circuit_rows(text, schematic=False):
    text = re.sub(r'\n\s*\+\s*', ' ', text)
    rows = [s.split() for s in text.splitlines() if s.strip() and not s.lstrip().startswith('*')]
    if len(rows) != 3 or rows[0] != ['.subckt', 'device_coupon', 'P', 'N'] or rows[-1] not in (['.ends'], ['.ends', 'device_coupon']):
        raise ValueError('Native capacitor circuit has unexpected rows/interface.')
    fields = rows[1]
    if len(fields) not in ((6, 7, 8) if schematic else (6, 7)) or not fields[0].startswith('X') or fields[1:3] != ['P', 'N']:
        raise ValueError('Native capacitor terminals or element count changed.')
    parameters = [v.split('=') for v in fields[4:]]
    if any(len(v) != 2 for v in parameters): raise ValueError('Malformed native parameters.')
    values = {k: float(v) for k, v in parameters}
    if len(values) != len(parameters) or set(values) - ({'w', 'l', 'm', 'mf'} if schematic else {'w', 'l', 'm'}) or not {'w', 'l'} <= values.keys():
        raise ValueError('Ambiguous native parameters.')
    if values['w'] != 2 or values['l'] != 10 or values.get('m', 1) != 1 or values.get('mf', 1) != 1:
        raise ValueError('Native dimensions or multiplicity differ.')
    return fields[3]


def rc(plate, coefficients, width=2, length=10, count=1):
    suffix = str(plate + 2)
    delta = (coefficients['m' + suffix + '_dw'] + coefficients['tol_m' + suffix]) * 1e6
    width += delta; length += delta
    c = (coefficients['camimc'] * width * length + coefficients['cpmimc'] * 2 * (width + length)) * count
    pitch_area = (.56 if plate == 1 else .73) ** 2
    r = (coefficients['rm' + suffix] * length / width + coefficients['rcvia' + suffix] * pitch_area / (width * length)) / count
    if not all(math.isfinite(x) and x > 0 for x in (width, length, r, c)): raise ValueError('Invalid analytical capacitor.')
    return r, c


def expected(plate, coefficients, name):
    w, l, n = 2, 10, 1
    if name == 'wrong-width': w = 2.4
    elif name == 'wrong-length': l = 12
    elif name == 'wrong-count': n = 2
    elif name == 'swapped': w, l = l, w
    elif name == 'wrong-model': plate = 3 - plate
    elif name not in ('schematic', 'extracted', 'independent'): raise ValueError('Unknown comparison path.')
    return rc(plate, coefficients, w, l, n)


def check_raw(path, plate, coefficients, saved, intended=None):
    intended = coefficients if intended is None else intended
    samples = raw(path)
    names = {'frequency', *('i(vp_' + s.replace('-', '_') + ')' for s in PATHS),
             *('v(p_' + s.replace('-', '_') + ')' for s in PATHS),
             *('v(par_' + s + ')' for s in (*PARAMETERS, 'mc_mm_switch', 'mc_pr_switch'))}
    if len(saved['samples']) != 8 or set(samples[0]) != names: raise ValueError('Native AC channel coverage differs.')
    worst = {name: 0.0 for name in PATHS}; coefficient_error = 0.0
    target_r, target_c = rc(plate, intended)
    if not math.isclose(saved['expected_R_ohm'], target_r, rel_tol=1e-12) or not math.isclose(saved['expected_C_F'], target_c, rel_tol=1e-12):
        raise ValueError('Saved analytical target differs from source equations.')
    for sample, recorded in zip(samples, saved['samples']):
        frequency = sample['frequency'].real
        if recorded['frequency_Hz'] != frequency: raise ValueError('Recorded frequency differs.')
        if set(recorded['paths']) != set(PATHS): raise ValueError('Recorded path coverage differs.')
        for key in (*PARAMETERS, 'mc_mm_switch', 'mc_pr_switch'):
            value = coefficients.get(key, 0)
            if abs(sample['v(par_' + key + ')'] - value) > 1e-24 + 1e-10 * abs(value):
                raise ValueError('Actual passive coefficient differs: ' + key)
            if saved['coefficients'][key] != sample['v(par_' + key + ')'].real:
                raise ValueError('Recorded passive coefficient differs.')
            target_value = intended.get(key, 0)
            coefficient_error = max(coefficient_error, abs(sample['v(par_' + key + ')'] - target_value) / (1e-24 + 1e-10 * abs(target_value)))
        for name in PATHS:
            if abs(sample['v(p_' + name.replace('-', '_') + ')'] - 1) > 1e-12:
                raise ValueError('Incorrect applied AC source.')
            r, c = expected(plate, coefficients, name)
            target = 1 / complex(r, -1 / (2 * math.pi * frequency * c))
            y = -sample['i(vp_' + name.replace('-', '_') + ')']
            if not (y.real > 0 and y.imag > 0) or abs(y / target - 1) > 1e-6:
                raise ValueError('Independent complex response differs: ' + name)
            measured_r = (1 / y).real
            measured_c = -1 / (2 * math.pi * frequency * (1 / y).imag)
            if abs(measured_r / r - 1) > 1e-6 or abs(measured_c / c - 1) > 1e-6:
                raise ValueError('Independent series R/C differs: ' + name)
            item = recorded['paths'][name]
            saved_y = complex(*item['Y_S'])
            if not math.isfinite(abs(saved_y)) or abs(saved_y / y - 1) > 1e-12 or not math.isclose(item['R_ohm'], measured_r, rel_tol=1e-12) or not math.isclose(item['C_F'], measured_c, rel_tol=1e-12):
                raise ValueError('Saved numerical results differ from native output.')
            intended_y = 1 / complex(target_r, -1 / (2 * math.pi * frequency * target_c))
            error = max(abs(y / intended_y - 1), abs(measured_r / target_r - 1), abs(measured_c / target_c - 1))
            worst[name] = max(worst[name], error)
            if not math.isclose(item['relative_error'], error, rel_tol=1e-9, abs_tol=1e-12): raise ValueError('Saved response error differs.')
    if not math.isclose(saved['maximum_coefficient_normalized_error'], coefficient_error, rel_tol=1e-10, abs_tol=1e-9): raise ValueError('Saved coefficient error differs.')
    if any(not math.isclose(saved['maximum_relative_errors'][name], error, rel_tol=1e-9, abs_tol=1e-12) for name, error in worst.items()): raise ValueError('Saved maximum response error differs.')
    return len(samples)


def check_deck(path, selected, staged, native, plate):
    text = path.read_text(encoding='utf-8')
    if text.count(staged[selected]) != 1 or text.count('.include ' + native) != 1:
        raise ValueError('Executed library section or original extraction include differs.')
    for line in ('.param mc_mm_switch=0 mc_pr_switch=0', '.option tnom=27', '.temp 27', '.ac dec 1 1k 10G', '.end'):
        if text.splitlines().count(line) != 1: raise ValueError('Execution condition differs: ' + line)
    # Check the actual three comparison paths, not only their output labels.
    blocks = re.findall(r'(?ims)^\.subckt (\w+) P N\s*\n(.*?)^\.ends(?: \w+)?\s*$', text)
    if {name for name, _ in blocks} != {'schematic', 'independent'} or len(blocks) != 2:
        raise ValueError('Comparison circuit definitions differ.')
    for name, body in blocks:
        statement = [line for line in body.splitlines() if line.strip() and not line.lstrip().startswith('*')]
        if len(statement) != 1: raise ValueError('Extra schematic/reference element.')
        normalized = f'.subckt device_coupon P N\n{statement[0]}\n.ends\n'
        if circuit_rows(normalized, schematic=name == 'schematic') != f'sky130_fd_pr__cap_mim_m3_{plate}': raise ValueError('Comparison model differs.')
    outside = re.sub(r'(?ims)^\.subckt .*?^\.ends(?: \w+)?\s*$', '', text)
    saves = ['i(vp_' + k.replace('-', '_') + ')' for k in PATHS]
    saves += ['v(p_' + k.replace('-', '_') + ')' for k in PATHS]
    saves += ['v(par_' + k + ')' for k in (*PARAMETERS, 'mc_mm_switch', 'mc_pr_switch')]
    directives = [line.strip() for line in outside.splitlines() if line.lstrip().startswith('.')]
    expected_directives = [line.strip() for line in staged[selected].splitlines() if line.strip()]
    expected_directives += ['.param mc_mm_switch=0 mc_pr_switch=0', '.option tnom=27', '.temp 27',
                            '.include ' + native, '.ac dec 1 1k 10G', '.save ' + ' '.join(saves), '.end']
    if directives != expected_directives: raise ValueError('Additional or changed execution directive/include.')
    elements = [line.split() for line in outside.splitlines() if line.strip() and not line.lstrip().startswith(('*', '.'))]
    expected_names = {'VP_' + name.replace('-', '_') for name in PATHS} | {'X_' + name.replace('-', '_') for name in PATHS} | {'VPAR_' + name for name in (*PARAMETERS, 'mc_mm_switch', 'mc_pr_switch')}
    if len(elements) != len(expected_names) or {v[0] for v in elements} != expected_names:
        raise ValueError('Executed deck has extra/substituted circuit elements.')
    for row in elements:
        if row[0].startswith('VP_'):
            key = row[0][3:]
            if row != ['VP_' + key, 'p_' + key, '0', 'DC', '0', 'AC', '1']: raise ValueError('Applied stimulus differs.')
        elif row[0].startswith('VPAR_'):
            key = row[0][5:]
            if row != ['VPAR_' + key, 'par_' + key, '0', 'DC', '{' + key + '}', 'AC', '{' + key + '}']: raise ValueError('Parameter probe differs.')
        elif row[0] in ('X_schematic', 'X_extracted', 'X_independent'):
            key = row[0][2:]
            if row != ['X_' + key, 'p_' + key, '0', 'device_coupon' if key == 'extracted' else key]: raise ValueError('Comparison path differs.')
        else:
            key = row[0][2:]; width, length, count = 2, 10, 1
            if key == 'wrong_width': width = 2.4
            elif key == 'wrong_length': length = 12
            elif key == 'wrong_count': count = 2
            elif key == 'swapped': width, length = 10, 2
            chosen = 3 - plate if key == 'wrong_model' else plate
            expected_row = ['X_' + key, 'p_' + key, '0', f'sky130_fd_pr__cap_mim_m3_{chosen}', f'w={width:g}', f'l={length:g}', f'm={count}']
            if row != expected_row: raise ValueError('Executed electrical mutation differs.')


def verify_manifest(root):
    manifest = load(root / 'manifest.json')
    actual = set()
    for p in root.rglob('*'):
        if p.is_symlink(): raise ValueError('Symlink in evidence.')
        if p.is_file() and p != root / 'manifest.json': actual.add(p.relative_to(root).as_posix())
    if not manifest or set(manifest) != actual: raise ValueError('Incomplete evidence manifest.')
    for name, digest in manifest.items():
        p = root / name
        if Path(name).as_posix() != name or not p.resolve().is_relative_to(root) or sha(p) != digest:
            raise ValueError('Evidence hash/path differs.')
    return manifest


def verify_sources(root, report, contract, manifest):
    sources = load(root / 'source-files.json')
    if not sources or sha(root / 'source-files.json') != report['source_files_sha256']:
        raise ValueError('Execution source inventory differs.')
    if {'source/' + n for n in sources} != {n for n in manifest if n.startswith('source/')}:
        raise ValueError('Execution source closure differs.')
    for name, digest in sources.items():
        if manifest['source/' + name] != digest: raise ValueError('Executed source hash differs.')
    if sha(root / 'executed-runner.py') != sources['scripts/qualify_sky130_mim_passive_corners.py']:
        raise ValueError('Executed runner differs.')
    for name, source in contract['sources'].items():
        if manifest.get('contract-sources/' + name) != source['sha256']:
            raise ValueError('Retained public contract source differs.')


def verify_models(root, report, manifest):
    folder = root / 'shared-models'
    identity = load(folder / 'source-identity.json')
    files = load(root / 'model-files.json')
    if not files or files != identity['files']: raise ValueError('Model inventories differ.')
    expected_names = {'shared-models/' + n for n in files} | {'shared-models/source-identity.json'}
    if expected_names != {n for n in manifest if n.startswith('shared-models/')}:
        raise ValueError('Staged model closure differs.')
    if any(manifest['shared-models/' + n] != h for n, h in files.items()): raise ValueError('Staged model binding differs.')
    package = load(root / 'contract-sources/package')
    if sha(root / 'contract-sources/package') != report['simulation_package']['manifest_sha256'] or package['revision'] != report['simulation_package']['revision']:
        raise ValueError('Simulation package identity differs.')
    mapping = load(folder / 'pdk-model-files.json')
    if {'model-sources/' + n for n in mapping.values()} != {n for n in manifest if n.startswith('model-sources/')}:
        raise ValueError('Original model closure differs.')
    if set(mapping) | {'pdk-model-files.json'} != set(files) or len(set(mapping.values())) != len(mapping):
        raise ValueError('Ambiguous staged source mapping.')
    names = {}
    for staged_name, original in mapping.items():
        digest = package['files'][original]
        if manifest['model-sources/' + original] != digest: raise ValueError('Original model differs from public package.')
        expected_name = 'pdk-models/' + hashlib.sha256((original + '\0' + digest).encode()).hexdigest()[:24] + '.spice'
        if staged_name != expected_name: raise ValueError('Staged name differs from original identity.')
        names[original] = staged_name
    execution = report['execution_root'] + '/shared-models/'
    pattern = re.compile(r'(?im)^[^\S\n]*(\.include|\.inc|\.lib)[^\S\n]+("[^"\n]+"|\'[^\'\n]+\'|[^\s]+)([^\n]*)')
    for original, staged_name in names.items():
        text = (root / 'model-sources' / original).read_text(encoding='utf-8')
        def substitute(match):
            if match[1].lower() == '.lib' and not match[3].strip(): return match[0]
            relative = posixpath.normpath(posixpath.join(posixpath.dirname(original), match[2].strip('\"\'')))
            if relative not in names: raise ValueError('Model include escapes retained closure.')
            return match[1] + ' ' + execution + names[relative] + match[3]
        if pattern.sub(substitute, text) != (folder / staged_name).read_text(encoding='utf-8'):
            raise ValueError('Staged model statements differ from locked original.')
    expected_staged = {}
    for section in SECTIONS:
        lines = []
        for item in package['technology']['simulation']['includes']:
            selection = item.get('sections', {}).get(section, item.get('section'))
            lines.append(('.lib ' if selection else '.include ') + execution + names[item['path']] + (' ' + selection if selection else ''))
        expected_staged[section] = '\n'.join(lines)
    if identity['staged'] != expected_staged: raise ValueError('Selected public model section differs.')
    return identity['staged']


def audit(root):
    root = root.resolve(); report = load(root / 'qualification.json')
    if report['status'] != 'PASS' or not all(report[k] for k in ('source_unchanged', 'models_unchanged', 'tools_unchanged', 'contract_unchanged')):
        raise ValueError('Run did not complete with unchanged inputs.')
    manifest = verify_manifest(root)
    bindings = len(manifest)
    contract = load(root / 'contract.json')
    if sha(root / 'contract.json') != report['contract_sha256'] or report['contract_sha256'] != sha(ROOT / 'docs/qualification/sky130-mim-contract-v1.json'):
        raise ValueError('Source contract identity differs.')
    verify_sources(root, report, contract, manifest)
    coefficients = {s: contract['passive_sections'][s]['coefficients'] for s in SECTIONS}
    selected = report['selected_cases']
    full = [f'p{p}-{s}-r{a}' for p in (1, 2) for s in SECTIONS for a in (0, 90)]
    if report['full_declared_cases'] != full or not selected or len(selected) != len(set(selected)) or not set(selected) <= set(full):
        raise ValueError('Declared selection differs.')
    if sorted(r['name'] for r in report['cases']) != sorted(selected): raise ValueError('Selected case coverage differs.')
    staged = verify_models(root, report, manifest)
    counts = dict(cases=0, layouts=0, physical_faults=0, electrical_faults=0, raw_files=0, ac_samples=0, integrity_bindings=bindings)
    for plate in sorted({r['plate'] for r in report['cases']}):
        folder = root / 'physical' / str(plate); physical = load(folder / 'record.json')
        if physical not in report['physical'] or physical['status'] != 'PASS' or physical['size'] != [2, 10, 1]: raise ValueError('Physical case identity differs.')
        physical_counts = audit_physical(folder, plate, physical)
        for key, value in physical_counts.items(): counts[key] += value
    for row in report['cases']:
        plate, section, angle = row['plate'], row['section'], row['rotation']
        if row['name'] != f'p{plate}-{section}-r{angle}' or row['status'] != 'PASS': raise ValueError('Case label differs.')
        folder = root / row['name']
        if load(folder / 'record.json') != row: raise ValueError('Case receipt differs.')
        relative = f'physical/{plate}/valid-{angle}-plain/lvs-extraction/extracted.spice'
        native = root / relative
        if row['native_path'] != (Path(report['execution_root']) / relative).as_posix() or row['native_sha256'] != sha(native): raise ValueError('Original native extraction differs.')
        for fault, key in ((False, 'selected'), (True, 'wrong_section')):
            choice = ('hh' if section != 'hh' else 'll') if fault else section
            result = row[key]; dest = folder / ('wrong-section' if fault else 'selected')
            if result['executed_section'] != choice or sha(dest / 'probe.cir') != result['deck_sha256'] or sha(dest / 'probe.raw') != result['raw_sha256']: raise ValueError('Executed section/evidence differs.')
            check_deck(dest / 'probe.cir', choice, staged, row['native_path'], plate)
            counts['ac_samples'] += check_raw(dest / 'probe.raw', plate, coefficients[choice], result, coefficients[section])
            counts['raw_files'] += 1
            if result['status'] != ('MISMATCH' if fault else 'PASS'): raise ValueError('Wrong expected comparison outcome.')
        if any(row['selected']['maximum_relative_errors'][k] <= (.05 if k == 'swapped' else 1e-6) for k in PATHS[3:]) or row['wrong_section']['maximum_coefficient_normalized_error'] <= 1: raise ValueError('Fault sensitivity absent.')
        counts['electrical_faults'] += 6; counts['cases'] += 1
    return dict(status='PASS', qualified=False, chunk_complete=False, counts=counts, scope=__doc__, audit_sha256=sha(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--root', type=Path, required=True); ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args(); result = audit(a.root)
    a.output.write_bytes((json.dumps(result, indent=2) + '\n').encode()); print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
