"""Strict OpenRCX SPEF readback and floating-fill timing model export.

Only the pinned extractor's 1 PF / 1 OHM dialect is accepted. Signal terminals
and resistances survive reduction unchanged; each mutual is checked at both
owning nets. This is a quasistatic fill model, not a calibrated field solver.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import math
from pathlib import Path
import re

from .model import atomic_write


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse(path):
    path = Path(path)
    require(0 < path.stat().st_size <= 128*1024**2, 'SPEF exceeds the 128 MiB capture budget.')
    maps = {}; nets = {}; units = {}; current = None; section = None; owners = {}
    def node(token):
        if not token.startswith('*'):
            return token
        match = re.fullmatch(r'\*(\d+)(:.*)?', token)
        require(match is not None and match[1] in maps, 'Unknown SPEF name-map reference.')
        return maps[match[1]] + (match[2] or '')
    def own(name, net):
        require(name not in owners or owners[name] == net, 'SPEF node belongs to multiple nets.')
        owners[name] = net
    def value(text, positive=False):
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError('Invalid SPEF numeric value.') from exc
        require(number.is_finite() and (number > 0 if positive else number >= 0), 'Invalid SPEF RC value.')
        return number
    identifiers = set(); name = None
    for line in path.read_text().splitlines():
        t = line.split()
        if not t:
            continue
        key = t[0]
        if key in ('*R_UNIT', '*C_UNIT'):
            require(current is None and key not in units, 'Repeated or misplaced SPEF units.')
            units[key] = t[1:]; continue
        if key == '*NAME_MAP':
            require(not maps and current is None, 'Repeated SPEF name map.')
            section = 'map'; continue
        if key == '*D_NET':
            require(len(t) == 3 and section in ('*END', '*PORTS', 'map'), 'Malformed or unterminated SPEF net.')
            name = node(t[1]); require(name not in nets, 'Repeated SPEF net.')
            current = dict(total=value(t[2]), ground={}, coupling=[], res=[], conn=[])
            nets[name] = current; section = 'net'; continue
        if key in ('*CONN', '*CAP', '*RES', '*PORTS', '*END'):
            if key != '*PORTS':
                require(current is not None, 'SPEF section outside a net.')
            else:
                require(current is None, 'Misplaced SPEF port section.')
            section = key; identifiers = set(); continue
        if section == 'map':
            require(len(t) == 2 and re.fullmatch(r'\*\d+', key) is not None, 'Malformed SPEF name map.')
            require(key[1:] not in maps and t[1] not in maps.values(), 'Repeated SPEF name-map entry.')
            maps[key[1:]] = t[1]; continue
        if section == '*CONN':
            require(len(t) >= 3 and key in ('*I', '*P', '*N'), 'Malformed SPEF terminal.')
            n = node(t[1]); own(n, name)
            require(n not in identifiers, 'Repeated SPEF terminal.'); identifiers.add(n)
            current['conn'].append([key, n, *t[2:]]); continue
        if section in ('*CAP', '*RES'):
            require(key.isdigit() and key not in identifiers, 'Repeated or invalid SPEF element identifier.')
            identifiers.add(key)
            require(len(t) in ((3, 4) if section == '*CAP' else (4,)), 'Malformed SPEF element.')
            v = value(t[-1], section == '*RES')
            if section == '*CAP' and len(t) == 3:
                n = node(t[1]); own(n, name)
                require(n not in current['ground'], 'Repeated SPEF ground capacitance.')
                current['ground'][n] = v
            else:
                pair = tuple(sorted((node(t[1]), node(t[2]))))
                require(pair[0] != pair[1], 'SPEF element has identical endpoints.')
                if section == '*RES':
                    for n in pair: own(n, name)
                    current['res'].append((pair, v))
                else:
                    current['coupling'].append((pair, v))
            continue
        require(current is None or section == '*PORTS', 'Unexpected SPEF content after a net.')
    require(section == '*END' and nets, 'SPEF has no complete extracted nets.')
    require(units == {'*R_UNIT': ['1', 'OHM'], '*C_UNIT': ['1', 'PF']}, 'Unsupported SPEF units.')
    couplings = defaultdict(list)
    for name, item in nets.items():
        for pair, v in item['coupling']:
            require(all(n in owners for n in pair), 'SPEF coupling endpoint was not extracted.')
            require(name in {owners[n] for n in pair}, 'SPEF coupling belongs to another net.')
            couplings[pair].append((name, v))
        total = sum(item['ground'].values(), Decimal(0)) + sum((v for _, v in item['coupling']), Decimal(0))
        require(abs(total-item['total']) <= max(Decimal('1e-10'), abs(total)*Decimal('2e-5')),
                'SPEF net total disagrees with extracted capacitance.')
    for pair, items in couplings.items():
        expected = {owners[n] for n in pair}
        require(len(items) == len(expected) and {n for n, _ in items} == expected and len({v for _, v in items}) == 1,
                'SPEF mutual capacitance is missing, duplicated or inconsistent.')
    return dict(nets=nets, owners=owners, couplings={p: items[0][1] for p, items in couplings.items()})


def reduce(path, target, floating):
    from .fill_capacitance import reduce_floating
    data = parse(path); floats = set(floating); owners = data['owners']
    require(floats and floats <= data['nets'].keys(), 'Extracted floating-fill nets are missing.')
    require({n for n in data['nets'] if n.startswith('ICSTUDIO_FLOAT_')} == floats, 'Unexpected floating-fill extraction.')
    for f in floats:
        item = data['nets'][f]
        require(all(r[0] == '*N' for r in item['conn']) and len(item['res']) == 1 and len(item['ground']) == 2,
                'A floating square must extract as an isolated two-node resistor.')
        require(set(item['ground']) == set(item['res'][0][0]), 'Floating square extraction is incomplete.')
    def collapse(n): return owners[n] if owners[n] in floats else n
    ground = defaultdict(float); caps = defaultdict(float)
    for n in owners: ground[collapse(n)] += 0.
    for item in data['nets'].values():
        for n, v in item['ground'].items(): ground[collapse(n)] += float(v)*1e-12
    for (a, b), v in data['couplings'].items():
        a, b = collapse(a), collapse(b)
        if a != b: caps[tuple(sorted((a, b)))] += float(v)*1e-12
    reduced = reduce_floating(dict(ground), dict(caps), floats, max_component=256)
    export(path, target, data, reduced)
    return reduced


def export(path, target, data, reduced):
    floats = set(reduced['floating_nodes'])
    kept = {n: v for n, v in data['nets'].items() if n not in floats}
    grounds = {n: v*1e12 for n, v in reduced['ground_f'].items()}
    couplings = {(r['a'], r['b']): r['value_f']*1e12 for r in reduced['coupling_f']}
    header = Path(path).read_text().split('*D_NET', 1)[0]; mapping = {}
    for line in header.splitlines():
        match = re.fullmatch(r'\*(\d+) (\S+)', line)
        if match: mapping[match[2]] = '*'+match[1]
    header = '\n'.join(line for line in header.splitlines() if not any(line.endswith(' '+n) for n in floats))
    ports = {r[1] for item in kept.values() for r in item['conn'] if r[0] == '*P'}
    def token(n):
        if n in mapping: return mapping[n]
        if ':' not in n:
            require(n in ports, 'Unmapped retained SPEF node.'); return n
        parent, suffix = n.rsplit(':', 1)
        require(parent in mapping, 'Unmapped retained SPEF instance.')
        return mapping[parent]+':'+suffix
    lines = [header.rstrip()]; owners = data['owners']
    for name, item in kept.items():
        gc = [(n, v) for n, v in grounds.items() if owners[n] == name]
        cc = [(p, v) for p, v in couplings.items() if name in {owners[n] for n in p}]
        total = math.fsum([v for _, v in gc]+[v for _, v in cc])
        lines += ['', '*D_NET '+mapping[name]+' '+format(total, '.17g'), '*CONN']
        lines += [' '.join([r[0], token(r[1]), *r[2:]]) for r in item['conn']]
        lines.append('*CAP'); i = 1
        for n, v in sorted(gc): lines.append(f'{i} {token(n)} {v:.17g}'); i += 1
        for (a, b), v in sorted(cc): lines.append(f'{i} {token(a)} {token(b)} {v:.17g}'); i += 1
        lines.append('*RES')
        lines += [f'{i} {token(p[0])} {token(p[1])} {v}' for i, (p, v) in enumerate(item['res'], 1)]
        lines.append('*END')
    atomic_write(target, '\n'.join(lines)+'\n')
    reread = parse(target)
    require(reread['nets'].keys() == kept.keys(), 'Reduced SPEF lost signal nets.')
    for n, item in kept.items():
        require(reread['nets'][n]['res'] == item['res'] and reread['nets'][n]['conn'] == item['conn'],
                'Reduced SPEF changed signal resistance or terminals.')
    actual = {n: float(v) for item in reread['nets'].values() for n, v in item['ground'].items()}
    require(all(math.isclose(actual.get(n, 0), grounds.get(n, 0), rel_tol=1e-14, abs_tol=1e-20)
                for n in actual.keys() | grounds.keys()), 'Reduced SPEF ground capacitance changed on readback.')
    require(all(math.isclose(float(reread['couplings'].get(p, 0)), couplings.get(p, 0), rel_tol=1e-14, abs_tol=1e-20)
                for p in reread['couplings'].keys() | couplings.keys()), 'Reduced SPEF coupling changed on readback.')
