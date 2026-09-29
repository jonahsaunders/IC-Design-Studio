"""Occurrence-aware schematic/physical links and explicit net propagation."""
from .physical_cells import terminals,ports

def net_names(p,cid):
    """Offer scalar probe choices for compact buses and project globals."""
    from .native_vectors import devices, ports as scalar_ports, global_nets
    cell=next(c for c in p['cells'] if c['id']==cid)
    return sorted({net for d in devices(cell,p) for net in d['nets'].values()} |
                  set(scalar_ports(cell['ports'])) | set(global_nets(p)))

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
    from .native_vectors import devices, ports as scalar_ports, global_nets
    globals_=set(global_nets(p))
    by={c['id']:c for c in p['cells']};rows=[];steps=0
    def walk(cid,path,names,mapping,array_path):
        nonlocal steps
        steps+=1
        if steps>10000:raise ValueError('Net probe exceeds 10,000 hierarchy occurrences.')
        c=by[cid];expanded=devices(c,p)
        localnets={n for d in expanded for n in d['nets'].values()}|set(scalar_ports(c['ports']))
        selected={n for n in localnets if (n=='0' or n in globals_) and n==name or mapping.get(n)==name}
        for net in sorted(selected):
            attached=[d for d in expanded if net in d['nets'].values()]
            row={'root':root,'cell':cid,'path':list(path),'name':' / '.join(names),'net':net,
                 'objects':list(dict.fromkeys(d.get('array_source_id',d['id']) for d in attached))}
            # Navigation uses the real compact capture IDs. Member indices and
            # names distinguish electrical occurrences without inventing editor
            # objects or treating a member as a separately placed physical cell.
            if array_path:row['array_path']=list(array_path)
            members={}
            for d in attached:
                if 'array_source_id' in d:members.setdefault(d['array_source_id'],[]).append(d['array_index'])
            if members:row['array_members']=members
            rows.append(row)
        for d in expanded:
            if d['kind']=='X':
                ident=d.get('array_source_id',d['id'])
                member=[{'device_id':ident,'index':d['array_index']}] if 'array_source_id' in d else []
                walk(d['cell'],path+[ident],names+[d['name']],{pin:name for pin,n in d['nets'].items() if n in selected},array_path+member)
    walk(root,[],[by[root]['name']],{name:name},[]);return rows
