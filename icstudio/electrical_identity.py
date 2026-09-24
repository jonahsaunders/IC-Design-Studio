"""Persistent electrical identities, independent of route vertex numbering.

Geometry establishes intentional connections; this ledger follows their identity
through edits. Splits retain one identity, merges retain one predecessor, and
terminal identities survive renames, movement, route edits and save/reopen.
"""
from collections import defaultdict
from functools import lru_cache
from .model import digest


@lru_cache(maxsize=65536)
def _terminal_id(device_id, identity):
    return 't_' + digest([device_id, identity])[:24]


def terminal_id(device, pin):
    identity = device.get('symbol', {}).get('pin_meta', {}).get(pin, {}).get('id', pin)
    if isinstance(device['id'], str) and isinstance(identity, str):
        return _terminal_id(device['id'], identity)
    # Preserve the original digest behavior for imported metadata whose empty
    # identities are accepted by the existing symbol schema.
    return 't_' + digest([device['id'], identity])[:24]


def identify_symbol(symbol):
    for pin in symbol['pins']:
        symbol.setdefault('pin_meta', {}).setdefault(pin, {}).setdefault('id', 'pin_' + digest([symbol['pins'], pin])[:24])


def synchronize(cell):
    old = cell.get('electrical', {}).get('nets', [])
    groups = defaultdict(lambda: {'terminals': [], 'wires': []})
    for d in cell['devices']:
        d['terminal_ids'] = {pin: terminal_id(d, pin) for pin in d['nets']}
        for pin, net in d['nets'].items():
            groups[net]['terminals'].append(d['terminal_ids'][pin])
    for wire in cell.get('wires', []):
        groups[wire['net']]['wires'].append(wire['id'])
    # Prefer terminal continuity; geometry-only changes cannot steal a pin net.
    # Only a prior net sharing a terminal or wire can be a predecessor. Index
    # those memberships once instead of intersecting every pair of nets. Keep
    # the original global ranking, including its deterministic tie breakers.
    by_terminal = defaultdict(set); by_wire = defaultdict(set)
    for index, prior in enumerate(old):
        for terminal in prior['terminals']: by_terminal[terminal].add(index)
        for wire in prior['wires']: by_wire[wire].add(index)
    candidates = []
    for name, group in groups.items():
        overlaps = defaultdict(lambda: [0, 0])
        for terminal in set(group['terminals']):
            for index in by_terminal.get(terminal, ()): overlaps[index][0] += 1
        for wire in set(group['wires']):
            for index in by_wire.get(wire, ()): overlaps[index][1] += 1
        for index, (terminals, wires) in overlaps.items():
            prior = old[index]
            candidates.append((-terminals, -wires, prior['name'] != name, prior['id'], name))
    assigned = {}; used = set()
    for _, _, _, ident, name in sorted(candidates):
        if name not in assigned and ident not in used:
            assigned[name] = ident; used.add(ident)
    rows = []
    for name, group in sorted(groups.items()):
        if name not in assigned:
            seed = ['net', cell['id'], sorted(group['terminals']), sorted(group['wires'])]
            ident = 'n_' + digest(seed)[:24]
            while ident in used:
                seed.append(ident); ident = 'n_' + digest(seed)[:24]
            assigned[name] = ident; used.add(ident)
        rows.append({'id': assigned[name], 'name': name,
                     'terminals': sorted(group['terminals']), 'wires': sorted(group['wires'])})
    for d in cell['devices']:
        d['net_ids'] = {pin: assigned[name] for pin, name in d['nets'].items()}
    for wire in cell.get('wires', []):
        wire['net_id'] = assigned[wire['net']]
    cell['electrical'] = {'version': 1, 'nets': rows}


def partition(cell):
    groups = defaultdict(list)
    for d in cell['devices']:
        for pin, name in d['nets'].items():
            groups[name].append((d['id'], pin))
    return sorted(sorted(members) for members in groups.values())


def require_preserved(before, after):
    if partition(before) != partition(after):
        raise ValueError('This move would change electrical connections. Move to a clear location, or use an explicit connection edit.')
