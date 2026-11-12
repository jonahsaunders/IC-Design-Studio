"""Experimental reciprocal port transform for the conserved IHP C matrix.

One ideal transformer per distributed net maps voltage to its weighted mean
and returns capacitor current to every physical endpoint with the same weight.
Positive same-net capacitors restore the original distributed diagonal. This
changes the linear realization only; it must be independently audited and
compared in the native simulator before accepting performance results.
"""
import math
import re

PREFIX = 'IHP_CPORT_'


def build(weights, ground_af, coupling_af, original_diagonal_af, reference):
    if (set(weights) != set(ground_af) or reference not in weights or
            weights[reference] != {reference: 1.} or ground_af[reference] != 0):
        raise ValueError('Port-transform inventories or reference disagree.')
    physical = {n for group in weights.values() for n in group}
    if (sum(map(len, weights.values())) != len(physical) or '0' in physical or
            len({n.casefold() for n in physical}) != len(physical) or
            any(not re.fullmatch(r'[A-Za-z0-9_:#.\[\]-]+', n) or n.casefold().startswith(PREFIX.casefold()) for n in physical)):
        raise ValueError('Ambiguous, overlapping or unsafe physical nodes.')
    lines = []; ports = {}; source_count = 0
    for index, (name, group) in enumerate(sorted(weights.items())):
        if (not group or any(not math.isfinite(v) or v <= 0 for v in group.values()) or
                not math.isclose(math.fsum(group.values()), 1, abs_tol=1e-12, rel_tol=0)):
            raise ValueError('Positive normalized port weights are required.')
        if len(group) == 1:
            ports[name] = next(iter(group))
            continue
        anchor = max(group, key=group.get)
        order = [anchor] + sorted(set(group)-{anchor})
        port = PREFIX+str(index); previous = '0'
        # Linear series VCVSs retain a native branch-current identity. ngspice
        # rewrites POLY sources into XSPICE devices, which CCCSs cannot name.
        for j, node in enumerate(order):
            output = port if j == len(order)-1 else port+'_STEP_'+str(j)
            negative = '0' if j == 0 else anchor
            gain = 1. if j == 0 else group[node]
            element = f'EIHP_PORT_{index}_{j}'
            lines.append(f'{element} {output} {previous} {node} {negative} {gain:.17g}')
            previous = output
        # I(E) is the negative of the capacitor current. A source directed
        # from ground into an endpoint therefore returns +w*I(C) at that port.
        actual = dict(group); actual[anchor] = 1.-math.fsum(group[n] for n in order[1:])
        for j, node in enumerate(order):
            lines.append(f'FIHP_RETURN_{index}_{j} 0 {node} {element} {actual[node]:.17g}')
        ports[name] = port; source_count += 2*len(order)
    if source_count > 50000:
        raise ValueError('Port-transform source budget exceeded.')
    capacitors = []
    def cap(a, b, value):
        if not math.isfinite(value) or value < 0 or a == b:
            raise ValueError('Invalid port-transform capacitor.')
        if value:
            capacitors.append((a, b, value))
            if len(capacitors) > 500000:
                raise ValueError('Port-transform capacitor budget exceeded.')
    diagonal = {n: float(v) for n, v in ground_af.items()}
    for name, value in ground_af.items():
        if name != reference:
            cap(ports[name], reference, value)
    for (a, b), value in coupling_af.items():
        if a not in ports or b not in ports:
            raise ValueError('Unknown coupling port.')
        cap(ports[a], ports[b], value)
        diagonal[a] += value; diagonal[b] += value
    for name, group in weights.items():
        if len(group) == 1:
            continue
        total = original_diagonal_af[name]
        if not math.isfinite(total) or total < diagonal[name]-max(1e-7, total*1e-12):
            raise ValueError('Original diagonal cannot be smaller than its Schur reduction.')
        # W^T C W supplies the reduced mean-port diagonal. The original
        # distributed model additionally needs C_original*(diag(w)-w*w^T).
        items = list(group.items())
        for i, (a, wa) in enumerate(items):
            for b, wb in items[i+1:]:
                cap(a, b, total*wa*wb)
    lines.extend(f'CIHP_PORT_{i} {a} {b} {c*1e-18:.17g}' for i, (a, b, c) in enumerate(capacitors))
    return dict(text='\n'.join(lines)+'\n', capacitors=len(capacitors), sources=source_count,
                virtual_ports=sum(len(g)>1 for g in weights.values()), qualified=False)


def contract(text, physical_nodes):
    """Parse serialized E/F equations independently; return capacitor stamps.

    Each stamp has independent current-return and voltage-control vectors, so
    a reversed, missing or misweighted return produces a different matrix.
    No helper may impose a voltage on a physical node or add DC leakage.
    """
    physical = set(physical_nodes)
    voltages = {n: {n: 1.} for n in physical}; returns = {n: {n: 1.} for n in physical}
    elements = {}; names = set(); caps = []; predecessors = set()
    for line in text.splitlines():
        t = line.split()
        if not t or t[0].casefold() in names:
            raise ValueError('Empty or repeated transformer element.')
        names.add(t[0].casefold())
        if t[0].startswith('EIHP_PORT_'):
            if (len(t) != 6 or not t[1].startswith(PREFIX) or t[1] in voltages or
                    (t[2] != '0' and (t[2] not in voltages or t[2] in physical or t[2] in predecessors))):
                raise ValueError('Invalid transformer voltage port.')
            a,b = t[3:5]; coefficient = float(t[5])
            if a not in physical or (b != '0' and b not in physical) or not math.isfinite(coefficient) or coefficient <= 0:
                raise ValueError('Unknown or nonfinite transformer control.')
            vector = dict(voltages[t[2]]) if t[2] != '0' else {}
            if t[2] != '0':predecessors.add(t[2])
            vector[a] = vector.get(a, 0.)+coefficient
            if b != '0':vector[b] = vector.get(b, 0.)-coefficient
            if any(v <= 0 for v in vector.values()) or not math.isclose(math.fsum(vector.values()),1.,abs_tol=1e-12,rel_tol=0):
                raise ValueError('Transformer is not a normalized positive mean.')
            voltages[t[1]] = vector; returns[t[1]] = {}; elements[t[0]] = t[1]
        elif t[0].startswith('FIHP_RETURN_'):
            if len(t) != 5 or t[1] != '0' or t[2] not in physical or t[3] not in elements:
                raise ValueError('Invalid transformer current return.')
            value = float(t[4]); output = returns[elements[t[3]]]
            if not math.isfinite(value) or value <= 0 or t[2] in output:
                raise ValueError('Repeated or invalid current-return weight.')
            output[t[2]] = value
        elif t[0].startswith('CIHP_PORT_'):
            if len(t) != 4 or t[1] not in voltages or t[2] not in voltages or t[1] == t[2]:
                raise ValueError('Invalid transformed capacitor terminals.')
            value = float(t[3])*1e18
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Invalid transformed capacitance.')
            caps.append((t[1],t[2],value))
        else:
            raise ValueError('Unsupported transformer-model element.')
    terminals = set(elements.values())-predecessors
    if any(returns[n] for n in predecessors) or any(a in predecessors or b in predecessors for a,b,c in caps):
        raise ValueError('Intermediate series ports must remain unloaded.')
    for node in terminals:
        if (returns[node].keys() != voltages[node].keys() or
                any(not math.isclose(returns[node][n],v,rel_tol=1e-12,abs_tol=1e-15) for n,v in voltages[node].items())):
            raise ValueError('Transformer voltage and current weights are not reciprocal.')
    def difference(a,b):
        return {n:a.get(n,0.)-b.get(n,0.) for n in a.keys()|b.keys()}
    return [(difference(returns[a],returns[b]), difference(voltages[a],voltages[b]), c) for a,b,c in caps]


def apply(stamps, voltage):
    """Return dQ/dt for independently chosen physical dV/dt values (aF units)."""
    current = {}
    for output, control, c in stamps:
        value = c*math.fsum(weight*voltage[node] for node,weight in control.items())
        for node, weight in output.items():current[node] = current.get(node,0.)+weight*value
    return current
