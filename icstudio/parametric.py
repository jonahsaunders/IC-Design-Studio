"""Schematic-linked parametric geometry with stable roles and declared technology rules."""
import math
from .model import clone,uid,scalar,digest,validate
from .layout import rect,guard_ring


def rules(tech):
    declared=tech.get('pcell_rules')
    if declared:return clone(declared)
    if tech.get('revision')=='generic-1':
        return {'qualification':'Illustrative teaching geometry; electrical coefficients are declared examples, not calibrated process data.',
          'resistor':{'body':'poly','terminal':'metal1','sheet_ohm':100.,'min_width':500},
          'capacitor':{'bottom':'metal1','top':'metal2','f_per_um2':1e-15},
          'mos':{'active':'active','gate':'poly','terminal':'metal1','well':'nwell'},
          'contact':{'lower':'metal1','cut':'via1','upper':'metal2','size':150,'enclosure':100},
          'guard_ring':{'metal':'metal1','active':'active','cut':'contact','cut_size':150,'pitch':400,'enclosure':100}}
    raise ValueError('This technology has no declared parametric-device rules. Use a supported process MOS recipe or register pcell_rules with explicit layer mappings and coefficients.')


def build(p,cid,did,spec):
    cell=next(c for c in p['cells'] if c['id']==cid);d=next((d for d in cell['devices'] if d['id']==did),None);kind=spec.get('kind') or {'R':'resistor','C':'capacitor','NMOS':'mos','PMOS':'mos'}.get((d or {}).get('kind'))
    if d and d.get('native_spice'):
        from .native_physical import build as native_build
        return native_build(p,cid,did,spec)
    config=rules(p['pdk']);cfg=config.get(kind)
    if not cfg:raise ValueError('No '+str(kind)+' recipe is declared by this technology.')
    grid=p['pdk']['grid']
    if scalar(spec.get('width',0))<0:raise ValueError('Width must be positive, or blank for automatic sizing.')
    x=int(spec.get('x',0));y=int(spec.get('y',0));ls={l['name']:l for l in p['pdk']['layers']};shapes=[];pins=[]
    def snap(v):return max(grid,math.ceil(v/grid)*grid)
    def box(role,layer,a,b,w,h,net=''):
        if layer not in ls:raise ValueError('Recipe layer is not mapped: '+layer)
        if min(w,h)<ls[layer]['width']:raise ValueError(role+': dimensions are below the declared minimum width.')
        s=rect(layer,x+a,y+b,w,h,did or '',net);s['pcell_role']=role;shapes.append(s);return s
    def pin(name,layer,pt):
        if d is None or name not in d['nets']:raise ValueError('Recipe terminal differs from the schematic device.')
        pins.append({'id':uid(),'device_id':did,'pin':name,'layer':layer,'point':[x+pt[0],y+pt[1]]})
    if x%grid or y%grid:raise ValueError('Place the generator origin on the technology grid.')
    electrical={}
    if kind=='resistor':
        if not d or d['kind']!='R':raise ValueError('Choose a resistor instance.')
        w=snap(max(int(spec.get('width',1000)),cfg['min_width']));sheet=scalar(cfg['sheet_ohm'])
        if sheet<=0:raise ValueError('Sheet resistance must be positive.')
        length=snap(scalar(d['value'])/sheet*w);pad=snap(max(w,ls[cfg['terminal']]['width'],500));half=snap(pad/2)
        box('body',cfg['body'],0,0,length,w);box('positive',cfg['terminal'],-half,-half+snap(w/2),pad,pad,d['nets']['p']);box('negative',cfg['terminal'],length-half,-half+snap(w/2),pad,pad,d['nets']['n'])
        pin('p',cfg['terminal'],[0,snap(w/2)]);pin('n',cfg['terminal'],[length,snap(w/2)]);electrical={'target':scalar(d['value']),'realized':sheet*length/w,'unit':'Ohm'}
    elif kind=='capacitor':
        if not d or d['kind']!='C':raise ValueError('Choose a capacitor instance.')
        density=scalar(cfg['f_per_um2'])
        if density<=0:raise ValueError('Capacitance density must be positive.')
        area=scalar(d['value'])/density*1e6;w=snap(math.sqrt(area) if not spec.get('width') else int(spec['width']));h=snap(area/w)
        box('bottom',cfg['bottom'],0,0,w,h,d['nets']['p']);box('top',cfg['top'],0,0,w,h,d['nets']['n']);pin('p',cfg['bottom'],[snap(w/2),snap(h/2)]);pin('n',cfg['top'],[snap(w/2),snap(h/2)]);electrical={'target':scalar(d['value']),'realized':w*h*1e-6*density,'unit':'F'}
    elif kind=='mos':
        if not d or d['kind'] not in ('NMOS','PMOS'):raise ValueError('Choose a MOS instance.')
        from .catalog import binding_for
        if binding_for(p['pdk'],d):raise ValueError('Use the process MOS generator for a bound model. Generic geometry cannot replace a process footprint.')
        nf=int(spec.get('fingers',1))
        if not 1<=nf<=64:raise ValueError('Use 1–64 fingers.')
        w=snap(scalar(d['params']['w'])*1e9/nf);length=snap(scalar(d['params']['l'])*1e9)
        pitch=length+1000;total=nf*pitch+500;metal=cfg['terminal'];pad=snap(max(400,ls[metal]['width']))
        box('active',cfg['active'],0,0,total,w)
        if d['kind']=='PMOS':box('well',cfg['well'],-1000,-1000,total+2000,w+2000)
        for i in range(nf):box('gate'+str(i),cfg['gate'],500+i*pitch,-600,length,w+1200,d['nets']['g'])
        box('gate_bus',cfg['gate'],500,-600,(nf-1)*pitch+length,200,d['nets']['g'])
        for name,pt in [('s',[0,snap(w/2)]),('d',[total,snap(w/2)]),('g',[500,-500]),('b',[-1000,-1200])]:
            box(name,metal,pt[0]-snap(pad/2),pt[1]-snap(pad/2),pad,pad,d['nets'][name]);pin(name,metal,pt)
        # This pedagogical footprint records topology; it is not a process-recognized transistor.
        electrical={'width_nm':w*nf,'length_nm':length,'fingers':nf}
    elif kind=='contact':
        size=int(cfg['size']);enc=int(cfg['enclosure']);nx=int(spec.get('columns',1));ny=int(spec.get('rows',1));pitch=snap(size+ls[cfg['cut']]['space']);net=spec.get('net','0')
        if not 1<=nx<=32 or not 1<=ny<=32:raise ValueError('Contact arrays support 1–32 rows and columns.')
        w=(nx-1)*pitch+size;h=(ny-1)*pitch+size
        for layer in ('lower','upper'):box(layer,cfg[layer],-enc,-enc,w+2*enc,h+2*enc,net)
        for a in range(nx):
            for b in range(ny):box(f'cut{a}_{b}',cfg['cut'],a*pitch,b*pitch,size,size,net)
    elif kind=='guard_ring':
        w=int(spec.get('width',10000));h=int(spec.get('height',10000));t=int(spec.get('thickness',600));net=spec.get('net','0');size=int(cfg['cut_size']);enc=int(cfg['enclosure']);pitch=int(cfg['pitch'])
        if t<size+2*enc or min(w,h)<=2*t:raise ValueError('Guard ring needs an open center and enough thickness to enclose contacts.')
        for key in ('metal','active'):
            for i,s in enumerate(guard_ring(x,y,w,h,t,net)):s.update(layer=cfg[key],pcell_role=key+str(i));shapes.append(s)
        if cfg.get('implant'):
            for i,s in enumerate(guard_ring(x-enc,y-enc,w+2*enc,h+2*enc,t+2*enc,net)):s.update(layer=cfg['implant'],pcell_role='implant'+str(i));shapes.append(s)
        centers=[]
        for a in range(enc,w-enc-size+1,pitch):centers.extend([[a,enc],[a,h-enc-size]])
        for b in range(t,h-t-size+1,pitch):centers.extend([[enc,b],[w-enc-size,b]])
        for i,(a,b) in enumerate(centers):box('cut'+str(i),cfg['cut'],a,b,size,size,net)
    else:raise ValueError('Unknown parametric recipe.')
    if any(abs(v)>100000000 or v%grid for s in shapes for pt in s['points'] for v in pt):raise ValueError('Generated geometry exceeds 100 mm or leaves the technology grid.')
    for s in shapes:
        if s['layer'] not in ls:raise ValueError('Unmapped recipe layer: '+s['layer'])
    return {'shapes':shapes,'pins':pins,'record':{'id':uid(),'device_id':did or '', 'spec':{**clone(spec),'kind':kind,'x':x,'y':y},'electrical':electrical,'source_signature':electrical_signature(d) if d else None,'rules_hash':digest(config),'qualification':config.get('qualification','Declared technology geometry; verify with the process extraction and rule decks.')}}


def install(p,cid,did,spec,record_id=None):
    cell=next(c for c in p['cells'] if c['id']==cid);records=cell.setdefault('parametric_devices',[]);old=next((r for r in records if r['id']==record_id or did and r['device_id']==did),None)
    if did and not old and any(s.get('device_id')==did for s in cell['shapes']):raise ValueError('This device already has a footprint. Select its original regeneration workflow.')
    if old:
        existing={s['pcell_role']:s for s in cell['shapes'] if s.get('pcell_id')==old['id']};prior=old.get('reference');anchor=existing.get(prior['role']) if prior else None
        if anchor:
            deltas={(pt[0]-ref[0],pt[1]-ref[1]) for pt,ref in zip(anchor['points'],prior['points'])}
            if len(deltas)!=1:raise ValueError('The footprint anchor was reshaped or rotated. Restore it before regeneration.')
            dx,dy=deltas.pop();spec={**spec,'x':old['spec']['x']+dx,'y':old['spec']['y']+dy}
    data=build(p,cid,did,spec);record=data['record'];record['id']=old['id'] if old else record['id'];key=record['id'];old_shapes={s.get('pcell_role'):s for s in cell['shapes'] if s.get('pcell_id')==key};old_pins={v['pin']:v for v in cell.get('layout_pins',[]) if v['device_id']==did}
    for s in data['shapes']:
        s['pcell_id']=key
        if s['pcell_role'] in old_shapes:s['id']=old_shapes[s['pcell_role']]['id']
    for pin in data['pins']:
        if pin['pin'] in old_pins:pin['id']=old_pins[pin['pin']]['id']
    record['geometry_signature']=geometry_signature(data['shapes'])
    record['reference']={'role':data['shapes'][0]['pcell_role'],'points':clone(data['shapes'][0]['points'])};cell['shapes']=[s for s in cell['shapes'] if s.get('pcell_id')!=key]+data['shapes'];cell['layout_pins']=[v for v in cell.get('layout_pins',[]) if not did or v['device_id']!=did]+data['pins'];cell['parametric_devices']=[r for r in records if r['id']!=key]+[record];return record


def placement_inventory(p,cid):
    from .physical_cells import terminals
    c=next(c for c in p['cells'] if c['id']==cid);pins=terminals(p,cid);rows=[]
    for d in c['devices']:
        if d['kind'] in ('V','I'):continue
        if d.get('native_spice'):
            from .native_analysis import sources
            if not d['nets'] or d['name'] in {v[0] for v in sources(p,cid)}:continue
        assigned={v['pin'] for v in pins if v['device_id']==d['id']};missing=set(d['nets'])-assigned;shapes=[s for s in c['shapes'] if s.get('device_id')==d['id']];instances=[i for i in c.get('layout_instances',[]) if i.get('device_id')==d['id']]
        rows.append({'id':d['id'],'name':d['name'],'kind':d['kind'],'state':'Unplaced' if not shapes and not instances else 'Terminals missing' if missing else 'Placed','missing':sorted(missing)})
    return rows


def electrical_signature(d):
    return digest({k:d.get(k) for k in ('kind','value','params','model_ref','model_params','nets','cell','parameters')}|{k:d[k] for k in ('native_spice','physical_binding') if k in d})


def geometry_signature(shapes):
    if not shapes:return None
    ordered=sorted(shapes,key=lambda s:s.get('pcell_role',''));origin=ordered[0]['points'][0]
    return digest([{k:s.get(k) for k in ('pcell_role','kind','layer','width','net')}|{'points':[[x-origin[0],y-origin[1]] for x,y in s['points']],'holes':[[[x-origin[0],y-origin[1]] for x,y in hole] for hole in s.get('holes',[])]} for s in ordered])


def audit(p,cid):
    c=next(c for c in p['cells'] if c['id']==cid);ds={d['id']:d for d in c['devices']};out=[]
    for r in c.get('parametric_devices',[]):
        d=ds.get(r.get('device_id'));message=None;code='PCELL.STALE'
        if r.get('device_id') and not d:message='The linked schematic device was deleted.'
        elif d and r.get('source_signature')!=electrical_signature(d):message='Schematic parameters or terminals changed. Regenerate this footprint.'
        elif r.get('geometry_signature')!=geometry_signature([s for s in c['shapes'] if s.get('pcell_id')==r['id']]):message='Generated geometry was changed or deleted. Review or regenerate the footprint.';code='PCELL.EDITED'
        else:
            try:
                if r.get('rules_hash')!=digest(rules(p['pdk'])):message='Technology generator rules changed. Regenerate the footprint.'
            except ValueError:message='The original parametric rules are no longer available.'
        if message:out.append({'severity':'error','code':code,'cell_id':cid,'object':r.get('device_id',''),'objects':[s['id'] for s in c['shapes'] if s.get('pcell_id')==r['id']],'message':(d['name']+': ' if d else '')+message,'fingerprint':digest([r['id'],message,p['revision']])})
    return out
