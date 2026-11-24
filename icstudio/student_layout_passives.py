"""Editable capacitor routing labs with geometry-derived electrical checks."""

import math

from .layout import drc, kdb, polygon, rect
from .model import clone, device, scalar, uid
from .physical import capacitance_estimate, connectivity

LABS = {'mim-plate','decoupling'}
SHEET_OHM = .25
DECAP = 200e-12
FEED_OHM = 70
PULSE_A = .002
PULSE_SECONDS = .8e-9


def _route(net, layer, points, width, key):
    clean = [list(p) for i,p in enumerate(points) if not i or p!=points[i-1]]
    return dict(id=key, kind='path', layer=layer, points=clean, width=width, net=net, device_id='')


def _cell(p):
    return next(c for c in p['cells'] if c['id']==p['top'])


def _port(c,name,layer,point):
    c.setdefault('layout_ports',[]).append(dict(name=name,layer=layer,point=list(point)))


def _pin(c, part, name, x, y):
    c['layout_pins'].append(dict(id=uid(),device_id=part['id'],pin=name,layer='metal1',point=[x,y]))


def mim(p,c):
    from .catalog import create_device, link_technology
    from .sky130_devices import configure_connectivity, layers
    from .sky130_layout import install_mos
    from .student_analog import bundled_technology

    link_technology(p,bundled_technology())
    model = 'sky130_fd_pr/cap_mim_m3_1.sym'
    cap = create_device(p['pdk'],model,'CMIM',470,240)
    cap['model_params'].update(w='10',l='10',mf='1')
    cap['nets'] = dict(c0='sense',c1='ref')
    c['ports'] = ['sense','ref']
    c['devices'].append(cap)
    install_mos(p,c['id'],cap['id'],0,0)
    configure_connectivity(p['pdk'])
    layer = layers(p['pdk'])['m4']
    p['pdk']['parasitics'] = {layer:dict(cap_f_per_um2='0.025f',edge_f_per_um='0.006f')}
    _port(c,'sense',layer,(-10000,5000))
    _port(c,'ref',layer,(25000,5000))
    c['shapes'].append(_route('ref',layer,[(11500,5000),(25000,5000)],600,'mim-reference'))
    route_mim(p,24000)


def route_mim(p,height,locked=()):
    c = _cell(p)
    layer = next(row['layer'] for row in c['layout_ports'] if row['name']=='sense')
    if layer in locked:
        raise ValueError('Unlock the MIM access layer first.')
    y = 5000
    points = [(-10000,y),(-5000,y),(-5000,y+height),(5000,y+height),(5000,y)]
    c['shapes'] = [s for s in c['shapes'] if s['id']!='mim-sense'] + [_route('sense',layer,points,600,'mim-sense')]


def decoupling(p,c):
    rails = dict(p='local',n='return')
    c['devices'] = [
        device('I','ILOAD',230,230,nets=rails,value='0',
               source=dict(type='pulse',low='0',high='2m',delay='1n',period='10n',duty='.08',ac='0')),
        device('C','CDEC',600,245,value='200p',nets=rails),
    ]
    c['ports'] = ['local','return']
    for pin,y,net in [('p',0,'local'),('n',12000,'return')]:
        c['shapes'].append(rect('metal1',-600,y-600,1200,1200,net=net))
        _pin(c,c['devices'][0],pin,0,y)
        _port(c,net,'metal1',(0,y))
    place_decap(p,40000)


def place_decap(p,distance,locked=()):
    if 'metal1' in locked:
        raise ValueError('Unlock Metal 1 to change the capacitor placement.')
    c = _cell(p)
    cap = next(d for d in c['devices'] if d['name']=='CDEC')
    c['shapes'] = [s for s in c['shapes'] if not s['id'].startswith('decap-')]
    c['layout_pins'] = [p for p in c['layout_pins'] if p['device_id']!=cap['id']]
    for pin,y,dy,net in [('p',0,4000,'local'),('n',12000,8000,'return')]:
        access = rect('metal1',distance-600,dy-600,1200,1200,net=net)
        access['id'] = 'decap-pad-'+pin
        c['shapes'] += [access,_route(net,'metal1',[(0,y),(distance,y),(distance,dy)],600,'decap-route-'+pin)]
        _pin(c,cap,pin,distance,dy)
    marker = rect('metal2',distance-1000,4200,2000,3600)
    marker['id'] = 'decap-body'
    c['shapes'].append(marker)


def dimension(p,key):
    c = _cell(p)
    path = next(s for s in c['shapes'] if s['id']==('mim-sense' if key=='mim-plate' else 'decap-route-p'))
    if key=='mim-plate':
        return (max(y for _,y in path['points'])-5000)/1000
    return path['points'][-1][0]/1000


def _connected(p,c):
    result = connectivity(p,c['id'])
    if result['issues']:
        raise ValueError(result['issues'][0]['message'])
    for port in c['layout_ports']:
        nets = {group['net'] for group in result['net_regions'] for shape in group['shapes']
                if shape['layer']==port['layer'] and polygon(shape).inside(kdb().Point(*port['point']))}
        if nets != {port['name']}:
            raise ValueError('Connect the physical '+port['name']+' port to its own terminal.')


def _capacitance(p,c):
    rows = capacitance_estimate(p,c['id'])['capacitors']
    return sum(row['capacitance'] for row in rows if row['net']=='sense')


def measure(p,lab,step):
    c = _cell(p)
    _connected(p,c)
    issues = drc(p,c['id'])
    if issues:
        raise ValueError(issues[0]['message'])
    if lab=='mim-plate':
        from .sky130_layout import audit
        if len(c['devices'])!=1 or len(c['pdk_layouts'])!=1 or audit(p,c['id']):
            raise ValueError('Keep the original model-linked 10 × 10 µm MIM geometry.')
        cap = c['devices'][0]
        if cap['nets']!={'c0':'sense','c1':'ref'} or any(scalar(cap['model_params'][k])!=v for k,v in dict(w=10,l=10,mf=1).items()):
            raise ValueError('Preserve the top-plate assignment and active capacitor dimensions.')
        layer = c['layout_ports'][0]['layer']
        minimum = next(entry['width'] for entry in p['pdk']['layers'] if entry['name']==layer)
        if any(s['kind']=='path' and s['layer']==layer and s['width']<minimum for s in c['shapes']):
            raise ValueError('Keep both access routes at least as wide as the layer rule.')
        bare = clone(p)
        body = _cell(bare)
        body['shapes'] = [s for s in body['shapes'] if s.get('device_id')==cap['id']]
        baseline = _capacitance(bare,body)
        added = (_capacitance(p,c)-baseline)*1e15
        if (step=='baseline' and added <= .55) or (step=='repair' and not 0 < added <= .55):
            raise ValueError(f'The sense route adds {added:.3f} fF. Measure the original detour, then bring added capacitance below 0.55 fF.')
        return {'Added sense-route capacitance (fF)':round(added,4),'Active MIM area (µm²)':100}

    cap = next(d for d in c['devices'] if d['name']=='CDEC')
    if cap['kind']!='C' or not math.isclose(scalar(cap['value']),DECAP,rel_tol=1e-12,abs_tol=0):
        raise ValueError('Use the same 200 pF capacitor for both placements.')
    paths = [s for s in c['shapes'] if s['id'].startswith('decap-route-')]
    if len(paths)!=2 or {s['net'] for s in paths}!={'local','return'}:
        raise ValueError('Keep the independent supply and return branch routes.')
    squares = sum(sum(abs(a[0]-b[0])+abs(a[1]-b[1]) for a,b in zip(s['points'],s['points'][1:]))/s['width']
                  for s in paths)
    rloop = SHEET_OHM*squares
    initial = PULSE_A*FEED_OHM*rloop/(FEED_OHM+rloop)
    final = PULSE_A*FEED_OHM
    drop = (final - (final-initial)*math.exp(-PULSE_SECONDS/((FEED_OHM+rloop)*DECAP)))*1000
    if (step=='baseline' and drop <= 25) or (step=='repair' and drop > 25):
        raise ValueError(f'The load droops {drop:.2f} mV. Measure the distant capacitor first, then move it to meet 25 mV.')
    return {'Peak droop during 0.8 ns pulse (mV)':round(drop,3),'Capacitor loop resistance (Ω)':round(rloop,3),
            'Capacitance (pF)':200,'Capacitor distance (µm)':dimension(p,lab)}
