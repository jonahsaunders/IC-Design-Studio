"""Measured electrical diagnostics; no inferred stability or manufacturing claims."""
import math
import re
from .model import clone, scalar, digest, design_digest, NET


def integrate(x, y):
    if len(x)!=len(y) or len(x)<2 or any(not math.isfinite(v) for v in x+y) or any(b<=a for a,b in zip(x,x[1:])):
        raise ValueError('Integration requires finite, increasing samples.')
    return sum((b-a)*(u+v)/2 for a,b,u,v in zip(x,x[1:],y,y[1:]))


def noise_report(variables, rows):
    if 'onoise_spectrum' not in variables or 'inoise_spectrum' not in variables:raise ValueError('Input/output noise spectra were not returned.')
    x=[float(r[0]) for r in rows]
    power={n:integrate(x,[float(r[j])**2 for r in rows]) for j,n in enumerate(variables) if n.startswith(('onoise_','inoise_','onoise.','inoise.'))}
    total=power['onoise_spectrum']; names=[n for n in power if n.startswith(('onoise_','onoise.')) and n!='onoise_spectrum']
    # SPICE returns both device totals and their component vectors. Prefix
    # parents are displayed as subtotals; they must not be added to children.
    # Indexed prefix lookup stays linear in name length for large extracted
    # networks, whose resistor noise vectors can number in the tens of thousands.
    name_set=set(names)
    parents={n[:i] for n in names for i,char in enumerate(n) if char in '._' and n[:i] in name_set}
    sources=[dict(vector=n,rms_V=math.sqrt(max(0,power[n])),fraction_of_output=power[n]/total if total>0 else None,
                  subtotal=n in parents) for n in names]
    sources.sort(key=lambda r:r['rms_V'],reverse=True)
    return dict(kind='noise',band_Hz=[x[0],x[-1]],output_rms_V=math.sqrt(max(0,total)),input_rms_V=math.sqrt(max(0,power['inoise_spectrum'])),
        contributors=sources,scope='Trapezoidal integration of squared amplitude density over the sampled band. Device subtotals overlap their components; do not sum all rows.')


def pole_zero_report(variables, rows):
    poles=[];zeros=[]
    for j,name in enumerate(variables):
        destination=poles if 'pole(' in name.lower() else zeros if 'zero(' in name.lower() else None
        if destination is None:continue
        for row in rows:
            z=complex(row[j])
            if not math.isfinite(z.real) or not math.isfinite(z.imag):raise ValueError('Nonfinite pole/zero result.')
            destination.append(dict(vector=name,real_rad_s=z.real,imag_rad_s=z.imag,frequency_Hz=abs(z)/(2*math.pi),right_half_plane=z.real>0))
    if not poles and not zeros:raise ValueError('No poles or zeros were returned for the selected transfer function.')
    return dict(kind='pole_zero',poles=poles,zeros=zeros,scope='Small-signal poles and zeros of the specified voltage transfer. Cancellations and unobserved modes can hide instability; this is not a full-loop stability proof.')


def loop_report(result, numerator, denominator, sign=1):
    """Return-ratio convention: the closed-loop characteristic is 1 + T."""
    if result.get('settings',{}).get('type')!='ac':raise ValueError('Loop margins require a saved AC injection fixture.')
    x=result['x']; traces=result['traces']; phase=result.get('phase',{})
    if numerator not in traces or denominator not in traces or numerator not in phase or denominator not in phase:raise ValueError('Select captured complex injection and return voltages.')
    if len(x)<2 or any(v<=0 for v in x) or any(b<=a for a,b in zip(x,x[1:])):raise ValueError('Loop analysis needs increasing positive frequencies.')
    if any(v<=0 for v in traces[denominator]) or any(v<=0 for v in traces[numerator]):raise ValueError('The sampled return ratio contains zero magnitude; refine the fixture or frequency sweep.')
    gain=[20*math.log10(a/b) for a,b in zip(traces[numerator],traces[denominator])]
    angles=[a-b+(180 if sign==-1 else 0) for a,b in zip(phase[numerator],phase[denominator])]
    if not len(gain)==len(angles)==len(x) or any(not math.isfinite(v) for v in gain+angles):raise ValueError('Incomplete complex loop data.')
    angles[0]=(angles[0]+180)%360-180
    for i in range(1,len(angles)):
        while angles[i]-angles[i-1]>180:angles[i]-=360
        while angles[i]-angles[i-1]<-180:angles[i]+=360
    unity=[];negative=[]
    for i in range(len(x)-1):
        def crossing(values,level):
            a,b=values[i],values[i+1]
            if a==b or not (min(a,b)<=level<=max(a,b)):return None
            if level==b and i<len(x)-2:return None
            t=(level-a)/(b-a);return t,math.exp(math.log(x[i])+t*math.log(x[i+1]/x[i]))
        c=crossing(gain,0)
        if c:
            t,hz=c;angle=angles[i]+t*(angles[i+1]-angles[i]);unity.append(dict(frequency_Hz=hz,phase_margin_deg=180+angle))
        for k in range(math.ceil((min(angles[i:i+2])+180)/360),math.floor((max(angles[i:i+2])+180)/360)+1):
            c=crossing(angles,-180+360*k)
            if c:
                t,hz=c;negative.append(dict(frequency_Hz=hz,gain_margin_dB=-(gain[i]+t*(gain[i+1]-gain[i]))))
    return dict(kind='loop',unity_crossings=unity,negative_real_crossings=negative,
        scope='User-declared return ratio T; characteristic 1 + T. Every sampled crossing is shown. Missing crossings mean unavailable margins, not infinite margin. Multiple crossings, open-loop RHP poles, and phase aliasing require Nyquist/fixture review.')


def startup_report(result, config):
    x=result['x']; values=result['traces'].get(config['output'])
    if not values or len(x)!=len(values) or len(x)<2:raise ValueError('Startup output was not captured.')
    lower,upper=scalar(config['minimum']),scalar(config['maximum'])
    tail=scalar(config.get('tail_fraction',.2));start=x[-1]-(x[-1]-x[0])*tail
    samples=[v for t,v in zip(x,values) if t>=start]
    if len(samples)<2:raise ValueError('The final startup window needs at least two saved samples.')
    passing=all(lower<=v<=upper for v in samples)
    last_bad=max((i for i,v in enumerate(values) if not lower<=v<=upper),default=-1)
    settled=x[last_bad+1] if passing and last_bad+1<len(x) else None
    return dict(kind='startup',passed=passing,final_V=values[-1],tail_min_V=min(samples),tail_max_V=max(samples),
        peak_V=max(values),settled_by_s=settled,window_s=[start,x[-1]],limits_V=[lower,upper],ramp_s=scalar(config['ramp']),
        initial_voltage_V=scalar(config.get('initial_voltage',0)),scope='Measured saved transient samples for this ramp and initial condition. Settling is known only through the end of this run; short excursions between samples may be missed.')


def bias_report(result):
    devices=[]
    for name,data in result.get('device_operating_point',{}).items():
        row=dict(device=name,region=data.get('region'),headroom_V=data.get('headroom'),gm_Id_per_V=None,
                 evidence=data.get('source','Simulator operating-point data'))
        if data.get('id') and data.get('gm') is not None:row['gm_Id_per_V']=abs(data['gm']/data['id'])
        if row['headroom_V'] is None and data.get('vds') is not None and data.get('vdsat') is not None:row['headroom_V']=abs(data['vds'])-abs(data['vdsat'])
        row['bias_status']=row['region'] or ('Below model VDSAT' if row['headroom_V']<0 else 'At/above model VDSAT') if row['headroom_V'] is not None else row['region'] or 'Region unavailable'
        devices.append(row)
    return dict(kind='bias',devices=devices,scope='Captured operating-point evidence. Model saturation headroom and weak/moderate/strong inversion are different properties; missing region data is not inferred from a universal gm/Id threshold.')


def validate_config(project,cid,config):
    from .native_analysis import sources
    kind=config['kind'];cell=next(c for c in project['cells'] if c['id']==cid)
    nets=set(cell.get('ports',[]))|{n for d in cell['devices'] for n in d.get('nets',{}).values()}|{'0'}
    def net(key):
        value=config.get(key,'')
        if not NET.fullmatch(value) or value not in nets:raise ValueError('Choose a connected net for '+key.replace('_',' ')+'.')
    if kind not in ('noise','pole_zero','startup','loop','bias'):raise ValueError('Unknown electrical diagnostic.')
    if kind in ('noise','pole_zero','startup'):net('output')
    if kind=='pole_zero':
        for key in ('input','input_return','output_return'):net(key)
        if config['input']==config['input_return'] or config['output']==config['output_return']:raise ValueError('Each transfer-function port needs two distinct nets.')
    if kind in ('noise','startup'):
        if not any(name==config.get('source') and typ=='V' for name,_,typ in sources(project,cid)):raise ValueError('Choose an independent voltage source in this cell.')
    if kind=='startup':
        net('initial_node')
        if scalar(config['minimum'])>scalar(config['maximum']):raise ValueError('Startup output limits must increase.')
        if not 0<scalar(config.get('tail_fraction',.2))<=1:raise ValueError('Startup tail fraction must be in (0, 1].')
        if not 0<scalar(config['ramp'])<scalar(config['stop']):raise ValueError('Supply ramp must be positive and shorter than the transient.')
        scalar(config['supply']);scalar(config.get('initial_voltage',0))
    if kind=='loop':
        net('numerator');net('denominator')
        if config.get('sign') not in (-1,1):raise ValueError('Choose the return-ratio polarity of your injection fixture.')


def alter_deck(project,cid,settings,text):
    """Edit only generated analyses/one top-level source, preserving model decks."""
    c=settings['diagnostic'];kind=c['kind'];validate_config(project,cid,c)
    if kind=='noise':return re.sub(r'(^\s*\.noise[^\n]*)$',r'\1 1',text,flags=re.M|re.I)
    if kind=='pole_zero':
        text=re.sub(r'^\s*\.(?:op|save)[^\n]*\n','',text,flags=re.M|re.I)
        return re.sub(r'^\s*\.end\s*$',f'.pz {c["input"]} {c["input_return"]} {c["output"]} {c["output_return"]} vol pz\n.end',text,flags=re.M|re.I)
    if kind=='startup':
        from .native_analysis import sources
        source=next(name for label,name,typ in sources(project,cid) if label==c['source']);lines=text.splitlines();level=0;found=0
        for i,line in enumerate(lines):
            parts=line.split()
            if not parts:continue
            if parts[0].lower()=='.subckt':level+=1
            elif parts[0].lower()=='.ends':level-=1
            elif level==0 and parts[0].lower()==source.lower():
                if len(parts)<4:raise ValueError('The startup source could not be identified.')
                if i+1<len(lines) and lines[i+1].lstrip().startswith('+'):raise ValueError('Simplify the multiline supply source before a startup study.')
                lines[i]=' '.join(parts[:3])+f' PWL(0 0 {scalar(c["ramp"]):.12g} {scalar(c["supply"]):.12g} {scalar(c["stop"]):.12g} {scalar(c["supply"]):.12g})';found+=1
        if found!=1:raise ValueError('Expected exactly one top-level startup supply.')
        text='\n'.join(lines)+'\n'
        text=re.sub(r'^\s*\.tran([^\n]*)$',r'.tran\1 uic',text,flags=re.M|re.I)
        return re.sub(r'^\s*\.end\s*$',f'.ic v({c["initial_node"]})={scalar(c.get("initial_voltage",0)):.12g}\n.end',text,flags=re.M|re.I)
    return text


def prepare(project,cid,plan,prepare_job,config,budget=100,ramps=None,initials=None):
    from . import analog_optimizer as opt
    config=clone(config);validate_config(project,cid,config)
    plan=clone(plan)
    if len(plan['entries'])!=1 or plan['entries'][0]['cell']!=cid or plan['entries'][0]['settings']['type']=='testbench':raise ValueError('Choose one saved graphical analysis for diagnostics. Its PVT conditions are retained.')
    entry=plan['entries'][0];kind=config['kind'];settings=entry['settings']
    settings['type']={'noise':'noise','pole_zero':'op','startup':'tran','loop':'ac','bias':'op'}[kind]
    settings.update({key:config[key] for key in ('start','end','points','stop','step') if key in config})
    if kind=='noise':settings.update(output=config['output'],noise_source=config['source'],source=config['source'])
    cases=[config]
    if kind=='startup':cases=[{**config,'ramp':r,'initial_voltage':v} for r in ramps or [config['ramp']] for v in initials or [config.get('initial_voltage',0)]]
    per=len(plan['corners'])*len(plan['temperatures'])*max(1,len(plan.get('voltages',[])))
    if len(cases)*per>budget:raise ValueError('Diagnostic cases exceed the simulation budget.')
    jobs=[];first=None
    for candidate,c in enumerate(cases,1):
        validate_config(project,cid,c)
        part=opt.prepare(project,cid,plan,dict(kind='analog_diagnostics',axes=[],budget=budget),prepare_job,_changes=[{}])
        if first is None:first=part
        for job in part['jobs']:
            if job['engine']!='ngspice' and kind!='bias':raise ValueError('This electrical diagnostic requires ngspice. Select ngspice in the saved analysis.')
            job['settings']['diagnostic']=clone(c)
            if kind=='pole_zero':job['settings']['type']='pz'
            if kind=='startup' and job['case']['labels'].get('voltage') is not None:job['settings']['diagnostic']['supply']=job['case']['labels']['voltage']
            job['case'].update(group=first['id'],index=len(jobs)+1,candidate=candidate,changes={'ramp_s':scalar(c['ramp']),'initial_V':scalar(c.get('initial_voltage',0))} if kind=='startup' else {})
            job['case']['fingerprint']=digest({k:v for k,v in job.items() if k!='case'});jobs.append(job)
    first.update(jobs=jobs,name='Electrical diagnostics · '+kind,advanced=dict(kind='diagnostics',diagnostic=kind,done=True));return first


def analyze(manifest,rows):
    from .variation_runs import latest
    current=latest(manifest,rows);data=[]
    for job in manifest['jobs']:
        row=current.get(job['case']['index'],{});result=row.get('result',{});state=row.get('state','Not queued');evidence=None
        if state=='Complete':
            valid=result.get('settings')==job['settings'] and result.get('design_hash')==design_digest(job['project']) and result.get('project_id')==manifest['project_id'] and result.get('cell_id')==job['cell']
            if job['engine']=='ngspice':valid=valid and result.get('engine_hash')==job['environment'].get('executable_sha256')
            evidence=result.get('diagnostics') if valid else None
            if not evidence:state='Invalid evidence'
        data.append(dict(index=job['case']['index'],condition=job['case']['labels'],scenario=job['case']['changes'],state=state,run_id=row.get('id'),evidence=evidence))
    return dict(rows=data,complete=all(r['state'] not in ('Not queued','Queued','Running','Stopping') for r in data),scope='Read-only diagnostics from the saved snapshot and simulator deck.')
