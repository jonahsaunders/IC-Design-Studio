"""Editable circuits and fixtures for the Student Hub interview labs."""

from .catalog import create_device, link_technology
from .components import configure_component
from .model import device, example, uid, validate
from .student_analog import _cell, bundled_technology
from .testbenches import create as save_bench


def passive(kind, name, value, p, n='0'):
    item = device(kind,name,value=value,nets={'p':p,'n':n})
    item['source']['ac'] = '0'
    return item


def pulse(kind, name, low, high, delay, p, n='0', edge='1n', period='100u'):
    item = passive(kind,name,low,p,n)
    item['source'].update(type='pulse', low=low, high=high, delay=delay,
                          rise=edge, fall=edge, duty='.5', period=period)
    return item


def mos(p, kind, name, nets, width, length='1u'):
    if p['pdk'].get('package_lock'):
        model = 'sky130_fd_pr__' + ('nfet' if kind=='NMOS' else 'pfet') + '_01v8'
        entries = p['pdk']['simulation']['catalog']
        key = min((key for key, item in entries.items() if item.get('model')==model
                   and not item.get('unavailable') and item['pin_order']==['d','g','s','b']
                   and item.get('emit_parameters',{}).get('w')=='w'),
                   key=lambda key:(bool(entries[key].get('notes')),key))
        item = create_device(p['pdk'],key,name,0,0)
    else:
        item = device(kind,name)
    item['nets'] = dict(zip(('d','g','s','b'),nets,strict=True))
    item['params'].update(w=width,l=length)
    return item


def place(items):
    for index,item in enumerate(items):
        item.update(x=160+(index%5)*295,y=180+(index//5)*235)
    return items


def circuit(p, name, ports, items):
    c = dict(id=uid(),name=name,ports=ports,devices=place(items),shapes=[])
    p['cells'].append(c)
    configure_component(p,c['id'],name,ports,{})
    return c


def fixture(p, dut, name, devices, connections, analysis, *, currents=()):
    pins = {n:connections.get(n,n.lower()) for n in dut['ports']}
    instance = device('X','XDUT',cell=dut['id'],nets=pins)
    c = dict(id=uid(),name=name+'_fixture',ports=[],shapes=[],devices=place([*devices,instance]))
    p['cells'].append(c)
    bench = save_bench(p,c['id'],name)
    bench['analysis'].update(analysis)
    bench['measurements'] = [dict(name='current_'+source.lower(),kind='current',source=source)
                             for source in currents]
    p['testbenches'].append(bench)
    return bench


def dc(source, start, stop, step):
    return dict(type='dc',source=source,dc_start=start,dc_stop=stop,dc_step=step)


def pair(p, polarity):
    is_n = polarity=='NMOS'
    tail_rail, load_rail = ('VSS','VDD') if is_n else ('VDD','VSS')
    width = '8u' if is_n else '36u'
    tail_width = '4u' if is_n else '10u'
    items = [mos(p,polarity,name,(out,gate,'TAIL',tail_rail),width)
             for name,out,gate in [('MLEFT','LEFT','INP'),('MRIGHT','RIGHT','INN')]]
    items.append(mos(p,polarity,'MTAIL',('TAIL','BIAS',tail_rail,tail_rail),tail_width))
    items.extend([passive('R','RL','32k','LEFT',load_rail), passive('R','RR','32k','RIGHT',load_rail)])
    return circuit(p,polarity.lower()+'_input_pair',['VDD','VSS','INP','INN','BIAS','LEFT','RIGHT','TAIL'],items)


def input_pairs(p, compare):
    for polarity in ('NMOS','PMOS') if compare else ('NMOS',):
        dut = pair(p,polarity)
        is_n = polarity=='NMOS'
        names = ('nmos_common_mode',) if compare else ('differential_sweep','common_mode_sweep')
        if not is_n:
            names = ('pmos_common_mode',)
        for name in names:
            differential = name=='differential_sweep'
            fixture(p,dut,name,[
                passive('V','VDD','1.8','vdd'), passive('V','VBIAS','.64' if is_n else '.73','bias'),
                passive('V','VCM','.90','cm'),
                passive('V','VDIFF','0' if differential else '5m','inp','cm'),
                passive('V','VOFF','0' if differential else '-5m','inn','cm'),
            ],{'VSS':'0'},dc('VDIFF','-.24','.24','.004') if differential else dc('VCM','0','1.8','.01'))


def gain(p):
    dut = circuit(p,'common_source_device',['D','G','VSS'],
                  [mos(p,'NMOS','MGAIN',('D','G','VSS','VSS'),'8u','.5u')])
    for name, gate in [('drain_nominal','.65'),('drain_gate_low','.64'),('drain_gate_high','.66')]:
        fixture(p,dut,name,[passive('V','VG',gate,'g'),passive('V','VD','.8','d')],{'VSS':'0'},
                dc('VD','.02','1.20','.01'),currents=('VD',))


def opamp():
    from .two_stage_opamp import reference

    p, core, _ = reference(bundled_technology())
    dut = _cell(p,core)
    p['cells'] = [dut]
    p['testbenches'] = []
    p['test_plans'] = []
    p['top'] = core
    return p,dut


def slew(p, dut):
    for name,low,high,load in [('small_step','.89','.91','2p'),
                               ('large_step','.65','1.15','2p'),
                               ('heavy_load_step','.65','1.15','8p'),
                               ('falling_step','1.15','.65','2p'),
                               ('heavy_load_fall','1.15','.65','8p')]:
        fixture(p,dut,name,[
            passive('V','VDD','1.8','vdd'), pulse('V','VIN',low,high,'2u','inp'),
            passive('I','IREF','5u','vdd','ibias'),passive('C','CL',load,'out'),
        ],{'VSS':'0','INN':'out'},dict(type='tran',step='4n',stop='20u'))


def noise(p,dut):
    for name, source in [('low_source_resistance','1k'),('high_source_resistance','100k')]:
        vin = passive('V','VIN','.9','drive')
        vin['source']['ac'] = '1'
        bench = fixture(p,dut,name,[
            passive('V','VDD','1.8','vdd'), vin, passive('R','RS',source,'drive','inp'),
            passive('I','IREF','5u','vdd','ibias'), passive('C','CL','1p','out'),
        ],{'VSS':'0','INN':'out'},dict(type='noise',start='10',end='1Meg',points=50,output='out',
                                      noise_source='VIN',diagnostic=dict(kind='noise',output='out',source='VIN')))
        bench['measurements'] = [dict(name='input_noise',kind='input_noise'),
                                 dict(name='output_noise',kind='output_noise')]


def mismatch(p):
    p['cells'] = []
    for name,width,length in [('small_devices','2u','1u'),('large_devices','4u','2u')]:
        # Keep W/L and the nominal bias equal so this experiment isolates area.
        parts = [mos(p,'NMOS',name,('v'+side,'g'+side,'tail','0'),width,length)
                 for name,side in [('MLEFT','left'),('MRIGHT','right')]]
        parts.extend([passive('V','VDD','1.8','vdd'),passive('I','ITAIL','40u','tail'),
                      passive('V','VLEFT','.98','gleft'),passive('V','VRIGHT','.98','gright'),
                      passive('R','RL','15.3k','vleft','vdd'),passive('R','RR','15k','vright','vdd')])
        p['cells'].append(dict(id=uid(),name=name,ports=[],devices=place(parts),shapes=[]))


def comparator(p):
    devices = [
        mos(p,'PMOS','MRP',('OUTP','CLK','VDD','VDD'),'3u','.18u'),
        mos(p,'PMOS','MRN',('OUTN','CLK','VDD','VDD'),'3u','.18u'),
        mos(p,'PMOS','MRX',('XP','CLK','VDD','VDD'),'2u','.18u'),
        mos(p,'PMOS','MRY',('XN','CLK','VDD','VDD'),'2u','.18u'),
        mos(p,'PMOS','MPP',('OUTP','OUTN','VDD','VDD'),'3u','.18u'),
        mos(p,'PMOS','MNN',('OUTN','OUTP','VDD','VDD'),'3u','.18u'),
        mos(p,'NMOS','MNP',('OUTP','OUTN','XP','VSS'),'2u','.18u'),
        mos(p,'NMOS','MPN',('OUTN','OUTP','XN','VSS'),'2u','.18u'),
        mos(p,'NMOS','MINP',('XP','INP','TAIL','VSS'),'4u','.18u'),
        mos(p,'NMOS','MINN',('XN','INN','TAIL','VSS'),'4u','.18u'),
        mos(p,'NMOS','MTAIL',('TAIL','CLK','VSS','VSS'),'8u','.18u'),
    ]
    dut = circuit(p,'dynamic_comparator',['VDD','VSS','CLK','INP','INN','OUTP','OUTN'],devices)
    for name,overdrive in [('small_overdrive',.003),('large_overdrive',.040)]:
        fixture(p,dut,name,[
            passive('V','VDD','1.8','vdd'), pulse('V','VCLK','0','1.8','20n','clk',edge='300p',period='240n'),
            passive('V','VPLUS',str(.9+overdrive/2),'srcp'),passive('V','VMINUS',str(.9-overdrive/2),'srcn'),
            passive('R','RP','10k','srcp','inp'),passive('R','RN','10k','srcn','inn'),
            passive('C','CINP','30f','inp'),passive('C','CINN','30f','inn'),
            passive('C','CLP','20f','outp'),passive('C','CLN','20f','outn'),
        ],{'VSS':'0'},dict(type='tran',step='20p',stop='95n'))


def sar(p):
    caps = [passive('C',f'C{i}',value,'HOLD',f'BIT{i}') for i,value in enumerate(('100f','200f','400f','650f'))]
    dut = circuit(p,'sampler_and_capacitor_dac',['VDD','VSS','IN','HOLD','CLK','CLKB','BIT0','BIT1','BIT2','BIT3'],[
        mos(p,'NMOS','MNSW',('HOLD','CLK','IN','VSS'),'3u','.18u'),
        mos(p,'PMOS','MPSW',('HOLD','CLKB','IN','VDD'),'6u','.18u'),
        *caps,passive('C','CDUMMY','100f','HOLD','VSS'),
    ])
    for name,resistor in [('slow_acquisition','45k'),('fast_acquisition','1.5k')]:
        fixture(p,dut,name,[
            passive('V','VDD','1.8','vdd'),pulse('V','VCLK','1.8','0','50n','clk',edge='200p',period='400n'),
            pulse('V','VCLKB','0','1.8','50n','clkb',edge='200p',period='400n'),
            pulse('V','VIN','.25','.90','4n','drive',edge='200p',period='400n'),
            passive('R','RDRIVE',resistor,'drive','in'),
            *[passive('V',f'VB{i}','0',f'bit{i}') for i in range(3)],
            pulse('V','VB3','0','1.6','75n','bit3',edge='200p',period='400n'),
        ],{'VSS':'0'},dict(type='tran',step='50p',stop='110n'))


def ldo(p,amp):
    regulator = circuit(p,'pmos_ldo',['VDD','VSS','REF','IBIAS','OUT','FB','GATE'],[
        device('X','XERROR',cell=amp['id'],nets={'INP':'FB','INN':'REF','OUT':'GATE','IBIAS':'IBIAS','VDD':'VDD','VSS':'VSS'}),
        mos(p,'PMOS','MPASS',('OUT','GATE','VDD','VDD'),'80u','1u'),
        passive('R','RUP','20k','OUT','FB'),passive('R','RDN','60k','FB','VSS'),
    ])
    for name,test,esr in [('dropout_sweep','dc','20'),('load_step','load','20'),
                          ('capacitor_esr','load','350'),('supply_step','line','350'),('supply_startup','start','350')]:
        supply = passive('V','VDD','1.8','vdd')
        load = passive('I','ILOAD','25u','out')
        if test=='load':
            load = pulse('I','ILOAD','25u','100u','3u','out',edge='10n')
        if test=='line':
            supply = pulse('V','VDD','1.8','1.63','3u','vdd',edge='10n')
        if test=='start':
            supply = pulse('V','VDD','0','1.8','1u','vdd',edge='3u')
            load = passive('R','RLOAD','48k','out')
        fixture(p,regulator,name,[
            supply, load, passive('V','VREF','.9','ref'),passive('I','IREF','5u','vdd','ibias'),
            passive('R','RESR',esr,'out','cap'),passive('C','COUT','120p','cap'),
        ],{'VSS':'0'},dc('VDD','1.35','1.8','.01') if test=='dc' else dict(type='tran',step='10n',stop='36u'))


def post_layout():
    from .student_layout_decisions import project

    p = project()
    cell = _cell(p,p['top'])
    p['cells'] = [cell]
    cell['name'] = 'routed_settling_fixture'
    source = next(d for d in cell['devices'] if d['kind']=='V')
    source['source'].update(type='pulse',low='0',high='1.8',delay='10p',rise='.5p',fall='.5p',period='800p',duty='.5')
    p['analysis'].update(type='tran',step='.25p',stop='140p')
    cell['specifications'] = []
    return p


def project(kind):
    if kind=='post-layout-debug':
        p = post_layout()
    elif kind in ('slew','noise','ldo'):
        p,dut = opamp()
        {'slew':slew,'noise':noise,'ldo':ldo}[kind](p,dut)
    else:
        p = example('empty')
        p.update(cells=[],testbenches=[])
        p['analysis'].update(type='op',corner='nominal',temperature=27)
        if kind!='mismatch':
            link_technology(p,bundled_technology())
        if kind in ('differential','input-pairs'):
            input_pairs(p,kind=='input-pairs')
        else:
            {'gain':gain,'mismatch':mismatch,'comparator':comparator,'sar':sar}[kind](p)
    p['name'] = 'Student · ' + {
        'differential':'Differential pair and common mode','input-pairs':'PMOS and NMOS input pairs',
        'gain':'Gain, swing and headroom','slew':'Slew rate and precision settling','noise':'Noise budget',
        'mismatch':'Offset and mismatch','comparator':'Dynamic comparator','sar':'SAR sampling and capacitor DAC',
        'ldo':'LDO and power delivery','post-layout-debug':'Post-layout settling debug',
    }[kind]
    p['student_interview'] = kind
    p['top'] = p['testbenches'][0]['bench_cell'] if p.get('testbenches') else p['cells'][0]['id']
    return validate(p)
