"""Bounded multilayer Manhattan routing with declared via geometry.

Plans are immutable proposals. Installation checks the exact source revision;
all lengths are geometric, not extracted delay or resistance guarantees.
"""
import heapq
import math
from .model import clone, digest, design_digest, uid, validate, NET
from .layout import kdb, polygon, rect
from .design_ops import flatten_layout
from .wiring import clean


class RoutingCancelled(ValueError):
    pass


def via_recipes(tech):
    declared = tech.get('routing_vias')
    if declared is None:
        from .layout_edit import via_options
        try:
            declared = [dict(name=n, lower=a, cut=cut, upper=b, size=size,
                             enclosure=(pad-size)//2)
                        for n, (a, cut, b, size, pad) in via_options(tech).items()]
        except ValueError:
            from .parametric import rules
            try:
                cfg = rules(tech).get('contact', {})
                declared = [dict(name='Declared contact', **cfg)] if cfg else []
            except ValueError:
                declared = []
    layers = {l['name']: l for l in tech['layers']}; grid = tech['grid']; out = []
    for item in declared:
        v = clone(item)
        if any(v.get(k) not in layers for k in ('lower', 'cut', 'upper')):
            raise ValueError('A routing via references an unmapped layer.')
        if len({v['lower'], v['cut'], v['upper']}) != 3:
            raise ValueError('A routing via needs distinct lower, cut and upper layers.')
        if any(type(v.get(k)) is not int for k in ('size', 'enclosure')):
            raise ValueError('Via size and enclosure must be integer nanometres.')
        if v['size'] <= 0 or v['enclosure'] < 0 or v['size'] % (2*grid) or v['enclosure'] % grid:
            raise ValueError('Via dimensions must allow a centered, on-grid stack.')
        v['pad'] = v['size'] + 2*v['enclosure']
        if v['size'] < layers[v['cut']]['width'] or any(v['pad'] < layers[v[k]]['width'] for k in ('lower', 'upper')):
            raise ValueError('Via recipe is smaller than declared layer minimum widths.')
        v.setdefault('name', v['lower']+' to '+v['upper']); out.append(v)
    return out


def conductors(tech):
    via = via_recipes(tech)
    return list(dict.fromkeys(tech.get('connectivity', {}).get('conductors', [])
                             or [v[k] for v in via for k in ('lower', 'upper')]
                             or [l['name'] for l in tech['layers'] if l['name'].startswith('metal')]))


def via_shapes(recipe, point, net, group=None):
    group = group or uid(); result = []
    for layer, size in ((recipe['lower'], recipe['pad']), (recipe['cut'], recipe['size']),
                        (recipe['upper'], recipe['pad'])):
        s = rect(layer, point[0]-size//2, point[1]-size//2, size, size, net=net)
        s['via_group'] = group; result.append(s)
    return result


class Geometry:
    def __init__(self, p, cid, net, ignored=(), ignored_keys=()):
        self.db = kdb(); self.rules = {l['name']: l for l in p['pdk']['layers']}
        self.regions = {}; self.shapes = []
        for s in flatten_layout(p, cid):
            key=('shape',s['id'],s.get('source_id',''),s.get('instance_path',''))
            if s['id'] in ignored or key in ignored_keys or net is not None and s.get('net') == net: continue
            self.regions.setdefault(s['layer'], self.db.Region()).insert(polygon(s)); self.shapes.append(s)
        self.blocked = {name: r.merged().sized(self.rules[name]['space']) for name, r in self.regions.items()}

    def clear(self, shape):
        blocked = self.blocked.get(shape['layer'])
        return blocked is None or (self.db.Region(polygon(shape)) & blocked).is_empty()


def length(shapes):
    return sum(abs(a[0]-b[0])+abs(a[1]-b[1]) for s in shapes if s['kind']=='path'
               for a, b in zip(s['points'], s['points'][1:]))


def plan(p, cid, start, end, net, width, layers=None, via_cost=2000, margin=5000,
         max_nodes=50000, locked=(), cancelled=lambda: False):
    """Search an obstacle-derived grid, including layer transitions with full pads."""
    grid = p['pdk']['grid']; rules = {l['name']: l for l in p['pdk']['layers']}
    layers = list(dict.fromkeys(layers or conductors(p['pdk'])))
    if not layers or any(l not in conductors(p['pdk']) for l in layers):
        raise ValueError('Select declared conductor layers for routing.')
    if set(layers) & set(locked): raise ValueError('Unlock every selected routing layer.')
    cfg=p['pdk'].get('connectivity',{})
    if not set(layers)<=set(cfg.get('conductors',['metal1','metal2'])):
        raise ValueError('Declare connectivity mappings for each routing layer in the technology first.')
    if not isinstance(net, str) or not NET.fullmatch(net): raise ValueError('Enter a valid route net.')
    if type(width) is not int or width % (2*grid) or width < max(rules[l]['width'] for l in layers):
        raise ValueError('Route width must meet each layer minimum and be a multiple of twice the grid.')
    for endpoint in (start, end):
        if endpoint.get('layer') not in layers or len(endpoint.get('point', [])) != 2:
            raise ValueError('Each endpoint needs a selected layer and X/Y coordinates.')
        if any(type(v) is not int or v % grid or abs(v)>100000000 for v in endpoint['point']):
            raise ValueError('Route endpoints must be on-grid within ±100 mm.')
    if start == end: raise ValueError('Route endpoints must differ.')
    if type(margin) is not int or margin <= 0 or margin % grid or margin>1000000:
        raise ValueError('Routing margin must be on-grid, positive and at most 1 mm.')
    if type(via_cost) is not int or via_cost <= 0: raise ValueError('Via cost must be positive.')
    if type(max_nodes) is not int or not 1 <= max_nodes <= 200000:
        raise ValueError('Routing search supports 1–200,000 grid nodes.')
    recipes = [v for v in via_recipes(p['pdk']) if v['lower'] in layers and v['upper'] in layers
               and not {v['lower'], v['cut'], v['upper']} & set(locked)]
    known_vias={tuple(v) for v in cfg.get('vias',[['metal1','via1','metal2']])}
    if any((v['lower'],v['cut'],v['upper']) not in known_vias and (v['upper'],v['cut'],v['lower']) not in known_vias for v in recipes):
        raise ValueError('Declare physical connectivity for every routing via recipe first.')
    geometry = Geometry(p, cid, net); db = kdb()
    sx, sy = start['point']; ex, ey = end['point']
    bounds = [min(sx, ex)-margin, min(sy, ey)-margin, max(sx, ex)+margin, max(sy, ey)+margin]
    if any(abs(v)>100000000 for v in bounds): raise ValueError('Routing search exceeds ±100 mm.')
    xs = {sx, ex, bounds[0], bounds[2]}; ys = {sy, ey, bounds[1], bounds[3]}
    pad = max([width]+[v['pad'] for v in recipes])
    for s in geometry.shapes:
        if cancelled(): raise RoutingCancelled('Routing cancelled.')
        b = polygon(s).bbox(); space = rules[s['layer']]['space'] + pad//2 + grid
        if b.right < bounds[0]-space or b.left > bounds[2]+space or b.top < bounds[1]-space or b.bottom > bounds[3]+space: continue
        xs.update(v for v in (grid*math.floor((b.left-space)/grid), grid*math.ceil((b.right+space)/grid)) if bounds[0]<=v<=bounds[2])
        ys.update(v for v in (grid*math.floor((b.bottom-space)/grid), grid*math.ceil((b.top+space)/grid)) if bounds[1]<=v<=bounds[3])
    xs = sorted(xs); ys = sorted(ys)
    if len(xs)*len(ys)*len(layers)>max_nodes:
        raise ValueError('Routing region exceeds the search budget. Use a waypoint or a smaller margin.')
    first = (start['layer'], xs.index(sx), ys.index(sy)); target = (end['layer'], xs.index(ex), ys.index(ey))
    def heuristic(n): return abs(xs[n[1]]-ex)+abs(ys[n[2]]-ey)
    queue = [(heuristic(first), 0, first)]; costs = {first: 0}; previous = {}; checked = {}; via_cache = {}; visited = 0
    def edge_clear(a, b):
        key = tuple(sorted((a, b)))
        if key not in checked:
            checked[key] = geometry.clear({'kind':'path','layer':a[0],'width':width,
                                           'points':[[xs[a[1]], ys[a[2]]], [xs[b[1]], ys[b[2]]]]})
        return checked[key]
    while queue:
        if cancelled(): raise RoutingCancelled('Routing cancelled.')
        _, cost, n = heapq.heappop(queue)
        if cost != costs[n]: continue
        visited += 1
        if n == target: break
        layer, x, y = n; candidates = []
        for xx, yy in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0<=xx<len(xs) and 0<=yy<len(ys):
                nxt = (layer, xx, yy)
                if edge_clear(n, nxt): candidates.append((nxt, abs(xs[x]-xs[xx])+abs(ys[y]-ys[yy]), None))
        for vi, v in enumerate(recipes):
            if layer not in (v['lower'], v['upper']): continue
            key = (vi, x, y)
            if key not in via_cache: via_cache[key] = all(geometry.clear(s) for s in via_shapes(v, [xs[x],ys[y]], net))
            if via_cache[key]: candidates.append(((v['upper'] if layer==v['lower'] else v['lower'], x, y), via_cost, vi))
        for nxt, distance, vi in candidates:
            new = cost + distance
            if new < costs.get(nxt, math.inf):
                costs[nxt] = new; previous[nxt] = (n, vi); heapq.heappush(queue, (new+heuristic(nxt),new,nxt))
    else: raise ValueError('No clear route within this region and declared via rules. Add a waypoint or increase the margin.')
    steps = []; n = target
    while n != first:
        prev, vi = previous[n]; steps.append((prev,n,vi)); n = prev
    steps.reverse(); shapes = []; points = [start['point']]; layer = start['layer']; vias = 0
    def emit():
        pts = clean(points)
        if len(pts)>1: shapes.append({'id':uid(),'kind':'path','layer':layer,'points':pts,'width':width,'net':net,'device_id':''})
    for a,b,vi in steps:
        if vi is None: points.append([xs[b[1]],ys[b[2]]])
        else:
            emit(); shapes.extend(via_shapes(recipes[vi], [xs[a[1]],ys[a[2]]], net)); vias += 1
            layer = b[0]; points = [[xs[b[1]],ys[b[2]]]]
    emit()
    if vias and p['pdk'].get('package_lock'):
        from .process_adapters import adapter
        process=adapter(p['pdk']);process.engine_assets(p['pdk'])
        if process.id=='gf180mcuC':process.implementation().prepare(clone(p['pdk']))
    group = uid()
    for s in shapes: s.update(route_group=group, generated_route=True)
    return {'version':1,'project_id':p['id'],'cell_id':cid,'design_hash':design_digest(p),
            'shapes':shapes,'route_group':group,'net':net,'length_nm':length(shapes),'via_count':vias,
            'visited_nodes':visited,'start':clone(start),'end':clone(end),'width':width,'layers':layers,
            'qualification':'Declared width, spacing and via geometry only; run process verification and extraction.'}


def install(p, proposal, locked=()):
    if proposal['project_id']!=p['id'] or proposal['design_hash']!=design_digest(p):
        raise ValueError('The design changed after routing. Plan the route again.')
    if any(s['layer'] in locked for s in proposal['shapes']): raise ValueError('Unlock every route and via layer.')
    q=clone(p); c=next(c for c in q['cells'] if c['id']==proposal['cell_id'])
    c['shapes'].extend(clone(proposal['shapes']))
    c.setdefault('routing_records',[]).append({k:clone(v) for k,v in proposal.items() if k!='shapes'} | {'shape_ids':[s['id'] for s in proposal['shapes']]})
    validate(q)
    target=next(c for c in p['cells'] if c['id']==proposal['cell_id']); target.update(c)
    return [s['id'] for s in proposal['shapes']]


def matched_pair(p, cid, starts, ends, nets, width, tolerance=0, **options):
    if len(starts)!=2 or len(ends)!=2 or len(nets)!=2 or nets[0]==nets[1]:
        raise ValueError('A matched pair needs two distinct nets and two endpoint pairs.')
    if type(tolerance) is not int or tolerance<0: raise ValueError('Length tolerance must be non-negative nanometres.')
    a=plan(p,cid,starts[0],ends[0],nets[0],width,**options); q=clone(p)
    next(c for c in q['cells'] if c['id']==cid)['shapes'].extend(clone(a['shapes']))
    b=plan(q,cid,starts[1],ends[1],nets[1],width,**options)
    shorter,longer=sorted((a,b),key=lambda r:r['length_nm']); delta=longer['length_nm']-shorter['length_nm']
    if delta>tolerance:
        grid=p['pdk']['grid']
        if delta%(2*grid): raise ValueError('Exact length matching is not possible on this grid. Adjust endpoints or tolerance.')
        if delta//2 < width:
            raise ValueError('The tuning offset is narrower than the route. Increase tolerance or change endpoints.')
        q=clone(p);next(c for c in q['cells'] if c['id']==cid)['shapes'].extend(clone(longer['shapes']))
        geometry=Geometry(q,cid,shorter['net']); found=False
        for s in shorter['shapes']:
            if s['kind']!='path':continue
            # Bounded tuning of a single straight route avoids self-intersections
            # and hidden electrical shortcuts through another part of that route.
            if len(s['points'])!=2 or sum(t['kind']=='path' for t in shorter['shapes'])!=1:continue
            u,v=s['points'];axis=1 if u[1]==v[1] else 0
            for sign in (-1,1):
                aa=list(u);bb=list(v);aa[axis]+=sign*delta//2;bb[axis]+=sign*delta//2
                candidate={**s,'points':[u,aa,bb,v]}
                if geometry.clear(candidate):s['points']=candidate['points'];found=True;break
            if found:break
        if not found:raise ValueError('No clear tuning corridor for this pair. Move endpoints or reserve more space.')
        shorter['length_nm']=length(shorter['shapes'])
    shapes=a['shapes']+b['shapes']; group=uid()
    for s in shapes:s['route_group']=group
    return {'version':1,'project_id':p['id'],'cell_id':cid,'design_hash':design_digest(p),'shapes':shapes,
            'route_group':group,'kind':'matched_pair','nets':nets,'lengths_nm':[a['length_nm'],b['length_nm']],
            'skew_nm':abs(a['length_nm']-b['length_nm']),'tolerance_nm':tolerance,
            'via_count':a['via_count']+b['via_count'],'qualification':'Matched geometric length only; parasitic and electrical matching require extraction.'}


def shield(p, cid, sid, ground, net='0', width=400, gap=500, **options):
    """Generate two shields for a straight local path and route their ground ties."""
    c=next(c for c in p['cells'] if c['id']==cid); s=next((s for s in c['shapes'] if s['id']==sid),None)
    if not s or s['kind']!='path' or len(s['points'])!=2:raise ValueError('Select a straight two-point signal path for shielding.')
    if not s.get('net') or s['net']==net:raise ValueError('Signal and shield must have distinct named nets.')
    if not any(t['layer']==ground.get('layer') and t.get('net')==net and
               len(ground.get('point',[]))==2 and polygon(t).inside(kdb().Point(*ground['point']))
               for t in flatten_layout(p,cid)):
        raise ValueError('Choose a ground tie point on an existing conductor labeled with the reference net.')
    grid=p['pdk']['grid'];rules={l['name']:l for l in p['pdk']['layers']}
    if type(gap) is not int or gap<rules[s['layer']]['space'] or gap%grid:raise ValueError('Shield gap must meet spacing and grid rules.')
    if type(width) is not int or width<rules[s['layer']]['width'] or width%(2*grid):raise ValueError('Use an on-grid shield width above the layer minimum.')
    a,b=s['points'];axis=1 if a[1]==b[1] else 0
    if a==b or a[0]!=b[0] and a[1]!=b[1]:raise ValueError('Shielding needs a straight Manhattan path.')
    offset=math.ceil(((s['width']+width)/2+gap)/grid)*grid; q=clone(p); all_shapes=[]
    for sign in (-1,1):
        u=list(a);v=list(b);u[axis]+=sign*offset;v[axis]+=sign*offset
        shape={'id':uid(),'kind':'path','layer':s['layer'],'width':width,'points':[u,v],'net':net,'device_id':'','shield_for':sid}
        if not Geometry(q,cid,net).clear(shape):raise ValueError('A shield would violate declared spacing. Reserve a clear corridor.')
        next(c for c in q['cells'] if c['id']==cid)['shapes'].append(shape);all_shapes.append(shape)
        tie=plan(q,cid,{'layer':s['layer'],'point':u},ground,net,width,**options)
        next(c for c in q['cells'] if c['id']==cid)['shapes'].extend(tie['shapes']);all_shapes+=tie['shapes']
    group=uid()
    for shape in all_shapes:shape.update(route_group=group,generated_route=True)
    return {'version':1,'project_id':p['id'],'cell_id':cid,'design_hash':design_digest(p),'shapes':all_shapes,
            'route_group':group,'kind':'shield','net':net,'signal_id':sid,'gap_nm':gap,'ground':clone(ground),
            'length_nm':length(all_shapes),'qualification':'Two geometric shields with routed ties to the chosen point. Verify that point is on the intended reference net.'}
