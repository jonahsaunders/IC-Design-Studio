"""Design controls and measurements for the three specification challenges."""

from .model import scalar
from .student_cell_layout import PITCH, um_to_nm


METRICS = {
    'footprint_um': ('Cell width', 'µm'),
    'nand_fall_ps': ('B rising to Y falling', 'ps'),
    'clkq_rise_ps': ('Clock to Q rise', 'ps'),
    'clkq_fall_ps': ('Clock to Q fall', 'ps'),
    'drive_width_um': ('Combined Q driver width', 'µm'),
}
OPTIONS = {
    'inv-compact': [('pitch', 'Horizontal device pitch', 4.4, 7.0, ())],
    'nand-drive': [('stack', 'NMOS stack width', 1.0, 3.0, ('MN_A','MN_B'))],
    'dff-clock': [('q_n', 'Q NMOS width', 1.0, 2.8, ('MN_Q',)),
                  ('q_p', 'Q PMOS width', 2.0, 4.5, ('MP_Q',))],
}


def target_text(unit):
    return ' · '.join(f'{METRICS[key][0]} ≤ {maximum:g} {METRICS[key][1]}'
                      for key, maximum in unit.get('specs', {}).items())


def defaults(cell, key):
    parts = {d['name']:d for d in cell['devices']}
    return {name: scalar(parts[names[0]]['params']['w'])*1e6 if names
            else cell.get('student_cell_layout',{}).get('pitch',PITCH)/1000
            for name, _, _, _, names in OPTIONS[key]}


def apply_design(cell, key, values):
    options = OPTIONS[key]
    if set(values) != {name for name, *_ in options}:
        raise ValueError('Enter every design dimension for this challenge.')
    parts = {d['name']: d for d in cell['devices']}
    pitch = PITCH
    for name, label, minimum, maximum, names in options:
        number = um_to_nm(values[name])
        if not minimum*1000 <= number <= maximum*1000:
            raise ValueError(f'{label} must be between {minimum:g} and {maximum:g} µm.')
        if names:
            for device in names:
                parts[device]['params']['w'] = f'{number/1000:g}u'
        else:
            pitch = number
    return pitch


def propagation_delay(result, node, time_ns, output_edge):
    """Measure a single half-supply timing arc in a known applied test slot."""
    from .testbenches import crossings
    x, traces = result['x'], result['traces']
    window = dict(start=time_ns*1e-9, stop=(time_ns+10)*1e-9)
    triggers = crossings(x,traces[node],.9,'rising',**window)
    if len(triggers) != 1:
        return None
    edges = crossings(x,traces['out'],.9,output_edge,start=triggers[0],stop=window['stop'])
    return (edges[0]-triggers[0])*1e12 if len(edges)==1 else None


def measure(result, cell, geometry, unit):
    specs = unit.get('specs', {})
    if not specs:
        return []
    if unit['key'] == 'inv-compact':
        values = {'footprint_um': geometry['width_um']}
    elif unit['key'] == 'nand-drive':
        values = {'nand_fall_ps': propagation_delay(result, 'b', 36, 'falling')}
    else:
        drive = sum(scalar(d['params']['w'])*1e6 for d in cell['devices'] if d['name'] in ('MN_Q','MP_Q'))
        values = {'clkq_rise_ps': propagation_delay(result, 'clk', 120, 'rising'),
                  'clkq_fall_ps': propagation_delay(result, 'clk', 72, 'falling'), 'drive_width_um': drive}
    rows = []
    for name, maximum in specs.items():
        label, units = METRICS[name]
        value = values[name]
        rows.append(dict(metric=label, unit=units, maximum=maximum, value=value,
                         passed=value is not None and value <= maximum+1e-9))
    return rows
