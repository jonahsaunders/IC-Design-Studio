"""Explicit analog placement constraints checked against current geometry."""
import math
from .model import clone,digest,uid
from .layout import polygon,kdb

KINDS=('symmetry','matching','common_centroid','guard_ring')


def electrical_signature(p,cid,d):
    """Compare known process models by emitted dimensions, not symbol spelling."""
    native=d.get('native_spice',{})
    if not native and d.get('model_ref'):
        from .catalog import binding_for
        from .sky130_layout import resolved
        from .process_mos import dimensions
        actual=resolved(p,cid,d);binding=binding_for(p['pdk'],actual)
        try:spec=dimensions(p['pdk'],actual,binding)
        except ValueError:pass  # Other PDKs retain their exact declared parameters.
        else:
            emit=binding.get('emit_parameters',{'w':'w','l':'l'})
            return (d['kind'],spec['model'],{key:spec['values'][source] for key,source in emit.items()},d.get('physical_binding'))
    electrical={k:native.get(k) for k in ('tokens','parameters','model_name','definition')} if native else None
    return (d['kind'],d.get('model_ref'),d.get('model_params',{}),d.get('cell'),d.get('parameters',{}),
            d.get('value') if d['kind'] in ('R','C','L') else d.get('params'),electrical,d.get('physical_binding'))


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
            if len(set(row['members'])) != len(row['members']) or row['kind']=='common_centroid' and len(sum(row['groups'],[])) != len(row['members']):
                raise ValueError('Each device must occur exactly once in a constraint and its groups.')
            if row.get('axis','x') not in ('x','y'):raise ValueError('Symmetry axis must be x or y.')
            if not isinstance(row.get('coordinate',0),(int,float)) or not math.isfinite(row.get('coordinate',0)):raise ValueError('Symmetry coordinate must be numeric.')


def findings(p,cid):
    c=next(c for c in p['cells'] if c['id']==cid);ds={d['id']:d for d in c['devices']};out=[]
    for index,row in enumerate(c.get('analog_constraints',[])):
        metrics={};placed=[]
        try:
            metrics['missing_members']=sum(did not in ds for did in row['members'])
            if metrics['missing_members']:raise ValueError('A constraint member was deleted.')
            placed=[footprint(p,cid,did) for did in row['members']];kind=row['kind']
            if kind=='symmetry':
                a,b=[v[2] for v in placed];axis=0 if row.get('axis','x')=='x' else 1;other=1-axis
                metrics['axis_error_nm']=abs(a[axis]+b[axis]-2*row.get('coordinate',0))
                metrics['transverse_error_nm']=abs(a[other]-b[other])
                if metrics['axis_error_nm'] or metrics['transverse_error_nm']:raise ValueError('Device centers are not symmetric about the saved axis.')
            elif kind=='matching':
                signatures=[];geometries=[]
                for did,(shapes,box,center) in zip(row['members'],placed):
                    d=ds[did];regions={}
                    for shape in shapes:regions.setdefault(shape['layer'],kdb().Region()).insert(polygon(shape).transformed(kdb().Trans(-box.left,-box.bottom)))
                    geometries.append(regions)
                    signatures.append((electrical_signature(p,cid,d),{k:v.merged().to_s() for k,v in regions.items()}))
                metrics['electrical_mismatches']=sum(s[:-1]!=signatures[0][:-1] for s in signatures[1:])
                metrics['geometry_mismatches']=sum(s[-1]!=signatures[0][-1] for s in signatures[1:])
                metrics['geometry_error_nm2']=sum((regions.get(layer,kdb().Region()) ^ geometries[0].get(layer,kdb().Region())).area() for regions in geometries[1:] for layer in regions.keys() | geometries[0].keys())
                if metrics['electrical_mismatches'] or metrics['geometry_mismatches']:raise ValueError('Matched devices differ in electrical parameters, geometry or orientation.')
            elif kind=='common_centroid':
                centers={did:value[2] for did,value in zip(row['members'],placed)};group_centers=[tuple(sum(centers[i][axis] for i in group)/len(group) for axis in (0,1)) for group in row['groups']]
                metrics['centroid_error_nm']=max(math.dist(a,b) for a in group_centers for b in group_centers)
                if metrics['centroid_error_nm']:raise ValueError('Device-group centroids do not coincide.')
            elif kind=='guard_ring':
                ring=next((r for r in c.get('parametric_devices',[]) if r['id']==row.get('ring')),None)
                if not ring:raise ValueError('The assigned guard ring is missing.')
                spec=ring['spec'];x,y=spec['x'],spec['y'];t=spec['thickness'];
                reference=ring.get('reference',{});anchor=next((s for s in c['shapes'] if s.get('pcell_id')==ring['id'] and s.get('pcell_role')==reference.get('role')),None)
                if anchor:x+=anchor['points'][0][0]-reference['points'][0][0];y+=anchor['points'][0][1]-reference['points'][0][1]
                inner=kdb().Box(x+t,y+t,x+spec['width']-t,y+spec['height']-t)
                metrics['enclosure_error_nm']=max(max(inner.left-box.left,box.right-inner.right,inner.bottom-box.bottom,box.top-inner.top,0) for _,box,_ in placed)
                if metrics['enclosure_error_nm']:raise ValueError('A protected footprint extends outside the guard-ring opening.')
        except (ValueError,KeyError) as exc:
            shape_ids=[s['id'] for s in c['shapes'] if s.get('device_id') in row['members'] or s.get('generated_device') in row['members']]
            shape_ids += [i['id'] for i in c.get('layout_instances',[]) if i.get('device_id') in row['members']]
            boxes=[[box.left,box.bottom,box.right,box.top] for _,box,_ in placed]
            bbox=[min(v[0] for v in boxes),min(v[1] for v in boxes),max(v[2] for v in boxes),max(v[3] for v in boxes)] if boxes else None
            out.append({'severity':'error','code':'ANALOG.'+row['kind'].upper(),'constraint_id':row.get('id',str(index)),
                        'object':row['members'][0],'objects':row['members'],'shape_ids':shape_ids,'boxes':boxes,'bbox':bbox,
                        'metrics':metrics,'cell_id':cid,'message':row.get('name',row['kind'])+': '+str(exc),
                        'remediation':'Review all members together; regenerate equal devices, restore the saved placement, or revise the explicit constraint.',
                        'fingerprint':digest([cid,row,str(exc)])})
    return out


def preserve_centers(before,after,cid,device_ids):
    """Keep saved analog placement through resizing before attached-route repair.

    Unconstrained devices retain the generator's origin convention. A half-grid
    center change cannot be hidden by rounding; the user must change dimensions.
    """
    c=next(c for c in before['cells'] if c['id']==cid)
    members={did for row in c.get('analog_constraints',[]) for did in row['members']}
    moved=[]
    for did in sorted(members & set(device_ids)):
        try: old=footprint(before,cid,did)[2];new=footprint(after,cid,did)[2]
        except ValueError:continue  # Missing/orphaned members remain explicit findings.
        dx,dy=old[0]-new[0],old[1]-new[1]
        if dx or dy:
            move_device(after,cid,did,dx,dy);moved.append({'device_id':did,'delta_nm':[dx,dy]})
    return moved


def move_device(p,cid,did,dx,dy):
    c=next(c for c in p['cells'] if c['id']==cid)
    if any(v%p['pdk']['grid'] for v in (dx,dy)):raise ValueError('Constraint placement would leave the grid. Adjust dimensions or axis.')
    dx,dy=int(dx),int(dy)
    from .layout_arrange import translated_cell
    ids={s['id'] for s in c['shapes'] if s.get('device_id')==did}
    ids.update(i['id'] for i in c.get('layout_instances',[]) if i.get('device_id')==did)
    c.update(translated_cell(c,{ident:(dx,dy) for ident in ids}))


def arrange(p,cid,row,pitch=10000,columns=None):
    """Atomic placement; every group receives point-symmetric unit pairs."""
    q=clone(p)
    _arrange(q,cid,row,pitch,columns)
    from .model import validate
    validate(q)
    from .route_constraints import enforce_affected
    enforce_affected(p,q,[cid])
    p.clear();p.update(q)


def _arrange(p,cid,row,pitch,columns):
    validate_constraints({**p,'cells':[dict(next(c for c in p['cells'] if c['id']==cid),analog_constraints=[row])]})
    if not isinstance(pitch,(int,float)) or not math.isfinite(pitch) or pitch<=0 or pitch%p['pdk']['grid']:
        raise ValueError('Use a positive pitch on the technology grid.')
    kind=row['kind'];axis=0 if row.get('axis','x')=='x' else 1;coordinate=row.get('coordinate',0)
    if kind=='symmetry':
        a,b=[footprint(p,cid,did)[2] for did in row['members']];target=list(a);target[axis]=2*coordinate-a[axis];move_device(p,cid,row['members'][1],target[0]-b[0],target[1]-b[1])
    elif kind=='common_centroid':
        groups=row['groups']
        if len(groups)<2 or any(len(g)%2 for g in groups):raise ValueError('Automatic common-centroid placement requires at least two groups with an even number of explicit unit devices in each.')
        count=sum(map(len,groups));columns=count if columns is None else columns
        if type(columns)!=int or columns<2 or columns>count or columns%2:raise ValueError('Use an even column count between 2 and the number of unit devices.')
        height=math.ceil(count/columns)
        points=[((x-(columns-1)/2)*pitch,(y-(height-1)/2)*pitch) for y in range(height) for x in range(columns//2)]
        points.sort(key=lambda pt:(pt[0]**2+pt[1]**2,pt[1],pt[0]))
        pairs=[]
        for i in range(max(map(len,groups))//2):
            pairs.extend((g[2*i],g[2*i+1]) for g in groups if 2*i<len(g))
        for (first,second),(x,y) in zip(pairs,points):
            for did,target in ((first,[x,y]),(second,[-x,-y])):
                target[axis]+=coordinate;center=footprint(p,cid,did)[2]
                move_device(p,cid,did,target[0]-center[0],target[1]-center[1])
    else:raise ValueError('This constraint checks geometry; use the device generator to correct matching or guard coverage.')
    boxes=[footprint(p,cid,did)[1] for did in row['members']]
    if any(a.left<b.right and b.left<a.right and a.bottom<b.top and b.bottom<a.top for i,a in enumerate(boxes) for b in boxes[i+1:]):
        raise ValueError('The arranged footprints overlap. Increase the pitch or adjust the symmetry axis.')
