"""One source-defined IHP square TM2 pad attached to an existing cell port.

This is physical metal/marker/opening geometry, with no electrical pad model.
The public PCell comments "0 pins" yet sets pin#=1 and ignore=TRUE; its selected
branch emits no pin. The explicit port anchor is an application adaptation.
No substrate terminal, capacitance or rated operating limit is added.
"""
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from .layout import rect
from .model import clone, uid, validate

SOURCE_LOCK = '0811e348eb273f5827ff3f7ffb5fa32a7380f8ba53189a4c3004816c04661895'
SOURCE = Path(__file__).resolve().parent/'assets/qualification/ihp-bondpad'
RECIPE = 'ihp-square-tm2-unstacked-v1'
MASKS = {'metal': (134, 0), 'opening': (9, 0), 'marker': (41, 0), 'label': (134, 2)}
ENCLOSURE_NM = 2100
SCOPE = ('Square TM2 bondpad, unstacked, no fill, filler exclusion or flip-chip; '
         'one existing cell-port anchor. Geometry only; electrical pad binding, '
         'full process DRC, chip context and installed acceptance remain separate.')


def verify_sources(root=SOURCE):
    root = Path(root)
    raw = (root/'source-lock.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_LOCK:
        raise ValueError('Changed IHP bondpad source lock.')
    lock = json.loads(raw)
    for name, row in lock['files'].items():
        data = (root/name).read_bytes()
        blob = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if (len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']
                or blob != row['git_blob_sha1']):
            raise ValueError('Changed IHP bondpad source: '+name)
    return lock


def layers(technology):
    if technology.get('package_lock', {}).get('id') != 'ihp-sg13g2':
        raise ValueError('Link the IHP SG13G2 process before generating a bondpad.')
    table = {}
    for key, pair in MASKS.items():
        choices = [l['name'] for l in technology['layers'] if (l['gds'], l['datatype']) == pair]
        if len(choices) != 1:
            raise ValueError('Require one IHP bondpad layer mapping: '+key)
        table[key] = choices[0]
    if technology.get('grid') != 5 or technology.get('dbu_um') != .001:
        raise ValueError('The IHP bondpad recipe requires the 5 nm grid and 1 nm database.')
    return table


def specification(values=None):
    values = {} if values is None else values
    allowed = {'diameter_nm', 'hwquota', 'x_nm', 'y_nm', 'rotation'}
    if not isinstance(values, dict) or set(values)-allowed:
        raise ValueError('Unsupported bondpad class or parameter; choose a square unstacked TM2 pad.')
    result = dict(diameter_nm=80000, hwquota=1, x_nm=0, y_nm=0, rotation=0)
    result.update(values)
    diameter = result['diameter_nm']
    if type(diameter) is not int or diameter <= 0 or diameter % 10:
        raise ValueError('Use a positive diameter in integer nanometres on the 10 nm diameter grid.')
    if type(result['rotation']) is not int or result['rotation'] not in (0, 90, 180, 270):
        raise ValueError('Use a right-angle bondpad rotation.')
    for key in ('x_nm', 'y_nm'):
        if type(result[key]) is not int or result[key] % 5:
            raise ValueError('Place the bondpad center on the 5 nm grid.')
    quota = result['hwquota']
    if isinstance(quota, bool) or not isinstance(quota, (str, int, float)):
        raise ValueError('Use a finite positive height-width quota.')
    try:
        quota = Fraction(str(quota))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError('Use a finite positive height-width quota.') from exc
    if quota <= 0:
        raise ValueError('Use a finite positive height-width quota.')
    rx = Fraction(diameter, 2) / max(1, quota)
    ry = Fraction(diameter, 2) * min(1, quota)
    if quota != 1 and min(rx, ry)*2 < 10000:
        raise ValueError('This quota invokes the public PCell 10 um fallback; choose explicit dimensions.')
    if any(r.denominator != 1 or r.numerator % 5 for r in (rx, ry)):
        raise ValueError('Use exact on-grid radii; the application does not silently round the public PCell geometry.')
    rx, ry = int(rx), int(ry)
    if min(rx, ry) <= ENCLOSURE_NM:
        raise ValueError('The 2.1 um enclosure requires a positive passivation opening.')
    # Match the selected public square branch without applying a model validity
    # claim to the PCell's parameter domain or its 10 um aspect-ratio fallback.
    if any(abs(center)+max(rx, ry) > 2**31-1 for center in (result['x_nm'], result['y_nm'])):
        raise ValueError('Bondpad coordinates exceed the signed 32-bit stream range.')
    result['hwquota'] = str(quota)
    result['radii_nm'] = [rx, ry]
    return result


def geometry(technology, values=None):
    verify_sources(); ls = layers(technology); spec = specification(values)
    rx, ry = spec['radii_nm']; x, y = spec['x_nm'], spec['y_nm']
    if spec['rotation'] in (90, 270):
        rx, ry = ry, rx
    shapes = []
    for role, inset in (('metal', 0), ('marker', 0), ('opening', ENCLOSURE_NM)):
        shape = rect(ls[role], x-rx+inset, y-ry+inset, 2*(rx-inset), 2*(ry-inset))
        shape['bondpad_role'] = role; shapes.append(shape)
    return dict(shapes=shapes, specification=spec,
                terminals=[dict(name='pad', layer=ls['metal'], point=[x, y])],
                source_lock_sha256=SOURCE_LOCK, recipe=RECIPE, scope=SCOPE,
                qualified=False, electrical_model=False)


def install(project, cell_id, port, values=None):
    """Atomically attach physical pad metal to one already declared cell port.

    The caller uses its normal History/review transaction. No schematic device,
    model include or new terminal is created. Existing physical port assignments
    must be removed explicitly before installing a different pad at that port.
    """
    from .native_vectors import ports
    from .physical_cells import assign_port
    q = clone(project); cell = next(c for c in q['cells'] if c['id'] == cell_id)
    if port not in ports(cell['ports']):
        raise ValueError('Choose an existing explicit scalar cell port for the bondpad.')
    if any(p['name'] == port for p in cell.get('layout_ports', [])):
        raise ValueError('This cell port already has a physical anchor.')
    data = geometry(q['pdk'], values); ident = uid()
    for shape in data['shapes']:
        shape['bondpad_id'] = ident
        if shape['bondpad_role'] == 'metal':
            shape['net'] = port
    cell['shapes'].extend(data['shapes'])
    anchor = data['terminals'][0]
    assign_port(q, cell_id, port, anchor['layer'], anchor['point'])
    record = dict(id=ident, recipe=RECIPE, specification=data['specification'],
                  shape_ids=[s['id'] for s in data['shapes']],
                  terminals=[dict(name=port, layer=anchor['layer'], point=clone(anchor['point']))],
                  source_lock_sha256=SOURCE_LOCK, electrical_model=False)
    cell.setdefault('ihp_bondpads', []).append(record)
    validate(q); project.clear(); project.update(q)
    return clone(record)
