"""Transfer audited native capacitance onto an explicit resistance endpoint map.

This bypasses width-clamped capacitance tables; it does not validate geometry,
endpoint placement, resistance values, cell pin capacitance or a field model.
Callers must establish those independently. No endpoint map is inferred from
the rejected OpenRCX capacitance values. The native substrate is ideal.
"""
from collections import defaultdict
import hashlib
import math
from pathlib import Path

from icstudio.digital_fill_spef import parse
from scripts.check_ihp_flat_capacitance import raw_capacitors
from scripts.ihp_fill_spef import export


def transfer(extraction, source, target, weights):
    """Preserve every native C and original SPEF R/terminal, then audit readback.

    Each native conductor needs positive normalized weights covering every
    endpoint of exactly one SPEF net. Native and SPEF net sets must be bijective;
    unknown internal-cell or substrate nodes cannot be silently discarded.
    Keep floating fill explicit here, including its resistor endpoints.
    """
    extraction, source, target = map(Path, (extraction, source, target))
    if target.exists():
        raise ValueError('Use a new native capacitance SPEF output.')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    graph = raw_capacitors(extraction)
    data = parse(source)
    ground = graph['ground']
    if set(weights) != set(graph['nodes']) - {ground}:
        raise ValueError('Native capacitance nodes and endpoint maps differ.')
    endpoints = set()
    net_map = {}
    for name, group in weights.items():
        if (not isinstance(group, dict) or not group or
                any(not isinstance(v, (int, float)) or isinstance(v, bool) or
                    not math.isfinite(v) or v <= 0 for v in group.values()) or
                not math.isclose(math.fsum(group.values()), 1., rel_tol=0., abs_tol=1e-13)):
            raise ValueError('Endpoint weights must be positive and normalized.')
        if not group.keys() <= data['owners'].keys() or endpoints & group.keys():
            raise ValueError('Unknown or multiply mapped resistance endpoint.')
        nets = {data['owners'][n] for n in group}
        if len(nets) != 1 or next(iter(nets)) in net_map.values():
            raise ValueError('Native conductors must map bijectively to SPEF nets.')
        net_map[name] = next(iter(nets))
        endpoints.update(group)
    if endpoints != data['owners'].keys() or set(net_map.values()) != data['nets'].keys():
        raise ValueError('Every SPEF net and endpoint must be mapped.')
    if len(endpoints) > 100000:
        raise ValueError('Native capacitance handoff exceeds the endpoint budget.')
    required = 0
    for a, b, _ in graph['edges_af']:
        required += len(weights[b] if a == ground else weights[a]) if ground in (a, b) else len(weights[a])*len(weights[b])
        if required > 2000000:
            raise ValueError('Native capacitance handoff exceeds two million contributions.')
    shunts = {n: [] for n in endpoints}
    mutual = defaultdict(list)
    wanted_ground = {n: [] for n in net_map.values()}
    wanted_mutual = defaultdict(list)
    for a, b, value in graph['edges_af']:
        if ground in (a, b):
            name = b if a == ground else a
            wanted_ground[net_map[name]].append(value)
            for n, w in weights[name].items():
                shunts[n].append(value*w*1e-18)
        else:
            wanted_mutual[tuple(sorted((net_map[a], net_map[b])))].append(value)
            for x, wx in weights[a].items():
                for y, wy in weights[b].items():
                    mutual[tuple(sorted((x, y)))].append(value*wx*wy*1e-18)
    result = dict(floating_nodes=[], ground_f={n: math.fsum(v) for n, v in shunts.items()},
                  coupling_f=[dict(a=a, b=b, value_f=math.fsum(v)) for (a, b), v in sorted(mutual.items())])
    export(source, target, data, result)
    reread = parse(target)
    actual_ground = {name: math.fsum(map(float, item['ground'].values()))*1e6
                     for name, item in reread['nets'].items()}
    actual_mutual = defaultdict(list)
    for (a, b), value in reread['couplings'].items():
        actual_mutual[tuple(sorted((reread['owners'][a], reread['owners'][b])))].append(float(value)*1e6)
    wanted = {('ground', n): math.fsum(v) for n, v in wanted_ground.items()}
    wanted.update({('mutual', *p): math.fsum(v) for p, v in wanted_mutual.items()})
    actual = {('ground', n): v for n, v in actual_ground.items()}
    actual.update({('mutual', *p): math.fsum(v) for p, v in actual_mutual.items()})
    if wanted.keys() != actual.keys() or any(not math.isclose(actual[k], v, rel_tol=1e-12, abs_tol=1e-9)
                                            for k, v in wanted.items()):
        raise ValueError('SPEF readback lost native capacitance.')
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise ValueError('Original resistance source changed during export.')
    return dict(schema=1, status='native-capacitance-handoff-passed', qualified=False,
                source_spef_sha256=digest, native_ext_sha256=graph['source_sha256'],
                output_spef_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                nets=len(net_map), endpoints=len(endpoints), native_capacitors=len(graph['edges_af']),
                maximum_contracted_capacitance_error_af=max((abs(actual[k]-v) for k, v in wanted.items()), default=0.),
                negative_roundoff_count=graph['negative_roundoff_count'],
                negative_roundoff_total_af=graph['negative_roundoff_total_af'],
                scope='Native capacitance conservation and unchanged SPEF R/terminals only. Geometry, spatial distribution, cell-capacitance accounting, timing and field accuracy require separate checks.')
