"""Editable series-RLC experiments and measurements from captured AC runs."""

import bisect
import cmath
import math

from .model import device, example, scalar, validate

OUTPUTS = {
    'lp': 'Low-pass · across C',
    'hp': 'High-pass · across L',
    'bp': 'Band-pass · across R',
    'bs': 'Notch · across series LC',
}
ORDERS = {'lp': 'RLC', 'hp': 'RCL', 'bp': 'LCR', 'bs': 'RLC'}
NOMINAL_FREQUENCY = 1 / (2 * math.pi * math.sqrt(.01 * 100e-9))


def project():
    p = example('empty')
    p['name'] = 'Student · LC filters and Bode plots'
    cell = p['cells'][0]
    cell['name'] = 'series_rlc_filters'
    source = device('V', 'VIN', 80, 450, value='0', nets={'p': 'vin', 'n': '0'})
    source['source']['ac'] = '1'
    cell['devices'] = [source]
    for row, (output, order) in enumerate(ORDERS.items()):
        cut = 1 if output == 'bs' else 2
        nodes = ['vin', f'{output}_a', f'{output}_b', '0']
        nodes[cut] = output
        for i, kind in enumerate(order):
            cell['devices'].append(device(
                kind, kind + output.upper(), 360 + i * 250, 120 + row * 220,
                rotation=270, value={'R': '220', 'L': '10m', 'C': '100n'}[kind],
                nets={'p': nodes[i], 'n': nodes[i + 1]},
            ))
    p['analysis'].update(type='ac', start=NOMINAL_FREQUENCY / 100,
                         end=100 * NOMINAL_FREQUENCY, points=401)
    return validate(p)


def parameters(project, output):
    cell = next(cell for cell in project['cells'] if cell['id'] == project['top'])
    devices = {d['name']: d for d in cell['devices']}
    try:
        r, l, c = (scalar(devices[kind + output.upper()]['value']) for kind in 'RLC')
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Restore the marked resistor, inductor and capacitor for this branch.') from exc
    if min(r, l, c) <= 0:
        raise ValueError('Each test branch needs positive R, L and C.')
    return 1 / (2 * math.pi * math.sqrt(l * c)), math.sqrt(l / c) / r


def series(result, output):
    """Reconstruct H = Vout/Vin using the solver's magnitude and phase."""
    if result['settings'].get('type') != 'ac' or len(result.get('x', [])) < 2:
        raise ValueError('Run an AC sweep before opening the Bode plot.')
    from .wavecalc import evaluate

    try:
        if output not in OUTPUTS or not {'vin', output} <= result.get('phase', {}).keys():
            raise ValueError('Missing phase data.')
        response = evaluate(f'V("{output}") / V("vin")', result).values
    except ValueError as exc:
        raise ValueError('Keep VIN active and capture magnitude and phase on all filter outputs.') from exc
    if len(response) != len(result['x']):
        raise ValueError('The AC waveform is incomplete. Run the sweep again.')
    return response


def sample(xs, ys, frequency):
    if not xs[0] <= frequency <= xs[-1]:
        raise ValueError('Extend the AC sweep to cover the lesson measurement frequencies.')
    i = bisect.bisect_left(xs, frequency)
    if not i or xs[i] == frequency:
        return ys[i]
    weight = math.log(frequency / xs[i - 1]) / math.log(xs[i] / xs[i - 1])
    return (1 - weight) * ys[i - 1] + weight * ys[i]


def gain_db(value, floor=1e-15):
    return 20 * math.log10(max(abs(value), floor))


def phase_deg(value):
    if abs(value) >= 1e-5:
        return math.degrees(cmath.phase(value))
    return None


def asymptote(output, normalized_frequency, q):
    x = math.log10(normalized_frequency)
    return {'lp': -40 * max(x, 0), 'hp': 40 * min(x, 0),
            'bp': -20 * abs(x) - 20 * math.log10(q), 'bs': 0}[output]


def theory(output, normalized_frequency, q):
    z = 1j * normalized_frequency
    return {'lp': 1, 'hp': z*z, 'bp': z/q, 'bs': 1 + z*z}[output] / (1 + z/q + z*z)


def check(project, result, step):
    xs = result['x']
    if step == 'slopes':
        metrics = {}
        expected = {'lp': (0, -40), 'hp': (40, 0), 'bp': (20, -20), 'bs': (0, 0)}
        for output, slopes in expected.items():
            response = series(result, output)
            center, q = parameters(project, output)
            if not math.isclose(center, NOMINAL_FREQUENCY, rel_tol=.002) or not 1.35 <= q <= 1.50:
                raise ValueError('Use the starting 10 mH, 100 nF and 220 Ω branches for the first comparison.')
            # Use one full decade on each far tail, avoiding rounding at end points.
            reference = NOMINAL_FREQUENCY
            f = (reference / 80, reference / 8, reference * 8, reference * 80)
            low1, low2, high1, high2 = (gain_db(sample(xs, response, point)) for point in f)
            measured = (low2 - low1, high2 - high1)
            at_center = response[min(range(len(xs)), key=lambda i: abs(xs[i] - center))] if output == 'bs' else sample(xs, response, center)
            if any(abs(a - b) > 1 for a, b in zip(measured, slopes)):
                raise ValueError(f'{OUTPUTS[output]} has slopes {measured[0]:.1f} and {measured[1]:.1f} dB/decade. Check its output tap.')
            if output == 'bs':
                if gain_db(at_center) > -28:
                    raise ValueError('Resolve the notch near f₀ with the saved 401-point sweep and keep the output across series LC.')
            elif abs(at_center - theory(output, 1, q)) > .06:
                raise ValueError(f'{OUTPUTS[output]} has the wrong gain or phase at f₀. Check its wiring.')
            metrics[output] = dict(low_db_per_decade=measured[0], high_db_per_decade=measured[1],
                                   center_db=gain_db(at_center), phase_deg=phase_deg(at_center))
        return metrics

    response = series(result, 'lp')
    center, q = parameters(project, 'lp')
    if step == 'damping':
        if not math.isclose(center, NOMINAL_FREQUENCY, rel_tol=.01) or not .62 <= q <= .71:
            raise ValueError('Keep LLP and CLP fixed. Raise RLP to approximately 470 Ω and rerun.')
    elif step == 'tune':
        if not 9750 <= center <= 10250:
            raise ValueError('Retune CLP for a natural frequency of 10 kHz, within 2.5%.')
    else:
        raise ValueError('Unknown filter checkpoint.')
    at_center = sample(xs, response, center)
    if abs(at_center - theory('lp', 1, q)) > .06:
        raise ValueError('The simulated low-pass gain and phase do not match the selected RLC values.')
    return dict(f0_Hz=center, q=q, center_db=gain_db(at_center), phase_deg=phase_deg(at_center))
