"""Measured checkpoints for analog interview practice."""

from bisect import bisect_left
import math
from pathlib import Path

from .model import clone, design_digest, scalar
from .student_analog import _cell, _get_bench, _latest, _named

BENCHES = {
    'differential': ('differential_sweep','common_mode_sweep'),
    'input-pairs': ('nmos_common_mode','pmos_common_mode'),
    'gain': ('drain_nominal','drain_gate_low','drain_gate_high'),
    'slew': ('small_step','large_step','heavy_load_step','falling_step','heavy_load_fall'),
    'noise': ('low_source_resistance','high_source_resistance'),
    'mismatch': ('small_dc','small_trials','large_dc','large_trials'),
    'comparator': ('small_overdrive','large_overdrive'),
    'sar-fault': ('slow_acquisition','fast_acquisition'),
    'sar-repair': ('slow_acquisition','fast_acquisition'),
    'ldo': ('dropout_sweep','load_step','capacitor_esr','supply_step','supply_startup'),
    'route-baseline': ('route_comparison',),
    'route-repair': ('route_comparison',),
}
MISMATCH_TRIALS = 64
ROUTE_TARGET_PS = 50


def run_names(step):
    return BENCHES.get(step, ())


def focus(p,step,circuit=False):
    if p['student_interview'] in ('mismatch','post-layout-debug'):
        return p['top']
    name = (BENCHES.get(step) or (p['testbenches'][0]['name'],))[0]
    bench = _get_bench(p,name)
    return bench['dut_cell'] if circuit or step not in BENCHES else bench['bench_cell']


def _mismatch_job(p, name):
    size, analysis = name.split('_',1)
    cell = next(c for c in p['cells'] if c['name']==size+'_devices')
    settings = dict(type='dc',source='VLEFT',dc_start='.975',dc_stop='.985',dc_step='.001',temperature=27)
    if analysis=='trials':
        variations = []
        for label in ('MLEFT','MRIGHT'):
            item = _named(cell,label)
            area = scalar(item['params']['w'])*scalar(item['params']['l'])*1e12
            sigma = .004/math.sqrt(area)
            vto = scalar(item['params']['vto'])
            variations.append(dict(target=label+'.params.vto', relative_sigma=sigma/vto))
        study = dict(kind='monte_carlo',seed=37127,count=MISMATCH_TRIALS,variations=variations,
                     measurement=dict(trace='vleft',metric='final'))
        settings = dict(type='study',analysis={'type':'op','temperature':27},study=study)
    return cell['id'],settings


def prepare(p,step,tools):
    from .run_environment import stamp
    from .spice_program import find_ngspice

    names = run_names(step)
    if not names:
        raise ValueError('Select a measured exercise.')
    plain = step=='mismatch' or step.startswith('route-')
    if not plain:
        executable = find_ngspice(tools.get('ngspice',''))
        if not executable or not Path(executable).is_file():
            raise ValueError('Choose ngspice in Engine setup to run the saved SKY130 circuits.')
    jobs = []
    for name in names:
        extras = {}
        if step=='mismatch':
            cell,settings = _mismatch_job(p,name)
        elif step.startswith('route-'):
            from .student_layout_decisions import prepare as route
            job = route(p,'baseline')
            cell,settings = job['cell'],job['settings']
        else:
            bench = _get_bench(p,name)
            cell = bench['bench_cell']
            settings = dict(type='testbench',testbench=bench['id'],executable=executable)
            extras['executable'] = executable
        job = dict(project=clone(p),cell=cell,settings=settings,engine='builtin' if plain else 'ngspice',
                   student_analog=dict(project='interview',stage=step,bench=name),**extras)
        job['environment'] = stamp(job)
        jobs.append(job)
    return jobs


def _series(wave, name):
    values = wave.get('traces',{}).get(name)
    if not values or len(wave['x'])!=len(values):
        raise ValueError('Missing measured waveform '+name+'.')
    return values


def _at(xs, ys, x):
    i = bisect_left(xs,x)
    if i==len(xs) or x<xs[0]:
        raise ValueError('Extend the saved sweep to capture the requested measurement.')
    if not i or xs[i]==x:
        return ys[i]
    return ys[i-1]+(ys[i]-ys[i-1])*(x-xs[i-1])/(xs[i]-xs[i-1])


def _voltage(wave,name,x):
    return _at(wave['x'],_series(wave,name),x)


def _cross(xs, ys, y, begin):
    for a,b,va,vb in zip(xs,xs[1:],ys,ys[1:]):
        if a>=begin and va<y<=vb:
            return a+(b-a)*(y-va)/(vb-va)
    raise ValueError('The waveform did not reach the measurement threshold.')


def _settled(xs, ys, target, tolerance, begin):
    outside = [i for i,(t,v) in enumerate(zip(xs,ys)) if t>=begin and abs(v-target)>tolerance]
    if outside and outside[-1]+1==len(xs):
        raise ValueError('The waveform never settled into the required band.')
    return max(0,xs[outside[-1]+1]-begin) if outside else 0.


def _dut(p,name):
    return _cell(p,_get_bench(p,name)['dut_cell'])


def _currents(p,name,wave,polarity):
    c = _dut(p,name)
    loads = [scalar(_named(c,key)['value']) for key in ('RL','RR')]
    voltages = [_series(wave,key) for key in ('left','right')]
    if polarity=='NMOS':
        supply = _series(wave,'vdd')
        voltages = [[v-o for v,o in zip(supply,output)] for output in voltages]
    return [[v/r for v in output] for output,r in zip(voltages,loads)]


def _common_mode(p,name,wave,polarity):
    xs = wave['x']
    first,last = _currents(p,name,wave,polarity)
    total = [a+b for a,b in zip(first,last)]
    gain = [abs(a-b)/.01 for a,b in zip(_series(wave,'left'),_series(wave,'right'))]
    center = .7 if name in BENCHES['input-pairs'] else .9
    i = min(range(len(xs)),key=lambda i:abs(xs[i]-center))
    current,midgain = total[i],gain[i]
    if current <= 1e-6 or midgain < .1:
        raise ValueError(f'Bias the pair at {center:.2f} V common mode before measuring its usable input range.')
    passing = [current*.8<=t<=current*1.2 and g>=midgain*.7 for t,g in zip(total,gain)]
    start = end = i
    while start>0 and passing[start-1]:
        start -= 1
    while end+1<len(xs) and passing[end+1]:
        end += 1
    return {'Lower input limit (V)':xs[start], 'Upper input limit (V)':xs[end],
            f'Tail current at {center:.2f} V (µA)':current*1e6,
            f'Differential gain at {center:.2f} V (V/V)':midgain}


def differential(p,r):
    name = 'differential_sweep'
    w = r[name]
    first,last = _currents(p,name,w,'NMOS')
    steering = [i/(i+j) if i+j>1e-9 else 0 for i,j in zip(first,last)]
    return {'Differential sweep':{'Left share at −240 mV (%)':100*steering[0],
                                  'Left share at +240 mV (%)':100*steering[-1],
                                  'Left share at 0 V (%)':100*_at(w['x'],steering,0)},
            'Common-mode sweep':_common_mode(p,'common_mode_sweep',r['common_mode_sweep'],'NMOS')}


def input_pairs(p,r):
    return {label:_common_mode(p,key,r[key],label)
            for label,key in [('NMOS','nmos_common_mode'),('PMOS','pmos_common_mode')]}


def gain(p,r):
    def current(name,v):
        w = r[name]
        return -_at(w['x'],w['currents']['vd'],v)
    def at(v):
        gm = (current('drain_gate_high',v)-current('drain_gate_low',v))/.02
        gds = (current('drain_nominal',v+.02)-current('drain_nominal',v-.02))/.04
        if gm<=0 or gds<=0:
            raise ValueError('Bias the device with positive gm and gds.')
        return {'gm (µS)':gm*1e6,'ro (kΩ)':1e-3/gds,'Intrinsic gain (V/V)':gm/gds,
                'Gain magnitude with 50 kΩ load (V/V)':gm/(gds+1/50e3)}
    return {'Drain at 0.08 V':at(.08),'Drain at 0.80 V':at(.80)}


def slew(p,r):
    results = {}
    for name in BENCHES['slew']:
        w = r[name]
        xs,ys = w['x'],_series(w,'out')
        initial = _voltage(w,'out',1.5e-6)
        target = _voltage(w,'out',18e-6)
        command = _voltage(w,'inp',18e-6)
        step = target-initial
        if abs(step)<1e-3:
            raise ValueError('Apply an input step large enough to measure.')
        fraction = [(v-initial)/step for v in ys]
        transition = _cross(xs,fraction,.9,2e-6)-_cross(xs,fraction,.1,2e-6)
        errors = _settled(xs,ys,target,.02*abs(step),2e-6)
        results[name] = {'10–90% transition (ns)':transition*1e9,'10–90% slope (V/µs)':.8*step/transition*1e-6,
                         '2% settling (ns)':errors*1e9,'Final DC error (mV)':(command-target)*1e3}
    return results


def noise(p,r):
    results = {}
    for name in BENCHES['noise']:
        resistance = scalar(_named(_cell(p,_get_bench(p,name)['bench_cell']),'RS')['value'])
        values = r[name]['diagnostics']
        results[name] = {'Source resistor alone (nV/√Hz)':math.sqrt(4*1.380649e-23*300.15*resistance)*1e9,
                         'Integrated input noise (µV RMS)':values['input_rms_V']*1e6,
                         'Integrated output noise (µV RMS)':values['output_rms_V']*1e6}
    return results


def offset_samples(project,r,size):
    w = r[size+'_dc']
    vdiff = lambda v: _voltage(w,'vleft',v)-_voltage(w,'vright',v)
    dx = (vdiff(.984)-vdiff(.976))/.008
    if abs(dx)<.05:
        raise ValueError('Bias the differential stage before referring output error to its input.')
    cell = next(c for c in project['cells'] if c['name']==size+'_devices')
    supply,tail,left,right = [scalar(_named(cell,key)['value']) for key in ('VDD','ITAIL','RL','RR')]
    def referred(vleft):
        # The fixed tail current is the sum of both measured load currents.
        vright = supply-right*(tail-(supply-vleft)/left)
        return (vleft-vright)/dx*1e3
    return vdiff(.98)/dx*1e3,[referred(row['measurement']) for row in r[size+'_trials']['study_rows']]


def mismatch(p,r):
    from statistics import fmean, stdev

    results = {}
    for size in ('small','large'):
        systematic,samples = offset_samples(p,r,size)
        passed = sum(abs(v)<=8 for v in samples)
        results[size] = {'Input-referred systematic shift (mV)':systematic,
                         'Sample mean input-referred error (mV)':fmean(samples),
                         'Sample input-referred sigma (mV)':stdev(samples),
                         'Within ±8 mV (of 64)':passed}
    return results


def comparator(p,r):
    measures = {}
    for name in BENCHES['comparator']:
        w = r[name]
        xs = w['x']
        out = [n-p for n,p in zip(_series(w,'outn'),_series(w,'outp'))]
        decision = _cross(xs,out,.9,20e-9)
        peaks = [abs(a-b) for net,ref in [('inp','srcp'),('inn','srcn')]
                 for t,a,b in zip(xs,_series(w,net),_series(w,ref)) if 20e-9<=t<=40e-9]
        measures[name] = {'Decision delay (ns)':(decision-20e-9)*1e9,
                          'Peak input kickback (mV)':max(peaks)*1e3,'Final output difference (V)':out[-1]}
    return measures


def _code(voltage,weights):
    result = 0
    for bit,value in reversed(list(enumerate(weights))):
        if voltage>=value:
            voltage -= value
            result |= 1<<bit
    return result


def sar(p,r):
    dut = _dut(p,'fast_acquisition')
    caps = [scalar(_named(dut,'C'+str(i))['value']) for i in range(4)]
    total = sum(caps)+scalar(_named(dut,'CDUMMY')['value'])
    if total<=0:
        raise ValueError('Use a nonzero sampling capacitance.')
    results = {}
    for name in BENCHES['sar-fault']:
        w = r[name]
        hold = _voltage(w,'hold',49.8e-9)
        later = _voltage(w,'hold',70e-9)
        increment = _voltage(w,'hold',96e-9)-later
        weights = [1.6*c/total for c in caps[:3]]+[increment]
        results[name] = {'Acquisition error (mV)':abs(hold-_voltage(w,'drive',49.8e-9))*1e3,
                         'Hold pedestal (mV)':(later-hold)*1e3,'MSB step (V)':increment,
                         'Sampled kT/C noise (µV RMS)':math.sqrt(1.380649e-23*300.15/total)*1e6,
                         'Estimated code at 0.76 V':_code(.76,weights)}
    return results


def ldo(p,r):
    results = {}
    w = r['dropout_sweep']
    xs,ys = w['x'],_series(w,'out')
    reached = next((i for i,v in enumerate(ys) if 1.176<=v<=1.224),None)
    if reached is None or reached==0:
        raise ValueError('The supply sweep must show both dropout and regulation.')
    results['dropout_sweep'] = {'First in regulation supply (V)':xs[reached],
                                 'Headroom at that point (mV)':(xs[reached]-ys[reached])*1e3,
                                 'Final regulated output (V)':ys[-1]}
    for name in BENCHES['ldo'][1:]:
        w = r[name]
        begin = 1e-6 if name=='supply_startup' else 3e-6
        xs,ys = w['x'],_series(w,'out')
        tail = [value for t,value in zip(xs,ys) if t>=begin]
        baseline = 1.2 if name=='supply_startup' else _voltage(w,'out',2.9e-6)
        try:
            recovery = _settled(xs,ys,1.2,.024,begin)*1e6
        except ValueError:
            recovery = None
        results[name] = {'Maximum deviation (mV)':max(abs(y-baseline) for y in tail)*1e3,
                         'Peak output (V)':max(tail),'Final output (V)':ys[-1],
                         'Return to 2% band (µs)':recovery}
    return results


def route(p,r):
    case = r['route_comparison']
    results = {}
    for side in ('before','after'):
        w = case[side+'_waveform']
        results[side] = {'2% settling (ps)':_settled(w['x'],_series(w,'vout'),1.8,.036,10e-12)*1e12}
    results['after']['Extracted route resistance (Ω)'] = sum(v['value'] for v in case['extraction']['resistors'])
    results['after']['Added capacitance (fF)'] = sum(v['value'] for v in case['extraction']['capacitors'])*1e15
    return results


READOUTS = {'differential':differential,'input-pairs':input_pairs,'gain':gain,'slew':slew,'noise':noise,
            'mismatch':mismatch,'comparator':comparator,'sar-fault':sar,'sar-repair':sar,'ldo':ldo,
            'route-baseline':route,'route-repair':route}


def collect(p,step,rows):
    from .student_hub import captured

    saved = {}
    evidence = []
    for name in run_names(step):
        if step=='mismatch' or step.startswith('route-'):
            tag = dict(project='interview',stage=step,bench=name)
            key = design_digest(p)
            matches = [r for r in rows if r.get('state')=='Complete' and r['job'].get('student_analog')==tag
                       and r.get('result',{}).get('design_hash')==key]
            if not matches:
                raise ValueError('Run the exercise again after your latest edits.')
            job,result,record = captured(matches[-1])
            if job.get('student_analog')!=tag or design_digest(job['project'])!=key:
                raise ValueError('The saved data belongs to another experiment.')
        else:
            job,result,record = _latest(p,'interview',step,name,rows)
        evidence.append(record)
        saved[name] = result
    return saved,evidence


def assess(step,values):
    if step=='differential':
        group = values['Differential sweep']
        passed = group['Left share at −240 mV (%)']<20 and group['Left share at +240 mV (%)']>80
    elif step=='input-pairs':
        n,p = (values[k] for k in ('NMOS','PMOS'))
        current = n['Tail current at 0.70 V (µA)']
        passed = (p['Lower input limit (V)']<n['Lower input limit (V)']
                  and n['Upper input limit (V)']>p['Upper input limit (V)']
                  and .8*current<=p['Tail current at 0.70 V (µA)']<=1.2*current)
    elif step=='gain':
        passed = values['Drain at 0.80 V']['Intrinsic gain (V/V)']>3*values['Drain at 0.08 V']['Intrinsic gain (V/V)']
    elif step=='slew':
        passed = (values['heavy_load_step']['2% settling (ns)']>values['large_step']['2% settling (ns)']
                  and values['heavy_load_fall']['10–90% transition (ns)']>values['falling_step']['10–90% transition (ns)'])
    elif step=='noise':
        key = 'Integrated input noise (µV RMS)'
        passed = values['high_source_resistance'][key]>values['low_source_resistance'][key]
    elif step=='mismatch':
        key = 'Sample input-referred sigma (mV)'
        passed = 0<values['large'][key]<.75*values['small'][key]
    elif step=='comparator':
        passed = values['small_overdrive']['Decision delay (ns)']>values['large_overdrive']['Decision delay (ns)']
    elif step.startswith('sar-'):
        fast,slow = values['fast_acquisition'],values['slow_acquisition']
        good_msb = abs(fast['MSB step (V)']-.8)<=.025
        repaired = step=='sar-repair'
        passed = (fast['Acquisition error (mV)']<15<slow['Acquisition error (mV)']
                  and fast['Sampled kT/C noise (µV RMS)']<=60 and good_msb==repaired
                  and (fast['Estimated code at 0.76 V']==7)==repaired)
    elif step=='ldo':
        passed = all(values[name]['Return to 2% band (µs)'] is not None
                     for name in ('capacitor_esr','supply_step','supply_startup'))
    else:
        passed = (values['before']['2% settling (ps)']<ROUTE_TARGET_PS
                  and (values['after']['2% settling (ps)']<=ROUTE_TARGET_PS)==(step=='route-repair'))
    if not passed:
        raise ValueError('Open Results, compare the saved measurements with the exercise target, and run again.')


def check(p,step,rows):
    results,evidence = collect(p,step,rows)
    values = READOUTS[step](p,results)
    if not all(v is None or math.isfinite(v) for group in values.values() for v in group.values()):
        raise ValueError('The exercise requires finite measured values.')
    assess(step,values)
    return dict(interview_measurements=values,analog_runs=evidence)
