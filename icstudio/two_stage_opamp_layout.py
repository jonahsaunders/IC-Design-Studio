"""Bounded, inspectable three-metal routing for the Miller op-amp reference.

Separate vertical access tracks on M2/M4 meet horizontal M3 net buses. Every
cross-layer join is explicit; regenerated devices still need process DRC/LVS.
"""
from .model import clone, uid, validate, digest
from .layout import rect


def generate(p, cid, replace=False):
    from .sky130_layout import install_mos
    from .sky130_devices import layers, configure_connectivity, install_guard
    from .physical_cells import assign_port
    from .analog_constraints import footprint, findings
    q=clone(p)
    cell=next(c for c in q['cells'] if c['id']==cid)
    if cell.get('opamp_reference',{}).get('version')!=1:
        raise ValueError('Select the saved two-stage op-amp circuit cell.')
    if cell['shapes'] or cell.get('layout_instances'):
        if not replace or not cell.get('opamp_layout'):
            raise ValueError('Existing geometry requires explicit replacement of this op-amp layout recipe.')
    ds={d['name']:d for d in cell['devices']}
    if not all(name in ds and ds[name]['kind'] in ('NMOS','PMOS') for name in ('M1','M2','M3','M4','M5','M6','M7','M8')):
        raise ValueError('The op-amp layout requires its eight named MOS devices.')
    capacitors=[d for d in cell['devices'] if d['kind']=='PDK']
    if len(cell['devices'])!=8+len(capacitors) or not 1<=len(capacitors)<=4:
        raise ValueError('The op-amp recipe supports eight MOS and one to four explicit compensation capacitors.')
    for field in ('shapes','layout_pins','layout_ports','layout_texts','layout_instances','pdk_layouts','process_guards','analog_constraints','routing_records'):
        cell[field]=[]
    # Equal-device pairs are adjacent and have equal orientation and spacing.
    order=['M8','M5','M1','M2','M3','M4','M6','M7']
    for i,name in enumerate(order):
        install_mos(q,cid,ds[name]['id'],i*18000,0)
    cap_origins=[]
    for i,d in enumerate(capacitors):
        origin=[162000+i*42000,0]
        install_mos(q,cid,d['id'],*origin);cap_origins.append(origin)
    configure_connectivity(q['pdk']);ls=layers(q['pdk'])
    nets=sorted({net for d in cell['devices'] for net in d['nets'].values()})
    if not set(cell['ports'])<=set(nets):raise ValueError('Every op-amp port must connect to the circuit.')
    tracks={net:-5000-i*2000 for i,net in enumerate(nets)}
    def wire(layer,points,net,width=400):
        points=[list(point) for i,point in enumerate(points) if not i or point!=points[i-1]]
        if len(points)<2:return
        cell['shapes'].append(dict(id=uid(),kind='path',layer=ls[layer],points=points,width=width,
                                   net=net,generated_route=True,device_id=''))
    def via(cut,lower,upper,point,net,size=200,pad=400):
        group=uid()
        for key,side in ((cut,size),(lower,pad),(upper,pad)):
            shape=rect(ls[key],point[0]-side//2,point[1]-side//2,side,side,net=net if key!=cut else '')
            shape.update(via_group=group,generated_route=True)
            cell['shapes'].append(shape)
    xmax={net:-12000 for net in nets}
    for pin in clone(cell['layout_pins']):
        d=next(d for d in cell['devices'] if d['id']==pin['device_id'])
        net=d['nets'][pin['pin']];x,y=pin['point'];end=[x,tracks[net]]
        if pin['layer']==ls['m1']:
            via('via','m1','m2',[x,y],net,150,340)
            wire('m2',[[x,y],end],net)
            via('via2','m2','m3',end,net)
        elif pin['layer']==ls['m4']:
            wire('m4',[[x,y],end],net)
            via('via3','m3','m4',end,net)
        else:
            raise ValueError('The op-amp recipe requires MOS M1 and capacitor M4 access pins.')
        xmax[net]=max(xmax[net],x)
    for net,y in tracks.items():
        wire('m3',[[-12000,y],[xmax[net]+1000,y]],net,600)
        if net in cell['ports']:assign_port(q,cid,net,ls['m3'],[-12000,y])
    for first,second,name in [('M1','M2','Input pair'),('M3','M4','Active load')]:
        ids=[ds[first]['id'],ds[second]['id']]
        axis=sum(footprint(q,cid,key)[2][0] for key in ids)/2
        cell['analog_constraints'].extend([
            dict(id=uid(),name=name+' matching',kind='matching',members=ids),
            dict(id=uid(),name=name+' symmetry',kind='symmetry',members=ids,axis='x',coordinate=axis)])
    # A contacted substrate guard encloses the transistor bank. Its separate M2
    # access joins the same saved VSS bus without changing any signal routes.
    top=max(footprint(q,cid,ds[name]['id'])[1].top for name in order)
    guard_height=max(45000,((int(top)+5000+29000+999)//1000)*1000)
    guard=install_guard(q,cid,dict(kind='psub',x=-8000,y=-29000,width=148000,height=guard_height,thickness=800),
                        'VSS',members=[ds[name]['id'] for name in order])
    cell=next(c for c in q['cells'] if c['id']==cid)
    x,y=guard['tie_point'];via('via','m1','m2',[x,y],'VSS',150,340)
    wire('m2',[[x,y],[x,tracks['VSS']]],'VSS')
    via('via2','m2','m3',[x,tracks['VSS']],'VSS')
    cell['opamp_layout']=dict(version=1,device_ids=[d['id'] for d in cell['devices']],
        capacitor_origins_nm=cap_origins,bus_tracks_nm=tracks,guard_id=guard['id'],
        scope='M2/M4 terminal access and M3 net buses; paired matching/symmetry and contacted p-substrate guard. Requires actual DRC/LVS and extracted verification.')
    errors=findings(q,cid)
    if errors:raise ValueError(errors[0]['message'])
    validate(q);p.clear();p.update(q)
    return p
