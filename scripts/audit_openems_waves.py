"""Independently audit retained native port waveforms without attaching results.

Reads actual voltage/current probe files and compares direct Z = U inv(I) with
the application's full incident-wave conversion. Incomplete/aborted stages stay
incomplete. Historical files are never relabeled as new-driver executions.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import openems_backend as backend, openems_waves
from icstudio.model import digest, file_digest


def audit(source):
    source = Path(source).resolve(); model = json.loads((source/'model.json').read_text())
    if digest({k:v for k,v in model.items() if k != 'run_hash'}) != model['run_hash']:
        raise ValueError('Changed original model identity.')
    if file_digest(source/'driver.py') != model['driver_sha256']:
        raise ValueError('Changed original native driver.')
    files = {name:file_digest(source/name) for name in ('model.json', 'driver.py', 'manifest.json', 'exchange.zip')}
    opts = model['settings']; frequency = np.geomspace(opts['f_start_hz'], opts['f_stop_hz'], opts['samples'])
    report = dict(schema=1, status='AUDIT_MATCHED', source_run_hash=model['run_hash'],
                  original_wave_basis=model.get('wave_basis', 'legacy-independent-column'),
                  audit_wave_basis=openems_waves.BASIS, stages={}, meshes={}, incomplete=[],
                  scope=__doc__, qualified=False, chunk_complete=False)
    impedances = {}
    for label, scale in (('base', 1.), ('fine', .7)):
        if label == 'fine' and not opts['mesh_check']: continue
        pair = []
        for active in (1, 2):
            name = f'{label}-{active}'
            for path in (name+'.json', name+'.log', name+'/ABORT'):
                if (source/path).is_file(): files[path] = file_digest(source/path)
            if not (source/(name+'.json')).is_file() or (source/name/'ABORT').exists():
                report['incomplete'].append(name); continue
            log = (source/(name+'.log')).read_text()
            row = backend.check_completion(log, source, model, scale, active)
            report['stages'][name] = {k:row[k] for k in ('energy_db', 'cells', 'mesh_lines', 'versions')}
            pair.append(row)
        if len(pair) != 2: continue
        u = np.zeros((len(frequency), 2, 2), complex); current = u.copy()
        for column, active in enumerate((1, 2)):
            for row, port in enumerate((1, 2)):
                for kind, matrix in (('ut', u), ('it', current)):
                    name = f'{label}-{active}/port_{kind}_{port}'; path = source/name
                    data = np.loadtxt(path, comments='%')
                    if data.ndim != 2 or data.shape[1] != 2 or len(data) < 3 or not np.all(np.isfinite(data)):
                        raise ValueError('Malformed native probe: '+name)
                    intervals = np.diff(data[:,0])
                    if not np.all(intervals > 0) or not np.allclose(intervals, intervals[0], rtol=1e-7, atol=0):
                        raise ValueError('Probe sample times are not uniformly increasing: '+name)
                    # Independent direct Fourier sums at the recorded E/H times.
                    matrix[:,row,column] = 2*intervals[0]*(np.exp(-2j*np.pi*frequency[:,None]*data[:,0])@data[:,1])
                    files[name] = file_digest(path)
        incoming = (u+50*current)/2; reflected = (u-50*current)/2
        converted = {}
        for column, row in enumerate(pair):
            denominator = incoming[:,column,column,None]
            a = incoming[:,:,column]/denominator; b = reflected[:,:,column]/denominator
            prefixes = (('a',a), ('b',b)) if model.get('wave_basis') else (('s',b),)
            for prefix, expected in prefixes:
                actual = np.array(row[prefix+'_real'])+1j*np.array(row[prefix+'_imag'])
                np.testing.assert_allclose(actual, expected, rtol=1e-9, atol=1e-10,
                                           err_msg='Native probe/driver output disagreement')
            converted[f'{label}-{column+1}'] = dict(row, wave_basis=openems_waves.BASIS,
                a_real=a.real.tolist(), a_imag=a.imag.tolist(), b_real=b.real.tolist(), b_imag=b.imag.tolist())
        # This dictionary is an in-memory calculation input only. Never save it
        # as a staged model or claim its source hash identifies a fresh run.
        diagnostic = {}
        _, app = backend._pair_result(dict(model, wave_basis=openems_waves.BASIS), converted, scale, diagnostic)
        z = u@np.linalg.inv(current); vector = np.array([1., -1.]); differential = vector@z@vector
        np.testing.assert_allclose(np.array(app['z_real_ohm'])+1j*np.array(app['z_imag_ohm']), differential, rtol=1e-10, atol=1e-10)
        s = reflected@np.linalg.inv(incoming)
        report['meshes'][label] = dict(**diagnostic, frequency_hz=frequency.tolist(),
            resistance_ohm=differential.real.tolist(), reactance_ohm=differential.imag.tolist(),
            maximum_singular_value=float(np.max(np.linalg.svd(s, compute_uv=False))),
            maximum_reciprocity_error=float(np.max(abs(s[:,0,1]-s[:,1,0]))),
            minimum_impedance_hermitian_eigenvalue=float(np.min(np.linalg.eigvalsh((z+z.conj().transpose(0,2,1))/2))))
        impedances[label] = differential
    if opts['mesh_check'] and set(impedances) == {'base', 'fine'}:
        base, fine = impedances['base'], impedances['fine']
        ze = float(np.max(abs(base-fine)/np.maximum(abs(fine), 1e-3)))
        re = float(np.max(abs(base.real-fine.real)/np.maximum(abs(fine.real), 1e-3)))
        report['mesh_comparison'] = dict(max_relative_z_change=ze, max_relative_r_change=re,
                                         tolerance=opts['mesh_tolerance'], absolute_floor_ohm=1e-3)
        report['numerical_gate'] = 'passes_recorded_mesh_and_nonnegative_resistance' if max(ze,re) <= opts['mesh_tolerance'] and np.min(fine.real) >= 0 else 'rejected'
    else: report['numerical_gate'] = 'incomplete' if opts['mesh_check'] else 'mesh_not_checked'
    if any(file_digest(source/name) != sha for name,sha in files.items()):
        raise ValueError('Native evidence changed during readback.')
    report['files'] = files
    report['auditor_sha256'] = file_digest(__file__)
    report['converter_sha256'] = file_digest(ROOT/'icstudio/openems_waves.py')
    report['backend_sha256'] = file_digest(ROOT/'icstudio/openems_backend.py')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = audit(args.source)
    with args.output.open('x', encoding='utf-8') as stream: stream.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('meshes', 'files', 'stages')}, indent=2))


if __name__ == '__main__': main()
