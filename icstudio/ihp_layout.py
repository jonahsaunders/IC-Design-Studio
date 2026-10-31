"""Bounded IHP SG13G2 1.2/3.3 V MOS geometry using locked native decks.

Native GDS drawing datatype 0 and port datatype 2 are process-specific.
Total W=.15..10 um, L=.13..10 um, 5 nm grid, ng=1..8, m=1..16.
Each finger must be at least .15 um wide. All four terminals are contacted.
HV: W/finger >= .30 um, L >= .45 um NMOS / .40 um PMOS, same upper bounds.
"""
from pathlib import Path
from .model import clone, uid, scalar, validate, digest, file_digest
from .catalog import binding_for, parameter_values, create_device, link_technology
from .layout import rect
from .sky130_layout import resolved

MASKS = {'nwell': (31,0), 'diff': (1,0), 'poly': (5,0), 'psdm': (14,0),
         'nsdm': (7,0), 'contact': (6,0), 'm1': (8,0), 'via': (19,0), 'm2': (10,0),
         'm1label': (8,2), 'm2label': (10,2), 'thickox': (44,0)}
MODELS = {'NMOS': 'sg13_lv_nmos', 'PMOS': 'sg13_lv_pmos'}
HV_MODELS = {'NMOS': 'sg13_hv_nmos', 'PMOS': 'sg13_hv_pmos'}
API = 1


def layers(tech):
    if tech.get('package_lock',{}).get('id') != 'ihp-sg13g2': raise ValueError('Link an IHP SG13G2 package first.')
    by = {(l['gds'],l['datatype']): l['name'] for l in tech['layers']}
    return {key: by.get(pair, 'ihp_'+key) for key,pair in MASKS.items()}


def prepare(tech):
    from .process_adapters import adapter
    process = adapter(tech)
    assets = process.engine_assets(tech)
    names = layers(tech); present = {(l['gds'],l['datatype']) for l in tech['layers']}
    colors = ['#bb9a64','#73c683','#ef8a83','#a785d9','#75abc7','#cccccc','#6b9cf0','#d8b46c','#bd90ec','#6b9cf0','#bd90ec','#ffffcc']
    for (key,(gds,datatype)),color in zip(MASKS.items(), colors):
        if (gds,datatype) not in present:
            if any(l['name']==names[key] for l in tech['layers']): raise ValueError('Conflicting IHP native layer name: '+names[key])
            width,space = {'m1':(160,180),'m2':(200,210),'via':(190,220),'contact':(160,180),
                           'poly':(130,180),'diff':(150,210),'nwell':(620,620)}.get(key,(0,0))
            tech['layers'].append({'name':names[key],'gds':gds,'datatype':datatype,'color':color,'width':width,'space':space})
    tech['native_layer_contract'] = {'adapter': process.id, 'api': API,
        'source': assets['technology'].relative_to(Path(tech['package_root']).resolve()).as_posix(),
        'sha256': file_digest(assets['technology'])}
    tech['connectivity'] = {'conductors':[names['m1'],names['m2']], 'vias':[[names['m1'],names['via'],names['m2']]]}


def specification(tech, d):
    from .ihp_resistors import supported, specification as resistor_specification
    if supported(tech,d):return resistor_specification(tech,d)
    layers(tech); b = binding_for(tech,d)
    if not b or b['model'] not in (MODELS.get(d['kind']),HV_MODELS.get(d['kind'])) or set(d['nets']) != {'d','g','s','b'}:
        raise ValueError('Select a standard four-terminal IHP LV or HV NMOS/PMOS.')
    if set(b.get('emit_parameters',{}))-{'w','l','ng','m','mm_ok'}:
        raise ValueError('This IHP layout recipe requires the standard MOS view; RF geometry is not interchangeable.')
    high_voltage = b['model']==HV_MODELS.get(d['kind'])
    values = parameter_values(b,d)
    if any(values.get(k,1) != 1 for k in ('nf','mult')) or scalar(d['params'].get('nf','1'))!=1:
        raise ValueError('Use ng for IHP gate fingers and m for parallel copies.')
    if (b.get('prefix')!='X' or b.get('pin_order')!=['d','g','s','b']
            or b.get('parameter_scale')!={'w':1,'l':1}
            or any(b.get('emit_parameters',{}).get(k)!=k for k in ('w','l','ng','m'))):
        raise ValueError('Use the standard IHP model binding with W/L in metres and explicit ng/m.')
    from .process_mos_parallel import count
    count(values['m'])
    size = {}
    minimum_width=300 if high_voltage else 150
    minimum_length=(450 if d['kind']=='NMOS' else 400) if high_voltage else 130
    for k,minimum,maximum in (('w',minimum_width,10000),('l',minimum_length,10000)):
        raw = values[k]*1e9; n = round(raw)
        if abs(raw-n)>1e-6 or n%5 or not minimum<=n<=maximum:
            raise ValueError(f'{d["name"]}: {k.upper()} must be {minimum/1000:g} to {maximum/1000:g} micrometres on the 5 nm grid.')
        size[k] = n
    from .process_mos_fingers import dimensions as finger_dimensions
    finger_dimensions(size['w'],values['ng'],minimum_width)
    return {'api': API,'model_ref': clone(d.get('model_ref')),'model':b['model'], 'kind':d['kind'],
            'dimensions_nm':size,'values':values,'nets':clone(d['nets']),
            **({'high_voltage':True,'minimum_finger_width_nm':300} if high_voltage else {})}


def thick_oxide(data, spec, names):
    """Cover the HV row before repeating parallel units; body taps stay separate.

    Public TGO.a active enclosure is 270 nm; TGO.c gate enclosure is 340 nm.
    The channel row includes its 300 nm poly extension and contact landing pads.
    """
    if not spec.get('high_voltage'):return data
    # The public HV PCells use implicit N+ active (outside pSD). Explicit nSD
    # is an extra implant and the public KLayout deck excludes it from MOS.
    # Keep the historical LV recipe unchanged; HV must work in both engines.
    data['shapes']=[s for s in data['shapes'] if s['layer']!=names['nsdm']]
    x,y=data['record']['origin'];count=int(spec['values']['ng'])
    width=spec['dimensions_nm']['w']//count;length=spec['dimensions_nm']['l']
    last=(count-1)*(length+1200);active_extension=900 if count>1 else 800
    shape=rect(names['thickox'],x-active_extension-270,y-640,
        last+length+2*(active_extension+270),width+1280,data['record']['device_id'])
    shape.update(generated_device=data['record']['device_id'],generator_role='hv:oxide')
    data['shapes'].append(shape)
    return data


def mos(tech,d,x=0,y=0):
    from .ihp_resistors import supported, geometry as resistor_geometry
    if supported(tech,d):return resistor_geometry(tech,d,x,y)
    spec = specification(tech,d); ls = layers(tech); w,l = [spec['dimensions_nm'][k] for k in ('w','l')]
    if any(type(v) is not int or v%5 for v in (x,y)): raise ValueError('Place devices on the 5 nm grid.')
    if spec['values']['ng'] != 1:
        from .process_mos_fingers import generate as fingers
        from .process_mos_parallel import generate as parallel
        return parallel(tech,d,thick_oxide(fingers(tech,d,x,y,spec,ls),spec,ls),ls,spec['values']['m'])
    shapes=[]; pins=[]
    def box(key,a,b,c,e,net=''):
        s=rect(ls[key],x+a,y+b,c-a,e-b,d['id'],net);s['generated_device']=d['id'];shapes.append(s)
    gate=5*round(l/10);cy=5*round(w/10)
    bottom,top=min(0,cy-350),max(w,cy+350)
    box('diff',-800,0,l+800,w)
    box('psdm' if d['kind']=='PMOS' else 'nsdm',-1100,bottom-300,l+1100,top+300)
    box('poly',0,-1000,l,w+300);box('poly',gate-250,-1050,gate+250,-550)
    box('diff',-2850,cy-350,-2150,cy+350)
    box('nsdm' if d['kind']=='PMOS' else 'psdm',-3150,cy-650,-1850,cy+650)
    if w<700:
        # Append after the body tap so its regeneration role remains stable.
        box('diff',-800,cy-350,-300,cy+350)
        box('diff',l+300,cy-350,l+800,cy+350)
    if d['kind']=='PMOS':
        # NW.c1 requires 620 nm around HV P+ active, versus 600 nm here for LV.
        box('nwell',-3450,-1500,l+(1420 if spec.get('high_voltage') else 1400),top+700)
    for pin,px,py in (('s',-500,cy),('d',l+500,cy),('g',gate,-800),('b',-2500,cy)):
        # Exact 0.16 um contact cut; enclosure is provided by active/poly and M1.
        box('contact',px-80,py-80,px+80,py+80)
        box('m1',px-200,py-200,px+200,py+200,d['nets'][pin])
        pins.append({'id':uid(),'device_id':d['id'],'pin':pin,'layer':ls['m1'],'point':[x+px,y+py]})
    from .layout_eco import roles
    from .process_mos_parallel import generate
    return generate(tech,d,thick_oxide(roles({'shapes':shapes,'pins':pins,'record':{'device_id':d['id'],'spec':spec,'origin':[x,y]}}),spec,ls),ls,spec['values']['m'])


def install_mos(p,cid,did,x=0,y=0):
    c=next(c for c in p['cells'] if c['id']==cid)
    if any(r['device_id']==did for r in c.get('pdk_layouts',[])):raise ValueError('This device already has generated geometry. Review regeneration.')
    d=resolved(p,cid,next(d for d in c['devices'] if d['id']==did));specification(p['pdk'],d);prepare(p['pdk']);data=mos(p['pdk'],d,x,y)
    c['shapes'].extend(data['shapes']);c.setdefault('layout_pins',[]).extend(data['pins']);c.setdefault('pdk_layouts',[]).append(data['record']);return data


def regenerate_mos(p,cid,did):
    from .layout_eco import regenerate
    return regenerate(p,cid,did)


def inverter_devices(p,cid):
    c=next(c for c in p['cells'] if c['id']==cid)
    if len(c['devices'])!=2 or {d['kind'] for d in c['devices']}!={'NMOS','PMOS'}:raise ValueError('Use an inverter cell with one NMOS and one PMOS.')
    n,q=[resolved(p,cid,next(d for d in c['devices'] if d['kind']==kind)) for kind in ('NMOS','PMOS')]
    for d in (n,q):specification(p['pdk'],d)
    a,b=n['nets'],q['nets']
    if not (a['d']==b['d'] and a['g']==b['g'] and a['s']==a['b'] and b['s']==b['b'] and len({a['d'],a['g'],a['s'],b['s']})==4 and set(c['ports'])=={a['d'],a['g'],a['s'],b['s']}):raise ValueError('Expose common gate/drain and separate source/body supply ports.')
    return n,q


def generate_inverter(p,cid,replace=False):
    n,q=inverter_devices(p,cid);c=next(c for c in p['cells'] if c['id']==cid)
    if c['shapes'] or c.get('layout_instances'):
        if not replace or not c.get('inverter_layout'):raise ValueError('Review regeneration before replacing an existing generated inverter layout.')
    for key in ('shapes','layout_pins','layout_texts','layout_ports','pdk_layouts','layout_instances'):c[key]=[]
    prepare(p['pdk']);ls=layers(p['pdk']);py=specification(p['pdk'],n)['dimensions_nm']['w']+6000
    from .process_mos_parallel import inverter_separation
    from .process_adapters import adapter
    py=inverter_separation(p['pdk'],n,q,adapter(p['pdk']).implementation(),py)
    for d,y in ((n,0),(q,py)):install_mos(p,cid,d['id'],0,y)
    pins={(v['device_id'],v['pin']):v['point'] for v in c['layout_pins']}
    def wire(key,points,net):
        points=[list(pt) for i,pt in enumerate(points) if not i or list(pt)!=list(points[i-1])]
        c['shapes'].append({'id':uid(),'kind':'path','layer':ls[key],'points':points,'width':400,'net':net,'device_id':'','generated_route':True})
    for d in (n,q):wire('m1',[pins[d['id'],'b'],pins[d['id'],'s']],d['nets']['s'])
    nd,pd=pins[n['id'],'d'],pins[q['id'],'d'];right=max(nd[0],pd[0])+1200
    wire('m1',[nd,[right,nd[1]],[right,pd[1]],pd],n['nets']['d'])
    ng,pg=pins[n['id'],'g'],pins[q['id'],'g'];wire('m2',[ng,[ng[0],pg[1]],pg],n['nets']['g'])
    for px,yy in (ng,pg):
        for key,half in (('via',95),('m1',220),('m2',220)):
            c['shapes'].append(rect(ls[key],px-half,yy-half,half*2,half*2,net=n['nets']['g'] if key!='via' else ''))
    from .physical_cells import assign_port
    for net,key,pt in ((n['nets']['s'],'m1',pins[n['id'],'b']),(q['nets']['s'],'m1',pins[q['id'],'b']),(n['nets']['d'],'m1',[right,nd[1]]),(n['nets']['g'],'m2',ng)):
        assign_port(p,cid,net,ls[key],pt)
    c['inverter_layout']={'api':API,'process':p['pdk']['package_lock']['id'],'device_ids':[n['id'],q['id']]};validate(p);return p


def audit(p,cid):
    c=next(c for c in p['cells'] if c['id']==cid);ds={d['id']:d for d in c['devices']};out=[]
    for r in c.get('pdk_layouts',[]):
        try:
            if r['device_id'] not in ds or specification(p['pdk'],resolved(p,cid,ds[r['device_id']]))!=r['spec']:
                raise ValueError('IHP model, dimensions, parameters or nets changed. Regenerate and verify the layout.')
        except ValueError as exc:out.append({'severity':'error','code':'PDK.STALE','object':r['device_id'],'message':str(exc),'fingerprint':digest(str(exc))})
    return out
