"""Connection-preserving local layout edits, checked against polygon topology."""
from .model import clone, uid, validate
from .layout import kdb, polygon
from .design_ops import flatten_layout
from .physical_cells import terminals, ports, transform_selection
from .spatial import SpatialIndex
from .wiring import retarget_path, segment_drag, on_segment


def shape_key(s):
    return ('shape', s['id'], s.get('source_id', ''), s.get('instance_path', ''))


def partition(p, cid):
    """Stable identities in physical components; labels never create contact."""
    c=next(c for c in p['cells'] if c['id']==cid)
    if not c.get('layout_instances'):
        from .layout_graph import GeometryGraph
        graph=GeometryGraph();graph.sync(c['shapes'],p['pdk']);return graph.partition(p,cid)
    db = kdb(); cfg = p['pdk'].get('connectivity', {})
    vias = cfg.get('vias', [['metal1', 'via1', 'metal2']])
    allowed = {(a, b) for lower, cut, upper in vias
               for a, b in ((lower, cut), (cut, lower), (cut, upper), (upper, cut))}
    layers = set(cfg.get('conductors', ['metal1', 'metal2'])) | {v for _, v, _ in vias}
    shapes = [s for s in flatten_layout(p, cid) if s['layer'] in layers]
    if len(shapes) > 20000: raise ValueError('Connected editing supports at most 20,000 conducting shapes.')
    polys = [polygon(s) for s in shapes]; regions = [db.Region(v) for v in polys]
    keys = [shape_key(s) for s in shapes]; parents = list(range(len(keys)))
    def find(i):
        while parents[i] != i: parents[i] = parents[parents[i]]; i = parents[i]
        return i
    def union(i, j): parents[find(i)] = find(j)
    index = SpatialIndex([((b.left,b.bottom,b.right,b.top),i) for i,poly in enumerate(polys) for b in [poly.bbox()]])
    for i, poly in enumerate(polys):
        box = poly.bbox()
        for j in index.query((box.left,box.bottom,box.right,box.top)):
            a,b = shapes[i]['layer'],shapes[j]['layer']
            if j > i and (a == b or (a,b) in allowed) and not regions[i].interacting(regions[j]).is_empty(): union(i,j)
    anchors = [(('pin',v['id']),v) for v in terminals(p,cid)]
    anchors += [(('port',v['name']),v) for v in ports(p,cid)]
    for key, v in anchors:
        i = len(keys); keys.append(key); parents.append(i); x,y = v['point']
        for j in index.query((x,y,x,y)):
            if shapes[j]['layer'] == v['layer'] and polys[j].inside(db.Point(x,y)): union(i,j)
    groups = {}
    for i,key in enumerate(keys): groups.setdefault(find(i),set()).add(key)
    return {key:frozenset(group) for group in groups.values() for key in group}


def require_preserved(before, after, cid):
    graph=None
    if not _cell(before,cid).get('layout_instances') and not _cell(after,cid).get('layout_instances'):
        from .layout_graph import GeometryGraph
        graph=GeometryGraph().sync(_cell(before,cid)['shapes'],before['pdk'])
        a=graph.partition(before,cid)
        graph.sync(_cell(after,cid)['shapes'],after['pdk'])
        b=graph.partition(after,cid)
    else:a=partition(before,cid);b=partition(after,cid)
    universe = set(a)
    if not universe <= set(b): raise ValueError('Connected edit removed a physical identity.')
    old=set(a.values());new={group & universe for group in set(b.values())};new.discard(frozenset())
    if old!=new:raise ValueError('This edit would join or separate existing conductors or terminals. Adjust the route or selection.')
    return graph


def _cell(p,cid): return next(c for c in p['cells'] if c['id']==cid)


def _check_clearance(before, after, cid, graph=None):
    """Check edited conductors against other physical components, including unnamed metal."""
    c=_cell(after,cid)
    if not c.get('layout_instances'):
        from .layout_graph import GeometryGraph,key
        prior={s['id']:s for s in _cell(before,cid)['shapes']};db=kdb()
        if graph is None:graph=GeometryGraph().sync(c['shapes'],after['pdk'])
        spacing={l['name']:l['space'] for l in after['pdk']['layers']}
        for s in c['shapes']:
            ident=key(s)
            if s==prior.get(s['id']) or ident not in graph.records:continue
            row=graph.records[ident];space=spacing[s['layer']];box=row['box'];obstacles=db.Region()
            for other in graph.query((box[0]-space,box[1]-space,box[2]+space,box[3]+space)):
                target=graph.records[other]
                if target['shape']['layer']==s['layer'] and graph.groups[other]!=graph.groups[ident]:obstacles.insert(target['poly'])
            if not obstacles.is_empty() and not (row['region'] & obstacles.merged().sized(space)).is_empty():raise ValueError('The connected edit violates declared spacing. Reserve room for the adjusted leads.')
        return
    from .layout_routing import Geometry
    prior = {shape_key(s):s for s in flatten_layout(before,cid)}; groups = partition(after,cid)
    cache={}
    for s in flatten_layout(after,cid):
        key = shape_key(s)
        if key not in groups or s == prior.get(key): continue
        same = frozenset(v for v in groups[key] if v[0]=='shape')
        if same not in cache:cache[same]=Geometry(after,cid,None,ignored_keys=same)
        if not cache[same].clear(s):
            raise ValueError('The connected edit violates declared spacing. Reserve room for the adjusted leads.')


def move(p, cid, ids, dx=0, dy=0, locked=()):
    """Translate complete footprints and retarget local Manhattan wire endpoints."""
    from .layout_edit import selection_groups
    selection_groups(p,cid,ids,locked); chosen = set(ids); q = clone(p)
    old = _cell(p,cid); c = _cell(q,cid); db = kdb()
    for s in old['shapes']:
        if s['id'] not in chosen: continue
        for group_key in ('pcell_id','via_group','generated_device'):
            if s.get(group_key) and any(t.get(group_key)==s[group_key] and t['id'] not in chosen for t in old['shapes']):
                raise ValueError('Select the complete device footprint or via stack for a connected move.')
    transform_selection(q,cid,ids,dx,dy)
    # Process footprints are handled by transform_selection. Parametric footprints
    # use a separate ownership field and need their explicit terminals translated.
    process_ids = {r['device_id'] for r in old.get('pdk_layouts',[])}
    for r in old.get('parametric_devices',[]):
        footprint = [s for s in old['shapes'] if s.get('pcell_id')==r['id']]
        if footprint and all(s['id'] in chosen for s in footprint) and r.get('device_id') not in process_ids:
            for pin in c.get('layout_pins',[]):
                if r.get('device_id') and pin['device_id']==r['device_id']:
                    pin['point'] = [pin['point'][0]+dx,pin['point'][1]+dy]
    from .layout_index import LayoutBoxIndex
    routes=any(s['id'] not in chosen and s['kind']=='path' for s in c['shapes'])
    moving = [(s['layer'],polygon(s)) for s in (flatten_layout(p,cid) if old.get('layout_instances') else old['shapes']) if s['id'] in chosen] if routes else []
    index=LayoutBoxIndex([(b.left,b.bottom,b.right,b.top) for _,poly in moving for b in [poly.bbox()]]) if moving else None
    for s in c['shapes']:
        if s['id'] in chosen or s['kind']!='path': continue
        if any(a==b or a[0]!=b[0] and a[1]!=b[1] for a,b in zip(s['points'],s['points'][1:])): continue
        targets = []
        for pt in (s['points'][0],s['points'][-1]):
            nearby=(moving[j] for j in index.query((*pt,*pt))) if index is not None else ()
            attached = any(layer==s['layer'] and poly.inside(db.Point(*pt)) for layer,poly in nearby)
            targets.append([pt[0]+dx,pt[1]+dy] if attached else None)
        if any(v is not None for v in targets):
            if s['layer'] in locked: raise ValueError('Unlock attached route layers before moving the footprint.')
            s['points'] = retarget_path(s['points'],*targets)
    validate(q); graph=require_preserved(p,q,cid); _check_clearance(p,q,cid,graph)
    from .route_constraints import enforce
    enforce(p,q,cid)
    old.update(c); return p


def stretch(p, cid, sid, segment, offset, locked=()):
    """Slide a path segment while retaining endpoint and branch anchors."""
    q = clone(p); c = _cell(q,cid); s = next((s for s in c['shapes'] if s['id']==sid),None)
    if not s or s['kind']!='path': raise ValueError('Select one local Manhattan path.')
    if s['layer'] in locked: raise ValueError('Unlock the path layer before stretching.')
    if type(offset) is not int or offset % p['pdk']['grid']: raise ValueError('Stretch distance must be on the project grid.')
    pts = s['points']
    if type(segment) is not int or not 0<=segment<len(pts)-1: raise ValueError('Choose an existing segment.')
    if any(a==b or a[0]!=b[0] and a[1]!=b[1] for a,b in zip(pts,pts[1:])): raise ValueError('Connected stretch requires a Manhattan path.')
    a,b = pts[segment:segment+2]; axis = 1 if a[1]==b[1] else 0
    fixed = {tuple(v['point']) for v in terminals(p,cid)+ports(p,cid) if v['layer']==s['layer']}
    fixed.update(tuple(pt) for t in c['shapes'] if t['id']!=sid and t['layer']==s['layer'] and t['kind']=='path' and t.get('connected_lead')!=sid for pt in (t['points'][0],t['points'][-1]))
    s['points'] = segment_drag(pts,segment,offset if axis==0 else 0,offset if axis==1 else 0)
    if len(s['points'])<2: raise ValueError('The stretch collapses the path.')
    if offset:
        for lead in c['shapes']:
            if lead.get('connected_lead')==sid and on_segment(lead['points'][-1],a,b):
                target=list(lead['points'][-1]);target[axis]+=offset
                lead['points']=retarget_path(lead['points'],end=target)
                if len(lead['points'])<2:raise ValueError('The stretch collapses an attached branch lead. Undo its creation to return to the original route.')
        for pt in sorted(fixed):
            if list(pt) in (pts[0],pts[-1]) or not on_segment(pt,a,b): continue
            target = list(pt); target[axis] += offset
            c['shapes'].append({'id':uid(),'kind':'path','layer':s['layer'],'width':s['width'],
                                'points':[list(pt),target],'net':s.get('net',''),'device_id':'','connected_lead':sid})
    validate(q); graph=require_preserved(p,q,cid); _check_clearance(p,q,cid,graph)
    from .route_constraints import enforce
    enforce(p,q,cid)
    _cell(p,cid).update(c); return s
