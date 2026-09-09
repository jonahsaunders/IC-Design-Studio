"""Bounded local translations on an already validated History project.

Only local, unowned shape geometry can change here. Footprints, physical
instances and generated geometry use the general isolated transaction path.
"""
from copy import copy
from .model import clone,validate_shape,validate
from .layout import kdb,polygon
from .layout_graph import GeometryGraph,key
from .wiring import retarget_path


def propose(p,cid,ids,dx,dy,locked=(),graph=None):
    c=next(c for c in p['cells'] if c['id']==cid);chosen=set(ids)
    if c.get('layout_instances'):return None
    from .layout_edit import selection_groups
    selection_groups(p,cid,ids,locked)
    if any(type(v) is not int or v%p['pdk']['grid'] for v in (dx,dy)):raise ValueError('Transforms require grid-aligned integer coordinates.')
    ownership=('pcell_id','via_group','generated_device','device_id','connected_lead')
    selected=[s for s in c['shapes'] if s['id'] in chosen]
    if any(s.get('connected_lead') or s.get('device_id') and not (s.get('generated_device') or s.get('pcell_id')) for s in selected):return None
    owned=any(any(s.get(k) for k in ownership) for s in selected)
    from .layout_arrange import translated_cell
    candidate=translated_cell(c,{sid:(dx,dy) for sid in chosen})
    db=kdb();changed={}
    routes=any(s['id'] not in chosen and s['kind']=='path' for s in c['shapes'])
    moving=[(s['layer'],polygon(s)) for s in selected] if routes else []
    from .layout_index import LayoutBoxIndex
    index=LayoutBoxIndex([(b.left,b.bottom,b.right,b.top) for _,poly in moving for b in [poly.bbox()]]) if moving else None
    for i,s in enumerate(c['shapes']):
        if s['id'] in chosen:
            changed[i]=candidate['shapes'][i]
            changed[i].setdefault('holes',[])
        elif s['kind']=='path' and not any(a==b or a[0]!=b[0] and a[1]!=b[1] for a,b in zip(s['points'],s['points'][1:])):
            targets=[]
            for pt in (s['points'][0],s['points'][-1]):
                nearby=(moving[j] for j in index.query((*pt,*pt))) if index is not None else ()
                attached=any(layer==s['layer'] and poly.inside(db.Point(*pt)) for layer,poly in nearby)
                targets.append([pt[0]+dx,pt[1]+dy] if attached else None)
            if any(v is not None for v in targets):
                if s['layer'] in locked:raise ValueError('Unlock attached route layers before moving the footprint.')
                if any(s.get(k) for k in ownership):return None
                q=clone(s);q['points']=retarget_path(s['points'],*targets);changed[i]=q
    lnames={l['name'] for l in p['pdk']['layers']}
    for s in changed.values():validate_shape(s,lnames)
    shapes=list(c['shapes'])
    for i,s in changed.items():shapes[i]=s
    cell={**candidate,'shapes':shapes};cells=list(p['cells']);cells[cells.index(c)]=cell;nxt={**p,'cells':cells}
    if owned:validate(nxt)
    prior=copy(graph) if graph is not None else GeometryGraph()
    if getattr(prior,'project',None) is not p:prior.sync(c['shapes'],p['pdk'])
    after=copy(prior);after.sync(shapes,p['pdk'],trusted=True);after.project=nxt
    a=prior.partition(p,cid);b=after.partition(nxt,cid)
    # Compare each component once. Repeated members of a large net must not
    # turn the preservation check into a quadratic operation.
    if a.keys()!=b.keys() or set(a.values())!=set(b.values()):
        raise ValueError('This edit would join or separate existing conductors or terminals. Adjust the route or selection.')
    rules={l['name']:l['space'] for l in p['pdk']['layers']}
    for shape in changed.values():
        ident=key(shape)
        if ident not in after.records:continue
        record=after.records[ident];space=rules[shape['layer']];box=record['box'];obstacles=db.Region()
        for other in after.query((box[0]-space,box[1]-space,box[2]+space,box[3]+space)):
            row=after.records[other]
            if row['shape']['layer']==shape['layer'] and after.groups[other]!=after.groups[ident]:obstacles.insert(row['poly'])
        if not obstacles.is_empty() and not (record['region'] & obstacles.merged().sized(space)).is_empty():raise ValueError('The connected edit violates declared spacing. Reserve room for the adjusted leads.')
    from .route_constraints import enforce
    enforce(p,nxt,cid)
    return nxt,after,changed
