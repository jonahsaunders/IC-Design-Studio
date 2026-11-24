"""Native SPICE fixtures for the Student Hub circuit design challenges."""

import math

from .model import scalar

ANALYSIS = {
    'floating-voltage': {'type': 'op'},
    'open-drain': {'type': 'tran', 'step': '10n', 'stop': '10u'},
    'switch-drive': {'type': 'tran', 'step': '10n', 'stop': '10u'},
    'weak-sensor': {'type': 'tran', 'step': '10n', 'stop': '12u'},
    'window-detector': {'type': 'tran', 'step': '20n', 'stop': '42u'},
    'swcap-gain': {'type': 'tran', 'step': '5n', 'stop': '22u'},
    'tunable-gmc': {'type': 'ac', 'start': '100', 'end': '1meg', 'points': 60},
}
CONTROLS = {
    'floating-voltage': ('Set meter reference', ('BMETER','nets.ref','Meter negative terminal')),
    'open-drain': ('Size pull-up', ('RPULL','value','Pull-up resistance (Ω)')),
    'switch-drive': ('Size switch and gate drive', ('MSW','params.w','Switch width (m)'),
                     ('VGATE','source.high','High gate voltage (V)')),
    'weak-sensor': ('Set buffer parameters', ('RINPUT','value','Buffer input resistance (Ω)'),
                    ('RISO','value','Buffer output resistance (Ω)')),
    'window-detector': ('Set window references', ('VLOW','value','Lower threshold reference (V)'),
                         ('VHIGH','value','Upper threshold reference (V)')),
    'swcap-gain': ('Size sample and feedback capacitors', ('CS','value','Sampling capacitance (F)'),
                   ('CF','value','Feedback capacitance (F)')),
    'tunable-gmc': ('Size filter capacitor', ('CFILT','value','Filter capacitance (F)')),
}
TUNABLE = {key: {name:(field,) for name,field,_ in controls[1:]} for key,controls in CONTROLS.items()}


def floating_voltage(p,c):
    from .student_signal_circuits import _behavior, _r, _v
    _v(c,'VCM','.9','lo','0',120,300)
    _v(c,'VSIG','.3','hi','lo',330,210)
    _r(c,'RSENSE','10k','hi','lo',520,245)
    _behavior(c,'BMETER','out',dict(pos='hi',ref='0'),'V({pos})-V({ref})',770,260)


def open_drain(p,c):
    from .student_signal_circuits import _c, _mos, _pulse, _r, _v
    _v(c,'VDD','1.8','vdd','0',110,120)
    _v(c,'VGATE','1.8','gate','0',110,355,**_pulse('1.8','0','3u','16u'))
    _r(c,'RPULL','100k','vdd','out',450,140)
    _mos(c,'MSW','out','gate','0',450,380,'100u')
    _c(c,'CBUS','100p','out','0',700,360)


def switch_drive(p,c):
    from .student_signal_circuits import _mos, _pulse, _r, _v
    _v(c,'VDD','1.8','vdd','0',110,120)
    _v(c,'VGATE','0','gate','0',110,355,**_pulse('0','.7','3u','16u'))
    _r(c,'RL','1k','vdd','out',460,140)
    _mos(c,'MSW','out','gate','0',460,400,'200u')


def weak_sensor(p,c):
    from .student_signal_circuits import _behavior, _c, _pulse, _r, _v
    _v(c,'VSENSOR','.4','source','0',105,220,**_pulse('.4','.8','5u','24u'))
    _r(c,'RSENSOR','1meg','source','sense',295,205,rotation=270)
    _r(c,'RINPUT','10meg','sense','0',400,415)
    _behavior(c,'BBUF','drive',dict(i='sense'),'min(1.75,max(.05,V({i})))',580,205)
    _r(c,'RISO','10k','drive','out',785,205,rotation=270)
    _c(c,'CL','250p','out','0',860,425)
    _r(c,'RL','1meg','out','0',1080,425)


def window_detector(p,c):
    from .student_signal_circuits import _behavior, _v
    _v(c,'VIN','.9','clean','0',115,160,type='sine',low='.9',high='1.7',period='40u',delay='0')
    _v(c,'VNOISE','0','vin','clean',295,155,type='sine',low='0',high='.008',period='2u',delay='0')
    _v(c,'VLOW','.35','lo','0',115,370)
    _v(c,'VHIGH','1.52','hi','0',115,590)
    _behavior(c,'BLOW','above',dict(i='vin',vref='lo'),'.9*(1+tanh(450*(V({i})-V({vref}))))',460,280)
    _behavior(c,'BHIGH','below',dict(i='vin',vref='hi'),'.9*(1+tanh(450*(V({vref})-V({i}))))',460,490)
    _behavior(c,'BAND','out',dict(l='above',h='below'),'V({l})*V({h})/1.8',785,355)


def swcap_gain(p,c):
    from .sar_example import primitive
    from .student_signal_circuits import _behavior, _c, _pulse, _r, _v
    _v(c,'VIN','1','vin','0',115,150,**_pulse('1','1.1','9u','60u'))
    _v(c,'VCM','.9','cm','0',120,380)
    _v(c,'VSAMPLE','0','phi1','0',110,610,**_pulse('0','1.8','1u','10u','.35'))
    _v(c,'VTRANSFER','0','phi2','0',110,830,**_pulse('0','1.8','6u','10u','.33'))
    for i,(name,a,b,phase,x,y) in enumerate([
        ('SIN','vin','plate','phi1',370,170),('STR','cm','plate','phi2',370,410),
        ('SRST','sum','out','phi1',910,625)
    ]):
        c['devices'].append(primitive(name,dict(a=a,b=b,ctrl=phase,gnd='0'),'sample_switch',x,y,
                                     definition='.model sample_switch SW(Ron=100 Roff=1e12 Vt=.9 Vh=.02)' if i==0 else ''))
    _c(c,'CS','1p','plate','sum',565,270)
    _c(c,'CF','1p','sum','out',810,115)
    _r(c,'RBLEED','100g','plate','cm',540,490)
    _behavior(c,'BAMP','drive',dict(vref='cm',neg='sum'),
              'min(1.75,max(.05,V({vref})+400*(V({vref})-V({neg}))))',720,375)
    _r(c,'ROUT','100','drive','out',940,365,rotation=270)
    _c(c,'CL','1p','out','0',1090,390)


def tunable_gmc(p,c):
    from .sar_example import primitive
    from .student_signal_circuits import _c, _tokens, _v
    _v(c,'VIN','.9','vin','0',110,210)['source']['ac'] = '1'
    _v(c,'VTUNE','.4','tune','0',110,450)
    _v(c,'VCM','.9','cm','0',360,490)
    terminals = dict(p='0',n='out',i='vin',o='out',t='tune')
    ota = primitive('BOTA',terminals,'',410,240)
    ota['native_spice']['tokens'] = [dict(kind='instance'),*_tokens(
        ' {p} {n} I=25u*V({t})*tanh((V({i})-V({o}))/.25)',dict.fromkeys(terminals,'terminal'))]
    c['devices'].append(ota)
    _c(c,'CFILT','800p','out','cm',700,290)


BUILDERS = dict(zip(ANALYSIS,(floating_voltage, open_drain, switch_drive, weak_sensor,
                             window_detector, swcap_gain, tunable_gmc)))


def cases(project, lab, analysis, case):
    from .student_signal_circuits import named
    if lab == 'switch-drive':
        def load(c, ohms):
            named(c,'RL')['value'] = ohms
        return [case(project,name,analysis,lambda c,r=r: load(c,r))
                for name,r in [('light-load','1k'),('heavy-load','400')]]
    if lab == 'tunable-gmc':
        def tune(c, volts):
            named(c,'VTUNE')['value'] = volts
        def drive(c, volts):
            tune(c,volts)
            named(c,'VIN')['source'].update(type='sine',low='.9',high='1.1',period='200u',delay='0')
        pairs = [('low-tuning','.4'),('high-tuning','1.2')]
        transient = dict(type='tran',step='500n',stop='1.2m')
        return ([case(project,name,analysis,lambda c,v=v: tune(c,v)) for name,v in pairs]
                + [case(project,name+'-tone',transient,lambda c,v=v: drive(c,v)) for name,v in pairs])
    return [case(project,'nominal',analysis)]


def measurements(p, lab, waves):
    from .student_signal_labs import _crossings, _harmonic, _range, _sample, _samples, _series, _settling
    if lab == 'switch-drive':
        return {name: {'On drop (V)': _sample(w,'out',6e-6),
                       'Off drain (V)': _sample(w,'out',1e-6),
                       'High gate (V)': _sample(w,'gate',6e-6)} for name,w in waves.items()}
    if lab == 'tunable-gmc':
        readings = {}
        for name in ('low-tuning','high-tuning'):
            w = waves[name]
            axis, amps = _series(w,'out')
            gain = amps[0]
            cutoff = next((math.exp(math.log(a)+(math.log(b)-math.log(a))*(u-gain/math.sqrt(2))/(u-v))
                           for a,b,u,v in zip(axis,axis[1:],amps,amps[1:])
                           if u >= gain/math.sqrt(2) > v), None)
            values = _samples(waves[name+'-tone'],'out',.0006,.001,512)
            fundamental = _harmonic(values,2)
            thd = 100*math.hypot(*(_harmonic(values,2*k) for k in range(2,6)))/max(1e-12,fundamental)
            readings[name] = {'Passband gain (V/V)':gain,'Cutoff (Hz)':cutoff,'THD at 5 kHz (%)':thd}
        return readings
    w = waves['nominal']
    if lab == 'floating-voltage':
        plus, minus = _sample(w,'hi',0), _sample(w,'lo',0)
        return {'Positive terminal (V)':plus, 'Negative terminal (V)':minus,
                'Expected difference (V)':plus-minus,'Meter reading (V)':_sample(w,'out',0)}
    if lab == 'open-drain':
        low = _sample(w,'out',2e-6)
        xs, ys = _range(w,'out',3e-6,9e-6)
        rise = _crossings(xs,ys,1.26)[0]
        pull = next(d for d in p['cells'][0]['devices'] if d['name']=='RPULL')
        return {'Low (V)':low,'Released level (V)':_sample(w,'out',9e-6),
                'Sink current (mA)':(1.8-low)/scalar(pull['value'])*1000,
                'Release to 70% (µs)':(rise[0]-3e-6)*1e6 if rise else None}
    if lab == 'weak-sensor':
        duration = _settling(w,'out',5e-6,11e-6,.8,.008)
        return {'Sensor loading (%)':abs(.8-_sample(w,'sense',11e-6))/.8*100,
                'Output error (%)':abs(.8-_sample(w,'out',11e-6))/.8*100,
                'Settling (µs)':None if duration is None else duration*1e6}
    if lab == 'window-detector':
        rising, falling = _crossings(*_series(w,'out'),.9)
        lows, highs = [], []
        for t in (*rising,*falling):
            value = _sample(w,'vin',t)
            (lows if value<.9 else highs).append(value)
        return {'Lower crossings (V)':sorted(lows),'Upper crossings (V)':sorted(highs),
                'Outside high (V)':_sample(w,'out',10e-6),
                'Outside low (V)':_sample(w,'out',30e-6),'Inside (V)':_sample(w,'out',19e-6)}
    if lab == 'swcap-gain':
        early, late = (_sample(w,'out',t) for t in (8.5e-6,18.5e-6))
        held = _sample(w,'out',9.2e-6)
        return {'First plateau (V)':early,'Second plateau (V)':late,'Gain (V/V)':(late-early)/.1,
                'First deadline error (mV)':abs(_sample(w,'out',6.7e-6)-1.1)*1000,
                'Second deadline error (mV)':abs(_sample(w,'out',16.7e-6)-1.3)*1000,
                'Hold change (mV)':abs(held-early)*1000}
    raise ValueError('Unknown circuit lesson.')


def passed(lab, m):
    if lab == 'floating-voltage':
        return abs(m['Meter reading (V)']-m['Expected difference (V)']) <= .005
    if lab == 'open-drain':
        rise = m['Release to 70% (µs)']
        return 0 <= m['Low (V)'] <= .2 and m['Released level (V)'] >= 1.7 and m['Sink current (mA)'] <= .5 and rise is not None and rise <= .8
    if lab == 'switch-drive':
        return all(0 <= row['On drop (V)'] <= .15 and row['Off drain (V)'] >= 1.75 and 0 < row['High gate (V)'] <= 1.8
                   for row in m.values())
    if lab == 'weak-sensor':
        settle = m['Settling (µs)']
        return m['Sensor loading (%)'] <= 1 and m['Output error (%)'] <= 1 and settle is not None and settle <= 1.5
    if lab == 'window-detector':
        lower, upper = m['Lower crossings (V)'], m['Upper crossings (V)']
        return (len(lower)==len(upper)==2 and all(abs(v-.55)<.02 for v in lower)
                and all(abs(v-1.25)<.02 for v in upper) and max(m['Outside high (V)'],m['Outside low (V)']) <= .18
                and m['Inside (V)'] >= 1.62)
    if lab == 'swcap-gain':
        return (1.96 <= m['Gain (V/V)'] <= 2.04 and abs(m['First plateau (V)']-1.1) <= .005
                and abs(m['Second plateau (V)']-1.3) <= .005
                and max(m['First deadline error (mV)'],m['Second deadline error (mV)']) <= 5
                and m['Hold change (mV)'] <= 2)
    if lab == 'tunable-gmc':
        return all(row['Cutoff (Hz)'] is not None and abs(row['Cutoff (Hz)']/target-1) <= .06
                   and .98 <= row['Passband gain (V/V)'] <= 1.02 and row['THD at 5 kHz (%)'] <= 1
                   for row,target in zip(m.values(),(20000,60000)))
    raise ValueError('Unknown circuit lesson.')
