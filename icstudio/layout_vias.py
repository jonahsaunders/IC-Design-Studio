"""Bounded via arrays in selected conductor overlaps, in integer nanometres."""
import math
from .model import clone, design_digest, uid, validate
from .layout import kdb, polygon
from .layout_routing import via_recipes, via_shapes


def technology(project):
    """Recover mapped via definitions for older attached native imports.

    The saved library variant identifies the family; GDS pairs identify the
    actual layers. Never infer a process from layer numbers alone or manufacture
    a physical package lock from a simulation dependency.
    """
    tech=project['pdk']
    if 'routing_vias' in tech or tech.get('package_lock'):
        return tech
    if not (project.get('layout_attachment') or project.get('layout_source')):
        return tech
    variant=project.get('spice',{}).get('library_lock',{}).get('variant')
    if variant not in ('sky130A','gf180mcuC'):
        return tech
    from .layout_edit import _native_via_recipes
    recipes=_native_via_recipes(tech,variant)
    if not recipes:return tech
    return {**tech,'routing_vias':recipes,
            'via_source':dict(process=variant,source='Imported project library variant and mapped GDS layers',
                              scope='Via geometry only; no physical PDK qualification inferred.')}


def declare_connections(tech):
    """Retain existing topology and register the explicitly mapped via stacks."""
    cfg = tech.setdefault('connectivity', {})
    names={l['name'] for l in tech['layers']}
    conductors = cfg.setdefault('conductors', [n for n in ('metal1','metal2') if n in names])
    vias = cfg.setdefault('vias', [['metal1','via1','metal2']] if {'metal1','via1','metal2'}<=names else [])
    for recipe in via_recipes(tech):
        a, cut, b = (recipe[k] for k in ('lower', 'cut', 'upper'))
        for layer in (a, b):
            if layer not in conductors: conductors.append(layer)
        if [a, cut, b] not in vias and [b, cut, a] not in vias:
            vias.append([a, cut, b])


def _component_nets(p, cid, graph):
    """Include labels elsewhere on a conductor and assigned schematic terminals."""
    groups = graph.partition(p, cid)
    nets = {}
    for key, row in graph.records.items():
        shape = row['shape']; net = shape.get('net')
        if net:
            nets.setdefault(groups[('shape', *key)], set()).add(net)
    from .physical_cells import terminals, ports
    cell = next(c for c in p['cells'] if c['id'] == cid)
    devices = {d['id']: d for d in cell['devices']}
    anchors = [(('pin', v['id']), devices[v['device_id']]['nets'][v['pin']])
               for v in terminals(p, cid)]
    anchors += [(('port', v['name']), v['name']) for v in ports(p, cid)]
    for key, net in anchors:
        if key in groups: nets.setdefault(groups[key], set()).add(net)
    return groups, nets


def plan(p, cid, ids, connection=None, max_vias=1024, locked=()):
    """Propose centered arrays fully enclosed by selected, compatible conductors.

    Hierarchy participates in collision/net checks but is never edited. Searching
    a bounded regular array is conservative; it is not an optimal packing solver.
    """
    selected = set(ids)
    cell = next(c for c in p['cells'] if c['id'] == cid)
    local = {s['id']: s for s in cell['shapes']}
    if not 2 <= len(selected) <= 200 or not selected <= local.keys():
        raise ValueError('Select 2–200 conductor shapes in the active cell. Enter a child cell to edit its geometry.')
    if type(max_vias) is not int or not 1 <= max_vias <= 4096:
        raise ValueError('Autovia supports 1–4096 vias per operation.')
    tech = technology(p)
    recipes = via_recipes(tech)
    if connection:
        recipes = [v for v in recipes if v['name'] == connection]
    if not recipes: raise ValueError('Choose a mapped via connection for this technology.')
    layers = {v[k] for v in recipes for k in ('lower', 'upper')}
    if any(local[key]['layer'] not in layers for key in selected):
        raise ValueError('Select only conductor shapes for the chosen via connections, without cuts or instances.')
    if any(local[key]['layer'] in locked for key in selected):
        raise ValueError('Unlock the selected conductor layers before using Autovia.')
    from .design_ops import flatten_layout
    from .layout_graph import GeometryGraph
    q = clone(p); q['pdk']=clone(tech); declare_connections(q['pdk'])
    shapes = flatten_layout(q, cid); db = kdb(); grid = p['pdk']['grid']
    graph = GeometryGraph().sync(shapes, q['pdk'])
    groups, nets = _component_nets(q, cid, graph)
    regions = {}
    for key in sorted(selected):
        shape = local[key]; group = groups[('shape', key, '', '')]
        regions.setdefault((shape['layer'], group), db.Region()).insert(polygon(shape))
    cuts = {}
    for shape in shapes:
        cuts.setdefault(shape['layer'], db.Region()).insert(polygon(shape))
    result = []; attempts = 0; overlaps = 0; skipped = 0; used = set()
    for recipe in recipes:
        lower, upper, cut = (recipe[k] for k in ('lower', 'upper', 'cut'))
        for (layer, ga), ra in regions.items():
            if layer != lower: continue
            for (other, gb), rb in regions.items():
                if other != upper: continue
                overlap = (ra & rb).merged()
                if overlap.is_empty(): continue
                overlaps += 1
                if {lower, cut, upper} & set(locked):
                    raise ValueError('Unlock all three via-stack layers before using Autovia.')
                names = nets.get(ga, set()) | nets.get(gb, set())
                if len(names) > 1:
                    raise ValueError('Autovia would short conflicting nets: '+', '.join(sorted(names))+'.')
                net = next(iter(names), '')
                half = recipe['pad']//2
                space = recipe['spacing']
                if space <= 0:raise ValueError('Declare positive via cut spacing before using Autovia.')
                pitch = math.ceil((recipe['size']+space)/grid)*grid
                blocked = cuts.get(cut, db.Region()).merged().sized(space)
                for region in overlap.each():
                    box = region.bbox(); inside = db.Region(region)
                    x0 = math.ceil((box.left+half)/grid)*grid
                    x1 = math.floor((box.right-half)/grid)*grid
                    y0 = math.ceil((box.bottom+half)/grid)*grid
                    y1 = math.floor((box.top-half)/grid)*grid
                    if x0 > x1 or y0 > y1:
                        skipped += 1; continue
                    nx = (x1-x0)//pitch+1; ny = (y1-y0)//pitch+1
                    if attempts+nx*ny > 20000:
                        raise ValueError('Autovia search exceeds 20,000 sites. Select a smaller overlap.')
                    x0 += ((x1-x0-(nx-1)*pitch)//(2*grid))*grid
                    y0 += ((y1-y0-(ny-1)*pitch)//(2*grid))*grid
                    for iy in range(ny):
                        for ix in range(nx):
                            attempts += 1
                            point = [x0+ix*pitch, y0+iy*pitch]
                            candidate = via_shapes(recipe, point, net)
                            pad = db.Region(polygon(candidate[0]))
                            via = db.Region(polygon(candidate[1]))
                            # Bounding boxes alone are insufficient for paths,
                            # concave polygons, diagonal edges and polygon holes.
                            if not (pad-inside).is_empty() or not (via & blocked).is_empty():
                                skipped += 1; continue
                            if len(result)//3 >= max_vias:
                                raise ValueError('Autovia exceeds the via limit. Select a smaller region or increase the limit.')
                            result.extend(candidate); used.add(recipe['name'])
                            cuts.setdefault(cut, db.Region()).insert(polygon(candidate[1]))
                            blocked.insert(via.sized(space)); blocked.merge()
    if not result:
        raise ValueError('No new via fits the selected overlaps. Check conductor overlap, enclosure space and existing cuts.')
    # A blank conductor may bridge two differently named overlaps in one batch.
    # Rebuild topology for the entire proposal before any persistent mutation.
    graph.sync(shapes+result, q['pdk'])
    after, after_nets = _component_nets(q, cid, graph)
    for shape in result:
        group = after[('shape', shape['id'], '', '')]
        names = after_nets.get(group, set())
        if len(names) > 1:
            raise ValueError('Autovia would join conflicting nets through connected geometry: '+', '.join(sorted(names))+'.')
        shape['net'] = next(iter(names), '')
    return dict(kind='autovia', version=1, project_id=p['id'], cell_id=cid,
                design_hash=design_digest(p), route_group=uid(), shapes=result,
                via_count=len(result)//3, connections=sorted(used), selection=sorted(selected),
                overlaps=overlaps, skipped_sites=skipped,
                qualification='Vias fit inside selected conductors using declared cut spacing and enclosure. Run process DRC after editing.')


def install(p, proposal, locked=()):
    if proposal['project_id'] != p['id'] or proposal['design_hash'] != design_digest(p):
        raise ValueError('The design changed after the Autovia preview. Generate it again.')
    if any(s['layer'] in locked for s in proposal['shapes']):
        raise ValueError('Unlock all three via-stack layers before installing Autovia.')
    q = clone(p); q['pdk']=clone(technology(q)); declare_connections(q['pdk'])
    cell = next(c for c in q['cells'] if c['id'] == proposal['cell_id'])
    cell['shapes'].extend(clone(proposal['shapes']))
    validate(q)
    next(c for c in p['cells'] if c['id'] == cell['id']).update(cell)
    p['pdk'] = q['pdk']
    return [s['id'] for s in proposal['shapes']]
