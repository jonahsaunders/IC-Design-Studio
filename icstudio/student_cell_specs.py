"""Design controls and measurements for standard-cell specification challenges."""

from .model import scalar
from .student_cell_layout import PITCH, um_to_nm


METRICS = {
    'nor_rise_ps': ('B falling to Y rising', 'ps'),
    'input_cap_ff': ('Effective B input capacitance', 'fF'),
    'glitch_low_v': ('Peak excursion at logic 0', 'V'),
    'glitch_high_v': ('Peak excursion at logic 1', 'V'),
    'rise_ps': ('A to Y rise', 'ps'),
    'fall_ps': ('A to Y fall', 'ps'),
    'total_width_um': ('Total buffer width', 'µm'),
    'energy_fj': ('Supply energy per transition', 'fJ'),
    'worst_delay_ps': ('Worst of four XOR arcs', 'ps'),
    'setup_ps': ('Bracketed setup offset', 'ps'),
    'hold_ps': ('Bracketed hold offset', 'ps'),
    'footprint_um': ('Cell width', 'µm'),
    'nand_fall_ps': ('B rising to Y falling', 'ps'),
    'clkq_rise_ps': ('Clock to Q rise', 'ps'),
    'clkq_fall_ps': ('Clock to Q fall', 'ps'),
    'drive_width_um': ('Combined Q driver width', 'µm'),
}
OPTIONS = {
    'nor-rise': [('stack', 'PMOS stack width', 1, 4.5, ('MP_A', 'MP_B'))],
    'nand-input': [('b_n', 'B NMOS width', .5, 2.8, ('MN_B',)),
                   ('b_p', 'B PMOS width', .5, 4.5, ('MP_B',))],
    'mux-glitch': [('out_n', 'Output NMOS width', .5, 3.5, ('MN_BUF2',)),
                   ('out_p', 'Output PMOS width', .5, 4.5, ('MP_BUF2',))],
    'buffer-fo4': [('first_n', 'First-stage NMOS width', .5, 2.5, ('MN_IN',)),
                   ('first_p', 'First-stage PMOS width', .5, 4.5, ('MP_IN',)),
                   ('out_n', 'Output NMOS width', .5, 3.5, ('MN_OUT',)),
                   ('out_p', 'Output PMOS width', .5, 4.5, ('MP_OUT',))],
    'xor-energy': [('logic_n', 'Internal NMOS width', .5, 2.8, ('MN_BINV', 'MN_SEL', 'MN_L', 'MN_H', 'MN_BUF')),
                   ('logic_p', 'Internal PMOS width', .5, 4.5, ('MP_BINV', 'MP_SEL', 'MP_L', 'MP_H', 'MP_BUF')),
                   ('out_n', 'Output NMOS width', .5, 2.8, ('MN_OUT',)),
                   ('out_p', 'Output PMOS width', .5, 4.5, ('MP_OUT',))],
    'dff-aperture': [('in_n', 'Master-input NMOS width', .5, 2.8, ('MN_M_IN',)),
                     ('in_p', 'Master-input PMOS width', .5, 4.5, ('MP_M_IN',))],
    'inv-compact': [('pitch', 'Horizontal device pitch', 4.4, 7.0, ())],
    'nand-drive': [('stack', 'NMOS stack width', 1.0, 3.0, ('MN_A','MN_B'))],
    'dff-clock': [('q_n', 'Q NMOS width', 1.0, 2.8, ('MN_Q',)),
                  ('q_p', 'Q PMOS width', 2.0, 4.5, ('MP_Q',))],
}


def target_text(unit):
    labels = []
    for key, target in unit.get('specs', {}).items():
        title, unit_name = METRICS[key]
        limit = f'{target["relative"]*100:g}% of starter' if isinstance(target,dict) else f'{target:g} {unit_name}'
        labels.append(f'{title} ≤ {limit}')
    return ' · '.join(labels)


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


def measure(result, cell, geometry, unit, reference=None, sweep_rows=None):
    specs = unit.get('specs', {})
    if not specs:
        return []
    if unit['key'] == 'inv-compact':
        values = {'footprint_um': geometry['width_um']}
    elif unit['key'] == 'nand-drive':
        values = {'nand_fall_ps': propagation_delay(result, 'b', 36, 'falling')}
    elif unit['key'] == 'dff-clock':
        drive = sum(scalar(d['params']['w'])*1e6 for d in cell['devices'] if d['name'] in ('MN_Q','MP_Q'))
        values = {'clkq_rise_ps': propagation_delay(result, 'clk', 120, 'rising'),
                  'clkq_fall_ps': propagation_delay(result, 'clk', 72, 'falling'), 'drive_width_um': drive}
    elif unit['key'] == 'dff-aperture':
        from .student_cell_characterization import timing_limit
        values = {name+'_ps': timing_limit(sweep_rows,kind) for name,kind in (('setup','Setup'),('hold','Hold'))}
    else:
        from .student_cell_characterization import observed, total_width
        values = observed(result,unit['key'])
        values.update(footprint_um=geometry['width_um'], total_width_um=total_width(cell))
    rows = []
    for name, threshold in specs.items():
        label, units = METRICS[name]
        value = values[name]
        row = dict(metric=label, unit=units, value=value)
        maximum = threshold
        if isinstance(threshold,dict):
            baseline = reference[name]
            if baseline is None or baseline <= 0:
                raise ValueError('The reference stimulus did not produce a valid '+label+' measurement.')
            maximum = threshold['relative']*baseline
            row['reference'] = baseline
        row.update(maximum=maximum, passed=value is not None and value <= maximum+1e-9)
        rows.append(row)
    return rows
