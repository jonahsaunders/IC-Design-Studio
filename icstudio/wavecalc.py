"""Bounded, dimension-aware waveform expressions. No Python evaluation or file access."""
import ast, bisect, cmath, math
from dataclasses import dataclass

ONE=(0,0,0); VOLT=(1,0,0); AMP=(0,1,0); SECOND=(0,0,1)
UNITS={'':ONE,'1':ONE,'V':VOLT,'A':AMP,'s':SECOND,'Hz':(0,0,-1),'W':(1,1,0),'Ohm':(1,-1,0),'S':(-1,1,0),'F':(-1,1,1),'V*s':(1,0,1),'V/s':(1,0,-1),'V/√Hz':(1,0,.5),'A/√Hz':(0,1,.5),'rad':ONE,'dB':ONE}

def unit_name(unit):return next((k for k,v in UNITS.items() if v==unit),str(unit))

def finite(v):
    z=complex(v)
    if not math.isfinite(z.real) or not math.isfinite(z.imag):raise ValueError('Expression produced a non-finite value.')
    return z.real if not z.imag else z

@dataclass
class Signal:
    values:list
    x:object=None
    unit:tuple=ONE
    domain:str='scalar'
    def real_values(self):
        if any(abs(complex(v).imag)>1e-12*max(1,abs(v)) for v in self.values):raise ValueError('Choose abs(), real(), imag() or phase() for a complex output.')
        return [float(complex(v).real) for v in self.values]

def parse(expression):
    if not isinstance(expression,str) or not expression.strip() or len(expression)>2000:raise ValueError('Enter an expression of 1–2,000 characters.')
    try:tree=ast.parse(expression,mode='eval')
    except SyntaxError as exc:raise ValueError('Invalid expression syntax.') from exc
    nodes=list(ast.walk(tree))
    if len(nodes)>256:raise ValueError('Expression is too complex.')
    permitted=(ast.Expression,ast.Call,ast.Name,ast.Load,ast.Constant,ast.BinOp,ast.UnaryOp,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow,ast.USub,ast.UAdd)
    if any(not isinstance(n,permitted) for n in nodes):raise ValueError('Only arithmetic and named waveform functions are allowed.')
    for n in nodes:
        if isinstance(n,ast.Call) and (not isinstance(n.func,ast.Name) or n.func.id not in FUNCTIONS or n.keywords):raise ValueError('Unknown waveform function or keyword argument.')
        if isinstance(n,ast.Constant) and (type(n.value) not in (str,int,float) or isinstance(n.value,str) and len(n.value)>200):raise ValueError('Unsupported literal.')
        if isinstance(n,ast.Name) and n.id not in FUNCTIONS|{'pi','x'}:raise ValueError('Unknown name: '+n.id+'. Use V("net") or I("source").')
    return tree.body

FUNCTIONS={'V','I','trace','abs','real','imag','phase','db20','unwrap','sqrt','sin','cos','exp','log','deriv','integ','fft','min','max','mean','rms','pp','final','at','crossing','settling','clip'}

def _pair(a,b):
    if not isinstance(a,Signal) or not isinstance(b,Signal):raise ValueError('Expected numeric arguments.')
    if a.x is not None and b.x is not None and (a.x!=b.x or a.domain!=b.domain):raise ValueError('Signals use different X axes; combine signals before changing their domain.')
    axis=a if a.x is not None else b
    count=len(axis.values) if axis.x is not None else 1
    return (a.values*count if a.x is None else a.values,b.values*count if b.x is None else b.values,axis.x,axis.domain)

def binary(a,b,op):
    av,bv,x,domain=_pair(a,b)
    if isinstance(op,(ast.Add,ast.Sub)):
        if a.unit!=b.unit:raise ValueError('Addition/subtraction requires matching units.')
        unit=a.unit;fn=(lambda x,y:x+y) if isinstance(op,ast.Add) else (lambda x,y:x-y)
    elif isinstance(op,ast.Mult):unit=tuple(x+y for x,y in zip(a.unit,b.unit));fn=lambda x,y:x*y
    elif isinstance(op,ast.Div):unit=tuple(x-y for x,y in zip(a.unit,b.unit));fn=lambda x,y:x/y
    else:
        if b.x is not None or b.unit!=ONE or abs(complex(b.values[0]).imag) or abs(b.values[0])>8:raise ValueError('Power requires a constant real exponent between -8 and 8.')
        unit=tuple(v*b.values[0] for v in a.unit);fn=lambda x,y:x**y
    try:return Signal([finite(fn(x,y)) for x,y in zip(av,bv)],x,unit,domain)
    except (ArithmeticError,OverflowError) as exc:raise ValueError('Expression contains division by zero or an invalid numeric operation.') from exc

def evaluate(expression,result):
    axis=list(result.get('x',[]));n=len(axis)
    if not 1<=n<=200000:raise ValueError('Expressions require 1–200,000 saved samples.')
    typ=result.get('settings',{}).get('type');domain='frequency' if typ in ('ac','noise') or 'frequency' in result.get('x_label','').lower() else 'time' if typ=='tran' or 'time' in result.get('x_label','').lower() else 'sweep'
    xunit=(0,0,-1) if domain=='frequency' else SECOND if domain=='time' else VOLT
    def visit(node):
        if isinstance(node,ast.Constant):return node.value if isinstance(node.value,str) else Signal([finite(node.value)])
        if isinstance(node,ast.Name):
            if node.id not in ('pi','x'):raise ValueError('A function name must be called with arguments.')
            return Signal([math.pi]) if node.id=='pi' else Signal(axis,axis,xunit,domain)
        if isinstance(node,ast.UnaryOp):
            a=visit(node.operand)
            if not isinstance(a,Signal):raise ValueError('Expected a numeric argument.')
            return Signal([(-v if isinstance(node.op,ast.USub) else v) for v in a.values],a.x,a.unit,a.domain)
        if isinstance(node,ast.BinOp):return binary(visit(node.left),visit(node.right),node.op)
        if isinstance(node,ast.Call):
            name=node.func.id;args=[visit(a) for a in node.args]
            if name in ('V','I','trace'):
                if len(args)!=1 or not isinstance(args[0],str):raise ValueError(name+' requires one quoted signal name.')
                key=args[0];bank=result.get('currents' if name=='I' else 'traces',{});key=next((k for k in bank if k.casefold()==key.casefold()),key)
                if key=='0' and name=='V':return Signal([0.]*n,axis,VOLT,domain)
                if key not in bank or len(bank[key])!=n:raise ValueError('Signal unavailable: '+args[0])
                vals=bank[key];ph=result.get('current_phase' if name=='I' else 'phase',{}).get(key)
                if ph is not None:
                    if len(ph)!=n:raise ValueError('Phase sample count differs.')
                    vals=[cmath.rect(v,math.radians(p)) for v,p in zip(vals,ph)]
                unit=AMP if name=='I' else (1,0,.5) if typ=='noise' else VOLT
                if name=='trace':unit=tuple(result.get('trace_units',{}).get(key,VOLT))
                return Signal([finite(v) for v in vals],axis,unit,domain)
            return function(name,args,xunit)
        raise ValueError('Unsupported expression.')
    try:
        value=visit(parse(expression))
        if not isinstance(value,Signal):raise ValueError('Expression must produce a numeric result.')
        return value
    except (TypeError,ZeroDivisionError,OverflowError,IndexError) as exc:raise ValueError('Invalid waveform function arguments or numeric domain.') from exc

def scalar_arg(a):
    if not isinstance(a,Signal) or a.x is not None:raise ValueError('Expected a scalar argument.')
    return a.real_values()[0]

def function(name,args,xunit):
    expected={'at':2,'crossing':3,'settling':3,'clip':3}.get(name,1)
    if len(args)!=expected or not isinstance(args[0],Signal):raise ValueError(f'{name} requires {expected} numeric argument(s).')
    a=args[0];values=a.values
    if a.domain=='frequency':xunit=(0,0,-1)
    elif a.domain=='time':xunit=SECOND
    if name in ('min','max','mean','rms','pp','final'):
        real=a.real_values()
        val={'min':lambda:min(real),'max':lambda:max(real),'mean':lambda:sum(real)/len(real),'rms':lambda:math.sqrt(sum(v*v for v in real)/len(real)),'pp':lambda:max(real)-min(real),'final':lambda:real[-1]}[name]()
        return Signal([val],unit=a.unit)
    if name in ('at','crossing','settling','deriv','integ','fft','clip'):
        if a.x is None or len(a.x)<2 or any(b<=c for c,b in zip(a.x,a.x[1:])):raise ValueError(name+' requires a strictly increasing sampled X axis.')
    if name in ('at','clip','crossing','settling'):
        expected=xunit if name in ('at','clip') else a.unit
        checked=args[1:] if name in ('clip','settling') else args[1:2]
        if any(not isinstance(arg,Signal) or arg.unit not in (ONE,expected) for arg in checked):raise ValueError('Coordinate or threshold argument has incompatible units.')
        if name=='crossing' and args[2].unit!=ONE:raise ValueError('Crossing index must be dimensionless.')
    if name=='at':
        x=scalar_arg(args[1])
        if not a.x[0]<=x<=a.x[-1]:raise ValueError('Requested X is outside the saved samples.')
        i=max(1,bisect.bisect_left(a.x,x));x0,x1=a.x[i-1:i+1]
        weight=(math.log(x/x0)/math.log(x1/x0)) if a.domain=='frequency' and x0>0 else (x-x0)/(x1-x0)
        return Signal([finite(values[i-1]+weight*(values[i]-values[i-1]))],unit=a.unit)
    if name=='clip':
        lo,hi=map(scalar_arg,args[1:]);indices=[i for i,x in enumerate(a.x) if lo<=x<=hi]
        if len(indices)<2:raise ValueError('Selected interval contains fewer than two samples.')
        return Signal([values[i] for i in indices],[a.x[i] for i in indices],a.unit,a.domain)
    if name=='crossing':
        level=scalar_arg(args[1]);number=scalar_arg(args[2]);real=a.real_values();hits=[]
        if number==0 or int(number)!=number:raise ValueError('Crossing index is positive for rising and negative for falling crossings.')
        for i,(left,right) in enumerate(zip(real,real[1:])):
            if (number>0 and left<level<=right) or (number<0 and left>level>=right):
                w=(level-left)/(right-left)
                hits.append(a.x[i]*(a.x[i+1]/a.x[i])**w if a.domain=='frequency' and a.x[i]>0 else a.x[i]+w*(a.x[i+1]-a.x[i]))
        if len(hits)<abs(number):raise ValueError('Requested crossing was not observed.')
        return Signal([hits[int(abs(number))-1]],unit=xunit)
    if name=='settling':
        target,tolerance=map(scalar_arg,args[1:]);real=a.real_values()
        if tolerance<=0:raise ValueError('Settling tolerance must be positive.')
        outside=[i for i,v in enumerate(real) if abs(v-target)>tolerance]
        if outside and outside[-1]>=len(real)-2:raise ValueError('No settled interval is present at the end of the simulation.')
        return Signal([a.x[outside[-1]+1] if outside else a.x[0]],unit=xunit)
    if name=='deriv':
        vals=[(values[i+1]-values[i])/(a.x[i+1]-a.x[i]) for i in range(len(values)-1)];vals.append(vals[-1]);unit=tuple(v-u for v,u in zip(a.unit,xunit));return Signal([finite(v) for v in vals],a.x,unit,a.domain)
    if name=='integ':
        vals=[0.]
        for i in range(1,len(values)):vals.append(finite(vals[-1]+(values[i]+values[i-1])*.5*(a.x[i]-a.x[i-1])))
        return Signal(vals,a.x,tuple(v+u for v,u in zip(a.unit,xunit)),a.domain)
    if name=='fft':
        if a.domain!='time':raise ValueError('FFT requires a time-domain waveform.')
        real=a.real_values();count=len(real);dt=(a.x[-1]-a.x[0])/(count-1)
        if count<4 or any(abs((y-x)-dt)>dt*1e-4 for x,y in zip(a.x,a.x[1:])):raise ValueError('FFT requires at least four uniformly spaced time samples. Export/resample adaptive data first.')
        size=1<<(count-1).bit_length();win=[.5-.5*math.cos(2*math.pi*i/(count-1)) for i in range(count)];data=[complex(v*w) for v,w in zip(real,win)]+[0j]*(size-count)
        j=0
        for i in range(1,size):
            bit=size>>1
            while j&bit:j^=bit;bit>>=1
            j^=bit
            if i<j:data[i],data[j]=data[j],data[i]
        length=2
        while length<=size:
            step=cmath.exp(-2j*math.pi/length)
            for start in range(0,size,length):
                w=1
                for k in range(length//2):
                    u=data[start+k];v=data[start+k+length//2]*w;data[start+k]=u+v;data[start+k+length//2]=u-v;w*=step
            length*=2
        vals=[abs(v)*(1 if i in (0,size//2) else 2)/sum(win) for i,v in enumerate(data[:size//2+1])]
        return Signal(vals,[i/(size*dt) for i in range(len(vals))],a.unit,'frequency')
    if name=='unwrap':
        real=a.real_values();out=[real[0]];offset=0
        for left,right in zip(real,real[1:]):
            delta=right-left
            if delta>math.pi:offset-=2*math.pi*math.floor((delta+math.pi)/(2*math.pi))
            elif delta<-math.pi:offset+=2*math.pi*math.floor((-delta+math.pi)/(2*math.pi))
            out.append(right+offset)
        return Signal(out,a.x,a.unit,a.domain)
    if name in ('sin','cos','exp','log') and a.unit!=ONE:raise ValueError(name+' requires a dimensionless argument.')
    fn={'abs':abs,'real':lambda z:complex(z).real,'imag':lambda z:complex(z).imag,'phase':cmath.phase,'db20':lambda z:20*math.log10(abs(z)),'sqrt':cmath.sqrt,'sin':cmath.sin,'cos':cmath.cos,'exp':cmath.exp,'log':cmath.log}.get(name)
    if fn is None:raise ValueError('Unknown function: '+name)
    unit=ONE if name in ('phase','db20') else tuple(v/2 for v in a.unit) if name=='sqrt' else a.unit
    try:return Signal([finite(fn(v)) for v in values],a.x,unit,a.domain)
    except (ValueError,OverflowError) as exc:raise ValueError(name+' is undefined for one or more samples.') from exc


def plot_result(result,expression,name=None):
    signal=evaluate(expression,result);values=signal.real_values()
    if signal.x is None:raise ValueError('A plot expression must return a waveform; use a specification for scalar outputs.')
    root=parse(expression);display_unit=unit_name(signal.unit) or '1'
    if isinstance(root,ast.Call) and signal.unit==ONE:
        if root.func.id=='db20':display_unit='dB'
        elif root.func.id=='phase' or root.func.id=='unwrap' and 'phase(' in expression:display_unit='rad'
    return {**result,'traces':{name or expression:values},'trace_units':{name or expression:list(signal.unit)},'phase':{},'currents':{},'x':signal.x,'x_label':'Frequency (Hz)' if signal.domain=='frequency' else result.get('x_label','X'),'y_label':display_unit,'settings':{**result.get('settings',{}),'type':('fft' if signal.x and signal.x[0]==0 else 'ac') if signal.domain=='frequency' else 'tran' if signal.domain=='time' else 'dc'},'plot_unit':display_unit,'expression':expression}
