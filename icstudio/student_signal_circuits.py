"""Editable fixtures for Student Hub signal and mixed-signal experiments."""

import re

from . import student_circuit_challenges as challenges, student_device_labs as device_labs
from .model import device, example, uid, validate
from .sar_example import primitive

NATIVE = {'load', 'adc-ramp', 'chopper', 'relaxation', 'pll', 'pga', *challenges.ANALYSIS, *device_labs.ANALYSIS}


def named(cell, name):
    item = next((d for d in cell['devices'] if d['name'] == name), None)
    if item is None:
        raise ValueError('Restore the lesson device ' + name + '.')
    return item


def cell(project, name):
    item = next((c for c in project['cells'] if c['name'] == name), None)
    if item is None:
        raise ValueError('Restore the lesson circuit ' + name + '.')
    return item


def _part(c, kind, name, value, pos, neg, x, y, **kwargs):
    item = device(kind, name, x, y, value=value, nets={'p': pos, 'n': neg}, **kwargs)
    c['devices'].append(item)
    return item


def _r(c, name, value, pos, neg, x, y, **kwargs):
    return _part(c, 'R', name, value, pos, neg, x, y, **kwargs)


def _c(c, name, value, pos, neg, x, y):
    return _part(c, 'C', name, value, pos, neg, x, y)


def _v(c, name, value, pos, neg, x, y, **wave):
    item = _part(c, 'V', name, value, pos, neg, x, y)
    item['source'].update(ac='0', **wave)
    return item


def _mos(c, name, d, g, s, x, y, width='10u'):
    item = device('NMOS', name, x, y, nets=dict(d=d, g=g, s=s, b='0'))
    item['params'].update(w=width, l='1u', vto='.45', kp='100u', **{'lambda': '.02'})
    c['devices'].append(item)
    return item


def _pulse(low, high, delay, period, duty='.5'):
    return dict(type='pulse', low=low, high=high, period=period, delay=delay, duty=duty)


def _tokens(text, variables):
    result = []
    for i, part in enumerate(re.split(r'\{([a-z0-9_]+)\}', text)):
        if part:
            result.append(dict(kind=variables[part], value=part) if i % 2 else dict(kind='literal', value=part))
    return result


def _behavior(c, name, out, inputs, expression, x, y, parameters=None, *, output='V'):
    parameters = parameters or {}
    pins = dict(out=out, gnd='0', **inputs)
    item = primitive(name, pins, '', x, y, parameters=parameters)
    item['native_spice']['label'] = name
    variables = {**dict.fromkeys(pins, 'terminal'), **dict.fromkeys(parameters, 'parameter')}
    item['native_spice']['tokens'] = [dict(kind='instance'), *_tokens(f' {{out}} {{gnd}} {output}=' + expression, variables)]
    c['devices'].append(item)


def _linearity(p, c):
    _v(c, 'VDD', '1.8', 'vdd', '0', 420, 110)
    _v(c, 'VBIAS', '.75', 'bias', '0', 90, 330)
    _v(c, 'VIN', '0', 'gate', 'bias', 240, 245, type='sine', low='0', high='.075', period='100u')
    _mos(c, 'M1', 'out', 'gate', 'source', 540, 365)
    _r(c, 'RD', '12k', 'vdd', 'out', 570, 155)
    _r(c, 'RS', '1', 'source', '0', 570, 560)


def _rejection(p, c):
    _v(c, 'VDD', '1.8', 'rail', '0', 150, 120)
    _v(c, 'VP', '.85', 'inp', '0', 140, 330)
    _v(c, 'VN', '.85', 'inn', '0', 860, 330)
    _v(c, 'VTAIL', '.17', 'tail_ref', '0', 870, 630)
    _r(c, 'RISO', '600', 'rail', 'vdd', 360, 95, rotation=270)
    _c(c, 'CDEC', '2p', 'vdd', '0', 645, 90)
    _r(c, 'RD1', '8k', 'vdd', 'out', 370, 230)
    _r(c, 'RD2', '8k', 'vdd', 'other', 645, 230)
    _mos(c, 'M1', 'out', 'inp', 'tail', 345, 408)
    _mos(c, 'M2', 'other', 'inn', 'tail', 620, 408)
    tail = _part(c, 'I', 'ITAIL', '100u', 'tail', '0', 390, 650)
    tail['source']['ac'] = '0'
    _r(c, 'RTAIL', '2k', 'tail', 'tail_ref', 650, 650)


def _follower(c, feedback):
    _v(c, 'VDD', '1.8', 'vdd', '0', 570, 110)
    _v(c, 'VCMD', '.45', 'command', '0', 110, 245, **_pulse('.45', '.65', '5u', '80u'))
    if feedback:
        _behavior(c, 'BCTRL', 'drive', dict(cmd='command', fb='out'),
                  'min(1.74,max(.05,V({cmd})+.62+45*(V({cmd})-V({fb}))))', 320, 240)
        _r(c, 'RDOM', '10k', 'drive', 'gate', 450, 250, rotation=270)
        _c(c, 'CDOM', '2n', 'gate', '0', 440, 470)
    else:
        _v(c, 'VSHIFT', '.87', 'gate', 'command', 310, 260)
    _mos(c, 'MOUT', 'vdd', 'gate', 'out', 620, 305, '20u')
    _part(c, 'I', 'IBIAS', '200u', 'out', '0', 650, 550)
    _r(c, 'RLOAD', '50k', 'out', '0', 845, 410)
    _c(c, 'CL', '500p', 'out', '0', 1030, 410)


def _load(p, c):
    c['name'] = 'feedback_buffer'
    _follower(c, True)
    follower = dict(id=uid(), name='source_follower', ports=[], devices=[], shapes=[])
    p['cells'].append(follower)
    _follower(follower, False)


def _adc(p, c):
    _v(c, 'VREF', '1', 'vref', '0', 130, 150)
    _behavior(c, 'BRAMP', 'vin', {}, 'min(1,time/1m)', 120, 340)
    for i in range(1, 9):
        lower, upper = (f't{i-1}' if i > 1 else '0'), (f't{i}' if i < 8 else 'vref')
        _r(c, f'R{i}', '.01' if i == 4 else '1k', upper, lower, 350, 125 + i*130)
    for i in range(1, 8):
        _behavior(c, f'BC{i}', f'cmp{i}', dict(plus='vin', minus=f't{i}'),
                  '0.5*(1+tanh(12000*(V({plus})-V({minus}))))', 635, 145 + i*130)
    pins = {f'c{i}': f'cmp{i}' for i in range(1, 8)}
    _behavior(c, 'BENC', 'code', pins, '+'.join(f'V({{c{i}}})' for i in range(1, 8)), 1030, 580)


def _chopper(p, c):
    _v(c, 'VIN', '.01', 'input', '0', 110, 215, **_pulse('.01', '.03', '1.5m', '15m'))
    _v(c, 'VOS', '.004', 'offset', '0', 490, 450)
    _v(c, 'VCHOP', '1', 'clkmod', '0', 340, 510, **_pulse('-1', '1', '0', '50u'))
    _v(c, 'VDEMOD', '1', 'clkdemod', '0', 680, 510, **_pulse('-1', '1', '12.5u', '50u'))
    _behavior(c, 'BMOD', 'modulated', dict(i='input', clk='clkmod'), 'V({i})*V({clk})', 330, 210)
    _behavior(c, 'BAMP', 'raw', dict(i='modulated', off='offset'), '20*(V({i})+V({off}))', 520, 210)
    _behavior(c, 'BDEMOD', 'demodulated', dict(i='raw', clk='clkdemod'), 'V({i})*V({clk})', 710, 210)
    _r(c, 'RLP', '10k', 'demodulated', 'out', 895, 210, rotation=270)
    _c(c, 'CLP', '100p', 'out', '0', 1060, 380)


def _relaxation(p, c):
    c['spice_statements'] = ['.options method=gear']
    _v(c, 'VDD', '1.8', 'vdd', '0', 120, 150)
    _r(c, 'RUP', '10k', 'vdd', 'mid', 250, 120)
    _r(c, 'RDOWN', '10k', 'mid', '0', 250, 295)
    # One start-up disturbance. The steady-state circuit sees a zero kick.
    _v(c, 'VSTART', '-.02', 'kick', '0', 130, 480, **_pulse('-.02', '0', '8u', '100m', '.98'))
    _r(c, 'RH', '100k', 'out', 'trip', 480, 100, rotation=270)
    _r(c, 'RM', '100k', 'trip', 'mid', 480, 280)
    _behavior(c, 'BCOMP', 'compare', dict(v='vdd', pos='trip', neg='cap', kick='kick'),
              '0.5*V({v})*(1+tanh(90*(V({pos})+V({kick})-V({neg}))))', 680, 240)
    _r(c, 'RDRIVE', '1k', 'compare', 'out', 850, 210, rotation=270)
    _c(c, 'CPROP', '5p', 'out', '0', 970, 365)
    timer = primitive('RT', {'p': 'out', 'n': 'cap'}, '', 1070, 180, parameters={'r': '12k', 'tc': '.001'})
    timer['native_spice']['label'] = 'Timing resistor'
    timer['native_spice']['tokens'] = [dict(kind='instance'), *_tokens(' {p} {n} {r} tc1={tc}',
        dict(p='terminal', n='terminal', r='parameter', tc='parameter'))]
    c['devices'].append(timer)
    _c(c, 'CT', '10n', 'cap', '0', 1200, 365)


def _pll(p, c):
    # Phase voltages encode cycles relative to a 1 kHz carrier. The current
    # source and capacitor integrate the VCO frequency deviation into phase.
    _v(c, 'VSTEP', '100', 'step_hz', '0', 100, 120)
    _behavior(c, 'BREF', 'ref_phase', {'step': 'step_hz'},
              'V({step})*max(time-1m,0)', 280, 100)
    _behavior(c, 'BPD', 'phase_error', {'ref': 'ref_phase', 'fb': 'vco_phase'},
              'V({ref})-V({fb})', 500, 100)
    _r(c, 'RFILT', '40k', 'phase_error', 'control', 700, 95, rotation=270)
    _c(c, 'CFILT', '100n', 'control', '0', 825, 260)
    _behavior(c, 'BVCO', 'vco_phase', {'ctrl': 'control'},
              '-1000*V({ctrl})', 1025, 100, output='I')
    _c(c, 'CPHASE', '1', 'vco_phase', '0', 1200, 230)
    _r(c, 'RPHASE', '1e12', 'vco_phase', '0', 1330, 230)
    _behavior(c, 'BFREQ', 'vco_hz', {'ctrl': 'control'},
              '1000+1000*V({ctrl})', 1025, 400)


def _pga(p, c):
    _v(c, 'VDD', '1.8', 'vdd', '0', 100, 118)
    _v(c, 'VIN', '.10', 'input', '0', 130, 315)
    _behavior(c, 'BAMP', 'drive', dict(i='input', fb='feedback', dd='vdd'),
              '.5*V({dd})*(1+tanh(1400*(V({i})-V({fb}))))', 355, 258)
    _r(c, 'RDOM', '10k', 'drive', 'out', 575, 248, rotation=270)
    _c(c, 'CDOM', '680p', 'out', '0', 765, 310)
    _r(c, 'RFB', '20k', 'out', 'feedback', 650, 76, rotation=270)
    for i, (value, wave) in enumerate([('30k', _pulse('1.8', '0', '1m', '5m', '.75')),
                                     ('10k', _pulse('0', '1.8', '1m', '5m', '.2')),
                                     ('4k', _pulse('0', '1.8', '2m', '5m', '.2'))], 1):
        x = 270 + 235*i
        _v(c, f'VSEL{i}', '0', f'sel{i}', '0', x - 118, 665, **wave)
        switch = primitive(f'SSEL{i}', dict(a='feedback', b=f'r{i}', ctrl=f'sel{i}', gnd='0'),
                           'pga_switch', x, 502,
                           definition='.model pga_switch SW(Ron=1 Roff=1e10 Vt=.9 Vh=.02)' if i == 1 else '')
        c['devices'].append(switch)
        _r(c, f'RG{i}', value, f'r{i}', '0', x + 156, 665)


def _temperature(p, c):
    _v(c, 'VDD', '1.8', 'supply', '0', 130, 140)
    _v(c, 'VBAND', '1.2', 'bandgap', '0', 130, 370)
    _r(c, 'RFEED', '9.9k', 'supply', 'ref', 357, 138, rotation=270)
    _r(c, 'RREF', '100', 'bandgap', 'ref', 357, 370, rotation=270)
    _r(c, 'RFIX', '56k', 'ref', 'sensor', 640, 270)
    item = _r(c, 'RTEMP', '10k', 'sensor', '0', 640, 500)
    item['params'].update(tc1='.003', tc2='.000002')
    p['student_signal']['calibration'] = dict(gain_mC_per_count=400, offset_mC=-200000)


BUILDERS = {'linearity': _linearity, 'rejection': _rejection, 'load': _load, 'adc-ramp': _adc,
            'chopper': _chopper, 'relaxation': _relaxation, 'pll': _pll, 'pga': _pga, 'temperature': _temperature}

ANALYSIS = {
    'linearity': dict(type='tran', stop='500u', step='500n'),
    'rejection': dict(type='ac', start='1k', end='100k', points=41),
    'load': dict(type='tran', stop='28u', step='40n'),
    'adc-ramp': dict(type='tran', stop='1m', step='250n'),
    'chopper': dict(type='tran', stop='4m', step='500n'),
    'relaxation': dict(type='tran', stop='4m', step='1u'),
    'pll': dict(type='tran', stop='16m', step='10u'),
    'pga': dict(type='tran', stop='2.9m', step='500n'),
    'temperature': dict(type='op'),
}


BUILDERS.update(challenges.BUILDERS)
ANALYSIS.update(challenges.ANALYSIS)
BUILDERS.update(device_labs.BUILDERS)
ANALYSIS.update(device_labs.ANALYSIS)


def project(key):
    p = example('empty')
    p['name'] = 'Student lab · ' + key.replace('-', ' ').title()
    p['student_signal'] = dict(version=1, lab=key)
    p['analysis'].update(ANALYSIS[key])
    if key in NATIVE:
        p['spice'] = dict(version=1, assets={})
    c = p['cells'][0]
    c['name'] = key.replace('-', '_')
    BUILDERS[key](p, c)
    return validate(p)
