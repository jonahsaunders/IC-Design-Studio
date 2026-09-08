from __future__ import annotations
import cmath, ctypes, math, sys
from pathlib import Path
from .model import scalar,flatten,digest,design_digest,now
from .build_info import ENGINE_SOURCE_HASH

from .native_core import load_native_core

CORE = load_native_core()

def solve(a,b):
    n=len(b)
    if not n: return []
    if CORE is not None and not any(isinstance(v,complex) for row in a for v in row) and not any(isinstance(v,complex) for v in b):
        aa=(ctypes.c_double*(n*n))(*(v for row in a for v in row)); bb=(ctypes.c_double*n)(*b); x=(ctypes.c_double*n)()
        if CORE.ic_solve(n,aa,bb,x): raise ValueError('Singular circuit: check floating nets and ideal-source loops.')
        return list(x)
    a=[list(row)+[v] for row,v in zip(a,b)]
    for k in range(n):
        p=max(range(k,n),key=lambda i:abs(a[i][k]))
        if abs(a[p][k])<1e-24: raise ValueError('Singular circuit: check floating nets and ideal-source loops.')
        a[k],a[p]=a[p],a[k]
        for i in range(k+1,n):
            f=a[i][k]/a[k][k]
            if f:
                for j in range(k+1,n+1): a[i][j]-=f*a[k][j]
    x=[0]*n
    for i in range(n-1,-1,-1): x[i]=(a[i][n]-sum(a[i][j]*x[j] for j in range(i+1,n)))/a[i][i]
    return x

def source(d,t=0,override=None):
    if override is not None: return override
    s=d['source']; low=scalar(s['low']); high=scalar(s['high']); period=scalar(s['period']); delay=scalar(s['delay'])
    if s['type']=='dc': return scalar(d['value'])
    if s['type']=='sine': return low+(high-low)*math.sin(2*math.pi*(t-delay)/period)
    return high if t>=delay and (t-delay)%period<period*scalar(s['duty']) else low

def mos_current(d,vd,vg,vs):
    pol=1 if d['kind']=='NMOS' else -1
    vds=pol*(vd-vs); vgs=pol*(vg-vs); sign=1
    if vds<0: vgs-=vds; vds=-vds; sign=-1
    pa=d['params']; over=vgs-scalar(pa['vto']); beta=scalar(pa['kp'])*scalar(pa['w'])/scalar(pa['l'])
    if over<=0: return 0.0
    current=beta*((over*vds-vds*vds/2) if vds<over else over*over/2)*(1+scalar(pa['lambda'])*vds)
    return pol*sign*current

class Circuit:
    def __init__(self,p,cid=None,temperature=27):
        from .components import require_implementations
        require_implementations(p,cid or p['top'])
        self.ds=flatten(p,cid); self.nodes=sorted({n for d in self.ds for n in d['nets'].values()}-{'0'})
        from .catalog import binding_for
        if any(binding_for(p['pdk'],d) for d in self.ds):raise ValueError('The active PDK binds device models. Choose ngspice to use those models.')
        if temperature<=-273.15:raise ValueError('Temperature must exceed absolute zero.')
        if temperature!=27 and any(d['kind'] in ('NMOS','PMOS') for d in self.ds):raise ValueError('MOS temperature sweeps require ngspice and temperature-capable models.')
        for d in self.ds:
            if d['kind']=='R':
                delta=temperature-27;pa=d.get('params',{});factor=1+scalar(pa.get('tc1',0))*delta+scalar(pa.get('tc2',0))*delta*delta
                if factor<=0:raise ValueError('Temperature coefficients produce a non-positive resistance.')
                d['value']=str(scalar(d['value'])*factor)
        self.index={n:i for i,n in enumerate(self.nodes)}; self.branches={d['name']:len(self.nodes)+j for j,d in enumerate(d for d in self.ds if d['kind'] in ('V','L'))}; self.n=len(self.nodes)+len(self.branches)
        if not self.ds: raise ValueError('Add circuit devices before running an analysis.')
        if self.n>80: raise ValueError('Built-in solver is limited to 80 unknowns. Use ngspice for larger circuits.')
        if not any('0' in d['nets'].values() for d in self.ds): raise ValueError('A ground net (0) is required.')
        self.nonlinear=any(d['kind'] in ('NMOS','PMOS') for d in self.ds)
    def voltage(self,x,n): return 0 if n=='0' else x[self.index[n]]
    def system(self,guess,t=0,dt=None,previous=None,freq=None,override=None,noise=None):
        n=self.n; a=[[0.0]*n for _ in range(n)]; b=[0.0]*n; ac=freq is not None
        def add(i,j,v):
            if i is not None and j is not None: a[i][j]+=v
        def inj(i,v):
            if i is not None: b[i]+=v
        def conduct(ip,im,g): add(ip,ip,g);add(im,im,g);add(ip,im,-g);add(im,ip,-g)
        for i in range(len(self.nodes)): a[i][i]=1e-12
        for d in self.ds:
            k=d['kind']; nets=d['nets']; inds={pin:self.index.get(net) for pin,net in nets.items()}
            ip=inds.get('p'); im=inds.get('n')
            if k=='R': conduct(ip,im,1/scalar(d['value']))
            elif k=='C':
                if ac: conduct(ip,im,2j*math.pi*freq*scalar(d['value']))
                elif dt:
                    g=scalar(d['value'])/dt; conduct(ip,im,g); v=self.voltage(previous,nets['p'])-self.voltage(previous,nets['n']); inj(ip,g*v);inj(im,-g*v)
            elif k in ('V','L'):
                q=self.branches[d['name']]; add(ip,q,1);add(im,q,-1);add(q,ip,1);add(q,im,-1)
                if k=='V':
                    val=(0 if noise else scalar(d['source']['ac'])) if ac else source(d,t,override.get(d['name']) if override else None); b[q]=val
                elif ac: a[q][q]=-2j*math.pi*freq*scalar(d['value'])
                elif dt: a[q][q]=-scalar(d['value'])/dt; b[q]=-scalar(d['value'])/dt*previous[q]
            elif k=='I':
                val=(0 if noise else scalar(d['source']['ac'])) if ac else source(d,t,override.get(d['name']) if override else None);inj(ip,-val);inj(im,val)
            elif k in ('NMOS','PMOS'):
                values=[self.voltage(guess,nets[pin]) for pin in ('d','g','s')]; current=mos_current(d,*values); deriv=[]
                for j in range(3):
                    vp=values.copy();vm=values.copy();vp[j]+=1e-6;vm[j]-=1e-6
                    deriv.append((mos_current(d,*vp)-mos_current(d,*vm))/2e-6)
                for pin,g in zip(('d','g','s'),deriv): add(inds['d'],inds[pin],g);add(inds['s'],inds[pin],-g)
                if not ac:
                    ieq=current-sum(g*v for g,v in zip(deriv,values));inj(inds['d'],-ieq);inj(inds['s'],ieq)
            if noise and d['name']==noise: inj(ip,-1);inj(im,1)
        return a,b
    def point(self,t=0,dt=None,previous=None,override=None,initial=None):
        x=list(initial if initial is not None else [0.0]*self.n)
        for it in range(120):
            a,b=self.system(x,t,dt,previous,override=override); y=solve(a,b)
            if any(not math.isfinite(v) or abs(v)>1e15 for v in y): raise ValueError('Analysis diverged. Check device values and source connections.')
            delta=max([abs(u-v) for u,v in zip(y,x)]+[0])
            if not self.nonlinear or delta<1e-8: return y
            scale=min(1.0,0.3/delta); x=[v+scale*(u-v) for u,v in zip(y,x)]
        raise ValueError('MOS operating point did not converge after 120 iterations. Use ngspice or revise bias values.')

def run(p,cid,settings,progress=lambda *_:None):
    c=Circuit(p,cid,float(settings.get('temperature',27))); typ=settings['type']; xs=[]; data={n:[] for n in c.nodes}; op=c.point(); phase={}
    def record(x,y):
        xs.append(x)
        for n in c.nodes: data[n].append(y[c.index[n]])
    if typ=='op': record(0,op)
    elif typ=='tran':
        stop=scalar(settings['stop']); step=scalar(settings['step'])
        if not 0<step<=stop or stop/step>20000: raise ValueError('Transient needs positive stop/step and at most 20,000 steps.')
        steps=math.ceil(stop/step); previous=op; record(0,op)
        for i in range(1,steps+1):
            t=min(i*step,stop); dt=t-xs[-1]; previous=c.point(t,dt,previous,initial=previous);record(t,previous)
            if i%max(1,steps//100)==0: progress(i/steps,f'Transient point {i}/{steps}')
    elif typ=='dc':
        start=scalar(settings['dc_start']);stop=scalar(settings['dc_stop']);step=scalar(settings['dc_step']);src=settings['source']
        if not any(d['name']==src and d['kind'] in ('V','I') for d in c.ds): raise ValueError('DC sweep source is not a voltage/current source in this cell.')
        if step==0 or (stop-start)/step<0 or abs((stop-start)/step)>5000: raise ValueError('Invalid DC sweep: check direction and keep below 5,001 points.')
        count=math.floor((stop-start)/step+1e-9)+1; previous=op
        for i in range(count):
            v=start+i*step; previous=c.point(override={src:v},initial=previous);record(v,previous)
            if i%max(1,count//100)==0: progress((i+1)/count,f'DC point {i+1}/{count}')
    elif typ in ('ac','noise'):
        start=scalar(settings['start']);end=scalar(settings['end']);points=int(settings['points'])
        if not 0<start<end or not 2<=points<=1000: raise ValueError('Frequency range must increase from >0, with 2–1,000 points.')
        if typ=='noise' and c.nonlinear: raise ValueError('Built-in noise supports resistor thermal noise in linear RLC circuits only. Use an external noise-capable engine for MOS noise.')
        if typ=='noise' and float(settings.get('temperature',27))<=-273.15: raise ValueError('Temperature must exceed absolute zero.')
        phase={n:[] for n in c.nodes}
        for i in range(points):
            f=start*(end/start)**(i/(points-1));xs.append(f)
            if typ=='ac':
                a,b=c.system(op,freq=f);y=solve(a,b)
                for n in c.nodes:
                    v=y[c.index[n]];data[n].append(abs(v));phase[n].append(math.degrees(cmath.phase(v)))
            else:
                power=[0.0]*len(c.nodes)
                for d in c.ds:
                    if d['kind']!='R': continue
                    a,b=c.system(op,freq=f,noise=d['name']);y=solve(a,b);psd=4*1.380649e-23*(273.15+float(settings.get('temperature',27)))/scalar(d['value'])
                    for j in range(len(c.nodes)): power[j]+=abs(y[j])**2*psd
                for n in c.nodes: data[n].append(math.sqrt(power[c.index[n]]))
            if i%max(1,points//100)==0: progress((i+1)/points,f'Frequency point {i+1}/{points}')
    else: raise ValueError('Unsupported analysis.')
    return {'schema':1,'created':now(),'engine':'IC Studio teaching solver 0.1.0','engine_hash':digest({'implementation':ENGINE_SOURCE_HASH,'model':'square-law-no-body-effect'}),'project_id':p['id'],'revision':p['revision'],'design_hash':design_digest(p),'pdk_hash':digest(p['pdk']),'rule_hash':digest(p['pdk']['layers']),'cell_id':cid,'settings':settings,'x':xs,'x_label':{'op':'Operating point','tran':'Time (s)','dc':'Source value (V or A)','ac':'Frequency (Hz)','noise':'Frequency (Hz)'}[typ],'y_label':'Noise (V/√Hz)' if typ=='noise' else 'Voltage (V)','traces':data,'phase':phase,'operating_point':{n:op[j] for j,n in enumerate(c.nodes)},'warnings':['Generic educational models; no foundry qualification. MOS body effect, subthreshold current and device capacitances are not modeled.','1 pS conductance is added at each node for numeric conditioning.']}
