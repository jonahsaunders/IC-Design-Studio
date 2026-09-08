"""Reviewable, revision-bound electrical interface migrations across cell views."""
from .model import clone,digest,validate,uid,NET
from .symbol_geometry import enriched
from .symbol_io import default_symbol,validate_symbol
from . import wiring,net_labels
from .physical_cells import ports as layout_ports

def get(p,cid):return next(c for c in p['cells'] if c['id']==cid)

def default_mapping(cell,symbol,base=None):
    old=enriched(base or cell.get('symbol') or default_symbol(cell['ports']));new=enriched(symbol)
    ids={m['id']:name for name,m in new['pin_meta'].items()}
    return {name:ids.get(old['pin_meta'][name]['id'],name if name in new['pins'] else None) for name in cell['ports']}

def affected_benches(p,cid):
    ancestors={cid}
    while True:
        expanded=ancestors|{c['id'] for c in p['cells'] if any(d.get('cell') in ancestors for d in c['devices'])}
        if expanded==ancestors:break
        ancestors=expanded
    return [t for t in p.get('testbenches',[]) if t['dut_cell'] in ancestors or t['bench_cell']==cid]

def describe(p,cid,symbol,base=None):
    c=get(p,cid);mapping=default_mapping(c,symbol,base);users=[{'cell':parent['id'],'cell_name':parent['name'],'id':d['id'],'name':d['name'],'nets':clone(d['nets']),'physical':any(i.get('device_id')==d['id'] for i in parent.get('layout_instances',[]))} for parent in p['cells'] for d in parent['devices'] if d.get('cell')==cid]
    return {'mapping':mapping,'added':[n for n in symbol['pins'] if n not in mapping.values()],'removed':[n for n,v in mapping.items() if v is None],'instances':users,'physical_ports':layout_ports(p,cid),'testbenches':[{'id':t['id'],'name':t['name']} for t in affected_benches(p,cid)]}

def plan(p,cid,symbol,base=None,mapping=None,connections=None,physical=None,drop_invalid_probes=False):
    """Prepare the complete candidate; nothing is mutated until apply()."""
    original=get(p,cid);s=enriched(symbol);validate_symbol(s,s['pins']);order=s['pin_order'];mapping=clone(mapping if mapping is not None else default_mapping(original,s,base));connections=connections or {};physical=physical or {}
    if set(mapping)!=set(original['ports']):raise ValueError('Map every existing terminal, or explicitly choose Disconnect.')
    targets=[n for n in mapping.values() if n is not None]
    if len(targets)!=len(set(targets)) or set(targets)-set(order):raise ValueError('Each terminal must map to a distinct proposed terminal. Net merging is a separate wiring operation.')
    removed={n for n,v in mapping.items() if v is None};renames={a:b for a,b in mapping.items() if b is not None and a!=b};added=[n for n in order if n not in targets]
    oldbase=enriched(base or original.get('symbol') or default_symbol(original['ports']))
    for old,new in mapping.items():
        if new is not None:s['pin_meta'][new]['id']=oldbase['pin_meta'][old]['id']
    validate_symbol(s,order)
    used={n for d in original['devices'] for n in d['nets'].values()}|{l['name'] for l in original.get('labels',[])}|{v.get('net','') for v in original['shapes']}
    if any(new in used and (new not in mapping or mapping[new] is None) for new in renames.values()):raise ValueError('A proposed terminal name already identifies a different internal net. Choose a unique name.')
    q=clone(p);c=get(q,cid);users=[(parent,d) for parent in q['cells'] for d in parent['devices'] if d.get('cell')==cid];snapshots={parent['id']:clone(parent) for parent,_ in users};before={key:wiring.pins(value,p) for key,value in snapshots.items()};oldphysical=layout_ports(p,cid)
    userids={d['id'] for _,d in users}
    if set(connections)-userids:raise ValueError('An instance connection refers to a missing use of this cell.')
    for did,values in connections.items():
        if set(values)-set(added):raise ValueError('Supply instance connections only for added terminals.')
        if any(n and (not isinstance(n,str) or not NET.fullmatch(n)) for n in values.values()):raise ValueError('Invalid instance net name.')
    for d in c['devices']:
        for field in ('nets','net_labels'):d[field]={pin:renames.get(n,n) for pin,n in d.get(field,{}).items()}
    for label in c.get('labels',[]):label['name']=renames.get(label['name'],label['name'])
    for shape in c['shapes']:shape['net']=renames.get(shape.get('net',''),shape.get('net',''))
    for record in c.get('pdk_layouts',[]):
        spec=record.get('spec',{})
        if 'nets' in spec:spec['nets']={pin:renames.get(n,n) for pin,n in spec['nets'].items()}
    # Port labels are exact net names, not free-text find/replace.
    c['layout_texts']=[{**text,'text':renames.get(text['text'],text['text'])} for text in c.get('layout_texts',[]) if text['text'] not in removed]
    if oldphysical or 'layout_ports' in c or physical:
        c['layout_ports']=[{**port,'name':mapping.get(port['name'],port['name'])} for port in oldphysical if port['name'] not in removed]
        for name,spec in physical.items():
            if name not in added:raise ValueError('Physical placement is specified only for added terminals.')
            if spec:
                point=spec.get('point',[]);layer=spec.get('layer');grid=q['pdk']['grid']
                if layer not in {l['name'] for l in q['pdk']['layers']} or len(point)!=2 or any(type(v) is not int or v%grid for v in point):raise ValueError('Physical ports need a mapped layer and integer coordinates on the layout grid.')
                c['layout_ports'].append({'name':name,'layer':layer,'point':clone(point)})
                from .process_adapters import layer_datatypes
                labeltype=layer_datatypes(q['pdk'])[1];gds=next(l['gds'] for l in q['pdk']['layers'] if l['name']==layer);label=next((l['name'] for l in q['pdk']['layers'] if l['gds']==gds and l['datatype']==labeltype),None)
                if label:c['layout_texts'].append({'layer':label,'text':name,'x':point[0],'y':point[1],'rotation':0})
    for bus in c.get('buses',[]):bus['nets']=[renames.get(n,n) for n in bus.get('nets',[])]
    c.update(symbol=s,ports=list(order));disconnected=[]
    for parent,d in users:
        oldnets=clone(d['nets']);oldlabels=clone(d.get('net_labels',{}));oldpos=before[parent['id']]
        for old in removed:
            pt=oldpos[(d['id'],old)];disconnected.append({'cell':parent['id'],'instance':d['name'],'pin':old,'net':oldnets[old]})
            attached=False
            for label in parent.get('labels',[]):
                a=label['anchor']
                if a.get('kind')=='pin' and a.get('id')==d['id'] and a['pin']==old:label['anchor']={'kind':'point','point':clone(pt)};attached=True
            if old in oldlabels and not attached:parent.setdefault('labels',[]).append({'id':uid(),'kind':'net_label','name':oldlabels[old],'anchor':{'kind':'point','point':clone(pt)},'offset':[10,-12],'rotation':0})
        d['nets']={mapping[pin]:n for pin,n in oldnets.items() if mapping[pin] is not None};d['net_labels']={mapping[pin]:n for pin,n in oldlabels.items() if mapping[pin] is not None}
        for pin in added:
            net=connections.get(d['id'],{}).get(pin) or 'N_'+d['id']+'_'+pin;d['nets'][pin]=net
            if connections.get(d['id'],{}).get(pin):d['net_labels'][pin]=net
        d['nets']={pin:d['nets'][pin] for pin in order};d['symbol']=clone(s)
        for label in parent.get('labels',[]):
            a=label['anchor']
            if a.get('kind')=='pin' and a.get('id')==d['id']:a['pin']=mapping[a['pin']]
        parent['layout_pins']=[{**pin,'pin':mapping[pin['pin']]} if pin['device_id']==d['id'] else pin for pin in parent.get('layout_pins',[]) if pin['device_id']!=d['id'] or pin['pin'] not in removed]
        before[parent['id']]={(ident,mapping[pin] if ident==d['id'] else pin):pt for (ident,pin),pt in oldpos.items() if ident!=d['id'] or pin not in removed}
    for key,old in snapshots.items():
        parent=get(q,key);wiring.keep_connections(parent,before[key],q);net_labels.reconcile(parent,old,q);wiring.rebuild(parent,q)
    wiring.rebuild(c,q);bench_changes=[]
    for bench in q.get('testbenches',[]):
        if bench['bench_cell']==cid:
            bench['probes']=[renames.get(n,n) for n in bench['probes']];bench['initial_conditions']={renames.get(n,n):v for n,v in bench.get('initial_conditions',{}).items()}
            for m in bench['measurements']:
                for field in ('node','input','reference'):
                    if field in m:m[field]=renames.get(m[field],m[field])
        fixture=get(q,bench['bench_cell']);nets={n for d in fixture['devices'] for n in d['nets'].values()};missing=set(bench['probes'])-nets
        if missing:
            if not drop_invalid_probes:raise ValueError(bench['name']+': removal leaves missing probe(s) '+', '.join(sorted(missing))+'. Review removal of their measurements or connect replacement fixture nets.')
            bench['probes']=[n for n in bench['probes'] if n not in missing];bench['initial_conditions']={n:v for n,v in bench.get('initial_conditions',{}).items() if n not in missing};removed_measures=[m['name'] for m in bench['measurements'] if any(m.get(k) in missing for k in ('node','input','reference'))];bench['measurements']=[m for m in bench['measurements'] if m['name'] not in removed_measures];bench_changes.append({'testbench':bench['name'],'removed_probes':sorted(missing),'removed_measurements':removed_measures})
    impact=describe(p,cid,s,base);impact.update(mapping=mapping,added=added,removed=sorted(removed),disconnected=disconnected,bench_changes=bench_changes,unassigned_physical=[n for n in added if (oldphysical or c.get('shapes') or c.get('layout_instances')) and n not in {v['name'] for v in c.get('layout_ports',[])}])
    c.setdefault('interface_history',[]).append({'revision':p['revision'],'old_ports':list(original['ports']),'ports':order,'mapping':mapping,'disconnected':disconnected,'testbenches':impact['testbenches']});c['interface_history']=c['interface_history'][-20:]
    validate(q)
    return {'base_hash':digest(p),'cell':cid,'candidate':q,'impact':impact,'candidate_hash':digest(q)}

def apply(project,review):
    if digest(project)!=review['base_hash']:raise ValueError('The project changed after this review. Refresh the interface review before applying.')
    if digest(review['candidate'])!=review['candidate_hash']:raise ValueError('The reviewed candidate changed. Refresh the interface review.')
    validate(review['candidate']);project.clear();project.update(clone(review['candidate']))
