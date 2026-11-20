"""Build single-shape repair proposals from the actual edges of a Studio DRC marker."""
from collections import Counter
import math

from .design_ops import flatten_layout
from .layout import kdb, polygon
from .layout_topology import require_preserved
from .live_geometry import full
from .model import clone, design_digest, digest, validate_shape
from .route_constraints import enforce


def finding_key(issue):
    # Fingerprints differ between the live and full checkers. Edges distinguish
    # separate findings even when their bounding boxes and reported objects coincide.
    edges = sorted(sorted(tuple(p) for p in edge) for edge in issue.get('edges', []))
    return digest([issue.get(k) for k in ('code','layer','conductor','bbox','message','measured_nm','minimum_nm')] + [edges])


def checked_change(project, cid, original, proposed, before):
    validate_shape(proposed,{layer['name'] for layer in project['pdk']['layers']})
    after = {**project, 'cells':[
        {**c, 'shapes':[proposed if s['id']==original['id'] else s for s in c['shapes']]}
        if c['id']==cid else c for c in project['cells']]}
    require_preserved(project, after, cid)
    enforce(project, after, cid)
    findings = full(after, cid)['issues']
    def identities(rows):
        # Width and spacing object hints are coarse bounding-box hits. The
        # measured layer and edge pair identify those findings across edits.
        return Counter((finding_key(i), None if i['code'] in ('WIDTH','SPACE') else i.get('object')) for i in rows)
    if identities(findings) - identities(before):
        raise ValueError('This change would introduce or worsen another layout finding.')
    return findings


def endpoints(edge):
    return [[edge.p1.x,edge.p1.y], [edge.p2.x,edge.p2.y]]


def shifted(edge, dx, dy):
    return kdb().Edge(edge.p1.x+dx, edge.p1.y+dy, edge.p2.x+dx, edge.p2.y+dy)


def supporting_edge(shape, edge):
    # KLayout reports clipped edge segments. The marker's object ID is only a
    # bounding-box hit, so resolve both segments against the actual polygons.
    return next((e for e in polygon(shape).each_edge() if e.contains(edge.p1) and e.contains(edge.p2)), None)


def normal_axis(edge):
    if edge.p1==edge.p2:return None
    if edge.p1.x==edge.p2.x:return 0
    if edge.p1.y==edge.p2.y:return 1
    return None


def coordinate(edge, axis):
    return (edge.p1.x, edge.p1.y)[axis]


def offset(axis, amount):
    return (amount,0) if axis==0 else (0,amount)


def edge_span(edge, axis):
    a,b=endpoints(edge)
    return sorted((a[axis],b[axis]))


def adjust_edge(shape, edge, axis, amount, grow):
    """Move one Manhattan boundary, keeping everything outside its strip intact."""
    proposed = clone(shape)
    start = coordinate(edge,axis)
    if shape['kind']=='rect':
        if not grow and abs(amount)>=abs(proposed['points'][1][axis]-proposed['points'][0][axis]):return
        for point in proposed['points']:
            if point[axis]==start:point[axis]+=amount
    elif shape['kind']=='polygon':
        db = kdb()
        dx,dy = offset(axis,amount)
        strip = db.Region(edge.bbox()+shifted(edge,dx,dy).bbox())
        original = db.Region(polygon(shape))
        merged = (original | strip) if grow else (original - strip)
        pieces = list(merged.each_merged())
        if len(pieces)!=1 or pieces[0].holes()!=polygon(shape).holes():return
        poly = pieces[0]
        proposed['points'] = [[p.x,p.y] for p in poly.each_point_hull()]
        if 'holes' in shape or poly.holes():
            proposed['holes'] = [[[p.x,p.y] for p in poly.each_point_hole(i)] for i in range(poly.holes())]
    else:return
    before,after = polygon(shape),polygon(proposed)
    if (after.area()-before.area())*(1 if grow else -1)<=0:return
    return proposed


def translate(shape, dx, dy):
    proposed = clone(shape)
    def move(ring):
        return [[x+dx,y+dy] for x,y in ring]
    proposed['points'] = move(shape['points'])
    if shape.get('holes'):proposed['holes']=[move(hole) for hole in shape['holes']]
    return proposed


def spacing_offsets(edges, minimum, grid):
    # Find the smallest grid step along each editor axis that clears the pair.
    # Distance to a fixed segment is convex along a translation. An outward
    # first step rules out moving through the opposing edge.
    db = kdb()
    a,b = edges
    initial = db.EdgePair(a,b).distance()
    moves = []
    for axis in (0,1):
        for sign in (1,-1):
            def distance(steps):
                return db.EdgePair(shifted(a,*offset(axis,sign*steps*grid)), b).distance()
            if distance(1)<=initial:continue
            high = math.ceil(2*minimum/grid)+1
            if distance(high)<minimum:continue
            low = 1
            while low<high:
                mid=(low+high)//2
                if distance(mid)>=minimum:high=mid
                else:low=mid+1
            moves.append((low,axis,sign))
    return [offset(axis,sign*n*grid) for n,axis,sign in sorted(moves)]


def options(code, owners, edges, minimum, grid):
    db = kdb()
    measured = db.EdgePair(*edges).distance()
    step = math.ceil((minimum-measured)/grid)*grid
    same = owners[0] is owners[1]
    if code=='SPACE' and not same:
        for dx,dy in spacing_offsets(edges,minimum,grid):
            # Keep the first edge as the reference when both sides can move.
            for i,sign in ((1,-1),(0,1)):
                x,y=sign*dx,sign*dy
                new_edges=edges.copy()
                new_edges[i]=shifted(edges[i],x,y)
                yield i,translate(owners[i],x,y),new_edges,f'Move X {x:+d} nm, Y {y:+d} nm.'
    shape=owners[0]
    if code=='WIDTH' and same and shape['kind']=='path' and len(shape['points'])==2:
        # A straight stroke has two longitudinal polygon sides. Resolve them
        # again on the widened polygon to include database rounding on diagonals.
        (x,y),(r,t)=shape['points']
        def sides(s):
            return [e for e in polygon(s).each_edge() if
                    abs((e.p2.x-e.p1.x)*(r-x)+(e.p2.y-e.p1.y)*(t-y)) >
                    abs((e.p2.x-e.p1.x)*(t-y)-(e.p2.y-e.p1.y)*(r-x))]
        old=sides(shape)
        if len(old)==2 and all(any(e.contains(s.p1) and e.contains(s.p2) for e in old) for s in edges):
            base=math.ceil(minimum/grid)*grid
            for width in (base,base+grid):
                if width<=shape['width']:continue
                proposed={**shape,'width':width}
                new_edges=sides(proposed)
                if len(new_edges)==2 and db.EdgePair(*new_edges).distance()>=minimum:
                    yield 0,proposed,new_edges,f"Set path width from {shape['width']} to {width} nm along the stored centerline."
                    return
        return
    axis = normal_axis(edges[0])
    if axis is None or normal_axis(edges[1])!=axis:return
    where = [coordinate(e,axis) for e in edges]
    if abs(where[0]-where[1])!=measured or measured<=0:return
    if code=='WIDTH' and not same:return
    if code=='WIDTH' and owners[0]['kind']=='path':
        shape=owners[0]
        if shape['width']!=measured:return
        proposed=clone(shape)
        proposed['width']=math.ceil(minimum/grid)*grid
        # Identify the actual new sides after KLayout rounds the stroked path.
        spans=[edge_span(e,1-axis) for e in edges]
        lo,hi=max(a for a,b in spans),min(b for a,b in spans)
        section=(lo+hi)/2
        sides=[]
        for i,e in enumerate(edges):
            sign=1 if where[i]>where[1-i] else -1
            half=(proposed['width']-measured)/2
            for amount in dict.fromkeys((math.floor(half),math.ceil(half))):
                position=where[i]+sign*amount
                side=next((s for s in polygon(proposed).each_edge() if normal_axis(s)==axis and
                           coordinate(s,axis)==position and edge_span(s,1-axis)[0]<=section<=edge_span(s,1-axis)[1]),None)
                if side is not None:
                    sides.append(side)
                    break
        if len(sides)==2:
            # A miter shortens the inner edge as the stroke widens. Compare the
            # overlapping portion of the actual new boundaries at this segment.
            spans.extend(edge_span(s,1-axis) for s in sides)
            lo,hi=max(a for a,b in spans),min(b for a,b in spans)
            if lo<hi:
                def clipped(s):
                    v=coordinate(s,axis)
                    return db.Edge(v,lo,v,hi) if axis==0 else db.Edge(lo,v,hi,v)
                yield 0,proposed,[clipped(s) for s in sides],f"Set path width from {shape['width']} to {proposed['width']} nm along the stored centerline."
        return
    for i in (0,1):
        amount = step if where[i]>where[1-i] else -step
        edge = supporting_edge(owners[i],edges[i])
        proposed = adjust_edge(owners[i],edge,axis,amount,grow=code=='WIDTH')
        if proposed:
            new_edges=edges.copy()
            new_edges[i]=shifted(edges[i],*offset(axis,amount))
            label='XY'[axis]
            yield i,proposed,new_edges,f'Move the edge at {label} = {where[i]} nm to {where[i]+amount} nm.'


def rule_repair(project, cid, issue, locked=()):
    code=issue.get('code')
    if code not in ('WIDTH','SPACE') or len(issue.get('edges',[]))!=2:
        raise ValueError('Select a measured Studio width or spacing finding.')
    if issue.get('cell_id',cid)!=cid:raise ValueError('Select this finding in its original cell.')
    if issue.get('layer') in locked:raise ValueError('Unlock the affected layer before reviewing a change.')
    if any(i['cell']==cid for c in project['cells'] for i in c.get('layout_instances',[])):
        raise ValueError('This cell has parent instances. A local review cannot check every placement.')
    before=full(project,cid)['issues']
    key=finding_key(issue)
    matches=[i for i in before if finding_key(i)==key]
    if len(matches)!=1:raise ValueError('The complete checker could not reproduce this exact finding. Refresh the layout evidence.')
    marker=matches[0]
    db=kdb()
    edges=[db.Edge(db.Point(*a),db.Point(*b)) for a,b in marker['edges']]
    shapes=[s for s in flatten_layout(project,cid) if s['layer']==marker['layer']]
    owners=[]
    for edge in edges:
        touching=[s for s in shapes if supporting_edge(s,edge)]
        if len(touching)!=1:
            raise ValueError('The measured edge has no unique shape owner. Inspect the merged geometry in the layout editor.')
        owners.append(touching[0])
    cell=next(c for c in project['cells'] if c['id']==cid)
    local={s['id'] for s in cell['shapes']}
    reason='The selected edges do not support a verified single-shape repair.'
    for i,proposed,new_edges,description in options(code,owners,edges,marker['minimum_nm'],project['pdk']['grid']):
        original=owners[i]
        if (original['id'] not in local or original.get('instance_path') or
            any(original.get(k) for k in ('via_group','pcell_id','device_id','generated_device','generated_route','connected_lead'))):
            reason='A participating shape belongs to an instance or generated group. Edit its owner to change it.'
            continue
        after_owners=[proposed if s is original else s for s in owners]
        if not all(supporting_edge(s,e) for s,e in zip(after_owners,new_edges)):continue
        measured_after=db.EdgePair(*new_edges).distance()
        if measured_after<marker['minimum_nm']:continue
        try:
            findings=checked_change(project,cid,original,proposed,before)
        except ValueError as exc:
            reason=str(exc)
            continue
        if any(finding_key(f)==key for f in findings):continue
        return dict(original=original,proposed=proposed,description=description,after_nm=measured_after,
                    after_edges=[endpoints(e) for e in new_edges],reference=owners[1-i]['id'],
                    before_count=len(before),after_count=len(findings),origin=design_digest(project))
    raise ValueError('No checked repair is available. '+reason)
