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
    from .native_vectors import ports as electrical_ports
    drawing_type, _, port_types = layer_datatypes(p['pdk'])
    ls=p['pdk']['layers'];byname={l['name']:l for l in ls};result=[]
    port_layers=p['pdk'].get('interoperability',{}).get('port_layers',{})
    for text in c.get('layout_texts',[]):
        l=byname[text['layer']];drawing=next((name for name,label in port_layers.items() if label==text['layer']),None) or next((n['name'] for n in ls if n['gds']==l['gds'] and n['datatype']==drawing_type),None)
        if text['text'] in electrical_ports(c['ports']) and (text['layer'] in port_layers.values() or l['datatype'] in port_types) and drawing:
            port={'name':text['text'],'layer':drawing,'point':[text['x'],text['y']]}
            if port not in result:result.append(port)
    return result


def transform(inst):
    return kdb().ICplxTrans(1,inst.get('rotation',0),inst.get('mirror',False),inst['x'],inst['y'])


def instance_pins(p,cid):
    from .native_vectors import expand_device
    c=next(c for c in p['cells'] if c['id']==cid);ds={d['id']:d for d in c['devices']};result=[]
    for i in c.get('layout_instances',[]):
        d=ds.get(i.get('device_id'))
        if not d or d['kind']!='X' or d['cell']!=i['cell']:continue
        # Keep unresolved arrays viewable so the editor can offer explicit
        # materialization. audit() blocks verification; one compact symbol must
        # never masquerade as one valid set of physical member terminals.
        if d.get('array'):continue
        d=expand_device(d,p)[0]
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
    if d.get('array'):raise ValueError('Materialize electrical array members before placing their physical cells.')
    if rotation not in (0,90,180,270) or type(mirror) is not bool:raise ValueError('Physical placement requires a right-angle rotation and a boolean mirror flag.')
    # Stage specialization and regeneration before changing the live project.
    # A failed recipe or unsafe route update leaves both hierarchy and placement
    # untouched, including when place() is used outside a History transaction.
    from .design_ops import parameters, value
    child=next(c for c in p['cells'] if c['id']==d['cell'])
    global_=parameters(p.get('parameters',{}));context=parameters(c.get('parameters',{}),global_)
    defaults=parameters(child.get('parameters',{}),global_)
    actual=parameters({**child.get('parameters',{}),**{k:value(v,context) for k,v in d.get('parameters',{}).items()}},global_)
    if actual!=defaults:
        from .physical_variants import materialize
        from .model import validate
        q,_=materialize(p,cid,{did})
        result=place(q,cid,did,x,y,rotation,mirror)
        validate(q);p.clear();p.update(q)
        return result
    child=next(c for c in p['cells'] if c['id']==d['cell'])
    if not child['shapes'] and not child.get('layout_instances'):raise ValueError('Create the child cell layout before placing it.')
    from .native_vectors import ports as electrical_ports
    if {r['name'] for r in ports(p,child['id'])}!=set(electrical_ports(child['ports'])):raise ValueError('Assign every child cell layout port before placement.')
    if any(i.get('device_id')==did for i in c.get('layout_instances',[])):raise ValueError('This schematic instance already has a physical placement.')
    grid=p['pdk']['grid']
    if any(type(v) is not int or v%grid for v in (x,y)):raise ValueError('Place cells on the project layout grid.')
    i={'id':uid(),'name':d['name'],'cell':d['cell'],'device_id':did,'x':x,'y':y,'rotation':rotation,'mirror':mirror,'nx':1,'ny':1}
    c.setdefault('layout_instances',[]).append(i);return i


def assign_port(p,cid,name,layer,point):
    c=next(c for c in p['cells'] if c['id']==cid);ls=p['pdk']['layers'];source=next(l for l in ls if l['name']==layer)
    from .native_vectors import ports as electrical_ports
    if name not in electrical_ports(c['ports']):raise ValueError('Choose a declared scalar cell port.')
    from .process_adapters import layer_datatypes
    _, label_type, _ = layer_datatypes(p['pdk'])
    label=p['pdk'].get('interoperability',{}).get('port_layers',{}).get(layer) or next((l['name'] for l in ls if l['gds']==source['gds'] and l['datatype']==label_type),None)
    if not label:raise ValueError('This layer has no mapped process port-label datatype '+str(label_type)+'.')
    c['layout_ports']=[r for r in ports(p,cid) if r['name']!=name]+[{'name':name,'layer':layer,'point':point}]
    c['layout_texts']=[t for t in c.get('layout_texts',[]) if t['text']!=name]+[{'layer':label,'text':name,'x':point[0],'y':point[1],'rotation':0}];c['layout_label_mode']='explicit'


def audit(p,cid):
    from .process_adapters import audit as device_audit
    from .design_ops import parameters,value
    from .native_vectors import ports as electrical_ports
    by={c['id']:c for c in p['cells']};issues=[]
    def issue(code,cell,obj,message):issues.append({'severity':'error','code':code,'cell_id':cell,'object':obj,'message':by[cell]['name']+': '+message,'fingerprint':digest([code,cell,obj,message])})
    for key in reachable(p,cid):
        c=by[key]
        for found in device_audit(p,key):issues.append({**found,'cell_id':key})
        from .analog_layout import matching_findings
        issues.extend(matching_findings(p,key))
        if not c['shapes'] and not c.get('layout_instances'):issue('LAYOUT.EMPTY',key,'','Circuit cell has no physical implementation.')
        physical=ports(p,key)
        expected=electrical_ports(c['ports'])
        if len(physical)!=len(expected) or {i['name'] for i in physical}!=set(expected):issue('LAYOUT.PORTS',key,'','Physical port names must match the scalar electrical interface.')
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
            if d.get('array'):issue('LAYOUT.ARRAY',key,d['id'],'Materialize the compact electrical array into individually linked members before verification.')
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
            if (rotation or mirror) and (not record.get('transformed') or 'orientation' in record):
                old=record.get('orientation',{'rotation':0,'mirror':False})
                orientation=db.ICplxTrans(1,rotation,mirror,0,0)*db.ICplxTrans(1,old['rotation'],old['mirror'],0,0)
                record['orientation']={'rotation':round(orientation.angle)%360,'mirror':orientation.is_mirror()}
                record['transformed']=True
    return p


def materialize_array(p, cid, did, *, nx=None, ny=None, a=None, b=None):
    """Atomically replace a compact array with stable, independently linked cells.

    Member order follows the declared electrical range. Physical placement is
    row-major, with a/b vectors in parent coordinates; each member retains the
    template rotation/mirror. Unplaced arrays stay unplaced. Capture wires and
    labels are retained with explicit names while member symbols are arranged
    clear of the original capture geometry.
    """
    from .model import validate
    from .native_vectors import expand_device, signals
    from .physical_variants import electrical_signature, materialize
    q=clone(p); c=next(cell for cell in q['cells'] if cell['id']==cid)
    source=next(d for d in c['devices'] if d['id']==did)
    if source.get('array') is None:raise ValueError('Choose a compact electrical instance array.')
    before=electrical_signature(p,cid);members=clone(expand_device(source,q));count=len(members)
    placements=[i for i in c.get('layout_instances',[]) if i.get('device_id')==did]
    if len(placements)>1:raise ValueError('Resolve duplicate physical placements before materializing this array.')
    if any(s.get('device_id')==did or s.get('generated_device')==did for s in c['shapes']) or any(v.get('device_id')==did for key in ('layout_pins','parametric_devices','pdk_layouts') for v in c.get(key,[])):
        raise ValueError('Regenerate primitive array footprints per member; a shared generated footprint cannot be expanded as a linked cell.')
    if placements and source['kind']!='X':raise ValueError('Only hierarchical cell arrays can expand linked physical placements.')
    if any(t.get('dut_instance')==did for t in q.get('testbenches',[])):
        raise ValueError('Select an individual DUT member in the saved testbench before materializing its array.')
    # Capture keeps the original terminal grouping even when a child exposes a
    # vector interface; consumers expand those named groups into scalar pins.
    for member in members:
        nets=member['nets']
        member['nets']={pin:','.join(nets[name] for name in signals(pin)) if source['kind'] in ('X','SPICE','XS') else nets[pin] for pin in source['nets']}
        member['net_labels']=clone(member['nets'])
    if 'wires' in c:
        from .wiring import pins
        old_positions=pins(c,q)
        for label in c.get('labels',[]):
            anchor=label['anchor']
            if anchor['kind']=='pin' and anchor['id']==did:
                label['anchor']={'kind':'point','point':old_positions[(did,anchor['pin'])]}
        for wire in c['wires']:
            c.setdefault('labels',[]).append({'id':'arraylabel_'+digest([did,wire['id']])[:24],
                'kind':'net_label','name':wire['net'],'anchor':{'kind':'wire','id':wire['id'],'point':clone(wire['points'][0])},'offset':[10,-12],'rotation':0})
        touched=set(source['nets'].values())
        for other in c['devices']:
            if other['id']!=did:
                other.setdefault('net_labels',{}).update({pin:net for pin,net in other['nets'].items() if net in touched})
        # Prepared members enter through the same editor transaction as other
        # new symbols, whose implicit pin labels are intentionally cleared.
        # Explicit anchored labels preserve this reviewed array connectivity.
        for member in members:
            for pin,net in member['nets'].items():
                c.setdefault('labels',[]).append({'id':'arraypin_'+digest([member['id'],pin])[:24],
                    'kind':'net_label','name':net,'anchor':{'kind':'pin','id':member['id'],'pin':pin},
                    'offset':[10,-12],'rotation':0})
    # Leave all retained wire geometry clear, including free labels far from a
    # symbol. This avoids silently joining two member pins during rebuild.
    coordinates=[(d['x'],d['y']) for d in c['devices']]
    coordinates += [point for w in c.get('wires',[]) for point in w['points']]
    coordinates += [label['anchor']['point'] for label in c.get('labels',[]) if label['anchor']['kind'] in ('point','wire')]
    right=max(x for x,y in coordinates)+400; baseline=max(y for x,y in coordinates)+300
    for index,member in enumerate(members):member.update(x=right+index*240,y=baseline)
    offset=c['devices'].index(source);c['devices'][offset:offset+1]=members
    created=[]
    if placements:
        template=placements[0]
        columns=nx if nx is not None else template.get('nx',1) if template.get('nx',1)*template.get('ny',1)>1 else count
        rows=ny if ny is not None else template.get('ny',1) if nx is None and template.get('nx',1)*template.get('ny',1)>1 else 1
        if type(columns) is not int or type(rows) is not int or min(columns,rows)<1 or columns*rows!=count:
            raise ValueError('The physical array row/column product must equal its electrical member count.')
        av=a if a is not None else template.get('a',[template.get('dx',20000),0])
        bv=b if b is not None else template.get('b',[0,template.get('dy',20000)])
        grid=q['pdk']['grid']
        if any(not isinstance(vector,(list,tuple)) or len(vector)!=2 or any(type(v) is not int or v%grid for v in vector) for vector in (av,bv)):
            raise ValueError('Electrical array placement vectors must be integer points on the layout grid.')
        seen=set()
        for index,member in enumerate(members):
            column,row=index%columns,index//columns
            point=(template['x']+column*av[0]+row*bv[0],template['y']+column*av[1]+row*bv[1])
            if point in seen:raise ValueError('Array placement vectors must give every member a distinct origin.')
            seen.add(point);inst=clone(template)
            inst.update(id='arrayinst_'+digest([template['id'],member['array_index']])[:24],name=member['name'],device_id=member['id'],x=point[0],y=point[1],nx=1,ny=1,array_source_id=did,array_index=member['array_index'])
            for key in ('a','b','dx','dy'):inst.pop(key,None)
            created.append(inst)
        c['layout_instances']=[i for i in c['layout_instances'] if i.get('device_id')!=did]+created
    validate(q)
    if placements:q,_=materialize(q,cid,{d['id'] for d in members})
    validate(q)
    if electrical_signature(q,cid)!=before:raise ValueError('Array materialization changed the resolved circuit; the candidate was rejected.')
    p.clear();p.update(q)
    return {'cell_id':cid,'source_device_id':did,'members':[{'id':d['id'],'name':d['name'],'index':d['array_index']} for d in members], 'placements':len(created)}
