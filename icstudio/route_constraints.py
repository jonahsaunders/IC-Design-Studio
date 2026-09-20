"""Persisted geometric route intent and checks after editing.

Version 1 records retain their original length-only meaning. Version 2 records
also bind widths, layer balance, via structure and physical endpoint contact.
These checks describe geometry, never extracted resistance or delay matching.
"""
from .model import digest
from .layout_routing import length
from .layout import polygon


def validate_records(p):
    """Validate persisted intent without requiring existing geometry to pass it."""
    from .model import NET
    def integer(value,minimum=0): return type(value) is int and value>=minimum
    def endpoint(value):
        return (isinstance(value,dict) and isinstance(value.get('layer'),str)
                and isinstance(value.get('point'),(list,tuple)) and len(value['point'])==2
                and all(type(v) is int for v in value['point']))
    for c in p['cells']:
        rows=c.get('routing_records',[])
        if not isinstance(rows,list):raise ValueError('Saved routing records must be a list.')
        for row in rows:
            if not isinstance(row,dict):raise ValueError('Each saved routing record must be an object.')
            if row.get('kind') not in ('matched_pair','shield'):continue
            if row.get('version',1) not in (1,2):raise ValueError('Unsupported saved route-constraint version.')
            if not isinstance(row.get('route_group'),str) or not row['route_group']:raise ValueError('A saved route constraint needs its route identity.')
            ids=row.get('shape_ids')
            if not isinstance(ids,list) or not ids or any(not isinstance(v,str) for v in ids) or len(set(ids))!=len(ids):raise ValueError('A constrained route needs distinct shape identities.')
            if row['kind']=='matched_pair':
                nets=row.get('nets')
                if not isinstance(nets,list) or len(nets)!=2 or any(not isinstance(n,str) or not NET.fullmatch(n) for n in nets) or nets[0]==nets[1]:raise ValueError('A matched route needs two distinct valid nets.')
                if not integer(row.get('tolerance_nm')):raise ValueError('Saved route tolerance must be non-negative integer nanometres.')
                if row.get('version',1)==2:
                    m=row.get('matching',{})
                    if not isinstance(m,dict) or not integer(m.get('width_nm'),1) or type(m.get('match_layers')) is not bool or not integer(m.get('layer_tolerance_nm')):raise ValueError('Saved matching intent needs width, layer tolerance and an explicit layer-matching choice.')
                    ends=row.get('endpoints')
                    if not isinstance(ends,list) or len(ends)!=2 or any(not isinstance(v,list) or len(v)!=2 for v in ends):raise ValueError('A matched route needs two saved endpoint pairs.')
                    for pair in ends:
                        for anchor in pair:
                            if not isinstance(anchor,dict):raise ValueError('A route endpoint anchor must be an object.')
                            kind=anchor.get('kind')
                            valid=(kind=='point' and endpoint(anchor) or kind=='terminal' and all(isinstance(anchor.get(k),str) and anchor[k] for k in ('device_id','pin')) or kind=='port' and isinstance(anchor.get('name'),str) and bool(anchor['name']))
                            if not valid:raise ValueError('A saved route endpoint needs a point, terminal or port identity.')
            else:
                if not isinstance(row.get('net'),str) or not NET.fullmatch(row['net']) or not isinstance(row.get('signal_id'),str) or not endpoint(row.get('ground')):raise ValueError('Saved shielding needs a signal identity, reference net and tie point.')
                if not integer(row.get('gap_nm',0)):raise ValueError('Saved shield gap must be non-negative integer nanometres.')
                if row.get('version',1)==2 and (not integer(row.get('max_gap_nm')) or row['max_gap_nm']<row.get('gap_nm',0) or not isinstance(row.get('signal_net'),str) or not NET.fullmatch(row['signal_net'])):raise ValueError('Saved shielding needs a valid signal net and maximum gap at least equal to its minimum.')


def route_metrics(shapes):
    layers = {}; widths = {}; vias = {}
    for shape in shapes:
        if shape['kind'] == 'path':
            layer = shape['layer']
            layers[layer] = layers.get(layer, 0) + length([shape])
            widths.setdefault(layer, set()).add(shape['width'])
        if shape.get('via_group'):
            vias.setdefault(shape['via_group'], []).append(shape['layer'])
    signatures = {}
    for layers_ in vias.values():
        key = '/'.join(sorted(layers_)); signatures[key] = signatures.get(key, 0)+1
    return dict(length_nm=length(shapes), layers_nm=layers,
                widths_nm={k: sorted(v) for k,v in widths.items()}, vias=signatures)


def endpoint_anchor(p, cid, endpoint):
    """Prefer stable logical terminal identities to fixed cursor coordinates."""
    from .physical_cells import terminals, ports
    for pin in terminals(p,cid):
        if pin['layer'] == endpoint['layer'] and pin['point'] == endpoint['point']:
            return dict(kind='terminal', device_id=pin['device_id'], pin=pin['pin'])
    for port in ports(p,cid):
        if port['layer'] == endpoint['layer'] and port['point'] == endpoint['point']:
            return dict(kind='port', name=port['name'])
    return dict(kind='point', **endpoint)


def _endpoint(p, cid, anchor):
    from .physical_cells import terminals, ports
    if anchor['kind'] == 'point': return anchor
    if anchor['kind'] == 'terminal':
        return next((v for v in terminals(p,cid) if v['device_id']==anchor['device_id'] and v['pin']==anchor['pin']), None)
    return next((v for v in ports(p,cid) if v['name']==anchor['name']), None)


def findings(p, cid):
    from .layout import kdb
    from .layout_topology import partition, shape_key
    c = next(c for c in p['cells'] if c['id'] == cid)
    by = {s['id']: s for s in c['shapes']}; out = []; parts = None
    for row in c.get('routing_records', []):
        if not row.get('shape_ids') or row.get('kind') not in ('matched_pair', 'shield'): continue
        messages = []; metrics = {}; ids = row['shape_ids']
        shapes = [by[k] for k in ids if k in by]
        missing = len(set(ids)-by.keys()); metrics['missing_shapes'] = missing
        if missing: messages.append('Part of the constrained route was deleted.')
        elif row['kind'] == 'matched_pair':
            nets = row['nets']; traces = [[s for s in shapes if s.get('net') == n] for n in nets]
            measured = [route_metrics(v) for v in traces]
            metrics['length_skew_nm'] = abs(measured[0]['length_nm']-measured[1]['length_nm'])
            metrics['length_excess_nm'] = max(0, metrics['length_skew_nm']-row['tolerance_nm'])
            metrics['net_errors'] = sum(s.get('net') not in nets for s in shapes)
            if metrics['net_errors']: messages.append('A matched route changed its assigned net.')
            if metrics['length_excess_nm']: messages.append('Geometric route length skew exceeds the saved tolerance.')
            if row.get('version',1) >= 2:
                intent = row['matching']; metrics['measured_routes'] = measured
                metrics['width_errors'] = sum(s['kind']=='path' and s['width']!=intent['width_nm'] for s in shapes)
                if metrics['width_errors']: messages.append('Restore the saved common route width.')
                metrics['layer_excess_nm'] = sum(max(0,abs(measured[0]['layers_nm'].get(l,0)-measured[1]['layers_nm'].get(l,0))-intent['layer_tolerance_nm']) for l in measured[0]['layers_nm'].keys() | measured[1]['layers_nm'].keys()) if intent['match_layers'] else 0
                if metrics['layer_excess_nm']: messages.append('Per-layer route length skew exceeds the saved tolerance.')
                metrics['via_errors'] = sum(abs(measured[0]['vias'].get(k,0)-measured[1]['vias'].get(k,0)) for k in measured[0]['vias'].keys() | measured[1]['vias'].keys())
                if metrics['via_errors']: messages.append('The matched routes need equal via counts and layer transitions.')
                if parts is None: parts = partition(p,cid)
                groups = [{parts.get(shape_key(s),frozenset()) for s in trace} for trace in traces]
                metrics['disconnected_components'] = sum(max(0,len(v)-1) for v in groups)
                metrics['shorts'] = int(bool(groups[0] & groups[1]))
                if metrics['disconnected_components']: messages.append('A matched route contains physically disconnected geometry.')
                if metrics['shorts']: messages.append('The two matched routes are physically shorted.')
                endpoint_errors = 0
                for trace,anchors in zip(traces,row['endpoints']):
                    for anchor in anchors:
                        endpoint = _endpoint(p,cid,anchor)
                        if not endpoint or not any(s['layer']==endpoint['layer'] and polygon(s).inside(kdb().Point(*endpoint['point'])) for s in trace): endpoint_errors += 1
                metrics['endpoint_errors'] = endpoint_errors
                if endpoint_errors: messages.append('Reconnect the route to its saved terminal or endpoint.')
        elif row['kind'] == 'shield':
            signal = by.get(row['signal_id']); shields = [s for s in shapes if s.get('shield_for') == row['signal_id']]
            if not signal or signal['kind'] != 'path' or len(signal['points']) != 2 or len(shields) != 2:
                messages.append('The shield requires its original straight signal and both side traces.')
            else:
                a,b = signal['points']; axis = 0 if a[1] == b[1] else 1; other = 1-axis; signs = []
                metrics['coverage_errors'] = 0; metrics['gap_excess_nm'] = 0
                if a==b or a[0]!=b[0] and a[1]!=b[1]: messages.append('The shielded signal must remain a straight Manhattan path.')
                if signal.get('net') == row['net'] or row.get('signal_net',signal.get('net')) != signal.get('net'):
                    messages.append('Restore the shielded signal net; it must differ from the reference net.')
                for s in shields:
                    if s['kind']!='path' or len(s['points']) != 2 or s['layer'] != signal['layer'] or s.get('net') != row['net']:
                        metrics['coverage_errors'] += 1; continue
                    u,v = s['points']; gap = abs(u[other]-a[other])-(s['width']+signal['width'])/2
                    metrics['gap_excess_nm'] += max(0,row.get('gap_nm',0)-gap,gap-row.get('max_gap_nm',float('inf')))
                    if u[other] != v[other] or sorted((u[axis],v[axis])) != sorted((a[axis],b[axis])): metrics['coverage_errors'] += 1
                    signs.append(u[other]-a[other])
                if len(signs)!=2 or signs[0]*signs[1] >= 0: metrics['coverage_errors'] += 1
                if metrics['coverage_errors']: messages.append('Restore both parallel shields on opposite sides covering the whole signal.')
                if metrics['gap_excess_nm']: messages.append('Shield spacing is outside the saved minimum and maximum gap.')
                if parts is None: parts = partition(p,cid)
                ground = row['ground']
                from .design_ops import flatten_layout
                anchors = [shape_key(s) for s in flatten_layout(p,cid) if s['layer'] == ground['layer'] and s.get('net') == row['net'] and polygon(s).inside(kdb().Point(*ground['point']))]
                metrics['tie_errors'] = sum(not any(k in parts.get(shape_key(s), ()) for k in anchors) for s in shields)
                if not anchors or metrics['tie_errors']: messages.append('A shield lost contact with its saved reference tie point.')
                metrics['shorts'] = int(any(shape_key(signal) in parts.get(shape_key(s),()) for s in shields))
                if metrics['shorts']: messages.append('The shield reference is physically shorted to the signal.')
        if messages:
            linked = shapes + ([by[row['signal_id']]] if row.get('signal_id') in by else [])
            boxes = [[b.left,b.bottom,b.right,b.top] for s in linked for b in [polygon(s).bbox()]]
            bbox = [min(v[0] for v in boxes),min(v[1] for v in boxes),max(v[2] for v in boxes),max(v[3] for v in boxes)] if boxes else None
            out.append(dict(severity='error', code='ROUTE.'+row['kind'].upper(), cell_id=cid,
                            constraint_id=row['route_group'], object=row['route_group'], objects=ids,
                            shape_ids=[s['id'] for s in linked], boxes=boxes, bbox=bbox, metrics=metrics,
                            message=' '.join(messages), reasons=messages, remediation='Review highlighted geometry and replan the constrained route with its saved nets and endpoints.',
                            fingerprint=digest([row['route_group'],messages])))
    return out


def enforce(before, after, cid, strict=False):
    """Reject new or worsened violations; strict mode requires all checks to pass.

    Existing incomplete layouts remain editable when measured errors improve or
    stay unchanged. A new failure reason cannot hide behind an older finding.
    """
    from .analog_constraints import findings as analog
    key = lambda f: (f['code'], f.get('constraint_id', f.get('object')))
    old = {key(f): f for f in findings(before,cid)+analog(before,cid)}
    current = findings(after,cid)+analog(after,cid)
    for finding in current:
        prior = old.get(key(finding))
        if strict or prior is None:
            raise ValueError('Saved layout constraint: '+finding['message'])
        worsened = any(isinstance(value,(int,float)) and value > prior.get('metrics',{}).get(name,0)
                       for name,value in finding.get('metrics',{}).items()
                       if name not in ('length_skew_nm',))
        old_reasons=set(prior.get('reasons',[prior['message']]))
        new_reasons=set(finding.get('reasons',[finding['message']]))
        if worsened or new_reasons-old_reasons:
            raise ValueError('Saved layout constraint worsened: '+finding['message'])
    return current


def affected_cells(p, changed):
    """Include every physical ancestor, even when editing a child as active cell."""
    from .physical_cells import reachable
    changed=set(changed)
    return [c['id'] for c in p['cells'] if c['id'] in changed or changed.intersection(reachable(p,c['id'],physical=True))]


def enforce_affected(before,after,changed,strict=False):
    return {cid:enforce(before,after,cid,strict) for cid in affected_cells(after,changed)}
