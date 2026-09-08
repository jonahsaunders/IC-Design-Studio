"""Transactional layout operations. Coordinates and offsets are integer nanometres."""
from .model import uid, validate
from .layout import rect, polygon, kdb
from .physical_cells import transform_selection, transform


def via_options(tech):
    from .process_adapters import adapter
    process = adapter(tech); ls = process.layers(tech)
    if process.id == 'sky130A':
        return {'M1 to M2': (ls['m1'], ls['via'], ls['m2'], 150, 340),
                'Local interconnect to M1': (ls['li'], ls['mcon'], ls['m1'], 170, 340)}
    if process.id == 'gf180mcuC': return {'M1 to M2': (ls['m1'], ls['via'], ls['m2'], 260, 440)}
    raise ValueError('This process has no native via recipe.')


def place_via(p, cid, connection, point, net='', locked=()):
    from .model import NET
    from .process_adapters import adapter
    if len(point)!=2 or any(type(v) is not int or v%p['pdk']['grid'] for v in point): raise ValueError('Place a via on the project grid.')
    if net and not NET.fullmatch(net): raise ValueError('Use a valid net name or leave it blank.')
    options=via_options(p['pdk'])
    if connection not in options: raise ValueError('Choose a supported conductor connection.')
    a,cut,b,size,pad=options[connection]
    if {a,cut,b}&set(locked): raise ValueError('Unlock all three via-stack layers before placement.')
    process=adapter(p['pdk']);process.engine_assets(p['pdk'])
    if process.id=='gf180mcuC':process.implementation().prepare(p['pdk'])
    c=next(c for c in p['cells'] if c['id']==cid);group=uid();out=[]
    for layer,width in ((a,pad),(cut,size),(b,pad)):
        s=rect(layer,point[0]-width//2,point[1]-width//2,width,width,net=net if layer!=cut else '')
        s['via_group']=group;out.append(s)
    c['shapes'].extend(out);validate(p);return [s['id'] for s in out]


def stretch_path(p, cid, sid, segment, offset, locked=()):
    c=next(c for c in p['cells'] if c['id']==cid);s=next((s for s in c['shapes'] if s['id']==sid),None)
    if not s or s['kind']!='path':raise ValueError('Select one path in the active cell.')
    if s['layer'] in locked:raise ValueError('Unlock the path layer before stretching it.')
    if type(offset) is not int or offset%p['pdk']['grid']:raise ValueError('Stretch distance must be on the project grid.')
    pts=[list(pt) for pt in s['points']]
    if type(segment) is not int or not 0<=segment<len(pts)-1:raise ValueError('Choose an existing path segment.')
    if any(a==b or (a[0]!=b[0] and a[1]!=b[1]) for a,b in zip(pts,pts[1:])):raise ValueError('Stretch requires a Manhattan path with distinct vertices.')
    a,b=pts[segment:segment+2];axis=1 if a[1]==b[1] else 0
    for pt in (a,b):pt[axis]+=offset
    if any(a==b or (a[0]!=b[0] and a[1]!=b[1]) for a,b in zip(pts,pts[1:])):raise ValueError('This stretch collapses a segment or creates a diagonal. Use a smaller distance or edit the vertices.')
    s['points']=pts;validate(p);return s


def selection_groups(p, cid, ids, locked=()):
    c=next(c for c in p['cells'] if c['id']==cid);chosen=set(ids)
    objects={s['id']:s for s in c['shapes']};instances={i['id']:i for i in c.get('layout_instances',[])}
    if not chosen or not chosen<=objects.keys()|instances.keys():raise ValueError('Select local shapes or cell instances.')
    if any(objects[i]['layer'] in locked for i in chosen if i in objects):raise ValueError('Unlock selected layers before aligning.')
    if locked and chosen&instances.keys():
        from .design_ops import flatten_layout
        if any(s['layer'] in locked for s in flatten_layout(p,cid) if s['id'] in chosen&instances.keys()):raise ValueError('Unlock every affected layer in the selected physical cells.')
    groups=[];done=set()
    for oid in ids:
        if oid in done:continue
        s=objects.get(oid,{});key='generated_device' if s.get('generated_device') else 'via_group'
        linked={x['id'] for x in c['shapes'] if s.get(key) and x.get(key)==s[key]}
        if linked and not linked<=chosen:raise ValueError('Select the complete device footprint or via stack before aligning it.')
        group=linked or {oid};done|=group;groups.append(group)
    return groups


def align(p, cid, ids, edge, locked=()):
    groups=selection_groups(p,cid,ids,locked)
    if len(groups)<2:raise ValueError('Select at least two independent shapes, complete devices, via stacks or instances.')
    if edge not in ('left','right','top','bottom','center_x','center_y'):raise ValueError('Choose an alignment edge or axis.')
    c=next(c for c in p['cells'] if c['id']==cid)
    def bounds(group):
        region=kdb().Region()
        for s in c['shapes']:
            if s['id'] in group:region.insert(polygon(s))
        from .design_ops import flatten_layout
        for i in c.get('layout_instances',[]):
            if i['id'] in group:
                for s in flatten_layout(p,i['cell']):region.insert(polygon(s).transformed(transform(i)))
        if region.is_empty():raise ValueError('Selected instance has no physical geometry.')
        return region.bbox()
    boxes=[bounds(group) for group in groups]
    coordinate=lambda b:{'left':b.left,'right':b.right,'bottom':b.bottom,'top':b.top,
                          'center_x':(b.left+b.right)/2,'center_y':(b.bottom+b.top)/2}[edge]
    # Selection order defines an explicit fixed reference; never move that reference.
    target=coordinate(boxes[0]);moves=[]
    for group,box in zip(groups[1:],boxes[1:]):
        delta=target-coordinate(box)
        if delta!=int(delta) or int(delta)%p['pdk']['grid']:raise ValueError('Exact alignment would leave the layout grid. Align an edge or adjust dimensions first.')
        moves.append((group,int(delta)))
    for group,delta in moves:
        transform_selection(p,cid,group,dx=delta if edge in ('left','right','center_x') else 0,
                            dy=delta if edge in ('bottom','top','center_y') else 0)
    validate(p)
