"""Spacious, deterministic single-finger analog reference placement and routing.

Metal1 terminal columns cross metal2 net buses only at explicit vias. These
editable reference layouts require external DRC/LVS after every change.
"""
from .model import uid, validate
from .layout import rect, polygon
from .sky130_layout import layers, resolved, specification, install_mos
from .physical_cells import assign_port


def generate(p, cid, replace=False):
    c = next(c for c in p['cells'] if c['id'] == cid)
    if not 2 <= len(c['devices']) <= 8 or any(d['kind'] not in ('NMOS','PMOS') for d in c['devices']):
        raise ValueError('This analog layout recipe supports 2–8 standard SKY130 MOS devices.')
    devices = [resolved(p,cid,d) for d in c['devices']]
    specs = [specification(p['pdk'],d) for d in devices]
    if any(int(s['values'].get('nf',1)) != 1 for s in specs):
        raise ValueError('The analog reference bank supports one finger per device.')
    if c['shapes'] or c.get('layout_instances'):
        if not replace or not c.get('analog_bank'):
            raise ValueError('Use an empty layout, or review regeneration of an existing analog bank.')
    for key in ('shapes','layout_pins','layout_ports','layout_texts','layout_instances','pdk_layouts'): c[key] = []
    ls = layers(p['pdk']); pitch = 24000
    for i,d in enumerate(devices): install_mos(p,cid,d['id'],i*pitch,0)
    top = max(polygon(s).bbox().top for s in c['shapes']) + 2500
    nets = list(dict.fromkeys([*c['ports'],*[n for d in devices for n in d['nets'].values()]]))
    buses = {net: top+4000*i for i,net in enumerate(nets)}
    by = {d['id']:d for d in devices}; left = -6000; right = (len(devices)-1)*pitch+14000
    def path(layer,points,net):
        s = dict(id=uid(),kind='path',layer=ls[layer],points=points,width=340,net=net,device_id='',generated_route=True)
        c['shapes'].append(s); return s['id']
    routes = {}
    for net,y in buses.items(): routes[net] = path('m2',[[left,y],[right,y]],net)
    for pin in c['layout_pins']:
        net = by[pin['device_id']]['nets'][pin['pin']]; x,y = pin['point']; end = buses[net]
        path('m1',[[x,y],[x,end]],net)
        for layer,half in (('via',75),('m1',170),('m2',170)):
            s = rect(ls[layer],x-half,end-half,2*half,2*half,net=net if layer!='via' else '')
            s['generated_route'] = True; c['shapes'].append(s)
    for net in c['ports']: assign_port(p,cid,net,ls['m2'],[left,buses[net]])
    from .analog_constraints import footprint
    constraints = []
    # Check equal corresponding footprints and placement symmetry for equal pairs.
    grouped = {}
    from .model import digest
    for d,s in zip(devices,specs): grouped.setdefault(digest({k:v for k,v in s.items() if k!='nets'}),[]).append(d['id'])
    for members in grouped.values():
        if len(members) != 2: continue
        centers = [footprint(p,cid,did)[2] for did in members]
        constraints.extend([dict(id=uid(),name='Equal analog pair',kind='matching',members=members),
            dict(id=uid(),name='Analog pair axis',kind='symmetry',members=members,axis='x',coordinate=sum(v[0] for v in centers)/2)])
    old = set(c.get('analog_bank',{}).get('constraint_ids',[]))
    c['analog_constraints'] = [v for v in c.get('analog_constraints',[]) if v['id'] not in old]+constraints
    c['analog_bank'] = dict(api=1,pitch_nm=pitch,buses=buses,routes=routes,constraint_ids=[v['id'] for v in constraints],
        scope='Single-finger reference routing; equal pairs have geometry and symmetry checks. No statistical mismatch or density optimization.')
    validate(p); return p
