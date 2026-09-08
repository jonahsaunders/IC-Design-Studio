"""Geometric connectivity, Manhattan routing, and regenerable layout recipes."""
from __future__ import annotations
from .model import uid,clone,digest,design_digest,scalar
from .layout import kdb,polygon,shape_from_polygon,rect,guard_ring,generate_mos
from .design_ops import flatten_layout
from .spatial import SpatialIndex

def recipe_cell(name,spec,source_device=None):
    kind=spec['kind'];x=y=0
    if kind=='guard_ring':
        shapes=guard_ring(0,0,int(spec['width']),int(spec['height']),int(spec['thickness']),spec.get('net','0'))
        for s in shapes:s['layer']=spec.get('layer','metal1')
    elif kind=='mos':
        if source_device is None or source_device['kind'] not in ('NMOS','PMOS'):raise ValueError('Select a MOS device for this generator.')
        shapes=generate_mos(source_device,fingers=int(spec.get('fingers',1)))
    elif kind=='interdigitated':
        count=int(spec.get('count',4));width=int(spec['width']);height=int(spec['height']);gap=int(spec['gap'])
        if not 2<=count<=64 or min(width,height,gap)<=0:raise ValueError('Use 2–64 fingers and positive dimensions.')
        shapes=[rect(spec.get('layer','metal1'),i*(width+gap),0,width,height,net=spec.get('net_a','a') if i%2==0 else spec.get('net_b','b')) for i in range(count)]
    else:raise ValueError('Unknown layout generator.')
    return {'id':uid(),'name':name,'ports':[],'devices':[],'shapes':shapes,'generator':{'api':1,'spec':clone(spec),'source_device':clone(source_device)}}

def regenerate(cell,spec=None):
    recipe=cell.get('generator')
    if not recipe:raise ValueError('This cell has no saved generator recipe.')
    new=recipe_cell(cell['name'],spec or recipe['spec'],recipe.get('source_device'));cell['shapes']=new['shapes'];cell['generator']=new['generator']

def erase(cell,layer,box):
    db=kdb();brush=db.Region(db.Box(*box));out=[]
    for s in cell['shapes']:
        if s['layer']!=layer:out.append(s);continue
        region=db.Region(polygon(s));cut=region-brush
        if (region^cut).is_empty():out.append(s);continue
        for poly in cut.each():out.append(shape_from_polygon(poly,layer,s.get('net',''),s.get('device_id','')))
    cell['shapes']=out

def route(p,cid,layer,start,end,width,net):
    db=kdb();width=int(width);tech=next(l for l in p['pdk']['layers'] if l['name']==layer);grid=p['pdk']['grid']
    if width<max(1,tech['width']) or any(v%grid for v in list(start)+list(end)):raise ValueError('Use on-grid endpoints and a width at least the technology minimum.')
    if start==end:raise ValueError('Route endpoints must differ.')
    obstacles=db.Region()
    for s in flatten_layout(p,cid):
        if s['layer']==layer and (not net or s.get('net')!=net):obstacles.insert(polygon(s))
    clearance=int(tech['space']);blocked=obstacles.sized(clearance);sx,sy=start;ex,ey=end
    candidates=[[[sx,sy],[ex,sy],[ex,ey]],[[sx,sy],[sx,ey],[ex,ey]]]
    # Candidate detours along inflated obstacle edges, followed by exact polygon collision tests.
    margin=clearance+(width+1)//2+grid;xs=set();ys=set()
    for poly in obstacles.merged().each():
        b=poly.bbox();xs.update((grid*((b.left-margin)//grid),grid*((b.right+margin+grid-1)//grid)));ys.update((grid*((b.bottom-margin)//grid),grid*((b.top+margin+grid-1)//grid)))
    if len(xs)+len(ys)>1000:raise ValueError('Too many routing obstacles. Route a shorter section.')
    candidates += [[[sx,sy],[x,sy],[x,ey],[ex,ey]] for x in xs]
    candidates += [[[sx,sy],[sx,y],[ex,y],[ex,ey]] for y in ys]
    candidates.sort(key=lambda pts:sum(abs(a[0]-b[0])+abs(a[1]-b[1]) for a,b in zip(pts,pts[1:])))
    for points in candidates:
        points=[pt for i,pt in enumerate(points) if not i or pt!=points[i-1]]
        s={'id':uid(),'kind':'path','layer':layer,'width':width,'points':points,'net':net,'device_id':''}
        if (db.Region(polygon(s))&blocked).is_empty():return s
    raise ValueError('No clear Manhattan route with up to two bends. Add an intermediate waypoint or choose another layer.')

def connectivity(p,cid):
    """Compare explicit physical terminals using actual polygon contact, not device links."""
    db=kdb();cell=next(c for c in p['cells'] if c['id']==cid);shapes=flatten_layout(p,cid)
    conductors=set(p['pdk'].get('connectivity',{}).get('conductors',['metal1','metal2']))
    vias=p['pdk'].get('connectivity',{}).get('vias',[['metal1','via1','metal2']]);allowed={(a,b) for a,v,b in vias for a,b in ((a,v),(v,a),(v,b),(b,v))}
    layers=conductors|{v for _,v,_ in vias};shapes=[s for s in shapes if s['layer'] in layers]
    if len(shapes)>20000:raise ValueError('Connectivity check is limited to 20,000 conducting shapes.')
    polys=[polygon(s) for s in shapes];regions=[db.Region(poly) for poly in polys];parents=list(range(len(shapes)))
    def find(i):
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    def union(a,b):parents[find(a)]=find(b)
    index=SpatialIndex([((b.left,b.bottom,b.right,b.top),i) for i,poly in enumerate(polys) for b in [poly.bbox()]])
    for i,poly in enumerate(polys):
        b=poly.bbox()
        for j in index.query((b.left,b.bottom,b.right,b.top)):
            if j<=i:continue
            a,b=shapes[i]['layer'],shapes[j]['layer']
            if (a==b or (a,b) in allowed) and not regions[i].interacting(regions[j]).is_empty():union(i,j)
    from .physical_cells import terminals
    physical_pins=terminals(p,cid)
    issues=[];assignments={};expected={};ds={d['id']:d for d in cell['devices']};provided=set()
    def issue(code,obj,message,**extra):issues.append({'severity':'error','code':code,'cell_id':cid,'object':obj,'message':message,**extra})
    for pin in physical_pins:
        d=ds[pin['device_id']];provided.add((d['id'],pin['pin']));x,y=pin['point'];hits=[i for i in index.query((x,y,x,y)) if shapes[i]['layer']==pin['layer'] and polys[i].inside(db.Point(x,y))]
        if not hits:issue('LVS.UNLANDED',d['id'],f'{d["name"]}.{pin["pin"]}: physical terminal does not land on a conductor.');continue
        roots={find(i) for i in hits}
        if len(roots)!=1:issue('LVS.AMBIGUOUS',d['id'],'Terminal lies on disconnected boundary geometry.');continue
        root=roots.pop();net=d['nets'][pin['pin']];assignments.setdefault(root,[]).append((d['id'],pin['pin'],net));expected.setdefault(net,set()).add(root)
    for d in cell['devices']:
        if d['kind'] in ('V','I'):continue # Testbench sources do not require silicon footprints.
        for pin in d['nets']:
            if (d['id'],pin) not in provided:issue('LVS.MISSING_PIN',d['id'],f'{d["name"]}.{pin}: assign a physical terminal before checking connectivity.')
    for root,refs in assignments.items():
        nets={r[2] for r in refs}
        if len(nets)>1:issue('LVS.SHORT',refs[0][0],'Conductors short schematic nets: '+', '.join(sorted(nets)),nets=sorted(nets),objects=list(dict.fromkeys(shapes[i]['id'] for i in range(len(shapes)) if find(i)==root)))
    for i,s in enumerate(shapes):
        if s.get('net') and not s.get('instance_path'):
            refs=assignments.get(find(i),[]);names={r[2] for r in refs}
            if not names:issue('LVS.FLOATING_LABEL',s['id'],'Labeled conductor '+s['net']+' has no assigned terminal connection.')
            elif s['net'] not in names:issue('LVS.LABEL',s['id'],'Conductor label '+s['net']+' disagrees with its terminal net: '+', '.join(sorted(names)))
    guides=[]
    terminal_points={(pin['device_id'],pin['pin']):pin['point'] for pin in physical_pins}
    for net,roots in expected.items():
        if len(roots)>1:issue('LVS.OPEN',next(r[0] for root in roots for r in assignments[root] if r[2]==net),f'Net {net} has {len(roots)} disconnected conductor groups. Follow the dashed connection guides and reconnect the terminals.',net=net,disconnected_groups=len(roots))
        remaining=set(roots)
        if remaining:
            reached={min(remaining)};remaining-=reached
            while remaining:
                choices=[]
                for a in reached:
                    for b in remaining:
                        for da,pa,na in assignments[a]:
                            for db_,pb,nb in assignments[b]:
                                if na==nb==net:
                                    start=terminal_points[da,pa];end=terminal_points[db_,pb]
                                    choices.append((sum((x-y)**2 for x,y in zip(start,end)),b,start,end))
                _,b,start,end=min(choices);guides.append({'net':net,'start':start,'end':end});reached.add(b);remaining.remove(b)
    if not physical_pins:issue('LVS.NO_TERMINALS','', 'No physical terminals are assigned; connectivity cannot be verified.')
    for i in issues:i['fingerprint']=digest({'revision':p['revision'],'code':i['code'],'object':i['object'],'message':i['message']})
    return {'issues':issues,'guides':guides,'net_regions':[{'net':next(iter({r[2] for r in refs})),'shapes':[shapes[i] for i in range(len(shapes)) if find(i)==root]} for root,refs in assignments.items() if len({r[2] for r in refs})==1],'groups':[[shapes[i]['id'] for i in range(len(shapes)) if find(i)==root] for root in sorted({find(i) for i in range(len(shapes))})],'design_hash':design_digest(p),'qualification':'Terminal connectivity only; device recognition and foundry LVS require a qualified extraction deck.'}

def capacitance_estimate(p,cid):
    """Ground-capacitance estimate from declared area/perimeter coefficients."""
    db=kdb();coeff=p['pdk'].get('parasitics',{});grouped={}
    if not coeff:raise ValueError('Technology has no area/perimeter capacitance coefficients. Supply calibrated coefficients or use Magic extraction.')
    check=connectivity(p,cid)
    if check['issues']:raise ValueError('Resolve physical connectivity findings before estimating parasitics.')
    for group in check['net_regions']:
        net=group['net']
        if net=='0':continue
        for s in group['shapes']:
            layer=s['layer']
            if layer in coeff:grouped.setdefault((net,layer),db.Region()).insert(polygon(s))
    out=[]
    for (net,layer),region in grouped.items():
        region.merge();data=coeff[layer];area_coefficient=scalar(data.get('cap_f_per_um2',0));edge_coefficient=scalar(data.get('edge_f_per_um',0))
        if area_coefficient<0 or edge_coefficient<0:raise ValueError('Capacitance coefficients must be non-negative.')
        cap=region.area()*1e-6*area_coefficient+region.perimeter()*1e-3*edge_coefficient
        if cap<0:raise ValueError('Capacitance coefficients must be non-negative.')
        if cap:out.append({'net':net,'layer':layer,'capacitance':cap})
    if not out:raise ValueError('No labeled signal geometry has matching capacitance coefficients.')
    return {'design_hash':design_digest(p),'pdk_hash':digest(p['pdk']),'capacitors':out,'qualification':'Lumped ground capacitance estimate; no coupling or distributed resistance.'}

def with_parasitics(p,cid,extraction):
    from .model import device
    if extraction['design_hash']!=design_digest(p) or extraction['pdk_hash']!=digest(p['pdk']):raise ValueError('Extraction is stale. Extract the current revision again.')
    out=clone(p);cell=next(c for c in out['cells'] if c['id']==cid);names={d['name'].casefold() for d in cell['devices']}
    for i,item in enumerate(extraction['capacitors']):
        name='Cpar_'+str(i+1)
        while name.casefold() in names:name+='x'
        names.add(name.casefold());cell['devices'].append(device('C',name,value=str(item['capacitance']),nets={'p':item['net'],'n':'0'}))
    return out


def matching_checks(p,cid):
    cell=next(c for c in p['cells'] if c['id']==cid);instances={i['id']:i for i in cell.get('layout_instances',[])};issues=[]
    for constraint in cell.get('constraints',[]):
        if constraint.get('kind')!='common_centroid':continue
        centers=[]
        for group in constraint['groups']:
            if not group or any(i not in instances for i in group):
                issues.append({'severity':'error','code':'MATCH.MISSING','object':'','message':'A common-centroid constraint references a deleted physical instance.'});break
            centers.append([sum(instances[i][axis] for i in group)/len(group) for axis in ('x','y')])
        else:
            if any(center!=centers[0] for center in centers[1:]):issues.append({'severity':'error','code':'MATCH.CENTROID','object':constraint['groups'][0][0],'message':'Matched instance-origin centroids differ. Restore the common-centroid placement.'})
    for issue in issues:issue['fingerprint']=digest({'revision':p['revision'],**issue})
    return issues
