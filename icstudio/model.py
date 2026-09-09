from __future__ import annotations
import copy, hashlib, json, math, os, re, tempfile, uuid
from pathlib import Path
from datetime import datetime, timezone

SCHEMA = 1
KINDS = ('R', 'C', 'L', 'V', 'I', 'NMOS', 'PMOS', 'X', 'PDK', 'XS', 'SPICE')
PINS = {'R':['p','n'],'C':['p','n'],'L':['p','n'],'V':['p','n'],'I':['p','n'],
        'NMOS':['d','g','s','b'],'PMOS':['d','g','s','b']}
LAYERS = [
 {'name':'active','gds':1,'datatype':0,'color':'#64c77b','width':150,'space':150},
 {'name':'poly','gds':2,'datatype':0,'color':'#f18c89','width':150,'space':180},
 {'name':'contact','gds':3,'datatype':0,'color':'#d2d9de','width':150,'space':150},
 {'name':'metal1','gds':4,'datatype':0,'color':'#68a6f4','width':200,'space':200},
 {'name':'via1','gds':5,'datatype':0,'color':'#ddc086','width':150,'space':150},
 {'name':'metal2','gds':6,'datatype':0,'color':'#b49cef','width':250,'space':250},
 {'name':'nwell','gds':7,'datatype':0,'color':'#d2ab6a','width':1000,'space':500},
]
NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_.$-]{0,63}$')
NET = re.compile(r'^(0|[A-Za-z_][A-Za-z0-9_.$/\[\]-]{0,127})$')

def uid(): return uuid.uuid4().hex[:16]
def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def clone(x): return copy.deepcopy(x)
def digest(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def file_digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def design_digest(p):
    return digest({k:v for k,v in p.items() if k not in ("waivers","modified","native_migration")})

def scalar(text):
    if isinstance(text,(int,float)):
        x=float(text)
    else:
        m=re.fullmatch(r'\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(meg|[TGMkmunpf]?)\s*',str(text),re.I)
        if not m: raise ValueError(f'Invalid numeric value: {text}. Use e.g. 10k, 2.2n, 1.8.')
        x=float(m[1])*{'t':1e12,'g':1e9,'meg':1e6,'k':1e3,'m':1e-3,'u':1e-6,'n':1e-9,'p':1e-12,'f':1e-15,'':1}[m[2].lower()]
    if not math.isfinite(x): raise ValueError('Values must be finite.')
    return x

def device(kind,name,x=300,y=250,**kw):
    pins=PINS.get(kind,[])
    d={'id':uid(),'kind':kind,'name':name,'x':x,'y':y,'rotation':0,
       'nets':{p:'0' if p in ('n','s','b') else 'net_'+name for p in pins},
       'value':{'R':'10k','C':'1n','L':'1m','V':'1.8','I':'10u'}.get(kind,'1'),
       'params':{'w':'2u','l':'0.18u','vto':'0.45','kp':'100u','lambda':'0.02'},
       'source':{'type':'dc','low':'0','high':'1.8','period':'20u','delay':'0','duty':'0.5','ac':'1'}}
    d.update(kw); return d

def example(kind='rc'):
    cid=uid()
    p={'schema':SCHEMA,'id':uid(),'name':{'rc':'RC low-pass','inverter':'CMOS inverter','empty':'Untitled circuit'}[kind],
       'revision':0,'top':cid,'created':now(),'modified':now(),'pdk':{'name':'Generic teaching process','revision':'generic-1','status':'unqualified','dbu_um':0.001,'grid':5,'layers':clone(LAYERS)},
       'cells':[{'id':cid,'name':'top','ports':[],'devices':[],'shapes':[]}],
       'analysis':{'type':'tran','stop':'100u','step':'200n','start':'10','end':'10meg','points':150,'source':'V1','dc_start':'0','dc_stop':'1.8','dc_step':'0.01','temperature':27},'waivers':[]}
    c=p['cells'][0]
    if kind=='rc':
        c['devices']=[device('V','V1',180,260,nets={'p':'vin','n':'0'},source={'type':'pulse','low':'0','high':'1.8','period':'40u','delay':'2u','duty':'0.5','ac':'1'}),device('R','R1',420,180,nets={'p':'vin','n':'vout'},rotation=270),device('C','C1',650,260,nets={'p':'vout','n':'0'})]
    if kind=='inverter':
        c['devices']=[device('V','VDD',140,180,nets={'p':'vdd','n':'0'}),device('V','V1',140,390,nets={'p':'vin','n':'0'},source={'type':'pulse','low':'0','high':'1.8','period':'20u','delay':'1u','duty':'0.5','ac':'1'}),device('PMOS','MP1',490,200,nets={'d':'vout','g':'vin','s':'vdd','b':'vdd'}),device('NMOS','MN1',490,390,nets={'d':'vout','g':'vin','s':'0','b':'0'}),device('C','CL',730,310,value='20f',nets={'p':'vout','n':'0'})]
        p['analysis']['stop']='60u'; p['analysis']['step']='100n'
    return p

def validate(p):
    if not isinstance(p,dict) or p.get('schema')!=SCHEMA: raise ValueError('Unsupported project schema. This release reads schema 1.')
    if not isinstance(p.get('name'),str) or not p['name'].strip() or len(p['name'])>128: raise ValueError('Project name must be 1–128 characters.')
    if not isinstance(p.get('revision'),int) or p['revision']<0: raise ValueError('Invalid revision.')
    cells=p.get('cells',[])
    if not isinstance(cells,list) or not 1<=len(cells)<=100: raise ValueError('A project needs 1–100 cells.')
    ids=set(); cellids={c['id'] for c in cells}; names=set()
    def ident(value):
        if not isinstance(value,str) or not NAME.fullmatch(value): raise ValueError(f'Invalid identifier: {value!r}')
    def objid(value):
        if not isinstance(value,str) or not re.fullmatch('[a-zA-Z0-9_-]{1,80}',value) or value in ids: raise ValueError('Invalid or duplicate object ID.')
        ids.add(value)
    objid(p.get('id'))
    if p.get('top') not in cellids: raise ValueError('Top cell is missing.')
    tech=p.get('pdk',{})
    if tech.get('dbu_um')!=0.001: raise ValueError('This release uses 1 nm integer database units (dbu_um = 0.001).')
    if not isinstance(tech.get('grid'),int) or tech['grid']<1: raise ValueError('Invalid database grid.')
    layers=tech.get('layers',[])
    if not isinstance(layers,list) or not 1<=len(layers)<=2048: raise ValueError('Invalid layer table.')
    lnames=set()
    for l in layers:
        ident(l['name'])
        if l['name'] in lnames: raise ValueError('Duplicate layer name.')
        lnames.add(l['name'])
        if not re.fullmatch('#[0-9a-fA-F]{6}',l.get('color','')): raise ValueError('Invalid layer color.')
        for key in ('gds','datatype','width','space'):
            if not isinstance(l.get(key),int) or l[key]<0 or l[key]>2**31-1: raise ValueError('Invalid layer number or rule.')
        if l['gds']>65535 or l['datatype']>65535: raise ValueError('GDS layer/datatype out of range.')
    from .catalog import validate_catalog, binding_for, parameter_values
    from .symbol_io import validate_symbol
    validate_catalog(tech)
    for c in cells:
        if p.get('spice',{}).get('version')==1:c.setdefault('electrical',{'version':1,'nets':[]})
        objid(c['id']); ident(c['name'])
        if c['name'].casefold() in names: raise ValueError('Duplicate cell name.')
        names.add(c['name'].casefold()); dn=set(); net_case={}
        if len(c.get('ports',[]))>128 or len(set(c['ports']))!=len(c['ports']): raise ValueError('Invalid cell ports.')
        for port in c['ports']:
            if not NET.fullmatch(port) or port=='0':raise ValueError('Invalid cell port.')
        if len(c.get('devices',[]))>500 or len(c.get('shapes',[]))>100000: raise ValueError('Preview design-size limit exceeded.')
        from .design_ops import parameters,resolved_device
        context=parameters(c.get('parameters',{}),parameters(p.get('parameters',{})))
        for original in c['devices']:
            d=resolved_device(original,context) if original['kind']!='X' else original
            objid(d['id']); ident(d['name'])
            if d['name'].casefold() in dn: raise ValueError(f'Duplicate instance name {d["name"]}.')
            dn.add(d['name'].casefold()); k=d['kind']
            if k not in KINDS: raise ValueError('Unsupported device kind.')
            if k=='X':
                if d.get('cell') not in cellids: raise ValueError('Instance references a missing cell.')
                child=next(cc for cc in cells if cc['id']==d['cell']);pins=child['ports']
                if set(d.get('parameters',{}))-set(child.get('parameters',{})):raise ValueError(d['name']+': unknown component parameter override.')
                parameters({**child.get('parameters',{}),**{key:__import__('icstudio.design_ops',fromlist=['value']).value(raw,context) for key,raw in d.get('parameters',{}).items()}},parameters(p.get('parameters',{})))
            elif k=='SPICE':
                from .native_spice import validate_device
                validate_device(d);pins=d['symbol']['pin_order']
            elif k=='XS':
                if not d.get('xschem') or not d.get('symbol'):raise ValueError('An Xschem component requires its source properties and symbol.')
                pins=d['symbol']['pin_order']
            elif k=='PDK': pins=binding_for(tech,d)['pin_order']
            else: pins=PINS[k]
            if d.get('native_spice'):
                from .native_spice import validate_device
                validate_device(d)
            binding=binding_for(tech,d)
            if binding and d.get('model_ref'): parameter_values(binding,d)
            if d.get('symbol'): validate_symbol(d['symbol'],pins)
            if set(d.get('nets',{}))!=set(pins): raise ValueError(f'{d["name"]}: pin mapping does not match symbol.')
            if any(not isinstance(n,str) or not NET.fullmatch(n) for n in d['nets'].values()): raise ValueError('Invalid net name. Ground is 0.')
            for n in d['nets'].values():
                if n.casefold() in net_case and net_case[n.casefold()]!=n: raise ValueError('Net names differing only by case are not portable to SPICE.')
                net_case[n.casefold()]=n
            for axis in ('x','y'):
                if not isinstance(d.get(axis),(int,float)) or not math.isfinite(d[axis]) or abs(d[axis])>1e7: raise ValueError('Invalid schematic position.')
            if type(d.get('mirror',False)) is not bool:raise ValueError('Invalid schematic mirror flag.')
            if d.get('rotation') not in (0,90,180,270): raise ValueError('Invalid rotation.')
            if k not in ('X','NMOS','PMOS','PDK','SPICE'):
                v=scalar(d['value'])
                if k in ('R','C','L') and v<=0: raise ValueError(f'{k} value must be positive.')
            if k in ('NMOS','PMOS'):
                for key in ('w','l','kp','vto','lambda'):
                    v=scalar(d['params'][key])
                    if v<0 or (key in ('w','l','kp') and v==0): raise ValueError('Invalid MOS parameter.')
            if k in ('V','I'):
                s=d['source']
                if s['type'] not in ('dc','pulse','sine'): raise ValueError('Unsupported source waveform.')
                for key in ('low','high','period','delay','duty','ac'): scalar(s[key])
                if scalar(s['period'])<=0 or not 0<scalar(s['duty'])<1 or scalar(s['delay'])<0: raise ValueError('Invalid source timing.')
        for s in c['shapes']:
            objid(s['id'])
            if s['layer'] not in lnames: raise ValueError('Unknown layout layer.')
            if s['kind'] not in ('rect','polygon','path'): raise ValueError('Unsupported geometry.')
            pts=s.get('points',[])
            if not 2<=len(pts)<=10000 or (s['kind']=='polygon' and len(pts)<3): raise ValueError('Invalid polygon/path.')
            if s['kind']=='rect' and len(pts)!=2: raise ValueError('Rectangles require two corners.')
            holes=s.get('holes',[])
            if not isinstance(holes,list) or any(not isinstance(h,list) or len(h)<3 for h in holes): raise ValueError('Invalid polygon hole.')
            for pt in pts+[pt for h in holes for pt in h]:
                if not isinstance(pt,list) or len(pt)!=2 or any(not isinstance(v,int) or abs(v)>2**31-1 for v in pt): raise ValueError('Coordinates must be signed 32-bit nanometres for this release’s GDS path.')
            if s['kind']=='path' and (not isinstance(s.get('width'),int) or s['width']<=0): raise ValueError('Path width must be positive.')
            if s.get('net') and not NET.fullmatch(s['net']): raise ValueError('Invalid layout net label.')
    from .design_ops import validate_extras
    validate_extras(p,objid)
    from .wiring import validate_wiring
    for c in cells:
        validate_wiring(c,objid,p)
        if 'electrical' in c and 'wires' not in c:
            from .electrical_identity import synchronize
            synchronize(c)
    from .testbenches import validate_testbenches
    validate_testbenches(p,objid)
    from .analysis_plan import validate_plan
    validate_plan(p)
    from .specifications import validate_project as validate_specifications
    validate_specifications(p)
    from .analog_constraints import validate_constraints
    validate_constraints(p)
    for cell in cells:flatten(p,cell['id'])
    return p

def flatten(p,cell_id=None):
    by={c['id']:c for c in p['cells']}; out=[]
    from .design_ops import parameters,resolved_device,value
    global_params=parameters(p.get("parameters",{}))
    def walk(cid,path,mapping,seen,overrides=None):
        if cid in seen or len(seen)>12: raise ValueError('Recursive or excessively deep cell hierarchy.')
        c=by[cid]
        if 'wires' in c:
            from .wiring import rebuild
            c=clone(c);rebuild(c,p)
        context=parameters({**c.get('parameters',{}),**(overrides or {})},global_params)
        def net(n): return '0' if n=='0' else mapping.get(n,path+n)
        for d in c['devices']:
            if d['kind']=='X': walk(d['cell'],path+d['name']+'/',{pin:net(n) for pin,n in d['nets'].items()},seen+[cid],{k:value(v,context) for k,v in d.get('parameters',{}).items()})
            else:
                dd=resolved_device(d,context); dd['name']=path+d['name']; dd['nets']={pin:net(n) for pin,n in d['nets'].items()}; out.append(dd)
        if len(out)>500: raise ValueError('Flattened circuit exceeds the 500-device preview limit.')
    walk(cell_id or p['top'],'',{},[])
    return out

def atomic_write(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data if isinstance(data,bytes) else data.encode('utf-8')); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def save_project(p,path):
    validate(p); atomic_write(path,json.dumps(p,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def load_project(path):
    path=Path(path)
    if path.is_dir() or path.suffix=='.icstudio':
        from .project_store import load_directory
        return load_directory(path)
    if path.stat().st_size>50*1024*1024: raise ValueError('Project exceeds 50 MiB preview limit.')
    p=json.loads(path.read_text(encoding='utf-8'));package_root=p.get('pdk',{}).get('package_root')
    if package_root and not Path(package_root).is_absolute():p['pdk']['package_root']=str((path.parent/package_root).resolve())
    return validate(p)

class History:
    def __init__(self,p): self.project=clone(validate(p)); self.undo_stack=[]; self.redo_stack=[]; self.serial=p['revision']
    def commit(self,fn,label='Edit'):
        nxt=clone(self.project); fn(nxt); nxt['revision']=self.serial+1; nxt['modified']=now(); validate(nxt); self.serial+=1
        self.undo_stack.append((clone(self.project),label)); self.undo_stack=self.undo_stack[-100:]; self.redo_stack=[]; self.project=nxt
    def undo(self):
        if not self.undo_stack: return
        p,label=self.undo_stack.pop(); self.redo_stack.append((self.project,label)); self.serial+=1; p['revision']=self.serial; p['modified']=now(); self.project=p
    def redo(self):
        if not self.redo_stack: return
        p,label=self.redo_stack.pop(); self.undo_stack.append((self.project,label)); self.serial+=1; p['revision']=self.serial; p['modified']=now(); self.project=p

def erc(p,cid=None):
    from .electrical_rules import check
    return check(p,cid or p['top'])
