"""Audit native coupling diagnostics without qualifying their spatial accuracy.

Magic's coupling output uses %lg (six significant digits). Coupling to the
substrate is moved into node ground C before output. Keep that contribution
separate from negative shielding corrections. These checks establish accounting;
they do not establish where a capacitance belongs on a resistance graph.
"""
from collections import Counter, defaultdict
import hashlib
import math
from pathlib import Path
import re
import shlex

from scripts.check_ihp_flat_capacitance import raw_capacitors

KINDS = {'overlap', 'side-halo', 'side-legacy', 'corner', 'sidewall',
         'ground-overlap', 'ground-side-halo', 'ground-side-legacy',
         'ground-corner', 'ground-blocked-fringe'}
RESIDUE_AF = 1e-10
TOTAL_RESIDUE_AF = 1e-7


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _signal(name):
    return bool(re.fullmatch(r'NET\d{6}', name)) and name not in ('NET000000', 'NET000001')


def _native(path):
    graph = raw_capacitors(path)
    mutual = {}; ground = {}
    for line in Path(path).read_text().splitlines():
        if not line.startswith(('node ', 'substrate ', 'cap ')):
            continue
        row = shlex.split(line)
        if row[0] == 'cap':
            pair = tuple(sorted(row[1:3]))
            if pair in mutual:
                raise ValueError('Duplicate native capacitor pair.')
            mutual[pair] = float(row[3])
        else:
            ground[row[1]] = float(row[3])
    return graph, mutual, ground


def audit_trace(trace, extraction):
    """Require all traced signal couplings to reproduce native serialization.

    Every row has two valid rectangles, native node names and finite aF values.
    Rectangle validation checks syntax only, not conductor ownership or shielding.
    Signed corner corrections and tiny native cancellation residues are retained.
    """
    trace, extraction = map(Path, (trace, extraction))
    trace_digest = _sha(trace)
    graph, expected, ground_c = _native(extraction)
    nodes = set(graph['nodes']); substrate = graph['ground']
    contributions = defaultdict(list); shielding = defaultdict(list)
    kinds = Counter(); rows = 0; shielding_residues = []
    with trace.open(encoding='ascii') as stream:
        for line in stream:
            fields = line.rstrip('\n').split('\t')
            if len(fields) != 15 or fields[0] != 'ICSTUDIO_SPATIAL':
                raise ValueError('Incomplete or interleaved spatial trace row.')
            _, kind, a, b, value, *integers = fields
            try:
                value = float(value); integers = list(map(int, integers))
            except ValueError as error:
                raise ValueError('Invalid spatial trace number.') from error
            if (kind not in KINDS or not math.isfinite(value) or value == 0 or
                    not (_signal(a) or _signal(b)) or a not in nodes or
                    any(abs(v) > 2_147_483_647 for v in integers) or
                    any(v < 0 for v in integers[:2])):
                raise ValueError('Unsupported spatial trace contribution.')
            rects = integers[2:]
            if any(rects[i] > rects[i+2] or rects[i+1] > rects[i+3] for i in (0, 4)):
                raise ValueError('Inverted spatial trace rectangle.')
            if kind.startswith('ground-'):
                if b != '@substrate' or value >= RESIDUE_AF:
                    raise ValueError('Invalid substrate shielding contribution.')
                if value > 0:
                    shielding_residues.append(value)
                shielding[a].append(value)
            else:
                if b not in nodes or a == b:
                    raise ValueError('Unknown or shorted coupling endpoint.')
                contributions[tuple(sorted((a, b)))].append(value)
            kinds[kind] += 1; rows += 1
            if rows > 10_000_000:
                raise ValueError('Spatial trace exceeds the diagnostic row budget.')
    if not rows:
        raise ValueError('Empty spatial trace.')
    if math.fsum(shielding_residues) > TOTAL_RESIDUE_AF:
        raise ValueError('Spatial shielding residues exceed the bound.')
    actual = {p: math.fsum(v) for p, v in contributions.items() if substrate not in p}
    relocated = {next(n for n in p if n != substrate): math.fsum(v)
                 for p, v in contributions.items() if substrate in p}
    expected = {p: v for p, v in expected.items() if any(map(_signal, p))}
    maximum = 0.; residues = []
    for pair in expected.keys() | actual.keys():
        wanted, seen = expected.get(pair, 0.), actual.get(pair, 0.)
        maximum = max(maximum, abs(wanted-seen))
        if float(format(seen, '.6g')) != wanted:
            if max(abs(wanted), abs(seen)) >= RESIDUE_AF:
                raise ValueError('Spatial trace does not conserve native mutual C: '+str(pair))
            residues.append(abs(wanted-seen))
    if math.fsum(residues) > TOTAL_RESIDUE_AF:
        raise ValueError('Spatial trace cancellation residues exceed the bound.')
    if _sha(trace) != trace_digest or _sha(extraction) != graph['source_sha256']:
        raise ValueError('Spatial audit input changed while reading.')
    return dict(schema=1, status='trace-mutual-conserved', qualified=False,
                trace_sha256=trace_digest, native_ext_sha256=graph['source_sha256'],
                rows=rows, kinds=dict(kinds), signal_mutual_pairs=len(expected),
                trace_mutual_pairs=len(actual), maximum_serialization_error_af=maximum,
                cancellation_residue_count=len(residues), cancellation_residue_total_af=math.fsum(residues),
                positive_shielding_residue_count=len(shielding_residues),
                positive_shielding_residue_total_af=math.fsum(shielding_residues),
                relocated_to_substrate_af=relocated,
                ground_shielding_af={n: math.fsum(v) for n, v in shielding.items()},
                signal_ground_af={n: c for n, c in ground_c.items() if _signal(n)},
                substrate=substrate, native_output_format='%lg (six significant digits)',
                scope='Signal coupling accounting only. Ground initial terms, conductor ownership, spatial endpoint assignment, field accuracy and timing require separate evidence.')


def audit_ground_delta(before, after):
    """Check shielding/relocation changes assuming unchanged signal geometry.

    The caller must independently verify unchanged original conductor geometry
    and device masks. This audit does not prove that prerequisite. Half a native
    printed unit is allowed for each ground value, plus floating-point roundoff.
    """
    if (before['status'] != 'trace-mutual-conserved' or after['status'] != before['status'] or
            before['substrate'] != after['substrate'] or
            before['signal_ground_af'].keys() != after['signal_ground_af'].keys()):
        raise ValueError('Incompatible ground-delta trace audits.')
    rows = []
    def uncertainty(value):
        return 0. if value == 0 else .5 * 10. ** (math.floor(math.log10(abs(value))) - 5)
    for node, left in before['signal_ground_af'].items():
        right = after['signal_ground_af'][node]
        traced = [math.fsum((r['ground_shielding_af'].get(node, 0.),
                           r['relocated_to_substrate_af'].get(node, 0.))) for r in (before, after)]
        expected = right-left; actual = traced[1]-traced[0]
        allowance = uncertainty(left)+uncertainty(right)+max(abs(left), abs(right), *map(abs, traced), 1.)*1e-12
        if abs(expected-actual) > allowance:
            raise ValueError('Spatial trace does not account for the ground-C change: '+node)
        rows.append(dict(node=node, native_delta_af=expected, trace_delta_af=actual,
                         serialization_allowance_af=allowance))
    return dict(schema=1, status='trace-ground-delta-accounted', qualified=False,
                before_trace_sha256=before['trace_sha256'], after_trace_sha256=after['trace_sha256'],
                signal_nodes=len(rows), nodes=rows,
                scope='Ground-C delta accounting conditioned on independently verified unchanged signal geometry. This does not qualify spatial positions, field extraction or timing.')
