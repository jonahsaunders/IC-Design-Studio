"""Editable SKY130 two-stage Miller OTA and unchanged saved verification limits.

The circuit exposes an external reference-current bias input. Its AC fixture
uses a DC feedback inductor and an AC shunt capacitor, explicitly approximating
an open loop above 1 Hz while preserving the unity-follower operating point.
"""
from .model import example, clone, device, uid, validate
from .catalog import link_technology, create_device
from .testbenches import create


def reference(technology):
    if technology.get('package_lock', {}).get('id') != 'sky130A':
        raise ValueError('The two-stage op-amp requires the linked SKY130A 1.8 V PDK.')
    catalog = technology.get('simulation', {}).get('catalog', {})
    keys = {}
    for kind, model in [('NMOS', 'sky130_fd_pr__nfet_01v8'), ('PMOS', 'sky130_fd_pr__pfet_01v8'),
                        ('CC', 'sky130_fd_pr__cap_mim_m3_1')]:
        matches = [(k, b) for k, b in catalog.items() if b.get('model') == model and not b.get('unavailable')]
        if kind != 'CC':
            matches = [(k,b) for k,b in matches if b.get('pin_order') == ['d','g','s','b'] and
                       all(b.get('emit_parameters',{}).get(n) == n for n in ('w','l'))]
        if not matches:
            raise ValueError('Missing required catalog model: ' + model)
        keys[kind] = min(matches, key=lambda item:(bool(item[1].get('notes')), item[0]))[0]
    p = example('empty')
    link_technology(p, technology)
    p['name'] = 'Two-stage Miller op-amp · SKY130A'
    dut = {'id': uid(), 'name': 'two_stage_opamp', 'ports': ['INP','INN','OUT','IBIAS','VDD','VSS'],
           'devices': [], 'shapes': []}
    p['cells'] = [dut]
    for name, kind, nets, width, x, y in [
        ('M1','NMOS',['NREF','INN','TAIL','VSS'],'10u',240,320),
        ('M2','NMOS',['STAGE1','INP','TAIL','VSS'],'10u',520,320),
        ('M3','PMOS',['NREF','NREF','VDD','VDD'],'4u',240,100),
        ('M4','PMOS',['STAGE1','NREF','VDD','VDD'],'4u',520,100),
        ('M5','NMOS',['TAIL','IBIAS','VSS','VSS'],'2u',380,540),
        ('M6','PMOS',['OUT','STAGE1','VDD','VDD'],'30u',840,100),
        ('M7','NMOS',['OUT','IBIAS','VSS','VSS'],'3u',840,540),
        ('M8','NMOS',['IBIAS','IBIAS','VSS','VSS'],'1u',100,540)]:
        d = create_device(p['pdk'], keys[kind], name, x, y)
        d['params'].update(w=width, l='1u')
        if name=='M6':
            d['params']['l']='.5u'
            d['model_params']['nf']='6'
        d['nets'] = dict(zip(('d','g','s','b'), nets))
        dut['devices'].append(d)
    for i in range(2):
        cap = create_device(p['pdk'], keys['CC'], 'CC'+str(i+1), 700+i*140, 300)
        cap['model_params'].update(w='30', l='30', mf='1')
        cap['nets'] = {'c0': 'STAGE1', 'c1': 'OUT'}
        dut['devices'].append(cap)
    from .components import configure_component
    configure_component(p,dut['id'],dut['name'],dut['ports'],{})
    p['analysis'].update(type='op',corner='nominal',temperature=27)
    benches = []
    for analysis in ('op', 'ac', 'noise', 'startup'):
        fixture = {'id':uid(), 'name':'opamp_'+analysis+'_fixture', 'ports':[], 'devices':[], 'shapes':[]}
        p['cells'].append(fixture)
        fixture['devices'] = [
            device('V','VDD',80,80,value='1.8',nets={'p':'vdd','n':'0'}),
            device('V','VIN',80,300,value='.9',nets={'p':'inp','n':'0'}),
            device('I','IREF',80,500,value='5u',nets={'p':'vdd','n':'bias'}),
            device('C','CL',760,320,value='1p',nets={'p':'out','n':'0'}),
            device('X','XDUT',420,300,cell=dut['id'],nets={'INP':'inp','INN':'feedback' if analysis=='ac' else 'out',
                'OUT':'out','IBIAS':'bias','VDD':'vdd','VSS':'0'})]
        for source in fixture['devices']:
            if source['kind'] in ('V','I'):
                source['source']['ac']='1' if source['name']=='VIN' else '0'
        if analysis=='ac':
            fixture['devices'].extend([
                device('L','LDC',650,140,value='1G',nets={'p':'out','n':'feedback'}),
                device('C','CAC',650,500,value='1',nets={'p':'feedback','n':'0'})])
        t=create(p,fixture['id'],'opamp_'+analysis)
        if analysis=='op':
            t['analysis']['diagnostic']={'kind':'bias'}
            t['measurements']=[dict(name='output_bias',kind='voltage',node='out',min='.85',max='.95'),
                               dict(name='supply_current',kind='current',source='VDD',min='-100u',max='-1u')]
            t['specifications']=[dict(name='static_power',expression='-final(V("vdd") * I("VDD"))',unit='W',max='180u')]
        elif analysis=='ac':
            t['analysis'].update(type='ac',start='1',end='100Meg',points=40,
                diagnostic=dict(kind='loop',numerator='out',denominator='inp',sign=1))
            t['measurements']=[dict(name='phase_margin',kind='phase_margin',min='45',max='180'),
                               dict(name='unity_frequency',kind='unity_frequency',min='100k',max='50Meg')]
            t['specifications']=[dict(name='dc_gain',expression='at(db20(V("out") / V("inp")), 1)',unit='dB',min='40')]
        elif analysis=='noise':
            t['analysis'].update(type='noise',start='10',end='10Meg',points=30,output='out',noise_source='VIN',
                diagnostic=dict(kind='noise',output='out',source='VIN'))
            t['measurements']=[dict(name='integrated_input_noise',kind='input_noise',max='200u'),
                               dict(name='integrated_output_noise',kind='output_noise',max='200u')]
        else:
            t['analysis'].update(type='tran',stop='200u',step='100n',diagnostic=dict(kind='startup',output='out',source='VDD',
                initial_node='out',initial_voltage='0',minimum='.85',maximum='.95',tail_fraction=.2,
                ramp='20u',supply='1.8',supply_from_source=True,stop='200u'))
            t['measurements']=[dict(name='startup_settling',kind='startup_settling',max='100u'),
                               dict(name='final_output',kind='voltage',node='out',min='.85',max='.95')]
        benches.append(t)
    p['top']=benches[0]['bench_cell']
    p['testbenches']=benches
    p['test_plans']=[dict(id=uid(),name='Two-stage op-amp PVT requirements',variables={},
        corners=['nominal','ss','ff'],temperatures=[0,27,85],voltages=[1.62,1.8,1.98],compare_layout=False,
        entries=[dict(id='bench:'+t['id'],name=t['name'],cell=t['bench_cell'],engine='ngspice',
                      settings={'type':'testbench','testbench':t['id']},supply='VDD.value') for t in benches])]
    dut['opamp_reference']={'version':1,'topology':'eight MOS two-stage Miller OTA with external reference-current bias',
        'bias_A':5e-6,'second_stage_fingers':6,
        'compensation':'Two parallel SKY130 cap_mim_m3_1 devices, each 30 × 30 micrometres, mf=1',
        'load_F':1e-12,'loop_fixture':'1 GH DC feedback plus 1 F AC shunt; return ratio T=V(out)/V(inp), characteristic 1+T',
        'startup_scope':'VDD ramp with an externally established ideal 5 µA reference current; this does not test bias-reference generation.'}
    return validate(p),dut['id'],benches[0]['id']


def generate_layout(p,cid,replace=False):
    from .two_stage_opamp_layout import generate
    return generate(p,cid,replace)
