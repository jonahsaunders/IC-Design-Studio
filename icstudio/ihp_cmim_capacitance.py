"""Check Magic's flat capacitance export for ordinary parallel IHP MiM units."""
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import re

from .catalog import IDENT, binding_for
from .model import digest, file_digest
from .native_vectors import ports as electrical_ports


DEVICE = 'sg13g2_pr/cap_cmim.sym'
PACKAGE_SHA256 = '5cb4aca37ed4192eadd82d686a1d5fc97072b018e7c45d21f062333a3361eebd'
MAGIC_FILES = tuple('libs.tech/magic/' + name + '.tech' for name in (
    'icstudio-ihp-sg13g2', 'icstudio-ihp-sg13g2-cifout',
    'ihp-sg13g2-cifin', 'ihp-sg13g2-drc', 'ihp-sg13g2-extract',
))
FLAT_COMMANDS = ('\next2spice hierarchy off\next2spice -o extracted-flat.spice\n'
                 'puts "STUDIO_CMIM_CIF_SCALE [cif scale out]"\n')
INTEGER = re.compile(r'-?[0-9]{1,16}')
NUMBER = re.compile(r'([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,2})?)(meg|[tgkmunpf]?)', re.I)
EXPONENT = {'': 0, 't': 12, 'g': 9, 'meg': 6, 'k': 3, 'm': -3, 'u': -6, 'n': -9,
            'p': -12, 'f': -15}
SCOPE = ('IHP cap_cmim capacitance requires a flat two-port DUT with ordinary catalog units '
         'sharing ordered electrodes and positive integer multiplicity.')


@dataclass(frozen=True)
class Unit:
    top: str
    ports: tuple
    terminals: tuple
    width: Decimal
    length: Decimal


@dataclass(frozen=True)
class Parallel:
    top: str
    ports: tuple
    terminals: tuple
    # Sorted (width, length, count) groups, without expanding large multipliers.
    units: tuple


def intrinsic_units(unit):
    if isinstance(unit, Unit):
        return Counter({(unit.width, unit.length): 1})
    return Counter({(w, l): count for w, l, count in unit.units})


def number(text, units=False):
    match = NUMBER.fullmatch(text) if len(text) <= 40 else None
    if not match or (not units and match[2]):
        raise ValueError('IHP cap_cmim capacitance requires finite literal native values.')
    sign, digits, exponent = Decimal(match[1]).as_tuple()
    return Decimal((sign, digits, exponent + EXPONENT[match[2].lower()]))


def edge(a, b):
    return tuple(sorted((a, b)))


def spice_rows(text, top, ports):
    rows = [line.split() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith('*')]
    if (len(rows) < 3 or rows[0] != ['.subckt', top, *ports]
            or rows[-1] not in (['.ends'], ['.ends', top])):
        raise ValueError('IHP cap_cmim ordered SPICE interface differs.')
    return rows[1:-1]


def device_row(row, terminals, source=False):
    if (len(row) < 6 or not IDENT.fullmatch(row[0]) or row[0][0].upper() != 'X'
            or row[1:4] != [*terminals, 'cap_cmim']):
        raise ValueError('IHP cap_cmim ordered intrinsic device terminals differ.')
    params = {}
    allowed = {'w', 'l', 'm', 'mm_ok'} if source else {'w', 'l', 'm'}
    for item in row[4:]:
        key, separator, value = item.partition('=')
        if not separator or key in params or key not in allowed:
            raise ValueError('Unsupported or repeated IHP cap_cmim intrinsic parameter.')
        params[key] = number(value, units=True)
    multiplicity = params.get('m', Decimal(1))
    if (not {'w', 'l'} <= params.keys() or (source and params.keys() != allowed)
            or min(params['w'], params['l']) <= 0
            or multiplicity <= 0 or multiplicity != multiplicity.to_integral_value()
            or params.get('mm_ok', 1) not in (0, 1)):
        raise ValueError(SCOPE)
    return params['w'], params['l'], int(multiplicity)


def applicable(project, cell, schematic, selected_technology):
    """Identify a supported source device and authenticate its Magic inputs."""
    from .physical_cells import reachable

    children = set(reachable(project, cell['id']))
    devices = [d for c in project['cells'] if c['id'] in children for d in c['devices']]
    has_catalog_unit = any((d.get('model_ref') or {}).get('device') == DEVICE for d in devices)
    logical = re.sub(r'\n[ \t]*\+[ \t]*', ' ', schematic)
    has_native_unit = re.search(r'(?im)^\s*[xc]\S+[^\n]*\s+cap_cmim(?=[ \t\n]|$)', logical)
    if not has_catalog_unit and not has_native_unit:
        return None, {}
    technology = project['pdk']
    devices = cell['devices']
    if not devices or cell.get('layout_instances'):
        raise ValueError(SCOPE)
    for device in devices:
        if (device['kind'] != 'PDK' or (device.get('model_ref') or {}).get('device') != DEVICE
                or device.get('native_spice') or device.get('array')):
            raise ValueError(SCOPE)
    root = Path(technology['package_root']).resolve()
    lock = technology['package_lock']
    # Managed verification stages the locked assets and the project PDK, not
    # package.json. Reconstruct its complete pinned semantic identity from the
    # project contract, excluding runtime paths and the registry lock wrapper.
    manifest = {'schema': 1, 'family': 'ihp-sg13g2', 'id': lock['id'],
                'revision': lock['revision'], 'files': lock['files'],
                'technology': {name: value for name, value in technology.items()
                               if name not in ('package_root', 'package_lock')}}
    if (digest(manifest) != PACKAGE_SHA256
            or selected_technology.resolve() != root / MAGIC_FILES[0]):
        raise ValueError('IHP cap_cmim capacitance requires the pinned catalog and Magic technology.')
    catalog = binding_for(technology, devices[0])
    bound = {}
    for name in (*MAGIC_FILES, catalog['source'], catalog['model_source']):
        path = (root / name).resolve()
        if not path.is_relative_to(root) or file_digest(path) != lock['files'][name]:
            raise ValueError('IHP cap_cmim capacitance source changed: ' + name)
        bound[str(path)] = lock['files'][name]
    top = cell['name']
    ports = tuple(electrical_ports(cell['ports']))
    terminals = tuple(devices[0]['nets'].get(pin, '') for pin in ('c0', 'c1'))
    if (len(ports) != 2 or len({name.casefold() for name in (*ports, 'SUB')}) != 3
            or set(terminals) != set(ports) or not all(IDENT.fullmatch(name) for name in (top, *ports))):
        raise ValueError(SCOPE)
    rows = spice_rows(schematic, top, ports)
    # Bind every source instance and parameter to the current ordinary project,
    # independently of the captured source supplied by the caller. In particular,
    # a stale source with the same total area or multiplicity is insufficient.
    from .catalog_migration import emit
    expected, observed, units = {}, {}, Counter()
    def signature(row):
        return (*row[1:4], *sorted(row[4:]))
    for device in devices:
        if tuple(device['nets'].get(pin, '') for pin in ('c0', 'c1')) != terminals:
            raise ValueError(SCOPE)
        row = emit(device, technology, 'simulation').split()
        width, length, count = device_row(row, terminals, source=True)
        key = row[0].casefold()
        if key in expected:
            raise ValueError('Repeated IHP cap_cmim catalog instance.')
        expected[key] = (row[0], signature(row))
        units[width, length] += count
    for row in rows:
        device_row(row, terminals, source=True)
        key = row[0].casefold()
        if key in observed:
            raise ValueError('Repeated IHP cap_cmim source instance.')
        observed[key] = (row[0], signature(row))
    if observed != expected:
        raise ValueError('IHP cap_cmim source instances or parameters differ from the ordinary catalog project.')
    if sum(units.values()) == 1:
        width, length = next(iter(units))
        return Unit(top, ports, terminals, width, length), bound
    return Parallel(top, ports, terminals, tuple((w, l, n) for (w, l), n in sorted(units.items()))), bound


def raw_graph(text, unit):
    # The Magic .ext format uses centimicrons for linear quantities and aF
    # for capacitance after applying the scale row. The pinned style is 1:1.
    metadata = {
        'version 8.3', 'tech ihp-sg13g2', 'style ngspice()', 'scale 1000 1 1',
        'resistclasses 3000000 67000 110 88 88 88 88 18 11 7000 260000 1360000',
        'parameters cap_rfcmim w=w l=l', 'parameters cap_cmim w=w l=l',
    }
    counts = Counter()
    native_ports, nodes, graph = {}, {}, {}
    devices, locations = Counter(), set()
    quoted = {f'"{name}"': name for name in (*unit.ports, 'SUB')}
    layers = dict(zip(unit.terminals, ('m6', 'm5')))
    for line in text.splitlines():
        row = line.split()
        if not row:
            continue
        kind = row[0]
        counts[kind] += 1
        if line in metadata:
            metadata.remove(line)
        elif kind == 'timestamp' and len(row) == 2 and INTEGER.fullmatch(row[1]):
            continue
        elif (kind == 'port' and len(row) == 8 and row[1] in quoted
              and all(INTEGER.fullmatch(v) for v in row[2:7])):
            name = quoted[row[1]]
            if name in native_ports or layers.get(name) != row[-1]:
                raise ValueError('IHP cap_cmim raw port or electrode layer differs.')
            native_ports[name] = int(row[2])
        elif (kind in ('node', 'substrate') and len(row) == 31 and row[1] in quoted
              and all(INTEGER.fullmatch(v) for v in [*row[4:6], *row[7:]])):
            name = quoted[row[1]]
            expected = ('substrate', 'space') if name == 'SUB' else ('node', layers[name])
            if name in nodes or (kind, row[6]) != expected or number(row[2]) != 0:
                raise ValueError('IHP cap_cmim raw node or substrate differs.')
            nodes[name] = number(row[3])
        elif kind == 'cap' and len(row) == 4 and all(v in quoted for v in row[1:3]):
            pair = edge(quoted[row[1]], quoted[row[2]])
            if pair != edge(*unit.ports) or pair in graph:
                raise ValueError('Unsupported or repeated IHP cap_cmim raw coupling edge.')
            graph[pair] = number(row[3])
        elif (kind == 'device' and len(row) == 16 and row[1:3] == ['csubckt', 'cap_cmim']
              and all(INTEGER.fullmatch(v) for v in [*row[3:7], *row[11:13], row[14]])
              and row[9] == '"None"' and row[10] == f'"{unit.terminals[0]}"'
              and row[13] == f'"{unit.terminals[1]}"'
              and re.fullmatch(r'[0-9]{1,16},[0-9]{1,16}', row[15])
              and re.fullmatch(r'w=[0-9]{1,16}', row[7]) and re.fullmatch(r'l=[0-9]{1,16}', row[8])):
            width, length = (Decimal(v[2:] + 'e-8') for v in row[7:9])
            location = tuple(int(value) for value in row[3:7])
            if location in locations:
                raise ValueError('Repeated IHP cap_cmim raw intrinsic device location.')
            locations.add(location)
            devices[width, length] += 1
        else:
            raise ValueError('Unsupported IHP cap_cmim raw extraction record: ' + kind)
    if (metadata or counts['timestamp'] != 1 or devices != intrinsic_units(unit)
            or native_ports != {name: i for i, name in enumerate(unit.ports, 1)}
            or set(nodes) != set(quoted.values()) or nodes['SUB'] != 0):
        raise ValueError('Incomplete IHP cap_cmim raw device, interface or metadata.')
    graph.update({edge(name, 'SUB'): nodes[name] for name in unit.ports if nodes[name]})
    if not graph or min(graph.values()) < 1:
        raise ValueError('IHP cap_cmim raw graph has no capacitance or an unsupported sub-attofarad edge.')
    return graph


def spice_graph(text, unit):
    names, graph = set(), {}
    nodes = {*unit.ports, 'SUB'}
    devices = Counter()
    for row in spice_rows(text, unit.top, unit.ports):
        instance = row[0]
        key = instance.casefold()
        if key in names or not IDENT.fullmatch(instance):
            raise ValueError('Invalid or repeated IHP cap_cmim SPICE instance.')
        names.add(key)
        if key[0] == 'x':
            width, length, count = device_row(row, unit.terminals)
            devices[width, length] += count
        elif key[0] == 'c' and len(row) == 4 and set(row[1:3]) <= nodes:
            pair = edge(*row[1:3])
            value = number(row[3], units=True)
            if (pair in graph or pair[0] == pair[1] or value <= 0
                    or not re.fullmatch(r'[0-9]{1,12}(?:\.[0-9]{1,5})?[fpn]', row[3])):
                raise ValueError('Invalid or repeated IHP cap_cmim SPICE capacitance edge.')
            sign, digits, exponent = value.as_tuple()
            graph[pair] = Decimal((sign, digits, exponent + 18))
        else:
            raise ValueError('Unsupported IHP cap_cmim SPICE record: ' + instance)
    if devices != intrinsic_units(unit):
        raise ValueError('IHP cap_cmim SPICE intrinsic dimensions or multiplicities differ from the schematic.')
    return graph


def compare(raw, hierarchical, flat, log, unit):
    scales = re.findall(r'^STUDIO_CMIM_CIF_SCALE (\S+)\s*$', log, re.M)
    if len(scales) != 1 or abs(number(scales[0]) - Decimal('0.01')) > Decimal('5e-10'):
        raise ValueError('IHP cap_cmim extraction did not confirm its pinned 10 nm grid.')
    expected = raw_graph(raw, unit)
    original = spice_graph(hierarchical, unit)
    chosen = spice_graph(flat, unit)
    if chosen.keys() != expected.keys():
        raise ValueError('IHP cap_cmim flat capacitance edges differ from the raw graph.')
    errors = {}
    for pair, want in expected.items():
        # Magic prints five fractional digits in the selected SI unit, after
        # native float conversion. Compare each edge independently in aF.
        half_step = (Decimal('.005') if want < 99990 else
                     Decimal('5') if want < 100010000 else Decimal('5000'))
        error = abs(chosen[pair] - want)
        if error > half_step + want * Decimal('2e-7'):
            raise ValueError('IHP cap_cmim flat capacitance differs from the raw edge ' + '–'.join(pair))
        errors[pair] = error
    identity = {
        'schema': 1, 'scope': 'one flat IHP cap_cmim catalog unit',
        'width_m': str(unit.width), 'length_m': str(unit.length), 'multiplicity': 1,
    } if isinstance(unit, Unit) else {
        'schema': 2, 'scope': 'flat parallel IHP cap_cmim catalog units',
        'multiplicity': sum(intrinsic_units(unit).values()),
        'intrinsic_units': [{'width_m': str(w), 'length_m': str(l), 'multiplicity': count}
                            for (w, l), count in sorted(intrinsic_units(unit).items())],
    }
    return {
        **identity,
        'ports': list(unit.ports), 'intrinsic_terminals': list(unit.terminals),
        'package_semantic_sha256': PACKAGE_SHA256,
        'native_grid_um': scales[0], 'substrate': 'floating internal SUB',
        'hierarchical_export': {'file': 'extracted.spice', 'hierarchy': True},
        'simulation_export': {'file': 'extracted-flat.spice', 'hierarchy': False},
        'edges_af': [{'nodes': list(pair), 'raw': str(want),
                      'hierarchical': str(original[pair]) if pair in original else None,
                      'flat': str(chosen[pair]), 'serialization_error': str(errors[pair])}
                     for pair, want in sorted(expected.items())],
        'hierarchical_only_edges_af': [{'nodes': list(pair), 'value': str(original[pair])}
                                       for pair in sorted(original.keys() - expected.keys())],
    }
