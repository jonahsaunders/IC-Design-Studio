"""Lossless top-level naming adapter for the pinned IHP native LVS reader.

The reader strips []$\\/ from element lines, but not .SUBCKT headers. Encode
every top net and instance through a bijection before parsing; use the same
net aliases on a mask-identical comparison copy of the GDS. Master device
definitions remain byte-for-byte unchanged. This is not LVS acceptance.
"""
from collections import Counter
import hashlib
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def logical_lines(text):
    lines = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('*'):
            continue
        if line.lstrip().startswith('+'):
            require(bool(lines), 'Orphan CDL continuation.')
            lines[-1] += ' ' + line.lstrip()[1:].strip()
        else:
            lines.append(line.strip())
    return lines


def master_pins(text):
    masters = {}
    for line in logical_lines(text):
        tokens = line.split()
        if tokens[0].upper() == '.SUBCKT':
            require(len(tokens) >= 2 and tokens[1] not in masters, 'Repeated master definition.')
            require(all(re.fullmatch(r'[A-Za-z0-9_.-]+', p) for p in tokens[1:]),
                    'Master naming needs a separate adapter.')
            masters[tokens[1]] = tokens[2:]
    require(bool(masters), 'No CDL master definitions.')
    return masters


def encode_reference(raw, masters, database):
    """Check every exported instance terminal against OpenDB, then encode."""
    lines = logical_lines(raw)
    require(len(lines) >= 2 and lines[0].split()[0].upper() == '.SUBCKT' and
            lines[-1].split()[0].upper() == '.ENDS', 'Expected one complete top-level CDL circuit.')
    header = lines[0].split()
    top = database['top']
    require(header[1] == top, 'CDL top differs from the captured checkpoint.')
    ports = header[2:]
    port_names = [p['name'] for p in database['ports']]
    require(len(set(ports)) == len(ports) and set(ports) == set(port_names), 'CDL ports differ from OpenDB.')
    port_nets = {p['net']: p['name'] for p in database['ports']}
    require('' not in port_nets and len(port_nets) == len(port_names),
            'Disconnected or multiply aliased boundary ports need a separate adapter.')
    cells = master_pins(masters)
    instances = {i['name']: i for i in database['database']['instances']}
    require(len(instances) == len(database['database']['instances']), 'Repeated OpenDB instance names.')
    parsed = []; disconnected = {}
    connected_names = {p['net'] for i in instances.values() for p in i['pins'] if p['net']} | set(port_nets)
    nets = set(ports)
    seen = set()
    for line in lines[1:-1]:
        tokens = line.split()
        require(len(tokens) >= 3 and tokens[0].startswith('X'), 'Unexpected top-level CDL element.')
        name, master = tokens[0][1:], tokens[-1]
        require(name in instances and name not in seen and master in cells, 'Unknown or repeated CDL instance.')
        inst = instances[name]
        require(inst['master'] == master, 'CDL master differs from OpenDB.')
        pin_names = cells[master]
        values = tokens[1:-1]
        require(len(values) == len(pin_names), 'CDL instance arity differs from its master.')
        actual = {p['name']: p['net'] for p in inst['pins']}
        require(len(actual) == len(inst['pins']) and set(pin_names) == set(actual), 'Master pins differ from OpenDB.')
        for p, n in zip(pin_names, values):
            if actual[p]:
                require(port_nets.get(actual[p], actual[p]) == n,
                        'CDL terminal differs from the preserved implementation.')
            else:
                require(re.fullmatch(r'_unconnected_\d+', n) is not None and
                        n not in connected_names and n not in ports and n not in disconnected,
                        'A disconnected terminal was shorted or given an ambiguous name.')
                disconnected[n] = dict(instance=name, pin=p)
        seen.add(name); nets.update(values); parsed.append((name, values, master))
    require(seen == set(instances), 'CDL omitted implementation instances, including fillers.')
    uses = Counter(n for _, values, _ in parsed for n in values)
    require(all(uses[n] == 1 for n in disconnected), 'A disconnected terminal was connected to another instance.')
    net_map = {name: 'N' + str(i).zfill(7) for i, name in enumerate(sorted(nets))}
    inst_map = {name: 'I' + str(i).zfill(7) for i, name in enumerate(sorted(instances))}
    output = ['* Lossless IHP top naming; see aliases.json.', '.SUBCKT ' + top + ' ' + ' '.join(net_map[p] for p in ports)]
    output += ['X' + inst_map[name] + ' ' + ' '.join(net_map[n] for n in values) + ' ' + master
               for name, values, master in parsed]
    output += ['.ENDS ' + top, '', masters]
    mapping = dict(schema=1, top=top, nets=net_map, instances=inst_map,
                   ports={p: net_map[p] for p in ports}, source_cdl_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                   masters_sha256=hashlib.sha256(masters.encode()).hexdigest(),
                   boundary_net_names=port_nets, disconnected_terminals=disconnected,
                   checked_instances=len(parsed), checked_terminals=sum(len(v) for _, v, _ in parsed))
    return '\n'.join(output) + '\n', mapping


def label_copy(source, target, mapping):
    import klayout.db as k
    layout = k.Layout(); layout.read(str(source))
    tops = list(layout.top_cells())
    require(len(tops) == 1 and tops[0].name == mapping['top'], 'Unexpected GDS hierarchy.')
    top = tops[0]; bounds = top.bbox(); counts = Counter()
    before = {str(layout.get_info(i)): k.Region(top.begin_shapes_rec(i)).merged() for i in layout.layer_indices()}
    for i in layout.layer_indices():
        info = layout.get_info(i)
        if info.datatype != 25 or info.layer not in (8, 10, 30, 50, 67, 126, 134):
            continue
        for shape in top.shapes(i).each():
            if shape.is_text() and shape.text.string in mapping['ports']:
                label = shape.text
                counts[label.string] += 1
                label.string = mapping['ports'][label.string]
                shape.text = label
    require(set(counts) == set(mapping['ports']), 'A captured port has no top-level metal label.')
    options = k.SaveLayoutOptions(); options.gds2_write_timestamps = False
    layout.write(str(target), options)
    check = k.Layout(); check.read(str(target))
    require(check.top_cell().bbox() == bounds and check.dbu == layout.dbu, 'Port adaptation changed layout extent or units.')
    for name, region in before.items():
        i = check.find_layer(k.LayerInfo.from_string(name))
        require(i is not None and (region ^ k.Region(check.top_cell().begin_shapes_rec(i)).merged()).is_empty(),
                'Port adaptation changed a physical mask.')
    return dict(mask_preservation=True, renamed_labels=dict(counts))
