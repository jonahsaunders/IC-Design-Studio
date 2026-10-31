"""Check nonlinear capacitor multipliers against analytical small-signal currents."""
import argparse, json, math, os, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from icstudio.engines import parse_raw
from icstudio.model import file_digest
from scripts.qualify_standard_mos import write

CASES = {'default': ('', 1), 'literal': ('m=3', 3), 'scientific': ('m=3e0', 3),
         'parameter': ('m={copies}', 3), 'expression': ('m={copies+1}', 4)}


def deck(bias):
    lines = ['* Analytical nonlinear-capacitor multiplier regression', '.param copies=3']
    for name, (suffix, factor) in CASES.items():
        lines += [f'V{name} {name} 0 {bias:g} AC 1',
                  f"C{name} {name} 0 c='1p*(1+tanh(v({name})))' {suffix}"]
    lines += ['.subckt unit a b gain=1', "Cunit a b c='1p*(1+tanh(v(a,b)))' m={gain}",
              '.ends unit', f'Vnested nested 0 {bias:g} AC 1', 'Xnested nested 0 unit gain={copies}',
              f'Vcharge charge 0 {bias:g} AC 1', "Ccharge charge 0 q='1p*v(charge)' m={copies}",
              '.ac dec 5 100 10meg', '.save '+ ' '.join('i(v'+n+')' for n in (*CASES, 'nested', 'charge')), '.end']
    return '\n'.join(lines)+'\n'


def validate(variables, rows, complex_data, bias):
    if not complex_data or len(rows) != 26: raise ValueError('Missing complex analytical capacitor sweep.')
    indices = {name.casefold(): i for i, name in enumerate(variables)}; errors = {}
    for name, factor in {**{k: v[1] for k, v in CASES.items()}, 'nested': 3, 'charge': 3}.items():
        if 'i(v'+name+')' not in indices: raise ValueError('Missing multiplier current: '+name)
        worst = 0
        for i, row in enumerate(rows):
            f = 100*10**(i/5)
            if not math.isclose(row[0].real, f, rel_tol=1e-9): raise ValueError('Changed analytical frequency domain.')
            actual = row[indices['i(v'+name+')']]
            expected = -2j*math.pi*f*factor*1e-12*(1 if name == 'charge' else 1+math.tanh(bias))
            if not math.isfinite(actual.real) or not math.isfinite(actual.imag): raise ValueError('Nonfinite multiplier current.')
            worst = max(worst, abs(actual-expected)/(1e-14+1e-6*abs(expected)))
        errors[name] = worst
    if max(errors.values()) > 1: raise ValueError('Analytical capacitor multiplier mismatch: '+str(errors))
    return dict(status='PASS', vectors=len(errors), samples=26, maximum_normalized_error=max(errors.values()),
                channel_errors=errors, relative_tolerance=1e-6, absolute_tolerance_a=1e-14,
                tolerance_note='Allows the simulator numerical stabilizing shunt; no sub-1e-14-S conductance claim.')


def verify(executable, output):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    report = dict(status='RUNNING', engine_sha256=file_digest(executable), cases=[],
                  scope='Analytical AC tests of capacitor syntax/multipliers; no PDK or full runtime qualification.')
    for bias in (-.5, 0, .5):
        root = output/str(bias); root.mkdir(); (root/'input.cir').write_bytes(deck(bias).encode())
        cmd = [executable, '-n', '-D', 'ngbehavior=hsa', '-D', 'filetype=ascii', '-b', '-r', 'result.raw', 'input.cir']
        run = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=60,
                             env={**os.environ, 'OMP_THREAD_LIMIT': '1'})
        (root/'engine.log').write_bytes((run.stdout+run.stderr).encode()); row = dict(bias_v=bias, exit=run.returncode, command=cmd)
        try:
            if run.returncode: raise ValueError('Simulator failed; inspect retained engine.log.')
            row.update(validate(*parse_raw(root/'result.raw'), bias))
            row['raw_sha256'] = file_digest(root/'result.raw')
        except Exception as error: row.update(status='FAIL', error=repr(error))
        report['cases'].append(row); write(output/'report.json', report)
    report['status'] = 'PASS' if all(r['status'] == 'PASS' for r in report['cases']) else 'FAIL'
    write(output/'report.json', report); return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--ngspice', required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); result = verify(a.ngspice, a.output); print(json.dumps(result, indent=2)); raise SystemExit(result['status'] != 'PASS')
