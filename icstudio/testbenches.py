"""Saved electrical testbenches and measurements shared by pre/post-layout runs."""
from pathlib import Path
import math,re,json,cmath
from .model import clone,uid,scalar,NAME,NET,atomic_write,design_digest


def get(project,key):
    found=[t for t in project.get('testbenches',[]) if key in (t['id'],t['name'])]
    if len(found)!=1:raise ValueError('Choose one saved testbench.')
    return found[0]


def validate_testbenches(p,objid=lambda _:None):
    benches=p.get('testbenches',[]);by={c['id']:c for c in p['cells']};names=set()
    if not isinstance(benches,list) or len(benches)>50:raise ValueError('A project supports up to 50 saved testbenches.')
    for t in benches:
        objid(t['id']);name=t.get('name','')
        if not NAME.fullmatch(name) or name.casefold() in names:raise ValueError('Testbench names must be unique identifiers.')
        names.add(name.casefold())
        if t.get('bench_cell') not in by or t.get('dut_cell') not in by or t['bench_cell']==t['dut_cell']:raise ValueError('Testbench and circuit must be separate existing cells.')
        bench=by[t['bench_cell']];dut=by[t['dut_cell']]
        instances=[d for d in bench['devices'] if d['kind']=='X']
        if len(instances)!=1 or instances[0]['id']!=t.get('dut_instance') or instances[0]['cell']!=dut['id']:raise ValueError('A saved bench needs exactly one circuit instance; put hierarchy inside the circuit cell.')
        if instances[0].get('parameters'):raise ValueError('Use a concrete circuit cell for physical verification; testbench instance parameter overrides are unsupported.')
        if any(d['kind'] not in ('R','C','L','V','I','X') for d in bench['devices']):raise ValueError('Testbench fixtures support sources and R/C/L loads. Put silicon devices inside the circuit cell.')
        nets={n for d in bench['devices'] for n in d['nets'].values()}
        if '0' not in nets:raise ValueError('Ground the testbench using net 0.')
        a=t.get('analysis',{});typ=a.get('type')
        if typ not in ('tran','op','ac','dc'):raise ValueError('Saved testbenches support transient, operating point, AC and DC.')
        if scalar(a.get('temperature',27))<=-273.15:raise ValueError('Invalid testbench temperature.')
        if not isinstance(a.get('corner','nominal'),str):raise ValueError('Choose a model corner.')
        if typ=='tran':
            if not 0<scalar(a.get('step',0))<=scalar(a.get('stop',0)):raise ValueError('Transient step must be positive and no greater than stop time.')
            if scalar(a['stop'])/scalar(a['step'])>200000:raise ValueError('Use at most 200,000 requested transient intervals.')
            if type(a.get('uic',False)) is not bool:raise ValueError('Use initial conditions must be true or false.')
        elif typ=='ac':
            if not 0<scalar(a.get('start',0))<scalar(a.get('end',0)) or not 1<=int(a.get('points',0))<=10000:raise ValueError('Invalid AC range or points per decade.')
        elif typ=='dc':
            if not any(d['name']==a.get('source') and d['kind']=='V' for d in bench['devices']):raise ValueError('DC sweep requires a voltage source in the bench.')
            start,stop,step=[scalar(a.get(k,0)) for k in ('dc_start','dc_stop','dc_step')]
            if not step or (stop-start)*step<=0 or abs((stop-start)/step)>200000:raise ValueError('Invalid DC sweep range.')
        probes=t.get('probes',[])
        if not probes or len(probes)>64 or len(probes)!=len(set(probes)) or any(n not in nets or n=='0' for n in probes):raise ValueError('Choose 1–64 distinct non-ground testbench nets to observe.')
        for n,v in t.get('initial_conditions',{}).items():
            if typ!='tran' or n not in nets or n=='0':raise ValueError('Initial conditions require a transient bench net.')
            scalar(v)
        measures=t.get('measurements',[]);mn=set()
        if len(measures)>64:raise ValueError('At most 64 measurements per bench.')
        for m in measures:
            if not NAME.fullmatch(m.get('name','')) or m['name'].casefold() in mn:raise ValueError('Measurement names must be unique identifiers.')
            mn.add(m['name'].casefold())
            kind=m.get('kind')
            if kind not in ('frequency','delay','range','voltage','current'):raise ValueError('Supported measurements: frequency, delay, range, voltage and source current.')
            if kind=='current':
                if not any(d['kind']=='V' and d['name']==m.get('source') for d in bench['devices']):raise ValueError('Current measurements need a voltage source in the fixture (positive from its + to − terminal).')
            elif m.get('node') not in probes:raise ValueError('Measurement nodes must be saved probes.')
            if m.get('reference') and (kind!='voltage' or m['reference'] not in probes):raise ValueError('A differential voltage reference must be another saved probe.')
            if kind in ('frequency','delay') and typ!='tran':raise ValueError('Frequency and delay need transient analysis.')
            if kind=='delay' and (m.get('input') not in probes or m.get('input')==m['node']):raise ValueError('Delay requires a different saved input probe.')
            if kind in ('frequency','delay'):scalar(m.get('threshold','0.9'))
            if kind=='frequency' and not 2<=int(m.get('min_cycles',3))<=10000:raise ValueError('Frequency requires at least two complete cycles.')
            if kind=='frequency' and not 0<scalar(m.get('max_period_variation',.2))<=1:raise ValueError('Period variation must be in (0, 1].')
            if 'min' in m and 'max' in m and scalar(m['min'])>scalar(m['max']):raise ValueError('Measurement minimum exceeds maximum.')
            for key in ('min','max','start','stop','at'):
                if key in m:scalar(m[key])
            if typ=='tran' and not 0<=scalar(m.get('start',0))<scalar(m.get('stop',a['stop']))<=scalar(a['stop']):raise ValueError('Measurement window must fit within the transient.')
        if t.get('characterization') is not None:
            if type(t['characterization'].get('compare_layout',False)) is not bool:raise ValueError('Layout comparison must be enabled or disabled.')
            from .studies import cases
            cases(p,t['bench_cell'],t['characterization'])


def create(p,bench_cid,name='bench'):
    c=next(c for c in p['cells'] if c['id']==bench_cid);xs=[d for d in c['devices'] if d['kind']=='X']
    if len(xs)!=1:raise ValueError('Select a testbench cell with one circuit instance and source/load components.')
    nets=sorted({n for d in c['devices'] for n in d['nets'].values()}-{'0'})
    return {'id':uid(),'name':name,'bench_cell':bench_cid,'dut_cell':xs[0]['cell'],'dut_instance':xs[0]['id'], 'analysis':{**clone(p['analysis']),'corner':p['analysis'].get('corner','nominal')},'initial_conditions':{},'probes':nets,'measurements':[]}


def native_subcircuit(p,cid):
    """Numerically resolved reference; project and physical hierarchy stay intact."""
    from .interchange import spice
    from .pdks import model_lines
    c=next(c for c in p['cells'] if c['id']==cid);models=set(model_lines(p['pdk'],'nominal'))
    lines=[line for line in spice(p,cid,hierarchical=False).splitlines() if line not in models and line.strip().lower()!='.end']
    return '* Numerically resolved schematic reference\n.subckt '+c['name']+' '+' '.join(c['ports'])+'\n'+'\n'.join(lines)+'\n.ends '+c['name']+'\n'


def deck(p,t,subcircuit_path,ports=None):
    from .interchange import spice,spice_name
    from .sky130_flow import subcircuit
    by={c['id']:c for c in p['cells']};bench=clone(by[t['bench_cell']]);dut=by[t['dut_cell']];instance=next(d for d in bench['devices'] if d['id']==t['dut_instance'])
    ports=ports or dut['ports']
    if len(ports)!=len(dut['ports']) or set(ports)!=set(dut['ports']):raise ValueError('Extracted circuit interface differs from the saved bench.')
    bench['devices']=[d for d in bench['devices'] if d['id']!=instance['id']]
    # Keep explicit native pin nets while removing the DUT from the fixture deck.
    for key in ('wires','labels','junctions','layout_pins','layout_instances'):bench.pop(key,None)
    q=clone(p);q.pop('testbenches',None);q['cells']=[bench];q['top']=bench['id'];q['analysis']=clone(t['analysis'])
    text=spice(q,bench['id'],t['analysis'],hierarchical=False);text=re.sub(r'^\.end\s*$','',text,flags=re.M|re.I)
    if t['analysis']['type']=='tran' and t['analysis'].get('uic'):text=re.sub(r'^(\.tran .+)$',r'\1 uic',text,flags=re.M)
    text+='\n.include "'+Path(subcircuit_path).resolve().as_posix()+'"\n'+spice_name(instance)+' '+' '.join(instance['nets'][port] for port in ports)+' '+dut['name']+'\n'
    if t.get('initial_conditions'):text+='.ic '+' '.join('v('+n+')='+str(scalar(v)) for n,v in t['initial_conditions'].items())+'\n'
    source_names={d['name']:spice_name(d) for d in bench['devices'] if d['kind']=='V'}
    current_sources=sorted({source_names[m['source']] for m in t.get('measurements',[]) if m['kind']=='current'})
    text+='.save '+' '.join(['v('+n+')' for n in t['probes']]+['i('+n+')' for n in current_sources])+'\n.end\n'
    return text


def crossings(xs,ys,threshold,edge='rising',start=-math.inf,stop=math.inf):
    out=[]
    for a,b,ya,yb in zip(xs,xs[1:],ys,ys[1:]):
        hit=ya<threshold<=yb if edge=='rising' else ya>threshold>=yb
        if hit and yb!=ya:
            x=a+(b-a)*(threshold-ya)/(yb-ya)
            if start<=x<=stop:out.append(x)
    return out


def measure(result,t):
    xs=result['x'];traces=result['traces'];rows=[];a=t['analysis']
    for m in t.get('measurements',[]):
        row={'name':m['name'],'kind':m['kind'],'status':'failed'};rows.append(row)
        try:
            ys=result.get('currents',{})[m['source'].lower()] if m['kind']=='current' else traces[m['node'].lower()]
            if m.get('reference'):
                other=traces[m['reference'].lower()]
                if a['type']=='ac':
                    ph=result['phase'];ys=[abs(cmath.rect(v,math.radians(angle))-cmath.rect(w,math.radians(theta))) for v,angle,w,theta in zip(ys,ph[m['node'].lower()],other,ph[m['reference'].lower()])]
                else:ys=[v-w for v,w in zip(ys,other)]
            start=scalar(m.get('start',0 if a['type']=='tran' else min(xs)));stop=scalar(m.get('stop',a['stop'] if a['type']=='tran' else max(xs)))
            kind=m['kind'];samples=[y for x,y in zip(xs,ys) if start<=x<=stop] if a['type']!='op' else ys
            if not samples:raise ValueError('No samples in the measurement window.')
            if kind=='frequency':
                edge=crossings(xs,ys,scalar(m.get('threshold','.9')),start=start,stop=stop);periods=[b-a for a,b in zip(edge,edge[1:])]
                if len(periods)<int(m.get('min_cycles',3)):raise ValueError('Too few complete cycles; check startup, supply and observation window.')
                average=sum(periods)/len(periods);variation=(max(periods)-min(periods))/average
                if variation>scalar(m.get('max_period_variation',.2)):raise ValueError('Oscillation period has not settled within the configured tolerance.')
                val=1/average;row.update(unit='Hz',cycles=len(periods),period_s=average,period_variation=variation)
            elif kind=='delay':
                threshold=scalar(m.get('threshold','.9'));delays=[]
                for input_edge,output_edge in (('rising','falling'),('falling','rising')):
                    ins=crossings(xs,traces[m['input'].lower()],threshold,input_edge,start,stop);outs=crossings(xs,ys,threshold,output_edge,start,stop)
                    for i,x in enumerate(ins):
                        after=[y for y in outs if y>=x and (i+1==len(ins) or y<ins[i+1])]
                        if after:delays.append(after[0]-x)
                if len(delays)<2:raise ValueError('Too few corresponding input/output transitions for inverting delay.')
                val=sum(delays)/len(delays);row.update(unit='s',transitions=len(delays))
            elif kind=='range':val=sum(samples)/len(samples);row.update(unit='V',minimum=min(samples),maximum=max(samples))
            else:
                if 'at' in m and a['type']!='op':
                    at=scalar(m['at']);pair=next(((x,y,z,w) for x,y,z,w in zip(xs,xs[1:],ys,ys[1:]) if min(x,y)<=at<=max(x,y)),None)
                    if pair is None:raise ValueError('Measurement coordinate is outside returned samples.')
                    x,y,z,w=pair;val=z if y==x else z+(w-z)*(at-x)/(y-x)
                else:val=ys[-1]
                row['unit']='A' if kind=='current' else 'V'
            if not math.isfinite(val):raise ValueError('Measurement is not finite.')
            row['value']=val;low=row.get('minimum',val);high=row.get('maximum',val)
            if 'min' in m and low<scalar(m['min']):raise ValueError('Measured result is below the configured minimum.')
            if 'max' in m and high>scalar(m['max']):raise ValueError('Measured result is above the configured maximum.')
            row['status']='passed'
        except (ValueError,KeyError,ZeroDivisionError) as exc:row['error']=str(exc)
    return {'status':'passed' if all(r['status']=='passed' for r in rows) else 'failed','samples':len(xs),'measurements':rows,'probes':t['probes']}


def simulate(p,t,executable,directory,subcircuit_path=None,ports=None,progress=lambda *_:None):
    from .engines import run_deck
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if subcircuit_path is None:
        subcircuit_path=directory/'schematic.spice';atomic_write(subcircuit_path,native_subcircuit(p,t['dut_cell']))
    path=directory/'testbench.cir';atomic_write(path,deck(p,t,subcircuit_path,ports))
    r=run_deck(p,t['bench_cell'],{'type':'deck','deck':str(path)},executable,directory,progress);r['x_label']={'tran':'Time (s)','op':'Operating point','ac':'Frequency (Hz)','dc':'Source value'}[t['analysis']['type']]
    from .interchange import spice_name
    fixture=next(c for c in p['cells'] if c['id']==t['bench_cell'])
    for d in fixture['devices']:
        if d['kind']=='V':
            for field in ('currents','current_phase'):
                if spice_name(d).lower() in r.get(field,{}):r[field][d['name'].lower()]=r[field][spice_name(d).lower()]
    r['testbench_id']=t['id'];r['settings']=clone(t['analysis']);r['measurements']=measure(r,t);r['warnings']=['Saved testbench: '+t['name']+'. '+('Extracted circuit' if ports else 'Schematic circuit')+'.']
    atomic_write(directory/'result.json',json.dumps(r,allow_nan=False));return r


def spice_testbench(p,t):
    """One SPICE file with the saved fixture and resolved circuit definition."""
    marker=Path('__studio_dut_definition__.spice').resolve()
    return deck(p,t,marker).replace('.include "'+marker.as_posix()+'"',native_subcircuit(p,t['dut_cell']).rstrip())
