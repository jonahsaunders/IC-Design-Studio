"""Reproduce the pinned public IHP measurement fixture in isolated native processes.

This is an optional external reference workflow, not the application's generated
coil model or a general accuracy qualification. Existing outputs are never reused.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import openems_runtime, openems_waves
from scripts import audit_ihp_measured_reference as reference

WORKFLOW = ROOT/'tests/fixtures/ihp-measured-workflow-v1'
WORKFLOW_LOCK = '0506ea2973cb4c5485ba2864f452f46602a2d51150b0eebafb06a2d1ee9921a3'
INPUTS = {'coil.gds': 'L6n2_with_ports.gds', 'passicut.xml': 'openEMS_SG13G2_200um_passicut.xml'}
INTRO = '# IC Design Studio reproduction: one native excitation per process, four threads, selected mesh, -60 dB, preserve Windows path case. Original retained unchanged.\n'


def verify_workflow(root=WORKFLOW):
    root = Path(root)
    if reference.sha(root/'SOURCE.json') != WORKFLOW_LOCK:
        raise ValueError('Changed measured-coil workflow inventory.')
    lock = json.loads((root/'SOURCE.json').read_bytes())
    expected = {row['path'] for row in lock['files']}
    if {p.relative_to(root).as_posix() for p in (root/'gds2openEMS').glob('*.py')} != expected:
        raise ValueError('Unexpected measured-coil workflow module set.')
    for row in lock['files']:
        data = (root/row['path']).read_bytes()
        blob = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if len(data) != row['bytes'] or reference.sha(root/row['path']) != row['sha256'] or blob != row['git_blob']:
            raise ValueError('Changed measured-coil workflow module: '+row['path'])
    if reference.sha(root/'LICENSE') != reference.sha(reference.FIXTURE/'LICENSE'):
        raise ValueError('Changed measured-coil workflow license.')
    return lock


def render(mesh, port):
    """Only change process isolation, selected sweep points and Windows path case.

    Four threads are fixed to reproduce the retained local runs. Geometry,
    materials, pulse, boundaries, mesh algorithm and -60 dB target stay upstream.
    """
    if mesh not in (1, 2) or port not in (1, 2): raise ValueError('Invalid mesh or active port.')
    reference.verify_sources()
    text = (reference.FIXTURE/'original-workflow.py').read_text()
    changes = {"settings['numThreads'] = 0": "settings['numThreads'] = 4",
               'for cellsize in [1, 2]:': f'for cellsize in [{mesh}]:',
               'for energylimit in [-40,-50,-60]:': 'for energylimit in [-60]:',
               'script_path = utilities.get_script_path(__file__)': 'script_path = os.path.dirname(os.path.abspath(__file__))',
               'for excite_portnumbers in simulation_ports.all_active_excitations():': f'for excite_portnumbers in [[{port}]]:'}
    for before, after in changes.items():
        if text.count(before) != 1: raise ValueError('Upstream workflow anchor changed.')
        text = text.replace(before, after)
    marker = '        # Initialize an empty matrix for S-parameters'
    if text.count(marker) != 1: raise ValueError('Upstream postprocessing anchor changed.')
    return INTRO+text.split(marker)[0]+"        print('ICSTUDIO_SINGLE_PORT_COMPLETE', flush=True)\n"


def prepare(output, mesh):
    reference.verify_sources(); lock = verify_workflow(); output = Path(output).resolve()
    if mesh not in (1, 2): raise ValueError('Invalid mesh.')
    # The unmodified upstream utility redirects longer Windows paths into a
    # shared temporary folder. Reject that case before staging, so another
    # run's raw files can never be reused or overwritten through its fallback.
    if os.name == 'nt' and len(str(output/f'isolated/mesh{mesh}/port1/output')) > 200:
        raise ValueError('Choose a shorter output path; the upstream Windows workflow redirects paths over 200 characters.')
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(WORKFLOW/'gds2openEMS', output/'gds2openEMS')
    shutil.copyfile(WORKFLOW/'SOURCE.json', output/'workflow-source-lock.json')
    shutil.copyfile(WORKFLOW/'LICENSE', output/'LICENSE')
    for port in (1, 2):
        stage = output/f'isolated/mesh{mesh}/port{port}'; stage.mkdir(parents=True)
        (stage/'output').mkdir()
        for src, dest in INPUTS.items(): shutil.copyfile(reference.FIXTURE/src, stage/dest)
        (stage/'run.py').write_text(render(mesh, port), encoding='utf-8')
    record = dict(schema=1, source_commit=lock['commit'], mesh_um=mesh, threads=4, energy_target_db=-60,
                  runner_sha256=reference.sha(__file__), workflow_lock_sha256=WORKFLOW_LOCK,
                  reference_lock_sha256=reference.LOCK_SHA256, qualified=False,
                  modifications=['One excitation per native process.', 'Select one published mesh and -60 dB.',
                                 'Use four threads.', 'Preserve Windows path case.',
                                 'Read both raw probe columns only after both processes finish.'],
                  scope=__doc__)
    (output/'prepared.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    return output


def inputs(root, mesh, port):
    """Require the exact derived script and upstream physics before and after Run."""
    root = Path(root); stage = root/f'isolated/mesh{mesh}/port{port}'
    reference.verify_sources(); lock = verify_workflow()
    if reference.sha(root/'workflow-source-lock.json') != WORKFLOW_LOCK:
        raise ValueError('Changed staged workflow inventory.')
    if (stage/'run.py').read_text() != render(mesh, port):
        raise ValueError('Changed isolated native script.')
    files = [stage/'run.py', root/'workflow-source-lock.json']
    for src, dest in INPUTS.items():
        if reference.sha(stage/dest) != reference.sha(reference.FIXTURE/src):
            raise ValueError('Changed native geometry or stackup.')
        files.append(stage/dest)
    expected = {row['path'] for row in lock['files']}
    if {p.relative_to(root).as_posix() for p in (root/'gds2openEMS').glob('*.py')} != expected:
        raise ValueError('Unexpected staged workflow modules.')
    for row in lock['files']:
        if reference.sha(root/row['path']) != row['sha256']:
            raise ValueError('Changed staged workflow module.')
        files.append(root/row['path'])
    return {p.relative_to(root).as_posix(): reference.sha(p) for p in files}


def energy(log, port):
    first = 'Starting FDTD simulation for excitation  ['+str(port)+']'
    last = 'FDTD simulation completed successfully for excitation  ['+str(port)+']'
    if any(log.count(token) != 1 for token in (first, last, 'ICSTUDIO_SINGLE_PORT_COMPLETE')):
        raise ValueError('Missing or repeated native completion markers.')
    if not log.index(first) < log.index(last) < log.index('ICSTUDIO_SINGLE_PORT_COMPLETE'):
        raise ValueError('Native completion markers are out of order.')
    segment = log.split(first, 1)[1].split(last, 1)[0]
    lines = [line for line in segment.splitlines() if 'Energy:' in line]
    match = re.search(r'\(\s*([-+0-9.]+)dB\)', lines[-1]) if lines else None
    value = float(match[1]) if match else float('nan')
    if not math.isfinite(value) or value > -60:
        raise ValueError('Native residual energy has not reached -60 dB.')
    if 'Running FDTD engine' not in segment or 'Max. number of timesteps' not in segment:
        raise ValueError('Missing native engine execution.')
    return value


def execute(root, mesh, port, python, dependency_paths=(), timeout=10800):
    root = Path(root).resolve(); stage = root/f'isolated/mesh{mesh}/port{port}'
    before = inputs(root, mesh, port); python = Path(python).resolve()
    env = openems_runtime.environment(python)
    env['PYTHONPATH'] = os.pathsep.join(str(p) for p in [root, *map(lambda p: Path(p).resolve(), dependency_paths)])
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    command = [str(python), str(stage/'run.py')]; start = time.monotonic()
    timed_out = False
    with (stage/'native.log').open('xb') as stream:
        try: result = subprocess.run(command, cwd=stage, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True; result = None
    input_error = ''
    try: after = inputs(root, mesh, port)
    except (OSError, ValueError) as exc: after = {}; input_error = str(exc)
    output_error = ''; outputs = {}
    if result is not None and result.returncode == 0 and before == after:
        try:
            energy((stage/'native.log').read_text(), port)
            outputs = probe_bindings(root, mesh, port)
        except (OSError, ValueError) as exc: output_error = str(exc)
    record = dict(schema=2, returncode=result.returncode if result else None, timed_out=timed_out,
                  elapsed_seconds=time.monotonic()-start, command=command, inputs=before,
                  inputs_unchanged=before == after, input_error=input_error, mesh_um=mesh, active_port=port,
                  outputs=outputs, output_error=output_error,
                  threads=4, energy_target_db=-60, log_sha256=reference.sha(stage/'native.log'),
                  executable_sha256=reference.sha(python),
                  qualified=False, chunk_complete=False)
    (stage/'execution.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    if record['returncode'] != 0 or not record['inputs_unchanged'] or output_error or len(outputs) != 4:
        raise ValueError('Native excitation failed; original log and execution record retained.')
    return record


def probe_bindings(root, mesh, active):
    root = Path(root)
    directory = root/f'isolated/mesh{mesh}/port{active}/output/run_mesh{mesh}_limit-60_data/sub-{active}'
    result = {}
    for port in (1, 2):
        for kind in ('ut', 'it'):
            path = directory/f'port_{kind}_{port}'
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError('Missing or empty native probe output.')
            result[path.relative_to(root).as_posix()] = reference.sha(path)
    return result


def read_probe(path, frequency):
    """Independent trapezoid-free openEMS Fourier convention, with bounded RAM."""
    np = reference.np; path = Path(path); before = reference.sha(path)
    header = []; coordinates = {}
    with path.open() as stream:
        for line in stream:
            if not line.startswith('%'): break
            if 'coordinates:' not in line: continue
            header.append(line.rstrip())
            match = re.match(r'% (start|stop)-coordinates: \(([^)]+)\) m(?:\s|$)', line)
            if not match or match[1] in coordinates: raise ValueError('Invalid native probe coordinate headers.')
            values = np.array([float(v) for v in match[2].split(',')])
            if values.shape != (3,) or not np.isfinite(values).all(): raise ValueError('Invalid native probe coordinate headers.')
            coordinates[match[1]] = values
    if set(coordinates) != {'start', 'stop'}:
        raise ValueError('Invalid native probe coordinate headers.')
    samples = np.loadtxt(path, comments='%')
    if samples.ndim != 2 or samples.shape[1] != 2 or len(samples) < 3 or not np.isfinite(samples).all():
        raise ValueError('Invalid native time samples.')
    dt = np.diff(samples[:, 0])
    if not np.all(dt > 0) or not np.allclose(dt, dt[0], rtol=1e-7, atol=0):
        raise ValueError('Nonuniform or reversed native sampling.')
    values = np.empty(len(frequency), complex)
    for start in range(0, len(frequency), 16):
        f = frequency[start:start+16]
        values[start:start+16] = 2*dt[0]*(np.exp(-2j*np.pi*f[:, None]*samples[:, 0])@samples[:, 1])
    if reference.sha(path) != before: raise ValueError('Native samples changed during readback.')
    return values, header, before


def audit(root, mesh, allow_legacy_unbound_probes=False):
    """Read original native U/I files and compare full complex two-port matrices."""
    np = reference.np; root = Path(root); stages = {}; files = {}; headers = {}; bindings = {}; output_bindings = {}
    f = np.linspace(0, 14e9, 401)[1:]; u = np.zeros((len(f), 2, 2), complex); current = u.copy()
    for active in (1, 2):
        verified = inputs(root, mesh, active); stage = root/f'isolated/mesh{mesh}/port{active}'
        record = json.loads((stage/'execution.json').read_bytes())
        if (record.get('returncode') != 0 or record.get('inputs_unchanged') is not True
                or record.get('mesh_um') != mesh or record.get('active_port') != active
                or record.get('threads') != 4 or record.get('energy_target_db') != -60):
            raise ValueError('Invalid native execution record.')
        # Older retained execution records omit only the separately pinned lock.
        expected = {p: h for p, h in verified.items() if p != 'workflow-source-lock.json'}
        if record['inputs'] not in (verified, expected): raise ValueError('Native execution inputs differ.')
        if reference.sha(stage/'native.log') != record['log_sha256']:
            raise ValueError('Changed native execution log.')
        output_bindings[str(active)] = verify_probe_bindings(record, root, mesh, active, allow_legacy_unbound_probes)
        stages[str(active)] = dict(energy_db=energy((stage/'native.log').read_text(), active), returncode=0)
        bindings[str(active)] = dict(execution_sha256=reference.sha(stage/'execution.json'), log_sha256=record['log_sha256'])
        directory = stage/f'output/run_mesh{mesh}_limit-60_data/sub-{active}'
        if (directory/'ABORT').exists(): raise ValueError('Native abort marker retained.')
        for port in (1, 2):
            for kind, matrix in [('ut', u), ('it', current)]:
                path = directory/f'port_{kind}_{port}'; values, position, digest = read_probe(path, f)
                key = f'{kind}_{port}'
                if active == 1: headers[key] = position
                elif headers[key] != position: raise ValueError('Excitations used different probes.')
                matrix[:, port-1, active-1] = values; files[path.relative_to(root).as_posix()] = digest
    incoming = (u+50*current)/2; outgoing = (u-50*current)/2
    s = outgoing@np.linalg.inv(incoming); z = u@np.linalg.inv(current); vector = np.array([1., -1.])
    if not np.isfinite(s).all() or not np.isfinite(z).all(): raise ValueError('Nonfinite native network.')
    full = dict(frequency=f, scattering=s, impedance=z, differential=vector@z@vector, reference=50.)
    legacy = np.empty_like(s)
    for col in (0, 1): legacy[:, :, col] = outgoing[:, :, col]/incoming[:, col, col, None]
    original_z = 50*(np.eye(2)+legacy)@np.linalg.inv(np.eye(2)-legacy)
    original = dict(frequency=f, scattering=legacy, impedance=original_z, differential=vector@original_z@vector, reference=50.)
    for index in range(len(f)):
        actual, _ = openems_waves.scattering(incoming[index].tolist(), outgoing[index].tolist())
        np.testing.assert_allclose(actual, s[index], rtol=1e-10, atol=1e-10)
        np.testing.assert_allclose(openems_waves.maximum_gain(actual), np.linalg.svd(s[index], compute_uv=False)[0], rtol=1e-12, atol=1e-12)
    gain = float(np.max(np.linalg.svd(s, compute_uv=False)))
    comparisons = {}
    for name in (f'openems-{mesh}um.s2p', 'measured.s2p', 'palace-2um.s2p'):
        target = reference.network((reference.FIXTURE/name).read_text())
        comparisons[name] = dict(original_workflow=reference.compare(original, target), full_incident_matrix=reference.compare(full, target))
    return dict(schema=1, status='AUDIT_MATCHED', mesh_um=mesh, source_commit=reference.COMMIT,
                auditor_sha256=reference.sha(__file__), reference_auditor_sha256=reference.sha(reference.__file__),
                input_records=bindings, stages=stages, probe_coordinate_headers=headers, files=files,
                execution_bound_probe_outputs=output_bindings,
                original_workflow_metrics=reference.metrics(original), full_incident_matrix_metrics=reference.metrics(full),
                maximum_scattering_gain=gain, sampled_passivity=gain <= 1+openems_waves.PASSIVITY_ALLOWANCE,
                maximum_original_vs_full_s_difference=float(np.max(abs(s-legacy))),
                maximum_reciprocity_error=float(np.max(abs(s[:, 0, 1]-s[:, 1, 0]))),
                minimum_impedance_hermitian_eigenvalue=float(np.min(np.linalg.eigvalsh((z+z.conj().transpose(0, 2, 1))/2))),
                comparisons=comparisons, frequency_hz=f.tolist(), z_real_ohm=full['differential'].real.tolist(),
                z_imag_ohm=full['differential'].imag.tolist(), s_real=s.real.tolist(), s_imag=s.imag.tolist(),
                qualified=False, chunk_complete=False,
                scope='Independent readback of this public fixture, with sampled passivity and explicit complex errors. No measurement uncertainty or general device-accuracy bound is inferred; AUDIT_MATCHED does not mean an accuracy gate passed.')


def verify_probe_bindings(record, root, mesh, active, allow_legacy=False):
    if record.get('schema') == 2:
        if record.get('timed_out') is not False or record.get('output_error'):
            raise ValueError('Native execution did not retain completed probe outputs.')
        if record.get('outputs') != probe_bindings(root, mesh, active):
            raise ValueError('Native probe outputs changed after execution.')
        return True
    if 'schema' in record or 'outputs' in record or not allow_legacy:
        raise ValueError('Native probes lack execution-time hashes; legacy readback requires explicit acknowledgement.')
    return False


def response_text(result):
    """Portable full-matrix response for this exact fixture, without re-fitting."""
    np = reference.np
    s = np.array(result['s_real'])+1j*np.array(result['s_imag']); f = np.array(result['frequency_hz'])
    if (f.ndim != 1 or len(f) < 3 or s.shape != (len(f), 2, 2) or not np.isfinite(f).all()
            or not np.isfinite(s).all() or f[0] <= 0 or not (np.diff(f) > 0).all()):
        raise ValueError('Invalid native response for Touchstone export.')
    lines = ['! Public IHP L6n2 fixture; full measured-incident-matrix conversion.',
             '! Source '+reference.COMMIT+'; mesh '+str(result['mesh_um'])+' um.',
             '! Geometry-specific reference result; not a general IHP compact model.', '# Hz S RI R 50']
    for frequency, matrix in zip(f, s):
        values = [frequency]
        for z in matrix.flatten(order='F'): values.extend((z.real, z.imag))
        lines.append(' '.join(format(float(value), '.17g') for value in values))
    return '\n'.join(lines)+'\n'


def save_result(result, output):
    output = Path(output); response = output.with_suffix('.s2p')
    if output.exists() or response.exists() or output == response:
        raise FileExistsError('Choose new, distinct JSON and Touchstone output paths.')
    text = response_text(result)
    # Check written precision through the independent matrix reader before any
    # output is created. Preserve every complex component and its frequency.
    parsed = reference.network(text); np = reference.np
    np.testing.assert_allclose(parsed['scattering'], np.array(result['s_real'])+1j*np.array(result['s_imag']), rtol=0, atol=0)
    np.testing.assert_allclose(parsed['frequency'], result['frequency_hz'], rtol=0, atol=0)
    with response.open('x', encoding='utf-8') as stream: stream.write(text)
    result = dict(result, touchstone=dict(file=response.name, sha256=reference.sha(response),
                  reference_ohm=50, conversion='S = B inv(A)', qualified=False))
    with output.open('x', encoding='utf-8') as stream: json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mesh-um', choices=(1, 2), type=int, required=True)
    parser.add_argument('--python', type=Path)
    parser.add_argument('--dependency-path', type=Path, action='append', default=[])
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--audit-existing', type=Path)
    parser.add_argument('--allow-legacy-unbound-probes', action='store_true',
                        help='Read historical execution records lacking output hashes, explicitly reporting that provenance limit.')
    args = parser.parse_args()
    if args.allow_legacy_unbound_probes and not args.audit_existing:
        parser.error('Legacy acknowledgement is only available for existing readback.')
    if args.audit_existing:
        if args.prepare_only or args.python or args.dependency_path: parser.error('Existing readback does not execute a solver.')
        result = audit(args.audit_existing, args.mesh_um, args.allow_legacy_unbound_probes)
        save_result(result, args.output)
    else:
        if not args.prepare_only and not args.python: parser.error('--python is required for native execution.')
        root = prepare(args.output, args.mesh_um)
        if args.prepare_only: return
        for port in (1, 2):
            print('Running isolated excitation', port, 'at', args.mesh_um, 'um', flush=True)
            execute(root, args.mesh_um, port, args.python, args.dependency_path)
        result = audit(root, args.mesh_um)
        save_result(result, root/'audit.json')
    print('Native reference readback completed; see the declared comparison errors and qualification limits.')


if __name__ == '__main__': main()
