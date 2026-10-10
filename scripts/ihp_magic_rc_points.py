"""Place bounded IHP resistance endpoints on verified checkpoint metal pins.

Magic may expand imported labels to conductor bounding boxes. Those boxes can
span several tiles and produce duplicate or negative-area resistance nodes.
Select each exact net label, then make it a point. Never select every label in
the box: that can also move nearby floating-fill names onto the circuit.
The caller must verify the checkpoint pins against the actual electrical GDS.
"""
import re


METALS = dict(zip(('Metal1', 'Metal2', 'Metal3', 'Metal4', 'Metal5',
                  'TopMetal1', 'TopMetal2'), ('m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7')))


def point(pin):
    box = pin.get('box_nm')
    if (not isinstance(box, list) or len(box) != 4 or
            any(type(v) is not int for v in box) or pin.get('layer') not in METALS):
        raise ValueError('A captured integer-nanometre metal pin is required.')
    x0, y0, x1, y1 = box
    x, y = ((x0 + x1) // 10) * 5, ((y0 + y1) // 10) * 5
    if not (x0 < x < x1 and y0 < y < y1):
        raise ValueError('The 5 nm native-grid point must lie strictly inside its pin.')
    return x, y, METALS[pin['layer']]


def prepare(labels, boundary):
    checkpoint = labels.get('checkpoint_sha256')
    if (not isinstance(checkpoint, str) or not re.fullmatch('[0-9a-f]{64}', checkpoint)
            or checkpoint != boundary.get('checkpoint_sha256')):
        raise ValueError('Label and boundary checkpoints differ.')
    nets, aliases = {}, set()
    for net in labels['nets']:
        alias = net['alias']
        if (not re.fullmatch(r'NET\d{6}', alias) or alias in aliases or
                net['net'] in nets):
            raise ValueError('Ambiguous or unsafe net identity.')
        aliases.add(alias)
        nets[net['net']] = net
    if not {'VDD', 'VSS'} <= nets.keys():
        raise ValueError('The reference requires explicit ideal supply nets.')
    ports = {}
    for name, port in boundary['ports'].items():
        net = port['net']
        if net not in nets or net in ports or not port['boxes']:
            raise ValueError('Unknown, repeated or empty boundary terminal.')
        ports[net] = port['boxes'][0]
    commands, points = [], []
    for name, net in nets.items():
        alias = net['alias']
        if not net['pins']:
            if name in ports:
                raise ValueError('A boundary terminal has no verified metal pin.')
            continue
        if name not in ports or name in ('VDD', 'VSS'):
            commands.append(f'port {alias} remove')
        if name in ('VDD', 'VSS'):
            continue
        pin = ports[name] if name in ports else net['pins'][0]
        x, y, layer = point(pin)
        commands.extend(('select clear', f'findlabel {alias}',
                         f'select area labels {alias}',
                         f'setlabel box {x / 1000:.6f}um {y / 1000:.6f}um '
                         f'{x / 1000:.6f}um {y / 1000:.6f}um',
                         f'setlabel layer {layer}', 'select clear'))
        points.append(dict(net=name, alias=alias, point_nm=[x, y],
                           layer=pin['layer'], boundary=name in ports))
    return dict(schema=1, checkpoint_sha256=checkpoint, commands='\n'.join(commands),
                points=points, qualified=False,
                scope='Exact label selection on verified pins; ideal supplies. '
                      'Native capacitance, device and resistance audits remain mandatory.')
