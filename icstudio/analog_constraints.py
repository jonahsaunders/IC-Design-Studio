"""Explicit analog placement constraints checked against current geometry."""
import math
from .model import clone,digest,uid
from .layout import polygon,kdb

KINDS=('symmetry','matching','common_centroid','guard_ring')

def footprint(p,cid,did):
    c=next(c for c in p['cells'] if c['id']==cid);shapes=[s for s in c['shapes'] if s.get('device_id')==did]
    from .design_ops import flatten_layout
    from .physical_cells import transform
    for i in c.get('layout_instances',[]):
        if i.get('device_id')==did:
            for s in flatten_layout(p,i['cell']):
                from .layout import shape_from_polygon
                shapes.append(shape_from_polygon(polygon(s).transformed(transform(i)),s['layer']))
    if not shapes:raise ValueError('A constrained device is not placed.')
    box=polygon(shapes[0]).bbox()
    for s in shapes[1:]:box=box+polygon(s).bbox()
    return shapes,box,((box.left+box.right)/2,(box.bottom+box.top)/2)


def validate_constraints(p):
    for c in p['cells']:
        ds={d['id'] for d in c['devices']};rows=c.get('analog_constraints',[])
        if not isinstance(rows,list) or len(rows)>200:raise ValueError('Use at most 200 analog constraints per cell.')
        for row in rows:
            if row.get('kind') not in KINDS:raise ValueError('Unsupported analog constraint.')
            if not isinstance(row.get('members'),list) or not row['members'] or len(row['members'])>128:raise ValueError('Constraint members must be a nonempty device list.')
            # Deleted members remain an explicit finding, allowing ordinary deletion/undo.
            if row['kind']=='symmetry' and len(row['members'])!=2:raise ValueError('Symmetry needs exactly two devices.')
            if row['kind']=='common_centroid' and (not row.get('groups') or any(not g for g in row['groups']) or set(sum(row['groups'],[]))!=set(row['members'])):raise ValueError('Common-centroid groups must cover the selected devices.')
            if row.get('axis','x') not in ('x','y'):raise ValueError('Symmetry axis must be x or y.')
            if not isinstance(row.get('coordinate',0),(int,float)) or not math.isfinite(row.get('coordinate',0)):raise ValueError('Symmetry coordinate must be numeric.')


def findings(p,cid):
    c=next(c for c in p['cells'] if c['id']==cid);ds={d['id']:d for d in c['devices']};out=[]
    for row in c.get('analog_constraints',[]):
        try:
            if any(did not in ds for did in row['members']):raise ValueError('A constraint member was deleted.')
            placed=[footprint(p,cid,did) for did in row['members']];kind=row['kind']
            if kind=='symmetry':
                a,b=[v[2] for v in placed];axis=0 if row.get('axis','x')=='x' else 1;other=1-axis
                if a[axis]+b[axis]!=2*row.get('coordinate',0) or a[other]!=b[other]:raise ValueError('Device centers are not symmetric about the saved axis.')
            elif kind=='matching':
                signatures=[]
                for did,(shapes,box,center) in zip(row['members'],placed):
                    d=ds[did];regions={}
                    for shape in shapes:regions.setdefault(shape['layer'],kdb().Region()).insert(polygon(shape).transformed(kdb().Trans(-box.left,-box.bottom)))
                    native=d.get('native_spice',{});electrical={k:native.get(k) for k in ('tokens','parameters','model_name','definition')} if native else None
                    signatures.append((d['kind'],d.get('model_ref'),d.get('model_params',{}),d.get('cell'),d.get('parameters',{}),d.get('value') if d['kind'] in ('R','C','L') else d.get('params'),electrical,d.get('physical_binding'),{k:v.merged().to_s() for k,v in regions.items()}))
                if any(s!=signatures[0] for s in signatures[1:]):raise ValueError('Matched devices differ in electrical parameters, geometry or orientation.')
            elif kind=='common_centroid':
                centers={did:value[2] for did,value in zip(row['members'],placed)};group_centers=[tuple(sum(centers[i][axis] for i in group)/len(group) for axis in (0,1)) for group in row['groups']]
                if any(a!=group_centers[0] for a in group_centers[1:]):raise ValueError('Device-group centroids do not coincide.')
            elif kind=='guard_ring':
                ring=next((r for r in c.get('parametric_devices',[]) if r['id']==row.get('ring')),None)
                if not ring:raise ValueError('The assigned guard ring is missing.')
                spec=ring['spec'];x,y=spec['x'],spec['y'];t=spec['thickness'];
                reference=ring.get('reference',{});anchor=next((s for s in c['shapes'] if s.get('pcell_id')==ring['id'] and s.get('pcell_role')==reference.get('role')),None)
                if anchor:x+=anchor['points'][0][0]-reference['points'][0][0];y+=anchor['points'][0][1]-reference['points'][0][1]
                inner=kdb().Box(x+t,y+t,x+spec['width']-t,y+spec['height']-t)
                if any(not (inner.left<=box.left and inner.right>=box.right and inner.bottom<=box.bottom and inner.top>=box.top) for _,box,_ in placed):raise ValueError('A protected footprint extends outside the guard-ring opening.')
        except (ValueError,KeyError) as exc:
            out.append({'severity':'error','code':'ANALOG.'+row['kind'].upper(),'object':row['members'][0],'objects':row['members'],'cell_id':cid,'message':row.get('name',row['kind'])+': '+str(exc),'fingerprint':digest([row,str(exc),p['revision']])})
    return out


def move_device(p,cid,did,dx,dy):
    c=next(c for c in p['cells'] if c['id']==cid)
    if any(v%p['pdk']['grid'] for v in (dx,dy)):raise ValueError('Constraint placement would leave the grid. Adjust dimensions or axis.')
    dx,dy=int(dx),int(dy)
    for s in c['shapes']:
        if s.get('device_id')==did:s['points']=[[x+dx,y+dy] for x,y in s['points']];s['holes']=[[[x+dx,y+dy] for x,y in hole] for hole in s.get('holes',[])]
    for pin in c.get('layout_pins',[]):
        if pin['device_id']==did:pin['point']=[pin['point'][0]+dx,pin['point'][1]+dy]
    for i in c.get('layout_instances',[]):
        if i.get('device_id')==did:i['x']+=dx;i['y']+=dy


def arrange(p,cid,row,pitch=10000):
    kind=row['kind'];axis=0 if row.get('axis','x')=='x' else 1;coordinate=row.get('coordinate',0)
    if kind=='symmetry':
        a,b=[footprint(p,cid,did)[2] for did in row['members']];target=list(a);target[axis]=2*coordinate-a[axis];move_device(p,cid,row['members'][1],target[0]-b[0],target[1]-b[1])
    elif kind=='common_centroid':
        groups=row['groups']
        if len(groups)!=2 or len(groups[0])!=len(groups[1]) or len(groups[0])%2:raise ValueError('Automatic common-centroid placement supports two equal groups with an even number of unit devices (ABBA pairs).')
        order=[]
        for i in range(0,len(groups[0]),2):order.extend([groups[0][i],groups[1][i],groups[1][i+1],groups[0][i+1]])
        for index,did in enumerate(order):
            center=footprint(p,cid,did)[2];target=((index-(len(order)-1)/2)*pitch,0);move_device(p,cid,did,target[0]-center[0],target[1]-center[1])
    else:raise ValueError('This constraint checks geometry; use the device generator to correct matching or guard coverage.')
