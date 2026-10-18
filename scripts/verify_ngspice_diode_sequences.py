"""Check level-3 geometry across analyses against independent diode equations.

No reset, model rewrite or version-based exception is permitted. Explicit
AREA/PJ input units follow the existing measured engine behavior contract.
"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.engines import parse_raw
from icstudio.model import file_digest
from icstudio.ngspice_compat import behavior
from icstudio.spice_program import runtime_environment

# (area, perimeter, multiplicity), in the model's declared geometry units.
INITIAL = {1: (4, 8, 1), 3: (4, 8, 3)}
AC_CASES = {
    'ac1': INITIAL, 'ac2': INITIAL, 'ac3': INITIAL,
    'area': {1: (8, 8, 1), 3: (4, 8, 3)},
    'perimeter': {1: (8, 8, 1), 3: (4, 12, 3)},
    'multiplicity': {1: (8, 8, 1), 3: (4, 12, 2)},
}
# The engine model uses these pre-2019 SI constants (const.h), not the
# current exact SI values. That difference reaches 2.6 ppm at 0.2 V.
# https://github.com/imr/ngspice/blob/ngspice-46/src/include/ngspice/const.h
THERMAL_VOLTAGE = 1.38064852e-23 * 300.15 / 1.6021766208e-19
RELATIVE_TOLERANCE = 1e-6
ABSOLUTE_TOLERANCE = 1e-18


def deck(mode):
    if mode not in ('scales-explicit-area', 'unscaled-explicit-area'):
        raise ValueError('Unrecognized diode geometry convention.')
    area_scale, perimeter_scale = ((1e12, 1e6) if mode == 'scales-explicit-area' else (1, 1))
    lines = ['* Analytical repeated level-3 diode geometry regression',
             '.option scale=1u gmin=1e-30', '.temp 27',
             '.model check D level=3 is=1e-15 jsw=3e-15 n=1 ns=1 '
             'cjo=2p cjp=.5p vj=.7 php=.8 m=.5 mjsw=.33 rs=0']
    for number, (area, perimeter, multiplicity) in INITIAL.items():
        lines += [f'V{number} n{number} 0 0 ac 1',
                  f'D{number} n{number} 0 check area={area*area_scale:.17g} '
                  f'pj={perimeter*perimeter_scale:.17g} m={multiplicity}']
    lines += ['.control', 'set filetype=ascii', 'set numdgt=16', 'op', 'write op.raw all']
    for name in AC_CASES:
        if name == 'ac2':
            lines += ['dc V1 0 .2 .05', 'write dc.raw all']
        elif name == 'area':
            lines += [f'alter D1 area={8*area_scale:.17g}']
        elif name == 'perimeter':
            lines += [f'alter D3 pj={12*perimeter_scale:.17g}']
        elif name == 'multiplicity':
            lines += ['alter D3 m=2']
        lines += ['ac dec 5 1k 1meg', f'write {name}.raw all']
    return '\n'.join([*lines, 'quit', '.endc', '.end', ''])


def normalized_error(actual, expected):
    actual = complex(actual)
    if not math.isfinite(actual.real) or not math.isfinite(actual.imag):
        raise ValueError('Nonfinite diode result.')
    return abs(actual - expected) / (ABSOLUTE_TOLERANCE + RELATIVE_TOLERANCE * abs(expected))


def validate(variables, rows, complex_data, name):
    ac = name in AC_CASES
    if not ac and name not in ('op', 'dc'):
        raise ValueError('Unrecognized analysis.')
    count = 16 if ac else (5 if name == 'dc' else 1)
    if complex_data != ac or len(rows) != count:
        raise ValueError('Missing or malformed diode analysis: ' + name)
    indices = {v.casefold(): i for i, v in enumerate(variables)}
    if len(indices) != len(variables) or any(v not in indices for v in ('v(n1)', 'v(n3)', 'i(v1)', 'i(v3)')):
        raise ValueError('Missing or duplicate diode vectors.')
    if ac and variables[0].casefold() != 'frequency':
        raise ValueError('Missing frequency axis.')
    if name == 'dc' and variables[0].casefold() != 'v(v-sweep)':
        raise ValueError('Missing voltage sweep axis.')
    errors = []
    for index, row in enumerate(rows):
        if len(row) != len(variables):
            raise ValueError('Incomplete diode sample.')
        if any(not math.isfinite(complex(v).real) or not math.isfinite(complex(v).imag) for v in row):
            raise ValueError('Nonfinite diode sample.')
        frequency = 1000 * 10**(index / 5)
        voltage = .05 * index if name == 'dc' else 0
        if ac or name == 'dc':
            axis = complex(row[0])
            if axis.imag != 0 or not math.isclose(axis.real, frequency if ac else voltage, rel_tol=1e-9, abs_tol=1e-12):
                raise ValueError('Changed diode analysis domain.')
        for number, (area, perimeter, multiplicity) in (AC_CASES[name] if ac else INITIAL).items():
            bias = voltage if number == 1 else 0
            terminal = complex(row[indices[f'v(n{number})']])
            if abs(terminal - (1 if ac else bias)) > 1e-12:
                raise ValueError('Changed diode terminal stimulus.')
            saturation = (area * 1e-15 + perimeter * 3e-15) * multiplicity
            capacitance = (area * 2e-12 + perimeter * .5e-12) * multiplicity
            expected = (-saturation / THERMAL_VOLTAGE - 2j*math.pi*frequency*capacitance
                        if ac else -saturation * math.expm1(bias / THERMAL_VOLTAGE))
            errors.append(normalized_error(row[indices[f'i(v{number})']], expected))
    worst = max(errors)
    if worst > 1:
        raise ValueError(f'Analytical diode mismatch in {name}: normalized error {worst:.9g}')
    return dict(status='PASS', samples=count, currents=2, maximum_normalized_error=worst)


def verify(executable, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    executable = str(Path(executable).resolve())
    report = dict(status='FAIL', engine_sha256=file_digest(executable), checks=[],
                  relative_tolerance=RELATIVE_TOLERANCE, absolute_tolerance_a=ABSOLUTE_TOLERANCE,
                  scope='Analytical level-3 OP/DC/AC, repeated analyses and explicit AREA/PJ/M alteration; '
                        'no reset or PDK equations. This does not establish full runtime or PDK qualification.')
    try:
        report['behavior'] = behavior(executable, output)
        (output/'input.cir').write_bytes(deck(report['behavior']['mode']).encode())
        cmd = [executable, '-n', '-D', 'ngbehavior=hsa', '-b', 'input.cir']
        run = subprocess.run(cmd, cwd=output, capture_output=True, timeout=60,
                             env={**(runtime_environment(executable) or os.environ), 'OMP_THREAD_LIMIT': '1'})
        (output/'engine.log').write_bytes(run.stdout + run.stderr)
        report.update(command=cmd, exit=run.returncode)
        if run.returncode:
            raise ValueError('Simulator failed; inspect retained engine.log.')
        for name in ('op', 'dc', *AC_CASES):
            row = dict(name=name)
            try:
                raw = output/(name+'.raw')
                row.update(validate(*parse_raw(raw), name), raw_sha256=file_digest(raw))
            except Exception as error:
                row.update(status='FAIL', error=repr(error))
            report['checks'].append(row)
        report['status'] = 'PASS' if all(r['status'] == 'PASS' for r in report['checks']) else 'FAIL'
    except Exception as error:
        report['error'] = repr(error)
    (output/'report.json').write_bytes((json.dumps(report, indent=2)+'\n').encode())
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.ngspice, args.output)
    print(json.dumps(result, indent=2))
    raise SystemExit(result['status'] != 'PASS')
