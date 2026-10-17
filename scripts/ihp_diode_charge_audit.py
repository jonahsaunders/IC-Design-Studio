"""Check a captured intrinsic diode's charge against its tangent capacitance.

A pass bounds the accumulated charge error at every sampled bias in this
interval. It does not validate the physical model, temperature range, simulator
modifications or a complete circuit. Bind model and engine hashes separately.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

RELATIVE_LIMIT = 1e-4


def audit(curve, log, first_bias, last_bias):
    curve, log = Path(curve), Path(log)
    if not all(map(math.isfinite, (first_bias, last_bias))) or first_bias >= last_bias:
        raise ValueError('An explicit increasing finite bias interval is required.')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    hashes = [sha(p) for p in (curve, log)]
    if re.search(r'aborted|timestep too small|no such vector|failed', log.read_text(errors='replace'), re.I):
        raise ValueError('The native analysis did not complete successfully.')
    with curve.open() as stream:
        if stream.readline().lower().split() != ['v-sweep', 'i(vbias)', '@dtest[charge]', '@dtest[cd]', '@dtest[vd]']:
            raise ValueError('Save the actual diode current, charge, capacitance and voltage vectors.')
        rows = [list(map(float, line.split())) for line in stream]
    if len(rows) < 3 or any(len(row) != 5 or not all(map(math.isfinite, row)) or row[3] <= 0 for row in rows):
        raise ValueError('Finite complete rows with positive tangent capacitance are required.')
    if (not math.isclose(rows[0][0], first_bias, rel_tol=0., abs_tol=1e-12) or
            not math.isclose(rows[-1][0], last_bias, rel_tol=0., abs_tol=1e-12)):
        raise ValueError('The captured curve does not cover the declared interval.')
    integrals = []; largest_step = 0.
    for left, right in zip(rows, rows[1:]):
        if right[0] <= left[0] or right[4] >= left[4]:
            raise ValueError('Bias and intrinsic reverse voltage must advance at every sample.')
        if right[2] >= left[2]:
            raise ValueError('Stored charge must follow the positive tangent capacitance.')
        integrals.append((right[4]-left[4])*(right[3]+left[3])/2)
        largest_step = max(largest_step, abs(right[2]-left[2]))
    charge = rows[-1][2]-rows[0][2]; integral = math.fsum(integrals)
    scale = max(abs(charge), abs(integral))
    relative = abs(charge-integral)/scale
    accumulated = 0.; maximum_cumulative = 0.
    for row, increment in zip(rows[1:], integrals):
        accumulated += increment
        maximum_cumulative = max(maximum_cumulative, abs((row[2]-rows[0][2])-accumulated)/scale)
    if [sha(p) for p in (curve, log)] != hashes:
        raise ValueError('A captured input changed during the audit.')
    return dict(schema=1, status='charge-consistency-pass' if max(relative, maximum_cumulative) <= RELATIVE_LIMIT else 'charge-consistency-failed',
                qualified=False, samples=len(rows), first_bias_v=first_bias, last_bias_v=last_bias,
                charge_change_c=charge, integrated_capacitance_charge_c=integral,
                relative_error=relative, maximum_cumulative_relative_error=maximum_cumulative,
                relative_limit=RELATIVE_LIMIT, largest_charge_step_c=largest_step,
                curve_sha256=hashes[0], engine_log_sha256=hashes[1],
                scope='Cumulative sampled intrinsic charge/capacitance consistency only. External model and engine bindings, physical calibration, circuit behavior and qualification require separate evidence.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('curve', 'log', 'output'): parser.add_argument('--'+name, required=True, type=Path)
    for name in ('first-bias', 'last-bias'): parser.add_argument('--'+name, required=True, type=float)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError('Use a new report to preserve earlier evidence.')
    result = audit(args.curve, args.log, args.first_bias, args.last_bias)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    return 0 if result['status'] == 'charge-consistency-pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
