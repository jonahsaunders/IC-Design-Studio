"""Separately contacted standard MOS copies for GF180 and IHP.

The original unit and its public pins are preserved. Model m counts complete
parallel units; this does not reinterpret finger count or change W/L.
"""
import math
from .layout import polygon, rect
from .layout_eco import roles
from .model import clone, uid


def count(value):
    if not math.isfinite(value) or value != int(value) or not 1 <= value <= 16:
        raise ValueError('Use an integer physical parallel multiplicity from 1 to 16.')
    return int(value)


def generate(tech, device, data, layers, multiplicity):
    copies = count(multiplicity)
    if copies == 1:
        return data
    target = tech.get('package_lock', {}).get('id')
    if target not in ('gf180mcuC', 'gf180mcuD', 'ihp-sg13g2'):
        raise ValueError('No parallel interconnect recipe for this process.')
    if {p['pin'] for p in data['pins']} != {'d', 'g', 's', 'b'} or any(
            p['layer'] != layers['m1'] for p in data['pins']):
        raise ValueError('Parallel MOS units require four explicit metal1 terminals.')
    roles(data)
    base = clone(data['shapes'])
    bottom = min(polygon(s).bbox().bottom for s in base)
    top = max(polygon(s).bbox().top for s in base)
    pitch = 5 * math.ceil((top - bottom + 3000) / 5)
    for index in range(1, copies):
        for original in base:
            shape = clone(original)
            shape.update(id=uid(), generator_role=f'parallel:{index}:' + original['generator_role'])
            shape['points'] = [[x, y + index * pitch] for x, y in original['points']]
            if 'holes' in shape:
                shape['holes'] = [[[x, y + index * pitch] for x, y in hole] for hole in shape['holes']]
            data['shapes'].append(shape)

    def box(role, key, left, bottom, width, height, net=''):
        shape = rect(layers[key], left, bottom, width, height, device['id'], net)
        shape.update(generated_device=device['id'], generator_role=role)
        data['shapes'].append(shape)

    via_half = 95 if target == 'ihp-sg13g2' else 130
    for pin in data['pins']:
        terminal = pin['pin']; px, py = pin['point']; net = device['nets'][terminal]
        # Move source/drain rails outward so minimum-length gate accesses keep
        # full metal2 clearance. Do not move the unit's original public pins.
        rail_x = px + {'s': -200, 'd': 200}.get(terminal, 0)
        for index in range(copies):
            yy = py + index * pitch
            prefix = f'parallel:access:{terminal}:{index}:'
            box(prefix+'m1', 'm1', min(px, rail_x)-220, yy-220, abs(rail_x-px)+440, 440, net)
            box(prefix+'via', 'via', rail_x-via_half, yy-via_half, 2*via_half, 2*via_half)
            box(prefix+'m2', 'm2', rail_x-220, yy-220, 440, 440, net)
        box('parallel:rail:'+terminal, 'm2', rail_x-220, py-220, 440, (copies-1)*pitch+440, net)
    data['record']['parallel_units'] = dict(count=copies, pitch_nm=pitch,
        offsets_nm=[[0, index*pitch] for index in range(copies)])
    return data


def inverter_separation(tech, nmos, pmos, implementation, original):
    """Keep the full n-array below the p-array, preserving legacy single units."""
    spec = implementation.specification(tech, nmos)
    other = implementation.specification(tech, pmos)
    if spec['values'].get('m', 1) == 1 and all(
            s['values'].get(k, 1) == 1 for s in (spec, other) for k in ('nf', 'ng')):
        return original
    top = max(polygon(s).bbox().top for s in implementation.mos(tech, nmos)['shapes'])
    bottom = min(polygon(s).bbox().bottom for s in implementation.mos(tech, pmos)['shapes'])
    return max(original, top - bottom + 3000)
