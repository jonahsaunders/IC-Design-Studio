"""Contacted teaching MOS arrays; these are not process extraction recipes."""
import math
from .model import scalar


def generate(device, spec, cfg, layers, grid, box, pin):
    def integer(key, default, low, high):
        value=scalar(spec.get(key,default))
        if value!=int(value) or not low<=value<=high:raise ValueError(f'{key}: use a whole number from {low} to {high}.')
        return int(value)
    def snap(value):return math.ceil(value/grid)*grid
    nf=integer('fingers',1,1,64);dummies=integer('dummies',0,0,4)
    rows=integer('contact_rows',0,0,32)
    if type(spec.get('guard',False)) is not bool:raise ValueError('Guard ring must be enabled or disabled.')
    mode=spec.get('diffusion','shared')
    if mode not in ('shared','isolated'):raise ValueError('Choose shared or isolated finger diffusion.')
    width=scalar(device['params']['w'])*1e9/nf;length=scalar(device['params']['l'])*1e9
    if any(abs(value/grid-round(value/grid))>1e-6 for value in (width,length)):
        raise ValueError('W/fingers and L must lie on the technology grid. Adjust schematic W/L or finger count; geometry will not silently resize the device.')
    width=round(width/grid)*grid;length=round(length/grid)*grid
    cut=cfg.get('cut');upper=cfg.get('gate_metal');via=cfg.get('via')
    if not all(k in layers for k in (cut,upper,via)):
        raise ValueError('Contacted MOS arrays require declared cut, gate_metal, and via layers in pcell_rules.mos.')
    size=snap(layers[cut]['width']);enc=snap(100);pad=snap(max(size+2*enc,layers[cfg['terminal']]['width'],layers[upper]['width']))
    half=snap(pad/2);pad=2*half
    contact_pitch=snap(size+layers[cut]['space'])
    capacity=int((width-2*enc-size)//contact_pitch)+1
    if capacity<1:raise ValueError('Each finger is too narrow to enclose one contact; increase W or reduce fingers.')
    rows=rows or min(capacity,32)
    if rows>capacity:raise ValueError('Contact rows do not fit inside W/fingers with the required enclosure.')
    spacing=snap(max(1000,pad+layers[cfg['gate']]['space']*2));pitch=length+spacing
    if mode=='isolated':pitch+=spacing
    extent=(nf-1)*pitch+length+spacing
    cy=snap(width/2);metal=cfg['terminal'];gate=cfg['gate'];active=cfg['active']
    def contact(role,x,y,net,with_via=False):
        box(role+'_metal',metal,x-half,y-half,pad,pad,net)
        box(role+'_cut',cut,x-snap(size/2),y-snap(size/2),size,size)
        if with_via:
            vs=snap(layers[via]['width'])
            box(role+'_via',via,x-snap(vs/2),y-snap(vs/2),vs,vs)
            box(role+'_upper',upper,x-half,y-half,pad,pad,net)
    start=-spacing//2
    if mode=='shared':box('active',active,start,0,extent,width)
    gate_y=-2*spacing;source_y=width+spacing;drain_y=-3*spacing
    terminals={'s':[],'d':[]};gates=[]
    for i in range(nf):
        x=i*pitch
        if mode=='isolated':box(f'active{i}',active,x-spacing//2,0,length+spacing,width)
        box(f'gate{i}',gate,x,gate_y-half,length,width-gate_y+half,device['nets']['g'])
        gx=x+snap(length/2);gates.append(gx)
        box(f'gate_pad{i}',gate,gx-half,gate_y-half,pad,pad,device['nets']['g'])
        contact(f'gate_contact{i}',gx,gate_y,device['nets']['g'],True)
    box('gate_bus',upper,min(gates)-half,gate_y-half,max(gates)-min(gates)+pad,pad,device['nets']['g'])
    columns=([(start+spacing//4,'s')]+[(i*pitch+length+spacing//4,'d' if i%2==0 else 's') for i in range(nf)]
             if mode=='shared' else [(x,terminal) for i in range(nf) for x,terminal in ((i*pitch-spacing//4,'s'),(i*pitch+length+spacing//4,'d'))])
    for i,(x,terminal) in enumerate(columns):
        net=device['nets'][terminal];yy=source_y if terminal=='s' else drain_y;terminals[terminal].append(x)
        # A continuous strap contacts all rows in this diffusion column.
        box(f'{terminal}_strap{i}',metal,x-half,min(enc,yy)-half,pad,max(width-enc,yy)-min(enc,yy)+pad,net)
        for j in range(rows):contact(f'diffusion{i}_{j}',x,enc+snap(size/2)+j*contact_pitch,net)
    for terminal,yy in (('s',source_y),('d',drain_y)):
        xs=terminals[terminal];box(terminal+'_bus',metal,min(xs)-half,yy-half,max(xs)-min(xs)+pad,pad,device['nets'][terminal]);pin(terminal,metal,[xs[0],yy])
    pin('g',metal,[gates[0],gate_y])
    body_x=start-3*spacing;contact('bulk',body_x,cy,device['nets']['b']);box('bulk_active',active,body_x-half,cy-half,pad,pad,device['nets']['b']);pin('b',metal,[body_x,cy])
    for i in range(dummies):
        # Poly-only edge dummies do not introduce unmodelled transistor channels.
        for side,x in (('left',start-(i+1)*spacing),('right',extent+start+(i+1)*spacing)):
            box(f'dummy_{side}{i}',gate,x,0,length,width)
    if device['kind']=='PMOS':box('well',cfg['well'],body_x-spacing,-spacing,extent+start-body_x+2*spacing,width+2*spacing)
    return dict(width_nm=width*nf,length_nm=length,fingers=nf,contact_rows=rows,dummies_per_edge=dummies,diffusion=mode,
                dummy_type='poly-only edge patterns')
