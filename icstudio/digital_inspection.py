"""Revision-scoped selection and connectivity for linked digital views."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Selection:
    run_id: str
    cell_id: str
    module: str
    name: str
    kind: str = 'cell'
    bit: int | None = None

    def record(self):
        return asdict(self)


def cone(index, module, name, depth=2, limit=80):
    """Connectivity neighborhood with directed edges when port directions exist."""
    objects = {i['name']: i for i in index if i['module'] == module}
    if name not in objects:
        return {'nodes': [], 'edges': [], 'truncated': False}
    by_bit = defaultdict(list)
    for item in objects.values():
        if item['kind'] != 'cell':
            continue
        for port, bits in item.get('connections', {}).items():
            for bit in bits:
                if isinstance(bit, int):
                    by_bit[bit].append((item['name'], port, item.get('port_directions', {}).get(port, 'inout')))
    selected = {name: 0}; todo = deque([name]); edges = set(); truncated = False
    while todo:
        key = todo.popleft(); level = selected[key]; item = objects[key]
        bits = item.get('bits', []) if item['kind'] == 'net' else [b for values in item.get('connections', {}).values() for b in values]
        for bit in bits:
            if not isinstance(bit, int):
                continue
            peers = by_bit[bit]
            for other, port, direction in peers:
                if other == key:
                    continue
                if other not in selected:
                    if level >= depth:
                        continue
                    if len(selected) >= limit:
                        truncated = True; continue
                    selected[other] = level + 1; todo.append(other)
                here = [d for n,p,d in peers if n==key]
                if item['kind']=='net':
                    edges.add((other,key,bit) if direction=='output' else (key,other,bit))
                elif direction=='output' and any(d in ('input','inout') for d in here):
                    edges.add((other,key,bit))
                elif direction in ('input','inout') and any(d in ('output','inout') for d in here):
                    edges.add((key,other,bit))
    return {'nodes': [{**objects[key], 'distance': distance} for key, distance in selected.items()],
            'edges': [{'source': a, 'target': b, 'bit': bit} for a, b, bit in sorted(edges) if a in selected and b in selected],
            'truncated': truncated}


def sources_for_signal(index, full_name):
    """Return all exact candidates; never guess using an unqualified first match."""
    import re
    name = re.sub(r'\[[^\]]*\]$', '', full_name)
    candidates = []
    for item in index:
        if item['kind'] != 'net':
            continue
        qualified = item['module'] + '.' + item['name'].replace('/', '.')
        if name == qualified or name.endswith('.' + qualified):
            candidates.append(item)
    if not candidates:
        short = name.rsplit('.', 1)[-1]
        candidates = [i for i in index if i['kind'] == 'net' and i['name'] == short]
    return candidates
