"""Transactional layout operations. Coordinates and offsets are integer nanometres."""
from .model import uid, validate
from .layout import rect, polygon, kdb
from .physical_cells import transform_selection, transform


def via_options(tech):
    from .layout_routing import via_recipes
    if 'pdk' in tech:
        from .layout_vias import technology
        tech=technology(tech)
    return {v['name']: (v['lower'], v['cut'], v['upper'], v['size'], v['pad'])
            for v in via_recipes(tech)}


def _native_via_recipes(tech, process=None):
    # A via needs only its three mapped masks, not a complete MOS generator or
    # installed extraction engines. Physical verification still checks its decks.
    process = process or tech.get('package_lock', {}).get('id')
    by = {(l['gds'], l['datatype']): l['name'] for l in tech['layers']}
    definitions = {
        # SKY130 periphery via.2 / ct.2; GF180 via spacing also used by
        # gf180_layout.prepare. See docs/LAYOUT_VIAS.md for rule sources.
        'sky130A': [('M1 to M2', (68,20), (68,44), (69,20), 150, 340, 170),
                   ('Local interconnect to M1', (67,20), (67,44), (68,20), 170, 340, 190)],
        'gf180mcuC': [('M1 to M2', (34,0), (35,0), (36,0), 260, 440, 260)],
    }
    return [dict(name=name,lower=by[a],cut=by[cut],upper=by[b],size=size,
                 enclosure=(pad-size)//2,spacing=space)
            for name,a,cut,b,size,pad,space in definitions.get(process, [])
            if all(layer in by for layer in (a,cut,b))]


def place_via(p, cid, connection, point, net='', locked=()):
    from .model import NET
    from .layout_vias import declare_connections, technology
    from .model import clone
    if len(point)!=2 or any(type(v) is not int or v%p['pdk']['grid'] for v in point): raise ValueError('Place a via on the project grid.')
    if net and not NET.fullmatch(net): raise ValueError('Use a valid net name or leave it blank.')
    options=via_options(p)
    if connection not in options: raise ValueError('Choose a supported conductor connection.')
    a,cut,b,size,pad=options[connection]
    if {a,cut,b}&set(locked): raise ValueError('Unlock all three via-stack layers before placement.')
    c=next(c for c in p['cells'] if c['id']==cid);group=uid();out=[]
    for layer,width in ((a,pad),(cut,size),(b,pad)):
        s=rect(layer,point[0]-width//2,point[1]-width//2,width,width,net=net if layer!=cut else '')
        s['via_group']=group;out.append(s)
    q=clone(p);q['pdk']=clone(technology(q));target=next(c for c in q['cells'] if c['id']==cid)
    target['shapes'].extend(out);declare_connections(q['pdk']);validate(q)
    c['shapes'].extend(out);p['pdk']=q['pdk'];return [s['id'] for s in out]


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


# Kept here for compatibility with scripts and earlier source snapshots.
from .layout_arrange import selection_groups, arrange as align
