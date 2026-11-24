"""Shared SKY130 placement, routing and connectivity for standard-cell practice."""

from collections import defaultdict

from . import physical, sky130_layout
from .layout import kdb, polygon, rect
from .model import clone, scalar, uid, validate
from .physical_cells import assign_port


ROW_HEIGHT = 24500
PITCH = 5800
VPWR_Y = 1500
VGND_Y = 23000
TRACK_WIDTH = 640
RAIL_WIDTH = 900
M2_WIDTH = 340
ROUTING_SPACE = 270
# Explicit exercise coefficients in F/µm² and F/µm. The locked model
# package supplies the transistors. These numbers are illustrative.
CAPACITANCE = {
    'm1': ('0.018f', '0.008f'),
    'm2': ('0.012f', '0.005f'),
    'm3': ('0.008f', '0.004f'),
}


def layers(technology):
    named = {(entry['gds'], entry['datatype']): entry['name'] for entry in technology['layers']}
    standard = sky130_layout.layers(technology)
    return {**standard, 'm3': named[70, 20], 'via2': named[69, 44], 'boundary': named[235, 4]}


def path(layer, net, start, end, width):
    return dict(id=uid(), kind='path', layer=layer, net=net, points=[list(start), list(end)],
                width=width, device_id='')


def place(project, cell, pitch=PITCH):
    """Place real model-linked devices and leave two Metal 3 routes open."""
    if cell['shapes'] or cell.get('layout_instances'):
        raise ValueError('The lesson already has layout geometry. Open it to continue routing.')
    names = layers(project['pdk'])
    width = 8000 + pitch * (len(cell['devices']) - 1)
    expected = {part['id']: part for part in cell['devices']}
    for index, part in enumerate(cell['devices']):
        sky130_layout.install_mos(project, cell['id'], part['id'], 4000 + pitch * index,
                                  5000 if part['kind'] == 'PMOS' else 16500)
    config = project['pdk']['connectivity']
    if names['m3'] not in config['conductors']:
        config['conductors'].append(names['m3'])
    cut = [names['m2'], names['via2'], names['m3']]
    if cut not in config['vias']:
        config['vias'].append(cut)

    signal_nets = sorted({net for part in cell['devices'] for net in part['nets'].values()} - {'VPWR', 'VGND'})
    tracks = {net: 8250 + index*950 for index, net in enumerate(signal_nets)}
    tracks.update(VPWR=VPWR_Y, VGND=VGND_Y)
    towers = defaultdict(list)
    for terminal in cell['layout_pins']:
        x, y = terminal['point']
        pin = terminal['pin']
        net = expected[terminal['device_id']]['nets'][pin]
        escape = x + {'s': -300, 'd': 300, 'g': 0, 'b': 0}[pin]
        track = tracks[net]
        if escape != x:
            cell['shapes'].append(path(names['m1'], net, (x,y), (escape,y), M2_WIDTH))
        for layer, half in [('m1', 170), ('via', 85), ('m2', 200)]:
            cell['shapes'].append(rect(names[layer], escape-half, y-half, 2*half, 2*half,
                                       net=net if layer != 'via' else ''))
        if y != track:
            cell['shapes'].append(path(names['m2'], net, (escape,y), (escape,track), M2_WIDTH))
        for layer, half in [('m2', 240), ('via2', 100), ('m3', 320)]:
            cell['shapes'].append(rect(names[layer], escape-half, track-half, 2*half, 2*half,
                                       net=net if layer != 'via2' else ''))
        towers[net].append(escape)

    output = 'Q' if 'Q' in cell['ports'] else 'Y'
    breaks = {}
    for net, track in tracks.items():
        rail = net in ('VPWR','VGND')
        thickness = RAIL_WIDTH if rail else TRACK_WIDTH
        left = 0 if rail else 400 if net in cell['ports'] else min(towers[net])-100
        right = width if rail else max(towers[net])+350
        if net in ('VPWR', output) or (output=='Y' and net=='CO' and net in cell['ports']):
            x1, x2 = sorted(set(towers[net]))[:2]
            middle = 5*((x1+x2)//10)
            a, b = middle-260, middle+260
            cell['shapes'] += [path(names['m3'], net, (left,track), (a,track), thickness),
                               path(names['m3'], net, (b,track), (right,track), thickness)]
            breaks[net] = dict(layer=names['m3'], start=[a,track], end=[b,track], width=thickness)
        else:
            cell['shapes'].append(path(names['m3'], net, (left,track), (right,track), thickness))
        if net in cell['ports']:
            assign_port(project, cell['id'], net, names['m3'], [600,track])
    cell['shapes'].append(rect(names['boundary'], 0, 0, width, ROW_HEIGHT))
    cell['student_cell_layout'] = dict(version=1, width=width, height=ROW_HEIGHT, pitch=pitch, breaks=breaks)
    validate(project)


def check_placement(project, cell):
    state = cell.get('student_cell_layout', {})
    if not state or not cell['shapes']:
        raise ValueError('Choose Place cell rows to build the layout starter.')
    attached = {entry['device_id'] for entry in cell.get('pdk_layouts', [])}
    if (attached != {part['id'] for part in cell['devices']}
            or sky130_layout.audit(project, cell['id'])):
        raise ValueError('Keep model-linked physical geometry for every device in the layout.')
    names = layers(project['pdk'])
    outline = [shape for shape in cell['shapes'] if shape['layer'] == names['boundary']]
    if (len(outline) != 1 or state['height'] != ROW_HEIGHT
            or outline[0]['points'] != [[0,0], [state['width'], ROW_HEIGHT]]):
        raise ValueError('Preserve the teaching row boundary and its shared height.')
    ports = {port['name']: port for port in cell.get('layout_ports', [])}
    if set(ports) != set(cell['ports']) or any(port['layer'] != names['m3'] for port in ports.values()):
        raise ValueError('Keep the physical signal and power ports on the Metal 3 tracks.')
    if ports['VPWR']['point'][1] != VPWR_Y or ports['VGND']['point'][1] != VGND_Y:
        raise ValueError('Keep VPWR and VGND at the common row rail heights.')
    return dict(physical_devices=len(attached), physical_ports=list(cell['ports']),
                width_um=state['width']/1000, height_um=ROW_HEIGHT/1000)


def open_nets(project, cell):
    return {finding['net'] for finding in physical.connectivity(project, cell['id'])['issues']
            if finding['code'] == 'LVS.OPEN'}


def close_gap(project, cell, net, layer, start, end, width):
    """Draw a student-entered route. The canvas Path tool can draw the same connection."""
    check_placement(project, cell)
    options = cell['student_cell_layout']['breaks']
    if net not in options or net not in open_nets(project, cell):
        raise ValueError('Choose one of the remaining open rails or signal tracks.')
    gap = options[net]
    if (layer != gap['layer'] or sorted([start,end]) != sorted([gap['start'],gap['end']])
            or width != gap['width']):
        raise ValueError('Match the layer, width and two on-grid endpoints of the selected track.')
    cell['shapes'].append(path(layer, net, start, end, width))


def um_to_nm(value):
    nm = scalar(value)*1000
    if abs(nm-round(nm)) > 1e-6 or round(nm)%5:
        raise ValueError('Enter a coordinate or width on the 0.005 µm grid.')
    return round(nm)


def check_routing(project, cell):
    evidence = check_placement(project, cell)
    checked = physical.connectivity(project, cell['id'])
    if checked['issues']:
        raise ValueError(checked['issues'][0]['message'])
    names = layers(project['pdk'])
    db = kdb()
    boundary = db.Box(0, 0, cell['student_cell_layout']['width'], ROW_HEIGHT)
    routed = {names['m1']: 340, names['m2']: M2_WIDTH, names['m3']: TRACK_WIDTH}
    nets = {row['net']: row['shapes'] for row in checked['net_regions']}
    shape_nets = {shape['id']: net for net, shapes in nets.items() for shape in shapes}
    for port in cell['layout_ports']:
        point = db.Point(*port['point'])
        if not any(s['layer'] == port['layer'] and polygon(s).inside(point)
                   for s in nets.get(port['name'], [])):
            raise ValueError('Connect the physical port '+port['name']+' to its conductor.')
    for rail in ('VPWR','VGND'):
        metal = [polygon(s).bbox() for s in nets[rail] if s['layer'] == names['m3']]
        if min(box.left for box in metal) != 0 or max(box.right for box in metal) != boundary.right:
            raise ValueError('Extend '+rail+' to both edges of the teaching row.')
    for shape in cell['shapes']:
        if not boundary.contains(polygon(shape).bbox().p1) or not boundary.contains(polygon(shape).bbox().p2):
            raise ValueError('Keep the layout inside the teaching row boundary.')
        if shape['kind'] == 'path' and shape['layer'] in routed:
            minimum = routed[shape['layer']]
            if shape['layer'] == names['m3'] and shape_nets.get(shape['id']) in ('VPWR','VGND'):
                minimum = RAIL_WIDTH
            if shape['width'] < minimum or any(a[0]!=b[0] and a[1]!=b[1]
                    for a,b in zip(shape['points'],shape['points'][1:])):
                raise ValueError('Keep conductor paths Manhattan and at least the lesson minimum width.')
    for layer in (names['m2'], names['m3']):
        region = db.Region()
        for shape in cell['shapes']:
            if shape['layer'] == layer:
                region.insert(polygon(shape))
        if not region.merged().space_check(ROUTING_SPACE).is_empty():
            raise ValueError(f'{layer} has a gap below the {ROUTING_SPACE/1000:g} µm lesson spacing.')
    return dict(**evidence, connected_nets=sorted(nets))


def estimate(project, cell):
    """Apply the declared lumped load estimate to a disposable copy."""
    teaching = clone(project)
    names = layers(teaching['pdk'])
    teaching['pdk']['parasitics'] = {names[layer]: dict(cap_f_per_um2=cap, edge_f_per_um=edge)
                                   for layer, (cap,edge) in CAPACITANCE.items()}
    extracted = physical.capacitance_estimate(teaching, cell['id'])
    return physical.with_parasitics(teaching, cell['id'], extracted), extracted['capacitors']
