"""Native editor transactions; all geometry uses integer nanometres."""
from .model import clone, uid, validate, NET
from .layout import polygon, shape_from_polygon, kdb
from .physical_cells import transform_selection


def cell(p, cid):
    return next(c for c in p['cells'] if c['id'] == cid)


def local_shapes(p, cid, ids, locked=()):
    c=cell(p,cid);by={s['id']:s for s in c['shapes']}
    if not ids or not set(ids)<=by.keys():raise ValueError('Select local shapes. Enter a cell to edit its geometry.')
    rows=[by[i] for i in ids]
    if any(s['layer'] in locked for s in rows):raise ValueError('Unlock the selected layers before editing.')
    return rows


def grid(p, *values):
    if any(type(v) is not int or v%p['pdk']['grid'] for v in values):raise ValueError('Use coordinates on the project grid.')


def replace_geometry(p,cid,ids,operation,amount=0,box=None,locked=()):
    rows=local_shapes(p,cid,ids,locked);out=[];db=kdb()
    if operation=='size':grid(p,amount)
    if operation=='chop':
        if not box or len(box)!=4:raise ValueError('Choose a rectangular chop area.')
        grid(p,*box)
        if box[0]>=box[2] or box[1]>=box[3]:raise ValueError('Chop area must have positive width and height.')
    if operation not in ('size','chop'):raise ValueError('Unknown geometry operation.')
    for s in rows:
        region=db.Region(polygon(s))
        result=region.sized(amount) if operation=='size' else region-db.Region(db.Box(*box))
        if operation=='size' and result.is_empty():raise ValueError('Sizing would remove an entire shape. Use Delete explicitly.')
        for poly in result.each():
            new=shape_from_polygon(poly,s['layer'],s.get('net',''),s.get('device_id',''))
            for key in ('generated_device','generated_route','via_group'):
                if key in s:new[key]=s[key]
            out.append(new)
    c=cell(p,cid);c['shapes']=[s for s in c['shapes'] if s['id'] not in ids]+out;validate(p)
    return [s['id'] for s in out]


def move_vertex(p,cid,sid,index,point,edge=False,locked=()):
    s=local_shapes(p,cid,[sid],locked)[0];grid(p,*point);q=clone(s)
    if s.get('holes'):raise ValueError('Use polygon operations for shapes containing holes.')
    pts=q['points']
    if q['kind']=='rect':
        (x1,y1),(x2,y2)=pts;pts=[[x1,y1],[x2,y1],[x2,y2],[x1,y2]];q['kind']='polygon'
    if not 0<=index<len(pts):raise ValueError('Choose a visible vertex or edge.')
    if edge:
        j=(index+1)%len(pts)
        if s['kind']=='path' and index==len(pts)-1:raise ValueError('Choose an existing edge.')
        a,b=pts[index],pts[j]
        if a[0]!=b[0] and a[1]!=b[1]:raise ValueError('Edge stretch currently requires a Manhattan edge.')
        axis=1 if a[1]==b[1] else 0
        pts[index][axis]=point[axis];pts[j][axis]=point[axis]
    else:pts[index]=list(point)
    if any(a==b for a,b in zip(pts,pts[1:])):raise ValueError('This edit collapses an edge.')
    q['points']=pts;poly=polygon(q)
    if poly.area()<=0:raise ValueError('This edit collapses the geometry.')
    # Reject crossing boundaries; a geometrically normalized region must preserve area.
    if kdb().Region(poly).merged().area()!=poly.area():raise ValueError('This edit creates a self-intersecting boundary.')
    s.update(q);validate(p)


def properties(p,cid,ids,layer=None,net=None,width=None,locked=()):
    rows=local_shapes(p,cid,ids,locked)
    if layer is not None:
        if layer not in {l['name'] for l in p['pdk']['layers']}:raise ValueError('Choose an existing layer.')
        if layer in locked:raise ValueError('Unlock the target layer.')
    if net is not None and net and not NET.fullmatch(net):raise ValueError('Use a valid net name.')
    if width is not None:
        grid(p,width)
        if width<=0 or any(s['kind']!='path' for s in rows):raise ValueError('Positive path width applies only to paths.')
    for s in rows:
        if layer is not None:s['layer']=layer
        if net is not None:s['net']=net
        if width is not None:s['width']=width
    validate(p)


def copy_selection(p,cid,ids,dx,dy,locked=()):
    from .layout_edit import selection_groups
    selection_groups(p,cid,ids,locked);grid(p,dx,dy);c=cell(p,cid);out=[];groups={}
    if any(s.get('generated_device') for s in c['shapes'] if s['id'] in ids):
        raise ValueError('Copy the schematic device and generate its layout to preserve electrical identity.')
    for s in list(c['shapes']):
        if s['id'] in ids:
            q=clone(s);q['id']=uid();q['device_id']=''
            if q.get('via_group'):q['via_group']=groups.setdefault(q['via_group'],uid())
            c['shapes'].append(q);out.append(q['id'])
    for inst in list(c.get('layout_instances',[])):
        if inst['id'] in ids:
            if inst.get('device_id'):raise ValueError('Duplicate linked instances from the schematic first.')
            q=clone(inst);q['id']=uid();q['name']=inst['name']+'_copy_'+q['id'][:4];c['layout_instances'].append(q);out.append(q['id'])
    transform_selection(p,cid,out,dx,dy);validate(p);return out


def make_variant(p,cid,instance_id,name):
    c=cell(p,cid);inst=next(i for i in c.get('layout_instances',[]) if i['id']==instance_id)
    if any(x['name']==name for x in p['cells']):raise ValueError('Choose a unique cell name.')
    source=cell(p,inst['cell']);q=clone(source);mapping={source['id']:uid()}
    def scan(obj):
        if isinstance(obj,dict):
            if 'id' in obj:mapping.setdefault(obj['id'],uid())
            for v in obj.values():scan(v)
        elif isinstance(obj,list):
            for v in obj:scan(v)
    scan(q)
    def remap(obj):
        if isinstance(obj,dict):return {k:remap(v) for k,v in obj.items()}
        if isinstance(obj,list):return [remap(v) for v in obj]
        return mapping.get(obj,obj) if isinstance(obj,str) else obj
    q=remap(q);q['name']=name;inst['cell']=q['id']
    d=next((d for d in c['devices'] if d['id']==inst.get('device_id')),None)
    if d:d['cell']=q['id']
    p['cells'].append(q);validate(p);return q['id']


def flatten_instances(p,cid,ids,locked=()):
    from .design_ops import flatten_layout
    c=cell(p,cid);instances=[i for i in c.get('layout_instances',[]) if i['id'] in ids]
    if len(instances)!=len(ids) or not ids:raise ValueError('Select physical cell instances.')
    if any(i.get('device_id') for i in instances):raise ValueError('Linked circuit instances retain hierarchy. Use a cell variant for independent edits.')
    flat=[s for s in flatten_layout(p,cid) if s['id'] in ids]
    if any(s['layer'] in locked for s in flat):raise ValueError('Unlock every affected layer before flattening.')
    for s in flat:s['id']=uid();s.pop('source_id',None);s.pop('instance_path',None);s['device_id']=''
    c['shapes'].extend(flat);c['layout_instances']=[i for i in c['layout_instances'] if i['id'] not in ids];validate(p)
    return [s['id'] for s in flat]


def resolve_array(p,cid,ident):
    c=cell(p,cid);inst=next(i for i in c.get('layout_instances',[]) if i['id']==ident)
    if inst.get('device_id'):raise ValueError('Electrical arrays require explicit schematic instances.')
    if inst.get('nx',1)*inst.get('ny',1)<=1:raise ValueError('Select an array with more than one element.')
    out=[];a=inst.get('a',[inst.get('dx',0),0]);b=inst.get('b',[0,inst.get('dy',0)])
    for ix in range(inst.get('nx',1)):
        for iy in range(inst.get('ny',1)):
            q=clone(inst);q.update(id=uid(),name=inst['name']+f'_{ix}_{iy}',nx=1,ny=1,x=inst['x']+ix*a[0]+iy*b[0],y=inst['y']+ix*a[1]+iy*b[1]);out.append(q)
    c['layout_instances']=[i for i in c['layout_instances'] if i['id']!=ident]+out;validate(p);return [i['id'] for i in out]
