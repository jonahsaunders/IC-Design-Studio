"""Reduce independent floating components without enlarging the dense solver.

The global physical endpoint inventory may exceed 4,096. Each floating component
is eliminated against only its incident retained endpoints; its dense solve keeps
the existing 4,096-port bound. Direct physical capacitors never enter that solve.
This is an algebraic reduction, not an extraction or timing qualification.
"""
from collections import defaultdict
import math

from scripts.ihp_native_capacitance import reduce_capacitors


def reduce_components(graph, ground, *, additional_floating_nodes=(),
                      relative_charge_error=0, max_component_ports=4096,
                      max_output_pairs=2_000_000):
    """Return a passive Schur network with explicit allocation/output bounds."""
    if (type(max_component_ports) is not int or not 1 <= max_component_ports <= 4096 or
            type(max_output_pairs) is not int or not 1 <= max_output_pairs <= 2_000_000):
        raise ValueError('Invalid component reduction budget.')
    if not math.isfinite(relative_charge_error) or not 0 <= relative_charge_error <= 1e-4:
        raise ValueError('Invalid component reduction charge budget.')
    nodes = set(graph['nodes']); extra = set(additional_floating_nodes)
    if (not nodes or len(nodes) != len(graph['nodes']) or len(nodes) > 200000 or
            ground not in nodes or ground.startswith('FILL')):
        raise ValueError('Invalid or oversized component node inventory.')
    if not extra <= nodes or ground in extra or any(n.startswith('FILL001_') for n in extra):
        raise ValueError('Invalid additional floating conductor inventory.')
    metal = {n for n in nodes if n.startswith('FILL') and not n.startswith('FILL001_')}
    floating = metal | extra
    if len(floating) > 100000 or len(graph['edges_af']) > 2_000_000:
        raise ValueError('Component source exceeds its allocation budget.')
    retained = nodes-floating-{ground}
    parent = {n: n for n in floating}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]; n = parent[n]
        return n

    for a, b, value in graph['edges_af']:
        if (a not in nodes or b not in nodes or a == b or
                not math.isfinite(value) or value <= 0):
            raise ValueError('Invalid component capacitor.')
        if a in floating and b in floating:
            parent[find(a)] = find(b)
    groups = defaultdict(set)
    for n in sorted(floating):
        groups[find(n)].add(n)
    edges = defaultdict(list); ports = defaultdict(set)
    shunts = {n: [] for n in retained}; mutual = defaultdict(list)

    def add(a, b, value):
        if not value:
            return
        if not math.isfinite(value) or value < 0 or a == b:
            raise ValueError('Component solve produced a nonpassive capacitor.')
        if ground in (a, b):
            shunts[b if a == ground else a].append(value)
        else:
            pair = tuple(sorted((a, b)))
            if pair not in mutual and len(mutual) >= max_output_pairs:
                raise ValueError('Component reduction exceeds the output pair budget.')
            mutual[pair].append(value)

    for a, b, value in graph['edges_af']:
        if a in floating or b in floating:
            key = find(a if a in floating else b)
            edges[key].append((a, b, value))
            ports[key].update(n for n in (a, b) if n in retained)
        else:
            add(a, b, value)
    # Check every component before starting any factorization.
    if any(len(p) > max_component_ports for p in ports.values()):
        raise ValueError('A floating component exceeds the existing dense port budget.')
    reports = []; observable = 0
    for key, names in sorted(groups.items(), key=lambda item: min(item[1])):
        boundary = ports[key]
        if not boundary:
            reports.append(dict(floating_nodes=len(names), ports=0, observable=False, residual=0.))
            continue
        local = dict(nodes=sorted(names | boundary | {ground}), edges_af=edges[key],
                     source_sha256=graph['source_sha256'])
        result = reduce_capacitors(local, ground, relative_charge_error=0,
                                   additional_floating_nodes=names & extra)
        for n, value in result['ground_af'].items():
            add(n, ground, value)
        for a, b, value in result['couplings_af']:
            add(a, b, value)
        observable += result['observable_floating_nodes']
        reports.append(dict(floating_nodes=len(names), ports=len(boundary), observable=True,
                            residual=result['residual']))
    shunts = {n: math.fsum(v) for n, v in shunts.items()}
    pairs = {p: math.fsum(v) for p, v in mutual.items()}
    diagonal = {n: [v] for n, v in shunts.items()}
    for (a, b), value in pairs.items():
        diagonal[a].append(value); diagonal[b].append(value)
    budget = {n: relative_charge_error*math.fsum(v) for n, v in diagonal.items()}
    spent = dict.fromkeys(retained, 0.); kept = []
    for (a, b), value in sorted(pairs.items(), key=lambda row: (row[1], row[0])):
        if spent[a]+value <= budget[a] and spent[b]+value <= budget[b]:
            spent[a] += value; spent[b] += value
        else:
            kept.append((a, b, value))
    return dict(ground=ground, ground_af={n: math.fsum((shunts[n], spent[n])) for n in sorted(retained)},
                couplings_af=kept, floating_metal_nodes=len(metal), additional_floating_nodes=sorted(extra-metal),
                observable_floating_nodes=observable, active_junction_nodes=sum(n.startswith('FILL001_') for n in retained),
                retained_nodes=len(retained), components=reports, largest_component_ports=max(map(len, ports.values()), default=0),
                residual=max((r['residual'] for r in reports), default=0.), relative_charge_error=relative_charge_error,
                max_component_ports=max_component_ports, max_output_pairs=max_output_pairs,
                source_sha256=graph['source_sha256'])
