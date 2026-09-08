"""Occurrence-aware schematic/physical links and explicit net propagation."""
from .physical_cells import terminals,ports

def occurrences(p,root):
    by={c['id']:c for c in p['cells']};rows=[];pin_cache={}
    def walk(cid,path,names):
        c=by[cid];pin_cache.setdefault(cid,{(t['device_id'],t['pin']) for t in terminals(p,cid)})
        for d in c['devices']:
            if len(rows)>=10000:raise ValueError('Cross-probing exceeds 10,000 instances. Open a smaller subtree.')
            placements=[i['id'] for i in c.get('layout_instances',[]) if i.get('device_id')==d['id']];shapes=[s['id'] for s in c['shapes'] if s.get('device_id')==d['id'] or s.get('generated_device')==d['id']];missing=[pin for pin in d['nets'] if (d['id'],pin) not in pin_cache[cid]]
            status='Testbench source' if d['kind'] in ('V','I') else 'Placed' if placements or shapes else 'Missing placement'
            if status=='Placed' and missing:status='Missing terminals'
            if len(placements)>1:status='Duplicate placement'
            rows.append({'root':root,'cell':cid,'path':list(path),'object':d['id'],'name':' / '.join(names+[d['name']]),'kind':d['kind'],'physical':placements+shapes,'status':status,'missing_pins':missing})
            if d['kind']=='X':walk(d['cell'],path+[d['id']],names+[d['name']])
    walk(root,[],[by[root]['name']]);return rows

def net_occurrences(p,root,name):
    """Resolve a root net through instance terminal mappings; internal names are local."""
    by={c['id']:c for c in p['cells']};rows=[];steps=0
    def walk(cid,path,names,mapping):
        nonlocal steps
        steps+=1
        if steps>10000:raise ValueError('Net probe exceeds 10,000 hierarchy occurrences.')
        c=by[cid];localnets={n for d in c['devices'] for n in d['nets'].values()}|set(c['ports']);selected={n for n in localnets if n=='0' and name=='0' or mapping.get(n)==name}
        for net in sorted(selected):rows.append({'root':root,'cell':cid,'path':list(path),'name':' / '.join(names),'net':net,'objects':[d['id'] for d in c['devices'] if net in d['nets'].values()]})
        for d in c['devices']:
            if d['kind']=='X':walk(d['cell'],path+[d['id']],names+[d['name']],{pin:name for pin,n in d['nets'].items() if n in selected})
    walk(root,[],[by[root]['name']],{name:name});return rows
