"""Layout lesson built on the existing RC and geometry teaching fixtures."""

import math

from .model import clone, load_project, uid, validate
from .student_design_labs import layout_lab, check_layout

BANDWIDTH = 'Bandwidth'
COUPONS = {'via': 'layout-via', 'matching': 'layout-centroid'}
EXTRACTION_STEPS = frozenset(('baseline', 'optimize'))


def project():
    from .getting_started import resource_root

    p = load_project(resource_root() / 'examples/distributed-rc-specifications.icproj')
    p.update(id=uid(), revision=0, name='Student · Why layout choices matter')
    route = p['cells'][0]
    route['name'] = 'routing_bandwidth'
    _route(route)['width'] = 200
    p['analysis'].update(type='ac', start='100Meg', end='1e12', points=201)
    route['specifications'] = [dict(name=BANDWIDTH, unit='Hz', min='12.5G',
        expression='crossing(abs(V("vout")/V("vin")),at(abs(V("vout")/V("vin")),1e8)/sqrt(2),-1)')]
    for step, starter in COUPONS.items():
        coupon = layout_lab(starter)['cells'][0]
        coupon['name'] = step + '_coupon'
        for shape in coupon['shapes']:
            shape['id'] = step + '_' + shape['id']
        p['cells'].append(coupon)
    return validate(p)


def focus(project, step):
    if step in COUPONS:
        coupon = next((c for c in project['cells'] if c['name'] == step + '_coupon'), None)
        if coupon is None:
            raise ValueError('Restore the lesson’s ' + step + ' layout cell.')
        return coupon['id']
    return project['top']


def _route(cell):
    routes = [shape for shape in cell['shapes'] if shape['kind'] == 'path' and shape.get('net') == 'vout']
    if len(routes) != 1:
        raise ValueError('Keep the single Manhattan vout route in the bandwidth lab.')
    return routes[0]


def _geometry(project):
    from .layout import drc
    from .physical import connectivity

    cid = project['top']
    issues = drc(project, cid)
    if issues:
        raise ValueError('Resolve geometry findings first. ' + issues[0]['message'])
    issues = connectivity(project, cid)['issues']
    if issues:
        raise ValueError('Resolve physical connectivity findings. ' + issues[0]['message'])


def prepare(project, step):
    from .run_environment import stamp

    if step not in EXTRACTION_STEPS:
        raise ValueError('Choose a route comparison step before running.')
    _geometry(project)
    job = dict(project=clone(project), cell=project['top'], engine='builtin',
               settings=dict(type='rc_compare', analysis=clone(project['analysis'])))
    job['environment'] = stamp(job)
    return job


def check_geometry(project, step):
    if step == 'connectivity':
        _geometry(project)
        return dict(scope='Generic geometry and linked-terminal connectivity')
    cid = focus(project, step)
    coupon = clone(next(cell for cell in project['cells'] if cell['id'] == cid))
    for shape in coupon['shapes']:
        shape['id'] = shape['id'].removeprefix(step + '_')
    return check_layout({**project, 'cells': [coupon], 'top': cid}, COUPONS[step])


def check_run(project, result, step):
    row = next((r for r in result.get('rc_comparison', []) if r['name'] == BANDWIDTH), None)
    if result.get('settings', {}).get('type') != 'rc_compare' or not row:
        raise ValueError('Run the before-and-after interconnect comparison for this layout.')
    before, after = row['before'].get('value'), row['after'].get('value')
    if not before or not after or not 15.8e9 < before < 16.1e9:
        raise ValueError('Keep the original 1 kΩ / 10 fF circuit and run the saved AC analysis.')
    cell = next(cell for cell in project['cells'] if cell['id'] == project['top'])
    route = _route(cell)
    width = route['width']
    ext = result['extraction']
    resistance = sum(r['value'] for r in ext['resistors'] if r['shape'] == route['id'])
    added_cap = sum(c['value'] for c in ext['capacitors'])
    if min(resistance, added_cap) <= 0:
        raise ValueError('Use the recorded distributed resistance and capacitance model.')
    if step == 'baseline' and (width != 200 or not math.isclose(resistance, 226.65, rel_tol=.01) or after >= 12.5e9):
        raise ValueError('Use the original 0.20 µm route to capture the modeled bandwidth failure.')
    if step == 'optimize' and (width <= 200 or resistance >= 226.65 or after < 12.5e9):
        raise ValueError(f'Modeled bandwidth is {after/1e9:.3g} GHz. Adjust route width to meet 12.5 GHz and run again.')
    return dict(before_Hz=before, after_Hz=after, route_ohm=resistance, added_F=added_cap, width_nm=width)
