"""Bounded square second-plate SKY130 MiM layout, on metal4/cap2m/metal5.

The pinned open_pdks technology identifies cap2m as 97/44 and uses via4
contacts. These are editable recipes; each placed design still needs DRC/LVS.
"""
import math

from .catalog import binding_for, parameter_values
from .model import clone, uid
from .layout import rect

MODEL = 'sky130_fd_pr__cap_mim_m3_2'
MASKS = {'m4': (71, 20), 'm5': (72, 20), 'via4': (71, 44), 'cap2m': (97, 44)}


def supported(tech, device):
    binding = binding_for(tech, device)
    return bool(tech.get('package_lock', {}).get('id') == 'sky130A'
                and binding and binding.get('model') == MODEL)


def layers(tech):
    by = {(v['gds'], v['datatype']): v['name'] for v in tech['layers']}
    if not set(MASKS.values()) <= by.keys():
        raise ValueError('Second-plate MiM layout requires metal4, metal5, via4 and cap2m.')
    return {key: by[pair] for key, pair in MASKS.items()}


def specification(tech, device):
    binding = binding_for(tech, device)
    if (not supported(tech, device) or device['kind'] != 'PDK'
            or binding.get('prefix') != 'X' or binding.get('pin_order') != ['c0', 'c1']
            or set(device['nets']) != {'c0', 'c1'}
            or binding.get('emit_parameters') != {'w': 'w', 'l': 'l', 'vm': 'mf', 'm': 'mf'}
            or binding.get('parameter_scale') != {'w': 1e6, 'l': 1e6}):
        raise ValueError('Use the shipped SKY130 second-plate MiM terminal and parameter binding.')
    layers(tech)
    values = parameter_values(binding, device)
    count = values['mf']
    if not math.isfinite(count) or count != int(count) or not 1 <= count <= 16:
        raise ValueError('Use an integer MiM parallel multiplicity from 1 to 16.')
    size = {}
    for key in ('w', 'l'):
        nm = values[key] * 1000
        if not math.isfinite(nm) or abs(nm - round(nm)) > 1e-6 or round(nm) % 5 or not 2000 <= nm <= 30000:
            raise ValueError(key.upper() + ': use 2–30 µm on the 5 nm grid for the second-plate MiM recipe.')
        size[key] = round(nm)
    # The pinned Magic extractor exchanges rectangular W/L after rotation.
    # The public model's series resistance depends on L/W, so accepting that
    # exchange in LVS would change electrical behavior. Keep rectangles out of
    # this new recipe until their orientation has an independent extraction path.
    if size['w'] != size['l']:
        raise ValueError('Second-plate MiM layout currently requires W = L. Rectangular rotation is not qualified by the native extractor.')
    result = dict(api=1, recipe='mim2_capacitor', model=MODEL, model_ref=clone(device['model_ref']),
                  kind=device['kind'], values=values, dimensions_nm=size, nets=clone(device['nets']))
    if count > 1:
        result['multiplicity'] = int(count)
    return result


def configure_connectivity(tech):
    ls = layers(tech)
    cfg = tech.setdefault('connectivity', {})
    cfg['conductors'] = list(dict.fromkeys(cfg.get('conductors', []) + [ls[k] for k in ('m4', 'm5', 'cap2m')]))
    tech['routing_conductors'] = [v for v in tech.get('routing_conductors', cfg['conductors']) if v != ls['cap2m']]
    for row in ([ls['m4'], ls['via4'], ls['m5']], [ls['cap2m'], ls['via4'], ls['m5']]):
        if row not in cfg.setdefault('vias', []):
            cfg['vias'].append(row)
    blocker = dict(conductor=ls['m4'], cut=ls['via4'], mask=ls['cap2m'])
    if blocker not in cfg.setdefault('via_blockers', []):
        cfg['via_blockers'].append(blocker)


def geometry(tech, device, x=0, y=0):
    spec = specification(tech, device)
    ls = layers(tech)
    w, l = spec['dimensions_nm']['w'], spec['dimensions_nm']['l']
    if any(type(v) is not int or v % 5 or abs(v) > 100000000 for v in (x, y)):
        raise ValueError('Use a placement on the 5 nm grid within ±100 mm.')
    shapes, pins = [], []

    def box(role, key, a, b, width, height, net=''):
        shape = rect(ls[key], x+a, y+b, width, height, device['id'], net)
        shape.update(generated_device=device['id'], generator_role='passive:'+role)
        shapes.append(shape)

    top, bottom = device['nets']['c0'], device['nets']['c1']
    cx, cy = 5 * round(w/10), 5 * round(l/10)
    # 500 nm bottom surround; cap2m is the insulated top electrode. Via4
    # uses 800 nm square cuts with 800 nm spacing. Metal5 uses >=1600 nm
    # widths and 1700 nm separation, including the external bottom access.
    box('bottom', 'm4', -500, -500, w+4500, l+1000, bottom)
    box('dielectric_top', 'cap2m', 0, 0, w, l, top)
    box('top_access', 'm5', 0, 0, w, l, top)
    for ix, a in enumerate(range(800, w-799, 1600)):
        for iy, b in enumerate(range(800, l-799, 1600)):
            box(f'top_via_{ix}_{iy}', 'via4', a-400, b-400, 800, 800)
    # A single metal5 landing also needs 4 um2 area (met5.4).
    bx = w+2700
    box('bottom_access', 'm5', bx-1000, cy-1000, 2000, 2000, bottom)
    box('bottom_via', 'via4', bx-400, cy-400, 800, 800)
    for name, point in (('c0', [cx, cy]), ('c1', [bx, cy])):
        pins.append(dict(id=uid(), device_id=device['id'], pin=name, layer=ls['m5'], point=[x+point[0], y+point[1]]))
    from .sky130_devices import parallel_geometry
    return parallel_geometry(tech, device, dict(shapes=shapes, pins=pins,
        record=dict(device_id=device['id'], spec=spec, origin=[x, y])), spec.get('multiplicity', 1))
