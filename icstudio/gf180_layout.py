"""Bounded GF180MCU C standard 3.3 V MOS geometry, derived from locked Magic assets.

Native GDS drawing datatype 0 and port datatype 10 are process-specific.
W=1..10 um, L=.28..2 um, 5 nm grid, nf=m=mult=1. All four terminals are contacted.
"""
from .model import clone, uid, scalar, validate, digest, file_digest
from .catalog import binding_for, parameter_values, create_device, link_technology
from .layout import rect
from .sky130_layout import resolved

MASKS = {'nwell': (21,0), 'diff': (22,0), 'poly': (30,0), 'psdm': (31,0),
         'nsdm': (32,0), 'contact': (33,0), 'm1': (34,0), 'via': (35,0), 'm2': (36,0),
         'm1label': (34,10), 'm2label': (36,10)}
MODELS = {'NMOS': 'nfet_03v3', 'PMOS': 'pfet_03v3'}
API = 1


def layers(tech):
    if tech.get('package_lock',{}).get('id') != 'gf180mcuC': raise ValueError('Link a GF180MCU C package first.')
    by = {(l['gds'],l['datatype']): l['name'] for l in tech['layers']}
    return {key: by.get(pair, 'gf180_'+key) for key,pair in MASKS.items()}


def prepare(tech):
    from .process_adapters import GF180
    assets = GF180.engine_assets(tech)
    names = layers(tech); present = {(l['gds'],l['datatype']) for l in tech['layers']}
    colors = ['#bb9a64','#73c683','#ef8a83','#a785d9','#75abc7','#cccccc','#6b9cf0','#d8b46c','#bd90ec','#6b9cf0','#bd90ec']
    for (key,(gds,datatype)),color in zip(MASKS.items(), colors):
        if (gds,datatype) not in present:
            if any(l['name']==names[key] for l in tech['layers']): raise ValueError('Conflicting GF180 native layer name: '+names[key])
            width,space = {'m1':(230,230),'m2':(280,280),'via':(260,260),'contact':(220,250),
                           'poly':(180,240),'diff':(220,280),'nwell':(860,600)}.get(key,(0,0))
            tech['layers'].append({'name':names[key],'gds':gds,'datatype':datatype,'color':color,'width':width,'space':space})
    tech['native_layer_contract'] = {'adapter': 'gf180mcuC', 'api': API,
        'source': GF180.technology_file, 'sha256': file_digest(assets['technology'])}
    tech['connectivity'] = {'conductors':[names['m1'],names['m2']], 'vias':[[names['m1'],names['via'],names['m2']]]}


def specification(tech, d):
    layers(tech); b = binding_for(tech,d)
    if not b or b['model'] != MODELS.get(d['kind']) or set(d['nets']) != {'d','g','s','b'}:
        raise ValueError('Select a standard four-terminal GF180 nfet_03v3 or pfet_03v3.')
    values = parameter_values(b,d)
    if any(values.get(k,1) != 1 for k in ('nf','m','mult')):
        raise ValueError('GF180 native geometry supports one finger and multiplicity one.')
    if any(b.get('emit_parameters',{}).get(k) != k for k in ('w','l')):
        raise ValueError('Use a standard GF180 symbol without dimension transformations.')
    size = {}
    for k,minimum,maximum in (('w',1000,10000),('l',280,2000)):
        raw = scalar(d['params'][k])*1e9; n = round(raw)
        if abs(raw-n)>1e-6 or n%5 or not minimum<=n<=maximum:
            raise ValueError(f'{d["name"]}: {k.upper()} must be {minimum/1000:g}–{maximum/1000:g} µm on the 5 nm grid.')
        size[k] = n
    return {'api': API,'model_ref': clone(d.get('model_ref')),'model':b['model'], 'kind':d['kind'],
            'dimensions_nm':size,'values':values,'nets':clone(d['nets'])}


def mos(tech,d,x=0,y=0):
    spec = specification(tech,d); ls = layers(tech); w,l = [spec['dimensions_nm'][k] for k in ('w','l')]
    if any(type(v) is not int or v%5 for v in (x,y)): raise ValueError('Place devices on the 5 nm grid.')
    shapes=[]; pins=[]
    def box(key,a,b,c,e,net=''):
        s=rect(ls[key],x+a,y+b,c-a,e-b,d['id'],net);s['generated_device']=d['id'];shapes.append(s)
    box('diff',-800,0,l+800,w)
    box('psdm' if d['kind']=='PMOS' else 'nsdm',-1100,-300,l+1100,w+300)
    gate=5*round(l/10);cy=5*round(w/10)
    box('poly',0,-1000,l,w+300);box('poly',gate-250,-1050,gate+250,-550)
    box('diff',-2850,cy-350,-2150,cy+350)
    box('nsdm' if d['kind']=='PMOS' else 'psdm',-3150,cy-650,-1850,cy+650)
    if d['kind']=='PMOS':box('nwell',-3450,-1500,l+1400,w+700)
    for pin,px,py in (('s',-500,cy),('d',l+500,cy),('g',gate,-800),('b',-2500,cy)):
        # 0.22 um GDS contact becomes the Magic contact with its 5 nm surround.
        box('contact',px-110,py-110,px+110,py+110)
        box('m1',px-200,py-200,px+200,py+200,d['nets'][pin])
        pins.append({'id':uid(),'device_id':d['id'],'pin':pin,'layer':ls['m1'],'point':[x+px,y+py]})
    return {'shapes':shapes,'pins':pins,'record':{'device_id':d['id'],'spec':spec,'origin':[x,y]}}


def install_mos(p,cid,did,x=0,y=0):
    c=next(c for c in p['cells'] if c['id']==cid)
    if any(r['device_id']==did for r in c.get('pdk_layouts',[])):raise ValueError('This device already has generated geometry. Review regeneration.')
    d=resolved(p,cid,next(d for d in c['devices'] if d['id']==did));specification(p['pdk'],d);prepare(p['pdk']);data=mos(p['pdk'],d,x,y)
    c['shapes'].extend(data['shapes']);c.setdefault('layout_pins',[]).extend(data['pins']);c.setdefault('pdk_layouts',[]).append(data['record']);return data


def regenerate_mos(p,cid,did):
    c=next(c for c in p['cells'] if c['id']==cid);old=next((r for r in c.get('pdk_layouts',[]) if r['device_id']==did),None)
    if not old or old.get('transformed'):raise ValueError('Regenerate the full cell after a device has been rotated or mirrored.')
    d=resolved(p,cid,next(d for d in c['devices'] if d['id']==did));data=mos(p['pdk'],d,*old['origin'])
    c['shapes']=[s for s in c['shapes'] if s.get('generated_device')!=did]+data['shapes'];c['layout_pins']=[v for v in c['layout_pins'] if v['device_id']!=did]+data['pins'];c['pdk_layouts']=[r for r in c['pdk_layouts'] if r['device_id']!=did]+[data['record']];validate(p)


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
        for key,half in (('via',130),('m1',220),('m2',220)):
            c['shapes'].append(rect(ls[key],px-half,yy-half,half*2,half*2,net=n['nets']['g'] if key!='via' else ''))
    from .physical_cells import assign_port
    for net,key,pt in ((n['nets']['s'],'m1',pins[n['id'],'b']),(q['nets']['s'],'m1',pins[q['id'],'b']),(n['nets']['d'],'m1',[right,nd[1]]),(n['nets']['g'],'m2',ng)):
        assign_port(p,cid,net,ls[key],pt)
    c['inverter_layout']={'api':API,'process':'gf180mcuC','device_ids':[n['id'],q['id']]};validate(p);return p


def audit(p,cid):
    c=next(c for c in p['cells'] if c['id']==cid);ds={d['id']:d for d in c['devices']};out=[]
    for r in c.get('pdk_layouts',[]):
        try:
            if r['device_id'] not in ds or specification(p['pdk'],resolved(p,cid,ds[r['device_id']]))!=r['spec']:
                raise ValueError('GF180 model, dimensions, parameters or nets changed. Regenerate and verify the layout.')
        except ValueError as exc:out.append({'severity':'error','code':'PDK.STALE','object':r['device_id'],'message':str(exc),'fingerprint':digest(str(exc))})
    return out


def reference_project(tech):
    from .model import example, device
    from .testbenches import create
    p=example('empty');link_technology(p,tech);p['name']='GF180 3.3 V inverter';top=p['cells'][0];top['name']='inverter_fixture'
    c={'id':uid(),'name':'gf180_inverter','ports':['A','Y','VPWR','VGND'],'devices':[],'shapes':[]};p['cells'].append(c)
    for kind,name,width,supply in (('NMOS','MN1','2u','VGND'),('PMOS','MP1','4u','VPWR')):
        key=next(k for k,b in tech['simulation']['catalog'].items() if not b.get('unavailable') and b['model']==MODELS[kind] and b['pin_order']==['d','g','s','b'] and b.get('emit_parameters',{}).get('w')=='w')
        d=create_device(p['pdk'],key,name,350,400 if kind=='NMOS' else 180);d['params'].update(w=width,l='.28u');d['nets']={'d':'Y','g':'A','s':supply,'b':supply};c['devices'].append(d)
    top['devices']=[device('V','VDD',140,180,value='3.3',nets={'p':'vdd','n':'0'}),device('V','VIN',140,400,nets={'p':'vin','n':'0'},source={'type':'pulse','low':'0','high':'3.3','period':'20n','delay':'2n','duty':'.5','ac':'1'}),device('X','XDUT',400,280,cell=c['id'],nets={'A':'vin','Y':'vout','VPWR':'vdd','VGND':'0'}),device('C','CL',650,280,value='10f',nets={'p':'vout','n':'0'})]
    p['analysis'].update(type='tran',step='20p',stop='62n',corner='nominal')
    from .wiring import migrate
    for cell in p['cells']:migrate(cell,p)
    t=create(p,top['id'],'inverter_transient');t['measurements']=[{'name':'propagation_delay','kind':'delay','input':'vin','node':'vout','threshold':'1.65','min':'1p','max':'2n'},{'name':'output_low','kind':'voltage','node':'vout','at':'8n','min':'-.05','max':'.1'},{'name':'output_high','kind':'voltage','node':'vout','at':'18n','min':'3.2','max':'3.35'}];t['characterization']={'kind':'sweep','target':'CL.value','values':['5f','10f','20f'],'compare_layout':True};p['testbenches']=[t]
    return validate(p),c['id']
