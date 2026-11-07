"""Check literal standard MOS intent against native channels and diffusion groups.

This is separate from native LVS: its public comparator deliberately merges
devices and ignores finger counts. No electrical accuracy or envelope is inferred.
"""
from collections import Counter
from decimal import Decimal, DecimalException
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

from .model import atomic_write, file_digest

MODELS = {
    'gf180mcuC': {'nfet_03v3', 'pfet_03v3'},
    'gf180mcuD': {'nfet_03v3', 'pfet_03v3'},
    'ihp-sg13g2': {'sg13_lv_nmos', 'sg13_lv_pmos', 'sg13_hv_nmos', 'sg13_hv_pmos'},
}
SOURCE_HASHES = {
    'ihp-sg13g2': {
        'libs.tech/ngspice/models/sg13g2_moslv_mod.lib': '84ec57080b9dd4666417f05db6f7b34c8dd3f12118929f9b308018613bece16e',
        'libs.tech/ngspice/models/sg13g2_moshv_mod.lib': '58ce3084c253f2d3753c3b95386e8f4b81dcadfed4f4503dce56862a556c3328',
    },
    'gf180mcuC': {'libs.tech/ngspice/sm141064.ngspice': 'c08ee93073665b6c1f43a3523bb38d5b561bcee2b7e056a927175f5da8e96ba9'},
    'gf180mcuD': {'libs.tech/ngspice/sm141064.ngspice': 'c08ee93073665b6c1f43a3523bb38d5b561bcee2b7e056a927175f5da8e96ba9'},
}
PACKAGE_HASHES = {
    'ihp-sg13g2': '5190bfb7302999409f9f92fd064b5ede63d7a639d7b3b328d3fb5e55e8dc0e39',
    'gf180mcuC': '4fe66bd3c684301030380d4c1b13ecf1611a49dc4fc972f617767b0497430066',
    'gf180mcuD': 'fde9a85427c8457810a3fb87d6df545f7b4007f63def671bfe9dc74bca6a7f68',
}
SCOPE = ('Exact literal standard MOS channel dimensions, finger counts and physical '
         'diffusion groups, associated with model and terminals. Native LVS is separate; '
         'no operating-envelope, RC, statistical or model-accuracy qualification.')


class Unchecked(ValueError):
    """A supported-model occurrence has no unambiguous reviewed interpretation."""


def number(value):
    if len(value) > 96:
        raise Unchecked('MOS numeric literal exceeds the parser length limit.')
    match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d{1,3})?)(meg|[tgkmunpf])?', value, re.I)
    if not match:
        raise Unchecked('MOS grouping requires literal finite numeric parameters.')
    scales = {'': 0, 't': 12, 'g': 9, 'meg': 6, 'k': 3, 'm': -3, 'u': -6, 'n': -9, 'p': -12, 'f': -15}
    try:
        result = Decimal(match[1]) * Decimal(10) ** scales[(match[2] or '').lower()]
    except DecimalException as exc:
        raise Unchecked('Invalid MOS grouping parameter.') from exc
    if not result.is_finite():
        raise Unchecked('Nonfinite MOS grouping parameter.')
    return result


def parameters(tokens):
    result = {}
    for token in tokens:
        if token.count('=') != 1:
            raise Unchecked('Ambiguous MOS grouping parameter syntax.')
        key, value = token.lower().split('=')
        if key in result:
            raise Unchecked('Repeated MOS grouping parameter: ' + key)
        result[key] = number(value)
    return result


def signature(model, nodes):
    drain, gate, source, body = (n.casefold() for n in nodes)
    return model.casefold(), gate, body, tuple(sorted((drain, source)))


def logical_rows(text):
    text = re.sub(r'\n[ \t]*\+[ \t]*', ' ', text)
    return [line.split() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith('*')]


def circuit(text, top, models):
    """Read one literal flat circuit; preserve unknown contexts as unchecked."""
    rows = logical_rows(text)
    declarations = [r for r in rows if r[0].lower() == '.subckt']
    endings = [r for r in rows if r[0].lower() == '.ends']
    if (len(declarations) != 1 or len(endings) != 1 or len(declarations[0]) < 3
            or declarations[0][1].casefold() != top.casefold()
            or len(endings[0]) > 2 or (len(endings[0]) == 2 and endings[0][1].casefold() != top.casefold())):
        raise Unchecked('MOS grouping currently requires one flat, literal circuit.')
    ports = declarations[0][2:]
    if any('=' in n or n.lower() == 'params:' for n in ports) or len({n.casefold() for n in ports}) != len(ports):
        raise Unchecked('Parameterized or ambiguous MOS circuit interface.')
    opened = False
    devices, names = [], set()
    for row in rows:
        kind = row[0].lower()
        if kind == '.subckt':
            opened = True
            continue
        if kind == '.ends':
            opened = False
            continue
        if kind.startswith('.'):
            raise Unchecked('Conditional or external MOS definitions are not checked.')
        if not opened:
            raise Unchecked('Device outside the selected MOS circuit.')
        if kind in names:
            raise Unchecked('Duplicate circuit instance name.')
        names.add(kind)
        if kind[0] in 'xm' and len(row) > 5 and row[5].casefold() in models:
            devices.append((row, parameters(row[6:])))
        elif any(token.casefold() in models for token in row):
            raise Unchecked('Unsupported standard MOS terminal or instance syntax.')
        elif kind.startswith('x'):
            # Other catalog primitives are allowed, but hierarchy is not silently
            # expanded or interpreted as a directly named physical MOS model.
            continue
    return ports, devices


def intent(text, top, target):
    models = MODELS.get(target, set())
    if not any(any(token.casefold() in models for token in row) for row in logical_rows(text)):
        return None
    ports, devices = circuit(text, top, models)
    if not devices:
        raise Unchecked('No directly interpretable standard MOS devices.')
    expected = Counter()
    finger_key = 'ng' if target == 'ihp-sg13g2' else 'nf'
    for row, params in devices:
        if not {'w', 'l'} <= params.keys() or params.get('rfmode', 0) != 0:
            raise Unchecked('MOS grouping requires explicit W/L and the standard non-RF model.')
        width, length = params['w'], params['l']
        if ('nf' if finger_key == 'ng' else 'ng') in params:
            raise Unchecked('Wrong finger-parameter spelling for this MOS model.')
        fingers, copies = params.get(finger_key, Decimal(1)), params.get('m', Decimal(1))
        if (width <= 0 or length <= 0 or not 1 <= fingers <= 8 or fingers != int(fingers)
                or not 1 <= copies <= 16 or copies != int(copies)):
            raise Unchecked('MOS grouping parameters exceed the supported literal recipe.')
        key = (*signature(row[5], row[1:5]), width / fingers, length, int(fingers))
        expected[key] += int(copies)
    return ports, expected


def native_channels(text, top, models):
    _, devices = circuit(text, top, models)
    result = Counter()
    for row, params in devices:
        if (not {'w', 'l'} <= params.keys() or params.get('m', 1) != 1
                or params.get('nf', 1) != 1 or params.get('ng', 1) != 1 or params.get('rfmode', 0) != 0):
            raise ValueError('Native MOS output merged or changed individual channels.')
        result[(*signature(row[5], row[1:5]), params['w'], params['l'])] += 1
    return result


def raw_channels(text, models, scale_um, target='ihp-sg13g2'):
    """Magic locations associate each channel with its physical diffusion group."""
    records, locations, metadata = [], set(), Counter()
    for line in text.splitlines():
        row = shlex.split(line)
        if not row:
            continue
        metadata[row[0]] += 1
        if row[0] in ('version', 'tech', 'style') and row != {
                'version': ['version', '8.3'], 'tech': ['tech', target], 'style': ['style', 'ngspice()']}[row[0]]:
            raise Unchecked('Unreviewed raw MOS technology, version or extraction style.')
        if row[0] == 'use':
            raise Unchecked('Hierarchical raw MOS extraction needs explicit occurrence mapping.')
        # Magic's documented lscale converts linear values to centimicrons:
        # https://opencircuitdesign.com/magic/manpages/ext_manpage.html
        if row[0] == 'scale' and (len(row) != 4 or number(row[3]) * Decimal('.01') != scale_um):
            raise Unchecked('Native MOS extraction and coordinate scales disagree.')
        if row[0] != 'device' or len(row) < 3 or row[2].casefold() not in models:
            continue
        if len(row) != 19 or row[1] != 'msubckt':
            raise Unchecked('Unsupported raw standard MOS channel interface.')
        try:
            location = tuple(int(v) for v in row[3:7])
        except ValueError as exc:
            raise ValueError('Invalid native MOS location.') from exc
        if location in locations or location[0] >= location[2] or location[1] >= location[3]:
            raise ValueError('Repeated or invalid native MOS channel location.')
        locations.add(location)
        params = parameters(row[7:9])
        if set(params) != {'w', 'l'} or min(params.values()) <= 0:
            raise ValueError('Invalid raw MOS channel dimensions.')
        # Raw device terminals are body, gate, source and drain, respectively.
        key = signature(row[2], [row[16], row[10], row[13], row[9]])
        records.append(dict(key=key, width=params['w'] * scale_um * Decimal('1e-6'),
                            length=params['l'] * scale_um * Decimal('1e-6'), location=location))
    if any(metadata[k] != 1 for k in ('scale', 'tech', 'version', 'style')) or not records:
        raise ValueError('Incomplete raw MOS extraction metadata or devices.')
    return records


def geometry(stream, top, target, records, scale_um):
    """Read real masks; never use footprint roles to assign nets or groups."""
    import klayout.db as db
    layout = db.Layout()
    layout.read(str(stream))
    cell = layout.cell(top)
    if cell is None:
        raise ValueError('MOS layout top is missing.')
    dbu = Decimal(str(layout.dbu))
    active_layer, poly_layer = (1, 5) if target == 'ihp-sg13g2' else (22, 30)
    def region(layer):
        index = layout.find_layer(layer, 0)
        return db.Region(cell.begin_shapes_rec(index)).merged() if index is not None else db.Region()
    active, poly = region(active_layer), region(poly_layer)
    physical, consumed = Counter(), set()
    groups = 0
    for group in active.each():
        gates = (db.Region(group) & poly).merged()
        if gates.is_empty():
            continue
        assigned = []
        for gate in gates.each():
            found = []
            for index, record in enumerate(records):
                coords = [Decimal(v) * scale_um / dbu for v in record['location']]
                if any(v != int(v) for v in coords):
                    raise ValueError('Native MOS position is off the exported grid.')
                site = db.Region(db.Box(*map(int, coords)))
                overlap = site & db.Region(gate)
                if not overlap.is_empty() and not (site - db.Region(gate)).is_empty():
                    raise ValueError('Native MOS site is only partially inside a channel.')
                if not overlap.is_empty():
                    found.append(index)
            if not found:
                # Other device classes can intersect active/poly. They are not
                # treated as standard MOS without an actual native declaration.
                continue
            if len(found) != 1 or found[0] in consumed:
                raise ValueError('Native channel has ambiguous physical group membership.')
            index = found[0]
            record = records[index]
            box = gate.bbox()
            dimensions = sorted((Decimal(box.width()) * dbu * Decimal('1e-6'),
                                 Decimal(box.height()) * dbu * Decimal('1e-6')))
            if (dimensions != sorted((record['width'], record['length']))
                    or Decimal(gate.area()) * dbu * dbu * Decimal('1e-12') != record['width'] * record['length']):
                raise ValueError('Native MOS channel dimensions differ from actual masks.')
            consumed.add(index)
            assigned.append(record)
        if not assigned:
            continue
        if len(assigned) != gates.count():
            raise ValueError('A MOS diffusion group contains unaccounted gate crossings.')
        first = assigned[0]
        key = (*first['key'], first['width'], first['length'])
        if any((*r['key'], r['width'], r['length']) != key for r in assigned):
            raise Unchecked('A shared MOS diffusion group mixes terminal classes or dimensions.')
        physical[(*key, len(assigned))] += 1
        groups += 1
    if consumed != set(range(len(records))):
        raise ValueError('Native MOS channels are missing from exported diffusion groups.')
    return physical, groups


def authenticate(technology):
    """Registry formatting may differ; reviewed package content may not."""
    target = technology['package_lock']['id']
    root = Path(technology['package_root']).resolve()
    document = json.loads((root / 'package.json').read_text(encoding='utf-8'))
    canonical = json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    if hashlib.sha256(canonical).hexdigest() != PACKAGE_HASHES[target]:
        raise Unchecked('MOS grouping package semantics are not the reviewed package.')
    if any(technology['package_lock'].get(k) != document[k] for k in ('id', 'revision', 'files')):
        raise Unchecked('Saved MOS package identity differs from the reviewed package.')
    base = document['technology']
    # GF180's ordinary adapter adds its reviewed drawing layers to the sparse
    # upstream package. Preserve original name/mask identities, allow added
    # layers, and read the actual fixed process masks independently below.
    original_layers={r['name']:(r['gds'],r['datatype']) for r in base['layers']}
    current_layers={r['name']:(r['gds'],r['datatype']) for r in technology['layers']}
    if (any(current_layers.get(name)!=pair for name,pair in original_layers.items())
            or technology.get('interoperability',{}) != base.get('interoperability',{})):
        raise Unchecked('MOS grouping layer or native-tool semantics differ from the reviewed package.')
    sources = {str(root / 'package.json'): file_digest(root / 'package.json')}
    for name, expected in document['files'].items():
        if name.startswith(('libs.tech/magic/', 'libs.tech/netgen/')) or name in SOURCE_HASHES[target]:
            path = (root / name).resolve()
            if not path.is_relative_to(root) or file_digest(path) != expected:
                raise Unchecked('Reviewed MOS native/model dependency changed: ' + name)
            sources[str(path)] = expected
    return sources


def correspondence(directory, executable, left, right, top, setup, ports):
    """Retain native legal-node partitions; never force a name equivalence."""
    from .engines import execute, require_lvs_match, tcl_word
    directory.mkdir()
    logfile, mapping = directory/'lvs.log', directory/'nodes.tsv'
    script = ('lvs [list ' + tcl_word(left) + ' ' + tcl_word(top) + '] [list '
              + tcl_word(right) + ' ' + tcl_word(top) + '] ' + tcl_word(setup) + ' ' + tcl_word(logfile) + '\n'
              'set f [open ' + tcl_word(mapping) + ' w]\n'
              'foreach partition [netgen::print -list nodes legal] {\n'
              ' if {[llength $partition] != 2 || [llength [lindex $partition 0]] != 1 || [llength [lindex $partition 1]] != 1} {error "Ambiguous native MOS node partition"}\n'
              ' set a [lindex [lindex $partition 0] 0]\n set b [lindex [lindex $partition 1] 0]\n'
              ' puts $f "[binary encode hex [encoding convertto utf-8 $a]]\\t[binary encode hex [encoding convertto utf-8 $b]]"\n'
              '}\nclose $f\n')
    atomic_write(directory/'mapping.tcl', script)
    output = execute([executable, '-batch', 'source', str(directory/'mapping.tcl')], directory, timeout=60)
    atomic_write(directory/'console.log', output)
    require_lvs_match(logfile.read_text(encoding='utf-8'))
    result, right_names = {}, set()
    for line in mapping.read_text(encoding='utf-8').splitlines():
        fields = line.split('\t')
        if len(fields) != 2:
            raise Unchecked('Malformed native MOS node correspondence.')
        try:
            lhs, rhs = (bytes.fromhex(v).decode('utf-8').casefold() for v in fields)
        except (ValueError, UnicodeError) as exc:
            raise Unchecked('Malformed native MOS node name.') from exc
        if not lhs or not rhs or lhs in result or rhs in right_names:
            raise Unchecked('Native MOS node correspondence is not one-to-one.')
        result[lhs] = rhs; right_names.add(rhs)
    if any(result.get(p.casefold()) != p.casefold() for p in ports):
        raise ValueError('Native MOS correspondence changed an external terminal.')
    return result


def remap(counter, mapping):
    result = Counter()
    for key, count in counter.items():
        model, gate, body, terminals, *rest = key
        try:
            result[(model, mapping[gate], mapping[body], tuple(sorted(mapping[n] for n in terminals)), *rest)] += count
        except KeyError as exc:
            raise Unchecked('A MOS terminal has no retained native node correspondence.') from exc
    return result


def run(directory, technology, source, top, stream, native, magic, magic_technology,
        *, comparison=None, netgen=None, setup=None):
    """Always return a retained proof; callers gate acceptance and bind its files."""
    directory = Path(directory)
    target = technology.get('package_lock', {}).get('id')
    text = Path(source).read_text(encoding='utf-8')
    proof = dict(schema=1, status='NOT_APPLICABLE', scope=SCOPE,
                 native_lvs='Preserved separately; this proof does not change its result.')
    try:
        contract = intent(text, top, target)
        if contract is None:
            return proof, {}
        directory.mkdir()
        proof.update(source_sha256=file_digest(source), stream_sha256=file_digest(stream),
                     native_sha256=file_digest(native), target=target)
        ports, expected = contract
        sources = authenticate(technology)
        proof['model_sources'] = sources
        if (str(Path(magic_technology).resolve()) not in sources
                or (setup and str(Path(setup).resolve()) not in sources)):
            raise Unchecked('MOS grouping extraction/comparison technology is not a reviewed dependency.')
        from .silicon_flow import magic_script
        from .external_tools import extraction_commands
        commands, _ = extraction_commands('lvs')
        commands += 'ext2spice -o extracted.spice\nputs "STUDIO_MOS_CIF_SCALE [cif scale out]"\n'
        log = magic_script(magic, magic_technology, stream, top, ports, directory, commands)
        scales = re.findall(r'^STUDIO_MOS_CIF_SCALE (\S+)\s*$', log, re.M)
        raw_text = (directory / (top + '.ext')).read_text(encoding='utf-8')
        raw_scales = [r for r in logical_rows(raw_text) if r[0] == 'scale']
        if len(raw_scales) != 1 or len(raw_scales[0]) != 4:
            raise Unchecked('Missing or ambiguous native MOS coordinate scale.')
        scale = number(raw_scales[0][3]) * Decimal('.01')
        if scale <= 0 or len(scales) != 1 or abs(number(scales[0]) - scale) > Decimal('5e-10'):
            raise Unchecked('Native extraction and CIF coordinate scales disagree.')
        models = MODELS[target]
        raw = raw_channels(raw_text, models, scale, target)
        actual = Counter((*r['key'], r['width'], r['length']) for r in raw)
        for exporter,path in enumerate((Path(native), directory / 'extracted.spice')):
            exported = native_channels(path.read_text(encoding='utf-8'), top, models)
            if exported != actual and netgen and setup:
                mapping = correspondence(directory/('export-mapping-'+str(exporter)),netgen,path,directory/'extracted.spice',top,setup,ports)
                proof.setdefault('export_node_mapping',{})[str(exporter)] = mapping
                exported = remap(exported,mapping)
            if exported != actual:
                raise ValueError('Actual exported MOS channels differ from the located raw extraction.')
        observed, groups = geometry(stream, top, target, raw, scale)
        if observed != expected and netgen and setup and comparison:
            mapping = correspondence(directory/'source-mapping',netgen,comparison,directory/'extracted.spice',top,setup,ports)
            proof['source_node_mapping'] = mapping
            expected = remap(expected,mapping)
        if observed != expected:
            raise ValueError('MOS finger counts, diffusion groups or terminal-associated dimensions differ from schematic intent.')
        proof.update(status='PASS', channels=len(raw), groups=groups, native_grid_um=str(scale),
                     group_contracts=[dict(model=k[0],gate=k[1],body=k[2],drain_source=list(k[3]),
                                           channel_width_m=str(k[4]),length_m=str(k[5]),fingers=k[6],copies=v)
                                      for k,v in sorted(observed.items())])
        if any(file_digest(path) != expected_sha for path, expected_sha in sources.items()):
            raise ValueError('MOS model source changed during grouping verification.')
    except Unchecked as exc:
        proof.update(status='NOT_CHECKED', reason=str(exc))
    except InterruptedError:
        raise
    except (ValueError, OSError, DecimalException, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        proof.update(status='FAIL', reason=str(exc))
    directory.mkdir(exist_ok=True)
    proof['files'] = {p.relative_to(directory).as_posix(): file_digest(p)
                      for p in directory.rglob('*') if p.is_file()}
    atomic_write(directory / 'proof.json', json.dumps(proof, indent=2, allow_nan=False))
    files = {p.relative_to(directory.parent).as_posix(): file_digest(p)
             for p in directory.rglob('*') if p.is_file()}
    return proof, files
