"""Configurable, navigable electrical checks over explicit hierarchy occurrences."""
from collections import defaultdict
from .model import digest
from .design_ops import bus_nets
DEFAULTS={'ERC.EMPTY':'error','ERC.GROUND':'error','ERC.SHORT':'error','ERC.DANGLING':'warning','ERC.DRIVERS':'warning','ERC.UNDRIVEN':'warning','ERC.BUS.WIDTH':'error','ERC.BUS.MAPPING':'warning','SYMBOL.INTERFACE':'error','SYMBOL.OVERLAP':'warning','SYMBOL.UNUSED':'warning','LAYOUT.PORTS':'warning'}
LABELS={'ERC.EMPTY':'Empty circuit','ERC.GROUND':'Missing ground','ERC.SHORT':'All device terminals shorted','ERC.DANGLING':'Single-terminal nets','ERC.DRIVERS':'Multiple output drivers','ERC.UNDRIVEN':'Inputs without a source','ERC.BUS.WIDTH':'Incomplete bus width','ERC.BUS.MAPPING':'Bus member order / names','SYMBOL.INTERFACE':'Symbol / schematic interface','SYMBOL.OVERLAP':'Overlapping symbol pins','SYMBOL.UNUSED':'Unused cell ports','LAYOUT.PORTS':'Missing physical ports'}

def validate_policy(policy):
    if not isinstance(policy,dict) or set(policy)-{'rules','scope'}:raise ValueError('Invalid electrical rule policy.')
    rules=policy.get('rules',{})
    if not isinstance(rules,dict) or set(rules)-set(DEFAULTS) or any(v not in ('off','warning','error') for v in rules.values()):raise ValueError('Choose off, warning or error for each known electrical rule.')
    if policy.get('scope','hierarchy') not in ('hierarchy','project'):raise ValueError('Choose hierarchy or project check scope.')
    return {**DEFAULTS,**rules}

def check(p,cid):
    policy=p.get('electrical_rules',{});rules=validate_policy(policy);by={c['id']:c for c in p['cells']};issues=[];seen=set();counts=defaultdict(list);visited=set();optional=set();steps=0
    def add(code,c,message,obj='',pin='',net='',path=(),root=cid):
        if rules[code]=='off' or len(issues)>=10000:return
        key=(code,c['id'],obj,pin,net,tuple(path))
        if key in seen:return
        seen.add(key);row={'severity':rules[code],'code':code,'cell':c['id'],'cell_id':c['id'],'object':obj,'pin':pin,'net':net,'path':list(path),'root':root,'message':c['name']+': '+message};row['fingerprint']=digest(row);issues.append(row)
    def local(c,path,root):
        s=c.get('symbol',{});pins=s.get('pins',{});meta=s.get('pin_meta',{})
        if s and (set(pins)!=set(c['ports']) or s.get('pin_order',c['ports'])!=c['ports']):add('SYMBOL.INTERFACE',c,'Symbol terminals/order differ from the electrical interface.',path=path,root=root)
        positions={};used={n for d in c['devices'] for n in d['nets'].values()}
        for name,pt in pins.items():
            if tuple(pt) in positions:add('SYMBOL.OVERLAP',c,name+' overlaps '+positions[tuple(pt)]+'.',pin=name,path=path,root=root)
            positions[tuple(pt)]=name
            if name not in used and meta.get(name,{}).get('required',True):add('SYMBOL.UNUSED',c,name+' is not connected inside this cell.',pin=name,net=name,path=path,root=root)
        buses=defaultdict(set)
        for name,m in meta.items():
            if m.get('bus'):buses[m['bus']].add(name)
        for expression,members in buses.items():
            expected=set(bus_nets(expression))
            if members!=expected:add('ERC.BUS.WIDTH',c,expression+' defines '+str(len(expected))+' bits but has '+str(len(members))+' terminal members.',pin=next(iter(members)),path=path,root=root)
        for bus in c.get('buses',[]):
            expected=bus_nets(bus['name']);actual=bus.get('nets',[])
            if len(actual)!=len(expected) or len(set(actual))!=len(actual):add('ERC.BUS.WIDTH',c,bus['name']+' has an incomplete or repeated scalar mapping.',bus['id'],path=path,root=root)
            elif actual!=expected:add('ERC.BUS.MAPPING',c,bus['name']+' scalar mapping differs from its declared order.',bus['id'],path=path,root=root)
        grouped=defaultdict(list)
        for d in c['devices']:
            sm=by[d['cell']].get('symbol',{}) if d['kind']=='X' else d.get('symbol',{})
            for pin,n in d['nets'].items():
                m=sm.get('pin_meta',{}).get(pin,{});direction=m.get('direction','out' if d['kind']=='V' and pin=='p' else 'passive');grouped[n].append((d,pin,direction,m.get('required',True)))
        for n,refs in grouped.items():
            outputs=[r for r in refs if r[2]=='out'];inputs=[r for r in refs if r[2]=='in' and r[3]]
            if len(outputs)>1:add('ERC.DRIVERS',c,'Multiple outputs drive '+n+': '+', '.join(d['name']+'.'+pin for d,pin,_,_ in outputs),outputs[0][0]['id'],outputs[0][1],n,path,root)
            external=n in c['ports'] and meta.get(n,{}).get('direction','inout') in ('in','inout')
            if inputs and all(r[2]=='in' for r in refs) and not external:add('ERC.UNDRIVEN',c,'Input net '+n+' has no output, passive/source connection or external input.',inputs[0][0]['id'],inputs[0][1],n,path,root)
        if c['shapes'] or c.get('layout_instances'):
            from .physical_cells import ports
            actual={port['name'] for port in ports(p,c['id'])};missing=set(c['ports'])-actual
            for name in sorted(missing):add('LAYOUT.PORTS',c,'Assign a physical port for '+name+'.',pin=name,net=name,path=path,root=root)
    def walk(c,path,mapping,root):
        nonlocal steps
        steps+=1
        if steps>10000:raise ValueError('Electrical check exceeds 10,000 hierarchy occurrences. Check a smaller subtree.')
        visited.add(c['id']);local(c,path,root);prefix='/'.join(path)+'/' if path else ''
        def net(n):return '0' if n=='0' else mapping.get(n,prefix+n)
        optional.update((root,net(n)) for n,m in c.get('symbol',{}).get('pin_meta',{}).items() if not m.get('required',True))
        for d in c['devices']:
            nets={pin:net(n) for pin,n in d['nets'].items()}
            if d['kind']=='X':walk(by[d['cell']],path+[d['id']],nets,root)
            else:
                if len(set(nets.values()))==1:add('ERC.SHORT',c,d['name']+': all terminals share one net.',d['id'],net=next(iter(d['nets'].values())),path=path,root=root)
                for pin,n in nets.items():counts[(root,n)].append((c,d,pin,path,d['nets'][pin]))
    walk(by[cid],[],{n:n for n in by[cid]['ports']},cid)
    if policy.get('scope')=='project':
        for key,c in by.items():
            if key not in visited:walk(c,[],{n:n for n in c['ports']},key)
    roots={root for root,_ in counts}
    if not counts:add('ERC.EMPTY',by[cid],'The selected hierarchy has no primitive devices.')
    for root in roots:
        if (root,'0') not in counts and not any(m.get('role')=='ground' for m in by[root].get('symbol',{}).get('pin_meta',{}).values()):add('ERC.GROUND',by[root],'Circuit has no ground net (0).',root=root)
    for (root,n),refs in counts.items():
        if len(refs)==1 and n not in by[root]['ports'] and (root,n) not in optional:
            c,d,pin,path,localnet=refs[0]
            if d.get('symbol',{}).get('pin_meta',{}).get(pin,{}).get('required',True):add('ERC.DANGLING',c,d['name']+'.'+pin+' is alone on net '+localnet+'.',d['id'],pin,localnet,path,root)
    return issues
