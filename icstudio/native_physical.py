"""Explicit electrical-to-geometry mappings for native device definitions."""
from .model import clone, scalar

ROLES = {'R': ('p','n'), 'C': ('p','n'), 'NMOS': ('d','g','s','b'), 'PMOS': ('d','g','s','b')}


def proxy(device, binding=None):
    b = binding or device.get('physical_binding', {})
    kind = b.get('kind'); roles = b.get('terminals', {})
    if kind not in ROLES or set(roles) != set(ROLES[kind]) or set(roles.values()) != set(device['nets']) or len(set(roles.values())) != len(roles):
        raise ValueError('Map each geometry terminal to exactly one electrical terminal.')
    parameters = device.get('native_spice', {}).get('parameters', {})
    q = clone(device); q.pop('native_spice', None); q.pop('physical_binding', None)
    q.pop('model_ref', None); q['kind'] = kind; q['nets'] = {k:device['nets'][v] for k,v in roles.items()}
    def value(key):
        mapping=b.get('parameters',{}).get(key,{})
        name=mapping.get('name');scale=scalar(mapping.get('scale',1))
        if name not in parameters or scale<=0:raise ValueError('Choose a numeric native parameter and a positive unit multiplier for '+key+'.')
        number=scalar(parameters[name])*scale
        if number<=0:raise ValueError('Geometry requires a positive '+key+'; expressions must be resolved explicitly.')
        return str(number)
    if kind in ('R','C'):q['value']=value('value')
    else:q['params']={**q['params'],'w':value('w'),'l':value('l')}
    return q


def bind(p,cid,did,binding):
    d=next(d for c in p['cells'] if c['id']==cid for d in c['devices'] if d['id']==did)
    if d.get('native_spice',{}).get('type')!='device' or d['kind']=='X':raise ValueError('Select a native leaf device.')
    proxy(d,binding);d['physical_binding']=clone(binding)


def build(p,cid,did,spec):
    from .parametric import build as generate,electrical_signature
    q=clone(p);d=next(d for c in q['cells'] if c['id']==cid for d in c['devices'] if d['id']==did)
    original=clone(d);replacement=proxy(d);d.clear();d.update(replacement)
    spec=clone(spec);spec.pop('kind',None)
    if d['kind']=='R' and not spec.get('width'):spec['width']=1000
    data=generate(q,cid,did,spec)
    for pin in data['pins']:pin['pin']=original['physical_binding']['terminals'][pin['pin']]
    data['record']['source_signature']=electrical_signature(original)
    data['record']['binding']=clone(original['physical_binding'])
    data['record']['qualification']+=' Explicit native parameter/terminal mapping; this mapping alone does not establish model-to-layout equivalence.'
    return data
