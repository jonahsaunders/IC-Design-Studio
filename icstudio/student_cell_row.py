"""Place and check adjacent hierarchical standard cells on a teaching row."""

from . import physical, physical_cells
from .design_ops import flatten_layout
from .layout import kdb, polygon
from .model import device, validate
from .student_cell_layout import (ROUTING_SPACE, check_routing, close_gap, layers,
                                  place, um_to_nm)


KEY = 'abutment'
GOAL = 'Zero gap and vertical offset at the seam. Continuous VPWR and VGND. No Metal 2 or Metal 3 spacing errors.'


def create():
    from .student_standard_cells import context, create
    from .example_schematics import arrange

    project = create('inv')
    inv, row = context(project, 'inv')
    nand, _ = context(create('nand2'), 'nand2')
    project['cells'].append(nand)
    for cell in (inv, nand):
        place(project, cell)
        for net, coordinates in cell['student_cell_layout']['breaks'].items():
            close_gap(project, cell, net, **coordinates)
    row.update(name='inverter_nand_row', devices=[
        device('X', 'XINV', x=300, y=250, cell=inv['id'],
               nets=dict(A='inv_a', Y='inv_y', VPWR='VPWR', VGND='VGND')),
        device('X', 'XNAND', x=580, y=250, cell=nand['id'],
               nets=dict(A='nand_a', B='nand_b', Y='nand_y', VPWR='VPWR', VGND='VGND')),
    ])
    row.pop('wires', None)
    arrange(project)
    left, right = row['devices']
    physical_cells.place(project, row['id'], left['id'], 0, 0)
    physical_cells.place(project, row['id'], right['id'], inv['student_cell_layout']['width']+1000, 1000)
    project['name'] = 'Inverter and NAND · standard-cell row'
    project['student_standard_cell'] = dict(kind=KEY, cell=row['id'], fixture=row['id'])
    return validate(project)


def children(project, row):
    cells = {c['id']:c for c in project['cells']}
    schematic = {d['name']:d for d in row['devices']}
    layout = {i['name']:i for i in row['layout_instances']}
    if (len(row['devices']) != 2 or len(row['layout_instances']) != 2
            or set(schematic) != {'XINV','XNAND'} or set(layout) != set(schematic)):
        raise ValueError('Keep one inverter and one NAND on the assembly row.')
    pair = []
    for name in ('XINV', 'XNAND'):
        inst, part = layout[name], schematic[name]
        if (inst['cell'] != part.get('cell') or inst['device_id'] != part['id']
                or inst['cell'] not in cells or inst['rotation'] or inst['mirror']
                or inst.get('nx',1) != 1 or inst.get('ny',1) != 1):
            raise ValueError('Keep both children linked to their schematic instances in the original orientation.')
        cell = cells[inst['cell']]
        if part['nets'].get('VPWR') != 'VPWR' or part['nets'].get('VGND') != 'VGND':
            raise ValueError('Keep both power nets connected to the shared row rails.')
        pair.append((inst,cell))
    return pair


def dimensions(project, row):
    (left, inv), (right, _) = children(project,row)
    return [('x', 'NAND X position', right['x']/1000),
            ('y', 'NAND Y position', right['y']/1000),
            ('edge', 'Inverter right edge', (left['x']+inv['student_cell_layout']['width'])/1000)]


def move(project, row, values):
    (_, _), (right, _) = children(project,row)
    x,y = (um_to_nm(values[axis]) for axis in ('x','y'))
    if not 0 <= x <= 40000 or not -10000 <= y <= 10000:
        raise ValueError('Choose an X position from 0 to 40 µm and a Y position from −10 to 10 µm.')
    right.update(x=x,y=y)
    validate(project)


def check(project, row):
    (left, inv), (right, nand) = children(project,row)
    for cell in (inv,nand):
        check_routing(project,cell)
    gap = right['x'] - (left['x'] + inv['student_cell_layout']['width'])
    dy = right['y'] - left['y']
    if gap or dy:
        raise ValueError(f'At the seam, horizontal gap is {gap/1000:g} µm and rail offset is {dy/1000:g} µm. Both must be zero.')
    connectivity = physical.connectivity(project,row['id'])
    if connectivity['issues']:
        raise ValueError(connectivity['issues'][0]['message'])
    shapes = flatten_layout(project,row['id'])
    names = layers(project['pdk'])
    for name in ('m2','m3'):
        region = kdb().Region()
        for shape in shapes:
            if shape['layer'] == names[name]:
                region.insert(polygon(shape))
        if not region.merged().space_check(ROUTING_SPACE).is_empty():
            raise ValueError(f'Clear {name.upper()} spacing below {ROUTING_SPACE/1000:g} µm around the seam.')
    return dict(width_um=(inv['student_cell_layout']['width']+nand['student_cell_layout']['width'])/1000,
                seam_gap_um=0, rail_offset_um=0, continuous_rails=['VPWR','VGND'], spacing_issues=0)
