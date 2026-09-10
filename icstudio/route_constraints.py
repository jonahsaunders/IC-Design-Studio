"""Persisted geometric route intent and checks after editing."""
from .model import digest
from .layout_routing import length
from .layout import polygon


def findings(p, cid):
    c = next(c for c in p['cells'] if c['id'] == cid); by = {s['id']: s for s in c['shapes']}; out = []
    for row in c.get('routing_records', []):
        if not row.get('shape_ids') or row.get('kind') not in ('matched_pair', 'shield'): continue
        message = ''
        if not set(row['shape_ids']) <= by.keys(): message = 'Part of the constrained route was deleted.'
        elif row['kind'] == 'matched_pair':
            shapes = [by[k] for k in row['shape_ids']]; lengths = [length([s for s in shapes if s.get('net') == n]) for n in row['nets']]
            if set(s.get('net') for s in shapes)-set(row['nets']): message = 'A matched route changed its assigned net.'
            elif abs(lengths[0]-lengths[1]) > row['tolerance_nm']: message = 'Geometric route length skew exceeds the saved tolerance.'
        elif row['kind'] == 'shield':
            signal = by.get(row['signal_id']); shields = [by[k] for k in row['shape_ids'] if by[k].get('shield_for') == row['signal_id']]
            if not signal or signal['kind'] != 'path' or len(signal['points']) != 2 or len(shields) != 2:
                message = 'The shield requires its original straight signal and both side traces.'
            else:
                a,b = signal['points']; axis = 0 if a[1] == b[1] else 1; other = 1-axis; signs = []
                for s in shields:
                    if len(s['points']) != 2 or s['layer'] != signal['layer'] or s.get('net') != row['net']:
                        message = 'Shield layer, shape or reference net changed.'; break
                    u,v = s['points']; gap = abs(u[other]-a[other])-(s['width']+signal['width'])/2
                    if u[other] != v[other] or sorted((u[axis],v[axis])) != sorted((a[axis],b[axis])) or gap < row.get('gap_nm',0):
                        message = 'Shields no longer cover the signal with the saved minimum gap.'; break
                    signs.append(u[other]-a[other])
                if not message and signs[0]*signs[1] >= 0: message = 'Shields must remain on opposite sides of the signal.'
                if not message:
                    from .layout_topology import partition, shape_key
                    from .layout import kdb
                    parts = partition(p, cid); ground = row['ground']
                    anchors = [shape_key(s) for s in c['shapes'] if s['layer'] == ground['layer'] and s.get('net') == row['net'] and polygon(s).inside(kdb().Point(*ground['point']))]
                    if not anchors or any(not any(k in parts.get(shape_key(s), ()) for k in anchors) for s in shields):
                        message = 'A shield lost contact with its saved reference tie point.'
        if message: out.append({'severity':'error','code':'ROUTE.'+row['kind'].upper(),'cell_id':cid,'object':row['route_group'],'objects':row['shape_ids'],'message':message,'fingerprint':digest([row['route_group'], message])})
    return out


def enforce(before, after, cid):
    from .analog_constraints import findings as analog
    signature = lambda f: (f['code'], f.get('object'), f['message'])
    old = {signature(f) for f in findings(before,cid)+analog(before,cid)}
    added = [f for f in findings(after,cid)+analog(after,cid) if signature(f) not in old]
    if added: raise ValueError('Saved layout constraint: '+added[0]['message'])
