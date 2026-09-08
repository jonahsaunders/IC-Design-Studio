"""Three-stage hierarchical SKY130 reference built from one reusable inverter."""
from .model import clone,uid,device,validate
from .sky130_layout import reference_project,generate_inverter,layers
from .physical_cells import place,ports,assign_port,instance_pins
from .layout import rect


def reference(tech):
    p,inv_id=reference_project(tech);p['name']='SKY130 ring oscillator';inv=next(c for c in p['cells'] if c['id']==inv_id);inv['name']='inverter'
    ring={'id':uid(),'name':'ring_oscillator','ports':['N1','N2','OUT','VPWR','VGND'],'devices':[],'shapes':[]}
    for index,(a,y) in enumerate((('OUT','N1'),('N1','N2'),('N2','OUT'))):ring['devices'].append(device('X','X'+str(index+1),220+250*index,250,cell=inv_id,nets={'A':a,'Y':y,'VPWR':'VPWR','VGND':'VGND'}))
    p['cells'].append(ring);bench=p['cells'][0];bench['name']='ring_testbench';bench['devices']=[device('V','VDD',150,180,value='1.8',nets={'p':'vdd','n':'0'}),device('X','XDUT',400,280,cell=ring['id'],nets={'N1':'n1','N2':'n2','OUT':'out','VPWR':'vdd','VGND':'0'}),device('C','CL',650,280,value='5f',nets={'p':'out','n':'0'})]
    for c in (ring,bench):
        for key in ('wires','labels','junctions'):c.pop(key,None)
        from .wiring import migrate
        migrate(c,p)
    from .testbenches import create
    t=create(p,bench['id'],'ring_nominal');t['analysis'].update(type='tran',step='2p',stop='8n',uic=True,corner='nominal');t['probes']=['n1','n2','out'];t['initial_conditions']={'n1':'0','n2':'1.8','out':'0'};t['measurements']=[{'name':'oscillation','kind':'frequency','node':'out','threshold':'.9','start':'2n','stop':'8n','min_cycles':5,'max_period_variation':'.1','min':'10meg','max':'100G'},{'name':'output_range','kind':'range','node':'out','start':'2n','stop':'8n','min':'-0.2','max':'2.0'}]
    p['testbenches']=[t];p['analysis']=clone(t['analysis']);validate(p);return p,ring['id'],t['id']


def generate(p,cid,replace=False):
    c=next(c for c in p['cells'] if c['id']==cid);ds=c['devices']
    if len(ds)!=3 or any(d['kind']!='X' for d in ds) or len({d['cell'] for d in ds})!=1:raise ValueError('The ring layout recipe needs three instances of one inverter cell.')
    if c['ports']!=['N1','N2','OUT','VPWR','VGND'] or [d['nets'] for d in ds]!=[{'A':a,'Y':y,'VPWR':'VPWR','VGND':'VGND'} for a,y in [('OUT','N1'),('N1','N2'),('N2','OUT')]]:raise ValueError('The ring recipe requires the reference three-stage connectivity and interface.')
    if c['shapes'] or c.get('layout_instances'):
        if not replace or not c.get('ring_layout'):raise ValueError('Review regeneration before replacing an existing ring layout.')
    child=next(c for c in p['cells'] if c['id']==ds[0]['cell'])
    if not child['shapes']:generate_inverter(p,child['id'])
    ls=layers(p['pdk']);interface={port['name']:port for port in ports(p,child['id'])}
    if set(interface)!=set(child['ports']):raise ValueError('Assign every inverter layout port first.')
    from .design_ops import flatten_layout
    from .layout import polygon
    boxes=[polygon(s).bbox() for s in flatten_layout(p,child['id'])];left=min(b.left for b in boxes);right=max(b.right for b in boxes);bottom=min(b.bottom for b in boxes);top=max(b.top for b in boxes)
    # Generous access corridors stay outside the child geometry. The recipe is
    # intentionally orthogonal; each derived route is checked with the real PDK.
    pitch=1000*((right-left+4500+999)//1000);ground_y=1000*((bottom-1500)//1000);power_y=1000*((top+2000+999)//1000);signal_y=bottom-500;return_y=ground_y-1000
    if any(interface[n]['layer']!=ls[layer] for n,layer in [('A','m2'),('Y','m1'),('VGND','m1'),('VPWR','m1')]):raise ValueError('The ring recipe requires the inverter generator\'s m1/m2 access interface.')
    c.update(shapes=[],layout_instances=[],layout_pins=[],layout_texts=[],layout_ports=[],layout_label_mode='explicit')
    for i,d in enumerate(ds):place(p,cid,d['id'],i*pitch,0)
    pins={(pin['device_id'],pin['pin']):pin['point'] for pin in instance_pins(p,cid)}
    def wire(layer,points,net):
        points=[pt for i,pt in enumerate(points) if not i or pt!=points[i-1]]
        if len(points)>1:c['shapes'].append({'id':uid(),'kind':'path','layer':ls[layer],'points':points,'width':340,'net':net,'device_id':'','generated_route':True})
    def via(pt,net):
        for layer,size in [('m1',340),('via',150),('m2',340)]:c['shapes'].append(rect(ls[layer],pt[0]-size//2,pt[1]-size//2,size,size,net=net if layer!='via' else ''))
    for name,y in [('VGND',ground_y),('VPWR',power_y)]:
        taps=[]
        for d in ds:
            pt=pins[d['id'],name];at=[pt[0],y];wire('m2',[pt,at],name);via(pt,name);taps.append(at)
        wire('m2',[taps[0],taps[-1]],name);assign_port(p,cid,name,ls['m2'],taps[0])
    for i,d in enumerate(ds):
        source=pins[d['id'],'Y'];target=pins[ds[(i+1)%3]['id'],'A'];y=signal_y if i<2 else return_y
        wire('m1',[source,[source[0],y],[target[0],y],target],d['nets']['Y']);via(target,d['nets']['Y']);assign_port(p,cid,d['nets']['Y'],ls['m1'],source)
    c['ring_layout']={'api':1,'inverter_cell':child['id'],'pitch_nm':pitch};validate(p);return p
