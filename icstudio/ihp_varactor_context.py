"""Public SVaricap recognition for the additional native NPN geometry check.

This context is used only alongside both complete public IHP geometry decks.
It keeps their whole-polygon SVaricap recognition when Magic's bounded import
growth would split a large device. Original physical masks stay unchanged.
The derived rule files retain their Apache-2.0 notices and exact source hashes.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath

from .model import atomic_write, file_digest

SOURCES = {
    'icstudio-ihp-sg13g2.tech': '394b38e5d05bf999c1cdcd15df2672463902f51762edaa90052f455866bc5e3e',
    'ihp-sg13g2-cifin.tech': 'd1ac75da97a8ef3c944f1088086f8e47a46f5a04024d3570b93e2e2617587ec1',
    'icstudio-ihp-sg13g2-cifout.tech': '74b6df465b9d547c72deb2e423dbeccf63b68d271e304ffadb65a9b81daa74f2',
    'ihp-sg13g2-drc.tech': 'a0eb3c22f8e67945bfc00d9138e3d8b85611b9f02a4016ccf66dade734554581',
}
MARKERS = ((250, 0), (251, 0))
# Native edge checks inspect both lattice positions adjacent to an edge.
# This closes the nonphysical mask-hint interval; no mask or limit is grown.
CLOSED = '''snap internal
if {abs([cif scale out] - 0.005) > 0.000001} {error "Unqualified native varactor context grid"}
set studio_hints [property MASKHINTS_STUDIO_VARAREA]
if {[llength $studio_hints] == 0 || [llength $studio_hints] % 4 != 0} {error "Missing native varactor context"}
set studio_closed {}
foreach {a b c d} $studio_hints {
    lappend studio_closed [expr {$a-1}] [expr {$b-1}] [expr {$c+1}] [expr {$d+1}]
}
property MASKHINTS_STUDIO_VARCLOSED $studio_closed
'''


def corrected(name, content):
    if name not in SOURCES or hashlib.sha256(content).hexdigest() != SOURCES[name]:
        raise ValueError('Public varactor context requires the exact locked native rule sources.')
    text = content.decode('utf-8')
    changes = []
    if name == 'ihp-sg13g2-cifin.tech':
        changes = [
            (' templayer vararea POLY', ' templayer original_vararea POLY'),
            (' layer dnwell DNWELL\n and-not vararea',
             ' templayer vararea original_vararea\n or STUDIO_VARAREA\n\n'
             ' templayer varwell STUDIO_VARWELL\n\n'
             ' templayer restore_varwell DNWELL\n and varwell\n\n'
             ' layer dnwell DNWELL\n and-not vararea\n or restore_varwell'),
            (' calma NWELL 31 0',
             ' calma STUDIO_VARAREA 250 0\n calma STUDIO_VARWELL 251 0\n'
             ' templayer studio_vararea STUDIO_VARAREA\n mask-hints STUDIO_VARAREA\n\n'
             ' templayer studio_varwell STUDIO_VARWELL\n mask-hints STUDIO_VARWELL\n\n'
             ' calma NWELL 31 0'),
        ]
    if name == 'icstudio-ihp-sg13g2-cifout.tech':
        original = (' templayer tap_far_from_tap_contact psd,nsd,ptap,ntap,hvpsd,hvnsd,hvptap,hvntap\n'
                    '\tand-not tap_contact_halo')
        changes = [(original, ' templayer studio_vararea\n\tmask-hints STUDIO_VARAREA\n\n'
                    + original + '\n\tand-not studio_vararea')]
    for before, after in changes:
        if text.count(before) != 1:
            raise ValueError('Missing or ambiguous native varactor correction operand.')
        text = text.replace(before, after)
    if name == 'ihp-sg13g2-drc.tech':
        for rule, marker in [('NW.c1', 'STUDIO_VARCLOSED'), ('NW.f', 'STUDIO_VARCLOSED'), ('NBL.f', 'STUDIO_VARWELL')]:
            rows = text.splitlines(keepends=True)
            matches = [i for i, line in enumerate(rows) if '('+rule+')' in line]
            if len(matches) != 1:
                raise ValueError('Missing or ambiguous native varactor applicability rule.')
            end = start = matches[0]
            while start and rows[start-1].rstrip().endswith('\\'): start -= 1
            rows.insert(end+1, ' exemption none\n')
            rows.insert(start, ' exemption '+marker+'\n')
            text = ''.join(rows)
    if text != content.decode('utf-8'):
        text = ('# Modified by IC Design Studio: public SVaricap recognition context.\n'
                '# Original Apache-2.0 license and notices are retained below.\n' + text)
    return text.encode('utf-8')


def recognize(layout, cell):
    """Use public gate/active/text recognition; unsupported geometry falls back."""
    import klayout.db as k
    def region(layer):
        index = layout.find_layer(layer, 0)
        return k.Region(cell.begin_shapes_rec(index)).merged() if index is not None else k.Region()
    active, well, buried, poly, oxide, transistor = [region(i) for i in (1, 31, 32, 5, 44, 26)]
    labels = []; index = layout.find_layer(63, 0)
    if index is not None:
        iterator = cell.begin_shapes_rec(index)
        while not iterator.at_end():
            shape = iterator.shape()
            if shape.is_text() and shape.text.string.lower() == 'svaricap':
                labels.append(iterator.trans()*shape.text.trans.disp)
            iterator.next()
    gates = poly & well & buried; recognized = k.Region()
    for polygon in active.each():
        if not (k.Region(polygon) & gates).is_empty() and any(polygon.inside(p) for p in labels):
            recognized.insert(polygon)
    if recognized.is_empty(): return None
    selected_well = well.interacting(recognized)
    if not (recognized - oxide).is_empty(): return None
    if not ((recognized | selected_well).sized(5) & transistor).is_empty():
        raise ValueError('Varactor context must be separate from every native NPN TRANS region.')
    for polygon in (recognized | selected_well).each():
        for edge in polygon.each_edge():
            if (edge.dx() and edge.dy()) or any(value % 5 for value in (edge.p1.x, edge.p1.y, edge.p2.x, edge.p2.y)):
                return None
    return recognized, selected_well


def prepare(source, top, technology, assets, expected_hashes, destination):
    """Derive a retained verification copy; never alter the input or its PDK."""
    import klayout.db as k
    from .ihp_klayout_drc import assets as public_assets, COMMIT, LOCK_SHA256
    from .stream_contract import compare
    source = Path(source); technology = Path(technology); destination = Path(destination)
    before = file_digest(source); layout = k.Layout(); layout.read(str(source)); cell = layout.cell(top)
    if cell is None: raise ValueError('Missing public varactor context top cell.')
    if layout.dbu != .001: return None
    regions = recognize(layout, cell)
    if regions is None: return None
    if any(layout.find_layer(*pair) is not None for pair in MARKERS):
        raise ValueError('Input collides with private varactor verification markers.')
    public_assets()  # Authenticate the complete public definitions, including notices.
    prefix = 'ihp-magic/'
    sources = {name[len(prefix):]: Path(path) for name, path in assets.items() if name.startswith(prefix)}
    if set(SOURCES) - set(sources) or sources.get(technology.name) != technology:
        raise ValueError('Varactor context needs the complete validated native dependency closure.')
    prepared = {}
    for name, path in sources.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe native varactor dependency path.')
        content = path.read_bytes(); sha = hashlib.sha256(content).hexdigest()
        if expected_hashes.get(str(path)) != sha:
            raise ValueError('Native dependency changed before varactor context preparation.')
        prepared[name] = corrected(name, content) if name in SOURCES else content
    destination.mkdir(parents=True, exist_ok=False); rule_root = destination/'rules'
    for name, data in prepared.items():
        target = rule_root/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    for pair, region in zip(MARKERS, regions): cell.shapes(layout.layer(*pair)).insert(region)
    private = destination/'private-input.gds'; layout.write(str(private))
    reread = k.Layout(); reread.read(str(private))
    for pair in MARKERS: reread.delete_layer(reread.find_layer(*pair))
    restored = destination/'physical-readback.gds'; reread.write(str(restored))
    comparison = compare(source, restored, text_presentation=True)
    if file_digest(source) != before: raise ValueError('Layout changed while preparing varactor context.')
    proof = dict(schema=1, applied=True, source_sha256=before, private_input_sha256=file_digest(private),
                 public_source_commit=COMMIT, public_source_lock_sha256=LOCK_SHA256,
                 physical_readback_sha256=file_digest(restored), comparison=comparison,
                 markers=[list(pair) for pair in MARKERS], native_grid_nm=5, marker_edge_closure_grid_steps=1,
                 recognized_active=str(regions[0]), recognized_well=str(regions[1]),
                 sources={name: file_digest(path) for name, path in sources.items()},
                 derived={name: file_digest(rule_root/name) for name in prepared},
                 scope='Additional full native NPN check with public SVaricap context. Both complete public geometry decks remain mandatory; no physical changes, threshold changes or filtered findings.')
    atomic_write(destination/'proof.json', json.dumps(proof, indent=2))
    return rule_root/technology.name, private, CLOSED, proof
