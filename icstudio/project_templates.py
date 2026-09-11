"""Technology-neutral circuit templates built from selected catalog models."""
from .model import example, clone, device, uid, validate
from .catalog import link_technology, create_device

TEMPLATES = {'inverter': 'Inverter', 'ring': 'Ring oscillator',
             'current_mirror': 'Current mirror', 'differential_pair': 'Differential pair', 'amplifier': 'Five-transistor amplifier'}


def model_choices(technology, kind):
    return [(key, entry) for key, entry in technology.get('simulation', {}).get('catalog', {}).items()
            if not entry.get('unavailable') and entry.get('kind') == kind
            and set(entry.get('pin_order', [])) == {'d', 'g', 's', 'b'}]


def create(technology, kind='inverter', supply=1.8, nmos=None, pmos=None):
    from .model import scalar
    from .components import configure_component
    from .testbenches import create as create_bench
    from .wiring import migrate
    if kind not in TEMPLATES: raise ValueError('Choose an available circuit template.')
    supply = scalar(supply)
    if supply <= 0: raise ValueError('Supply voltage must be positive.')
    catalog = technology.get('simulation', {}).get('catalog', {})
    selected = {'NMOS': nmos, 'PMOS': pmos}
    for polarity in ('NMOS', 'PMOS') if kind in ('inverter', 'ring', 'amplifier') else ('NMOS',):
        choices = model_choices(technology, polarity)
        if selected[polarity] is None and choices: selected[polarity] = choices[0][0]
        if catalog and selected[polarity] not in {key for key, _ in choices}:
            raise ValueError('Select a supported four-terminal ' + polarity + ' model from this PDK.')
        if technology.get('package_lock') and not catalog:
            raise ValueError('This PDK has no device catalog. Register its simulation models before creating a circuit.')
    p = example('empty'); link_technology(p, technology)
    p['name'] = TEMPLATES[kind] + ' · ' + technology['name']
    bench = p['cells'][0]; bench['name'] = kind + '_testbench'
    cell = {'id': uid(), 'name': kind, 'ports': [], 'devices': [], 'shapes': []}
    p['cells'].append(cell)
    def mos(target, polarity, name, x, y, nets):
        key = selected[polarity]
        d = create_device(technology, key, name, x, y) if key else device(polarity, name, x, y, model_mode='generic')
        d['nets'] = nets; target['devices'].append(d); return d
    source_index = 0
    def source(kind, name, value, positive, negative='0', **kwargs):
        nonlocal source_index
        source_index += 1
        return device(kind, name, 100 + 140*source_index, 80, value=str(value),
                      nets={'p': positive, 'n': negative}, **kwargs)
    if kind in ('inverter', 'ring'):
        inv = cell if kind == 'inverter' else {'id': uid(), 'name': 'inverter', 'ports': [], 'devices': [], 'shapes': []}
        inv['ports'] = ['A', 'Y', 'VPWR', 'VGND']
        mos(inv, 'NMOS', 'MN', 360, 360, {'d': 'Y', 'g': 'A', 's': 'VGND', 'b': 'VGND'})
        mos(inv, 'PMOS', 'MP', 360, 180, {'d': 'Y', 'g': 'A', 's': 'VPWR', 'b': 'VPWR'})
        if kind == 'ring':
            p['cells'].append(inv); cell['ports'] = ['N1', 'N2', 'OUT', 'VPWR', 'VGND']
            for index, (a, y) in enumerate((('OUT', 'N1'), ('N1', 'N2'), ('N2', 'OUT'))):
                cell['devices'].append(device('X', 'X'+str(index+1), 220+250*index, 250, cell=inv['id'],
                    nets={'A': a, 'Y': y, 'VPWR': 'VPWR', 'VGND': 'VGND'}))
        bench['devices'].append(source('V', 'VDD', supply, 'vdd'))
        nets = {'A': 'in', 'Y': 'out', 'VPWR': 'vdd', 'VGND': '0'} if kind == 'inverter' else {'N1': 'n1', 'N2': 'n2', 'OUT': 'out', 'VPWR': 'vdd', 'VGND': '0'}
        if kind == 'inverter':
            bench['devices'].append(source('V', 'VIN', 0, 'in', source={'type':'pulse','low':'0','high':str(supply),'period':'20n','delay':'2n','duty':'.5','ac':'1'}))
        bench['devices'].append(device('X', 'XDUT', 420, 240, cell=cell['id'], nets=nets))
        bench['devices'].append(source('C', 'CL', '5f', 'out'))
        p['analysis'].update(type='tran', step='20p', stop='100n', uic=kind == 'ring')
    elif kind=='amplifier':
        cell['ports']=['INP','INN','OUT','BIAS','VDD','VSS']
        for index,(name,polarity,nets,width) in enumerate([
            ('M1','NMOS',['NREF','INP','TAIL','VSS'],'10u'),('M2','NMOS',['OUT','INN','TAIL','VSS'],'10u'),
            ('M3','PMOS',['NREF','NREF','VDD','VDD'],'10u'),('M4','PMOS',['OUT','NREF','VDD','VDD'],'10u'),
            ('M5','NMOS',['TAIL','BIAS','VSS','VSS'],'5u')]):
            d=mos(cell,polarity,name,180+index*160,260,dict(zip(('d','g','s','b'),nets)));d['params'].update(w=width,l='1u')
        bench['devices']=[source('V','VDD',supply,'vdd'),source('V','VCM',supply/2,'inn'),
            source('V','VIN',0,'inp','inn'),source('V','VBIAS',supply*7/18,'bias'),source('C','CL','20f','out'),
            device('X','XDUT',440,300,cell=cell['id'],nets={'INP':'inp','INN':'inn','OUT':'out','BIAS':'bias','VDD':'vdd','VSS':'0'})]
        for d in bench['devices']:
            if d['kind']=='V':d['source']['ac']='1' if d['name']=='VIN' else '0'
        p['analysis'].update(type='op')
    else:
        cell['ports'] = ['IREF', 'OUT', 'VSS'] if kind == 'current_mirror' else ['INP','INN','OUTP','OUTN','TAIL','VSS']
        if kind == 'current_mirror':
            mos(cell, 'NMOS', 'MREF', 240, 240, {'d':'IREF','g':'IREF','s':'VSS','b':'VSS'})
            mos(cell, 'NMOS', 'MOUT', 500, 240, {'d':'OUT','g':'IREF','s':'VSS','b':'VSS'})
            bench['devices'] = [source('I','IREF','10u','0','ref'), source('V','VOUT',supply/2,'out'),
                device('X','XDUT',360,320,cell=cell['id'],nets={'IREF':'ref','OUT':'out','VSS':'0'})]
        else:
            mos(cell, 'NMOS', 'MPAIR1',240,240,{'d':'OUTP','g':'INP','s':'TAIL','b':'VSS'})
            mos(cell, 'NMOS', 'MPAIR2',500,240,{'d':'OUTN','g':'INN','s':'TAIL','b':'VSS'})
            bench['devices'] = [source('V','VDD',supply,'vdd'),source('V','VCM',supply/2,'inn'),
                source('V','VIN',0,'inp','inn'),source('I','ITAIL','10u','tail'),
                source('R','RL1','10k','vdd','outp'),source('R','RL2','10k','vdd','outn'),
                device('X','XDUT',460,320,cell=cell['id'],nets={'INP':'inp','INN':'inn','OUTP':'outp','OUTN':'outn','TAIL':'tail','VSS':'0'})]
        p['analysis'].update(type='op')
    for c in p['cells']:
        if c['ports']: configure_component(p, c['id'], c['name'], c['ports'], {})
        migrate(c, p)
    testbench = create_bench(p, bench['id'], kind + '_nominal')
    testbench['analysis'] = clone(p['analysis'])
    if kind == 'ring': testbench.update(probes=['n1','n2','out'], initial_conditions={'n1':'0','n2':str(supply),'out':'0'})
    p['testbenches'] = [testbench]
    if kind=='amplifier':
        testbench['measurements']=[dict(name='output_bias',kind='voltage',node='out',min=str(supply/18),max=str(supply*17/18))]
        ac=clone(testbench);ac.update(id=uid(),name='amplifier_ac');ac['analysis'].update(type='ac',start='10',end='100Meg',points=20)
        ac['measurements']=[dict(name='low_frequency_gain',kind='voltage',node='out',at='10',min='5',max='10000')]
        p['testbenches'].append(ac)
    p['template'] = {'version':1,'kind':kind,'supply':supply,'models':selected,
                     'status':'Editable starting circuit; choose device ratings and measurement limits for this process.'}
    return validate(p), cell['id'], testbench['id']
