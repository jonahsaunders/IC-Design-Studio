"""Bounded scalar expansion of Xschem instance arrays and labelled bundles.

Supports scalar names and a single ascending/descending [start:end] range.
Electrical fan-out is resolved before changing drawing positions. More complex
Xschem repetition/slice expressions remain explicit import errors.
"""
import re
from .model import NAME, NET, clone, uid

RANGE = re.compile(r'([A-Za-z_][A-Za-z0-9_.$-]*)\[(\d+):(\d+)\]')
INDEX = re.compile(r'([A-Za-z_][A-Za-z0-9_.$-]*)\[(\d+)\]')
MAX_VECTOR = 128


def signals(text):
    match = RANGE.fullmatch(text)
    if match:
        start, end = int(match[2]), int(match[3])
        if abs(end - start) + 1 > MAX_VECTOR:
            raise ValueError('An imported Xschem vector supports at most 128 elements.')
        step = 1 if end >= start else -1
        return [f'{match[1]}[{i}]' for i in range(start, end + step, step)]
    if NET.fullmatch(text):
        return [text]
    raise ValueError('Unsupported Xschem vector expression: ' + text)


def instance_names(text):
    if NAME.fullmatch(text):
        return [text]
    values = signals(text)
    if any(not INDEX.fullmatch(v) for v in values):
        raise ValueError('Unsupported instance name ' + text)
    names = [INDEX.sub(r'\1__\2', value) for value in values]
    if any(not NAME.fullmatch(name) for name in names):
        raise ValueError('Expanded instance name exceeds the native name limit: ' + text)
    return names


def net_name(cell, text):
    values = signals(text)
    if len(values) == 1:
        return values[0]
    bundles = cell.setdefault('_xschem_bundles', {})
    # A fresh identity prevents collision with a source circuit's actual labels.
    if text not in bundles:
        bundles[text] = 'vector_' + uid()
    return bundles[text]


def expand(cell, project):
    """Replace vector instances with explicitly labelled scalar devices."""
    bundles = {alias: signals(text) for text, alias in cell.pop('_xschem_bundles', {}).items()}
    arrays = [d for d in cell['devices'] if d.get('_xschem_names')]
    if not bundles and not arrays:
        return
    from .layout_limits import MAX_MASTER_DEVICES
    count = sum(len(d.get('_xschem_names', [d['name']])) for d in cell['devices'])
    if count > MAX_MASTER_DEVICES:
        raise ValueError('Expanded Xschem instances exceed the per-cell device limit.')
    names = set()
    for d in cell['devices']:
        for name in d.get('_xschem_names', [d['name']]):
            if name.casefold() in names:
                raise ValueError('Expanded Xschem instance name collides: ' + name)
            names.add(name.casefold())
    # Remove only bundled conductors. Scalar wiring retains its original drawing.
    cell['wires'] = [w for w in cell['wires'] if w.get('net') not in bundles]
    removed = {l['id'] for l in cell['labels'] if l['name'] in bundles}
    cell['labels'] = [l for l in cell['labels'] if l['id'] not in removed]
    cell['xschem']['components'] = [i for i in cell['xschem']['components'] if i.get('label_id') not in removed]
    # Added members occupy a separate labelled bank, away from source wiring.
    from .wiring import pins
    points = list(pins(cell, project).values()) + [pt for w in cell['wires'] for pt in w['points']]
    bank_x = max([pt[0] for pt in points] + [0]) + 600
    bank_y = min([pt[1] for pt in points] + [0])
    devices, mapping = [], []
    extra = 0
    for d in cell['devices']:
        scalar_names = d.pop('_xschem_names', [d['name']])
        nets = {pin: bundles.get(net, [net]) for pin, net in d['nets'].items()}
        if any(len(values) not in (1, len(scalar_names)) for values in nets.values()):
            raise ValueError('Vector terminal width does not match instance count: ' + d['name'])
        expanded = len(scalar_names) > 1 or any(d['nets'][pin] in bundles for pin in nets)
        for index, name in enumerate(scalar_names):
            item = d if index == 0 else clone(d)
            item['name'] = name
            if index:
                item['id'] = uid()
                item['x'] = bank_x + (extra % 8) * 600
                item['y'] = bank_y + (extra // 8) * 600
                extra += 1
                item['xschem']['record_index'] = -1
                item['xschem']['device_id'] = item['id']
                cell['xschem']['components'].append(item['xschem'])
            if expanded:
                item['nets'] = {pin: values[0] if len(values) == 1 else values[index] for pin, values in nets.items()}
                item['net_labels'] = dict(item['nets'])
            item['xschem']['properties']['name'] = name
            item['symbol_context']['name'] = name
            devices.append(item)
        mapping.append({'source': d['xschem']['original_properties'].get('name', d['name']), 'instances': scalar_names})
    cell['devices'] = devices
    cell['xschem']['vector_expansion'] = mapping
    from .wiring import rebuild
    rebuild(cell, project)
