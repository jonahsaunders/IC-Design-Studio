"""Editable, one-to-eight-finger SKY130 1.8 V MOS layouts in integer nanometres.

This is a bounded Studio generator, not the upstream Magic PCell generator.
Actual DRC and extracted LVS are separate gates, including after manual edits.
"""
from .model import clone, digest, scalar, uid, validate, example, device
from .catalog import binding_for, parameter_values, create_device, link_technology
from .layout import rect

MASKS = {'diff': (65,20), 'tap': (65,44), 'nwell': (64,20),
         'nsdm': (93,44), 'psdm': (94,20), 'poly': (66,20),
         'npc': (95,20), 'licon': (66,44), 'li': (67,20),
         'mcon': (67,44), 'm1': (68,20), 'via': (68,44),
         'm2': (69,20), 'm1label': (68,5), 'm2label': (69,5)}
MODELS = {'NMOS': 'sky130_fd_pr__nfet_01v8', 'PMOS': 'sky130_fd_pr__pfet_01v8'}
API = 1


def resolved(p,cid,d):
    from .design_ops import resolved_device,parameters
    cell=next(c for c in p['cells'] if c['id']==cid)
    return resolved_device(d,parameters(cell.get('parameters',{}),parameters(p.get('parameters',{}))))


def layers(tech):
    if tech.get('package_lock',{}).get('id') != 'sky130A':
        raise ValueError('This generator requires a linked SKY130A PDK.')
    by = {(l['gds'], l['datatype']): l['name'] for l in tech['layers']}
    missing = [k for k,v in MASKS.items() if v not in by]
    if missing: raise ValueError('PDK is missing required masks: '+', '.join(missing))
    return {k: by[v] for k,v in MASKS.items()}


def specification(tech, d):
    layers(tech)
    b = binding_for(tech,d)
    if not b or b['model'] != MODELS.get(d['kind']) or set(d['nets']) != {'d','g','s','b'}:
        raise ValueError(d['name']+': select a standard four-terminal SKY130 nfet_01v8 or pfet_01v8.')
    values = parameter_values(b,d)
    nf=values.get('nf',1)
    if nf!=int(nf) or not 1<=nf<=8 or any(values.get(k,1)!=1 for k in ('m','mult')):
        raise ValueError(d['name']+': this layout supports 1–8 fingers and multiplicity 1.')
    size = {}
    for k, minimum in (('w',420),('l',150)):
        raw = scalar(d['params'][k])*1e9
        value = round(raw)
        if abs(raw-value)>1e-6 or value%5 or not minimum<=value<=10000:
            raise ValueError(d['name']+f': {k.upper()} must be on the 5 nm grid, from {minimum/1000:g} to 10 µm.')
        size[k]=value
    if size['w']%int(nf) or size['w']//int(nf)<420 or (size['w']//int(nf))%5:
        raise ValueError(d['name']+': total W divided by nf must be at least 0.42 µm on the 5 nm grid.')
    # Only the standard catalog's width/length emission is accepted. Symbol variants
    # that transform W (e.g. per-finger templates) require their own geometry adapter.
    emit=b.get('emit_parameters',{})
    if emit.get('w')!='w' or emit.get('l')!='l':
        raise ValueError('This symbol transforms dimensions; select the standard MOS catalog entry.')
    return {'api':API,'model_ref':clone(d.get('model_ref')),'model':b['model'],
            'kind':d['kind'],'dimensions_nm':size,'values':values,'nets':clone(d['nets'])}


def mos(tech,d,x=0,y=0):
    spec=specification(tech,d);ls=layers(tech);w,l=(spec['dimensions_nm'][k] for k in ('w','l'))
    if any(type(v) is not int or v%5 for v in (x,y)):raise ValueError('Placement must be on the 5 nm grid.')
    if int(spec['values'].get('nf',1))>1:
        from .sky130_fingers import generate
        return generate(tech,d,x,y,spec)
    shapes=[];pins=[]
    def box(key,a,b,c,e,net=''):
        s=rect(ls[key],x+a,y+b,c-a,e-b,d['id'],net);s['generated_device']=d['id'];shapes.append(s)
    # Wide access regions deliberately leave room for manual routing and labels.
    box('diff',-800,0,l+800,w)
    implant='psdm' if d['kind']=='PMOS' else 'nsdm'
    box(implant,-930,-130,l+930,w+130)
    box('poly',0,-800,l,w+300)
    gate=5*round(l/10);cy=5*round(w/10)
    box('poly',gate-220,-820,gate+220,-380)
    box('npc',gate-320,-920,gate+320,-280)
    box('tap',-2450,cy-250,-1950,cy+250)
    box('nsdm' if d['kind']=='PMOS' else 'psdm',-2580,cy-380,-1820,cy+380)
    if d['kind']=='PMOS':box('nwell',-2820,-1200,l+1180,max(w+400,cy+620))
    for pin,px,py in [('s',-500,cy),('d',l+500,cy),('g',gate,-600),('b',-2200,cy)]:
        net=d['nets'][pin]
        for key,half in [('licon',85),('li',170),('mcon',85),('m1',170)]:
            box(key,px-half,py-half,px+half,py+half,net if key in ('li','m1') else '')
        pins.append({'id':uid(),'device_id':d['id'],'pin':pin,'layer':ls['m1'],'point':[x+px,y+py]})
    return {'shapes':shapes,'pins':pins,'record':{'device_id':d['id'],'spec':spec,'origin':[x,y]}}


def install_mos(p,cid,did,x=0,y=0):
    c=next(c for c in p['cells'] if c['id']==cid);d=resolved(p,cid,next(d for d in c['devices'] if d['id']==did))
    data=mos(p['pdk'],d,x,y)
    old=next((r for r in c.get('pdk_layouts',[]) if r['device_id']==did),None)
    if old:
        raise ValueError('This device already has generated geometry. Use Regenerate linked layout to review replacement.')
    c['shapes'].extend(data['shapes']);c.setdefault('layout_pins',[]).extend(data['pins']);c.setdefault('pdk_layouts',[]).append(data['record'])
    configure_connectivity(p['pdk']);return data


def configure_connectivity(tech):
    ls=layers(tech)
    tech['connectivity']={'conductors':[ls['li'],ls['m1'],ls['m2']],
        'vias':[[ls['li'],ls['mcon'],ls['m1']],[ls['m1'],ls['via'],ls['m2']]]}


def regenerate_mos(p,cid,did):
    c=next(c for c in p['cells'] if c['id']==cid)
    old=next((r for r in c.get('pdk_layouts',[]) if r['device_id']==did),None)
    if not old:raise ValueError('No generated footprint is linked to this device.')
    if old.get('transformed'):raise ValueError('This footprint was rotated or mirrored. Regenerate the complete cell, or restore its original orientation before individual regeneration.')
    d=resolved(p,cid,next(d for d in c['devices'] if d['id']==did));data=mos(p['pdk'],d,*old['origin'])
    c['shapes']=[s for s in c['shapes'] if s.get('generated_device')!=did]+data['shapes']
    c['layout_pins']=[pin for pin in c.get('layout_pins',[]) if pin['device_id']!=did]+data['pins']
    c['pdk_layouts']=[r for r in c['pdk_layouts'] if r['device_id']!=did]+[data['record']]
    validate(p)


def inverter_devices(p,cid):
    c=next(c for c in p['cells'] if c['id']==cid)
    if len(c['devices'])!=2 or {d['kind'] for d in c['devices']}!={'NMOS','PMOS'}:
        raise ValueError('Select an inverter cell containing exactly one NMOS and one PMOS; keep sources and load in a separate testbench.')
    n=resolved(p,cid,next(d for d in c['devices'] if d['kind']=='NMOS'));q=resolved(p,cid,next(d for d in c['devices'] if d['kind']=='PMOS'))
    for d in (n,q):specification(p['pdk'],d)
    a,b=n['nets'],q['nets']
    if not (a['d']==b['d'] and a['g']==b['g'] and a['s']==a['b'] and b['s']==b['b'] and len({a['d'],a['g'],a['s'],b['s']})==4):
        raise ValueError('Inverter needs common gates/input and drains/output, with each body tied to its own source supply.')
    if set(c['ports'])!={a['g'],a['d'],a['s'],b['s']}:
        raise ValueError('Expose the inverter input, output, power and ground as four cell ports.')
    return n,q


def generate_inverter(p,cid,replace=False):
    c=next(c for c in p['cells'] if c['id']==cid);n,q=inverter_devices(p,cid);ls=layers(p['pdk'])
    if c['shapes'] or c.get('layout_instances'):
        if not replace:raise ValueError('This cell already contains layout. Review regeneration before replacing it.')
        if not c.get('inverter_layout'):raise ValueError('Regeneration only replaces a cell previously created by the inverter generator.')
    c['shapes']=[];c['layout_pins']=[];c['layout_texts']=[];c['layout_ports']=[];c['pdk_layouts']=[];c['layout_instances']=[]
    nw=specification(p['pdk'],n)['dimensions_nm']['w'];py=nw+5000
    for d,y in ((n,0),(q,py)):install_mos(p,cid,d['id'],0,y)
    pins={(r['device_id'],r['pin']):r['point'] for r in c['layout_pins']}
    def wire(key,points,net):
        c['shapes'].append({'id':uid(),'kind':'path','layer':ls[key],'points':points,'width':340,'net':net,'device_id':'','generated_route':True})
    for d in (n,q):wire('m1',[pins[d['id'],'b'],pins[d['id'],'s']],d['nets']['s'])
    nd,pd=pins[n['id'],'d'],pins[q['id'],'d'];right=max(nd[0],pd[0])+1000
    wire('m1',[nd,[right,nd[1]],[right,pd[1]],pd],n['nets']['d'])
    ng,pg=pins[n['id'],'g'],pins[q['id'],'g']
    wire('m2',[ng,[ng[0],pg[1]],pg] if ng[0]!=pg[0] else [ng,pg],n['nets']['g'])
    for px,yy in (ng,pg):
        for key,half in [('via',75),('m2',170)]:c['shapes'].append(rect(ls[key],px-half,yy-half,2*half,2*half,net=n['nets']['g'] if key=='m2' else ''))
    # Text uses actual PDK label datatypes, not decorative names on drawing layers.
    for net,key,pt in [(n['nets']['s'],'m1label',pins[n['id'],'b']), (q['nets']['s'],'m1label',pins[q['id'],'b']), (n['nets']['d'],'m1label',[right,nd[1]]), (n['nets']['g'],'m2label',ng)]:
        c['layout_texts'].append({'layer':ls[key],'text':net,'x':pt[0],'y':pt[1],'rotation':0})
    from .physical_cells import assign_port
    for net,key,pt in [(n['nets']['s'],'m1',pins[n['id'],'b']),(q['nets']['s'],'m1',pins[q['id'],'b']),(n['nets']['d'],'m1',[right,nd[1]]),(n['nets']['g'],'m2',ng)]:assign_port(p,cid,net,ls[key],pt)
    c['inverter_layout']={'api':API,'device_ids':[n['id'],q['id']]}
    c['layout_label_mode']='explicit'
    validate(p);return p


def audit(p,cid):
    c=next(c for c in p['cells'] if c['id']==cid);ds={d['id']:d for d in c['devices']};issues=[]
    for r in c.get('pdk_layouts',[]):
        d=ds.get(r['device_id']);message=''
        if d is None:message='Generated layout belongs to a deleted schematic device.'
        else:
            try:
                if specification(p['pdk'],resolved(p,cid,d))!=r['spec']:message=d['name']+': model, dimensions, parameters or nets changed. Regenerate and verify the layout.'
            except ValueError as e:message=str(e)
        if message:issues.append({'severity':'error','code':'PDK.STALE','object':r['device_id'],'message':message,'fingerprint':digest(message)})
    return issues


def reference_project(tech):
    layers(tech)
    p=example('empty');link_technology(p,tech);p['name']='Custom SKY130 inverter';top=p['cells'][0];top['name']='testbench'
    c={'id':uid(),'name':'custom_inverter','ports':['A','Y','VPWR','VGND'],'devices':[],'shapes':[]}
    p['cells'].append(c)
    catalog=tech['simulation']['catalog']
    for kind,name,width,supply in [('NMOS','MN1','1u','VGND'),('PMOS','MP1','2u','VPWR')]:
        key=next(k for k,b in catalog.items() if not b.get('unavailable') and b['model']==MODELS[kind] and b['pin_order']==['d','g','s','b'] and b.get('emit_parameters',{}).get('w')=='w')
        d=create_device(p['pdk'],key,name,350,400 if kind=='NMOS' else 180);d['params'].update(w=width,l='0.15u');d['nets']={'d':'Y','g':'A','s':supply,'b':supply};c['devices'].append(d)
    top['devices']=[device('V','VDD',140,180,value='1.8',nets={'p':'vdd','n':'0'}),device('V','VIN',140,400,nets={'p':'vin','n':'0'},source={'type':'pulse','low':'0','high':'1.8','period':'20n','delay':'2n','duty':'0.5','ac':'1'}),device('X','XINV',400,280,cell=c['id'],nets={'A':'vin','Y':'vout','VPWR':'vdd','VGND':'0'}),device('C','CL',650,280,value='5f',nets={'p':'vout','n':'0'})]
    p['analysis'].update(type='tran',step='20p',stop='62n',corner='nominal')
    from .wiring import migrate
    for cell in p['cells']:migrate(cell,p)
    return validate(p),c['id']
