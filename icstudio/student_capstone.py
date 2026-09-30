"""Independent design requirements for the student sensor-acquisition capstone."""
import math

from .model import clone, device, scalar, validate
from .sar_example import sar_project

INPUTS = [.2, .4, .6, .8, 1., 1.2, 1.4, 1.6]
CASES = ('nominal', 'low-rail', 'high-rail', 'hold-step')


def stimuli(values, hold_step=False):
    points = [[0., values[0]]]
    for i, value in enumerate(values):
        if i:
            points.extend([[i*8e-6, points[-1][1]], [i*8e-6+1e-9, value]])
        if hold_step:
            points.extend([[i*8e-6+3.5e-6, value], [i*8e-6+3.501e-6, .05]])
    return points


def project():
    from .getting_started import resource_root
    p = sar_project(); p['name'] = 'Sensor acquisition · SAR, averaging and alarm'
    c = p['mixed_signal']; c.pop('verification')
    analog = next(cell for cell in p['cells'] if cell['id'] == c['analog_cell'])
    next(d for d in analog['devices'] if d['name'] == 'Ssample')['nets']['in'] = 'filtered'
    analog['devices'] += [device('R', 'Rfilter', 60, 650, value='1k', nets={'p':'vin','n':'filtered'}),
                          device('C', 'Cfilter', 300, 650, value='100p', nets={'p':'filtered','n':'0'})]
    digital = next(cell for cell in p['cells'] if cell['id'] == c['digital_cell'])['digital']
    digital['top'] = 'sensor_controller'
    digital['files'].append(dict(path='sensor_controller.sv', role='rtl',
        text=(resource_root()/'examples/student-hub/sensor_controller.sv').read_text(encoding='utf-8')))
    c.update(cycles=67, timeout=240)
    c['inputs'][0]['values'] = [int(k < 2) for k in range(67)]
    c['inputs'][1]['values'] = [int(k in range(2, 59, 8)) for k in range(67)]
    c['outputs'] += [dict(port='average', width=4), dict(port='average_valid', width=1),
                     dict(port='alarm', width=1), dict(port='sample_count', width=4)]
    c['probes'].append('filtered'); c['stimuli']['vin'] = stimuli(INPUTS)
    return validate(p)


def case_project(base, name):
    if name not in CASES: raise ValueError('Unknown capstone case.')
    p = clone(base)
    values = [-.1]*8 if name == 'low-rail' else [1.9]*8 if name == 'high-rail' else INPUTS
    p['mixed_signal']['stimuli']['vin'] = stimuli(values, name == 'hold-step')
    return p


def report(result, case='nominal'):
    """Requirements are independent of the edited RTL, DAC and bridge drivers."""
    if case not in CASES: raise ValueError('Unknown capstone case.')
    samples = result.get('mixed_signal', {}).get('samples', [])
    values = [-.1]*8 if case == 'low-rail' else [1.9]*8 if case == 'high-rail' else INPUTS
    expected = [max(0, min(15, math.floor(v*16/1.8))) for v in values]
    averages = [(sum(expected[i:i+4])+2)//4 for i in (0, 4)]
    done = [s for s in samples if s['outputs'].get('done') == 1]
    valid = [s for s in samples if s['outputs'].get('average_valid') == 1]
    checks = []
    def add(name, actual, wanted):
        checks.append(dict(name=name, passed=actual == wanted, actual=actual, expected=wanted))
    add('Eight conversion codes', [s['outputs'].get('code') for s in done], expected)
    add('Conversion cadence', [s['edge'] for s in done], list(range(7, 64, 8)))
    add('Two rounded block averages', [s['outputs'].get('average') for s in valid], averages)
    add('Average valid cadence', [s['edge'] for s in valid], [32, 64])
    add('Alarm at average >= 10', [s['outputs'].get('alarm') for s in valid], [int(a >= 10) for a in averages])
    add('Every conversion counted once', samples[-1]['outputs'].get('sample_count') if samples else None, 8)
    add('Thirty-two comparator decisions', sum(s.get('sampled', {}).get('cmp', False) for s in samples), 32)
    # Check acquired analog voltage on the first comparison of every conversion.
    acquired = [s.get('analog', {}).get('held') for s in samples if s['edge'] in range(4, 61, 8)]
    checks.append(dict(name='Acquisition error below 2 mV', passed=len(acquired)==8 and
        all(v is not None and abs(v-target)<.002 for v, target in zip(acquired, values)), actual=acquired, expected=values))
    return dict(status='PASS' if all(c['passed'] for c in checks) else 'FAIL', case=case,
                codes=[s['outputs'].get('code') for s in done], averages=[s['outputs'].get('average') for s in valid], checks=checks)
