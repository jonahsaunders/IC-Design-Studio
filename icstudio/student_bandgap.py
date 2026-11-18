"""Parameterized classroom equations for four historical bandgap topologies."""

import math

from .model import device, example, validate

K_OVER_Q = 8.617333262145e-5  # V/K
ROOM_C = 27
BASE_SLOPE = -1.8e-3
CURVATURE = -1.2e-6
NAMES = {'widlar': 'Widlar', 'brokaw': 'Brokaw', 'kuijk': 'Kuijk', 'banba': 'Banba'}
RATIO_LABELS = {'widlar': 'Current ratio I₁/I₂', 'brokaw': 'Emitter-area ratio A₂/A₁',
                'kuijk': 'Emitter-area ratio A₂/A₁', 'banba': 'Emitter-area ratio N'}
WEIGHT_LABELS = {'widlar': 'Resistor ratio R₂/R₃', 'brokaw': 'Resistor ratio R₁/R₂',
                 'kuijk': 'Resistor ratio R₂/R₃', 'banba': 'Resistor ratio R₂/R₃'}


def defaults(kind):
    return {'widlar': (10, 9.1, 1), 'brokaw': (8, 5, 1),
            'kuijk': (8, 10, 1), 'banba': (8, 10, .5)}[kind]


def study(kind, ratio, weight, extra):
    if kind not in NAMES or not 2 <= ratio <= 32 or not 1 <= weight <= 30:
        raise ValueError('Choose a supported topology, ratio of 2–32 and resistor weight of 1–30.')
    if (kind == 'kuijk' and not .5 <= extra <= 3) or (kind == 'banba' and not .25 <= extra <= 1):
        raise ValueError('Choose an auxiliary resistor ratio in the displayed range.')
    density = ratio * extra if kind == 'kuijk' else ratio
    gain = weight * (2 if kind == 'brokaw' else 1)
    scale = extra if kind == 'banba' else 1
    ptat_slope = K_OVER_Q * math.log(density)
    temperatures = list(range(-40, 126))
    junction = [.700 + BASE_SLOPE*(t-ROOM_C) + CURVATURE*(t-ROOM_C)**2 for t in temperatures]
    delta_vbe = [ptat_slope * (t + 273.15) for t in temperatures]
    ct = [scale * value for value in junction]
    pt = [scale * gain * value for value in delta_vbe]
    output = [a + b for a, b in zip(ct, pt)]
    room = temperatures.index(ROOM_C)
    nominal = output[room]
    return dict(x=temperatures, ct=ct, pt=pt, output=output, nominal=nominal, density_ratio=density,
                delta_room=delta_vbe[room], slope27=scale*(BASE_SLOPE + gain*ptat_slope),
                drift=[v-nominal for v in output], span=max(output)-min(output),
                optimum_ratio=-BASE_SLOPE/(ptat_slope*(2 if kind=='brokaw' else 1)),
                i_ctat_uA=junction[room]*10, i_ptat_uA=gain*delta_vbe[room]*10)


def project(kind):
    data = study(kind, *defaults(kind))
    i = data['x'].index(ROOM_C)
    p = example('empty')
    p['name'] = f'Student · {NAMES[kind]} bandgap'
    cell = p['cells'][0]
    cell['name'] = kind + '_summation_model'
    if kind == 'banba':
        cell['devices'] = [
            device('I', 'ICTAT', 210, 280, value=f'{data["i_ctat_uA"]}u', nets={'p':'0','n':'vref'}),
            device('I', 'IPTAT', 520, 280, value=f'{data["i_ptat_uA"]}u', nets={'p':'0','n':'vref'}),
            device('R', 'ROUT', 830, 280, value='50k', nets={'p':'vref','n':'0'}),
        ]
    else:
        cell['devices'] = [
            device('V', 'VCTAT', 240, 430, value=str(data['ct'][i]), nets={'p':'junction','n':'0'}),
            device('V', 'VPTAT', 240, 170, value=str(data['pt'][i]), nets={'p':'vref','n':'junction'}),
        ]
    p['analysis']['type']='op'
    return validate(p)
