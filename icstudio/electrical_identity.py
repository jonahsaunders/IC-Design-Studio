"""Persistent electrical identities, independent of route vertex numbering.

Geometry establishes intentional connections; this ledger follows their identity
through edits. Splits retain one identity, merges retain one predecessor, and
terminal identities survive renames, movement, route edits and save/reopen.
"""
from collections import defaultdict
from .model import digest


def terminal_id(device, pin):
    identity = device.get('symbol', {}).get('pin_meta', {}).get(pin, {}).get('id', pin)
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
    candidates = []
    for name, group in groups.items():
        for prior in old:
            terminals = len(set(group['terminals']) & set(prior['terminals']))
            wires = len(set(group['wires']) & set(prior['wires']))
            if terminals or wires:
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
