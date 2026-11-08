"""Audit the finite GPL IHP center-tapped reference, retaining all three ports.

The source is one Palace-simulated example and a fitted passive circuit. Neither
a fourth catalog body terminal nor physical calibration is inferred from it.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT/'tests/fixtures/ihp-ct-reference-v1'
LOCK_SHA256 = 'ec527cb7043bbae8e1b6a4e7b5f2ef88e27c923d3696287fbb2d3130cddf8c93'
SPEC = importlib.util.spec_from_file_location('ct_reference_reader', ROOT/'icstudio/three_port_reference.py')
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)
PORTS = ('p1', 'p2', 'ct')
MODEL = 'ct_inductor_model'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_files():
    return {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p)
            for p in [Path(__file__).resolve(), ROOT/'icstudio/three_port_reference.py']}


def verify_sources(root=FIXTURE):
    root = Path(root)
    require(not root.is_symlink() and sha(root/'SOURCE.json') == LOCK_SHA256, 'Changed CT source inventory.')
    record = json.loads((root/'SOURCE.json').read_bytes())
    expected = {'SOURCE.json', 'NOTICES.txt', *(r['file'] for r in record['files'])}
    require({p.name for p in root.iterdir()} == expected, 'Changed CT source file set.')
    for p in root.iterdir():
        require(p.is_file() and not p.is_symlink(), 'Nonregular CT source file.')
    require(sha(root/'NOTICES.txt') == record['notices_sha256'], 'Changed CT notices.')
    for row in record['files']:
        raw = (root/row['file']).read_bytes()
        blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        require(len(raw) == row['bytes'] and sha(root/row['file']) == row['sha256'] and blob == row['git_blob'],
                'Changed CT source: '+row['file'])
    require(record['port_order'] == list(PORTS) and record['common_reference_node'] == '0'
            and record['separate_body_terminal'] is False, 'Changed CT terminal contract.')
    return record


def independent_touchstone(text):
    """NumPy decoder, separate from the application's complex/matrix arithmetic."""
    lines = [line.split('!', 1)[0].strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    require(lines and lines[0].startswith('#'), 'Missing reference option line.')
    words = lines[0][1:].upper().split()
    require(len(words) == 5 and words[0] in ('HZ', 'KHZ', 'MHZ', 'GHZ')
            and words[1] == 'S' and words[2] in ('RI', 'DB', 'MA') and words[3] == 'R',
            'Unexpected reference options.')
    z0 = float(words[4])
    require(math.isfinite(z0) and z0 > 0, 'Invalid reference impedance.')
    numbers = np.asarray([float(word) for line in lines[1:] for word in line.split()], dtype=float)
    require(numbers.size and numbers.size % 19 == 0 and np.isfinite(numbers).all(), 'Incomplete reference samples.')
    rows = numbers.reshape(-1, 19)
    f = rows[:, 0] * {'HZ': 1, 'KHZ': 1e3, 'MHZ': 1e6, 'GHZ': 1e9}[words[0]]
    require((f > 0).all() and (np.diff(f) > 0).all(), 'Invalid reference grid.')
    a, b = rows[:, 1::2], rows[:, 2::2]
    if words[2] == 'RI':
        scattering = a + 1j*b
    else:
        require(words[2] != 'MA' or (a >= 0).all(), 'Invalid reference magnitude.')
        scattering = (np.power(10., a/20) if words[2] == 'DB' else a) * np.exp(1j*b*np.pi/180)
    scattering = scattering.reshape(-1, 3, 3)
    require(np.isfinite(scattering).all(), 'Nonfinite reference response.')
    return f, scattering, z0


def s_to_y(s, z0):
    eye = np.eye(3, dtype=complex)
    return np.asarray([np.linalg.solve((eye+x).T, (eye-x).T).T/z0 for x in s])


def y_to_s(y, z0):
    eye = np.eye(3, dtype=complex)
    return np.asarray([np.linalg.solve((eye+z0*x).T, (eye-z0*x).T).T for x in y])


def parse_circuit(text):
    """Strict finite R/L/C/K SPICE reader. No includes, expressions or active devices."""
    elements, coupling, names = [], [], set()
    started = ended = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('*'):
            continue
        words = line.lower().split()
        if words[0] == '.subckt':
            require(not started and not ended and words == ['.subckt', MODEL, *PORTS],
                    'Unexpected model declaration or terminal order.')
            started = True
            continue
        if words[0] == '.ends':
            require(started and not ended and words in [['.ends'], ['.ends', MODEL]], 'Unexpected model end.')
            ended = True
            continue
        require(started and not ended and len(words) == 4 and words[0][0] in 'rlck',
                'Unsupported circuit statement.')
        name, n1, n2, literal = words
        require(name not in names and re.fullmatch('[a-z][a-z0-9_]*', name), 'Duplicate or invalid element name.')
        names.add(name)
        require(all(re.fullmatch('[a-z0-9_]+', n) for n in (n1, n2)), 'Invalid circuit node or reference.')
        value = float(literal)
        require(math.isfinite(value), 'Nonfinite circuit value.')
        if name[0] == 'k':
            require(-1 < value < 1 and n1 != n2, 'Invalid mutual coupling.')
            coupling.append((name, n1, n2, value))
        else:
            require(value > 0 and n1 != n2, 'Passive elements must have positive values and distinct nodes.')
            elements.append((name, n1, n2, value))
    require(started and ended and elements, 'Incomplete passive subcircuit.')
    nodes = {n for _, n1, n2, _ in elements for n in (n1, n2)}
    require(set(PORTS).issubset(nodes) and '0' in nodes, 'Missing port or explicit common reference.')
    inductors = [x for x in elements if x[0][0] == 'l']
    lookup = {x[0]: i for i, x in enumerate(inductors)}
    l_matrix = np.diag([x[3] for x in inductors])
    pairs = set()
    for _, a, b, k in coupling:
        require(a in lookup and b in lookup and frozenset((a, b)) not in pairs, 'Invalid or duplicate coupled-inductor pair.')
        pairs.add(frozenset((a, b)))
        i, j = lookup[a], lookup[b]
        l_matrix[i, j] = l_matrix[j, i] = k*np.sqrt(l_matrix[i, i]*l_matrix[j, j])
    require(inductors and np.linalg.eigvalsh(l_matrix).min() > 0, 'Nonpositive inductance matrix.')
    return dict(elements=elements, coupling=coupling, inductors=inductors, inductance=l_matrix,
                nodes=list(PORTS)+sorted(nodes-set(PORTS)-{'0'}), ground='0')


def circuit_admittance(circuit, frequencies):
    """Independent modified nodal analysis including the full mutual-inductance matrix."""
    nodes = circuit['nodes']
    index = {node: i for i, node in enumerate(nodes)}
    n, nl = len(nodes), len(circuit['inductors'])
    conductance = np.zeros((n, n))
    capacitance = np.zeros((n, n))
    incidence = np.zeros((n, nl))
    def vector(a, b):
        row = np.zeros(n)
        if a != '0':
            row[index[a]] += 1
        if b != '0':
            row[index[b]] -= 1
        return row
    for name, a, b, value in circuit['elements']:
        v = vector(a, b)
        if name[0] == 'r':
            conductance += np.outer(v, v)/value
        elif name[0] == 'c':
            capacitance += np.outer(v, v)*value
    for i, (_, a, b, _) in enumerate(circuit['inductors']):
        incidence[:, i] = vector(a, b)
    out = []
    for f in frequencies:
        require(math.isfinite(float(f)) and f > 0, 'Invalid circuit frequency.')
        w = 2*np.pi*f
        matrix = np.block([[conductance+1j*w*capacitance, incidence],
                           [incidence.T, -1j*w*circuit['inductance']]])
        known = np.arange(3)
        unknown = np.arange(3, n+nl)
        xu = np.linalg.solve(matrix[np.ix_(unknown, unknown)], -matrix[np.ix_(unknown, known)])
        y = matrix[:3, :3] + matrix[np.ix_(known, unknown)] @ xu
        require(np.isfinite(y).all(), 'Nonfinite passive response.')
        out.append(y)
    return np.asarray(out)


def deck(frequencies, excitation):
    require(type(excitation) is int and 0 <= excitation < 3, 'Invalid port excitation.')
    values = ' '.join(format(float(f), '.17g') for f in frequencies)
    voltages = '\n'.join(f'V{port} {port} 0 DC 0 AC {int(i == excitation)}' for i, port in enumerate(PORTS))
    return (f'CT reference independent excitation {excitation+1}\n.include model.sp\n'
            f'Xref p1 p2 ct {MODEL}\n{voltages}\n.control\nset noaskquit\n'
            'set wr_singlescale\nset numdgt=17\nset appendwrite\n'
            f'foreach f {values}\nac lin 1 $f $f\nwrdata response.txt i(vp1) i(vp2) i(vct)\nend\n'
            f'echo CT_REFERENCE_COMPLETE_{excitation+1}\nquit\n.endc\n.end\n')


def run_native(output, engine, frequencies, root=FIXTURE):
    """Execute only the retained circuit, with three independent clamped-port excitations."""
    output, engine, root = Path(output), Path(engine).resolve(), Path(root)
    require(engine.is_file() and not engine.is_symlink(), 'Select an actual ngspice executable.')
    output.mkdir(parents=True, exist_ok=False)
    engine_before = sha(engine)
    sources_before = source_files()
    verify_sources(root)
    version = subprocess.run([str(engine), '-v'], capture_output=True, timeout=30)
    (output/'engine-version.log').write_bytes(version.stdout+version.stderr)
    require(version.returncode == 0 and b'ngspice' in (version.stdout+version.stderr).lower(), 'Unexpected native engine.')
    commands = []
    for excitation in range(3):
        directory = output/f'port-{excitation+1}'
        directory.mkdir()
        shutil.copyfile(root/'fitted.sp', directory/'model.sp')
        text = deck(frequencies, excitation)
        (directory/'input.sp').write_bytes(text.encode())
        command = [str(engine), '-n', '-b', 'input.sp']
        env = dict(os.environ)
        for key in list(env):
            if key.upper().startswith(('SPICE', 'NGSPICE')):
                del env[key]
        try:
            completed = subprocess.run(command, cwd=directory, env=env, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired as exc:
            (directory/'stdout.log').write_bytes(exc.stdout or b'')
            (directory/'stderr.log').write_bytes((exc.stderr or b'')+b'\nCT_REFERENCE_TIMEOUT\n')
            raise ValueError('Native execution timed out; partial logs are not acceptance.') from exc
        (directory/'stdout.log').write_bytes(completed.stdout)
        (directory/'stderr.log').write_bytes(completed.stderr)
        commands.append(dict(excitation=excitation, command=command, returncode=completed.returncode))
        require(completed.returncode == 0 and f'CT_REFERENCE_COMPLETE_{excitation+1}'.encode() in completed.stdout,
                'Native three-port execution failed; retained logs are not acceptance.')
    require(sha(engine) == engine_before and source_files() == sources_before, 'Execution inputs changed.')
    verify_sources(root)
    files = {p.relative_to(output).as_posix(): dict(bytes=p.stat().st_size, sha256=sha(p))
             for p in sorted(output.rglob('*')) if p.is_file()}
    receipt = dict(schema=1, engine=dict(path=str(engine), sha256=engine_before),
                   source_files=sources_before, source_manifest=LOCK_SHA256,
                   port_order=list(PORTS), common_reference='0', commands=commands, files=files)
    (output/'native.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    return receipt


def read_native(output, frequencies, root=FIXTURE):
    output, root = Path(output), Path(root)
    require(not output.is_symlink(), 'Linked native evidence root.')
    receipt = json.loads((output/'native.json').read_bytes())
    require(receipt['source_files'] == source_files() and receipt['source_manifest'] == LOCK_SHA256,
            'Native evidence belongs to different authored inputs.')
    require(receipt['port_order'] == list(PORTS) and receipt['common_reference'] == '0', 'Changed native port contract.')
    files = receipt['files']
    expected = {'engine-version.log'} | {f'port-{i}/{name}' for i in range(1, 4)
        for name in ('input.sp', 'model.sp', 'stdout.log', 'stderr.log', 'response.txt')}
    require(set(files) == expected, 'Incomplete native file inventory.')
    allowed = {*files, 'native.json', 'verification.json'}
    paths = list(output.rglob('*'))
    require(not any(p.is_symlink() for p in paths), 'Linked native evidence member.')
    actual = {p.relative_to(output).as_posix() for p in paths if p.is_file()}
    require(set(files)|{'native.json'} <= actual <= allowed, 'Missing or extra native evidence.')
    for name, row in files.items():
        path = output/name
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(output.resolve()), 'Invalid native path.')
        require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'Changed native evidence: '+name)
    require(len(receipt['commands']) == 3, 'Missing native excitation.')
    require(b'ngspice' in (output/'engine-version.log').read_bytes().lower()
            and re.fullmatch('[0-9a-f]{64}', receipt['engine']['sha256']), 'Invalid native engine identity.')
    columns = []
    for excitation in range(3):
        directory = output/f'port-{excitation+1}'
        command = receipt['commands'][excitation]
        require(command['excitation'] == excitation and command['returncode'] == 0
                and command['command'] == [receipt['engine']['path'], '-n', '-b', 'input.sp'], 'Changed native invocation.')
        require((directory/'input.sp').read_bytes() == deck(frequencies, excitation).encode(), 'Changed native excitation deck.')
        require((directory/'model.sp').read_bytes() == (root/'fitted.sp').read_bytes(), 'Changed native circuit.')
        stdout = (directory/'stdout.log').read_bytes()
        require(f'CT_REFERENCE_COMPLETE_{excitation+1}'.encode() in stdout, 'Missing native completion marker.')
        table = np.loadtxt(directory/'response.txt', ndmin=2)
        require(table.shape == (len(frequencies), 7) and np.isfinite(table).all(), 'Incomplete native response matrix.')
        np.testing.assert_allclose(table[:, 0], frequencies, rtol=1e-12, atol=0)
        # SPICE voltage-source current points into the source; DUT current has the opposite sign.
        columns.append(-(table[:, 1::2]+1j*table[:, 2::2]))
    return np.stack(columns, axis=2), receipt


def audit(root=FIXTURE, native=None):
    root = Path(root)
    source = verify_sources(root)
    arrays = {}
    for name in ('reference.s3p', 'fitted.s3p'):
        text = (root/name).read_text(encoding='utf-8')
        f, s, z0 = independent_touchstone(text)
        app = reader.touchstone3(text)
        np.testing.assert_allclose(app['frequency_hz'], f, rtol=1e-14, atol=0)
        np.testing.assert_allclose(app['scattering'], s, rtol=1e-13, atol=1e-14)
        np.testing.assert_allclose(reader.matrices(app, 'y'), s_to_y(s, z0), rtol=1e-9, atol=1e-12)
        arrays[name] = (f, s, z0, app)
    f, raw_s, z0, app = arrays['reference.s3p']
    ff, fit_s, fit_z0, _ = arrays['fitted.s3p']
    require(np.array_equal(f, ff) and z0 == fit_z0 == 50 and len(f) == 82, 'Changed reference sample contract.')
    circuit = parse_circuit((root/'fitted.sp').read_text())
    y = circuit_admittance(circuit, f)
    calculated_s = y_to_s(y, z0)
    eigenvalues = np.linalg.eigvalsh((y+y.conj().transpose(0, 2, 1))/2)
    require(eigenvalues.min() >= -1e-12, 'Circuit is not passive on the retained grid.')
    np.testing.assert_allclose(y, y.transpose(0, 2, 1), rtol=1e-9, atol=1e-12)
    response = reader.center_tap_impedances(app, coil_ports=(0, 1), center_tap=2)
    summary = dict(schema=1, status='PASS_SOURCE_AND_AUTHORED_ARITHMETIC',
        source_commit=source['commit'], source_manifest_sha256=LOCK_SHA256, source_files=source_files(),
        samples=len(f), band_hz=[float(f[0]), float(f[-1])], port_order=list(PORTS), common_reference='0',
        circuit=dict(passive_elements=len(circuit['elements']), mutual_couplings=len(circuit['coupling']),
                     minimum_inductance_eigenvalue_h=float(np.linalg.eigvalsh(circuit['inductance']).min()),
                     minimum_sampled_conductance_eigenvalue_s=float(eigenvalues.min())),
        comparisons=dict(
            maximum_printed_circuit_vs_full_precision_fit_s_absolute=float(np.max(abs(calculated_s-fit_s))),
            maximum_fit_vs_original_em_s_absolute=float(np.max(abs(fit_s-raw_s))),
            rms_fit_vs_original_em_s_absolute_by_entry=np.sqrt(np.mean(abs(fit_s-raw_s)**2, axis=0)).tolist()),
        conditions={key: dict(first_ohm=[values[0].real, values[0].imag],last_ohm=[values[-1].real, values[-1].imag])
                    for key,values in response.items() if key not in ('frequency_hz','coil_ports','center_tap')},
        comparison_scope='Fit-to-EM differences are descriptive. They are not calibration uncertainty or operating/reliability limits.',
        fresh_spice_execution=False, native_spice_response_verified=False, measurement=False, original_em_reproduced=False,
        catalog_binding_resolved=False, qualified=False, chunk_complete=False, limitations=source['limitations'])
    if native is not None:
        observed, receipt = read_native(native, f, root)
        np.testing.assert_allclose(observed, y, rtol=5e-8, atol=1e-10,
                                   err_msg='Actual native circuit response differs from independent MNA.')
        native_s = y_to_s(observed, z0)
        np.testing.assert_allclose(native_s, calculated_s, rtol=5e-8, atol=1e-10)
        summary.update(status='PASS_SOURCE_AND_NATIVE_CIRCUIT_READBACK', native_spice_response_verified=True,
            native=dict(engine=receipt['engine'], source_files=receipt['source_files'],
                        maximum_y_absolute_error_s=float(np.max(abs(observed-y))),
                        maximum_s_absolute_error=float(np.max(abs(native_s-calculated_s))),
                        excitations=3, complex_entries_per_sample=9))
    verify_sources(root)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ngspice', type=Path)
    parser.add_argument('--readback', type=Path)
    args = parser.parse_args()
    require(not args.output.exists() and not(args.ngspice and args.readback), 'Use new output and one native mode.')
    if args.ngspice:
        frequency, _, _ = independent_touchstone((FIXTURE/'reference.s3p').read_text())
        run_native(args.output, args.ngspice, frequency)
        native = args.output
    else:
        args.output.mkdir(parents=True, exist_ok=False)
        native = args.readback
    result = audit(native=native)
    result['fresh_spice_execution'] = bool(args.ngspice)
    (args.output/'verification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

