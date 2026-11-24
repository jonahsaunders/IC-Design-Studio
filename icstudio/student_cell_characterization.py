"""Fixtures and waveform measurements for the standard-cell characterization labs."""

from bisect import bisect_left, bisect_right

from .analog_diagnostics import integrate
from .model import device, scalar
from .testbenches import crossings


SUPPLY = 1.8
LOAD_DESCRIPTION = {
    'buffer-fo4': 'four identical SKY130 inverter inputs',
    'mux-glitch': 'a 10 fF load and a select-to-output coupling stress fixture',
}
REFERENCE_KEYS = {'nor-rise', 'nand-input', 'xor-energy'}
SWEEP_PS = (-250, -100, 0, 25, 50, 75, 100, 150, 200, 300, 500, 800)
CLOCK_NS = 12
SETTLED_PS = 1500


def pulse(name, net, delay, period, duty):
    source = dict(type='pulse', low='0', high=str(SUPPLY), delay=f'{delay:.9g}n',
                  period=f'{period:.9g}n', duty=f'{duty:.12g}', ac='0')
    return device('V', name, nets={'p': net, 'n': '0'}, source=source)


def extra_sources(key):
    if key == 'mux-glitch':
        return [device('R', 'RSEL', x=330, y=260, rotation=270, value='6k', nets={'p': 's_drive', 'n': 's'}),
                device('C', 'CSEL', x=420, y=660, value='15f', nets={'p': 's', 'n': '0'}),
                device('C', 'CSTRESS', x=830, y=660, value='8f', nets={'p': 's', 'n': 'out'})]
    return []


def fo4_devices(inv_id):
    return [device('X', f'XLOAD{i}', x=920+180*((i-1)%2), y=180+180*((i-1)//2), cell=inv_id,
                   nets={'A': 'out', 'Y': f'load_out{i}', 'VPWR': 'vdd', 'VGND': '0'})
            for i in range(1, 5)]


def networks(key, inverter, transmission):
    if key == 'buffer':
        return inverter('IN', 'A', 'MID') + inverter('OUT', 'MID', 'Y')
    if key == 'xor2':
        return (inverter('BINV', 'B', 'B_B') + inverter('SEL', 'A', 'A_B')
                + transmission('L', 'A_B', 'A', 'B', 'M')
                + transmission('H', 'A', 'A_B', 'B_B', 'M')
                + inverter('BUF', 'M', 'Y_B') + inverter('OUT', 'Y_B', 'Y'))
    raise ValueError('Unknown standard cell.')


def sweep_cases():
    for kind in ('Setup', 'Hold'):
        for index, offset in enumerate((*SWEEP_PS, SETTLED_PS)):
            yield kind, offset, f'{kind.lower()}{index}'


def add_sweep(cell, fixture):
    """Exercise isolated copies simultaneously with the same load, clock and supply."""
    test = pulse('V_SWEEP_CLK', 'sweep_clk', 2, 10, .4)
    fixture['devices'].append(test)
    for kind, offset, tag in sweep_cases():
        delay = CLOCK_NS - offset/1000 if kind == 'Setup' else 5
        width = 5 if kind == 'Setup' else CLOCK_NS + offset/1000 - delay
        fixture['devices'] += [
            pulse('V_'+tag, 'd_'+tag, delay, 40, width/40),
            device('C', 'C_'+tag, value='10f', nets={'p': 'q_'+tag, 'n': '0'}),
            device('X', 'X_'+tag, cell=cell['id'], nets={
                'D': 'd_'+tag, 'CLK': 'sweep_clk', 'Q': 'q_'+tag, 'VPWR': 'vdd', 'VGND': '0'}),
        ]
    if 'wires' in fixture:
        # The generated characterization bench uses explicit fixture nets.
        fixture.pop('wires')


def clip(times, values, start, stop):
    if not times or len(times) != len(values) or start >= stop or start < times[0] or stop > times[-1]:
        raise ValueError('The transient does not cover the required measurement interval.')

    def at(t, i):
        if i == len(times)-1 or times[i] == t:
            return values[i]
        return values[i] + (values[i+1]-values[i])*(t-times[i])/(times[i+1]-times[i])

    left, right = bisect_right(times, start), bisect_left(times, stop)
    return ([start, *times[left:right], stop],
            [at(start, left-1), *values[left:right], at(stop, right-1)])


def charge(result, source, start_ns, stop_ns):
    currents = result.get('currents', {})
    current = currents.get(source) or currents.get(source.lower())
    if current is None:
        raise ValueError(f'The transient did not capture branch current for {source}.')
    return -integrate(*clip(result['x'], current, start_ns*1e-9, stop_ns*1e-9))


def arc(result, node, time_ns, output_edge, input_edge='rising', output='out', span=6):
    x, traces = result['x'], result['traces']
    start = (time_ns-.025)*1e-9
    stop = (time_ns+span)*1e-9
    trigger = crossings(x, traces[node], SUPPLY/2, input_edge, start=start, stop=stop)
    if len(trigger) != 1:
        return None
    edges = crossings(x, traces[output], SUPPLY/2, output_edge, start=trigger[0], stop=stop)
    return (edges[0]-trigger[0])*1e12 if len(edges)==1 else None


def swing(result, start_ns, stop_ns, expected):
    _, y = clip(result['x'], result['traces']['out'], start_ns*1e-9, stop_ns*1e-9)
    return max(abs(expected-v) for v in y)


def worst(arcs):
    return max(arcs) if all(t is not None for t in arcs) else None


def observed(result, key):
    if key == 'nor-rise':
        return {'nor_rise_ps': arc(result,'b',24,'rising','falling')}
    if key == 'nand-input':
        return {'input_cap_ff': charge(result,'V_B',35.975,39)/SUPPLY*1e15,
                'nand_fall_ps': arc(result,'b',36,'falling')}
    if key == 'mux-glitch':
        return {'glitch_low_v': swing(result,11.975,22,0),
                'glitch_high_v': swing(result,83.975,94,SUPPLY)}
    if key == 'buffer-fo4':
        return {'rise_ps': arc(result,'a',12,'rising'),
                'fall_ps': arc(result,'a',24,'falling','falling')}
    if key == 'xor-energy':
        points = [('b',12,'rising','rising'),('a',24,'falling','rising'),
                  ('b',36,'rising','falling'),('a',48,'falling','falling')]
        return {'energy_fj': charge(result,'VDD',2,50)*SUPPLY*1e15/4,
                'worst_delay_ps': worst([arc(result,*args) for args in points])}
    raise ValueError('Unknown characterization measurement.')


def sweep(result):
    """Score Q propagation at half supply and the held logic level at 15 ns."""
    reference = {}
    records = []
    for kind, offset, tag in sweep_cases():
        q = 'q_'+tag
        delay = arc(result, 'sweep_clk', CLOCK_NS, 'rising', output=q, span=3)
        _, held = clip(result['x'], result['traces'][q], 13e-9, 15e-9)
        captured = min(held) >= .8*SUPPLY
        if offset == SETTLED_PS:
            reference[kind] = delay if captured and delay is not None and delay > 0 else None
        records.append(dict(kind=kind, offset_ps=offset, delay_ps=delay, captured=captured))
    for row in records:
        nominal = reference[row['kind']]
        delay = row['delay_ps']
        row['passed'] = row['captured'] and delay is not None and nominal is not None and delay <= 1.1*nominal
    return records


def timing_bracket(rows, kind):
    """Return adjacent failing and stable passing offsets, walking from settled data."""
    passing = None
    for row in reversed([r for r in rows if r['kind']==kind]):
        offset = row['offset_ps']
        if not row['passed']:
            return (offset,passing) if passing is not None else None
        passing = offset
    return None


def timing_limit(rows, kind):
    bracket = timing_bracket(rows,kind)
    return bracket[1] if bracket else None


def total_width(cell):
    return sum(scalar(d['params']['w'])*1e6 for d in cell['devices'])

def wave_from_raw(path):
    from .engines import parse_raw
    from .operating_data import extras
    variables, rows, complex_data = parse_raw(path)
    traces = {name[2:-1]:[row[i] for row in rows] for i,name in enumerate(variables)
              if name.startswith('v(') and name.endswith(')')}
    currents, _, _ = extras(variables, rows, complex_data)
    return dict(x=[row[0] for row in rows], traces=traces, currents=currents)


def reference_from_raw(path,key):
    return observed(wave_from_raw(path),key)
