"""Presentation of bundled teaching circuits; never applied to user documents.

Electrical names, values, models and terminal order are immutable here. Every
route is checked against the original terminal map before it is accepted.
"""
import math
from .model import clone, uid
from . import wiring


def imported_labels(project):
    """Keep default lower-terminal labels clear of bundled symbol values."""
    from .net_labels import point
    for cell in project['cells']:
        positions=wiring.pins(cell,project)
        devices={d['id']:d for d in cell['devices']}
        for label in cell.get('labels',[]):
            if label['kind']=='ground' or label['offset']!=[10,-12]:continue
            pt=point(label,cell,project)
            key=next((key for key,position in positions.items() if list(position)==list(pt)),None)
            if key is not None and pt[1]>devices[key[0]]['y']:
                label['offset']=[10,24]
    return project


def arrange(project,cell_ids=None,*,replace_wires=False):
    """Prepare examples; replacing automatic wires is only for freshly built cells.

    Callers adding a DUT to a user project must select only the new cell.
    """
    for cell in project['cells']:
        if cell_ids is not None and cell['id'] not in cell_ids:continue
        if not cell['devices'] or len(cell['devices'])>40 or cell.get('xschem') or cell.get('example_drawing'):continue
        if any(d.get('xschem') for d in cell['devices']):continue
        # Preserve intentionally hand-routed and external reference drawings.
        if cell.get('wires') and not replace_wires:continue
        original=clone(cell)
        expected={d['id']:dict(d['nets']) for d in cell['devices']}
        devices={d['name']:d for d in cell['devices']}
        def place(name,x,y,rotation=0,mirror=False):
            if name not in devices:return
            d=devices[name];pins=d.get('symbol',{}).get('pins',{})
            if d['kind']=='PMOS' and rotation==180 and mirror and pins.get('d',[0,0])[1]>pins.get('s',[0,0])[1]:
                rotation=0;mirror=False  # This PDK already draws the source above the drain.
            d.update(x=x,y=y,rotation=rotation,mirror=mirror)
        names={name for name,d in devices.items() if d.get('native_spice',{}).get('type')!='program'}
        if names=={'V1','R1','C1'}:
            place('V1',140,240);place('R1',320,190,270);place('C1',500,240)
            for d in cell['devices']:
                if d.get('native_spice',{}).get('type')=='program':place(d['name'],700,100)
        elif {'MP1','MN1','VDD','V1','CL'}==names:
            place('VDD',140,200);place('V1',140,400)
            place('MP1',460,200,180,True);place('MN1',460,400);place('CL',720,350)
        elif names=={'MP','MN'}:
            place('MP',360,160,180,True);place('MN',360,400)
        elif {'M1','M2','M3','M4','M5'}==names and cell['name']=='amplifier':
            place('M3',280,140,180,True);place('M4',640,140,180,True)
            place('M1',280,360);place('M2',640,360);place('M5',460,580)
        elif cell['name']=='two_stage_opamp' and {'CC1','CC2'}<=names:
            # The imported capacitor's model caption extends beyond the old
            # 140-unit spacing and otherwise crosses the next capacitor lead.
            place('CC2',devices['CC1']['x']+280,devices['CC1']['y'])
        elif {'R1','R2'}<=names and names<={'V1','R1','R2','Rload'}:
            place('V1',120,220);place('R1',400,140);place('R2',400,340);place('Rload',700,340)
        elif {'VD','VG','M1'}==names:
            place('VD',120,140);place('VG',120,380);place('M1',440,330)
        elif {'VDD','VIN','X1','CL'}<=names:
            place('VDD',100,100);place('VIN',100,380);place('X1',420,330);place('CL',720,330)
        if cell['name'].endswith('_testbench') and {'VBIAS','CL'}<=names:
            place('CL',devices['VBIAS']['x']+240,devices['VBIAS']['y'])
        if 'sar_analog'==cell['name']:
            for bit in range(4):place('Rbit'+str(bit),180+bit*220,570)
            place('Rterm',1060,720);place('Cdac',1300,720)
            place('Ssample',300,140);place('Chold',560,230)
            place('Bcompare',900,140);place('Rcompare',1190,110,270);place('Ccompare',1410,230)
            place('Rfilter',120,110,270);place('Cfilter',160,270)
        # Only generic teaching blocks get a title; PDK symbol artwork is owned
        # by its library. Terminal geometry and order are left intact.
        for d in cell['devices']:
            if d.get('model_ref') and d.get('symbol'):
                prepare_symbol_labels(d)
            if d['name'] in ('Ssample','Bcompare') and d.get('native_spice',{}).get('label') and d.get('symbol') and not any(p['kind']=='text' for p in d['symbol']['primitives']):
                d['symbol']['primitives'].append(dict(kind='text',points=[[-34,-8],[34,8]],text=d['native_spice']['label'],font_size=5))
        cell.update(wires=[],labels=[],junctions=[])
        cell.pop('wiring_migration',None)
        for d in cell['devices']:d['net_labels']=dict(d['nets'])
        positions=wiring.pins(cell,project)
        pairs=[]
        keys=list(positions)
        for i,a in enumerate(keys):
            for b in keys[i+1:]:
                if expected[a[0]][a[1]]==expected[b[0]][b[1]]:
                    pairs.append((math.dist(positions[a],positions[b]),a,b))
        # Connect nearby pins through clear orthogonal corridors. Ambiguous or
        # crowded routes retain explicit labels instead of a visual short.
        for distance,a,b in sorted(pairs):
            if distance>720:continue
            groups=wiring.graph(cell,project,labels=False)
            if groups[a]==groups[b]:continue
            start,end=positions[a],positions[b]
            ax,ay=start;bx,by=end
            candidates=[[start,end]] if ax==bx or ay==by else []
            candidates += [[start,[bx,ay],end],[start,[ax,by],end]]
            for x in sorted({ax-80,ax+80,bx-80,bx+80,(ax+bx)/2}):
                candidates.append([start,[x,ay],[x,by],end])
            for y in sorted({ay-80,ay+80,by-80,by+80,(ay+by)/2}):
                candidates.append([start,[ax,y],[bx,y],end])
            candidates.sort(key=lambda p:sum(math.dist(u,v) for u,v in zip(p,p[1:]))+len(p)*8)
            for points in candidates:
                points=wiring.clean(points)
                if any(blocked(points,d) for d in cell['devices']):continue
                route=dict(id=uid(),points=points,net=expected[a[0]][a[1]])
                cell['wires'].append(route)
                try:
                    wiring.rebuild(cell,project)
                    if any(d['nets']!=expected[d['id']] for d in cell['devices']):raise ValueError('Connectivity changed')
                except ValueError:
                    cell['wires'].pop()
                    for d in cell['devices']:d['nets']=dict(expected[d['id']])
                    continue
                break
        groups=wiring.graph(cell,project,labels=False);components={}
        for key,point in positions.items():components.setdefault(groups[key],[]).append((key,point))
        for d in cell['devices']:d['net_labels']={}
        for members in components.values():
            net=expected[members[0][0][0]][members[0][0][1]]
            low=net.lower() in ('0','vss','gnd')
            key,pt=(max(members,key=lambda v:(v[1][1],v[1][0])) if low else min(members,key=lambda v:(v[1][1],v[1][0])))
            device=next(d for d in cell['devices'] if d['id']==key[0])
            ground=net=='0' and pt[1]>device['y']
            # Keep left-facing labels outside the body and its value text.
            offset=[-max(18,len(net)*7)-6,-8] if pt[0]<device['x'] else [8,-12]
            if device.get('model_ref'):
                offset=([-max(18,len(net)*7)-6,-38] if pt[0]<device['x'] else
                        [8,36] if pt[1]>device['y'] else [8,-30])
            if low:offset=[8,22]
            if device['kind'] in ('NMOS','PMOS') and pt[0]>device['x'] and pt[1]==device['y']:
                offset=[8,40]
            cell['labels'].append(dict(id=uid(),kind='ground' if ground else 'net_label',name=net,
                anchor=dict(kind='pin',id=key[0],pin=key[1]),offset=[0,0] if ground else offset,rotation=0))
        wiring.rebuild(cell,project)
        if any(d['nets']!=expected[d['id']] for d in cell['devices']):
            cell.clear();cell.update(original)
            raise ValueError('Example presentation changed terminal connectivity')
        cell['example_drawing']=1
    return project


def prepare_symbol_labels(device):
    """Space new example annotations without changing a locked PDK catalog."""
    items=[item for item in device['symbol']['primitives']
           if item['kind']=='text' and not item.get('hidden')
           and not item['text'].startswith(('@#','@spice_get_'))]
    items.sort(key=lambda item:0 if '@name' in item['text'] else 1 if '@model' in item['text'] else 2)
    angle=device['rotation'];mirror=device.get('mirror',False)
    co=round(math.cos(math.radians(angle)));si=round(math.sin(math.radians(angle)))
    for index,item in enumerate(items):
        # Text occupies horizontal rows beside the symbol regardless of how
        # the transistor is oriented. Keep its live parameter placeholders.
        x,y=70,-52+index*18
        local=[(x*co+y*si)*(-1 if mirror else 1),-x*si+y*co]
        item.update(points=[local,[local[0]+20,local[1]+10]],
                    rotation=(angle if mirror else -angle)%360,mirror=mirror,
                    text_anchor='corner',hcenter=False,vcenter=False,font_size=8)
        if '@name' in item['text']:
            item['text']=item['text'].replace('@spiceprefix','')


def blocked(points,device):
    """Reject paths through symbol bodies or reference/value text."""
    x,y=device['x'],device['y'];kind=device['kind']
    if kind=='SPICE' and device.get('native_spice',{}).get('label') in ('R','C','L','V','I'):
        kind=device['native_spice']['label']
    half_x,half_y=(26,30) if kind in ('NMOS','PMOS') else (22,26) if kind in ('R','C','L','V','I') else (39,49)
    if device.get('symbol') and kind in ('NMOS','PMOS','PDK'):
        pins=list(device['symbol']['pins'].values())
        half_x=max(2,min((abs(p[0]) for p in pins if p[0]),default=40)*.45)
        half_y=max(2,min((abs(p[1]) for p in pins if p[1]),default=40)*.45)
    if device['rotation'] in (90,270):half_x,half_y=half_y,half_x
    boxes=[(x-half_x,y-half_y,x+half_x,y+half_y)]
    if not device.get('symbol'):
        boxes.append((x+78,y-40,x+190,y-4) if kind in ('NMOS','PMOS') else (x-22,y-72,x+90,y-34) if device['rotation'] in (90,270) else (x+34,y-45,x+135,y-8))
    elif device.get('model_ref'):
        # New example captions have a reserved column; wires must stay out.
        count=sum(item['kind']=='text' and not item.get('hidden') for item in device['symbol']['primitives'])
        boxes.append((x+66,y-56,x+250,y-52+count*18))
    for a,b in zip(points,points[1:]):
        for left,top,right,bottom in boxes:
            if a[0]==b[0] and left<a[0]<right and max(min(a[1],b[1]),top)<min(max(a[1],b[1]),bottom):return True
            if a[1]==b[1] and top<a[1]<bottom and max(min(a[0],b[0]),left)<min(max(a[0],b[0]),right):return True
    return False
