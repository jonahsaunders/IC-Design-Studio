"""Run finite CMIM multiplicity comparisons from fully checked physical outputs."""
import argparse
from decimal import Decimal
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_ihp_cmim_multiplicity_electrical import CODE, linked_inputs, verify
from scripts.check_ihp_cmim_process_control import MANAGED_WRAPPER_SHA, MODEL, MODEL_NAMES, PDK, source_contract
from scripts.verify_frozen_ihp_cmim import FORBIDDEN, confined, require, safe, sha


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def read_units(path, physical):
    lines = path.read_text(encoding='utf-8').splitlines()
    out = []
    for line in lines:
        fields = line.split()
        if not fields or fields[0].startswith(('*', '.')):
            continue
        require(fields[0][0] == ('C' if physical else 'X') and fields[1:4] == ['C1', 'C2', 'cap_cmim'],
                'Unexpected actual physical or schematic device.')
        values = {}
        for token in fields[4:]:
            key, value = token.split('=')
            require(key.lower() not in values, 'Duplicate physical parameter.')
            suffix = value[-1:].lower()
            exponent = {'u': -6, 'p': -12}.get(suffix, 0)
            number = Decimal(value[:-1] if exponent else value)
            require(number.is_finite(), 'Nonfinite actual physical parameter.')
            parts = number.as_tuple()
            number = Decimal((parts.sign, parts.digits, parts.exponent + exponent))
            values[key.lower()] = str(number)
        out.append(dict(line=line.strip(), name=fields[0], values=values))
    return out


def render(inputs, section, model_text, corner_text):
    """Build the actual deck independently of the reader's expected deck."""
    core = re.search(r'(?im)^\.model cmim_core C \(([^\n]+)\)', model_text)[1]
    perimeter_coefficient = Decimal(re.search(r'\bCJSW=([0-9.Ee+-]+)', core)[1])
    body = re.search(r'(?is)\.subckt cap_cmim PLUS MINUS\s+(.*?)\.ends cap_cmim', model_text)[1]
    resistance = float(re.search(r'(?m)^R1 PLUS 1 r=([0-9.]+)m$', body)[1]) * 1e-3
    corner = re.search(r'(?is)\.LIB ' + section + r'\s+(.*?)\.ENDL ' + section + r'\b', corner_text)[1]
    terms = re.search(r'(?im)^\.param cap_carea\s*=\s*([0-9.Ee+*\-]+)\s*$', corner)[1].split('*')
    area_coefficient = math.prod((Decimal(term) for term in terms), start=Decimal(1))
    unit_capacitance = float(7 * 7 * area_coefficient + (7 + 7) * 2 * perimeter_coefficient)
    branches = {'catalog': [r['line'] for r in inputs['m2']['records']],
                'pair': [r['line'] for r in inputs['pair']['records']],
                'extracted': [f'Xraw{i} C1 C2 cap_cmim w={r["values"]["w"]} l={r["values"]["l"]} m={r["values"]["m"]} mm_ok=1'
                              for i, r in enumerate(inputs['native']['records'])],
                'literal': [f'R{i} C1 mid{i} {resistance:.17g}\nC{i} mid{i} C2 {unit_capacitance:.17g}' for i in (1, 2)],
                'count1': ['Xfault C1 C2 cap_cmim w=7u l=7u m=1 mm_ok=1'],
                'count3': ['Xfault C1 C2 cap_cmim w=7u l=7u m=3 mm_ok=1'],
                'areaonly': ['Xfault C1 C2 cap_cmim w=7u l=14u m=1 mm_ok=1'],
                'series': ['Xfault1 C1 junction cap_cmim w=7u l=7u m=1 mm_ok=1',
                           'Xfault2 junction C2 cap_cmim w=7u l=7u m=1 mm_ok=1', 'Rbias junction C2 1e12'],
                'wrongr': [f'R{i} C1 mid{i} {2 * resistance:.17g}\nC{i} mid{i} C2 {unit_capacitance:.17g}' for i in (1, 2)]}
    lines = ['CMIM multiplicity integration', f'.lib ../models/cornerCAP.lib {section}', '.temp 27']
    for name, devices in branches.items():
        lines += [f'.subckt {name} C1 C2', *devices, f'.ends {name}', f'V{name} {name} 0 DC 0 AC 1', f'X{name} {name} 0 {name}']
    probes = ' '.join(f'v({name}) i(v{name})' for name in branches)
    lines += ['.control', 'set filetype=ascii', 'set numdgt=17']
    for i, frequency in enumerate((1e5, 1e6, 1 / (2 * math.pi * resistance * unit_capacitance))):
        lines += [f'ac lin 1 {frequency:.17g} {frequency:.17g}', f'write ac-{i}.raw {probes}']
    return '\n'.join([*lines, 'quit', '.endc', '.end', ''])


def run(root, physical, out, engine, binary):
    require(sys.platform == 'linux', 'Producer requires native Linux.')
    root, physical, out, engine, binary = map(safe, (root, physical, out, engine, binary))
    require(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(physical), 'Use a fresh output outside source and physical evidence.')
    require(engine.is_file() and binary.is_file() and (engine == binary or (str(engine), str(binary), sha(engine)) ==
            ('/opt/icstudio/bin/ngspice', '/usr/bin/ngspice', MANAGED_WRAPPER_SHA)), 'Unverified simulator pairing.')
    # The physical reader must finish its complete selection before using any input.
    from scripts.check_ihp_cmim_multiplicity import verify_evidence
    physical_report = verify_evidence(physical)
    sources_before = source_contract(root)
    code_before = {name: sha(confined(root, name)) for name in CODE}
    out.mkdir()
    for name in ('inputs', 'home', 'tmp', 'models'):
        (out/name).mkdir()
    write(out/'physical-reader-report.json', physical_report)
    inputs = {}
    input_sources = {}
    for rotation in (0, 90):
        row = {}
        for kind in ('m2', 'pair', 'native'):
            relative = f'{"m2" if kind == "native" else kind}-{rotation}/job/physical-flow/' + (
                'lvs-extraction/native.cir' if kind == 'native' else 'schematic.spice')
            source = confined(physical, relative)
            target = out/f'inputs/{kind}-{rotation}.spice'
            target.write_bytes(source.read_bytes())
            row[kind] = dict(sha256=sha(target), records=read_units(target, kind == 'native'))
            input_sources[relative] = sha(source)
        inputs[str(rotation)] = row
    write(out/'physical-inputs.json', dict(scope='audited full physical multiplicity output', inputs=inputs,
          physical_reader_report_sha256=sha(out/'physical-reader-report.json'), original_input_hashes=input_sources))
    require(linked_inputs(out) == inputs, 'Independent input audit disagrees.')
    env = dict(PATH='/usr/bin:/bin', HOME=str(out/'home'), TMPDIR=str(out/'tmp'), LANG='C.UTF-8', LC_ALL='C.UTF-8', TZ='UTC')
    runtime_env = env if engine == binary else {**env, 'LD_LIBRARY_PATH': str(engine.parent.parent/'lib')}
    linkage = subprocess.run(['/usr/bin/ldd', str(binary)], env=runtime_env, capture_output=True, check=True, timeout=10).stdout
    require(b'not found' not in linkage, 'Missing dynamic runtime dependency.')
    (out/'runtime-ldd.log').write_bytes(linkage)
    dependencies = [Path(v.decode()) for v in re.findall(rb'(/[^\s]+) \(0x', linkage)]
    require(all(FORBIDDEN not in path.parts for path in dependencies), 'Forbidden runtime dependency.')
    runtime_paths = {engine, binary, *(path.resolve() for path in dependencies)}
    runtime = {str(path): sha(safe(path)) for path in sorted(runtime_paths)}
    version = subprocess.run([str(engine), '-n', '-v'], env=env, capture_output=True, check=True, timeout=10)
    (out/'runtime-version.log').write_bytes(version.stdout + version.stderr)
    for name in MODEL_NAMES:
        (out/'models'/name).write_bytes((root/PDK/MODEL/name).read_bytes())
    model = (out/'models/capacitors_mod.lib').read_text()
    corners = (out/'models/cornerCAP.lib').read_text()
    returncodes = {}
    for rotation in (0, 90):
        for section in ('cap_typ', 'cap_bcs', 'cap_wcs'):
            key = f'{rotation}-{section}'
            folder = out/key
            folder.mkdir()
            (folder/'input.cir').write_text(render(inputs[str(rotation)], section, model, corners), encoding='ascii')
            with (folder/'engine.log').open('xb') as log:
                result = subprocess.run([str(engine), '-n', '-b', 'input.cir'], cwd=folder, env=env, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=30)
            returncodes[key] = result.returncode
            require(result.returncode == 0, 'Native electrical run failed: ' + key)
    after = {str(path): sha(safe(path)) for path in sorted(runtime_paths)}
    require(after == runtime and source_contract(root) == sources_before and
            {name: sha(confined(root, name)) for name in CODE} == code_before and
            {name: sha(confined(physical, name)) for name in input_sources} == input_sources,
            'Runtime, model, source code or physical inputs changed.')
    write(out/'invocation.json', dict(engine=str(engine), binary=str(binary), argv=[str(engine), '-n', '-b', 'input.cir'],
          environment=env, returncodes=returncodes, runtime_before=runtime, runtime_after=after, source_code=code_before,
          version_sha256=sha(out/'runtime-version.log'), linkage_sha256=sha(out/'runtime-ldd.log')))
    result = verify(root, out)
    write(out/'comparison.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--physical-evidence', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--native-binary', type=Path, required=True)
    args = parser.parse_args()
    result = run(ROOT, args.physical_evidence, args.out, args.ngspice, args.native_binary)
    print(json.dumps(dict(status=result['status'], native_runs=len(result['results']), out=str(args.out))))


if __name__ == '__main__':
    main()
