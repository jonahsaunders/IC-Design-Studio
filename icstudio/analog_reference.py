"""Five-transistor SKY130 OTA with editable, saved OP and AC fixtures."""
from .model import example, device, uid, clone, validate
from .catalog import link_technology, create_device
from .sky130_layout import MODELS
from .testbenches import create


def amplifier(technology):
    if technology.get('package_lock', {}).get('id') != 'sky130A':
        raise ValueError('The amplifier reference requires the linked SKY130A 1.8 V models.')
    keys = {}
    for kind, model in MODELS.items():
        candidates = [(key, b) for key, b in technology.get('simulation', {}).get('catalog', {}).items()
                      if b.get('model') == model and b.get('pin_order') == ['d','g','s','b']
                      and not b.get('unavailable') and all(b.get('emit_parameters', {}).get(k) == k for k in ('w','l'))]
        if not candidates: raise ValueError('The amplifier needs standard four-terminal NMOS and PMOS catalog entries.')
        keys[kind] = min(candidates, key=lambda row: (bool(row[1].get('notes')), row[0]))[0]
    p = example('empty'); link_technology(p, technology); p['name'] = 'Five-transistor amplifier · SKY130A'
    fixture = p['cells'][0]; fixture['name'] = 'amplifier_fixture'
    dut = dict(id=uid(), name='amplifier', ports=['INP','INN','OUT','BIAS','VDD','VSS'], devices=[], shapes=[])
    p['cells'].append(dut)
    for index, (name, kind, nets, width) in enumerate([
        ('M1','NMOS',['NREF','INP','TAIL','VSS'],'10u'),
        ('M2','NMOS',['OUT','INN','TAIL','VSS'],'10u'),
        ('M3','PMOS',['NREF','NREF','VDD','VDD'],'10u'),
        ('M4','PMOS',['OUT','NREF','VDD','VDD'],'10u'),
        ('M5','NMOS',['TAIL','BIAS','VSS','VSS'],'5u')]):
        d = create_device(p['pdk'], keys[kind], name, 180+index*160, 260)
        d['params'].update(w=width, l='1u'); d['nets'] = dict(zip(('d','g','s','b'), nets)); dut['devices'].append(d)
    fixture['devices'] = [
        device('V','VDD',80,100,value='1.8',nets={'p':'vdd','n':'0'}),
        device('V','VCM',80,300,value='.9',nets={'p':'inn','n':'0'}),
        device('V','VIN',240,300,value='0',nets={'p':'inp','n':'inn'}),
        device('V','VBIAS',80,480,value='.7',nets={'p':'bias','n':'0'}),
        device('C','CL',680,300,value='20f',nets={'p':'out','n':'0'}),
        device('X','XDUT',440,300,cell=dut['id'],nets={'INP':'inp','INN':'inn','OUT':'out','BIAS':'bias','VDD':'vdd','VSS':'0'})]
    for d in fixture['devices']:
        if d['kind']=='V': d['source']['ac'] = '0'
    fixture['devices'][2]['source']['ac'] = '1'
    from .components import configure_component
    configure_component(p,dut['id'],dut['name'],dut['ports'],{})
    from .wiring import migrate
    for c in p['cells']: migrate(c,p)
    p['analysis'].update(type='op',corner='nominal',temperature=27)
    op = create(p,fixture['id'],'amplifier_op')
    op['measurements'] = [dict(name='output_bias',kind='voltage',node='out',min='.1',max='1.7'),
                          dict(name='supply_current',kind='current',source='VDD',min='-500u',max='-1n')]
    op['characterization'] = dict(kind='pvt',target='VDD.value',corners=['nominal'],voltages=[1.8],temperatures=[0,27,85])
    ac = clone(op); ac.update(id=uid(),name='amplifier_ac')
    ac['analysis'].update(type='ac',start='10',end='100Meg',points=20)
    ac['measurements'] = [dict(name='low_frequency_gain',kind='voltage',node='out',at='10',min='5',max='10000')]
    p['testbenches'] = [op,ac]
    return validate(p), dut['id'], op['id']
