"""Conserve the original flat Magic capacitance matrix on an extracted R graph.

Magic's extresist capacitance is a redistribution weight, not authoritative C:
the supported engine reads .ext coupling in aF into an fF accumulator, ignores
intrinsic node C, and kills some original coupling when splitting internal nets.
We use original .ext C values and retain the engine's R and device rewiring.
Positive rnode C values supply normalized area weights. A net with zero weights
uses the rnode nearest its original physical origin. Mutual C uses the product
of endpoint weights. This is an area weighted lumped approximation, not a field
solver or a determination of the physical locations of mutual capacitance.

Physical hierarchy is flattened by the orchestration layer before extraction.
Explicit aliases are canonicalized without merging independent node records.
Only complete extraction with unambiguous connected R groups is accepted. Raw files and an explicit conservation/provenance report survive.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import shlex
from collections import Counter

from .model import atomic_write, file_digest, scalar


MAX_CAPACITORS = 100_000
ALGORITHM = 'magic-flat-capacitance-conservation-v1'
_ORIGINAL_KEYS = {'timestamp', 'version', 'tech', 'style', 'scale', 'resistclasses',
                  'parameters', 'port', 'node', 'substrate', 'cap', 'device', 'fet', 'attr', 'equiv'}
_RESISTANCE_KEYS = {'scale', 'killnode', 'rnode', 'resist', 'device', 'fet'}


def _number(value, label, *, positive=False):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid Magic RC ' + label + '.') from exc
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError('Invalid Magic RC ' + label + ': require finite ' +
                         ('positive' if positive else 'nonnegative') + ' value.')
    return result


def _coordinate(value):
    try:
        result = int(value)
    except ValueError as exc:
        raise ValueError('Magic RC coordinates must be integers.') from exc
    if abs(result) > 2_147_483_647:
        raise ValueError('Magic RC coordinate is outside the supported range.')
    return result


def _records(content, allowed):
    records = []
    for line in content.splitlines():
        try:
            tokens = shlex.split(line, comments=False, posix=True)
        except ValueError as exc:
            raise ValueError('Malformed Magic extraction record.') from exc
        if not tokens:
            records.append((line, []))
            continue
        if tokens[0] not in allowed:
            raise ValueError('Unsupported Magic RC record: ' + tokens[0] +
                             '. Flatten physical hierarchy before extraction.')
        records.append((line, tokens))
    return records


def _scale(records):
    scales = [tokens for _, tokens in records if tokens and tokens[0] == 'scale']
    if len(scales) != 1 or len(scales[0]) != 4:
        raise ValueError('Magic RC requires one explicit complete scale record.')
    values = [_number(v, 'scale', positive=True) for v in scales[0][1:]]
    if any(v != int(v) or v > 2_147_483_647 for v in values[:2]):
        raise ValueError('Magic resistance and capacitance scale factors must be integers.')
    return values


def _name(value):
    if not value or any(c.isspace() for c in value) or any(c in value for c in ('\\', '\x00')):
        raise ValueError('Unsupported or malformed Magic RC node name.')
    return value


def _line(tokens):
    # efReadLine accepts double-quoted fields. Preserve spaces/quotes in attrs.
    return ' '.join(json.dumps(v) if (i == 1 or not re.fullmatch(r'[^\s"\\]+', v))
                    else v for i, v in enumerate(tokens))


def _device(tokens):
    """Decode supported Magic devices without confusing them with parasitics."""
    if tokens[0] != 'device':
        return None
    supported = ('msubckt', 'csubckt', 'rsubckt', 'mosfet', 'devres', 'devcap', 'devcaprev')
    if len(tokens) < 8 or tokens[1] not in supported:
        raise ValueError('Unsupported Magic RC device class.')
    kind, start = tokens[1], 7
    primitive = kind in ('devres', 'devcap', 'devcaprev')
    numeric_value = None
    if primitive:
        count = 1 if tokens[2] == 'None' else 2
        if len(tokens) < start + count:
            raise ValueError('Incomplete Magic primitive device value or dimensions.')
        for token in tokens[start:start + count]:
            _number(token, 'primitive device value or dimension', positive=True)
        if count == 1:
            numeric_value = float(tokens[start]) * (1e-15 if kind != 'devres' else 1.)
        start += count
    elif kind == 'mosfet' and '=' not in tokens[start]:
        for token in tokens[start:start + 2]:
            _number(token, 'MOS dimension', positive=True)
        start += 2
    header_end = start
    while start < len(tokens) and '=' in tokens[start]:
        start += 1
    remainder = (len(tokens) - start) % 3
    substrate = start if remainder == 1 else None
    if remainder not in (0, 1):
        raise ValueError('Malformed Magic RC device terminals.')
    indices = list(range(start + (substrate is not None), len(tokens), 3))
    if len(indices) != (2 if kind in ('csubckt', 'devcap', 'devcaprev') else 3):
        raise ValueError('Unsupported Magic RC device terminal count.')
    # Magic honors explicit drain/source terminal attributes.
    if len(indices) == 3 and (tokens[indices[1] + 2] == 'D' or tokens[indices[2] + 2] == 'S'):
        indices[1], indices[2] = indices[2], indices[1]
    if kind in ('msubckt', 'mosfet'):
        electrical = [indices[2], indices[0], indices[1]]
    elif kind in ('rsubckt', 'devres'):
        electrical = indices[1:]
    else:
        electrical = indices
    if not primitive and substrate is not None and tokens[substrate] != 'None':
        electrical.append(substrate)
    prefix = {'mosfet': 'm', 'devres': 'r', 'devcap': 'c', 'devcaprev': 'c'}.get(kind, 'x')
    return {'identity': tuple(tokens[1:7]), 'all_indices': ([substrate] if substrate is not None else []) + indices,
            'electrical': [tokens[i] for i in electrical], 'gate_attribute': indices[0] + 2,
            'model': tokens[2].casefold(), 'prefix': prefix, 'primitive': primitive,
            'numeric_value': numeric_value, 'header_end': header_end}


def _prepare_devices(original, resistance):
    """Give primitive devices stable export identities and restore known headers.

    Magic's ResPrint writes rewired devres/devcap records without their required
    value/L/W fields. Restore those fields only when the exact known omitted-
    header shape matches, using the original device at the same class/model/box.
    EFBuild retains original geometry and parameters and takes rewired terminals.
    """
    devices = {}
    for _, t in original:
        if t and t[0] == 'device':
            info = _device(t)
            if info['identity'] in devices:
                raise ValueError('Duplicate Magic device geometry identity.')
            devices[info['identity']] = (t, info)
    report = []
    tagged = {}
    for identity, (t, info) in devices.items():
        if info['primitive']:
            tag = 'STUDIO_DEVICE_' + hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:20]
            tagged[identity] = tag
            report.append({'identity': list(identity), 'name': info['prefix'].upper() + tag,
                           'original_gate_attribute': t[info['gate_attribute']],
                           'restored_resistance_header': False})
    def rewrite(records, rewired=False):
        result = []
        for line, t in records:
            if not t or t[0] != 'device' or tuple(t[1:7]) not in tagged:
                result.append((line, t)); continue
            identity = tuple(t[1:7]); original_t, original_info = devices[identity]
            updated = list(t)
            expected_terminals = 3 if t[1] == 'devres' else 2
            if rewired and len(t) == 8 + 3 * expected_terminals:
                updated = t[:7] + original_t[7:original_info['header_end']] + t[7:]
                next(row for row in report if tuple(row['identity']) == identity)['restored_resistance_header'] = True
            info = _device(updated)
            updated[info['gate_attribute']] = tagged[identity]
            result.append((_line(updated), updated))
        return result
    return rewrite(original), rewrite(resistance, True), report


def _aliases(original, resistance):
    """Resolve explicit label equivalences without guessing geometric shorts.

    A class must contain exactly one original node record. Multiple records can
    encode hierarchical capacitance corrections, which require a fresh physical
    flatten/extract and must never be naively summed. A port wins the canonical
    name so the public subcircuit interface is preserved.
    """
    parent, declared, ports = {}, set(), set()
    def find(name):
        _name(name)
        parent.setdefault(name, name)
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name
    for _, t in original:
        if not t:
            continue
        if t[0] in ('node', 'substrate'):
            declared.add(t[1]); find(t[1])
        elif t[0] == 'port':
            ports.add(t[1]); find(t[1])
        elif t[0] == 'equiv':
            if len(t) != 3:
                raise ValueError('Malformed Magic node equivalence.')
            parent[find(t[1])] = find(t[2])
    classes = {}
    for name in parent:
        classes.setdefault(find(name), set()).add(name)
    mapping = {}
    for names in classes.values():
        roots, interface = names & declared, names & ports
        if len(roots) != 1:
            raise ValueError('Magic alias class requires exactly one original node record; flatten before extraction.')
        if len(interface) > 1:
            raise ValueError('Magic aliases short distinct interface ports.')
        canonical = next(iter(interface or roots))
        mapping.update({name: canonical for name in names})
    aliases = {a: b for a, b in mapping.items() if a != b}
    if not aliases:
        return original, resistance, aliases
    def mapped(name):
        if name in mapping:
            return mapping[name]
        candidates = [(a, b) for a, b in aliases.items()
                      if re.fullmatch(re.escape(a.rstrip('#!')) + r'\.[nt][0-9]+', name)]
        if candidates:
            longest = max(len(a.rstrip('#!')) for a, _ in candidates)
            choices = {b.rstrip('#!') + name[len(a.rstrip('#!')):]
                       for a, b in candidates if len(a.rstrip('#!')) == longest}
            if len(choices) != 1:
                raise ValueError('Ambiguous aliased Magic resistance node.')
            return choices.pop()
        return name
    def rewrite(records):
        result = []
        for line, t in records:
            if not t:
                result.append((line, t)); continue
            if t[0] == 'equiv':
                continue
            indices = []
            if t[0] in ('node', 'substrate', 'rnode', 'killnode', 'port', 'attr'):
                indices = [1]
            elif t[0] in ('cap', 'resist'):
                indices = [1, 2]
            elif t[0] == 'device':
                indices = _device(t)['all_indices']
            elif t[0] == 'fet':
                raise ValueError('Alias normalization requires modern Magic device records.')
            updated = list(t)
            for i in indices:
                if i >= len(t):
                    raise ValueError('Incomplete aliased Magic extraction record.')
                updated[i] = mapped(t[i])
            result.append((_line(updated) if updated != t else line, updated))
        return result
    return rewrite(original), rewrite(resistance), aliases


def _matrix(ground, coupling):
    terms = {}
    for net, value in ground.items():
        terms.setdefault((net, net), []).append(value)
    for (a, b), value in coupling.items():
        if a == b:
            raise ValueError('Self-coupling is unsupported in the Magic capacitance matrix.')
        terms.setdefault((a, a), []).append(value)
        terms.setdefault((b, b), []).append(value)
        terms.setdefault(tuple(sorted((a, b))), []).append(-value)
    return {key: math.fsum(values) for key, values in terms.items()}


def normalize(directory, top, *, max_capacitors=50_000, require_device_reference=False):
    """Rewrite flat ``top.ext``/``top.res.ext`` and return provenance evidence.

    Call after ``extresist all`` and before ``ext2spice extresist on`` export.
    Existing raw copies or report are rejected, so normalization cannot silently
    consume a previous normalized output as original evidence. All validation,
    bounded expansion and matrix checks finish before any source file changes.
    """
    if not isinstance(top, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', top):
        raise ValueError('Magic RC top must be a plain cell name.')
    if type(max_capacitors) is not int or not 0 < max_capacitors <= MAX_CAPACITORS:
        raise ValueError('Magic RC capacitance expansion budget must be 1–100000.')
    directory = Path(directory).resolve()
    original_path = directory / (top + '.ext')
    resistance_path = directory / (top + '.res.ext')
    raw_original = directory / (top + '.raw.ext')
    raw_resistance = directory / (top + '.raw.res.ext')
    report_path = directory / 'rc-normalization.json'
    device_reference = directory / 'device-reference.spice'
    if require_device_reference and not device_reference.is_file():
        raise ValueError('Missing pre-resistance physical device reference export.')
    if any(p.exists() for p in (raw_original, raw_resistance, report_path)):
        raise ValueError('Magic RC normalization requires untouched extraction inputs.')
    original_bytes = original_path.read_bytes()
    resistance_bytes = resistance_path.read_bytes()
    original = _records(original_bytes.decode('utf-8'), _ORIGINAL_KEYS)
    resistance = _records(resistance_bytes.decode('utf-8'), _RESISTANCE_KEYS)
    original, resistance, primitive_devices = _prepare_devices(original, resistance)
    original, resistance, aliases = _aliases(original, resistance)
    scale = _scale(original)
    rscale = _scale(resistance)
    if scale[2] != rscale[2]:
        raise ValueError('Magic original and R extraction coordinate scales disagree.')

    nodes, rnodes, coupling_terms, killed, ports = {}, {}, {}, set(), set()
    substrate = []
    for _, tokens in original:
        if not tokens:
            continue
        kind = tokens[0]
        if kind in ('node', 'substrate'):
            if len(tokens) < 7:
                raise ValueError('Incomplete Magic original node record.')
            name = _name(tokens[1])
            if name in nodes:
                raise ValueError('Duplicate or aliased Magic original node: ' + name)
            nodes[name] = {'cap_af': _number(tokens[3], 'node capacitance') * scale[1],
                           'xy': [_coordinate(v) for v in tokens[4:6]]}
            if kind == 'substrate':
                substrate.append(name)
        elif kind == 'cap':
            if len(tokens) != 4:
                raise ValueError('Incomplete Magic coupling record.')
            a, b = (_name(v) for v in tokens[1:3])
            coupling_terms.setdefault(tuple(sorted((a, b))), []).append(
                _number(tokens[3], 'mutual capacitance') * scale[1])
        elif kind == 'port':
            if len(tokens) != 8:
                raise ValueError('Incomplete Magic port record.')
            ports.add(_name(tokens[1]))
        elif kind == 'device':
            _device(tokens)
    if not nodes or len(substrate) != 1 or nodes[substrate[0]]['cap_af'] != 0:
        raise ValueError('Magic RC requires one explicit zero-capacitance substrate reference.')
    if len({n.casefold() for n in nodes}) != len(nodes):
        raise ValueError('Magic original node names collide in case-insensitive SPICE.')
    if not ports <= nodes.keys():
        raise ValueError('Magic RC port has no original node record.')
    coupling = {key: math.fsum(values) for key, values in coupling_terms.items()}
    if any(a not in nodes or b not in nodes for a, b in coupling):
        raise ValueError('Magic coupling refers to an unknown original node.')

    edges = []
    for _, tokens in resistance:
        if not tokens:
            continue
        kind = tokens[0]
        if kind == 'rnode':
            if len(tokens) != 7 or _number(tokens[2], 'rnode intrinsic resistance') != 0:
                raise ValueError('Unsupported Magic rnode record.')
            name = _name(tokens[1])
            if name in rnodes:
                raise ValueError('Duplicate Magic resistance node: ' + name)
            rnodes[name] = {'raw_weight': _number(tokens[3], 'rnode capacitance weight'),
                            'xy': [_coordinate(v) for v in tokens[4:6]]}
        elif kind == 'resist':
            if len(tokens) != 4:
                raise ValueError('Incomplete Magic resistance record.')
            _number(tokens[3], 'resistance')
            edges.append(tuple(_name(v) for v in tokens[1:3]))
        elif kind == 'killnode':
            if len(tokens) != 2 or tokens[1] not in nodes or tokens[1] in killed:
                raise ValueError('Unknown or duplicate killed Magic node.')
            killed.add(tokens[1])
    if not rnodes or not killed.isdisjoint(ports):
        raise ValueError('Magic RC requires an intact original port interface.')
    if substrate[0] not in rnodes or substrate[0] in killed:
        raise ValueError('Magic RC requires an explicit retained substrate reference node.')
    if len({n.casefold() for n in rnodes}) != len(rnodes):
        raise ValueError('Magic resistance node names collide in case-insensitive SPICE.')
    if any(not math.isfinite(n['cap_af']) for n in nodes.values()) or any(not math.isfinite(c) for c in coupling.values()):
        raise ValueError('Overflow in original Magic capacitance values.')

    groups = {name: [] for name in nodes}
    owner = {}
    for name in rnodes:
        candidates = [original_name for original_name in nodes
                      if name == original_name or
                      re.fullmatch(re.escape(original_name.rstrip('#!')) + r'\.[nt][0-9]+', name)]
        if not candidates:
            raise ValueError('Unmapped Magic resistance node: ' + name)
        longest = max(len(n.rstrip('#!')) for n in candidates)
        candidates = [n for n in candidates if len(n.rstrip('#!')) == longest]
        if len(candidates) != 1:
            raise ValueError('Ambiguous Magic resistance node: ' + name)
        owner[name] = candidates[0]
        groups[candidates[0]].append(name)
    originals_casefold = {n.casefold(): n for n in nodes}
    if any(originals_casefold.get(n.casefold(), net) != net for n, net in owner.items()):
        raise ValueError('Magic original and resistance nodes collide in case-insensitive SPICE.')
    if any(not group for group in groups.values()):
        raise ValueError('Original Magic net has no extracted resistance nodes.')
    if any(name not in killed and name not in rnodes for name in nodes):
        raise ValueError('Unsplittable original Magic node has no retained anchor.')

    parent = {name: name for name in rnodes}
    def find(name):
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name
    for a, b in edges:
        if a not in rnodes or b not in rnodes or owner[a] != owner[b]:
            raise ValueError('Magic resistance graph crosses or escapes an original net.')
        parent[find(a)] = find(b)
    for names in groups.values():
        if len({find(name) for name in names}) != 1:
            raise ValueError('Magic resistance nodes for one original net are disconnected.')

    originals, replacements = {}, {}
    for records, target in ((original, originals), (resistance, replacements)):
        for _, tokens in records:
            if tokens and tokens[0] == 'device':
                info = _device(tokens)
                if info['identity'] in target:
                    raise ValueError('Duplicate Magic device geometry identity.')
                target[info['identity']] = info
    if replacements.keys() - originals.keys():
        raise ValueError('Magic resistance extraction introduced an unknown device.')
    device_signatures = []
    for identity, info in originals.items():
        effective = replacements.get(identity, info)
        terminals = effective['electrical']
        if any(n not in owner for n in terminals):
            raise ValueError('Magic resistance device has an unmapped electrical terminal.')
        if [owner[n] for n in terminals] != info['electrical']:
            raise ValueError('Magic resistance extraction changed a device terminal net.')
        device_signatures.append({'prefix': info['prefix'], 'model': info['model'],
                                  'terminals': terminals, 'original_terminals': info['electrical'],
                                  'name': next((d['name'] for d in primitive_devices if tuple(d['identity']) == identity), None),
                                  'numeric_value': info['numeric_value']})

    weights, net_evidence = {}, {}
    for net, names in groups.items():
        total = math.fsum(rnodes[name]['raw_weight'] for name in names)
        if not math.isfinite(total):
            raise ValueError('Overflow in Magic node area weights.')
        if total:
            values = {name: rnodes[name]['raw_weight'] / total for name in names
                      if rnodes[name]['raw_weight'] > 0}
            fallback = None
        else:
            origin = nodes[net]['xy']
            anchor = min(names, key=lambda name: (sum((a - b) ** 2 for a, b in
                                                     zip(rnodes[name]['xy'], origin)), name))
            values = {anchor: 1.0}
            fallback = {'method': 'nearest-original-node-origin', 'anchor': anchor,
                        'original_xy': origin, 'anchor_xy': rnodes[anchor]['xy']}
        weights[net] = values
        net_evidence[net] = {'original_ground_af': nodes[net]['cap_af'],
                             'rnode_count': len(names), 'nodes': names, 'weights': values, 'fallback': fallback}
    generated_count = sum(len(weights[a]) * len(weights[b]) for (a, b), cap in coupling.items() if cap)
    ground_count = sum(len(weights[net]) for net, data in nodes.items() if data['cap_af'])
    if generated_count + ground_count > max_capacitors:
        raise ValueError('Magic capacitance expansion exceeds the declared budget: ' + str(generated_count + ground_count))

    corrected_rnode = {name: 0.0 for name in rnodes}
    for net, values in weights.items():
        for name, weight in values.items():
            corrected_rnode[name] = nodes[net]['cap_af'] * weight / rscale[1]
    normalized_original = []
    for line, tokens in original:
        if tokens and tokens[0] == 'cap':
            continue
        if tokens and tokens[0] in ('node', 'substrate'):
            tokens = list(tokens)
            tokens[3] = '0'
            line = _line(tokens)
        normalized_original.append(line)
    normalized_resistance = []
    for line, tokens in resistance:
        if tokens and tokens[0] == 'rnode':
            tokens = list(tokens)
            tokens[3] = format(corrected_rnode[tokens[1]], '.17g')
            line = _line(tokens)
        normalized_resistance.append(line)
    # Check serialized values, not just the pre-serialization arithmetic.
    actual_ground = {net: math.fsum(float(format(corrected_rnode[name], '.17g')) * rscale[1]
                                   for name in names) for net, names in groups.items()}
    actual_coupling = {}
    for (a, b), cap in sorted(coupling.items()):
        terms = []
        if cap:
            for aname, aw in weights[a].items():
                for bname, bw in weights[b].items():
                    value = format(cap * aw * bw / rscale[1], '.17g')
                    normalized_resistance.append('cap ' + json.dumps(aname) + ' ' +
                                                 json.dumps(bname) + ' ' + value)
                    terms.append(float(value) * rscale[1])
        actual_coupling[(a, b)] = math.fsum(terms)
    expected = _matrix({net: data['cap_af'] for net, data in nodes.items()}, coupling)
    actual = _matrix(actual_ground, actual_coupling)
    differences = [abs(expected[key] - actual.get(key, 0.0)) for key in expected]
    if (set(actual) != set(expected) or
            any(not math.isclose(expected[key], actual[key], rel_tol=1e-12, abs_tol=1e-12)
                for key in expected)):
        raise ValueError('Magic RC normalization did not conserve the original capacitance matrix.')
    normalized_original_text = '\n'.join(normalized_original) + '\n'
    normalized_resistance_text = '\n'.join(normalized_resistance) + '\n'
    evidence = {'schema_version': 1, 'algorithm': ALGORITHM, 'top': top,
                'implementation_sha256': file_digest(__file__),
                'scope': 'Flat distributed Magic resistance with area weighted lumped original ground and mutual capacitance; not a spatial field solver.',
                'units': 'attofarads', 'original_scale': scale, 'resistance_scale': rscale,
                'equations': {'ground': 'C_i = C_original_ground * w_i',
                              'mutual': 'C_ij = C_original_mutual * w_i * w_j',
                              'weights': 'w_i = positive_raw_rnode_C_i / sum(positive_raw_rnode_C)'},
                'weights_scope': 'Normalized positive extresist rnode C follows its area redistribution. Raw C magnitudes are discarded.',
                'aliases': aliases, 'devices': device_signatures, 'primitive_devices': primitive_devices,
                'nets': net_evidence, 'mutual_pairs': len(coupling),
                'generated_mutual_capacitors': generated_count, 'max_capacitors': max_capacitors,
                'generated_ground_capacitors': ground_count,
                'resistor_count': len(edges),
                'conservation': {'status': 'passed', 'matrix_entries': len(expected),
                                 'maximum_error_af': max(differences, default=0.0),
                                 'relative_tolerance': 1e-12, 'absolute_tolerance_af': 1e-12,
                                 'entries': [{'a': a, 'b': b, 'original_af': expected[(a, b)],
                                              'normalized_af': actual[(a, b)]} for a, b in sorted(expected)]},
                'files': {raw_original.name: hashlib.sha256(original_bytes).hexdigest(),
                          raw_resistance.name: hashlib.sha256(resistance_bytes).hexdigest(),
                          original_path.name: hashlib.sha256(normalized_original_text.encode()).hexdigest(),
                          resistance_path.name: hashlib.sha256(normalized_resistance_text.encode()).hexdigest()}}
    if device_reference.is_file():
        evidence['files'][device_reference.name] = file_digest(device_reference)
    # Check the input bytes again before preserving and replacing them.
    if original_path.read_bytes() != original_bytes or resistance_path.read_bytes() != resistance_bytes:
        raise ValueError('Magic extraction changed during capacitance normalization.')
    atomic_write(raw_original, original_bytes)
    atomic_write(raw_resistance, resistance_bytes)
    atomic_write(original_path, normalized_original_text)
    atomic_write(resistance_path, normalized_resistance_text)
    atomic_write(report_path, json.dumps(evidence, indent=2, allow_nan=False))
    return evidence


def _spice_devices(text, *, owner=None, physical_passives=None):
    """Canonical physical-device inventory with every emitted parameter."""
    owner = owner or {}
    inventory = Counter()
    text = re.sub(r'\n[ \t]*\+[ \t]*', ' ', text)
    def value(token):
        try:
            return ('number', scalar(token))
        except ValueError:
            return ('expression', token.casefold())
    for line in text.splitlines():
        t = line.split()
        if not t or t[0].startswith(('*', '.')):
            continue
        prefix = t[0][0].casefold()
        if prefix in ('r', 'c') and physical_passives is not None and t[0].casefold() not in physical_passives:
            continue
        start = next((i for i, token in enumerate(t) if '=' in token), len(t))
        params = []
        for token in t[start:]:
            if '=' not in token:
                raise ValueError('Malformed physical device reference parameter.')
            name, raw = token.split('=', 1)
            params.append((name.casefold(), value(raw)))
        if len({name for name, _ in params}) != len(params):
            raise ValueError('Duplicate physical device reference parameter.')
        explicit = None
        if prefix in ('r', 'c'):
            terminal_end = 3
            rest = t[3:start]
            if len(rest) == 1:
                try:
                    explicit, model = scalar(rest[0]), 'none'
                except ValueError:
                    model = rest[0].casefold()
            elif len(rest) == 2:
                explicit, model = scalar(rest[0]), rest[1].casefold()
            else:
                raise ValueError('Unsupported physical passive reference record.')
        elif prefix in ('x', 'm'):
            terminal_end = 5 if prefix == 'm' else start - 1
            if terminal_end < 2 or terminal_end >= len(t):
                raise ValueError('Malformed physical device reference record.')
            model = t[terminal_end].casefold()
        else:
            raise ValueError('Unsupported physical device reference record.')
        terminals = tuple(owner.get(n, n) for n in t[1:terminal_end])
        inventory[(prefix, model, terminals, explicit, tuple(sorted(params)))] += 1
    return inventory


def _restore_junction_parameters(lines, reference, owner, physical_passives, names_by_model):
    """Retain pre-R junction geometry when node splitting redistributes it.

    Match by model, contracted ordered terminals, value and every non-junction
    parameter (including W/L/multiplicity). Ambiguous reference geometries fail;
    never select an arbitrary device or alter dimension/multiplicity fields.
    """
    groups = {}
    def identity(signature):
        names = names_by_model.get(signature[1], set())
        return (*signature[:4], tuple(p for p in signature[4] if p[0] not in names))
    for signature in reference:
        groups.setdefault(identity(signature), set()).add(signature[4])
    restored = 0
    for index, line in enumerate(lines):
        signatures = _spice_devices(line, owner=owner, physical_passives=physical_passives)
        if not signatures:
            continue
        signature = next(iter(signatures)); candidates = groups.get(identity(signature), set())
        names = names_by_model.get(signature[1], set())
        if signature[4] in candidates:
            continue
        if len(candidates) != 1:
            continue  # The final inventory check reports changed/ambiguous data.
        parameters = next(iter(candidates)); expected = dict(parameters); actual = dict(signature[4])
        if actual.keys() != expected.keys():
            continue
        replacements = {key: expected[key] for key in names & expected.keys() if expected[key] != actual[key]}
        if any(value[0] != 'number' for value in replacements.values()):
            continue
        def replace(match):
            key = match[1].casefold()
            return (match[1] + '=' + format(replacements[key][1], '.17g')) if key in replacements else match[0]
        lines[index] = re.sub(r'(?<!\S)([^\s=]+)=([^\s]+)', replace, line)
        restored += len(replacements)
    return restored


def finalize(directory, top, *, spice_name='extracted.spice'):
    """Preserve Magic's export and replace quantized parasitic C at full precision.

    The supported exporter prints C below 1 aF as zero and can bias resistance
    by 0.5 milliohm. Preserve identified physical R/C, MOS and subcircuit lines;
    restore original wire R values and parasitic C at full precision. Require
    the exact named R graph and device connections, then independently collapse
    the resulting SPICE parasitic C matrix and compare it with the raw .ext.
    """
    directory = Path(directory).resolve()
    if not isinstance(spice_name, str) or Path(spice_name).name != spice_name:
        raise ValueError('Magic RC SPICE filename must be a plain filename.')
    report_path = directory / 'rc-normalization.json'
    evidence = json.loads(report_path.read_text())
    if evidence.get('algorithm') != ALGORITHM or evidence.get('top') != top:
        raise ValueError('Magic RC normalization report does not match this extraction.')
    if 'export' in evidence or (directory / 'raw-export.spice').exists():
        raise ValueError('Magic RC export has already been finalized.')
    for filename, checksum in evidence['files'].items():
        if Path(filename).name != filename or file_digest(directory / filename) != checksum:
            raise ValueError('Magic RC normalization evidence changed before export finalization.')
    original = _records((directory / (top + '.raw.ext')).read_text(), _ORIGINAL_KEYS)
    raw_resistance = _records((directory / (top + '.raw.res.ext')).read_text(), _RESISTANCE_KEYS)
    original, raw_resistance, _ = _prepare_devices(original, raw_resistance)
    original, _, _ = _aliases(original, raw_resistance)
    resistance = _records((directory / (top + '.res.ext')).read_text(), _RESISTANCE_KEYS | {'cap'})
    cscale = _scale(original)[1]
    rscale = _scale(resistance)
    ground, original_coupling, reference = {}, {}, None
    expected_devices = Counter()
    expected_ports = sorted((int(t[2]), t[1]) for _, t in original if t and t[0] == 'port')
    for _, t in original:
        if not t:
            continue
        if t[0] in ('node', 'substrate'):
            ground[t[1]] = float(t[3]) * cscale
            if t[0] == 'substrate':
                reference = t[1]
        elif t[0] == 'cap':
            pair = tuple(sorted(t[1:3]))
            original_coupling[pair] = original_coupling.get(pair, 0.) + float(t[3]) * cscale
        elif t[0] == 'device':
            info = _device(t)
            expected_devices[(info['prefix'], info['model'])] += 1
        elif t[0] == 'fet':
            expected_devices[('m', t[1].casefold())] += 1
    owner = {name: net for net, info in evidence['nets'].items() for name in info['nodes']}
    required_edges, desired_caps, required_resistance = [], [], {}
    for _, t in resistance:
        if not t:
            continue
        if t[0] == 'resist':
            required_edges.append((t[1], t[2]))
            required_resistance.setdefault(tuple(sorted(t[1:3])), []).append(float(t[3]) * rscale[0] / 1000.)
        elif t[0] == 'rnode' and float(t[3]):
            desired_caps.append((t[1], reference, float(t[3]) * rscale[1] * 1e-18))
        elif t[0] == 'cap' and float(t[3]):
            desired_caps.append((t[1], t[2], float(t[3]) * rscale[1] * 1e-18))
    spice_path = directory / spice_name
    raw = spice_path.read_bytes()
    lines = raw.decode('utf-8').splitlines(keepends=True)
    active = False
    declarations = endings = 0
    edges, seen_nodes, keep, removed = [], set(), [], 0
    declared_names = set()
    observed_devices = Counter()
    observed_terminals = Counter()
    observed_resistance = {}
    resistor_lines = {}
    physical_passives = {d['name'].casefold(): d for d in evidence.get('devices', []) if d.get('name')}
    observed_passives = set()
    insert_at = None
    for line in lines:
        tokens = line.split()
        if not tokens or tokens[0].startswith('*'):
            keep.append(line)
            continue
        token = tokens[0].casefold()
        if token == '.subckt':
            declarations += 1
            if len(tokens) < 3 or tokens[1] != top or active:
                raise ValueError('Unexpected Magic RC SPICE subcircuit interface.')
            active = True
            if tokens[2:] != [name for _, name in expected_ports]:
                raise ValueError('Magic exporter changed the original port interface.')
            seen_nodes.update(tokens[2:])
        elif token == '.ends':
            if not active:
                raise ValueError('Unexpected Magic RC SPICE subcircuit ending.')
            endings += 1
            active = False
            insert_at = len(keep)
        elif not token.startswith(('.', '+')):
            if not active or token in declared_names:
                raise ValueError('Duplicate or out-of-scope Magic RC SPICE device.')
            declared_names.add(token)
            if token in physical_passives:
                physical = physical_passives[token]
                if len(tokens) < 4 or list(tokens[1:3]) != physical['terminals']:
                    raise ValueError('Magic exporter changed a physical passive device terminal.')
                if physical['numeric_value'] is not None:
                    value = scalar(tokens[3])
                    if not math.isclose(value, physical['numeric_value'], rel_tol=5e-6, abs_tol=1e-24):
                        raise ValueError('Magic exporter changed a physical passive device value.')
                    if any('=' not in v for v in tokens[4:]):
                        raise ValueError('Unexpected numeric physical passive device model.')
                else:
                    parameters = next((i for i, v in enumerate(tokens) if '=' in v), len(tokens))
                    if parameters < 4 or tokens[parameters - 1].casefold() != physical['model']:
                        raise ValueError('Magic exporter changed a physical passive device model.')
                    if parameters not in (4, 5):
                        raise ValueError('Unsupported physical passive device value/model fields.')
                    if parameters == 5:
                        _number(scalar(tokens[3]), 'physical passive device value')
                seen_nodes.update(tokens[1:3]); observed_passives.add(token)
                observed_devices[(physical['prefix'], physical['model'])] += 1
                observed_terminals[(physical['prefix'], physical['model'], tuple(tokens[1:3]))] += 1
            elif token.startswith('r'):
                if len(tokens) != 4:
                    raise ValueError('Unsupported Magic RC SPICE resistor record.')
                edges.append((tokens[1], tokens[2]))
                value = scalar(tokens[3])
                if value < 0:
                    raise ValueError('Magic exported a negative distributed resistance.')
                observed_resistance.setdefault(tuple(sorted(tokens[1:3])), []).append(value)
                resistor_lines.setdefault(tuple(sorted(tokens[1:3])), []).append((value, len(keep)))
                seen_nodes.update(tokens[1:3])
            elif token.startswith('c'):
                if len(tokens) != 4:
                    raise ValueError('Unsupported Magic RC SPICE capacitor record.')
                removed += 1
                seen_nodes.update(tokens[1:3])
                continue
            elif token.startswith(('m', 'x')):
                parameter_start = next((i for i, v in enumerate(tokens) if '=' in v), len(tokens))
                model_index = 5 if token.startswith('m') else parameter_start - 1
                if model_index < 2 or model_index >= len(tokens) or (token.startswith('m') and parameter_start < 6):
                    raise ValueError('Malformed Magic RC MOS or subcircuit device.')
                terminals = tokens[1:model_index]
                if not terminals or any(n not in owner for n in terminals):
                    raise ValueError('Magic RC MOS or subcircuit device has an unmapped endpoint.')
                seen_nodes.update(terminals)
                observed_devices[(token[0], tokens[model_index].casefold())] += 1
                observed_terminals[(token[0], tokens[model_index].casefold(), tuple(terminals))] += 1
            else:
                raise ValueError('Unsupported Magic RC SPICE device type.')
        keep.append(line)
    if active or declarations != 1 or endings != 1 or insert_at is None:
        raise ValueError('Magic RC requires one complete flat SPICE subcircuit.')
    if Counter(tuple(sorted(e)) for e in edges) != Counter(tuple(sorted(e)) for e in required_edges):
        raise ValueError('Magic exporter changed or renamed the distributed resistance graph.')
    # EFread's RESISTOR path adds 0.5 milliohm before storing a float (a remnant
    # of former integer rounding), so it biases every exported resistor. Accept
    # only the exact value or that identified engine artifact within six-digit
    # serialization error, then emit the original .res.ext resistance exactly.
    restored_resistors = 0
    for pair, values in required_resistance.items():
        for expected, (observed, index) in zip(sorted(values), sorted(resistor_lines[pair])):
            if not any(math.isclose(value, observed, rel_tol=5e-6, abs_tol=1e-15)
                       for value in (expected, expected + .0005)):
                raise ValueError('Magic exporter changed a distributed resistance value.')
            if expected != observed:
                restored_resistors += 1
            keep[index] = re.sub(r'^(\s*\S+\s+\S+\s+\S+\s+)\S+(\s*)$',
                                 lambda m: m[1] + format(expected, '.17g') + m[2], keep[index])
    if observed_devices != expected_devices:
        raise ValueError('Magic exporter changed the original MOS or subcircuit model inventory.')
    if observed_passives != physical_passives.keys():
        raise ValueError('Magic exporter omitted a physical primitive resistor or capacitor.')
    if not any(t and t[0] == 'fet' for _, t in original):
        expected_terminals = Counter((d['prefix'], d['model'], tuple(d['terminals']))
                                     for d in evidence.get('devices', []))
        if observed_terminals != expected_terminals:
            raise ValueError('Magic exporter changed a device electrical terminal connection.')
    parameter_check = {'status': 'not_checked', 'reason': 'No pre-resistance physical device reference export.'}
    if 'device-reference.spice' in evidence['files']:
        expected_signatures = _spice_devices((directory / 'device-reference.spice').read_text(), owner=evidence.get('aliases'))
        junction_names = {d['model']: {'ad', 'as', 'pd', 'ps'} for d in evidence.get('devices', [])}
        protected = {model: {'w', 'l', 'm', 'mf', 'nf', 'mult', 'width', 'length'} for model in junction_names}
        for _, tokens in original:
            if tokens and tokens[0] == 'parameters':
                model = tokens[1].casefold()
                junction_names.setdefault(model, set()).update(token.split('=', 1)[1].casefold() for token in tokens[2:]
                                                               if re.match(r'^[ap][12]=[^=]+$', token))
                protected.setdefault(model, {'w', 'l', 'm', 'mf', 'nf', 'mult', 'width', 'length'}).update(
                    token.split('=', 1)[1].casefold() for token in tokens[2:] if re.match(r'^[wl]=[^=]+$', token))
        for model in junction_names:
            junction_names[model] -= protected[model]
        restored_junctions = _restore_junction_parameters(keep, expected_signatures, owner,
                                                         physical_passives, junction_names)
        actual_signatures = _spice_devices(''.join(keep), owner=owner,
                                          physical_passives=physical_passives)
        if expected_signatures != actual_signatures:
            raise ValueError('Magic exporter changed physical device parameters or contracted terminal connectivity.')
        parameter_check = {'status': 'passed', 'devices': sum(actual_signatures.values()),
                           'reference': 'device-reference.spice',
                           'restored_junction_fields': restored_junctions,
                           'junction_scope': 'Pre-R area/perimeter fields retained when splitting shared nets changes Magic redistribution; unambiguous model/terminals/all other parameters required.',
                           'scope': 'All physical model/value/parameter fields after contracting only distributed wire resistance.'}
    required_nodes = {n for a, b, _ in desired_caps for n in (a, b)}
    required_nodes.update(n for d in evidence.get('devices', []) for n in d['terminals'])
    required_nodes.update(n for _, n in expected_ports)
    if not required_nodes <= seen_nodes:
        raise ValueError('Magic exporter omitted or renamed normalized capacitance nodes.')
    emitted = []
    for index, (a, b, cap) in enumerate(desired_caps):
        name = 'C_STUDIO_RC_' + str(index)
        if name.casefold() in declared_names:
            raise ValueError('Magic RC generated capacitor name collides with an exported device.')
        if a not in owner or b not in owner or not math.isfinite(cap) or cap <= 0:
            raise ValueError('Magic RC full-precision capacitance has an invalid endpoint or value.')
        emitted.append(name + ' ' + a + ' ' + b + ' ' + format(cap, '.17g') + '\n')
    keep[insert_at:insert_at] = emitted
    corrected = ''.join(keep)
    # Independent final SPICE graph collapse: do not use the rewrite's matrix.
    parents = {name: name for name in owner}
    def find(name):
        while parents[name] != name:
            parents[name] = parents[parents[name]]
            name = parents[name]
        return name
    for a, b in edges:
        if a not in parents or b not in parents:
            raise ValueError('Magic SPICE resistor has an unmapped endpoint.')
        parents[find(a)] = find(b)
    components = {}
    for name, net in owner.items():
        component = find(name)
        if component in components and components[component] != net:
            raise ValueError('Exported Magic resistance shorts original nets.')
        components[component] = net
    actual_ground = {name: 0. for name in ground}
    actual_coupling = {}
    for line in corrected.splitlines():
        t = line.split()
        if not t or not t[0].startswith('C_STUDIO_RC_'):
            continue
        a, b = components[find(t[1])], components[find(t[2])]
        cap = float(t[3]) * 1e18
        if a == b:
            raise ValueError('Normalized capacitor collapses onto one net.')
        if reference in (a, b):
            other = b if a == reference else a
            actual_ground[other] += cap
        else:
            pair = tuple(sorted((a, b)))
            actual_coupling[pair] = actual_coupling.get(pair, 0.) + cap
    # Original explicit coupling to substrate is ground in the reduced matrix.
    for pair in list(original_coupling):
        if reference in pair:
            other = pair[1] if pair[0] == reference else pair[0]
            ground[other] += original_coupling.pop(pair)
    expected = _matrix(ground, original_coupling)
    observed = _matrix(actual_ground, actual_coupling)
    all_keys = set(expected) | set(observed)
    if any(not math.isclose(expected.get(k, 0.), observed.get(k, 0.), rel_tol=1e-12, abs_tol=1e-12)
           for k in all_keys):
        raise ValueError('Final Magic SPICE capacitance matrix does not match original extraction.')
    export = {'status': 'passed', 'raw_file': 'raw-export.spice', 'file': spice_name,
              'raw_sha256': hashlib.sha256(raw).hexdigest(),
              'sha256': hashlib.sha256(corrected.encode()).hexdigest(),
              'removed_quantized_capacitors': removed, 'full_precision_capacitors': len(emitted),
              'preserved_physical_passives': sorted(observed_passives),
              'device_parameters': parameter_check,
              'unobservable_normalization_nodes': sorted(set(owner) - seen_nodes),
              'resistor_graph': 'exact original named edge multiset preserved',
              'resistor_values': {'status': 'passed', 'relative_tolerance': 5e-6,
                                  'absolute_tolerance_ohm': 1e-15, 'count': len(edges),
                                  'restored_values': restored_resistors,
                                  'final_values': 'Original .res.ext resistance scaled to ohms at 17 significant digits.',
                                  'recognized_export_bias_ohm': .0005},
              'device_terminals': {'status': 'passed' if not any(t and t[0] == 'fet' for _, t in original)
                                  else 'legacy-record-inventory-only', 'count': sum(observed_terminals.values())},
              'physical_device_lines': 'preserved except explicitly reported pre-R junction area/perimeter restoration',
              'non_capacitor_lines': 'preserved except original full-precision distributed resistance values restored',
              'quantization_reason': 'Supported Magic esSIvalue emits C below 1 aF as zero; all parasitic C is serialized at 17 significant digits.',
              'matrix_entries': len(all_keys),
              'maximum_error_af': max((abs(expected.get(k, 0.) - observed.get(k, 0.)) for k in all_keys), default=0.),
              'relative_tolerance': 1e-12, 'absolute_tolerance_af': 1e-12}
    evidence['export'] = export
    evidence['files'].update({'raw-export.spice': export['raw_sha256'], spice_name: export['sha256']})
    serialized = json.dumps(evidence, indent=2, allow_nan=False)
    if spice_path.read_bytes() != raw:
        raise ValueError('Magic SPICE export changed during finalization.')
    atomic_write(directory / 'raw-export.spice', raw)
    atomic_write(spice_path, corrected)
    atomic_write(report_path, serialized)
    return evidence


def contract(text, normalization):
    """Contract only interconnect R/C, keeping primitive physical R/C devices.

    This creates an independent topology-check deck, not a simulation substitute
    for post-layout RC. Every physical device parameter is retained verbatim.
    """
    if normalization.get('export', {}).get('status') != 'passed':
        raise ValueError('Contract only a finalized Magic RC extraction.')
    if hashlib.sha256(text.encode()).hexdigest() != normalization['export']['sha256']:
        raise ValueError('Finalized Magic RC netlist changed before contraction.')
    owner = {name: net for net, data in normalization['nets'].items() for name in data['nodes']}
    physical_passives = {d['name'].casefold() for d in normalization.get('devices', []) if d.get('name')}
    lines = []
    for line in text.splitlines(keepends=True):
        fields = line.split()
        if not fields or fields[0].startswith(('*', '.', '+')):
            lines.append(line); continue
        prefix = fields[0][0].lower()
        if prefix in ('r', 'c') and fields[0].casefold() not in physical_passives:
            continue
        end = (3 if prefix in ('r', 'c') else 5 if prefix == 'm' else
               next((i for i, v in enumerate(fields) if '=' in v), len(fields)) - 1)
        if prefix not in ('r', 'c', 'm', 'x') or end < 2 or any(n not in owner for n in fields[1:end]):
            raise ValueError('Unsupported device while contracting finalized Magic RC.')
        # Replace node fields alone; preserve model parameters and all remaining
        # characters, including continuation lines handled below.
        spans = list(re.finditer(r'\S+', line))
        for i in range(end - 1, 0, -1):
            match = spans[i]; line = line[:match.start()] + owner[fields[i]] + line[match.end():]
        lines.append(line)
    return ''.join(lines)
