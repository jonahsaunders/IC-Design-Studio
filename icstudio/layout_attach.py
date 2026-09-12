"""Explicit cell-level attachment; matching names never establish LVS."""
from .model import clone, validate, digest


def matching_cells(project, layout):
    names = {c['name']: c['id'] for c in project['cells']}
    return {c['id']: names[c['name']] for c in layout['cells'] if c['name'] in names}


def attach(project, layout, mapping):
    validate(project); validate(layout)
    before = {c['id']: c for c in project['cells']}
    incoming = {c['id']: c for c in layout['cells']}
    if not mapping or not set(mapping) <= incoming.keys() or not set(mapping.values()) <= before.keys():
        raise ValueError('Choose existing layout and schematic cells.')
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('Each schematic cell can receive only one layout cell.')
    if mapping.get(layout['top']) != project['top']:
        raise ValueError('The layout top must map to the schematic top.')
    if any(before[c].get(key) for c in mapping.values()
           for key in ('shapes', 'layout_instances', 'layout_texts', 'layout_ports')):
        raise ValueError('Mapped cells already contain layout. Use external layout review to merge edits.')
    result = clone(project); by = {c['id']: c for c in result['cells']}
    layers = result['pdk']['layers']; pairs = {(l['gds'], l['datatype']): l['name'] for l in layers}
    layer_map = {}
    for layer in layout['pdk']['layers']:
        pair = (layer['gds'], layer['datatype'])
        if pair not in pairs:
            item = clone(layer); name = item['name']
            while name in {l['name'] for l in layers}: name += '_imported'
            item['name'] = name; layers.append(item); pairs[pair] = name
        layer_map[layer['name']] = pairs[pair]
    ids = {key: mapping.get(key, key) for key in incoming}
    for original in layout['cells']:
        c = clone(original)
        if c['id'] in mapping:
            dest = by[mapping[c['id']]]
        else:
            if c['id'] in by or any(q['name'].casefold() == c['name'].casefold() for q in result['cells']):
                raise ValueError('Unmapped layout cell collides with an existing cell: ' + c['name'])
            dest = c; result['cells'].append(dest)
        for key in ('shapes', 'layout_instances', 'layout_texts', 'external_properties'):
            dest[key] = c.get(key, [])
        for item in dest['shapes'] + dest['layout_texts']: item['layer'] = layer_map[item['layer']]
        for inst in dest['layout_instances']: inst['cell'] = ids[inst['cell']]
    if layout.get('layout_source'): result['layout_source'] = clone(layout['layout_source'])
    result['layout_attachment'] = dict(schema=1, source_hash=digest(layout),
        cells=[dict(layout=incoming[k]['name'], schematic=before[v]['name']) for k, v in mapping.items()],
        verification='Cell names reviewed. Electrical equivalence requires extraction and LVS.')
    return validate(result)
