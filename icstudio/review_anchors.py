"""Resolve review references against the exact checkpoint, without Qt."""
from .electrical_identity import terminal_id


def targets(project, cid, findings=False):
    cell = next((c for c in project['cells'] if c['id'] == cid), None)
    if cell is None: return {}
    result = {}
    for field in ('devices', 'wires', 'labels', 'buses', 'shapes', 'layout_instances', 'layout_pins'):
        view = 'schematic' if field in ('devices', 'wires', 'labels', 'buses') else 'layout'
        for obj in cell.get(field, []):
            result[obj['id']] = dict(label=obj.get('name', obj['id']), view=view,
                                     objects=[('pin:' if field == 'layout_pins' else '') + obj['id']], net='')
    nets = {}
    for d in cell['devices']:
        for pin, net in d['nets'].items():
            result['terminal:' + terminal_id(d, pin)] = dict(label=d['name'] + '.' + pin, view='schematic', objects=[d['id']], net=net)
            nets.setdefault(net, []).append(d['id'])
    for w in cell.get('wires', []): nets.setdefault(w.get('net', ''), []).append(w['id'])
    for l in cell.get('labels', []): nets.setdefault(l['name'], []).append(l['id'])
    for name, objects in nets.items():
        if name: result['net:' + name] = dict(label='Net ' + name, view='schematic', objects=list(dict.fromkeys(objects)), net=name)
    if findings:
        from .electrical_rules import check
        for row in check(project, cid):
            result['finding:' + row['fingerprint']] = dict(label=row['message'], view='schematic',
                cell=row['cell_id'], objects=[row['object']] if row['object'] else [], net=row.get('net', ''))
    return result
