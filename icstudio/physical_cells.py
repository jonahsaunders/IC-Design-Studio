"""Named physical cell interfaces and schematic-linked hierarchy."""
from .model import clone,uid,digest,scalar
from .layout import kdb,polygon


def reachable(p,cid,physical=False):
    by={c['id']:c for c in p['cells']};seen=set();order=[]
    def visit(key):
        if key in seen:return
        seen.add(key)
        for i in by[key].get('layout_instances',[]) if physical else by[key]['devices']:
            if physical or i['kind']=='X':visit(i['cell'])
        order.append(key)
    visit(cid);return order


def ports(p,cid):
    c=next(c for c in p['cells'] if c['id']==cid)
    if 'layout_ports' in c:return clone(c['layout_ports'])
    return infer_ports(p,c)


def infer_ports(p,c):
    from .process_adapters import layer_datatypes
    drawing_type, _, port_types = layer_datatypes(p['pdk'])
    ls=p['pdk']['layers'];byname={l['name']:l for l in ls};result=[]
    for text in c.get('layout_texts',[]):
        l=byname[text['layer']];drawing=next((n['name'] for n in ls if n['gds']==l['gds'] and n['datatype']==drawing_type),None)
        if text['text'] in c['ports'] and l['datatype'] in port_types and drawing:
            port={'name':text['text'],'layer':drawing,'point':[text['x'],text['y']]}
            if port not in result:result.append(port)
    return result


def transform(inst):
    return kdb().ICplxTrans(1,inst.get('rotation',0),inst.get('mirror',False),inst['x'],inst['y'])


def instance_pins(p,cid):
    c=next(c for c in p['cells'] if c['id']==cid);ds={d['id']:d for d in c['devices']};result=[]
    for i in c.get('layout_instances',[]):
        d=ds.get(i.get('device_id'))
        if not d or d['kind']!='X' or d['cell']!=i['cell']:continue
        tr=transform(i)
        for pin in ports(p,i['cell']):
            if pin['name'] not in d['nets']:continue
            pt=tr*kdb().Point(*pin['point']);result.append({'id':i['id']+'_'+pin['name'],'device_id':d['id'],'pin':pin['name'],'layer':pin['layer'],'point':[pt.x,pt.y],'instance_id':i['id']})
    return result


def terminals(p,cid):
    c=next(c for c in p['cells'] if c['id']==cid);automatic=instance_pins(p,cid);keys={(i['device_id'],i['pin']) for i in automatic}
    return [pin for pin in c.get('layout_pins',[]) if (pin['device_id'],pin['pin']) not in keys]+automatic


def place(p,cid,did,x,y,rotation=0,mirror=False):
    c=next(c for c in p['cells'] if c['id']==cid);d=next(d for d in c['devices'] if d['id']==did)
    if d['kind']!='X':raise ValueError('Select a schematic cell instance.')
    child=next(c for c in p['cells'] if c['id']==d['cell'])
    if not child['shapes'] and not child.get('layout_instances'):raise ValueError('Create the child cell layout before placing it.')
    if {r['name'] for r in ports(p,child['id'])}!=set(child['ports']):raise ValueError('Assign every child cell layout port before placement.')
    if any(i.get('device_id')==did for i in c.get('layout_instances',[])):raise ValueError('This schematic instance already has a physical placement.')
    grid=p['pdk']['grid']
    if any(type(v) is not int or v%grid for v in (x,y)):raise ValueError('Place cells on the project layout grid.')
    i={'id':uid(),'name':d['name'],'cell':d['cell'],'device_id':did,'x':x,'y':y,'rotation':rotation,'mirror':mirror,'nx':1,'ny':1}
    c.setdefault('layout_instances',[]).append(i);return i


def assign_port(p,cid,name,layer,point):
    c=next(c for c in p['cells'] if c['id']==cid);ls=p['pdk']['layers'];source=next(l for l in ls if l['name']==layer)
    if name not in c['ports']:raise ValueError('Choose a declared cell port.')
    from .process_adapters import layer_datatypes
    _, label_type, _ = layer_datatypes(p['pdk'])
    label=next((l['name'] for l in ls if l['gds']==source['gds'] and l['datatype']==label_type),None)
    if not label:raise ValueError('This layer has no mapped process port-label datatype '+str(label_type)+'.')
    c['layout_ports']=[r for r in ports(p,cid) if r['name']!=name]+[{'name':name,'layer':layer,'point':point}]
    c['layout_texts']=[t for t in c.get('layout_texts',[]) if t['text']!=name]+[{'layer':label,'text':name,'x':point[0],'y':point[1],'rotation':0}];c['layout_label_mode']='explicit'


def audit(p,cid):
    from .process_adapters import audit as device_audit
    from .design_ops import parameters,value
    by={c['id']:c for c in p['cells']};issues=[]
    def issue(code,cell,obj,message):issues.append({'severity':'error','code':code,'cell_id':cell,'object':obj,'message':by[cell]['name']+': '+message,'fingerprint':digest([code,cell,obj,message])})
    for key in reachable(p,cid):
        c=by[key]
        for found in device_audit(p,key):issues.append({**found,'cell_id':key})
        from .analog_layout import matching_findings
        issues.extend(matching_findings(p,key))
        if not c['shapes'] and not c.get('layout_instances'):issue('LAYOUT.EMPTY',key,'','Circuit cell has no physical implementation.')
        physical=ports(p,key)
        if len(physical)!=len(c['ports']) or {i['name'] for i in physical}!=set(c['ports']):issue('LAYOUT.PORTS',key,'','Physical port names must match the electrical interface.')
        ds={d['id']:d for d in c['devices']};seen=set();context=parameters(c.get('parameters',{}),parameters(p.get('parameters',{})))
        for i in c.get('layout_instances',[]):
            d=ds.get(i.get('device_id'))
            if not d and not by[i['cell']]['devices']:continue
            if not d or d['kind']!='X' or d['cell']!=i['cell']:issue('LAYOUT.UNLINKED',key,i['id'],'Link physical placement '+i['name']+' to its matching schematic cell instance.');continue
            if d['id'] in seen:issue('LAYOUT.DUPLICATE',key,i['id'],'More than one physical placement is linked to '+d['name']+'.')
            seen.add(d['id'])
            if i.get('nx',1)!=1 or i.get('ny',1)!=1:issue('LAYOUT.ARRAY',key,i['id'],'A linked electrical instance needs one physical placement; instantiate electrical arrays explicitly.')
            child=by[d['cell']];defaults=parameters(child.get('parameters',{}),parameters(p.get('parameters',{})))
            if any(value(v,context)!=defaults[k] for k,v in d.get('parameters',{}).items()):issue('LAYOUT.PARAMETERS',key,i['id'],'Instance overrides differ from the shared physical cell. Create a concrete cell variant.')
        for d in c['devices']:
            if d['kind']=='X' and d['id'] not in seen:issue('LAYOUT.MISSING',key,d['id'],'Place the physical cell for '+d['name']+'.')
    return issues


def transform_selection(p,cid,ids,dx=0,dy=0,rotation=0,mirror=False,pivot=(0,0),include_annotations=False):
    """Transform selected geometry or whole linked cell instances in one transaction."""
    db=kdb();c=next(c for c in p['cells'] if c['id']==cid);chosen=set(ids);grid=p['pdk']['grid']
    if rotation not in (0,90,180,270) or any(type(v) is not int or v%grid for v in (dx,dy,*pivot)):raise ValueError('Transforms require right angles and grid-aligned coordinates.')
    tr=db.ICplxTrans(1,0,False,pivot[0]+dx,pivot[1]+dy)*db.ICplxTrans(1,rotation,mirror,0,0)*db.ICplxTrans(1,0,False,-pivot[0],-pivot[1])
    def point(pt):v=tr*db.Point(*pt);return [v.x,v.y]
    moved={s['id'] for s in c['shapes'] if s['id'] in chosen}
    # Annotation movement is explicit and applies only to a complete cell layout.
    # This prevents a partial wire edit from moving an unrelated port marker.
    if include_annotations:
        objects={s['id'] for s in c['shapes']}|{i['id'] for i in c.get('layout_instances',[])}
        if not objects or not objects <= chosen:
            raise ValueError('Select all cell shapes and physical instances to move named ports and labels together.')
        c['layout_ports']=ports(p,cid)
        for port in c['layout_ports']:port['point']=point(port['point'])
        for text in c.get('layout_texts',[]):
            text['x'],text['y']=point([text['x'],text['y']])
            text['rotation']=(rotation+(-text.get('rotation',0) if mirror else text.get('rotation',0)))%360
        for pin in c.get('layout_pins',[]):pin['point']=point(pin['point'])
    for s in c['shapes']:
        if s['id'] in chosen:
            s['points']=[point(pt) for pt in s['points']];s['holes']=[[point(pt) for pt in h] for h in s.get('holes',[])]
    for i in c.get('layout_instances',[]):
        if i['id'] in chosen:
            result=tr*transform(i);i.update(x=result.disp.x,y=result.disp.y,rotation=round(result.angle)%360,mirror=result.is_mirror())
            linear=db.ICplxTrans(1,rotation,mirror,0,0)
            for key,default in (('a',[i.get('dx',0),0]),('b',[0,i.get('dy',0)])):
                v=linear*db.Vector(*i.get(key,default));i[key]=[v.x,v.y]
    # Assigned terminals follow a complete selected footprint. Partial edits remain
    # explicit geometry edits and are checked against stationary terminal markers.
    for record in c.get('pdk_layouts',[]):
        shapes=[s for s in c['shapes'] if s.get('generated_device')==record['device_id']]
        if shapes and all(s['id'] in moved for s in shapes):
            if not include_annotations:
                for pin in c.get('layout_pins',[]):
                    if pin['device_id']==record['device_id']:pin['point']=point(pin['point'])
            record['origin']=point(record['origin'])
            if rotation or mirror:record['transformed']=True
    return p
