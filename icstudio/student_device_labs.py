"""Editable analog teaching experiments and measurements from captured ngspice runs."""

import math

from .model import device, scalar

ANALYSIS = {
    'output-resistance': dict(type='dc', source='VDRAIN', dc_start='.1', dc_stop='1.5', dc_step='.01'),
    'body-effect': dict(type='dc', source='VGATE', dc_start='.2', dc_stop='1.2', dc_step='.005'),
    'active-load': dict(type='ac', start='10', end='100k', points=20),
    'transmission-gate': dict(type='dc', source='VCM', dc_start='.1', dc_stop='1.7', dc_step='.02'),
    'noise-spectrum': dict(type='noise', source='VIN', output='out_full', start='10', end='1meg', points=25),
    'bias-leakage': dict(type='op'),
    'common-mode-feedback': dict(type='tran', stop='20u', step='20n'),
    'switch-pedestal': dict(type='tran', stop='2u', step='1n'),
}

CONTROLS = {
    'output-resistance': ('Set drain bias', ('VGATE', 'value', 'Gate bias (V)')),
    'body-effect': ('Set reverse body bias', ('VSB', 'value', 'Source-to-body voltage (V)')),
    'active-load': ('Match the output bias', ('RLOAD', 'value', 'Resistive load (Ω)')),
    'transmission-gate': ('Size the PMOS switch', ('MP', 'native_spice.parameters.w', 'PMOS width (m)')),
    'bias-leakage': ('Set the bias resistance', ('RBIAS', 'value', 'Bias resistance (Ω)')),
    'common-mode-feedback': ('Compensate the common-mode loop', ('VGAIN', 'value', 'Loop gain (V/V)'),
                             ('CFILT', 'value', 'Compensation capacitance (F)')),
    'switch-pedestal': ('Set the hold capacitance', ('CHOLD', 'value', 'Hold capacitance (F)')),
}
TUNABLE = {key: {name: (field,) for name, field, _ in controls[1:]} for key, controls in CONTROLS.items()}
TUNABLE['noise-spectrum'] = {}

NMOS = 'NMOS LEVEL=1 VTO=.45 KP=100u LAMBDA=.045 GAMMA=.45 PHI=.7'
PMOS = 'PMOS LEVEL=1 VTO=-.45 KP=50u LAMBDA=.045 GAMMA=.45 PHI=.7'


def _native(c, name, pins, spec, x, y, *, parameters=None):
    from .sar_example import primitive
    from .student_signal_circuits import _tokens
    parameters = parameters or {}
    part = primitive(name, pins, '', x, y, parameters=parameters)
    part['native_spice']['tokens'] = [
        dict(kind='instance'),
        *_tokens(spec, {**dict.fromkeys(pins, 'terminal'), **dict.fromkeys(parameters, 'parameter')}),
    ]
    c['devices'].append(part)
    return part


def _fet(c, name, d, g, s, b, x, y, *, model='teach_n', width='10u'):
    from .symbol_io import device_symbol
    pins=dict(d=d,g=g,s=s,b=b)
    part=_native(c,name,pins,' {d} {g} {s} {b} '+model+' W={w} L=1u',x,y,parameters={'w':width})
    schematic=device('PMOS' if model=='teach_p' else 'NMOS',name,x,y,nets=pins)
    # Use Studio's transistor symbol and keep the embedded model authoritative.
    part['symbol']={**device_symbol(schematic),'pin_order':list(pins)}
    part['native_spice']['model']=model
    return part


def output_resistance(p, c):
    from .student_signal_circuits import _v
    c['spice_statements'] = ['.model teach_n '+NMOS]
    _v(c, 'VDRAIN', '1', 'out', '0', 450, 105)
    _v(c, 'VGATE', '.72', 'gate', '0', 120, 260)
    _fet(c, 'M1', 'out', 'gate', '0', '0', 450, 300)


def body_effect(p, c):
    from .student_signal_circuits import _v
    c['spice_statements'] = ['.model teach_n '+NMOS]
    _v(c, 'VDRAIN', '1.2', 'out', '0', 540, 105)
    _v(c, 'VGATE', '.7', 'gate', '0', 110, 290)
    _v(c, 'VSB', '.2', '0', 'body', 305, 470)
    _fet(c, 'M1', 'out', 'gate', '0', 'body', 540, 300)


def active_load(p, c):
    from .student_signal_circuits import _v, _r
    c['spice_statements'] = ['.model teach_n '+NMOS, '.model teach_p '+PMOS]
    _v(c, 'VDD', '1.8', 'vdd', '0', 125, 110)
    _v(c, 'VIN', '.8', 'gate', '0', 125, 410)['source']['ac'] = '1'
    _r(c, 'RLOAD', '30k', 'vdd', 'out_r', 420, 125)
    _fet(c, 'MPLOAD', 'out_p', 'out_p', 'vdd', 'vdd', 685, 125, model='teach_p')
    _fet(c, 'MNR', 'out_r', 'gate', '0', '0', 420, 385)
    _fet(c, 'MNP', 'out_p', 'gate', '0', '0', 685, 385)


def transmission_gate(p, c):
    from .student_signal_circuits import _v
    c['spice_statements'] = ['.model teach_n '+NMOS, '.model teach_p '+PMOS]
    _v(c, 'VCM', '.9', 'in', '0', 120, 110)
    _v(c, 'VEN', '1.8', 'en', '0', 120, 330)
    _v(c, 'VNMOS', '.005', 'out_n', 'in', 425, 110)
    _v(c, 'VTG', '.005', 'out_tg', 'in', 690, 110)
    _fet(c, 'MNREF', 'out_n', 'en', 'in', '0', 425, 350)
    _fet(c, 'MN', 'out_tg', 'en', 'in', '0', 690, 350)
    _fet(c, 'MP', 'out_tg', '0', 'in', 'en', 945, 350, model='teach_p', width='2u')


def noise_spectrum(p, c):
    from .student_signal_circuits import _v, _r
    c['spice_statements'] = ['.model teach_n '+NMOS, '.model teach_f '+NMOS+' KF=1e-25 AF=1']
    _v(c, 'VDD', '1.8', 'vdd', '0', 125, 110)
    _v(c, 'VIN', '.8', 'gate', '0', 125, 400)['source']['ac'] = '1'
    for x, name, model in ((410, 'thermal', 'teach_n'), (685, 'full', 'teach_f')):
        _r(c, 'R'+name.upper(), '12k', 'vdd', 'out_'+name, x, 125)
        _fet(c, 'M'+name.upper(), 'out_'+name, 'gate', '0', '0', x, 380, model=model)


def bias_leakage(p, c):
    from .student_signal_circuits import _v, _r
    c['spice_statements'] = ['.model leak_d D(IS=10p XTI=3 EG=1.11)']
    _v(c, 'VREF', '1.2', 'ref', '0', 130, 150)
    _r(c, 'RBIAS', '10meg', 'ref', 'out', 410, 140)
    _native(c, 'DLEAK', {'a':'0', 'k':'out'}, ' {a} {k} leak_d', 410, 370)


def common_mode_feedback(p, c):
    from .student_signal_circuits import _behavior, _c, _pulse, _r, _v
    _v(c, 'VREF', '.9', 'ref', '0', 100, 100)
    _v(c, 'VDIFF', '.2', 'diff', '0', 100, 260)
    _v(c, 'VGAIN', '1', 'gain', '0', 100, 420)
    _v(c, 'VBUMP', '0', 'bump', '0', 100, 580, **_pulse('0','.12','5u','40u'))
    _behavior(c, 'BCM', 'cm', dict(p='out_p', n='out_n'), '(V({p})+V({n}))/2', 1200, 200)
    _behavior(c, 'BERR', 'err', dict(ref='ref', cm='cm', gain='gain'),
              'V({gain})*(V({ref})-V({cm}))', 300, 190)
    _r(c, 'RFILT', '10k', 'err', 'control', 515, 165, rotation=270)
    _c(c, 'CFILT', '200p', 'control', '0', 640, 390)
    for x, name, sign in ((860, 'p', '+'), (1020, 'n', '-')):
        _behavior(c, 'BOUT'+name.upper(), 'out_'+name,
                  dict(ref='ref', bump='bump', d='diff', v='control'),
                  'V({ref})+V({bump})+V({v})'+sign+'V({d})/2', x, 175)


def switch_pedestal(p, c):
    from .student_signal_circuits import _c, _part, _pulse, _r, _v
    c['spice_statements'] = ['.model sample_gate SW(RON=100 ROFF=1e12 VT=.9 VH=.02)']
    _v(c, 'VIN', '.9', 'vin', '0', 120, 120)
    _v(c, 'VCLK', '1.8', 'clk', '0', 120, 365, **_pulse('1.8','0','1u','4u'))
    _native(c, 'SSAMPLE', dict(a='vin', b='out', ctrl='clk', gnd='0'),
            ' {a} {b} {ctrl} {gnd} sample_gate', 380, 180)
    _c(c, 'COV', '40f', 'out', 'clk', 615, 180)
    _c(c, 'CHOLD', '1p', 'out', '0', 710, 410)
    _r(c, 'RBLEED', '100g', 'out', 'vin', 940, 415)
    pulse = _part(c, 'I', 'IINJ', '0', 'out', '0', 950, 180)
    pulse['source'].update(ac='0', **_pulse('0','1u','1.03u','4u','.005'))


BUILDERS = dict(zip(ANALYSIS, (output_resistance, body_effect, active_load, transmission_gate,
                              noise_spectrum, bias_leakage, common_mode_feedback, switch_pedestal)))


def cases(p, lab, analysis, case):
    from .student_signal_labs import _dc

    if lab == 'output-resistance':
        return [case(p,'sweep',analysis),case(p,'dc-bias',dict(type='op'))]
    if lab == 'body-effect':
        return [case(p, 'body-tied', analysis, lambda c: _dc(c, 'VSB', 0)),
                case(p, 'reverse-bias', analysis),case(p,'dc-bias',dict(type='op'))]
    if lab == 'active-load':
        return [case(p, 'dc-bias', dict(type='op')), case(p, 'small-signal', analysis)]
    if lab == 'noise-spectrum':
        return [case(p, 'thermal-only', {**analysis, 'output':'out_thermal'}),
                case(p, 'with-flicker', analysis)]
    if lab == 'bias-leakage':
        return [case(p, name, {**analysis, 'temperature': temp}) for name,temp in (('room',27),('hot',85))]
    if lab == 'common-mode-feedback':
        return [case(p, 'open-loop', analysis, lambda c: _dc(c, 'VGAIN', 0)),
                case(p, 'closed-loop', analysis)]
    if lab == 'switch-pedestal':
        def remove_overlap(c):
            c['devices'] = [d for d in c['devices'] if d['name'] != 'COV']
        return [case(p, 'clock-feedthrough', analysis, lambda c: _dc(c, 'IINJ', 0)),
                case(p, 'charge-injection', analysis, remove_overlap),
                case(p, 'combined', analysis)]
    return [case(p, 'sweep', analysis)]


def _current(wave, name, x):
    from .student_signal_labs import _at, _series
    return abs(_at(*_series(wave, name, 'currents'), x))


def _constant_current_threshold(wave):
    from .student_signal_labs import _series
    axis, current = _series(wave, 'VDRAIN', 'currents')
    target = 10e-6
    for lo, hi, a, b in zip(axis, axis[1:], current, current[1:]):
        a, b = abs(a), abs(b)
        if a < target <= b:
            return lo + (hi-lo)*(target-a)/(b-a)
    raise ValueError('The sweep did not reach the 10 µA threshold criterion.')


def measurements(p, lab, waves):
    from .student_signal_labs import _sample, _settling
    from .student_signal_circuits import named

    if lab == 'output-resistance':
        w = waves['sweep']
        a, b = (_current(w, 'VDRAIN', v) for v in (.8, 1.2))
        if b <= a:
            raise ValueError('The drain current must increase across the saturation measurement interval.')
        return {'Saturation current at 0.8 V (µA)': 1e6*a,
                'Saturation current at 1.2 V (µA)': 1e6*b,
                'Output resistance (kΩ)': .4/(b-a)/1e3}
    if lab == 'body-effect':
        tied = _constant_current_threshold(waves['body-tied'])
        reverse = _constant_current_threshold(waves['reverse-bias'])
        return {'Body-tied VGS at 10 µA (V)': tied, 'Reverse-bias VGS at 10 µA (V)': reverse,
                'Threshold shift (mV)': 1e3*(reverse-tied)}
    if lab == 'active-load':
        bias, ac = (waves[name] for name in ('dc-bias','small-signal'))
        return {label: {'Output bias (V)': _sample(bias,node,0), 'Gain magnitude (V/V)': _sample(ac,node,100)}
                for label,node in (('resistor','out_r'), ('diode-connected PMOS','out_p'))}
    if lab == 'transmission-gate':
        w = waves['sweep']
        return {f'{v:g} V': {'NMOS on resistance (Ω)': .005/max(_current(w,'VNMOS',v), 1e-15),
                            'Transmission-gate resistance (Ω)': .005/max(_current(w,'VTG',v), 1e-15)}
                for v in (.2,.9,1.6)}
    if lab == 'noise-spectrum':
        thermal, full = (waves[name] for name in ('thermal-only','with-flicker'))
        out = {}
        for f in (10,100,1000,100_000,1_000_000):
            floor = _sample(thermal, 'out_thermal', f)
            total = _sample(full, 'out_full', f)
            flicker = math.sqrt(max(0, total**2-floor**2))
            out[f'{f:g} Hz'] = {'Thermal density (nV/√Hz)': 1e9*floor, 'Total density (nV/√Hz)': 1e9*total,
                              'Inferred flicker density (nV/√Hz)': 1e9*flicker}
        return out
    if lab == 'bias-leakage':
        cell = next(c for c in p['cells'] if c['id'] == p['top'])
        r = scalar(named(cell,'RBIAS')['value'])
        return {name: {'Bias voltage (V)': v, 'Leakage (nA)': (1.2-v)/r*1e9}
                for name,w in waves.items() for v in [_sample(w,'out',0)]}
    if lab == 'common-mode-feedback':
        cases={}
        for name,wave in waves.items():
            final=_sample(wave,'cm',18e-6)
            recovery=_settling(wave,'cm',5e-6,18e-6,final,.002)
            cases[name]={
                'Common-mode error (mV)': 1e3*abs(final-.9),
                'Differential output (mV)': 1e3*(_sample(wave,'out_p',18e-6)-_sample(wave,'out_n',18e-6)),
                'Common-mode recovery (µs)': None if recovery is None else 1e6*recovery,
            }
        return cases
    return {name: {'Held voltage step (mV)': 1e3*(_sample(w,'out',1.3e-6)-_sample(w,'out',.8e-6))}
            for name,w in waves.items()}


def assess(lab, values):
    passed = True
    if lab == 'output-resistance':
        passed = 15 <= values['Saturation current at 0.8 V (µA)'] <= 100 and 300 <= values['Output resistance (kΩ)'] <= 500
    elif lab == 'body-effect':
        passed = 130 <= values['Threshold shift (mV)'] <= 230
    elif lab == 'active-load':
        r, m = values['resistor'], values['diode-connected PMOS']
        passed = abs(r['Output bias (V)']-m['Output bias (V)']) <= .12 and r['Gain magnitude (V/V)'] > 2*m['Gain magnitude (V/V)']
    elif lab == 'transmission-gate':
        resistance = [v['Transmission-gate resistance (Ω)'] for v in values.values()]
        passed = max(resistance) <= 1900 and max(resistance)/min(resistance) <= 2.6
    elif lab == 'noise-spectrum':
        low, high = values['100 Hz'], values['1e+06 Hz']
        passed = (low['Inferred flicker density (nV/√Hz)'] > low['Thermal density (nV/√Hz)']
                  and high['Inferred flicker density (nV/√Hz)'] < high['Thermal density (nV/√Hz)'])
    elif lab == 'bias-leakage':
        room, hot = values['room'], values['hot']
        passed = abs(hot['Bias voltage (V)']-1.2) <= .05 and hot['Leakage (nA)'] > 10*room['Leakage (nA)'] > 0
    elif lab == 'common-mode-feedback':
        closed = values['closed-loop']
        recovery=closed['Common-mode recovery (µs)']
        passed = (closed['Common-mode error (mV)'] <= 10 and abs(closed['Differential output (mV)']-200) <= 1
                  and recovery is not None and recovery <= 2)
    elif lab == 'switch-pedestal':
        a, b, total = (values[name]['Held voltage step (mV)'] for name in
                       ('clock-feedthrough','charge-injection','combined'))
        passed = a < -2 and b < -2 and abs(total) <= 35 and abs(a+b-total) <= 10
    if not passed:
        raise ValueError('The measured comparison misses the design targets. Open Results to see which measurements to tune.')
