"""An original four-bit SAR teaching design with editable analog and RTL cells."""
from .model import clone, device, example, uid, validate
from .symbol_io import default_symbol


def primitive(name, pins, suffix, x, y, parameters=None, definition=''):
    symbol = default_symbol(list(pins)); symbol['pin_order'] = list(pins)
    return device('SPICE', name, x, y, nets=pins, symbol=symbol,
                  native_spice=dict(version=1, type='device', label={'Ssample':'Sampling switch','Bcompare':'Comparator'}.get(name,name), parameters=parameters or {},
                                    tokens=[dict(kind='instance'), dict(kind='literal', value=' '),
                                            dict(kind='terminals'), dict(kind='literal', value=' '+suffix)],
                                    definition=definition))


def sar_project():
    from .getting_started import resource_root
    p = example('empty'); p['name'] = 'Four-bit SAR ADC'; p['spice'] = dict(version=1, assets={})
    analog = p['cells'][0]; analog['name'] = 'sar_analog'
    # Parallel weighted resistors plus the terminating resistor give
    # Vdac = 1.8 * (8*b3 + 4*b2 + 2*b1 + b0)/16; Rout = 5 kohm.
    analog['devices'] = [device('R', 'Rbit'+str(bit), 420+bit*170, 300,
                                value=str(80000/(2**bit)), nets={'p':'d'+str(bit), 'n':'vdac'})
                          for bit in range(4)]
    analog['devices'] += [device('R', 'Rterm', 1100, 300, value='80k', nets={'p':'vdac', 'n':'0'}),
                          device('C', 'Cdac', 1100, 500, value='2p', nets={'p':'vdac', 'n':'0'}),
                          primitive('Ssample', {'in':'vin', 'out':'held', 'control':'track', 'ground':'0'},
                                    'sample_switch', 160, 100,
                                    definition='.model sample_switch SW(Ron=100 Roff=1e12 Vt=0.9 Vh=0)'),
                          device('C', 'Chold', 370, 100, value='20p', nets={'p':'held', 'n':'0'}),
                          primitive('Bcompare', {'positive':'held', 'negative':'vdac', 'out':'cmp_raw', 'ground':'0'},
                                    'V=0.9*(1+tanh((V(held)-V(vdac)-{offset})*10000))', 650, 100,
                                    parameters={'offset':'0'}),
                          device('R', 'Rcompare', 870, 100, value='1k', nets={'p':'cmp_raw', 'n':'cmp'}),
                          device('C', 'Ccompare', 1100, 100, value='1p', nets={'p':'cmp', 'n':'0'})]
    # Make the comparator offset a native editable parameter in its expression.
    b = next(d for d in analog['devices'] if d['name'] == 'Bcompare')
    b['native_spice']['tokens'] = [dict(kind='instance'), dict(kind='literal', value=' '),
                                 dict(kind='terminal', value='out'), dict(kind='literal', value=' '),
                                 dict(kind='terminal', value='ground'), dict(kind='literal', value=' V=0.9*(1+tanh((V('),
                                 dict(kind='terminal', value='positive'), dict(kind='literal', value=')-V('),
                                 dict(kind='terminal', value='negative'), dict(kind='literal', value=')-('),
                                 dict(kind='parameter', value='offset'), dict(kind='literal', value='))*10000))')]
    rtl = dict(id=uid(), name='sar_controller', ports=[], devices=[], shapes=[],
               digital=dict(version=1, top='sar_controller', testbench='', include_dirs=['.'],
                            defines={}, waveform='sar.vcd', timeout=60, files=[
                                dict(path='sar_controller.sv', role='rtl',
                                     text=(resource_root()/'examples/sar-adc/sar_controller.sv').read_text())]))
    p['cells'].append(rtl); p['digital_cell'] = rtl['id']
    p['mixed_signal'] = dict(version=1, analog_cell=analog['id'], digital_cell=rtl['id'],
                            clock='clk', period=1e-6, rise=1e-9, max_step=1e-8, cycles=10, timeout=180,
                            inputs=[dict(port='reset', width=1, values=[1,1,0,0,0,0,0,0,0,0]),
                                    dict(port='start', width=1, values=[0,0,1,0,0,0,0,0,0,0]),
                                    dict(port='cmp', width=1, node='cmp', low=.6, high=1.2,
                                         sample_when=dict(port='compare', value=1))],
                            outputs=[dict(port='dac', width=4, nodes=['d0','d1','d2','d3'], low=0., high=1.8, initial=0),
                                     dict(port='code', width=4),
                                     dict(port='track', width=1, nodes=['track'], low=0., high=1.8, initial=1),
                                     dict(port='busy', width=1), dict(port='done', width=1), dict(port='compare', width=1)],
                            stimuli={'vin':[[0., .93]]}, probes=['vin','held','vdac','cmp','track'],
                            verification=dict(kind='sar4', reference=1.8))
    return validate(p)


def conversion_report(result, expected=None):
    """Check protocol and code independently of the implementation's decisions."""
    samples = result['mixed_signal']['samples']; done = [s for s in samples if s['outputs']['done']]
    checks = [dict(name='One completion pulse', passed=len(done)==1),
              dict(name='Four comparator decisions', passed=sum(s['sampled'].get('cmp',False) for s in samples)==4)]
    code = done[0]['outputs']['code'] if len(done)==1 else None
    checks += [dict(name='Completion at edge 7', passed=len(done)==1 and done[0]['edge']==7),
               dict(name='Idle after completion', passed=not samples[-1]['outputs']['busy']),
               dict(name='Code held after completion', passed=code is not None and all(s['outputs']['code']==code for s in samples if s['edge']>=7))]
    if expected is not None: checks.append(dict(name='Expected conversion code', passed=code==expected, expected=expected, actual=code))
    starts = [s for s in samples if s['inputs'].get('start')]
    latency = done[0]['time']-starts[0]['time'] if len(done)==1 and starts else None
    return dict(status='PASS' if all(c['passed'] for c in checks) else 'FAIL', code=code,
                conversion_seconds=latency, checks=checks)
