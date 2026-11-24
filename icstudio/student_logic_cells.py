"""Physical standard-cell fixtures for arithmetic, hysteresis and bus drive."""

from .model import device
from .student_cell_characterization import arc, clip, pulse, worst
from .testbenches import crossings


KEYS = {'half-adder', 'schmitt', 'tristate'}
PORTS = {'half-adder': {'CO':'carry'}}
BIAS_OHM = 25000
STOP = {'half-adder':55, 'schmitt':70, 'tristate':67}
STIMULUS = {
    'half-adder': {'A':(24,48,'.5'), 'B':(12,48,'.5')},
    'schmitt': {'A':(10,64,'.5')},
    'tristate': {'EN':(24,48,'.5'), 'A':(12,24,'.5')},
}
SAMPLES = {
    'half-adder': [(8,(0,0),0),(20,(0,1),1),(32,(1,1),0),(44,(1,0),1),(51,(0,0),0)],
    'schmitt': [(5,(0,),1),(34,(1,),0),(65,(0,),1)],
    'tristate': [(8,(0,0),1),(20,(0,1),0),(32,(1,0),0),(44,(1,1),1),(57,(0,0),0),(66,(0,1),0)],
}


def network(key,inverter):
    def nand(label,a,b,y):
        mid = 'N_'+label
        return [('P','MP_'+label+'A',a,y,'VPWR'), ('P','MP_'+label+'B',b,y,'VPWR'),
                ('N','MN_'+label+'A',a,y,mid), ('N','MN_'+label+'B',b,mid,'VGND')]

    if key=='half-adder':
        return (nand('AB','A','B','NAB') + nand('LEFT','A','NAB','NL')
                + nand('RIGHT','B','NAB','NR') + nand('SUM','NL','NR','Y') + inverter('CARRY','NAB','CO'))
    if key=='schmitt':
        return [('P','MP_TOP','A','P_MID','VPWR'), ('P','MP_OUT','A','Y','P_MID'),
                ('P','MP_FB','Y','VGND','P_MID'), ('N','MN_BOT','A','N_MID','VGND'),
                ('N','MN_OUT','A','Y','N_MID'), ('N','MN_FB','Y','VPWR','N_MID')]
    if key=='tristate':
        return (inverter('DATA_IN','A','A_B') + inverter('ENABLE','EN','EN_B')
                + [('P','MP_EN','EN_B','P_INT','VPWR'),('P','MP_DATA','A_B','Y','P_INT'),
                   ('N','MN_EN','EN','N_INT','VGND'),('N','MN_DATA','A_B','Y','N_INT')])
    raise ValueError('Unknown logic cell.')


def extras(key):
    if key=='half-adder':
        return [device('C','CCARRY',1040,435,value='20f',nets={'p':'carry','n':'0'})]
    if key=='schmitt':
        return [device('R','RIN',330,265,rotation=270,value='10k',nets={'p':'a_drive','n':'a'}),
                device('C','CIN',340,515,value='350f',nets={'p':'a','n':'0'})]
    if key=='tristate':
        pull = pulse('VBIAS','bias',12,24,.5)
        pull.update(x=1050,y=150)
        pull['source'].update(high='0',low='1.8')
        peer = pulse('VPEER','peer_en',50,80,.15)
        peer.update(x=115,y=690)
        supply = device('V','VSENSE',930,665,value='0',nets={'p':'vdd','n':'peer_vdd'})
        return [pull,peer,supply,device('R','RBIAS',1040,365,value=str(BIAS_OHM),nets={'p':'bias','n':'out'})]
    return []


def extra_instances(key,cid):
    if key=='tristate':
        return [device('X','XPEER',580,665,cell=cid,
                       nets={'EN':'peer_en','A':'0','Y':'out','VPWR':'peer_vdd','VGND':'0'})]
    return []


def values(key, result, geometry):
    from .student_hub import at

    if key=='half-adder':
        sum_arcs = [('b',12,'rising','rising'),('a',24,'falling','rising'),
                    ('b',36,'rising','falling'),('a',48,'falling','falling')]
        return {'footprint_um':geometry['width_um'],
                'sum_delay_ps':worst([arc(result,*case) for case in sum_arcs]),
                'carry_delay_ps':worst([arc(result,'a',24,'rising',output='carry'),
                                        arc(result,'b',36,'falling','falling',output='carry')])}

    if key=='schmitt':
        x, y = result['x'], result['traces']['out']
        fall = crossings(x,y,.9,'falling',start=10e-9,stop=36e-9)
        rise = crossings(x,y,.9,'rising',start=42e-9,stop=66e-9)
        upper = at(result,'a',fall[0]) if len(fall)==1 else None
        lower = at(result,'a',rise[0]) if len(rise)==1 else None
        valid = upper is not None and lower is not None and .4 <= lower < upper <= 1.4
        return {'schmitt_width_v':upper-lower if valid else None,
                'schmitt_upper_v':upper, 'schmitt_lower_v':lower}

    if key=='tristate':
        errors = [abs(at(result,'out',t)-at(result,'bias',t))/BIAS_OHM*1e6 for t in (8e-9,22.8e-9)]
        x = result['x']
        en, peer = (clip(x,result['traces'][n],45e-9,60e-9)[1] for n in ('en','peer_en'))
        overlap = any(a>=.9 and b>=.9 for a,b in zip(en,peer))
        return {'leakage_ua':max(errors), 'overlap':int(overlap),
                'tristate_delay_ps':arc(result,'a',36,'rising')}
    raise ValueError('Unknown timed logic cell measurement.')


def contention_comparison(normal, overlap):
    from .analog_diagnostics import integrate

    def mean_supply(result):
        currents = {n.casefold():v for n,v in result.get('currents',{}).items()}
        if 'vdd' not in currents:
            raise ValueError('Capture the supply branch current for the bus comparison.')
        start,stop = 45e-9,47e-9
        t,current = clip(result['x'],currents['vdd'],start,stop)
        return -integrate(t,current)*1e6/(stop-start)

    return {'normal_uA':mean_supply(normal),'overlap_uA':mean_supply(overlap)}
