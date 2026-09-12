"""Square spiral geometry and explicitly declared two-terminal device boundaries.

Inductance is the Mohan current-sheet DC estimate (JSSC 34(10), 1999,
doi:10.1109/4.792620). Leads, substrate loss, Q and resonance are not modeled.
All dimensions are integer nanometres. Export always retains the full winding.
"""
import math

from .model import clone, device, digest, design_digest, scalar, uid, validate, NAME, NET
from .layout import rect, polygon, kdb
from .layout_routing import via_recipes, via_shapes
from .layout_vias import technology, declare_connections

MODEL = 'mohan-current-sheet-square-1'
QUALIFICATION = 'Estimated DC inductance; excludes leads, substrate loss, Q and resonance. Run process DRC and qualified EM/device extraction for fabrication.'


def rules_hash(tech):
    return digest(dict(model=MODEL, grid=tech['grid'],
        layers=[{k:l.get(k) for k in ('name','gds','datatype','width','space')} for l in tech['layers']],
        vias=via_recipes(tech)))


def defaults(p):
    tech=technology(p); recipes=via_recipes(tech)
    if not recipes:
        raise ValueError('This technology has no mapped via stack. Declare routing_vias before creating an inductor.')
    recipe=recipes[-1]; grid=tech['grid']; layers={l['name']:l for l in tech['layers']}
    snap=lambda n:math.ceil(n/(2*grid))*2*grid
    width=snap(max(10000,recipe['pad']*3,layers[recipe['upper']]['width'],layers[recipe['lower']]['width']))
    return dict(kind='inductor',shape='square',turns=3,width=width,
        spacing=snap(max(3000,layers[recipe['upper']]['space'])),inner=snap(80000),
        lead=snap(max(30000,width*2)),via=recipe['name'],metal=recipe['upper'],
        via_rows=2,via_columns=2,rotation=0,mirror=False,x=0,y=0)


def geometry(tech, spec, did='', nets=None):
    """Pure bounded generator; no project edits, solver calls or inferred PDK data."""
    s=clone(spec); grid=tech['grid']; layers={l['name']:l for l in tech['layers']}
    if s.get('kind')!='inductor' or s.get('shape')!='square':
        raise ValueError('Choose the square spiral inductor recipe.')
    for key in ('turns','width','spacing','inner','lead','via_rows','via_columns','rotation','x','y'):
        if type(s.get(key)) is not int:raise ValueError(key+' must be an integer in database units.')
    if not 1<=s['turns']<=32 or not 1<=s['via_rows']<=8 or not 1<=s['via_columns']<=8:
        raise ValueError('Use 1–32 turns and 1–8 via rows/columns.')
    if s['rotation'] not in (0,90,180,270) or type(s.get('mirror')) is not bool:
        raise ValueError('Use a quarter-turn orientation and a boolean mirror setting.')
    if any(s[k]<=0 or s[k]>2000000 or s[k]%(2*grid) for k in ('width','spacing','inner','lead')):
        raise ValueError(f'Dimensions must be positive multiples of {2*grid} nm, at most 2,000 µm.')
    if any(abs(s[k])>100000000 or s[k]%grid for k in ('x','y')):
        raise ValueError('Place the origin on the technology grid within ±100 mm.')
    recipe=next((v for v in via_recipes(tech) if v['name']==s.get('via')),None)
    if not recipe or s.get('metal') not in (recipe['lower'],recipe['upper']):
        raise ValueError('Select a mapped via stack and one of its conductor layers.')
    metal=s['metal']; lower=recipe['lower'] if metal==recipe['upper'] else recipe['upper']
    width=s['width']; spacing=s['spacing']; n=s['turns']; inner=s['inner']; lead=s['lead']
    if width<max(layers[metal]['width'],layers[lower]['width']) or spacing<layers[metal]['space']:
        raise ValueError('Trace width or winding spacing is below the selected layer rules.')
    if inner<max(width,spacing) or lead<width+max(layers[metal]['space'],layers[lower]['space']):
        raise ValueError('The opening must be at least the trace width/spacing; leads need width plus clearance.')
    pitch=width+spacing; outer=inner+2*n*width+2*(n-1)*spacing; radius=(outer-width)//2
    if outer+2*lead>5000000:raise ValueError('The complete inductor must fit within 5 mm.')
    p=[-radius,-radius-lead]; points=[p,[-radius,-radius]]
    for i in range(n):
        left=-radius+i*pitch; right=radius-i*pitch
        points.extend([[right,left],[right,right],[left,right],[left,left+pitch]])
    end=points[-1]; q=[-radius-lead,end[1]]
    via_pitch=math.ceil((recipe['size']+recipe['spacing'])/(2*grid))*2*grid
    if max((s['via_columns']-1)*via_pitch+recipe['pad'],(s['via_rows']-1)*via_pitch+recipe['pad'])>width:
        raise ValueError('The via array does not fit the trace width. Widen the trace or use fewer vias.')
    nets=nets or dict(p='',n=''); shapes=[]
    def add(role, shape):
        shape.update(device_id=did,pcell_role=role);shapes.append(shape)
    def path(role,layer,pts):
        add(role,dict(id=uid(),kind='path',layer=layer,points=clone(pts),width=width,net=''))
    path('body.coil',metal,points);path('body.underpass',lower,[end,q])
    add('body.inner_landing',rect(metal,end[0]-width//2,end[1]-width//2,width,width))
    for terminal,center in (('inner',end),('outer',q)):
        for row in range(s['via_rows']):
            for col in range(s['via_columns']):
                at=[center[0]+(2*col-s['via_columns']+1)*via_pitch//2,
                    center[1]+(2*row-s['via_rows']+1)*via_pitch//2]
                for i,shape in enumerate(via_shapes(recipe,at,nets['n'] if terminal=='outer' else '')):
                    add(('port.n_stack' if terminal=='outer' else 'body.inner_stack')+f'.{row}.{col}.{i}',shape)
    for role,point in (('p',p),('n',q)):
        add('port.'+role,rect(metal,point[0]-width//2,point[1]-width//2,width,width,net=nets[role]))
    def transform(pt):
        x,y=pt
        if s['mirror']:x=-x
        for _ in range(s['rotation']//90):x,y=-y,x
        return [x+s['x'],y+s['y']]
    for shape in shapes:shape['points']=[transform(pt) for pt in shape['points']]
    pins=[dict(id=uid(),device_id=did,pin=role,layer=metal,point=transform(pt)) for role,pt in (('p',p),('n',q))]
    average=(outer+inner)*.5e-9; rho=(outer-inner)/(outer+inner)
    inductance=4*math.pi*1e-7*n*n*average*1.27/2*(math.log(2.07/rho)+.18*rho+.13*rho*rho)
    return dict(shapes=shapes,pins=pins,spec=s,estimate_h=inductance,outer_nm=outer,
        winding_length_nm=sum(abs(a[0]-b[0])+abs(a[1]-b[1]) for a,b in zip(points,points[1:])),
        via_count=2*s['via_rows']*s['via_columns'],model=MODEL,qualification=QUALIFICATION)


def build(p,cid,did,spec):
    from .parametric import electrical_signature
    c=next(c for c in p['cells'] if c['id']==cid);d=next((d for d in c['devices'] if d['id']==did),None)
    if not d or d['kind']!='L' or d.get('native_spice'):
        raise ValueError('Link a standard schematic L device using Tools → Inductor creator.')
    if spec.get('kind')!='inductor':raise ValueError('Use Tools → Inductor creator to define the spiral dimensions first.')
    data=geometry(technology(p),spec,did,d['nets'])
    data['record']=dict(id=uid(),device_id=did,spec=data['spec'],
        electrical=dict(target=scalar(d['value']),realized=data['estimate_h'],unit='H',model=MODEL),
        source_signature=electrical_signature(d),rules_hash=rules_hash(technology(p)),qualification=QUALIFICATION)
    return data


def current_spec(cell,record):
    """Retain a translated footprint's position; reject silent loss of manual edits."""
    from .parametric import geometry_signature
    shapes=[s for s in cell['shapes'] if s.get('pcell_id')==record['id']]
    if geometry_signature(shapes)!=record.get('geometry_signature'):
        raise ValueError('Generated winding geometry was edited. Undo those edits before regenerating it.')
    anchor=next(s for s in shapes if s['pcell_role']==record['reference']['role'])
    old=record['reference']['points'][0];point=anchor['points'][0]
    return {**clone(record['spec']),'x':record['spec']['x']+point[0]-old[0],'y':record['spec']['y']+point[1]-old[1]}


def _recognized(p):
    """Body exclusions require an intact, reproducible recipe and valid terminals."""
    from .parametric import geometry_signature
    found={}; invalid=[]
    for cell in p['cells']:
        for r in cell.get('parametric_devices',[]):
            if r.get('spec',{}).get('kind')!='inductor':continue
            try:
                d=next(d for d in cell['devices'] if d['id']==r['device_id'])
                if d['kind']!='L' or d.get('native_spice'):raise ValueError('Schematic device changed.')
                if r.get('rules_hash')!=rules_hash(technology(p)):raise ValueError('Technology rules changed.')
                spec=current_spec(cell,r);expected=geometry(technology(p),spec,d['id'],d['nets'])
                actual=[s for s in cell['shapes'] if s.get('pcell_id')==r['id']]
                if geometry_signature(actual)!=geometry_signature(expected['shapes']):raise ValueError('Winding differs from its recipe.')
                pins={v['pin']:v for v in cell.get('layout_pins',[]) if v['device_id']==d['id']}
                for v in expected['pins']:
                    if pins.get(v['pin'],{}).get('point')!=v['point'] or pins[v['pin']]['layer']!=v['layer']:raise ValueError('Physical terminal moved.')
                for shape in actual:found[shape['id']]=(r['id'],shape['pcell_role'])
            except (ValueError,KeyError,StopIteration,TypeError) as exc:
                invalid.append(dict(severity='error',code='INDUCTOR.STALE',cell_id=cell['id'],object=r.get('device_id',''),message='Inductor requires regeneration: '+str(exc)))
    return found,invalid


def contact_shapes(p,cid,shapes=None):
    if shapes is None:
        from .design_ops import flatten_layout
        shapes=flatten_layout(p,cid)
    found,_=_recognized(p)
    if not found:return shapes
    return [s for s in shapes if not found.get(s.get('source_id',s['id']),('',''))[1].startswith('body.')]


def contact_findings(p,cid):
    from .design_ops import flatten_layout
    from .physical_cells import reachable
    from .spatial import SpatialIndex
    found,invalid=_recognized(p); reachable_cells=set(reachable(p,cid))|set(reachable(p,cid,physical=True))
    issues=[{**v,'cell_id':cid} for v in invalid if v['cell_id'] in reachable_cells]
    if found:
        shapes=flatten_layout(p,cid);db=kdb();groups={};polys=[polygon(s) for s in shapes]
        index=SpatialIndex([((b.left,b.bottom,b.right,b.top),i) for i,poly in enumerate(polys) for b in [poly.bbox()]])
        def group(s):
            rec=found.get(s.get('source_id',s['id']))
            return (rec[0],s.get('instance_path','')) if rec else None
        for i,s in enumerate(shapes):
            g=group(s)
            if g is not None:groups.setdefault(g,[]).append(i)
        joins={(a,b) for a,cut,b in p['pdk'].get('connectivity',{}).get('vias',[]) for a,b in ((a,cut),(cut,a),(cut,b),(b,cut))}
        seen=set()
        for g,indices in groups.items():
            ports=db.Region()
            for i in indices:
                if found[shapes[i].get('source_id',shapes[i]['id'])][1] in ('port.p','port.n'):ports.insert(polys[i])
            ports.merge()
            for i in indices:
                s=shapes[i]
                if not found[s.get('source_id',s['id'])][1].startswith('body.'):continue
                body=db.Region(polys[i]);b=polys[i].bbox()
                for j in index.query((b.left,b.bottom,b.right,b.top)):
                    other=shapes[j]
                    if group(other)==g or (g,j) in seen:continue
                    if s['layer']!=other['layer'] and (s['layer'],other['layer']) not in joins:continue
                    target=db.Region(polys[j])
                    if body.interacting(target).is_empty():continue
                    # Include edge-only contact, and allow access only within declared port pads.
                    if not ((body.sized(1)&target.sized(1))-ports.sized(2)).is_empty():
                        seen.add((g,j));issues.append(dict(severity='error',code='INDUCTOR.TAP',cell_id=cid,object=other['id'],objects=[s['id'],other['id']],message='Geometry contacts an inductor winding outside its P/N terminal pads. Route to a terminal or remove the contact.'))
    for issue in issues:issue['fingerprint']=digest([p['revision'],issue])
    return issues


def reject_parasitic_estimate(p,cid):
    from .physical_cells import reachable
    cells=set(reachable(p,cid))|set(reachable(p,cid,physical=True))
    if any(c['id'] in cells and any(r.get('spec',{}).get('kind')=='inductor' for r in c.get('parametric_devices',[])) for c in p['cells']):
        raise ValueError('Spiral inductor parasitics require a qualified EM/device model. The interconnect RC estimator cannot characterize this winding.')


def plan(p,cid,spec,did=None,name='L1',nets=None,use_estimate=False,locked=()):
    from .parametric import geometry_signature,electrical_signature
    from .live_geometry import preview
    q=clone(p);q['pdk']=clone(technology(q));declare_connections(q['pdk'])
    c=next(c for c in q['cells'] if c['id']==cid); old=next((r for r in c.get('parametric_devices',[]) if did and r.get('device_id')==did),None)
    if old and old['spec']['kind']!='inductor':raise ValueError('This device has a different generator.')
    if old:current_spec(c,old)
    old_shapes=[s for s in c['shapes'] if old and s.get('pcell_id')==old['id']]
    if did:
        d=next((d for d in c['devices'] if d['id']==did),None)
        if not d or d['kind']!='L' or d.get('native_spice'):raise ValueError('Choose a standard schematic inductor.')
        if not old and (any(s.get('device_id')==did for s in c['shapes']) or any(v.get('device_id')==did for v in c.get('layout_instances',[]))):
            raise ValueError('This inductor already has a different physical implementation.')
    else:
        if not NAME.fullmatch(name) or not name.upper().startswith('L') or any(d['name'].casefold()==name.casefold() for d in c['devices']):
            raise ValueError('Choose a unique schematic name beginning with L.')
        nets=nets or dict(p=name+'_p',n=name+'_n')
        if set(nets)!=set(('p','n')) or any(not NET.fullmatch(v) for v in nets.values()) or nets['p']==nets['n']:
            raise ValueError('Choose two distinct valid terminal net names.')
        from .wiring import migrate
        migrate(c,q)
        d=device('L',name,x=max([v['x'] for v in c['devices']]+[120])+180,y=250,nets=clone(nets));did=d['id'];c['devices'].append(d)
        if 'wires' in c:
            from .net_labels import add
            for pin,net in nets.items():add(c,net,dict(kind='pin',id=did,pin=pin),q)
        use_estimate=True
    validate(q)
    data=build(q,cid,did,spec)
    if use_estimate:d['value']=format(data['estimate_h'],'.12g')
    r=data['record'];r.update(id=old['id'] if old else uid(),source_signature=electrical_signature(d))
    r['electrical']['target']=scalar(d['value']);by_role={s['pcell_role']:s['id'] for s in old_shapes}
    for shape in data['shapes']:
        shape['id']=by_role.get(shape['pcell_role'],shape['id']);shape['pcell_id']=r['id']
    if {s['layer'] for s in old_shapes+data['shapes']} & set(locked):raise ValueError('Unlock every winding and via layer before creating or regenerating the inductor.')
    previous_pins={v['pin']:v for v in c.get('layout_pins',[]) if v['device_id']==did}
    for v in data['pins']:
        if v['pin'] in previous_pins:v['id']=previous_pins[v['pin']]['id']
    r['geometry_signature']=geometry_signature(data['shapes']);r['reference']=dict(role=data['shapes'][0]['pcell_role'],points=clone(data['shapes'][0]['points']))
    old_ids={s['id'] for s in old_shapes}
    c['shapes']=[s for s in c['shapes'] if s['id'] not in old_ids]
    errors=preview(q,cid,data['shapes'])
    if errors:raise ValueError('Geometry check: '+errors[0]['message'])
    # Capture actual external conductors and anchors, including via access on
    # the return layer. Internal recipe metal is never a routing attachment.
    if old:
        from .layout_graph import GeometryGraph
        foreign=contact_shapes(q,cid)
        before=GeometryGraph().sync(foreign+[s for s in old_shapes if s['pcell_role'].startswith('port.')],q['pdk']).partition(p,cid)
    c['shapes'].extend(data['shapes']);c['layout_pins']=[v for v in c.get('layout_pins',[]) if v['device_id']!=did]+data['pins']
    c['parametric_devices']=[v for v in c.get('parametric_devices',[]) if v is not old]+[r]
    validate(q)
    if old:
        after=GeometryGraph().sync(contact_shapes(q,cid),q['pdk']).partition(q,cid)
        for pin in data['pins']:
            anchor=('pin',pin['id'])
            attached={k for k in before.get(anchor,()) if k[0]!='shape' or k[1] not in old_ids}
            if not attached<=after.get(anchor,frozenset()):
                raise ValueError('Regeneration would disconnect an attached terminal route or port. Keep the terminal position or detach the route first.')
    findings=contact_findings(q,cid)
    if findings:raise ValueError(findings[0]['message'])
    from .physical import connectivity
    old_shorts={digest({k:v.get(k) for k in ('code','object','message')}) for v in connectivity(p,cid)['issues'] if v['code']=='LVS.SHORT'}
    for v in connectivity(q,cid)['issues']:
        if v['code']=='LVS.SHORT' and digest({k:v.get(k) for k in ('code','object','message')}) not in old_shorts:raise ValueError(v['message'])
    return dict(project_id=p['id'],cell_id=cid,design_hash=design_digest(p),pdk=q['pdk'],cell=c,device_id=did,
        shapes=data['shapes'],pins=data['pins'],estimate_h=data['estimate_h'],outer_nm=data['outer_nm'],via_count=data['via_count'],qualification=QUALIFICATION,
        touched_layers=sorted({s['layer'] for s in old_shapes+data['shapes']}))


def install(p,proposal,locked=()):
    if proposal['project_id']!=p['id'] or proposal['design_hash']!=design_digest(p):
        raise ValueError('The design changed after the preview. Refresh the inductor preview before applying it.')
    if set(locked)&set(proposal['touched_layers']):raise ValueError('Unlock the winding and via layers first.')
    q=clone(p);q['pdk']=clone(proposal['pdk']);c=next(c for c in q['cells'] if c['id']==proposal['cell_id']);c.update(clone(proposal['cell']));validate(q)
    p['pdk']=q['pdk'];next(v for v in p['cells'] if v['id']==c['id']).update(c)
    return [s['id'] for s in proposal['shapes']]
