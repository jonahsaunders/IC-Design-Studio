"""Parameterized hierarchy, reusable physical cells, and schematic utilities."""
from __future__ import annotations
import ast,math,operator,re
from .model import clone,uid,scalar,NAME,NET

def value(text,parameters=None):
    if not isinstance(text,str) or not text.startswith('{'):return scalar(text)
    if not text.endswith('}') or len(text)>256:raise ValueError('Use a bounded expression in braces, such as {resistance * 2}.')
    tree=ast.parse(text[1:-1],mode='eval');params=parameters or {}
    def visit(n):
        if isinstance(n,ast.Expression):return visit(n.body)
        if isinstance(n,ast.Constant) and type(n.value) in (int,float):return scalar(n.value)
        if isinstance(n,ast.Name) and n.id in params:return params[n.id]
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.USub,ast.UAdd)):return -visit(n.operand) if isinstance(n.op,ast.USub) else visit(n.operand)
        if isinstance(n,ast.BinOp) and type(n.op) in (ast.Add,ast.Sub,ast.Mult,ast.Div):return {ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}[type(n.op)](visit(n.left),visit(n.right))
        raise ValueError('Expressions support numbers, parameter names, +, −, × and ÷ only.')
    return scalar(visit(tree))

def parameters(definitions,parent=None):
    resolved=dict(parent or {});pending=dict(definitions)
    if len(pending)>100:raise ValueError('Too many parameters.')
    for _ in range(len(pending)+1):
        for key,text in list(pending.items()):
            if not NAME.fullmatch(key):raise ValueError('Invalid parameter name.')
            try:resolved[key]=value(text,resolved)
            except ValueError:continue
            del pending[key]
        if not pending:return resolved
    raise ValueError('Unresolved or recursive parameter expressions: '+', '.join(pending))

def resolved_device(d,context):
    d=clone(d)
    if d['kind'] not in ('X','NMOS','PMOS'):d['value']=str(value(d['value'],context))
    for key,text in list(d.get('params',{}).items()):d['params'][key]=str(value(text,context))
    if d['kind'] in ('V','I'):
        for key,text in list(d['source'].items()):
            if key!='type':d['source'][key]=str(value(text,context))
    if d['kind'] in ('R','C','L') and scalar(d['value'])<=0:raise ValueError('Resolved passive value must be positive.')
    if d['kind'] in ('NMOS','PMOS') and any(scalar(d['params'][k])<=0 for k in ('w','l','kp')):raise ValueError('Resolved MOS geometry and gain must be positive.')
    return d

def bus_nets(expression):
    m=re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)\[(\d+):(\d+)\]',expression.strip())
    if not m:raise ValueError('Enter a bus such as data[7:0].')
    start,end=int(m[2]),int(m[3])
    if abs(start-end)>127:raise ValueError('A bus can contain at most 128 signals.')
    return [f'{m[1]}[{i}]' for i in range(start,end+(1 if end>=start else -1),1 if end>=start else -1)]

def connect_bus(cell,ids,pin,expression):
    nets=bus_nets(expression)
    if len(ids)!=len(nets):raise ValueError('Select exactly one component per bus signal.')
    for ident,net in zip(ids,nets):
        d=next(d for d in cell['devices'] if d['id']==ident)
        if pin not in d['nets']:raise ValueError(d['name']+' has no pin '+pin)
        if 'wires' in cell:
            from .wiring import set_label
            set_label(cell,ident,pin,net)
        else:d['nets'][pin]=net
    cell.setdefault('buses',[]).append({'id':uid(),'name':expression,'nets':nets})

def validate_extras(p,objid):
    from .electrical_rules import validate_policy
    validate_policy(p.get('electrical_rules',{}))
    by={c['id']:c for c in p['cells']};parameters(p.get('parameters',{}))
    for c in p['cells']:
        parameters(c.get('parameters',{}),parameters(p.get('parameters',{})))
        for note in c.get('annotations',[]):
            objid(note['id'])
            if not isinstance(note.get('text'),str) or not 0<len(note['text'])<=2000:raise ValueError('Annotation requires 1–2,000 characters.')
            if any(not math.isfinite(float(note.get(k,0))) or abs(float(note.get(k,0)))>1e7 for k in ('x','y')):raise ValueError('Invalid annotation position.')
        if c.get('symbol'):
            from .symbol_io import validate_symbol
            validate_symbol(c['symbol'],c['ports'])
        names=set()
        for inst in c.get('layout_instances',[]):
            objid(inst['id'])
            if inst.get('cell') not in by or not NAME.fullmatch(inst.get('name','')) or inst['name'].casefold() in names:raise ValueError('Missing layout cell or duplicate instance name.')
            names.add(inst['name'].casefold())
            if inst.get('rotation',0) not in (0,90,180,270):raise ValueError('Invalid layout instance rotation.')
            for key in ('x','y','dx','dy'):
                if type(inst.get(key,0)) is not int or abs(inst.get(key,0))>2**31-1:raise ValueError('Layout placement requires integer nanometres.')
            from .layout_limits import MAX_ARRAY_AXIS
            if any(type(inst.get(k,1)) is not int or not 1<=inst.get(k,1)<=MAX_ARRAY_AXIS for k in ('nx','ny')):raise ValueError(f'Layout arrays require 1–{MAX_ARRAY_AXIS} rows/columns.')
            for vector in ('a','b'):
                if vector in inst and (len(inst[vector])!=2 or any(type(v) is not int or abs(v)>2**31-1 for v in inst[vector])):raise ValueError('Invalid layout array vector.')
        port_names=set()
        for port in c.get('layout_ports',[]):
            if port.get('name') not in c['ports'] or port['name'] in port_names:raise ValueError('Invalid or duplicate physical cell port.')
            port_names.add(port['name'])
            if port.get('layer') not in {l['name'] for l in p['pdk']['layers']} or len(port.get('point',[]))!=2 or any(type(v) is not int or abs(v)>2**31-1 for v in port['point']):raise ValueError('Invalid physical cell port location.')
        for text in c.get('layout_texts',[]):
            if text.get('layer') not in {l['name'] for l in p['pdk']['layers']} or not isinstance(text.get('text'),str) or len(text['text'])>10000:raise ValueError('Invalid layout text.')
            if any(type(text.get(k)) is not int or abs(text[k])>2**31-1 for k in ('x','y')) or text.get('rotation',0) not in (0,90,180,270):raise ValueError('Invalid layout text position.')
        for pin in c.get('layout_pins',[]):
            objid(pin['id']);d=next((d for d in c['devices'] if d['id']==pin.get('device_id')),None)
            if not d or pin.get('pin') not in d['nets']:raise ValueError('Physical terminal must reference an existing device pin.')
            if pin.get('layer') not in {l['name'] for l in p['pdk']['layers']}:raise ValueError('Unknown physical pin layer.')
            if len(pin.get('point',[]))!=2 or any(type(v) is not int or abs(v)>2**31-1 for v in pin['point']):raise ValueError('Invalid physical terminal position.')
        for bus in c.get('buses',[]):objid(bus['id']);bus_nets(bus['name'])
    depths={}
    def walk(cid,seen):
        if cid in seen or len(seen)>12:raise ValueError('Recursive or excessively deep physical hierarchy.')
        if cid not in depths:depths[cid]=max((1+walk(i['cell'],seen|{cid}) for i in by[cid].get('layout_instances',[])),default=0)
        if depths[cid]+len(seen)>12:raise ValueError('Recursive or excessively deep physical hierarchy.')
        return depths[cid]
    for cid in by:walk(cid,set())

def flatten_layout(p,cid,max_depth=None):
    from .layout import polygon,shape_from_polygon,kdb
    db=kdb();by={c['id']:c for c in p['cells']};out=[]
    def walk(cell,transform,owner=None,path='',depth=0,mapping=None,device_owner=None):
        mapping=mapping or {}
        def net(n):return '0' if n=='0' else mapping.get(n,path+n) if n else ''
        for s in cell['shapes']:
            if len(out)>=100000:raise ValueError('This operation expands at most 100,000 shapes. Choose a smaller physical cell or hierarchy depth.')
            if owner:
                q=shape_from_polygon(polygon(s).transformed(transform),s['layer'],net(s.get('net','')),device_owner or s.get('device_id',''));q['id']=owner;q['source_id']=s['id'];q['instance_path']=path;out.append(q)
            else:out.append(s)
        if max_depth is not None and depth>=max_depth:return
        for inst in cell.get('layout_instances',[]):
            for ix in range(inst.get('nx',1)):
                for iy in range(inst.get('ny',1)):
                    tr=db.ICplxTrans(1,inst.get('rotation',0),inst.get('mirror',False),inst['x']+ix*inst.get('a',[inst.get('dx',0),0])[0]+iy*inst.get('b',[0,inst.get('dy',0)])[0],inst['y']+ix*inst.get('a',[inst.get('dx',0),0])[1]+iy*inst.get('b',[0,inst.get('dy',0)])[1])
                    d=next((d for d in cell['devices'] if d['id']==inst.get('device_id')),None)
                    pins={pin:net(n) for pin,n in d['nets'].items()} if d else {}
                    walk(by[inst['cell']],transform*tr,owner or inst['id'],path+inst['name']+f'[{ix},{iy}]/',depth+1,pins,device_owner or inst.get('device_id'))
        if len(out)>100000:raise ValueError('Flattened layout exceeds 100,000 shapes.')
    walk(by[cid],db.ICplxTrans());return out

def verilog(p):
    """Structural connectivity export with declared analog black boxes."""
    def ident(name):return name if re.fullmatch('[A-Za-z_][A-Za-z0-9_$]*',name) else '\\'+name+' '
    by={c['id']:c for c in p['cells']};lines=['// Structural connectivity only. Analog primitives are black boxes.']
    if any(d.get('model_ref') for c in p['cells'] for d in c['devices']):raise ValueError('PDK devices require SPICE export; structural Verilog does not preserve their electrical models.')
    kinds=sorted({d['kind'] for c in p['cells'] for d in c['devices'] if d['kind']!='X'})
    from .model import PINS
    for k in kinds:
        pins=PINS[k];lines.extend([f'(* black_box *) module IC_{k}('+', '.join(pins)+');','  parameter real VALUE=1, W=1, L=1;','  inout '+', '.join(pins)+';','endmodule'])
    for c in p['cells']:
        ctx=parameters(c.get('parameters',{}),parameters(p.get('parameters',{})))
        lines.append('module '+ident(c['name'])+'('+', '.join(ident(n) for n in c['ports'])+');')
        for name,raw in c.get('parameters',{}).items():lines.append('  parameter real '+name+' = '+str(ctx[name])+';')
        if c['ports']:lines.append('  inout '+', '.join(ident(n) for n in c['ports'])+';')
        nets=sorted({n for d in c['devices'] for n in d['nets'].values()}-set(c['ports']))
        if nets:lines.append('  wire '+', '.join(ident(n) for n in nets)+';')
        if '0' in nets:lines.append("  assign \\0 = 1'b0;")
        for d in c['devices']:
            k=d['kind'];resolved=resolved_device(d,ctx) if k!='X' else d;module=ident(by[d['cell']]['name']) if k=='X' else 'IC_'+k
            opts=('#('+', '.join('.'+key+'('+str(value(raw,ctx))+')' for key,raw in d.get('parameters',{}).items())+') ' if d.get('parameters') else '') if k=='X' else ('#(.W('+resolved['params']['w']+'), .L('+resolved['params']['l']+')) ' if k in ('NMOS','PMOS') else '#(.VALUE('+(d['value'][1:-1] if isinstance(d['value'],str) and d['value'].startswith('{') else resolved['value'])+')) ')
            lines.append('  '+module+' '+opts+ident(d['name'])+'('+', '.join('.'+ident(pin)+'('+ident(net)+')' for pin,net in d['nets'].items())+');')
        lines.append('endmodule')
    return '\n'.join(lines)+'\n'
