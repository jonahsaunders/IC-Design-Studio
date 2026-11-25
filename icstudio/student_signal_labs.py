"""Capture and grade repeatable signal-chain lesson simulations."""

import bisect
from collections import Counter
from functools import lru_cache
import json
import math
from pathlib import Path
import statistics

from . import student_signal_circuits as circuits, student_circuit_challenges as challenges
from .model import atomic_write, clone, design_digest, device, file_digest

STARTER = 'signal-study-'
TEMPERATURE_ANCHORS = (0, 80)
TEMPERATURE_TRIALS = (5, 20, 35, 55, 75)
SUPPLY_TRIALS = ('1.6', '1.8', '2.0')


def course():
    from .getting_started import resource_root
    path = resource_root() / 'examples/student-hub/signal-course.json'
    return json.loads(path.read_text(encoding='utf-8'))


def lessons(source):
    result = []
    for unit in source:
        steps = [dict(id='predict', kind='quiz', title='Predict the result', **unit['quiz'])]
        steps.extend(dict(**task, kind='check', rule={'type': 'signal_study'}) for task in unit['tasks'])
        steps.append(dict(id='reflect', kind='reflection', title='Record your reasoning',
                          instructions=unit['reflection']))
        starter = STARTER + unit['lab']
        lesson = dict(id=unit['id'], title=unit['title'], summary=unit['summary'], skills=unit['skills'],
                      minutes=unit['minutes'], path=unit['path'], topic=unit['topic'], requires=unit['requires'],
                      signal_lab=unit['lab'], starter=starter, workspace=starter, steps=steps,
                      doc='STUDENT_SIGNAL_LABS.md')
        if unit.get('goal'):
            lesson['goal'] = unit['goal']
        result.append(lesson)
    return result


def focus(p, lab, step):
    if p.get('student_signal', {}).get('lab') != lab or p['student_signal'].get('version') != 1:
        raise ValueError('Open or resume this experiment in Student Hub.')
    return circuits.cell(p, 'source_follower')['id'] if lab == 'load' and step == 'baseline' else p['top']


def calibration(p):
    values = p['student_signal'].get('calibration', {})
    gain, offset = (values.get(key) for key in ('gain_mC_per_count', 'offset_mC'))
    if type(gain) is not int or type(offset) is not int or not 1 <= gain <= 4000 or not -5_000_000 <= offset <= 5_000_000:
        raise ValueError('Use integer gain from 1 to 4000 m°C/count and a signed offset within ±5,000,000 m°C.')
    return gain, offset


def set_calibration(p, gain, offset):
    focus(p, 'temperature', 'validate')
    p['student_signal']['calibration'] = dict(gain_mC_per_count=gain, offset_mC=offset)
    calibration(p)


def run_name(lab, step):
    if step in ('predict', 'reflect'):
        return ''
    return {'rejection': 'Run three AC excitations', 'adc-ramp': 'Capture and measure ramp',
            'temperature': 'Validate held-out conditions' if step == 'validate' else 'Measure reference points',
            'pga': 'Measure PGA response', 'pll': 'Run lock test'}.get(lab, 'Run experiment')


def _case(p, name, settings, update=None, cid=None):
    q = clone(p)
    c = next(c for c in q['cells'] if c['id'] == (cid or q['top']))
    if update:
        update(c)
    return name, q, c['id'], settings


def _dc(c, label, voltage, ac='0'):
    part = circuits.named(c, label)
    part.update(value=str(voltage))
    part['source'].update(type='dc', ac=ac)


def _set_value(c, label, value):
    circuits.named(c, label)['value'] = str(value)


def _rejection_cases(p, analysis):
    def select(c, values):
        for label, dc, ac in zip(('VP', 'VN', 'VDD'), ('.85', '.85', '1.8'), values):
            _dc(c, label, dc, ac)
    inputs = {'differential': ('.5', '-.5', '0'), 'common-mode': ('1', '1', '0'), 'supply': ('0', '0', '1')}
    return [_case(p, name, analysis, lambda c, v=values: select(c, v)) for name, values in inputs.items()]


def _pga_cases(p, analysis):
    def select(c, code):
        _dc(c, 'VIN', '.1', '1')
        # Hold each selector at its DC switch resistance for the small-signal bench.
        for key in ('wires', 'labels', 'junctions'):
            c.pop(key, None)
        for i in range(1, 4):
            _dc(c, f'VSEL{i}', '1.8' if i == code else '0')
            switch = circuits.named(c, f'SSEL{i}')
            c['devices'][c['devices'].index(switch)] = device('R', f'RSW{i}', switch['x'], switch['y'],
                id=switch['id'], value='1' if i == code else '10g', nets={'p': switch['nets']['a'], 'n': switch['nets']['b']})
    ac = dict(type='ac', start='100', end='30meg', points=26)
    return [_case(p, f'gain-code-{i}', ac, lambda c, k=i: select(c, k)) for i in range(1, 4)] + [_case(p, 'gain-switching', analysis)]


def _temp_conditions(step):
    anchors = [('1.8', t) for t in TEMPERATURE_ANCHORS]
    if step != 'validate':
        return anchors
    return anchors + [(supply, t) for supply in SUPPLY_TRIALS for t in TEMPERATURE_TRIALS]


def _temp_key(supply, temp):
    return f'{supply.replace(".", "p")}v-{temp}c'


def cases(p, lab, step):
    focus(p, lab, step)
    analysis = circuits.ANALYSIS[lab]
    if lab in challenges.ANALYSIS:
        return challenges.cases(p,lab,analysis,_case)
    if lab == 'rejection':
        return _rejection_cases(p, analysis)
    if lab == 'load':
        cells = ('source_follower', 'feedback_buffer') if step == 'repair' else ('source_follower',)
        return [_case(p, f'{name.replace("_", "-")}-{size}', analysis,
                      lambda c, v=size: _set_value(c, 'CL', v), cid=circuits.cell(p, name)['id'])
                for name in cells for size in ('100p', '500p')]
    if lab == 'chopper':
        def bypass(c):
            for label in ('VCHOP', 'VDEMOD'):
                _dc(c, label, '1')
        return [_case(p, 'bypassed', analysis, bypass), _case(p, 'chopped', analysis)]
    if lab == 'relaxation':
        conditions = [('nominal', '1.8', 27)]
        if step == 'corners':
            conditions.extend([('cold-low-rail', '1.62', 0), ('hot-high-rail', '1.98', 70)])
        return [_case(p, name, dict(analysis, temperature=temp), lambda c, v=supply: _dc(c, 'VDD', v))
                for name, supply, temp in conditions]
    if lab == 'pll':
        steps = [('step-up', '100')]
        if step == 'repair':
            steps.append(('step-down', '-100'))
        return [_case(p, name, analysis, lambda c, target=target: _dc(c, 'VSTEP', target))
                for name, target in steps]
    if lab == 'pga':
        return _pga_cases(p, analysis)
    if lab == 'temperature':
        return [_case(p, _temp_key(supply, t), dict(type='op', temperature=t), lambda c, v=supply: _dc(c, 'VDD', v))
                for supply, t in _temp_conditions(step)]
    return [_case(p, 'transient' if lab == 'linearity' else 'adc-ramp', analysis)]


def prepare(p, lesson, step, tools):
    from .run_environment import stamp
    lab = lesson['signal_lab']
    cid = focus(p, lab, step)
    if not run_name(lab, step):
        raise ValueError('Use Check this step for the current task.')
    _contract(p, lab)
    engine = 'ngspice' if lab in circuits.NATIVE else 'builtin'
    job = dict(project=clone(p), cell=cid, engine=engine,
               settings=dict(type='student_signal_lab', lab=lab, step=step),
               student_lesson=lesson['id'], student_signal_step=step)
    if engine == 'ngspice':
        from .spice_program import find_ngspice
        exe = find_ngspice(tools.get('ngspice', ''))
        if not exe or not Path(exe).is_file():
            raise ValueError('Select ngspice under Student Hub → Engine setup, then run this experiment again.')
        job['executable'] = str(Path(exe).resolve())
    job['environment'] = stamp(job)
    return job


def _series(wave, node, field='traces'):
    axis = wave.get('x', [])
    traces = wave.get(field, {})
    key = next((key for key in traces if key.casefold() == node.casefold()), None)
    values = traces.get(key, [])
    if (not axis or len(axis) != len(values) or not all(math.isfinite(v) for v in (*axis, *values))
            or any(b <= a for a, b in zip(axis, axis[1:]))):
        raise ValueError(f'Missing or invalid data for {node}. Inspect the saved simulation.')
    return axis, values


def _at(axis, values, point):
    if not axis[0] <= point <= axis[-1]:
        raise ValueError('The saved simulation does not cover the measurement window.')
    i = bisect.bisect_left(axis, point)
    if i == 0 or axis[i] == point:
        return values[i]
    return values[i-1] + (values[i]-values[i-1]) * (point-axis[i-1])/(axis[i]-axis[i-1])


def _samples(wave, node, begin, stop, count=256, field='traces'):
    axis, values = _series(wave, node, field)
    return [_at(axis, values, begin + (stop-begin)*(i+.5)/count) for i in range(count)]


def _sample(wave, node, x):
    return _at(*_series(wave, node), x)


def _range(wave, node, first, last):
    xs, ys = _series(wave, node)
    left, right = bisect.bisect_right(xs, first), bisect.bisect_left(xs, last)
    return [first, *xs[left:right], last], [_at(xs, ys, first), *ys[left:right], _at(xs, ys, last)]


def _settling(wave, node, edge, end, goal, tolerance):
    xs, ys = _range(wave, node, edge, end)
    outside = [i for i, v in enumerate(ys) if abs(v-goal) > tolerance]
    if not outside:
        return 0.0
    i = outside[-1]
    if i+1 == len(xs):
        return None
    return xs[i+1]-edge


def _harmonic(values, index):
    theta = 2*math.pi*index/len(values)
    x = sum(v*math.cos(theta*i) for i, v in enumerate(values))
    y = sum(v*math.sin(theta*i) for i, v in enumerate(values))
    return math.hypot(x, y)*2/len(values)


def _linearity(p, waves, step):
    wave = waves['transient']
    input_tone = _samples(wave, 'gate', .0003, .0005)
    output = _samples(wave, 'out', .0003, .0005)
    a1 = _harmonic(output, 2)
    if min(a1, _harmonic(input_tone, 2)) <= 1e-8:
        raise ValueError('Keep the fixed sine stimulus and measurable output fundamental.')
    return {'Drain bias (µA)': abs(wave['operating_currents']['RD'])*1e6,
            'Fundamental gain (V/V)': a1/_harmonic(input_tone, 2),
            'THD, harmonics 2–5 (%)': 100*math.sqrt(sum(_harmonic(output, 2*h)**2 for h in range(2, 6)))/a1}


def _rejection(p, waves, step):
    ad, acm, supply = (_sample(waves[case], 'out', 10000) for case in ('differential', 'common-mode', 'supply'))
    if ad <= 1e-7:
        raise ValueError('Differential gain is too low to define a rejection ratio.')
    return {'Differential gain (V/V)': ad, 'Common-mode gain (V/V)': acm, 'Supply-to-output gain (V/V)': supply,
            'CMRR at 10 kHz (dB)': 20*math.log10(ad/max(acm, 1e-12)),
            'Input-referred PSRR+ at 10 kHz (dB)': 20*math.log10(ad/max(supply, 1e-12))}


def _load(p, waves, step):
    values = {}
    for name, wave in waves.items():
        mean = statistics.mean(_samples(wave, 'out', 22e-6, 27e-6))
        time = _settling(wave, 'out', 5e-6, 28e-6, .65, .01)
        response = _settling(wave, 'out', 5e-6, 28e-6, mean, .01)
        peak = max(_range(wave, 'out', 5e-6, 28e-6)[1])
        current = statistics.mean(_samples(wave, 'VDD', 22e-6, 27e-6, field='currents'))
        values[name] = {'DC error (mV)': abs(.65-mean)*1000, 'Settling to ±10 mV (µs)': time*1e6 if time is not None else None,
                        'Settling about own final level (µs)': response*1e6 if response is not None else None,
                        'Positive overshoot (mV)': max(0, peak-.65)*1000, 'Mean drain supply (µA)': abs(current)*1e6}
    return values


def _adc(p, waves, step):
    wave = waves['adc-ramp']
    n = 4096
    input_ = _samples(wave, 'vin', 0, .001, n)
    if abs(input_[0]) > .002 or abs(input_[-1] - 1) > .002 or any(b <= a for a, b in zip(input_, input_[1:])):
        raise ValueError('Keep the complete monotonic 0–1 V input ramp.')
    comparators = [_samples(wave, 'cmp'+str(i), 0, .001, n) for i in range(1, 8)]
    codes = [sum(value >= .5 for value in sample) for sample in zip(*comparators)]
    if (min(codes) != 0 or max(codes) != 7 or any(b < a for a, b in zip(codes, codes[1:]))):
        raise ValueError('The decoded ADC must span codes 0–7 in monotonic order.')
    histogram = Counter(codes)
    count = [histogram.get(i, 0) for i in range(8)]
    ideal = n/8
    dnl = [k/ideal-1 for k in count]
    transitions = [sum(count[:i])/n for i in range(1, 8)]
    inl = [8*v-i for i,v in enumerate(transitions, 1)]
    return {'Peak |DNL| (LSB)': max(map(abs, dnl)), 'Peak |INL| (LSB)': max(map(abs, inl)),
            'Missing codes': [i for i, n in enumerate(count) if n == 0],
            'Near-missing codes': [i for i, n in enumerate(count) if 0 < n < .01*ideal], 'Code counts': count,
            'Transitions (V)': transitions, 'DNL by code (LSB)': dnl, 'INL by transition (LSB)': inl}


def _chopper(p, waves, step):
    reading = {}
    for case, wave in waves.items():
        low = statistics.mean(_samples(wave, 'out', .0008, .0013))
        high_samples = _samples(wave, 'out', .0032, .0038, 480)
        high = statistics.mean(high_samples)
        gain = (high-low)/.02
        averaged = [statistics.mean(_samples(wave, 'out', .0015+i*50e-6, .0015+(i+1)*50e-6, 25)) for i in range(46)]
        last_error = max([i for i,v in enumerate(averaged) if abs(v-.6) > .015], default=-1)
        reading[case] = {'Recovered gain (V/V)': gain, 'Output offset (mV)': (high-.03*gain)*1000,
                         'Ripple p-p (mV)': (max(high_samples)-min(high_samples))*1000,
                         'Average settling (µs)': None if last_error == len(averaged)-1 else (last_error+1)*50}
    return reading


def _crossings(xs, ys, level):
    up, down = [], []
    for a, b, va, vb in zip(xs, xs[1:], ys, ys[1:]):
        if va < level <= vb:
            up.append(a+(level-va)*(b-a)/(vb-va))
        elif va >= level > vb:
            down.append(a+(level-va)*(b-a)/(vb-va))
    return up, down


def _oscillator(p, waves, step):
    values = {}
    for name, wave in waves.items():
        vdd = _sample(wave, 'vdd', 0)
        all_x, all_y = _series(wave, 'out')
        up, down = _crossings(all_x, all_y, vdd/2)
        ups = [t for t in up if t >= .0007]
        periods = [b-a for a,b in zip(ups, ups[1:])]
        if len(periods) < 3:
            raise ValueError('Capture at least four natural rising edges after startup.')
        width = [next((t-a for t in down if a<t<b), None) for a,b in zip(ups, ups[1:])]
        if any(v is None for v in width):
            raise ValueError('Each oscillator cycle needs a falling edge.')
        _, cap = _range(wave, 'cap', .0007, .004)
        settled = _range(wave, 'out', .0007, .004)[1]
        if max(settled)-min(settled) < .8*vdd or not .22*vdd < min(cap) < .45*vdd or not .55*vdd < max(cap) < .82*vdd:
            raise ValueError('The oscillator needs rail-to-rail swing and the expected RC threshold crossings.')
        values[name] = {'Frequency (Hz)': 1/statistics.median(periods),
                        'Duty cycle (%)': 100*sum(width)/sum(periods),
                        'First rising edge (µs)': up[0]*1e6,
                        'Capacitor low (V)': min(cap), 'Capacitor high (V)': max(cap)}
    return values


def _pga(p, waves, step):
    result = {}
    transient = waves['gain-switching']
    for i in range(1, 4):
        wave = waves[f'gain-code-{i}']
        xs, ys = _series(wave, 'out')
        gain = ys[0]
        between = [(a, b, u, v) for a,b,u,v in zip(xs, xs[1:], ys, ys[1:]) if u >= gain/math.sqrt(2) > v]
        bandwidth = None
        if between:
            a,b,u,v = between[0]
            bandwidth = math.exp(math.log(a) + (gain/math.sqrt(2)-u)/(v-u)*math.log(b/a))
        value = statistics.mean(_samples(transient, 'out', (i-1)*.001+.00035, (i-1)*.001+.0008))
        time = _settling(transient, 'out', (i-1)*.001, min(i*.001-.00002, .00288), value, .015) if i > 1 else 0
        result[f'gain-code-{i}'] = {'Small-signal gain (V/V)': gain, 'Bandwidth (Hz)': bandwidth,
                                    'DC output (V)': value, 'Switching settling (µs)': time*1e6 if time is not None else None}
    return result


def _temperature(p, waves, step):
    gain, offset = calibration(p)
    rows = {}
    for supply, temp in _temp_conditions(step):
        key = _temp_key(supply, temp)
        wave = waves[key]
        ref = _sample(wave, 'ref', 0)
        sensor = _sample(wave, 'sensor', 0)
        if not 1.1 < ref < 1.3 or not 0 < sensor < ref:
            raise ValueError('The sensor voltage must lie inside the energized ADC reference span.')
        code = math.floor(1024*sensor/ref)
        corrected = (gain*code + offset)/1000
        rows[key] = {'Temperature (°C)': temp, 'Supply (V)': float(supply), 'Reference (V)': ref,
                     'Sensor (V)': sensor, 'ADC code': code, 'Estimate (°C)': corrected, 'Error (°C)': corrected-temp,
                     'Role': 'Anchor' if temp in TEMPERATURE_ANCHORS else 'Held-out trial'}
    return rows


def _pll(p, waves, step):
    result = {}
    for name, wave in waves.items():
        target = 1100 if name == 'step-up' else 900
        direction = 1 if name == 'step-up' else -1
        edge = .001
        end = .015
        _, frequency = _range(wave, 'vco_hz', edge, end)
        _, phase = _range(wave, 'phase_error', .012, end)
        lock = _settling(wave, 'vco_hz', edge, end, target, 2)
        result[name] = {
            'Frequency target (Hz)': target,
            'Final frequency (Hz)': frequency[-1],
            'Overshoot (% of step)': 100*max(0, max(direction*(f-target) for f in frequency))/abs(target-1000),
            'Lock time (ms)': None if lock is None else 1e3*lock,
            'Final phase error (cycles)': phase[-1],
            'Late phase drift (cycles peak-to-peak)': max(phase)-min(phase),
        }
    return result


READOUTS = {'linearity': _linearity, 'rejection': _rejection, 'load': _load, 'adc-ramp': _adc,
            'chopper': _chopper, 'relaxation': _oscillator, 'pll': _pll, 'pga': _pga, 'temperature': _temperature}


def readout(p,lab,waves,step):
    if lab in challenges.ANALYSIS:
        return challenges.measurements(p,lab,waves)
    return READOUTS[lab](p,waves,step)


def run_job(p, job, directory, progress):
    from .engines import run_ngspice
    from .simulation import run

    lab, step = (job['settings'][field] for field in ('lab', 'step'))
    manifest, waves = [], {}
    planned = cases(p, lab, step)
    for i, (name, q, cid, settings) in enumerate(planned):
        folder = Path(directory) / name
        folder.mkdir(parents=True, exist_ok=True)
        def notify(fraction, message):
            progress((i + fraction)/len(planned), name + ' · ' + message)
        if job['engine'] == 'ngspice':
            wave = run_ngspice(q, cid, settings, job['executable'], folder, notify)
        else:
            wave = run(q, cid, settings, notify)
        path = folder / 'wave.json'
        atomic_write(path, json.dumps(wave, allow_nan=False))
        waves[name] = wave
        manifest.append(dict(name=name, sha256=file_digest(path)))
    measures, issue = {}, ''
    try:
        measures = readout(p,lab,waves,step)
    except ValueError as exc:
        # Preserve genuine captures for debugging, including a non-oscillating design.
        issue = str(exc)
    primary = next(name for name, _, cid, _ in planned if cid == job['cell'])
    wave = waves[primary]
    return {**wave, 'design_hash': design_digest(p), 'settings': job['settings'],
            'plot_kind': wave['settings']['type'],
            'student_signal': dict(cases=manifest, measurements=measures, issue=issue)}


def read_cases(p, lab, step, result, root):
    record = result.get('student_signal', {})
    manifest = record.get('cases', [])
    planned = cases(p, lab, step)
    if [case['name'] for case in manifest] != [name for name, _, _, _ in planned]:
        raise ValueError('The captured experiment is missing one or more declared cases.')
    waves = {}
    for captured, (name, snapshot, cid, settings) in zip(manifest, planned):
        path = Path(root) / name / 'wave.json'
        if not path.is_file() or file_digest(path) != captured.get('sha256'):
            raise ValueError('Saved waveform evidence changed. Run the experiment again.')
        wave = json.loads(path.read_text(encoding='utf-8'))
        if (wave.get('design_hash') != design_digest(snapshot) or wave.get('cell_id') != cid
                or wave.get('settings') != settings):
            raise ValueError('A saved case does not match its declared test circuit and conditions.')
        waves[name] = wave
    return waves


TUNABLE = {
    'linearity': {'RS': ('value',), 'VBIAS': ('value',)},
    'rejection': {'CDEC': ('value',), 'RTAIL': ('value',)},
    'load': {'CDOM': ('value',)},
    'adc-ramp': {'R4': ('value',)},
    'chopper': {'CLP': ('value',), 'VDEMOD': ('source.delay',)},
    'relaxation': {'RT': ('native_spice.parameters.r',), 'CT': ('value',)},
    'pll': {'RFILT': ('value',), 'CFILT': ('value',)},
    'pga': {f'RG{i}': ('value',) for i in range(1, 4)},
    'temperature': {'RFIX': ('value',)},
}


def _circuit_signature(p, lab):
    cells = {}
    for c in p['cells']:
        parts = {}
        for device in c['devices']:
            signature = {key: clone(device.get(key)) for key in ('kind', 'nets', 'value', 'params', 'source', 'native_spice')}
            for field in TUNABLE[lab].get(device['name'], ()):
                *parents, item = field.split('.')
                value = signature
                for parent in parents:
                    value = value[parent]
                value.pop(item, None)
            parts[device['name']] = signature
        cells[c['name']] = (c['ports'], c.get('spice_statements', []), parts)
    return cells


TUNABLE.update(challenges.TUNABLE)


@lru_cache(maxsize=len(TUNABLE))
def _reference_signature(lab):
    return _circuit_signature(circuits.project(lab), lab)


def _contract(p, lab):
    if (_circuit_signature(p, lab) != _reference_signature(lab)
            or p.get('spice') != (dict(version=1, assets={}) if lab in circuits.NATIVE else None)
            or p.get('parameters') or any(c.get('parameters') or c.get('spice_parameters') for c in p['cells'])):
        raise ValueError('Restore the supplied topology, models and stimulus. Change the components named in the task.')
    if lab == 'temperature':
        calibration(p)


def _meets_pga(rows):
    for i, target in enumerate((2, 4, 8), 1):
        group = rows[f'gain-code-{i}']
        band, settle = (group[key] for key in ('Bandwidth (Hz)', 'Switching settling (µs)'))
        if (not math.isclose(group['Small-signal gain (V/V)'], target, rel_tol=.035)
                or not math.isclose(group['DC output (V)'], target*.1, rel_tol=.04)
                or band is None or band < 1e6 or settle is None or settle > 12):
            return False
    return True


def assess(lab, step, measured):
    def require(condition, message):
        if not condition:
            raise ValueError(message + ' Open Results to inspect this run.')

    if lab in challenges.ANALYSIS:
        ok = challenges.passed(lab,measured)
        if step == 'baseline':
            require(not ok, 'Capture the original missed target before tuning the circuit.')
        else:
            require(ok, 'The measured circuit misses one or more targets in the lesson.')
    elif lab == 'linearity':
        bias, gain, thd = (measured[k] for k in ('Drain bias (µA)', 'Fundamental gain (V/V)', 'THD, harmonics 2–5 (%)'))
        require(43 <= bias <= 49, f'Drain bias is {bias:.1f} µA. Rebias within 43–49 µA before comparing.')
        if step == 'baseline':
            require(gain >= 3.3 and thd >= 4, 'Capture the original low-degeneration stage first.')
        else:
            require(1.25 <= gain <= 2.8 and thd <= 3, f'Measured gain {gain:.2f} V/V and THD {thd:.2f}%. Meet 1.25–2.8 V/V and ≤3% THD.')
    elif lab == 'rejection':
        cmrr, psrr = (measured[k] for k in ('CMRR at 10 kHz (dB)', 'Input-referred PSRR+ at 10 kHz (dB)'))
        if step == 'baseline':
            require(cmrr < 12 and psrr < 12, 'Capture the original rejection limitations first.')
        else:
            require(cmrr >= 28 and psrr >= 30 and measured['Differential gain (V/V)'] >= 1,
                    f'Measured {cmrr:.1f} dB CMRR and {psrr:.1f} dB PSRR+. Meet 28 dB, 30 dB and gain ≥1 V/V.')
    elif lab == 'load':
        follower = measured['source-follower-500p']
        require(follower['DC error (mV)'] > 20, 'Keep the original follower reference and both test loads.')
        if step == 'repair':
            for case in ('feedback-buffer-100p', 'feedback-buffer-500p'):
                r = measured[case]
                duration = r['Settling to ±10 mV (µs)']
                require(r['DC error (mV)'] <= 10 and duration is not None and duration <= 4
                        and r['Positive overshoot (mV)'] <= 35 and 180 <= r['Mean drain supply (µA)'] <= 245,
                        f'Meet 10 mV DC error, 4 µs settling and 35 mV overshoot at {case.rsplit("-", 1)[1]}F with the original bias.')
    elif lab == 'adc-ramp':
        missing = measured['Missing codes'] + measured['Near-missing codes']
        if step == 'baseline':
            require(3 in missing, 'Identify the collapsed original code-3 bin first.')
        else:
            require(not missing and measured['Peak |DNL| (LSB)'] <= .05 and measured['Peak |INL| (LSB)'] <= .05,
                    'Recover all eight codes within 0.05 LSB peak DNL and INL.')
    elif lab == 'chopper':
        off, on = measured['bypassed'], measured['chopped']
        require(abs(off['Output offset (mV)']) >= 70, 'Preserve the reference amplifier offset in the bypassed comparison.')
        gain, offset, ripple, settle = (on[key] for key in ('Recovered gain (V/V)', 'Output offset (mV)',
                                                           'Ripple p-p (mV)', 'Average settling (µs)'))
        if step == 'baseline':
            require(gain < 10 and ripple > 60, 'Capture the original clock-phase fault and ripple before aligning the switches.')
        else:
            require(19 <= gain <= 21 and abs(offset) < 5 and ripple <= 30 and settle is not None and settle <= 700,
                    'Recover 19–21 V/V, <5 mV output offset, ≤30 mV p-p ripple and ≤700 µs average settling.')
    elif lab == 'relaxation':
        if step == 'baseline':
            require(measured['nominal']['Frequency (Hz)'] >= 3000, 'Capture the original fast oscillator first.')
        else:
            frequencies = [case['Frequency (Hz)'] for case in measured.values()]
            require(all(1800 <= f <= 2500 for f in frequencies)
                    and (max(frequencies)-min(frequencies))/measured['nominal']['Frequency (Hz)'] < .15
                    and all(46 <= case['Duty cycle (%)'] <= 54 and case['First rising edge (µs)'] <= 850 for case in measured.values()),
                    'All three cases need 1.8–2.5 kHz, 46–54% duty, startup within 850 µs and <15% frequency spread.')
    elif lab == 'pll':
        for name, readings in measured.items():
            overshoot = readings['Overshoot (% of step)']
            lock = readings['Lock time (ms)']
            if step == 'baseline':
                require(overshoot > 10 and (lock is None or lock > 6),
                        'Capture the original underdamped loop before changing RFILT or CFILT.')
            else:
                require(overshoot <= 10 and lock is not None and lock <= 6
                        and abs(readings['Final phase error (cycles)']) <= .15
                        and readings['Late phase drift (cycles peak-to-peak)'] <= .01,
                        f'{name}: lock within 6 ms with ≤10% overshoot, ≤0.15 cycles final phase error, '
                        'and ≤0.01 cycles late phase drift.')
    elif lab == 'pga':
        if step == 'baseline':
            require(not _meets_pga(measured), 'Capture the original gain-ladder error first.')
        else:
            require(_meets_pga(measured), 'Meet the 2×, 4× and 8× gain targets, at least 1 MHz bandwidth and switching within 12 µs.')
    else:
        anchors = [row for row in measured.values() if row['Role'] == 'Anchor']
        low, high = (r['ADC code'] for r in anchors)
        if step == 'baseline':
            require(high-low < 55, 'Capture the original compressed sensor span first.')
        else:
            require(120 <= low < high <= 900 and high-low >= 55,
                    f'The anchor codes are {low} and {high}. Adjust RFIX for at least 55 counts of span within codes 120–900.')
        if step == 'validate':
            worst = max(abs(r['Error (°C)']) for r in measured.values() if r['Role'] == 'Held-out trial')
            require(max(abs(r['Error (°C)']) for r in anchors) <= .8 and worst <= 2.5,
                    f'Worst held-out error is {worst:.2f} °C. Fit both anchors within 0.8 °C and all 15 held-out trials within 2.5 °C.')


def check(p, lesson, step, rows):
    from .student_hub import current_result

    lab = lesson['signal_lab']
    cid = focus(p, lab, step)
    _contract(p, lab)
    eligible = [r for r in rows if r['job'].get('student_lesson') == lesson['id']
                and r['job'].get('student_signal_step') == step and r['job']['cell'] == cid]
    result, evidence = current_result(p, eligible)
    if result.get('settings') != dict(type='student_signal_lab', lab=lab, step=step):
        raise ValueError('Run the saved experiment for the active lesson step.')
    waves = read_cases(p, lab, step, result, evidence['run'])
    metrics = readout(p,lab,waves,step)
    assess(lab, step, metrics)
    return dict(**evidence, signal_measurements=metrics,
                signal_cases=result['student_signal']['cases'])
