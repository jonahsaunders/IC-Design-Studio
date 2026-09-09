"""Native/Xschem symbol artwork and declarative attributes; no script execution."""
import math, re,json
from pathlib import Path
from .model import atomic_write


def validate_symbol(symbol, ports):
    from .model import NET
    if any(not isinstance(n,str) or not NET.fullmatch(n) or n=='0' for n in ports):raise ValueError('Invalid symbol terminal name.')
    if set(symbol.get('pins', {})) != set(ports): raise ValueError('Symbol pins must match the electrical terminals exactly.')
    if len({p.casefold() for p in symbol['pins']})!=len(symbol['pins']):raise ValueError('Pin names must be unique under SPICE case folding.')
    order=symbol.get('pin_order',list(symbol['pins']))
    if len(order)!=len(set(order)) or set(order)!=set(ports):raise ValueError('Netlist order must contain each terminal exactly once.')
    metadata=symbol.get('pin_meta',{})
    if set(metadata)-set(ports):raise ValueError('Pin metadata refers to a missing terminal.')
    ids=set()
    for name,m in metadata.items():
        if m.get('direction','inout') not in ('in','out','inout','passive'):raise ValueError('Choose input, output, inout or passive pin direction.')
        if m.get('role','signal') not in ('signal','power','ground','clock','analog'):raise ValueError('Invalid pin signal role.')
        if type(m.get('required',True)) is not bool:raise ValueError('Required terminal must be boolean.')
        if type(m.get('label_visible',True)) is not bool:raise ValueError('Pin label visibility must be boolean.')
        if m.get('id'):
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',m['id']) or m['id'] in ids:raise ValueError('Invalid or duplicate stable pin identity.')
            ids.add(m['id'])
        if m.get('bus'):
            from .design_ops import bus_nets
            if name not in bus_nets(m['bus']):raise ValueError('Bus metadata must include this scalar terminal.')
    attributes=symbol.get('attributes',{})
    if not isinstance(attributes,dict) or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',k) or not isinstance(v,str) or len(v)>2000 for k,v in attributes.items()):raise ValueError('Invalid declarative symbol attributes.')
    points = list(symbol['pins'].values())
    if len(symbol.get('primitives', [])) > 1000: raise ValueError('A symbol supports at most 1,000 primitives.')
    for primitive in symbol.get('primitives', []):
        kind=primitive.get('kind');n=len(primitive.get('points', []))
        if kind not in ('line','rect','ellipse','text','polygon','arc') or (not 3<=n<=500 if kind=='polygon' else n!=2): raise ValueError('Invalid symbol primitive.')
        if primitive['kind'] == 'text' and (not isinstance(primitive.get('text'), str) or len(primitive['text']) > 200): raise ValueError('Text is limited to 200 characters.')
        for key,low,high,default in [('font_size',1,72,8),('line_width',.1,20,1.5),('start',-360,360,0),('sweep',-360,360,90)]:
            value=primitive.get(key,default)
            if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError('Invalid symbol style: '+key)
        if primitive.get('rotation',0) not in (0,90,180,270):raise ValueError('Invalid text rotation.')
        if 'color' in primitive and not re.fullmatch(r'#[0-9a-fA-F]{6}',primitive['color']):raise ValueError('Use a six-digit color.')
        points += primitive['points']
    if any(len(pt) != 2 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v) > 500 for v in pt) for pt in points): raise ValueError('Symbol coordinates must be within ±500 drawing units.')
    return symbol


def import_symbol(path,preserve_case=False):
    from .xschem_io import records, properties
    text = Path(path).read_text(encoding='utf-8')
    if len(text) > 2_000_000: raise ValueError('Symbol file is too large.')
    symbol = {'pins': {}, 'primitives': [],'pin_meta':{},'pin_order':[]}; notes = []; metadata = {}; pin_numbers={}
    for r in records(text):
        kind = r[0]
        if kind == 'K': metadata = properties(r[1])
        elif kind == 'B' and r[1] == '5':
            props = properties(r[-1]); name = props.get('name', '');name=name if preserve_case else name.lower()
            from .model import NET
            if not NET.fullmatch(name) or name=='0' or name in symbol['pins']: raise ValueError('Missing, invalid or duplicate symbol pin.')
            x1,y1,x2,y2 = map(float, r[2:6]); symbol['pins'][name] = [(x1+x2)/2,(y1+y2)/2]
            symbol['pin_order'].append(name)
            if 'sim_pinnumber' in props:pin_numbers[name]=int(props['sim_pinnumber'])
            role=props.get('sig_type','signal');role=role if role in ('signal','power','ground','clock','analog') else 'signal'
            symbol['pin_meta'][name]={'direction':props.get('dir','inout'),'role':role,'bus':props.get('studio_bus',''),'label_visible':props.get('hide','false')!='true','required':props.get('studio_required','true')!='false'}
            if props.get('studio_pin_id'):symbol['pin_meta'][name]['id']=props['studio_pin_id']
        elif kind in ('L','B'):
            x1,y1,x2,y2 = map(float,r[2:6]); symbol['primitives'].append({'kind':'line' if kind=='L' else 'rect','points':[[x1,y1],[x2,y2]]})
        elif kind == 'P':
            count=int(r[2]); coords=list(map(float,r[3:3+count*2])); points=[coords[i:i+2] for i in range(0,len(coords),2)]
            if len(points)>2 and points[-1]==points[0]:points.pop()
            if len(points)>=3:symbol['primitives'].append({'kind':'polygon','points':points})
            elif len(points)==2:symbol['primitives'].append({'kind':'line','points':points})
        elif kind == 'A':
            x,y,radius,start,sweep=map(float,r[2:7]);symbol['primitives'].append({'kind':'arc','points':[[x-radius,y-radius],[x+radius,y+radius]],'start':-start,'sweep':-sweep})
        elif kind == 'T':
            if 'tcleval' in r[1]:notes.append('Executable text retained as metadata only.');continue
            x,y=float(r[2]),float(r[3]); symbol['primitives'].append({'kind':'text','points':[[x,y],[x+20,y+10]],'text':r[1],'rotation':int(r[4])*90,'font_size':max(1,min(72,float(r[6])*40))})
        elif kind not in ('v','G','K','V','S','E','F'): notes.append('Preserved only as source: ' + kind)
    # Restore styles only when visible artwork records are unchanged. External edits win.
    payload=metadata.pop('studio_symbol_v2','')
    if payload:
        import base64,hashlib
        stored=json.loads(base64.urlsafe_b64decode(payload))
        visible=[r for r in records(text) if r[0] in ('L','P','A','T') or r[0]=='B' and r[1]!='5']
        fingerprint=hashlib.sha256(json.dumps(visible,separators=(',',':')).encode()).hexdigest()
        if stored.get('artwork_hash')==fingerprint:
            restored=stored['symbol'];validate_symbol(restored,restored['pins']);symbol['primitives']=restored['primitives']
        else:notes.append('External artwork edits imported; native-only styles were not restored.')
    if pin_numbers and len(pin_numbers)==len(symbol['pins']):
        if len(set(pin_numbers.values()))!=len(pin_numbers):raise ValueError('Duplicate sim_pinnumber makes the terminal order ambiguous.')
        symbol['pin_order'].sort(key=pin_numbers.get)
    symbol['attributes']=metadata
    validate_symbol(symbol, symbol['pins'])
    return symbol, metadata, notes


def symbol_text(symbol, name='X1', fmt='@name @pinlist', pins=None):
    validate_symbol(symbol, symbol['pins'])
    def quote(value):return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('{','\\{').replace('}','\\}')+'"'
    attributes=dict(symbol.get('attributes',{}));attributes.setdefault('type','subcircuit');attributes.setdefault('format',fmt);attributes.setdefault('template','name='+name)
    if pins is not None:attributes.update(format=fmt,template='name='+name)
    import base64
    from .model import clone
    payload=clone(symbol);payload.pop('attributes',None)
    attributes['studio_symbol_v2']=base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':')).encode()).decode()
    lines=['v {xschem version=3.4.7 file_version=1.2}','G {}','K {'+' '.join(k+'='+quote(v) for k,v in attributes.items())+'}','V {}','S {}','E {}']
    for pin in pins or symbol.get('pin_order',symbol['pins']):
        x,y=symbol['pins'][pin];m=symbol.get('pin_meta',{}).get(pin,{})
        props={'name':pin,'dir':m.get('direction','inout'),'sig_type':m.get('role','signal'),'hide':'false' if m.get('label_visible',True) else 'true','studio_bus':m.get('bus',''),'studio_required':'true' if m.get('required',True) else 'false'}
        if m.get('id'):props['studio_pin_id']=m['id']
        lines.append(f'B 5 {x-2.5:g} {y-2.5:g} {x+2.5:g} {y+2.5:g} '+'{'+' '.join(k+'='+quote(v) for k,v in props.items())+'}')
    for item in symbol['primitives']:
        (x1,y1),(x2,y2)=item['points'][0],item['points'][-1]; k=item['kind']
        if k in ('line','rect'): lines.append(f'{"L" if k=="line" else "B"} 4 {x1:g} {y1:g} {x2:g} {y2:g} {{}}')
        elif k=='polygon':
            points=item['points']+[item['points'][0]];lines.append('P 4 '+str(len(points))+' '+' '.join(f'{v:g}' for pt in points for v in pt)+' {}')
        elif k=='arc' and abs(x2-x1)==abs(y2-y1):lines.append(f'A 4 {(x1+x2)/2:g} {(y1+y2)/2:g} {abs(x2-x1)/2:g} {-item.get("start",0):g} {-item.get("sweep",90):g} {{}}')
        elif k in ('ellipse','arc'):
            start=math.radians(item.get('start',0)) if k=='arc' else 0;sweep=math.radians(item.get('sweep',90)) if k=='arc' else math.tau
            points=[[(x1+x2)/2+abs(x2-x1)/2*math.cos(start+i*sweep/48),(y1+y2)/2+abs(y2-y1)/2*math.sin(start+i*sweep/48)] for i in range(49)]
            for a,b in zip(points,points[1:]):lines.append(f'L 4 {a[0]:g} {a[1]:g} {b[0]:g} {b[1]:g} {{}}')
        else:
            text=item['text'].replace('\\','\\\\').replace('{','\\{').replace('}','\\}').replace('\n',' ')
            size=item.get('font_size',8)/40;lines.append(f'T {{{text}}} {x1:g} {y1:g} {item.get("rotation",0)//90} 0 {size:g} {size:g} {{}}')
    from .xschem_io import records
    import hashlib
    visible=[r for r in records('\n'.join(lines)) if r[0] in ('L','P','A','T') or r[0]=='B' and r[1]!='5']
    attributes['studio_symbol_v2']=base64.urlsafe_b64encode(json.dumps({'symbol':payload,'artwork_hash':hashlib.sha256(json.dumps(visible,separators=(',',':')).encode()).hexdigest()},separators=(',',':')).encode()).decode()
    lines[2]='K {'+' '.join(k+'='+quote(v) for k,v in attributes.items())+'}'
    return '\n'.join(lines)+'\n' 


def device_symbol(d):
    """Editable vector seed matching the built-in schematic device artwork."""
    from .interchange import pin_positions
    symbol={'pins':{k:list(v) for k,v in pin_positions({**d,'x':0,'y':0,'rotation':0,'mirror':False}).items()},'primitives':[]}
    def line(a,b):symbol['primitives'].append({'kind':'line','points':[list(a),list(b)]})
    kind=d['kind']
    if kind in ('R','C','V','I','L'):
        end=5 if kind=='C' else 24 if kind in ('R','L') else 20;line((0,-50),(0,-end));line((0,end),(0,50))
        if kind=='R':
            points=[(0,-24),(7,-20),(-7,-12),(7,-4),(-7,4),(7,12),(-7,20),(0,24)]
            for a,b in zip(points,points[1:]):line(a,b)
        elif kind=='C':line((-16,-5),(16,-5));line((-16,5),(16,5))
        elif kind=='L':
            for start in (-24,-12,0,12):
                points=[[9*math.sin(i*math.pi/16),start+12*i/16] for i in range(17)]
                for a,b in zip(points,points[1:]):line(a,b)
        else:
            symbol['primitives'].append({'kind':'ellipse','points':[[-20,-20],[20,20]]})
            if kind=='V':line((-4,-7),(4,-7));line((0,-11),(0,-3));line((-4,8),(4,8))
            else:line((0,-10),(0,10));line((0,10),(-4,3));line((0,10),(4,3))
    elif kind in ('NMOS','PMOS'):
        for a,b in [((-50,0),(-12,0)),((-12,-27),(-12,27)),((-2,-25),(-2,25)),((-2,-25),(20,-25)),((20,-25),(20,-50)),((-2,25),(20,25)),((20,25),(20,50)),((2,0),(50,0))]:line(a,b)
        if kind=='PMOS':symbol['primitives'].append({'kind':'ellipse','points':[[-23,-5],[-13,5]]})
        else:line((10,0),(18,-5));line((10,0),(18,5))
    else:symbol['primitives'].append({'kind':'rect','points':[[-40,-50],[40,50]]})
    return symbol


def default_symbol(ports):
    height=max(50,math.ceil(len(ports)/2)*20)
    return {'primitives':[{'kind':'rect','points':[[-40,-height],[40,height]]}],'pins':{pin:[-60 if i%2==0 else 60,-height+20+40*(i//2)] for i,pin in enumerate(ports)}}
