"""Editable teaching op amp, verification fixtures, and shared acceptance limits."""

import math
import re

from .model import device, example, scalar, uid
from .sar_example import primitive
from .testbenches import crossings

PROJECT = 'opamp-verification'
TOPIC = 'Build an Op-Amp Verification Suite'
PREFIX = 'tb-verify-'
PORTS = ['INP', 'INN', 'OUT', 'VDD', 'VSS']
AC = dict(type='ac', points=80, start='10', end='30Meg')
TRAN = dict(type='tran', step='5n', stop='12u')
NOISE = dict(type='noise', points=80, start='10', end='100k', output='out', noise_source='VIN')
BIAS = dict(kind='current', source='VDD', min='-105u', max='-95u')


def checkpoint(title, fixture, analysis, probes, limits, goal, work, edit, **details):
    return dict(title=title, fixture=fixture, analysis=analysis, probes=probes.split(), limits=limits,
                goal=goal, work=work, edit=edit, project=PROJECT, **details)


BIAS_CASE = checkpoint('Measure quiescent current and offset', 'follower', dict(type='op'), 'vin out', (-105e-6, -95e-6),
    'At 0.90 V input, verify 95–105 µA drawn from VDD and +0.8 to +1.2 mV equivalent input offset.',
    'Set VIN to 0.90 V DC. OUT feeds INN. Use the negative of I(VDD) for supply draw. Compute signed offset as V(out) − V(vin) under unity feedback.',
    ('VIN', 'value', '.9', '.8'), measurement=BIAS, metric='bias')

COMMON_MODE = checkpoint('Sweep input common mode', 'balanced',
    dict(type='dc', source='VCM', dc_start='-.8', dc_stop='2.6', dc_step='.02'), 'inp inn out', (.898, .904),
    'Verify tracking from 0.35 through 1.45 V actual input common mode. Report the first tracking failure on each side using a ±4 mV output window around 0.90 V.',
    'Set RP to 10k to match RN, RF and RR. RP/RR average VCM with the 0.90 V reference, while RN/RF average VCM with OUT. Plot the actual INP and INN pins. Their mean is the DUT common mode, about (VCM + 0.90 V)/2 inside the range.',
    ('RP', 'value', '10k', '2k'), at='.9', metric='common-mode')

SWING = checkpoint('Sweep loaded output swing', 'inverting',
    dict(type='dc', source='VIN', dc_start='0', dc_stop='1.8', dc_step='.01'), 'vin inp inn out', (.898, .905),
    'With a 100 kΩ load to ground, reach at least 0.22–1.55 V. Report the two clipping plateaus while both input pins stay near 0.90 V.',
    'Set RL from OUT to ground to 100k. The equal 100k input and feedback resistors command 1.8 V − VIN while the noninverting input holds the inverting pin near 0.90 V throughout the usable swing.',
    ('RL', 'value', '100k', '1Meg'), at='.9', metric='swing')

LOOP_BIAS = checkpoint('Confirm bias with the injector in place', 'injection', dict(type='op'), 'vin fb out', (.9008, .9012),
    'Verify that a series injector preserves the follower operating point and that FB and OUT have the same DC voltage.',
    'Set VINJ to 0 V DC with its + terminal on FB (INN) and − terminal on OUT. Leave VIN at 0.90 V and CL at 47 pF.',
    ('VINJ', 'value', '0', '.01'), metric='loop-bias')

LOOP = checkpoint('Measure loop gain and phase margin', 'injection', AC, 'out fb', (.99, 1.01),
    'At 47 pF, inject 1 V AC in series with the feedback path while preserving DC feedback. Verify at least 75 dB loop gain at 10 Hz, a 1.2–1.8 MHz first falling unity crossing, and at least 55° phase margin.',
    'Set VINJ to 1 V AC and 0 V DC. Keep VIN at 0.90 V DC with zero AC and CL at 47 pF. Probe both sides of the series source. Plot T = −V(out)/V(fb) and read 180° + phase(T) at its first falling 0 dB crossing.',
    ('VINJ', 'ac', '1', '0'), at='10', metric='loop')

SMALL = checkpoint('Measure small-signal ringing and settling', 'small-step', TRAN, 'vin out', (.9058, .9062),
    'Apply a rising 10 mV step centered on 0.90 V at 2 µs with 5 ns edges. With 47 pF, limit overshoot to 20% and settle within 2% in 1.5 µs.',
    'Use VIN as a pulse from 0.895 to 0.905 V, with a 2 µs delay, 5 ns edges, and 20 µs period at 50% duty. Connect OUT directly back to INN and leave CL at 47 pF. Measure relative to the observed output plateau.',
    ('VIN', 'type', 'pulse', 'dc'), at='11u', metric='small')

LARGE = checkpoint('Measure large-signal slew rate', 'large-step', TRAN, 'vin out', (1.2512, 1.2518),
    'Apply a rising 0.70 V step centered on 0.90 V with the same timing and 47 pF load as the small step. Verify 0.15–0.25 V/µs between the 30% and 70% crossings.',
    'Use VIN as a pulse from 0.55 to 1.25 V with the same edges, delay, period, duty cycle, feedback and 47 pF load. Use the actual initial and final output levels to locate the 30% and 70% crossings.',
    ('VIN', 'type', 'pulse', 'dc'), at='11u', metric='large')


def psrr(name, label):
    return checkpoint(f'Measure {label} rejection', 'follower', AC, 'out '+name.lower(), (0, .06),
        'At 1 kHz, verify at least 45 dB positive-supply rejection and 45 dB negative-supply rejection with unity noise gain.',
        f'Set {name} to 1 V AC and leave the other supply and VIN at zero AC. Keep VDD at 1.8 V DC and VSS at 0 V DC. Use 20 log10(|V({name.lower()})| / |V(out)|) at 1 kHz.',
        (name, 'ac', '1', '0'), at='1k', metric='psrr')


CMRR = checkpoint('Drive both inputs in common mode', 'balanced', AC, 'inp inn out', (0, .02),
    'Verify at least 45 dB input-referred common-mode rejection at 1 kHz, using the fixture noise gain of 2.',
    'Set VCM to 1 V AC and 0.90 V DC. Keep VREF and both supplies at zero AC and all four divider resistors at 10k. Use the complex mean of INP and INN for actual common-mode excitation. Refer OUT back to the input by dividing by the noise gain of 2.',
    ('VCM', 'ac', '1', '0'), at='1k', metric='cmrr')

NOISE_CASE = checkpoint('Plot density and integrate RMS noise', 'noise', NOISE, 'out', (1.8e-6, 2.8e-6),
    'With a 1 kΩ source resistance at 27 °C, verify 1.8–2.8 µV RMS input-referred noise over 10 Hz–100 kHz. Record the density near 1 kHz as well.',
    'Set RS between VIN and INP to 1k. Use VIN as the noise reference source and OUT as the observed node. Integrate the squared input density over the stated bandwidth, then take its square root.',
    ('RS', 'value', '1k', '10k'), measurement=dict(kind='input_noise', min='1.8u', max='2.8u'), metric='noise')


def variant(base, letter, title, goal=None, **extra):
    return dict(base, title=f'Case {letter.upper()} · {title}', variant=letter, goal=goal or base['goal'], **extra)


# Bases are reused with independently editable fixture cells for each checkpoint.
UNITS = {
    'bias': BIAS_CASE, 'common-mode': COMMON_MODE, 'swing': SWING,
    'loop-bias': LOOP_BIAS, 'loop-ac': LOOP,
    'loop-step': dict(SMALL, title='Restore feedback and compare the step',
        work='Select XDUT and change INN from feedback_open to out in Connections. That restores direct feedback in the transient fixture. VIN already supplies the 10 mV pulse. Keep the same 47 pF load and compare ringing and settling with the measured phase margin.',
        edit=('XDUT', 'INN', 'out', 'feedback_open')),
    'small-step': SMALL, 'large-step': LARGE,
    'psrr-plus': psrr('VDD', 'positive-rail'), 'psrr-minus': psrr('VSS', 'negative-rail'),
    'cmrr': CMRR, 'noise': NOISE_CASE,
    'a-bias': variant(BIAS_CASE, 'a', 'nominal DC'),
    'a-evidence': variant(SMALL, 'a', 'capture transient evidence',
        'Apply the same 10 mV step and 47 pF load as the reference. Compare the captured response with the healthy limits. Save the plot and explain the result.',
        fault='Case A exceeds 20% overshoot under the same capacitive load.'),
    'b-bias': variant(BIAS_CASE, 'b', 'nominal DC'),
    'b-evidence': variant(SWING, 'b', 'capture sweep evidence',
        'Apply the same loaded sweep as the reference. Compare both output extremes with the healthy limits. Save the plot and explain the result.',
        fault='Case B clips before reaching the required loaded output swing.'),
    'c-bias': variant(BIAS_CASE, 'c', 'nominal DC'),
    'c-evidence': variant(psrr('VDD', 'positive-rail'), 'c', 'capture AC evidence',
        'Apply the same 1 kHz positive-supply disturbance as the reference. Compare the measured rejection with the healthy limit. Save the plot and explain the result.',
        fault='Case C falls below 45 dB positive-supply rejection at 1 kHz.'),
}

LESSONS = {
    'dc-bias': ('DC bias and input offset', ('bias',),
        'A follower holds the amplifier in its linear region and translates input offset to an output error. The DUT pins are INP (noninverting), INN (inverting), OUT, VDD (1.8 V), and VSS (0 V).',
        'Why use negative I(VDD) for quiescent current?', ('SPICE defines branch current entering the positive terminal.', 'The negative supply is disconnected.', 'The current is AC.'),
        'Record the operating point, current, signed offset and the assumptions behind the offset estimate.'),
    'input-output-range': ('Input common-mode range and output swing', ('common-mode', 'swing'),
        'Input-pair headroom and output clipping are separate limits. Change one operating condition while keeping the other in its linear region.',
        'Why hold the output near midrail during the common-mode sweep?', ('It isolates input headroom from output clipping.', 'It turns the sweep into a noise analysis.', 'It cancels output load current.'),
        'Report both ranges, the actual pin voltages, the output load and the clipping or tracking criterion.'),
    'loop-stability': ('Open-loop gain and feedback stability', ('loop-bias', 'loop-ac', 'loop-step'),
        'A zero-DC series voltage source is a short at the operating point and an AC injection point after linearization. Use the complex return ratio for a voltage loop with a high-impedance return input.',
        'What must the injector do in the operating-point solve?', ('Preserve DC feedback as a zero-volt source.', 'Leave the inverting input floating.', 'Apply a 1 V DC offset.'),
        'Compare first unity frequency and phase margin with ringing and settling at the same load, after restoring direct feedback.'),
    'step-response': ('Small- and large-signal step response', ('small-step', 'large-step'),
        'A small step reveals linear settling. A large step can drive the compensation current into its limit and reveal slew rate.',
        'Why use both step amplitudes?', ('They distinguish linear settling from slew limiting.', 'A larger step measures DC bias current.', 'They always give the same normalized response.'),
        'Record overshoot and settling for the small step, then compare 30–70% rise slope for the large step.'),
    'rejection': ('PSRR and CMRR', ('psrr-plus', 'psrr-minus', 'cmrr'),
        'Excite one disturbance at a time. Refer each observed error to the input with the fixture noise gain before quoting rejection.',
        'Which adjustment isolates positive-supply rejection?', ('Enable AC on VDD only.', 'Enable equal AC on both rails.', 'Drive INP and INN in opposite directions.'),
        'Report all three rejection values at 1 kHz and name the active source and the noise gain used for each.'),
    'input-noise': ('Input-referred noise', ('noise',),
        'Amplitude density is measured in V/√Hz. Integrating its square over frequency gives noise power in V², which converts to RMS voltage.',
        'What must be integrated to find the mean-square voltage?', ('The square of the input-referred density.', 'The density without squaring.', 'The signed time-domain waveform.'),
        'Report input-referred density at 1 kHz, integrated RMS noise, source resistance and both band edges.'),
    'challenge': ('Op-amp verification challenge', ('a-bias', 'a-evidence', 'b-bias', 'b-evidence', 'c-bias', 'c-evidence'),
        'Each unknown amplifier clears the nominal DC screen. Use the known-good response from the earlier lessons to diagnose each case under the same conditions.',
        'What does a passing DC screen establish?', ('The nominal operating point is acceptable.', 'Every dynamic specification passes.', 'All variants have the same phase margin.'),
        'Save one diagnostic plot for A, B and C. Write one sentence per case naming the failure, the observed figure and the corresponding reference limit.'),
}


def units():
    return {PREFIX+step: {**UNITS[step], 'id': PREFIX+step, 'lesson': PREFIX+lesson, 'step': step}
            for lesson, (_, steps, *_) in LESSONS.items() for step in steps}


def _cell(name, ports=()):
    return dict(id=uid(), name=name, ports=list(ports), devices=[], shapes=[])


def _part(c, kind, name, value, p, n, x, y):
    item = device(kind, name, x, y, value=value, nets=dict(p=p, n=n))
    item['source']['ac'] = '0'
    c['devices'].append(item)
    return item


def _behavior(c, name, pins, formula, x, y):
    item = primitive(name, pins, '', x, y)
    parts = re.split(r'\{([a-z]+)\}', formula)
    item['native_spice']['tokens'] = [dict(kind='instance'), *(
        dict(kind='terminal' if i % 2 else 'literal', value=part) for i, part in enumerate(parts) if part)]
    c['devices'].append(item)


def _amplifier(variant=''):
    c = _cell('verification_reference' if not variant else 'verification_case_'+variant, PORTS)
    _part(c, 'I', 'IQ', '100u', 'VDD', 'VSS', 180, 140)
    _part(c, 'R', 'RINPUT', '2k', 'INP', 'plus', 180, 325)
    # Nominal gain is gm times RP. CP sets the dominant pole and Imax/CP sets slew rate.
    pos_ripple = '.025' if variant == 'c' else '.001'
    error = (f'min(max(V({{plus}}),.35),1.45)-V({{minus}})+.001'
             f'+{pos_ripple}*(V({{dd}})-1.8)+.002*V({{ss}})'
             '+.0015*((V({plus})+V({minus}))/2-.9)')
    _behavior(c, 'BGM', dict(pole='pole', ss='VSS', dd='VDD', plus='plus', minus='INN'),
              ' {pole} {ss} I=-min(max(.001*('+error+'),-20u),20u)', 410, 315)
    _part(c, 'R', 'RP', '10Meg', 'pole', 'VSS', 610, 200)
    _part(c, 'C', 'CP', '100p', 'pole', 'VSS', 610, 410)
    headroom = '.42' if variant == 'b' else '.18'
    _behavior(c, 'BDRIVE', dict(drive='drive', ss='VSS', dd='VDD', pole='pole'),
              f' {{drive}} {{ss}} V=min(max(.9+V({{pole}},{{ss}}),{headroom}),V({{dd}},{{ss}})-{headroom})', 830, 315)
    _part(c, 'R', 'RO', '8k' if variant == 'a' else '1k', 'drive', 'OUT', 1060, 315)
    return c


def _fixture(unit, amplifier):
    kind = unit['fixture']
    c = _cell(unit['id'].replace('-', '_')+'_fixture')
    inp, inn = 'vin', 'out'
    _part(c, 'V', 'VDD', '1.8', 'vdd', '0', 140, 115)
    _part(c, 'V', 'VSS', '0', 'vss', '0', 140, 505)
    if kind == 'balanced':
        inp, inn = 'inp', 'inn'
        _part(c, 'V', 'VCM', '.9', 'cm', '0', 140, 275)
        _part(c, 'V', 'VREF', '.9', 'ref', '0', 140, 395)
        for name, pos, neg, x, y in (('RP','cm','inp',360,200), ('RR','ref','inp',360,310),
                                      ('RN','cm','inn',470,420), ('RF','out','inn',690,560)):
            _part(c, 'R', name, '10k', pos, neg, x, y)['rotation'] = 270
    else:
        source = _part(c, 'V', 'VIN', '.9', 'vin', '0', 140, 315)
        if kind.endswith('-step'):
            lo, hi = ('.895','.905') if kind == 'small-step' else ('.55','1.25')
            source.update(value=lo)
            source['source'].update(type='pulse', low=lo, high=hi, delay='2u', period='20u', duty='.5', rise='5n', fall='5n')
        if kind == 'injection':
            inn = 'fb'
            _part(c, 'V', 'VINJ', '0', 'fb', 'out', 730, 510)['rotation'] = 270
        if kind == 'noise':
            inp = 'inp'
            _part(c, 'R', 'RS', '1k', 'vin', 'inp', 370, 260)['rotation'] = 270
        if kind == 'inverting':
            inp, inn = 'inp', 'inn'
            _part(c, 'V', 'VREF', '.9', 'inp', '0', 350, 135)
            _part(c, 'R', 'RI', '100k', 'vin', 'inn', 375, 410)['rotation'] = 270
            _part(c, 'R', 'RF', '100k', 'out', 'inn', 730, 550)['rotation'] = 270
            _part(c, 'R', 'RL', '100k', 'out', '0', 1050, 255)
    _part(c, 'C', 'CL', '47p', 'out', '0', 1050, 420)
    c['devices'].append(device('X', 'XDUT', 650, 320, cell=amplifier['id'],
                               nets=dict(INP=inp, INN=inn, OUT='out', VDD='vdd', VSS='vss')))
    edit(c, unit, solved=False)
    return c


def edit(cell, unit, solved):
    name, field, target, starter = unit['edit']
    part = next(d for d in cell['devices'] if d['name'] == name)
    value = target if solved else starter
    if part['kind'] == 'X':
        old = part['nets'][field]
        part['nets'][field] = value
        for label in cell.get('labels', []):
            if label['name'] == old:
                label['name'] = value
    else:
        fields = part if field == 'value' else part['source']
        fields[field] = value


def validate_fixture(project, cell, unit):
    variant = unit.get('variant')
    dut_name = 'verification_case_'+variant if variant else 'verification_reference'
    dut = next((c for c in project['cells'] if c['name'] == dut_name), None)
    if dut is None:
        raise ValueError('Restore the amplifier assigned to this fixture.')
    expected = _fixture(unit, dut)
    edit(expected, unit, solved=True)
    devices = {d['name']:d for d in cell['devices']}
    for part in expected['devices']:
        actual = devices.get(part['name'], {})
        kind = part['kind']
        correct = actual.get('kind') == kind and actual.get('nets') == part['nets']
        if correct and kind == 'X':
            correct = actual.get('cell') == dut['id']
        elif correct:
            correct = math.isclose(scalar(actual['value']), scalar(part['value']))
            if kind == 'V':
                source, wanted = actual['source'], part['source']
                correct = source['type'] == wanted['type'] and math.isclose(scalar(source['ac']), scalar(wanted['ac'])) and correct
                if wanted['type'] == 'pulse':
                    correct = correct and all(math.isclose(scalar(source[key]), scalar(wanted[key]))
                                              for key in ('low','high','period','delay','duty','rise','fall'))
        if not correct:
            raise ValueError(f'Complete the fixture setup for {part["name"]}. {unit["work"]}')


def project():
    p = example('empty')
    p['spice'] = dict(version=1, assets={})
    amplifiers = {variant: _amplifier(variant) for variant in ('', 'a', 'b', 'c')}
    p['cells'] = [*amplifiers.values(), *(_fixture(unit, amplifiers[unit.get('variant', '')]) for unit in units().values())]
    return p


def loop_trace(result):
    traces, phases = result['traces'], result.get('phase', {})
    if any(len(vectors.get(net, ())) != len(result['x']) for vectors in (traces, phases) for net in ('out', 'fb')):
        raise ValueError('Capture both OUT and FB as complex AC traces.')
    if any(value <= 0 for net in ('out', 'fb') for value in traces[net]):
        raise ValueError('A loop trace has zero magnitude. Check the AC injection and return path.')
    magnitude = [20*math.log10(a)-20*math.log10(b) for a, b in zip(traces['out'], traces['fb'])]
    phase = []
    for a, b in zip(phases['out'], phases['fb']):
        angle = (a-b) % 360 - 180
        phase.append(angle if not phase else phase[-1] + (angle-phase[-1]+180) % 360 - 180)
    return magnitude, phase


def figures(unit, result, verify):
    from .student_hub import at

    xs, traces = result['x'], result['traces']
    metric = unit['metric']
    readings, ok = {}, True
    if metric == 'noise':
        readings = {'Density at 1 kHz (nV/√Hz)': at(result, 'inoise_spectrum', 1e3)*1e9,
                    'Integrated input noise (µV RMS)': result['diagnostics']['input_rms_V']*1e6}
    elif metric == 'bias':
        offset = (traces['out'][0]-traces['vin'][0])*1e3
        drawn = -result['currents']['vdd'][0]*1e6
        readings = {'Input offset (mV)': offset, 'Quiescent current (µA)': drawn}
        ok = .8 <= offset <= 1.2 and 95 <= drawn <= 105 and abs(traces['vin'][0]-.9) < .001
    elif metric == 'loop-bias':
        drop = (traces['fb'][0]-traces['out'][0])*1e3
        readings = {'DC voltage across injection source (mV)': drop}
        ok = abs(drop) < .01
    elif metric == 'loop':
        gain, phase = loop_trace(result)
        unity = crossings([math.log(x) for x in xs], gain, 0, edge='falling')
        frequency = math.exp(unity[0]) if unity else None
        margin = 180+at(dict(x=[math.log(x) for x in xs], traces={'phase': phase}), 'phase', unity[0]) if unity else None
        readings = {'Gain at 10 Hz (dB)': gain[0], 'First unity crossing (Hz)': frequency, 'Phase margin (°)': margin}
        ok = gain[0] >= 75 and frequency is not None and 1.2e6 <= frequency <= 1.8e6 and margin >= 55
    elif metric == 'common-mode':
        good = [(a+b)/2 for a,b,y in zip(traces['inp'], traces['inn'], traces['out']) if abs(y-.9) <= .004]
        low, high = (min(good), max(good)) if good else (None, None)
        readings = {'First passing common mode (V)': low, 'Last passing common mode (V)': high}
        ok = bool(good) and .33 <= low <= .36 and 1.44 <= high <= 1.47 and all(
            abs(y-.9) <= .004 for a,b,y in zip(traces['inp'], traces['inn'], traces['out']) if .35 <= (a+b)/2 <= 1.45)
    elif metric == 'swing':
        low, high = min(traces['out']), max(traces['out'])
        readings = {'Low clipping plateau (V)': low, 'High clipping plateau (V)': high}
        ok = low <= .22 and high >= 1.55
    elif metric in ('small', 'large'):
        initial, final = (at(result, 'out', t) for t in (1e-6, 11e-6))
        height = final-initial
        if metric == 'small' and height > 0:
            edge = 2e-6
            peak = max(0, 100*(max(traces['out'])-final)/height)
            outside = [i for i,(x,y) in enumerate(zip(xs,traces['out'])) if x >= edge and abs(y-final) > .02*height]
            last = outside[-1]+1 if outside else next(i for i,x in enumerate(xs) if x >= edge)
            settle = (xs[last]-edge)*1e6 if last < len(xs) else None
            readings = {'Overshoot (%)': peak, 'Settling within 2% (µs)': settle}
            ok = peak > 20 if unit.get('fault') else peak <= 20 and settle is not None and settle <= 1.5
        elif metric == 'large' and height > 0:
            edges = [crossings(xs, traces['out'], initial+fraction*height, start=2e-6) for fraction in (.3,.7)]
            slew = .4*height/(edges[1][0]-edges[0][0])*1e-6 if all(edges) else None
            readings = {'30–70% rising slew rate (V/µs)': slew}
            ok = slew is not None and .15 <= slew <= .25
        else:
            ok = False
    elif metric in ('psrr', 'cmrr'):
        output = at(result, 'out', 1e3)
        if metric == 'cmrr':
            from cmath import rect
            inputs = [rect(at(result, net, 1e3), math.radians(at({**result,'traces':result['phase']}, net, 1e3)))
                      for net in ('inp','inn')]
            excitation = abs(sum(inputs))  # Mean of two pins multiplied by noise gain of two.
        else:
            excitation = at(result, unit['probes'][1], 1e3)
        rejection = 20*math.log10(excitation/max(output, 1e-30)) if excitation > .4 else None
        readings = {'Rejection at 1 kHz (dB)': rejection}
        ok = rejection is not None and rejection >= 45
        if unit.get('fault'):
            ok = rejection is not None and rejection < 45
    if metric == 'swing' and unit.get('fault'):
        ok = not ok
    if verify and not ok:
        raise ValueError('The waveform did not reproduce the expected case signature.' if unit.get('fault') else unit['goal'])
    return readings
