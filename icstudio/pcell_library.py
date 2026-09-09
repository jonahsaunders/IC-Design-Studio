"""Portable, declarative PCells: bounded arithmetic and explicit layer mappings."""
from .model import clone, digest, uid, validate, NAME, NET
from .design_ops import value
from .layout import rect, polygon, kdb


def validate_definition(definition):
    d=definition
    if not isinstance(d,dict) or d.get('version')!=1 or not NAME.fullmatch(d.get('name','')):
        raise ValueError('A PCell definition needs version 1 and a valid name.')
    if not isinstance(d.get('revision'),str) or not 1<=len(d['revision'])<=80:raise ValueError('Declare a PCell revision.')
    params=d.get('parameters',{})
    if not isinstance(params,dict) or len(params)>32:raise ValueError('PCells support at most 32 parameters.')
    for name,spec in params.items():
        if not NAME.fullmatch(name) or name=='i' or not isinstance(spec,dict):raise ValueError('Invalid PCell parameter; i is reserved for repetition.')
        if any(type(spec.get(k)) is not int for k in ('default','min','max','step')):
            raise ValueError('Parameters require integer default, min, max and step values.')
        if spec['step']<=0 or not -100000000<=spec['min']<=spec['default']<=spec['max']<=100000000:
            raise ValueError('Invalid PCell parameter bounds.')
        if (spec['default']-spec['min'])%spec['step']:raise ValueError('The PCell default does not match its step.')
    primitives=d.get('shapes',[])
    if not isinstance(primitives,list) or not 1<=len(primitives)<=256:raise ValueError('Define 1–256 shape templates.')
    roles=set()
    for s in primitives:
        if not isinstance(s,dict) or s.get('kind') not in ('rect','path') or not NAME.fullmatch(s.get('role','')) or s['role'] in roles:
            raise ValueError('Use rectangle or path templates with unique, valid roles.')
        roles.add(s['role'])
        if not isinstance(s.get('layer'),str) or not NAME.fullmatch(s['layer']):raise ValueError('Declare each template layer.')
        if s.get('net') and not NET.fullmatch(s['net']):raise ValueError('Invalid template net.')
    ports=d.get('ports',[])
    if not isinstance(ports,list) or len(ports)>64 or len({v.get('name') for v in ports})!=len(ports):raise ValueError('Use at most 64 distinct PCell ports.')
    if any(not NAME.fullmatch(v.get('name','')) for v in ports):raise ValueError('Use valid PCell port names.')
    return d


def register(p, definition):
    validate_definition(definition); q=clone(p)
    q.setdefault('pcell_library',{})[definition['name']]=clone(definition)
    # Validate default geometry before accepting a library update.
    build(q,definition['name'],{})
    p['pcell_library']=q['pcell_library'];return definition['name']


def build(p, name, parameters):
    d=validate_definition(p.get('pcell_library',{}).get(name)); specs=d.get('parameters',{})
    if set(parameters)-set(specs):raise ValueError('Unknown PCell parameter: '+', '.join(sorted(set(parameters)-set(specs))))
    values={n:parameters.get(n,s['default']) for n,s in specs.items()}
    for n,v in values.items():
        spec=specs[n]
        if type(v) is not int or not spec['min']<=v<=spec['max'] or (v-spec['min'])%spec['step']:
            raise ValueError(n+': value is outside the declared bounds or step.')
    grid=p['pdk']['grid'];layers={l['name']:l for l in p['pdk']['layers']};shapes=[]
    def number(raw,context,geometry=True):
        try:v=value(raw,context)
        except (SyntaxError,ZeroDivisionError,OverflowError,TypeError) as exc:raise ValueError('Invalid PCell arithmetic expression.') from exc
        if not v.is_integer() or abs(v)>100000000 or geometry and int(v)%grid:raise ValueError('PCell geometry must use integer on-grid nanometres within ±100 mm.')
        return int(v)
    for template in d['shapes']:
        layer=template['layer']
        if layer not in layers:raise ValueError('PCell layer is not mapped: '+layer)
        count=number(template.get('repeat',1),values,False)
        if not 1<=count<=256 or len(shapes)+count>5000:raise ValueError('PCell repetition supports 1–256 copies and 5,000 shapes total.')
        for i in range(count):
            context={**values,'i':i};role=template['role']+'/'+str(i)
            if template['kind']=='rect':
                x,y,w,h=[number(template[k],context) for k in ('x','y','width','height')]
                if min(w,h)<max(grid,layers[layer]['width']):raise ValueError(role+': rectangle is below the declared minimum width.')
                s=rect(layer,x,y,w,h,net=template.get('net',''))
            else:
                pts=template.get('points',[])
                if not 2<=len(pts)<=256 or any(len(pt)!=2 for pt in pts):raise ValueError('PCell paths need 2–256 coordinate pairs.')
                pts=[[number(v,context) for v in pt] for pt in pts];width=number(template['width'],context)
                if width<max(grid,layers[layer]['width']) or width%(2*grid):raise ValueError('PCell path width must meet the minimum and twice-grid rule.')
                if any(a==b or a[0]!=b[0] and a[1]!=b[1] for a,b in zip(pts,pts[1:])):raise ValueError('PCell paths must be Manhattan with distinct vertices.')
                s={'id':uid(),'kind':'path','layer':layer,'points':pts,'width':width,'net':template.get('net',''),'device_id':''}
            s['library_role']=role;shapes.append(s)
    ports=[]
    for v in d.get('ports',[]):
        point=[number(x,values) for x in v.get('point',[])]
        if len(point)!=2 or v.get('layer') not in layers:raise ValueError('Each PCell port needs a mapped layer and a coordinate pair.')
        if not any(s['layer']==v['layer'] and s.get('net')==v['name'] and polygon(s).inside(kdb().Point(*point)) for s in shapes):
            raise ValueError('PCell port '+v['name']+' must land on geometry with its net name.')
        ports.append({'name':v['name'],'layer':v['layer'],'point':point})
    return {'shapes':shapes,'layout_ports':ports,'ports':[v['name'] for v in ports],
            'library_pcell':{'name':name,'revision':d['revision'],'definition_hash':digest(d),
                'parameters':values,'pdk_hash':digest(p['pdk']),
                'qualification':d.get('qualification','Declared geometry only; run the process DRC and extraction decks.')}}


def geometry_hash(cell):
    return digest({k:cell.get(k,[]) for k in ('shapes','layout_ports','ports')})


def create_cell(p, cell_name, name, parameters):
    q=clone(p);c={'id':uid(),'name':cell_name,'devices':[],**build(p,name,parameters)}
    c['library_pcell']['geometry_hash']=geometry_hash(c);q['cells'].append(c);validate(q)
    p['cells'].append(c);return c['id']


def regenerate(p, cid, parameters):
    q=clone(p);c=next(c for c in q['cells'] if c['id']==cid);record=c.get('library_pcell')
    if not record:raise ValueError('The active cell was not created from the PCell library.')
    if geometry_hash(c)!=record['geometry_hash']:raise ValueError('Generated cell geometry was edited. Restore it before regeneration.')
    data=build(p,record['name'],parameters)
    previous={s['library_role']:s['id'] for s in c['shapes']}
    for s in data['shapes']:
        if s['library_role'] in previous:s['id']=previous[s['library_role']]
    c.update(data);c['library_pcell']['geometry_hash']=geometry_hash(c);validate(q)
    from .physical_cells import reachable
    from .layout_topology import require_preserved
    for parent in p['cells']:
        if parent['id']!=cid and cid in reachable(p,parent['id'],True):require_preserved(p,q,parent['id'])
    next(c for c in p['cells'] if c['id']==cid).update(c);return c


def audit(p):
    rows=[]
    for c in p['cells']:
        r=c.get('library_pcell')
        if not r:continue
        definition=p.get('pcell_library',{}).get(r['name'])
        states=[]
        if r['definition_hash']!=digest(definition):states.append('Definition changed')
        if r['pdk_hash']!=digest(p['pdk']):states.append('Technology changed')
        if r['geometry_hash']!=geometry_hash(c):states.append('Geometry edited')
        rows.append({'cell_id':c['id'],'cell':c['name'],'name':r['name'],'state':'; '.join(states) or 'Current'})
    return rows
