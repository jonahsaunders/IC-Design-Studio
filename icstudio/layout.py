from __future__ import annotations
from .model import uid,clone,digest

def kdb():
    import klayout.db as db
    return db

def polygon(s):
    db=kdb();pts=[db.Point(*pt) for pt in s['points']]
    if s['kind']=='rect': return db.Polygon(db.Box(pts[0],pts[1]))
    if s['kind']=='path': return db.Path(pts,s['width']).polygon()
    p=db.Polygon(pts)
    for hole in s.get('holes',[]): p.insert_hole([db.Point(*v) for v in hole])
    return p

def shape_from_polygon(poly,layer,net='',device_id=''):
    return {'id':uid(),'kind':'polygon','layer':layer,'points':[[p.x,p.y] for p in poly.each_point_hull()],
            'holes':[[[p.x,p.y] for p in poly.each_point_hole(i)] for i in range(poly.holes())],'net':net,'device_id':device_id}

def boolean(shapes,operation):
    if len(shapes)<2: raise ValueError('Select at least two shapes (Ctrl+click).')
    if len({s['layer'] for s in shapes})!=1: raise ValueError('Boolean operations require one layer.')
    if len({s.get('net','') for s in shapes})>1: raise ValueError('Boolean operations cannot merge different net labels.')
    db=kdb();r=db.Region(polygon(shapes[0]))
    for s in shapes[1:]:
        other=db.Region(polygon(s))
        if operation=='union': r=r|other
        elif operation=='subtract': r=r-other
        elif operation=='intersection': r=r&other
        elif operation=='xor': r=r^other
        else: raise ValueError('Unsupported Boolean operation.')
    r.merge();return [shape_from_polygon(p,shapes[0]['layer'],shapes[0].get('net',''),shapes[0].get('device_id','')) for p in r.each()]

def rect(layer,x,y,w,h,device_id='',net=''):
    return {'id':uid(),'kind':'rect','layer':layer,'points':[[int(x),int(y)],[int(x+w),int(y+h)]],'device_id':device_id,'net':net}

def generate_mos(d,x=0,y=0,fingers=1):
    from .model import scalar
    w=max(400,round(scalar(d['params']['w'])*1e9/5)*5);l=max(150,round(scalar(d['params']['l'])*1e9/5)*5)
    if not 1<=fingers<=64 or w>1000000 or l>1000000: raise ValueError('Generator size limit exceeded.')
    out=[];ref=d['id'];nets=d['nets'];pitch=l+800
    if d['kind']=='PMOS': out.append(rect('nwell',x-500,y-700,fingers*pitch+1500,w+1400,ref,nets['b']))
    out.append(rect('active',x,y,fingers*pitch+500,w,ref))
    for i in range(fingers):
        xx=x+500+i*pitch;out.append(rect('poly',xx,y-300,l,w+600,ref,nets['g']))
    for i in range(fingers+1):
        xx=x+150+i*pitch;net=nets['s'] if i%2==0 else nets['d'];out.extend([rect('metal1',xx-60,y-100,270,w+200,ref,net),rect('contact',xx,y+100,150,150,ref,net)])
    return out

def guard_ring(x,y,w,h,thickness=300,net='0'):
    if w<=2*thickness or h<=2*thickness: raise ValueError('Ring outer size must exceed twice its thickness.')
    return [rect('metal1',x,y,w,thickness,net=net),rect('metal1',x,y+h-thickness,w,thickness,net=net),rect('metal1',x,y+thickness,thickness,h-2*thickness,net=net),rect('metal1',x+w-thickness,y+thickness,thickness,h-2*thickness,net=net)]

def drc(p,cid):
    db=kdb();cell=next(c for c in p['cells'] if c['id']==cid)
    from .design_ops import flatten_layout
    cell={**cell,'shapes':flatten_layout(p,cid)};issues=[];grid=p['pdk']['grid']
    for s in cell['shapes']:
        if any(v%grid for pt in s['points'] for v in pt): issues.append({'severity':'error','code':'GRID','object':s['id'],'message':f'{s["layer"]}: vertex is off the {grid} nm grid.','bbox':list(polygon(s).bbox().to_s()) if False else None})
        if polygon(s).area()==0: issues.append({'severity':'error','code':'ZERO_AREA','object':s['id'],'message':'Shape has zero area.'})
    for layer in p['pdk']['layers']:
        shapes=[s for s in cell['shapes'] if s['layer']==layer['name']];r=db.Region()
        for s in shapes:r.insert(polygon(s))
        r.merge()
        for code,checks in [('WIDTH',r.width_check(layer['width'])),('SPACE',r.space_check(layer['space']))]:
            for pair in checks.each():
                box=pair.bbox();ref=next((s['id'] for s in shapes if polygon(s).bbox().touches(box)),'')
                issues.append({'severity':'error','code':code,'object':ref,'message':f'{layer["name"]}: {code.lower()} below {layer["width" if code=="WIDTH" else "space"]} nm.','bbox':[box.left,box.bottom,box.right,box.top]})
                if len(issues)>2000: raise ValueError('More than 2,000 violations. Fix coarse geometry first.')
    for i in issues:i['fingerprint']=digest({'revision':p['revision'],'rule':i['code'],'object':i['object'],'bbox':i.get('bbox')})
    return issues

def mapping_audit(p,cid):
    c=next(c for c in p['cells'] if c['id']==cid);refs={s.get('device_id') for s in c['shapes']};ids={d['id'] for d in c['devices']};issues=[]
    for d in c['devices']:
        if d['kind'] in ('NMOS','PMOS','R','C','L') and d['id'] not in refs:issues.append({'severity':'warning','code':'MAPPING','object':d['id'],'message':f'{d["name"]}: no linked layout geometry.'})
    for s in c['shapes']:
        if s.get('device_id') and s['device_id'] not in ids:issues.append({'severity':'error','code':'ORPHAN','object':s['id'],'message':'Shape refers to a missing device.'})
    return issues
