"""Atomic schematic editing and stable reusable-cell interfaces (no GUI state)."""
from .model import clone,uid,device,NET,NAME
from . import wiring,net_labels
from .symbol_io import default_symbol,validate_symbol
from .symbol_geometry import enriched

def cell(project,cid):return next(c for c in project['cells'] if c['id']==cid)

def transform(project,cid,ids,dx=0,dy=0,stretch=True,copy=False,mirror=False):
    c=cell(project,cid);old=clone(c);before=wiring.pins(c,project);ids=set(ids);mapping={};names={d['name'].casefold() for d in c['devices']}
    for group in ('devices','wires','labels','annotations'):
        for obj in list(c.get(group,[])):
            if obj['id'] not in ids:continue
            if copy:
                source=obj;obj=clone(obj);obj['id']=uid();mapping[source['id']]=obj['id'];c[group].append(obj)
                if group=='devices':
                    base=obj['name'];i=2
                    while (base+'_'+str(i)).casefold() in names:i+=1
                    obj['name']=base+'_'+str(i);names.add(obj['name'].casefold());obj['net_labels']={}
            if group=='devices':
                obj['x']+=dx;obj['y']+=dy
                if mirror:obj['mirror']=not obj.get('mirror',False)
            elif group=='annotations':
                obj['x']+=dx;obj['y']+=dy
                if copy:obj.pop('xschem_record',None)
            elif group=='wires':obj['points']=[[x+dx,y+dy] for x,y in obj['points']]
            else:
                a=obj['anchor']
                if copy and a.get('id') in mapping:a['id']=mapping[a['id']]
                if a['kind']=='point' or a['kind']=='wire' and (a['id'] in ids or a['id'] in mapping.values()):a['point']=[a['point'][0]+dx,a['point'][1]+dy]
                elif a.get('id') not in ids and a.get('id') not in mapping.values():obj['offset']=[obj['offset'][0]+dx,obj['offset'][1]+dy]
    for label in c.get('labels',[]):
        a=label['anchor']
        if label['id'] not in ids and not copy and a['kind']=='wire' and a['id'] in ids:a['point']=[a['point'][0]+dx,a['point'][1]+dy]
    if stretch and not copy:wiring.keep_connections(c,before,project,[w['id'] for w in old.get('wires',[]) if w['id'] in ids])
    net_labels.reconcile(c,old,project);wiring.rebuild(c,project)
    return list(mapping.values()) if copy else list(ids)

def cut_wire(project,cid,wire_id,index,point,gap=10):
    c=cell(project,cid);old=clone(c);w=next(w for w in c['wires'] if w['id']==wire_id);a,b=w['points'][index:index+2];q=wiring.nearest(point,a,b);axis=0 if a[1]==b[1] else 1;direction=1 if b[axis]>a[axis] else -1
    left=list(q);right=list(q);left[axis]-=direction*gap/2;right[axis]+=direction*gap/2
    if not all(wiring.on_segment(pt,a,b) and pt not in (a,b) for pt in (left,right)):raise ValueError('Cut inside a segment, at least 10 units from either end.')
    contacts=list(wiring.pins(c,project).values())+c.get('junctions',[])
    if any(wiring.on_segment(pt,left,right) for pt in contacts):raise ValueError('Move the cut away from a terminal or junction.')
    new={'id':uid(),'points':wiring.clean([right]+w['points'][index+1:])};w['points']=wiring.clean(w['points'][:index+1]+[left]);c['wires'].append(new)
    for l in c.get('labels',[]):
        anchor=l['anchor']
        if anchor['kind']=='wire' and anchor['id']==wire_id:
            if any(wiring.on_segment(anchor['point'],a,b) for a,b in zip(new['points'],new['points'][1:])):anchor['id']=new['id']
            elif wiring.on_segment(anchor['point'],left,right):anchor.update(kind='point');anchor.pop('id',None)
    net_labels.reconcile(c,old,project);wiring.rebuild(c,project);return [wire_id,new['id']]

def rejoin(project,cid,ids):
    c=cell(project,cid);ws=[w for w in c.get('wires',[]) if w['id'] in ids]
    if len(ws)!=2:raise ValueError('Select exactly two wires to rejoin their nearest ends.')
    _,a,b=min((abs(a[0]-b[0])+abs(a[1]-b[1]),a,b) for a in (ws[0]['points'][0],ws[0]['points'][-1]) for b in (ws[1]['points'][0],ws[1]['points'][-1]))
    if a==b:raise ValueError('These wires already share an endpoint.')
    result=wiring.add_wire(c,wiring.clean([a,[b[0],a[1]],b]),project);wiring.rebuild(c,project);return result

def bulk_parameters(project,cid,ids,changes):
    c=cell(project,cid);chosen=[d for d in c['devices'] if d['id'] in ids]
    if not chosen:raise ValueError('Select devices first.')
    for d in chosen:
        for field,value in changes.items():
            if field=='value':d['value']=value
            elif field.startswith('params.'):
                key=field.split('.',1)[1]
                if key not in d['params']:raise ValueError(d['name']+': unknown parameter '+key)
                d['params'][key]=value
            elif field.startswith('parameters.') and d['kind']=='X':
                key=field.split('.',1)[1]
                if key not in cell(project,d['cell']).get('parameters',{}):raise ValueError('Unknown cell parameter '+key)
                d.setdefault('parameters',{})[key]=value
            else:raise ValueError('Choose a shared value, device parameter or cell parameter.')
    from .model import validate
    validate(project)

def make_cell(project,cid,ids,name):
    c=cell(project,cid);chosen=[d for d in c['devices'] if d['id'] in ids];selected={d['id'] for d in chosen}
    if not chosen:raise ValueError('Select the circuitry to turn into a cell.')
    if not NAME.fullmatch(name) or any(v['name'].casefold()==name.casefold() for v in project['cells']):raise ValueError('Use a unique cell identifier.')
    if any(s.get('device_id') in selected for s in c['shapes']+c.get('layout_pins',[])+c.get('layout_instances',[])):raise ValueError('Detach or move the linked physical implementation before extracting these devices into a new cell.')
    if any(t['bench_cell']==cid and t.get('dut_instance') in selected for t in project.get('testbenches',[])):raise ValueError('Edit this saved testbench interface before extracting its DUT instance.')
    old=clone(c);positions=wiring.pins(c,project);groups=wiring.graph(c,project);inside={n for d in chosen for n in d['nets'].values()};outside={n for d in c['devices'] if d['id'] not in selected for n in d['nets'].values()}|set(c['ports']);ports=sorted((inside&outside)-{'0'})
    cx=round(sum(d['x'] for d in chosen)/len(chosen)/10)*10;cy=round(sum(d['y'] for d in chosen)/len(chosen)/10)*10
    child={'id':uid(),'name':name,'ports':ports,'devices':clone(chosen),'shapes':[],'parameters':clone(c.get('parameters',{}))}
    for d in child['devices']:d['x']-=cx;d['y']-=cy;d.pop('net_labels',None)
    symbol=enriched(default_symbol(ports));symbol['pins']={n:[pt[0]-cx,pt[1]-cy] for n in ports for pt in [next(positions[(d['id'],pin)] for d in chosen for pin,value in d['nets'].items() if value==n)]}
    # Interface pins keep the former contacts; artwork can be regenerated afterwards.
    validate_symbol(symbol,ports);child['symbol']=symbol;project['cells'].append(child);wiring.migrate(child,project)
    internal_roots={groups[(d['id'],pin)] for d in chosen for pin,n in d['nets'].items() if n not in outside and n!='0'}
    c['devices']=[d for d in c['devices'] if d['id'] not in selected];c['wires']=[w for w in c.get('wires',[]) if groups[('wire',w['id'])] not in internal_roots]
    names={d['name'].casefold() for d in c['devices']};i=1
    while ('X'+str(i)).casefold() in names:i+=1
    inst=device('X','X'+str(i),cx,cy,cell=child['id'],nets={n:n for n in ports},net_labels={n:n for n in ports},symbol=clone(symbol));c['devices'].append(inst)
    for label in c.get('labels',[]):
        anchor=label['anchor']
        if anchor['kind']=='pin' and anchor['id'] in selected:
            olddevice=next(d for d in chosen if d['id']==anchor['id']);net=olddevice['nets'][anchor['pin']]
            if net in ports:anchor.update(id=inst['id'],pin=net)
    net_labels.reconcile(c,old,project);wiring.rebuild(c,project);return child['id'],inst['id']

def apply_symbol(project,cid,symbol,base=None):
    c=cell(project,cid);base=base or enriched(c.get('symbol') or default_symbol(c['ports']));s=enriched(symbol);validate_symbol(s,s['pins']);order=s['pin_order'];oldports=list(c['ports'])
    byid={m['id']:name for name,m in s['pin_meta'].items()};renames={old:byid.get(base['pin_meta'][old]['id'],old) for old in oldports};removed={old for old,new in renames.items() if new not in s['pins']}
    users=[(parent,d) for parent in project['cells'] for d in parent['devices'] if d.get('cell')==cid]
    if removed and (users or any(n in removed for d in c['devices'] for n in d['nets'].values())):raise ValueError('Disconnect and remove instances before deleting electrically used terminals: '+', '.join(sorted(removed)))
    if any(old!=new for old,new in renames.items()) and (c.get('layout_ports') or any(t['dut_cell']==cid for t in project.get('testbenches',[]))):raise ValueError('Rename terminals through the circuit interface before changing a physical port or saved testbench contract.')
    snapshots={p['id']:clone(p) for p,_ in users};before={key:wiring.pins(value,project) for key,value in snapshots.items()}
    for d in c['devices']:
        for field in ('nets','net_labels'):d[field]={pin:renames.get(n,n) for pin,n in d.get(field,{}).items()}
    for label in c.get('labels',[]):label['name']=renames.get(label['name'],label['name'])
    c.update(symbol=s,ports=order)
    for parent,d in users:
        d['nets']={renames.get(pin,pin):n for pin,n in d['nets'].items() if pin not in removed};d['nets']={pin:d['nets'].get(pin,'N_'+d['id']+'_'+pin) for pin in order}
        d['net_labels']={renames.get(pin,pin):n for pin,n in d.get('net_labels',{}).items() if pin not in removed};d['symbol']=clone(s)
        for token in d.get('native_spice', {}).get('tokens', []):
            if token['kind'] == 'terminal': token['value'] = renames.get(token['value'], token['value'])
        for label in parent.get('labels',[]):
            a=label['anchor']
            if a.get('kind')=='pin' and a.get('id')==d['id']:a['pin']=renames.get(a['pin'],a['pin'])
        before[parent['id']]={(ident,renames.get(pin,pin) if ident==d['id'] else pin):pt for (ident,pin),pt in before[parent['id']].items()}
    for key,old in snapshots.items():
        parent=cell(project,key);wiring.keep_connections(parent,before[key],project);net_labels.reconcile(parent,old,project);wiring.rebuild(parent,project)
    wiring.rebuild(c,project)

def findings(project,cid):
    from .electrical_rules import check
    return check(project,cid)
