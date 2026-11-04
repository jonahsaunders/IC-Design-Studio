"""Shared-diffusion GF180/IHP MOS fingers with explicit four-terminal routing.

W is total width; every channel is W/nf (GF180) or W/ng (IHP). Parallel
m repeats this entire contacted structure without changing channel dimensions.
"""
from .layout import rect
from .model import uid


def dimensions(width_nm, fingers, minimum):
    if fingers != int(fingers) or not 1 <= fingers <= 8:
        raise ValueError('Use an integer physical gate-finger count from 1 to 8.')
    count = int(fingers)
    if width_nm % count or width_nm // count < minimum or (width_nm // count) % 5:
        raise ValueError(f'Total W divided by gate-finger count must be at least {minimum/1000:g} micrometres on the 5 nm grid.')
    return count, width_nm // count


def generate(tech, device, x, y, spec, layers):
    ihp = tech['package_lock']['id'] == 'ihp-sg13g2'
    count, width = dimensions(spec['dimensions_nm']['w'], spec['values']['ng' if ihp else 'nf'], spec.get('minimum_finger_width_nm',150) if ihp else 220)
    length = spec['dimensions_nm']['l']; pitch = length+1200; last = (count-1)*pitch
    cy = 5*round(width/10); shapes = []; pins = []

    def box(role, key, left, bottom, right, top, net=''):
        shape = rect(layers[key], x+left, y+bottom, right-left, top-bottom, device['id'], net)
        shape.update(generated_device=device['id'], generator_role='fingers:'+role)
        shapes.append(shape)

    def wire(role, key, points, net):
        points = [pt for i, pt in enumerate(points) if not i or pt != points[i-1]]
        if len(points) < 2: return
        shapes.append(dict(id=uid(), kind='path', layer=layers[key],
            points=[[x+a, y+b] for a,b in points], width=440, net=net,
            device_id=device['id'], generated_device=device['id'], generator_role='fingers:'+role))

    def contact(role, px, py, net):
        half = 80 if ihp else 110
        box(role+':cut', 'contact', px-half, py-half, px+half, py+half)
        box(role+':m1', 'm1', px-220, py-220, px+220, py+220, net)

    implant = 'psdm' if device['kind']=='PMOS' else 'nsdm'
    body_implant = 'nsdm' if device['kind']=='PMOS' else 'psdm'
    bottom, top = min(0, cy-350), max(width, cy+350)
    box('active', 'diff', -900, 0, last+length+900, width)
    box('implant', implant, -1200, bottom-300, last+length+1200, top+300)
    gate_points = []
    for index in range(count):
        start = index*pitch; gate = start+5*round(length/10); role = 'gate:'+str(index)
        box(role+':poly', 'poly', start, -1000, start+length, width+300)
        box(role+':pad', 'poly', gate-250, -1050, gate+250, -550)
        contact(role, gate, -800, device['nets']['g'])
        half = 95 if ihp else 130
        box(role+':via', 'via', gate-half, -800-half, gate+half, -800+half)
        box(role+':m2', 'm2', gate-220, -1020, gate+220, -580, device['nets']['g'])
        gate_points.append([gate, -800])
    wire('gate:rail', 'm2', [gate_points[0], gate_points[-1]], device['nets']['g'])

    columns = [-600]+[index*pitch+length+600 for index in range(count)]
    sources, drains = [], []; source_y = width+900; drain_y = -2000; drain_x = last+length+2400
    for index, px in enumerate(columns):
        terminal = 's' if index%2==0 else 'd'; net = device['nets'][terminal]; role = 'diffusion:'+str(index)
        if width < 700: box(role+':pad', 'diff', px-300, cy-350, px+300, cy+350)
        contact(role, px, cy, net)
        yy = source_y if terminal=='s' else drain_y
        wire(role+':access', 'm1', [[px,cy],[px,yy]], net)
        (sources if terminal=='s' else drains).append(px)
    wire('source:rail', 'm1', [[sources[0],source_y],[sources[-1],source_y]], device['nets']['s'])
    wire('drain:rail', 'm1', [[drains[0],drain_y],[drain_x,drain_y],[drain_x,cy]], device['nets']['d'])

    # A long multi-finger row needs body contacts along its full extent.
    # Separate these from the source rail so all four nets remain independent.
    body_y = width+2200; bodies = [[-2600,cy]]+[[point[0],body_y] for point in gate_points]
    for index, (px,py) in enumerate(bodies):
        role = 'body:'+str(index)
        box(role+':active', 'diff', px-350, py-350, px+350, py+350)
        box(role+':implant', body_implant, px-650, py-650, px+650, py+650)
        contact(role, px, py, device['nets']['b'])
    wire('body:rail', 'm1', [bodies[0],[-2600,body_y],bodies[-1]], device['nets']['b'])
    if device['kind']=='PMOS': box('well', 'nwell', -3550, -1500, last+length+1600, width+3200)
    for terminal, point in (('s',[columns[0],cy]),('d',[drain_x,cy]),('g',gate_points[0]),('b',bodies[0])):
        pins.append(dict(id=uid(), device_id=device['id'], pin=terminal, layer=layers['m1'], point=[x+point[0], y+point[1]]))
    return dict(shapes=shapes, pins=pins, record=dict(device_id=device['id'], spec=spec, origin=[x,y],
        fingers=dict(count=count, width_nm=width, pitch_nm=pitch, shared_diffusion=True)))
