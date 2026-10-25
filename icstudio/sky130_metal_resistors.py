"""Editable straight SKY130 LI and M1--M4 resistors with explicit markers.

This is a bounded geometry recipe, not a device operating-envelope claim.
The marker defines the primitive W/L; unmarked ends remain routable terminals.
Every completed layout still requires native process DRC and extracted LVS.
"""
import math

from .catalog import binding_for, parameter_values
from .layout import rect
from .model import clone, uid

LAYERS = {'l1': 67, 'm1': 68, 'm2': 69, 'm3': 70, 'm4': 71}
MODELS = {'sky130_fd_pr__res_generic_'+key: key for key in LAYERS}


def supported(tech, device):
    binding = binding_for(tech, device)
    return bool(tech.get('package_lock', {}).get('id') == 'sky130A'
                and binding and binding.get('model') in MODELS)


def layers(tech, key):
    table = {(v['gds'], v['datatype']): v['name'] for v in tech['layers']}
    gds = LAYERS[key]
    if not {(gds, 20), (gds, 13)} <= table.keys():
        raise ValueError('The selected resistor needs its drawing and resistor-marker layers.')
    return dict(conductor=table[gds, 20], marker=table[gds, 13])


def specification(tech, device):
    binding = binding_for(tech, device)
    if (not supported(tech, device) or device['kind'] != 'PDK'
            or binding.get('prefix') != 'R' or binding.get('pin_order') != ['m', 'p']
            or set(device['nets']) != {'m', 'p'}
            or binding.get('emit_parameters') != {'w': 'w', 'l': 'l', 'm': 'mult'}
            or binding.get('parameter_scale') != {'w': 1e6, 'l': 1e6}):
        raise ValueError('Use the reviewed SKY130 LI/metal resistor model, terminals and micrometre parameters.')
    key = MODELS[binding['model']]
    layers(tech, key)
    values = parameter_values(binding, device)
    if values['mult'] != 1:
        raise ValueError('The straight LI/metal layout recipe supports one resistor; parallel arrays require a separate layout.')
    size = {}
    for name in ('w', 'l'):
        nm = values[name]*1000
        if (not math.isfinite(nm) or abs(nm-round(nm)) > 1e-6
                or round(nm) % 5 or not 500 <= nm <= 10000):
            raise ValueError(name.upper()+': use 0.5–10 µm on the 5 nm grid for this straight resistor recipe.')
        size[name] = round(nm)
    return dict(api=1, recipe='metal_resistor', model=binding['model'], layer=key,
                model_ref=clone(device['model_ref']), kind=device['kind'], values=values,
                dimensions_nm=size, nets=clone(device['nets']))


def configure_connectivity(tech):
    table = {(v['gds'], v['datatype']): v['name'] for v in tech['layers']}
    cfg = tech.setdefault('connectivity', {})
    for gds in LAYERS.values():
        if not {(gds, 20), (gds, 13)} <= table.keys():
            continue
        conductor, marker = table[gds, 20], table[gds, 13]
        if conductor not in cfg.setdefault('conductors', []):
            cfg['conductors'].append(conductor)
        rule = dict(conductor=conductor, mask=marker)
        if rule not in cfg.setdefault('resistive_masks', []):
            cfg['resistive_masks'].append(rule)


def geometry(tech, device, x=0, y=0):
    spec = specification(tech, device)
    if any(type(v) is not int or v % 5 or abs(v) > 100000000 for v in (x, y)):
        raise ValueError('Use a placement on the 5 nm grid within ±100 mm.')
    ls = layers(tech, spec['layer'])
    w, l = spec['dimensions_nm']['w'], spec['dimensions_nm']['l']
    # A 0.5 um unmarked landing at each end leaves room for routing on the
    # same layer. No via/contact or exemption marker is implied by this recipe.
    end = 500
    shapes = []
    for role, layer, px, py, width, height in (
            ('conductor', ls['conductor'], 0, -end, w, l+2*end),
            ('marker', ls['marker'], 0, 0, w, l)):
        shape = rect(layer, x+px, y+py, width, height, device['id'])
        shape.update(generated_device=device['id'], generator_role='metal_resistor:'+role)
        shapes.append(shape)
    cx = 5*(w//10)
    pins = [dict(id=uid(), device_id=device['id'], pin=name, layer=ls['conductor'],
                 point=[x+cx, y+py]) for name, py in (('m', -end//2), ('p', l+end//2))]
    return dict(shapes=shapes, pins=pins,
                record=dict(device_id=device['id'], spec=spec, origin=[x, y]))
