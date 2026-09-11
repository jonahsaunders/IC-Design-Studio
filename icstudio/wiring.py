"""Stored schematic paths and electrical connectivity; independent of Qt.

Wire ends, shared vertices, pins and explicit junctions join conductors.
Interior crossings do not. Net labels deliberately connect distant conductors.
"""
from __future__ import annotations
import math
from .model import uid, clone, NET


def clean(points):
    out=[]
    for point in points:
        pt=list(point)
        if out and pt==out[-1]:continue
        while len(out)>1 and ((out[-2][0]==out[-1][0]==pt[0]) or (out[-2][1]==out[-1][1]==pt[1])):
            # Only collapse a vertex between its neighbours, never a reversal.
            if (out[-1][0]-out[-2][0])*(pt[0]-out[-1][0])+(out[-1][1]-out[-2][1])*(pt[1]-out[-1][1])<0:break
            out.pop()
        out.append(pt)
    return out


def on_segment(pt,a,b):
    return (min(a[0],b[0])-1e-7<=pt[0]<=max(a[0],b[0])+1e-7 and
            min(a[1],b[1])-1e-7<=pt[1]<=max(a[1],b[1])+1e-7 and
            abs((pt[0]-a[0])*(b[1]-a[1])-(pt[1]-a[1])*(b[0]-a[0]))<1e-6)


def nearest(pt,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1];length=dx*dx+dy*dy
    t=max(0,min(1,((pt[0]-a[0])*dx+(pt[1]-a[1])*dy)/length)) if length else 0
    return [a[0]+t*dx,a[1]+t*dy]


def pins(cell,project=None):
    from .interchange import pin_positions
    by={c['id']:c for c in project['cells']} if project else {}
    result={}
    for original in cell['devices']:
        d=original
        if d['kind']=='X' and by.get(d.get('cell'),{}).get('symbol'):d={**d,'symbol':by[d['cell']]['symbol']}
        for name,point in pin_positions(d).items():result[(d['id'],name)]=list(point)
    return result


def segment_index(cell):
    from .spatial import SpatialIndex
    segments=[(('wire',w['id']),a,b) for w in cell.get('wires',[]) for a,b in zip(w['points'],w['points'][1:])]
    index=SpatialIndex([((min(a[0],b[0])-1e-7,min(a[1],b[1])-1e-7,max(a[0],b[0])+1e-7,max(a[1],b[1])+1e-7),i) for i,(_,a,b) in enumerate(segments)])
    return segments,index


def graph(cell,project=None,labels=True):
    wires=cell.get('wires',[]);positions=pins(cell,project)
    parent={('wire',w['id']):('wire',w['id']) for w in wires}
    parent.update({key:key for key in positions})
    parent.update({('label',l['id']):('label',l['id']) for l in cell.get('labels',[])})
    def find(key):
        while parent[key]!=key:parent[key]=parent[parent[key]];key=parent[key]
        return key
    def join(a,b):parent[find(b)]=find(a)
    segments,index=segment_index(cell)
    # Endpoints on another segment connect; a bare interior crossing does not.
    for i,(key,a,b) in enumerate(segments):
        for j in index.query((min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1]))):
            if j>=i:continue
            other,c,d=segments[j]
            if key==other:continue
            if max(min(a[0],b[0]),min(c[0],d[0]))>min(max(a[0],b[0]),max(c[0],d[0])):continue
            if max(min(a[1],b[1]),min(c[1],d[1]))>min(max(a[1],b[1]),max(c[1],d[1])):continue
            if any(on_segment(pt,c,d) for pt in (a,b)) or any(on_segment(pt,a,b) for pt in (c,d)):join(key,other)
    at={}
    for key,point in positions.items():
        coord=tuple(point)
        if coord in at:join(key,at[coord])
        at[coord]=key
        for j in index.query((*point,*point)):
            wire,a,b=segments[j]
            if on_segment(point,a,b):join(key,wire)
    for point in cell.get('junctions',[]):
        hits=[segments[j][0] for j in index.query((*point,*point)) if on_segment(point,*segments[j][1:])]
        for key in hits[1:]:join(hits[0],key)
    from .net_labels import entries,point,target
    for label in cell.get('labels',[]):
        key=('label',label['id']);attached=target(label)
        if attached is not None:
            if attached not in parent:raise ValueError('Label attachment is missing.')
            join(key,attached)
        else:
            pt=point(label,cell,project)
            for other,position in positions.items():
                if pt==position:join(key,other)
            for j in index.query((*pt,*pt)):
                wire,a,b=segments[j]
                if on_segment(pt,a,b):join(key,wire)
            coord=tuple(pt)
            if coord in at:join(key,at[coord])
            at[coord]=key
    if labels:
        named={}
        for key,obj,field,name in entries(cell):
            if name in named:join(named[name],key)
            named[name]=key
    return {key:find(key) for key in parent}


def rebuild(cell,project=None):
    if 'wires' not in cell:return
    groups=graph(cell,project);names={};members={}
    for d in cell['devices']:
        for pin in d['nets']:
            key=(d['id'],pin);root=groups[key];members.setdefault(root,[]).append(key)
            if pin in d.get('net_labels',{}):names.setdefault(root,set()).add(d['net_labels'][pin])
    for label in cell.get('labels',[]):
        root=groups[('label',label['id'])];names.setdefault(root,set()).add(label['name']);members.setdefault(root,[])
    for values in names.values():
        if len(values)>1:raise ValueError('Wire joins conflicting labels: '+', '.join(sorted(values))+'. Rename or remove a label before moving this connection.')
    # Preserve generated names when only a symbol's terminal roles change.
    # Explicit labels still win, and splits/merges receive fresh names.
    from .electrical_identity import terminal_id
    terminals={(d['id'],pin):terminal_id(d,pin) for d in cell['devices'] for pin in d['nets']}
    previous={frozenset(net['terminals']):net['name'] for net in cell.get('electrical',{}).get('nets',[])
              if net['terminals'] and net['name'].startswith('N_')}
    reserved={name for values in names.values() for name in values};assigned={}
    for root,keys in members.items():
        if names.get(root):assigned[root]=next(iter(names[root]));continue
        ident,pin=min(keys);name=previous.get(frozenset(terminals[key] for key in keys),'N_'+ident+'_'+pin)
        while name in reserved:name+='x'
        reserved.add(name);assigned[root]=name
    for wire in cell['wires']:
        root=groups[('wire',wire['id'])]
        if root not in assigned:
            name='N_wire_'+root[1]
            while name in reserved:name+='x'
            reserved.add(name);assigned[root]=name
        wire['net']=assigned[root]
    for d in cell['devices']:
        for pin in d['nets']:d['nets'][pin]=assigned[groups[(d['id'],pin)]]
    if 'electrical' in cell:
        from .electrical_identity import synchronize
        synchronize(cell)


def validate_wiring(cell,objid,project):
    if 'wires' not in cell:return
    wires=cell['wires']
    if not isinstance(wires,list) or len(wires)>5000:raise ValueError('A cell supports at most 5,000 wires.')
    points=[]
    for wire in wires:
        objid(wire['id']);pts=wire.get('points',[])
        if not isinstance(pts,list) or not 2<=len(pts)<=1000:raise ValueError('A wire requires 2–1,000 points.')
        points+=pts
        for a,b in zip(pts,pts[1:]):
            if a==b:raise ValueError('Wire segments must have distinct endpoints.')
    junctions=cell.get('junctions',[])
    if not isinstance(junctions,list) or len(junctions)>5000:raise ValueError('Invalid junction list.')
    points+=junctions
    if any(not isinstance(pt,list) or len(pt)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>1e7 for v in pt) for pt in points):raise ValueError('Invalid schematic wire coordinate.')
    from .net_labels import validate as validate_labels
    validate_labels(cell,objid,project)
    for d in cell['devices']:
        labels=d.get('net_labels',{})
        if not isinstance(labels,dict) or any(pin not in d['nets'] or not isinstance(name,str) or not NET.fullmatch(name) for pin,name in labels.items()):raise ValueError('Invalid pin net label. Use 0 for ground.')
    rebuild(cell,project)


def migrate(cell,project=None):
    """Freeze legacy paths only if geometry preserves every original net.

    Ambiguous old drawings instead retain their named connections as explicit
    pin labels. No invisible change to the legacy electrical circuit is made.
    """
    if 'wires' in cell:return
    positions=pins(cell,project);expected={(d['id'],pin):net for d in cell['devices'] for pin,net in d['nets'].items()}
    groups={}
    for key,point in positions.items():groups.setdefault(expected[key],[]).append((key,point))
    cell['wires']=[];cell['junctions']=[]
    for d in cell['devices']:d['net_labels']={}
    by={d['id']:d for d in cell['devices']}
    for name,items in groups.items():
        key,a=items[0];by[key[0]]['net_labels'][key[1]]=name
        for _,b in items[1:]:
            mid=round((a[0]+b[0])/20)*10
            path=clean([a,[mid,a[1]],[mid,b[1]],b])
            if len(path)>1:cell['wires'].append({'id':uid(),'points':path})
    try:
        rebuild(cell,project)
        if any(d['nets'][pin]!=expected[(d['id'],pin)] for d in cell['devices'] for pin in d['nets']):raise ValueError('Ambiguous legacy paths')
    except ValueError:
        cell['wires']=[];cell['wiring_migration']='named_connections'
        for d in cell['devices']:d['net_labels']={pin:expected[(d['id'],pin)] for pin in d['nets']}
        # Coincident pins on contradictory old nets are invalid physically.
        # Preserve the old representation until the user moves them apart.
        try:rebuild(cell,project)
        except ValueError:
            cell.pop('wires');cell.pop('junctions')
            for d in cell['devices']:d.pop('net_labels',None);d['nets']={pin:expected[(d['id'],pin)] for pin in d['nets']}


def add_wire(cell,points,project=None):
    migrate(cell,project)
    if 'wires' not in cell:raise ValueError('Move overlapping legacy pins apart before placing wires.')
    points=clean(points)
    if len(points)<2:return None,[]
    pos=pins(cell,project);preferred=None
    for d in cell['devices']:
        for pin in d['nets']:
            if pos[(d['id'],pin)]==points[0]:preferred=d['nets'][pin]
    if preferred is None:
        for w in cell['wires']:
            if any(on_segment(points[0],a,b) for a,b in zip(w['points'],w['points'][1:])):preferred=w.get('net');break
    wire={'id':uid(),'points':points};cell['wires'].append(wire)
    # Drawing an intentional connection merges the ENTIRE connected nets.
    groups=graph(cell,project);root=groups[('wire',wire['id'])]
    changes=merge_labels(cell,groups,root,preferred,project)
    rebuild(cell,project);return wire['id'],changes


def merge_labels(cell,groups,root,preferred=None,project=None):
    from .net_labels import entries
    labels=[(key,obj,field,name) for key,obj,field,name in entries(cell) if groups[key]==root]
    names={name for _,_,_,name in labels};chosen='0' if '0' in names else preferred if preferred in names else sorted(names)[0] if names else None
    changes=sorted(names-{chosen});physical=graph(cell,project,labels=False);kept=set()
    for key,obj,field,name in sorted(labels,key=lambda item:(item[0][0]!='label',item[3]!=chosen)):
        group=physical[key]
        if key[0]!='label' and group in kept:del obj[field]
        else:
            obj[field]=chosen;kept.add(group)
            if obj.get('kind')=='ground' and chosen!='0':obj['kind']='net_label'
    return changes


def set_label(cell,device_id,pin,name,project=None):
    migrate(cell,project)
    target=next(d for d in cell['devices'] if d['id']==device_id)
    if 'wires' not in cell:target['nets'][pin]=name;return
    if name and not NET.fullmatch(name):raise ValueError('Invalid net label. Use 0 for ground.')
    # Rename a geometric conductor; identical remote labels remain intentional.
    groups=graph(cell,project,labels=False);root=groups[(device_id,pin)]
    for d in cell['devices']:
        for p in list(d.get('net_labels',{})):
            if groups[(d['id'],p)]==root:del d['net_labels'][p]
    attached=[l for l in cell.get('labels',[]) if groups[('label',l['id'])]==root]
    for l in attached:
        if name:
            l['name']=name
            if l['kind']=='ground' and name!='0':l['kind']='net_label';l['offset']=[10,-12]
        else:cell['labels'].remove(l)
    if name and not attached:target.setdefault('net_labels',{})[pin]=name
    rebuild(cell,project)


def segment_drag(points,index,dx,dy,fixed_start=True,fixed_end=True):
    """Slide a segment and its adjacent bends, retaining anchored outer ends.

    The old segment vertices are replaced, not copied into the new path. This
    makes repeated drags reversible without accumulating stair-step geometry.
    """
    a,b=points[index:index+2]
    shift=[0,dy] if a[1]==b[1] else [dx,0] if a[0]==b[0] else [dx,dy]
    if not any(shift):return clone(points)
    aa=[a[0]+shift[0],a[1]+shift[1]];bb=[b[0]+shift[0],b[1]+shift[1]]
    prefix=points[:index] if index else ([a] if fixed_start else [])
    suffix=points[index+2:] if index+2<len(points) else ([b] if fixed_end else [])
    return clean(prefix+[aa,bb]+suffix)


def retarget_path(points,start=None,end=None,protected=()):
    """Adjust terminal leads in place; do not retain each previous elbow."""
    path=clone(points);protected={tuple(p) for p in protected}
    if len(path)==2 and start is not None and end is not None:
        bend=[start[0],end[1]] if path[0][0]==path[1][0] else [end[0],start[1]]
        return clean([start,bend,end])
    for reverse,target in ((False,start),(True,end)):
        if target is None:continue
        if reverse:path.reverse()
        old=path[0];target=list(target)
        if old!=target:
            if len(path)<2:path=[target];continue
            next_pt=path[1]
            elbow=[target[0],next_pt[1]] if old[0]==next_pt[0] else [next_pt[0],target[1]]
            if len(path)>2 and tuple(next_pt) not in protected:
                path=clean([target,elbow]+path[2:])
            else:path=clean([target,elbow]+path[1:])
        if reverse:path.reverse()
    return path


def reshape_segment(cell,ident,index,dx,dy,project=None):
    """Keep pins/junctions fixed and stretch branch leads with the dragged run."""
    from .net_labels import reconcile
    old=clone(cell);wire=next(w for w in cell['wires'] if w['id']==ident)
    a,b=wire['points'][index:index+2];shift=[0,dy] if a[1]==b[1] else [dx,0]
    if not any(shift):return
    fixed={tuple(p) for p in pins(cell,project).values()}|{tuple(p) for p in cell.get('junctions',[])}
    fixed.update(tuple(l['anchor']['point']) for l in cell.get('labels',[]) if l['anchor']['kind']=='point')
    others=[w for w in cell['wires'] if w['id']!=ident]
    # An endpoint meeting the interior of another conductor remains a junction.
    for pt in (a,b):
        if any(pt not in (w['points'][0],w['points'][-1]) and any(on_segment(pt,c,d) for c,d in zip(w['points'],w['points'][1:])) for w in others):fixed.add(tuple(pt))
    wire['points']=segment_drag(wire['points'],index,dx,dy,tuple(a) in fixed,tuple(b) in fixed)
    for other in others:
        start,end=other['points'][0],other['points'][-1]
        move=lambda pt:[pt[0]+shift[0],pt[1]+shift[1]] if on_segment(pt,a,b) and tuple(pt) not in fixed else None
        new_start,new_end=move(start),move(end)
        if new_start is not None or new_end is not None:other['points']=retarget_path(other['points'],new_start,new_end,fixed)
    for pt in sorted(fixed):
        if on_segment(pt,a,b) and list(pt) not in (a,b):
            cell['wires'].append({'id':uid(),'points':[list(pt),[pt[0]+shift[0],pt[1]+shift[1]]]})
    for label in cell.get('labels',[]):
        anchor=label['anchor']
        if anchor['kind']=='wire' and anchor['id']==ident and on_segment(anchor['point'],a,b):
            anchor['point']=[anchor['point'][0]+shift[0],anchor['point'][1]+shift[1]]
    cell['wires']=[w for w in cell['wires'] if len(w['points'])>1]
    reconcile(cell,old,project);rebuild(cell,project)
    if 'electrical' in cell:
        from .electrical_identity import require_preserved
        require_preserved(old,cell)


def keep_connections(cell,before,project=None,moved_wires=()):
    """Batch terminal changes against one geometry snapshot, preserving branches."""
    if 'wires' not in cell:return
    electrical_before=clone(cell) if 'electrical' in cell else None
    after=pins(cell,project);moved_wires=set(moved_wires);original=clone(cell['wires'])
    changes={tuple(old):after[key] for key,old in before.items() if key in after and old!=after[key]}
    if not changes:return
    fixed={tuple(pt) for key,pt in before.items() if after.get(key)==pt}|{tuple(p) for p in cell.get('junctions',[])}
    destinations={}
    for key,old in before.items():
        if key in after:destinations.setdefault(tuple(old),set()).add(tuple(after[key]))
    fixed.update(pt for pt,targets in destinations.items() if len(targets)>1)
    fixed.update(tuple(l['anchor']['point']) for l in cell.get('labels',[]) if l['anchor']['kind']=='point')
    # Shared vertices and branch contacts constrain adjacent bend adjustment.
    contacts=set(fixed);records,index=segment_index({'wires':original});by_id={w['id']:w for w in original}
    for w in original:
        for pt in w['points']:
            if any(records[j][0][1]!=w['id'] and on_segment(pt,*records[j][1:]) for j in index.query((*pt,*pt))):contacts.add(tuple(pt))
    attached=set()
    for wire in cell['wires']:
        if wire['id'] in moved_wires:continue
        pts=wire['points'];ends=[]
        for pt in (pts[0],pts[-1]):
            key=tuple(pt);target=changes.get(key)
            if target is None:ends.append(None);continue
            shared=key in fixed or any(records[j][0][1]!=wire['id'] and pt not in (by_id[records[j][0][1]]['points'][0],by_id[records[j][0][1]]['points'][-1]) and on_segment(pt,*records[j][1:]) for j in index.query((*pt,*pt)))
            ends.append(target if target is not None and not shared else None)
            if ends[-1] is not None:attached.add(key)
        if all(pt is not None for pt in ends) and [ends[0][i]-pts[0][i] for i in (0,1)]==[ends[1][i]-pts[-1][i] for i in (0,1)] and not any(tuple(pt) in contacts for pt in pts[1:-1]):
            delta=[ends[0][i]-pts[0][i] for i in (0,1)];wire['points']=[[pt[i]+delta[i] for i in (0,1)] for pt in pts]
        elif any(pt is not None for pt in ends):wire['points']=retarget_path(pts,*ends,contacts)
    branches=set()
    for key,old in before.items():
        new=after.get(key);coord=tuple(old)
        if new is None or new==old or coord in attached or (coord,tuple(new)) in branches:continue
        if any(records[j][0][1] not in moved_wires and on_segment(old,*records[j][1:]) for j in index.query((*old,*old))):
            path=clean([old,[new[0],old[1]],new])
            if len(path)>1:cell['wires'].append({'id':uid(),'points':path});branches.add((coord,tuple(new)))
    cell['wires']=[w for w in cell['wires'] if len(w['points'])>1]
    if electrical_before is not None:
        from .electrical_identity import require_preserved
        rebuild(cell,project);require_preserved(electrical_before,cell)


def junction_points(cell,project=None):
    records,index=segment_index(cell);segments=[(a,b) for _,a,b in records]
    candidates={tuple(pt) for pt in cell.get('junctions',[])}|{tuple(pt) for a,b in segments for pt in (a,b)}|{tuple(pt) for pt in pins(cell,project).values()}
    dots=[]
    for pt in candidates:
        directions=set()
        for j in index.query((*pt,*pt)):
            a,b=segments[j]
            if on_segment(pt,a,b):
                for end in (a,b):
                    dx,dy=end[0]-pt[0],end[1]-pt[1]
                    if dx or dy:directions.add((0 if dx==0 else 1 if dx>0 else -1,0 if dy==0 else 1 if dy>0 else -1))
        if len(directions)>=3:dots.append(pt)
    return dots
