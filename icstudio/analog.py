"""Editable analog schematics and fixtures using explicitly linked PDK models."""
from .model import example, clone, uid, device, validate
from .catalog import link_technology, create_device
from .testbenches import create


PROCESSES = {
    'sky130A': {'model': 'sky130_fd_pr__nfet_01v8', 'supply': 1.8, 'common_mode': .9,
               'outputs': [.9, 1.2, 1.5]},
    'gf180mcuC': {'model': 'nfet_03v3', 'supply': 3.3, 'common_mode': 1.65,
                 'outputs': [1.2, 1.8, 2.4]},
}


def reference(technology, kind='current_mirror'):
    if kind not in ('current_mirror', 'differential_pair'):
        raise ValueError('Choose current_mirror or differential_pair.')
    process = PROCESSES.get(technology.get('package_lock', {}).get('id'))
    if process is None: raise ValueError('Analog recipes require linked SKY130A 1.8 V or GF180MCU C 3.3 V models.')
    matches = [(k, b) for k, b in technology.get('simulation', {}).get('catalog', {}).items()
               if not b.get('unavailable') and b.get('model') == process['model']
               and b.get('pin_order') == ['d', 'g', 's', 'b']
               and all(b.get('emit_parameters', {}).get(key) == key for key in ('w', 'l'))]
    if not matches: raise ValueError('The standard four-terminal NMOS model is absent from this PDK catalog.')
    # Prefer a visible four-terminal symbol over one with an exposed hidden body.
    key = min(matches, key=lambda item: (bool(item[1].get('notes')), item[0]))[0]
    p = example('empty')
    link_technology(p, technology)
    p['name'] = ('Current mirror' if kind == 'current_mirror' else 'Differential pair') + ' · ' + technology['name']
    top = p['cells'][0]
    top['name'] = kind + '_fixture'
    c = {'id': uid(), 'name': kind, 'ports': [], 'devices': [], 'shapes': []}
    p['cells'].append(c)
    def mos(name, x, nets):
        d = create_device(p['pdk'], key, name, x, 240)
        d['params'].update(w='10u', l='1u')
        d['nets'] = nets
        c['devices'].append(d)
    if kind == 'current_mirror':
        c['ports'] = ['IREF', 'OUT', 'VSS']
        mos('MREF', 240, {'d': 'IREF', 'g': 'IREF', 's': 'VSS', 'b': 'VSS'})
        mos('MOUT', 500, {'d': 'OUT', 'g': 'IREF', 's': 'VSS', 'b': 'VSS'})
        top['devices'] = [
            device('I', 'IREF', 140, 180, value='50u', nets={'p': '0', 'n': 'ref'}),
            device('V', 'VOUT', 680, 180, value=str(process['outputs'][1]), nets={'p': 'force', 'n': '0'}),
            device('V', 'VSENSE', 560, 180, value='0', nets={'p': 'force', 'n': 'out'}),
            device('X', 'XDUT', 360, 320, cell=c['id'], nets={'IREF': 'ref', 'OUT': 'out', 'VSS': '0'})]
        measures = [{'name': 'output_current', 'kind': 'current', 'source': 'VSENSE', 'min': '40u', 'max': '60u'},
                    {'name': 'bias_voltage', 'kind': 'voltage', 'node': 'ref', 'min': '0', 'max': str(process['supply'])}]
        study = {'kind': 'sweep', 'target': 'VOUT.value', 'values': process['outputs']}
        dc = {'source': 'VOUT', 'dc_start': '0', 'dc_stop': str(process['supply']), 'dc_step': '.01'}
    else:
        c['ports'] = ['INP', 'INN', 'OUTP', 'OUTN', 'TAIL', 'VSS']
        mos('MPAIR1', 240, {'d': 'OUTP', 'g': 'INP', 's': 'TAIL', 'b': 'VSS'})
        mos('MPAIR2', 500, {'d': 'OUTN', 'g': 'INN', 's': 'TAIL', 'b': 'VSS'})
        top['devices'] = [
            device('V', 'VDD', 80, 100, value=str(process['supply']), nets={'p': 'vdd', 'n': '0'}),
            device('V', 'VCM', 80, 320, value=str(process['common_mode']), nets={'p': 'inn', 'n': '0'}),
            device('V', 'VIN', 240, 320, value='0', nets={'p': 'inp', 'n': 'inn'}),
            device('R', 'RL1', 520, 120, value='10k', nets={'p': 'vdd', 'n': 'outp'}),
            device('R', 'RL2', 680, 120, value='10k', nets={'p': 'vdd', 'n': 'outn'}),
            device('I', 'ITAIL', 600, 460, value='100u', nets={'p': 'tail', 'n': '0'}),
            device('X', 'XDUT', 460, 320, cell=c['id'], nets={'INP': 'inp', 'INN': 'inn', 'OUTP': 'outp', 'OUTN': 'outn', 'TAIL': 'tail', 'VSS': '0'})]
        measures = [{'name': 'differential_output', 'kind': 'voltage', 'node': 'outp', 'reference': 'outn'},
                    {'name': 'output_p', 'kind': 'voltage', 'node': 'outp', 'min': '.1', 'max': str(process['supply'])},
                    {'name': 'output_n', 'kind': 'voltage', 'node': 'outn', 'min': '.1', 'max': str(process['supply'])}]
        study = {'kind': 'sweep', 'target': 'VIN.value', 'values': ['-.04', '0', '.04']}
        dc = {'source': 'VIN', 'dc_start': '-.08', 'dc_stop': '.08', 'dc_step': '.002'}
    p['analysis'].update(type='op', corner='nominal', temperature=27)
    from .components import configure_component
    configure_component(p,c['id'],c['name'],c['ports'],{})
    from .wiring import migrate
    for cell in p['cells']: migrate(cell, p)
    op = create(p, top['id'], kind + '_op')
    op.update(measurements=measures, characterization=study)
    sweep = clone(op)
    sweep.update(id=uid(), name=kind + '_dc')
    sweep['analysis'].update(type='dc', **dc)
    if kind == 'current_mirror':
        sweep['measurements'][0]['at'] = str(process['outputs'][1])
        sweep['characterization'] = {'kind': 'sweep', 'target': 'IREF.value', 'values': ['45u', '50u', '55u']}
    else:
        for m in sweep['measurements']: m['at'] = '0'
        sweep['characterization'] = {'kind': 'pvt', 'target': 'VDD.value', 'corners': ['nominal'],
                                     'voltages': [process['supply']], 'temperatures': [0, 27, 85]}
    p['testbenches'] = [op, sweep]
    return validate(p), c['id'], op['id']
