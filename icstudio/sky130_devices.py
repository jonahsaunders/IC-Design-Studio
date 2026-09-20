"""Bounded SKY130 MiM, poly resistor, contacted guards and explicit MOS dummies.

Geometry is integer nanometres; catalog passive W/L are emitted micrometres.
The recipes follow the pinned open_pdks SKY130 technology. Every edited layout
still requires actual process DRC/LVS; this module never substitutes a nominal
capacitor or resistor value for its process model.
"""
import math
from .model import clone, uid, validate, design_digest, NET
from .layout import rect, polygon, kdb
from .catalog import binding_for, parameter_values

MODELS={'sky130_fd_pr__cap_mim_m3_1':'mim_capacitor',
        'sky130_fd_pr__res_generic_po':'poly_resistor'}
MASKS={'m1':(68,20),'m2':(69,20),'m3':(70,20),'m4':(71,20),
       'via':(68,44),'via2':(69,44),'via3':(70,44),'capm':(89,44),
       'poly':(66,20),'polyres':(66,13),'npc':(95,20),'licon':(66,44),
       'li':(67,20),'mcon':(67,44),'tap':(65,44),'psdm':(94,20),
       'nsdm':(93,44),'nwell':(64,20)}


def layers(tech):
    if tech.get('package_lock',{}).get('id')!='sky130A':raise ValueError('These physical devices require the linked SKY130A process.')
    table={(r['gds'],r['datatype']):r['name'] for r in tech['layers']}
    missing=[name for name,mask in MASKS.items() if mask not in table]
    if missing:raise ValueError('Missing SKY130 physical-device layers: '+', '.join(missing))
    return {name:table[mask] for name,mask in MASKS.items()}


def supported(tech,d):
    binding=binding_for(tech,d)
    return bool(binding and binding.get('model') in MODELS)


def specification(tech,d):
    layers(tech);binding=binding_for(tech,d)
    if not binding or binding.get('model') not in MODELS:raise ValueError('Choose the SKY130 MiM m3_1 capacitor or generic poly resistor catalog model.')
    model=binding['model'];kind=MODELS[model]
    pins=['c0','c1'] if kind=='mim_capacitor' else ['m','p']
    emit={'w':'w','l':'l','mf':'mf','m':'mf'} if kind=='mim_capacitor' else {'w':'w','l':'l','m':'mult'}
    if binding.get('prefix')!=('X' if kind=='mim_capacitor' else 'R') or binding.get('pin_order')!=pins or binding.get('emit_parameters')!=emit or set(d['nets'])!=set(pins):
        raise ValueError('The passive recipe requires its exact shipped model, terminal order and W/L/multiplicity emission; reindex legacy resistor catalogs that emit X instead of R.')
    if binding.get('parameter_scale')!={'w':1e6,'l':1e6}:raise ValueError('SKY130 passive W and L must be catalog micrometre parameters.')
    values=parameter_values(binding,d)
    if any(values.get(k,1)!=1 for k in ('mf','mult','m')):raise ValueError('This physical passive recipe supports multiplicity one; place explicit parallel devices.')
    size={}
    for key in ('w','l'):
        nm=values[key]*1000;minimum=2000 if kind=='mim_capacitor' else (500 if key=='w' else 1650)
        maximum=30000 if kind=='mim_capacitor' else (10000 if key=='w' else 100000)
        if not math.isfinite(nm) or abs(nm-round(nm))>1e-6 or round(nm)%5 or not minimum<=nm<=maximum:
            raise ValueError(f'{key.upper()}: use {minimum/1000:g}–{maximum/1000:g} µm on the 5 nm grid.')
        size[key]=round(nm)
    if kind=='mim_capacitor' and max(size.values())>5*min(size.values()):raise ValueError('The bounded MiM recipe supports aspect ratio at most 5:1.')
    return dict(api=1,recipe=kind,model=model,model_ref=clone(d['model_ref']),
                kind=d['kind'],values=values,dimensions_nm=size,nets=clone(d['nets']))


def configure_connectivity(tech):
    ls=layers(tech);cfg=tech.setdefault('connectivity',{})
    cfg['conductors']=list(dict.fromkeys(cfg.get('conductors',[])+[ls[k] for k in ('li','m1','m2','m3','m4','capm')]))
    # capm is a device electrode, not a general routing layer. Keeping it in
    # physical connectivity is necessary to recognize the insulated top plate.
    tech['routing_conductors']=[layer for layer in tech.get('routing_conductors',cfg['conductors']) if layer!=ls['capm']]
    vias=cfg.setdefault('vias',[])
    for a,cut,b in (('li','mcon','m1'),('m1','via','m2'),('m2','via2','m3'),('m3','via3','m4'),('capm','via3','m4')):
        row=[ls[a],ls[cut],ls[b]]
        if row not in vias:vias.append(row)
    blocker=dict(conductor=ls['m3'],cut=ls['via3'],mask=ls['capm'])
    if blocker not in cfg.setdefault('via_blockers',[]):cfg['via_blockers'].append(blocker)


def geometry(tech,d,x=0,y=0):
    spec=specification(tech,d);ls=layers(tech);w,l=spec['dimensions_nm']['w'],spec['dimensions_nm']['l']
    if any(type(v) is not int or v%5 or abs(v)>100000000 for v in (x,y)):raise ValueError('Use a placement on the 5 nm grid within ±100 mm.')
    shapes=[];pins=[]
    def box(role,key,a,b,width,height,net=''):
        s=rect(ls[key],x+a,y+b,width,height,d['id'],net)
        s.update(generated_device=d['id'],generator_role='passive:'+role);shapes.append(s)
    def pin(name,key,pt):pins.append(dict(id=uid(),device_id=d['id'],pin=name,layer=ls[key],point=[x+pt[0],y+pt[1]]))
    if spec['recipe']=='mim_capacitor':
        # c0 is the MiM top electrode; c1 is the metal3 bottom electrode.
        top,bottom=d['nets']['c0'],d['nets']['c1'];cy=5*round(l/10);cx=5*round(w/10)
        box('bottom','m3',-500,-500,w+3000,l+1000,bottom)
        box('dielectric_top','capm',0,0,w,l,top)
        box('top_access','m4',100,100,w-200,l-200,top)
        for ix,a in enumerate(range(300,w-300,400)):
            for iy,b in enumerate(range(300,l-300,400)):
                box(f'top_via_{ix}_{iy}','via3',a,b,200,200)
        bx=w+1500
        box('bottom_access','m4',bx-700,cy-700,1400,1400,bottom)
        for ix in (-1,0,1):
            for iy in (-1,0,1):box(f'bottom_via_{ix}_{iy}','via3',bx+ix*400-100,cy+iy*400-100,200,200)
        pin('c0','m4',[cx,cy]);pin('c1','m4',[bx,cy])
    else:
        # The resistor marker sets model L exactly; terminal extensions are
        # unmarked conductive poly, contacted through licon/LI/mcon to metal1.
        cy=5*round(w/10)
        box('poly','poly',-2000,0,l+4000,w)
        box('resistor_marker','polyres',0,0,l,w)
        for role,px in (('m',-1500),('p',l+1500)):
            net=d['nets'][role]
            for key,half in (('npc',320),('licon',85),('li',170),('mcon',85),('m1',170)):
                box(role+'_'+key,key,px-half,cy-half,2*half,2*half,net if key in ('li','m1') else '')
            pin(role,'m1',[px,cy])
    return dict(shapes=shapes,pins=pins,record=dict(device_id=d['id'],spec=spec,origin=[x,y]))


def install(p,cid,did,x=0,y=0):
    """Install a passive through the normal process footprint/ECO identity path."""
    from .sky130_layout import install_mos
    return install_mos(p,cid,did,x,y)


def guard_geometry(tech,spec):
    """Continuous contacted p+ substrate or n+ well ring; four metal1 sides."""
    ls=layers(tech);kind=spec.get('kind','psub')
    if kind not in ('psub','nwell'):raise ValueError('Choose a p+ substrate guard or n+ well guard.')
    s={**spec,'kind':kind,'thickness':spec.get('thickness',800)}
    for key in ('x','y','width','height','thickness'):
        if type(s.get(key)) is not int or s[key]%5:raise ValueError('Guard dimensions and origin must use integer nanometres on the 5 nm grid.')
    x,y,w,h,t=(s[k] for k in ('x','y','width','height','thickness'))
    if not 800<=t<=5000 or not 2*t+2000<=min(w,h) or max(w,h)>500000 or max(abs(x),abs(y))>100000000:raise ValueError('Use 0.8–5 µm guard thickness and a 2 µm opening, within 500 µm overall.')
    shapes=[]
    def add(role,key,a,b,width,height):
        shape=rect(ls[key],x+a,y+b,width,height)
        shape.update(pcell_role=role,process_guard=True);shapes.append(shape)
    def ring(role,key,offset,thickness):
        a=-offset;ww=w+2*offset;hh=h+2*offset
        for side,(bx,by,bw,bh) in enumerate(((a,a,ww,thickness),(a,a+hh-thickness,ww,thickness),(a,a+thickness,thickness,hh-2*thickness),(a+ww-thickness,a+thickness,thickness,hh-2*thickness))):add(role+str(side),key,bx,by,bw,bh)
    ring('tap','tap',0,t);ring('implant','psdm' if kind=='psub' else 'nsdm',130,t+260)
    ring('li','li',0,t);ring('metal','m1',0,t)
    if kind=='nwell':add('well','nwell',-500,-500,w+1000,h+1000)
    center=5*round(t/10);points=[]
    # Explicit corner contacts plus interior contacts at least one pitch away
    # avoid subminimum end gaps when width/height are not multiples of pitch.
    for px in [center,*range(center+400,w-center-399,400),w-center]:points.extend(((px,center),(px,h-center)))
    for py in range(center+400,h-center-399,400):points.extend(((center,py),(w-center,py)))
    for i,(px,py) in enumerate(dict.fromkeys(points)):
        add('licon'+str(i),'licon',px-85,py-85,170,170)
        add('mcon'+str(i),'mcon',px-85,py-85,170,170)
    return dict(shapes=shapes,spec=s,tie_point=[x+center,y+center],layer=ls['m1'])


def install_guard(p,cid,spec,net,tie=None,members=()):
    """Atomic guard installation, optionally routed to an existing metal1 tie."""
    if not isinstance(net,str) or not NET.fullmatch(net):raise ValueError('Use a valid guard reference net.')
    q=clone(p);c=next(c for c in q['cells'] if c['id']==cid);data=guard_geometry(q['pdk'],spec);ident=uid()
    configure_connectivity(q['pdk'])
    if tie is not None:
        if not isinstance(tie,dict) or not isinstance(tie.get('point'),list) or len(tie['point'])!=2 or not any(s['layer']==tie.get('layer') and s.get('net')==net and polygon(s).inside(kdb().Point(*tie['point'])) for s in c['shapes']):
            raise ValueError('Choose a guard tie on an existing conductor carrying the reference net.')
    ls=layers(q['pdk'])
    for shape in data['shapes']:
        shape['pcell_id']=ident
        if tie is not None and shape['layer'] in (ls['li'],ls['m1']):shape['net']=net
    c['shapes'].extend(data['shapes'])
    record=dict(id=ident,spec={**data['spec'],'net':net},reference=dict(role=data['shapes'][0]['pcell_role'],points=clone(data['shapes'][0]['points'])),shape_ids=[s['id'] for s in data['shapes']],tie_point=data['tie_point'],layer=data['layer'])
    c.setdefault('process_guards',[]).append(record)
    if tie is not None:
        from .layout_routing import Geometry,install as route_install,length
        from .wiring import clean
        if tie['layer']!=data['layer']:raise ValueError('The bounded guard tie requires an existing metal1 conductor.')
        start=data['tie_point'];end=tie['point'];obstacles=Geometry(q,cid,net);group=uid();route=None
        # Prefer a single bend: tiny A* stair steps around same-net contacts can
        # create metal notches despite satisfying different-net clearance.
        for elbow in ([end[0],start[1]],[start[0],end[1]]):
            shape=dict(id=uid(),kind='path',layer=data['layer'],points=clean([start,elbow,end]),width=340,net=net,device_id='',route_group=group,generated_route=True)
            if len(shape['points'])>1 and obstacles.clear(shape):route=shape;break
        if route is None:raise ValueError('Clear an orthogonal metal1 corridor from the lower-left guard corner to its tie.')
        proposal=dict(version=1,project_id=q['id'],cell_id=cid,design_hash=design_digest(q),shapes=[route],route_group=group,net=net,length_nm=length([route]),via_count=0,visited_nodes=0,start=dict(layer=data['layer'],point=start),end=clone(tie),width=340,layers=[data['layer']],qualification='Bounded single-bend guard tie; run process DRC/LVS.')
        route_ids=route_install(q,proposal)
        record=next(r for r in c['process_guards'] if r['id']==ident);record['route_ids']=route_ids
    if members:
        if not set(members)<={d['id'] for d in c['devices']}:raise ValueError('Choose existing devices protected by this guard.')
        c.setdefault('analog_constraints',[]).append(dict(id=uid(),name='Process '+data['spec']['kind']+' guard',kind='guard_ring',members=list(members),ring=ident))
    validate(q);p.clear();p.update(q);return record


def install_dummy(p,cid,name,kind,tie_net,w='1u',l='1u',x=0,y=0):
    """Create a real schematic MOS dummy with D/G/S/B explicitly tied together."""
    if kind not in ('NMOS','PMOS') or not NET.fullmatch(tie_net):raise ValueError('Choose NMOS or PMOS and an explicit reference net.')
    q=clone(p);c=next(c for c in q['cells'] if c['id']==cid)
    from .catalog import create_device
    from .sky130_layout import MODELS,install_mos
    key=next((key for key,b in q['pdk']['simulation']['catalog'].items() if b.get('model')==MODELS[kind] and b.get('pin_order')==['d','g','s','b'] and b.get('emit_parameters',{}).get('w')=='w'),None)
    if key is None:raise ValueError('The standard four-terminal SKY130 model is missing.')
    sx=max((v['x'] for v in c['devices']),default=-300)+300
    d=create_device(q['pdk'],key,name,sx,0);d['params'].update(w=w,l=l);d['nets']={pin:tie_net for pin in ('d','g','s','b')};d['physical_dummy']=True
    c['devices'].append(d)
    if 'wires' in c:
        # Explicit attached labels survive the desktop's normal newly-placed
        # device initialization, which deliberately clears legacy pin labels.
        for pin in d['nets']:
            c.setdefault('labels',[]).append(dict(id=uid(),kind='net_label',name=tie_net,anchor=dict(kind='pin',id=d['id'],pin=pin),offset=[10,-12],rotation=0))
    install_mos(q,cid,d['id'],x,y)
    validate(q);p.clear();p.update(q);return d


def finish_mos(tech,d,data):
    """Persist dummy terminal straps in the generator, including later ECOs."""
    if not d.get('physical_dummy'):return data
    if len(set(d['nets'].values()))!=1:raise ValueError('A physical MOS dummy requires D/G/S/B tied to one explicit reference net.')
    ls=layers(tech);pins=data['pins'];rail=min(v['point'][1] for v in pins)-1200;net=next(iter(d['nets'].values()))
    def path(role,points):data['shapes'].append(dict(id=uid(),kind='path',layer=ls['m1'],points=points,width=340,net=net,generated_device=d['id'],device_id=d['id'],generator_role=role))
    for i,pin in enumerate(pins):
        px,py=pin['point'];path('dummy_tie_'+str(i),[[px,py],[px,rail]])
    xs=[v['point'][0] for v in pins];path('dummy_rail',[[min(xs),rail],[max(xs),rail]])
    return data
