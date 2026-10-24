"""Integrity checks for the public Open PDKs four-corner Nikon template.

This recognizes the *complete* public seal boundary before choosing windows.
It does not construct foundry masks or promote the 56 related catalog records.
Geometry below is transcribed from the pinned Magic source; independent Magic
exports, including complete generated seals, are the regression oracle.
"""
from fractions import Fraction
from pathlib import Path

from .model import file_digest

RECIPE = 'sky130-public-nikon-template-v1'
SOURCE = {
    'repository': 'fossi-foundation/open-pdks',
    'revision': '0ec4fa67eade28cd0a4352c04df981840809427b',
    'directory': 'sky130/custom/scripts/seal_ring_generator',
    'nikon_sha256': 'f0f30fb10c9f7a2fda02525ba7c5b45f0e2355bc76a9b969c287860fab0ee023',
    'technology_sha256': 'c980ded99aa919b9a750c6736fcc19198b03f11c26230c8484e8bbc538303c21',
    'generator_sha256': '711688fb70b8a844668b8ca3e1c2755d60b3182015ff18d44812c6b75d011cfd',
    'catalog_revision': '7198cf647113f56041e02abf3eb623692820c5e1',
}
# GDS mask purposes, not ordinary drawing layers. cctm1 in errors.csv is
# CTM1mk, whose published GDS-map name is ctm1 (35:0).
MASKS = {
    'cfom': (23, False, 1076), 'cdnm': (48, True, 1078),
    'cnwm': (21, False, 1080), 'chvtpm': (97, False, 1082),
    'clvtnm': (25, True, 1084), 'clvom': (46, False, 1086),
    'cp1m': (28, False, 1088), 'cntm': (27, False, 1090),
    'chvntm': (39, True, 1092), 'cldntm': (11, True, 1094),
    'cnpc': (49, True, 1096), 'cnsdm': (30, False, 1098),
    'cpsdm': (32, False, 1100), 'clicm1': (43, False, 1102),
    'cli1m': (56, False, 1104), 'cctm1': (35, False, 1106),
    'cmm1': (36, False, 1108), 'cviam': (40, False, 1110),
    'cmm2': (41, False, 1112), 'cnsm': (22, False, 1114),
    'cpdm': (37, True, 1116), 'cviam2': (44, False, 1118),
    'cmm3': (34, False, 1120), 'cviam3': (50, False, 1122),
    'cmm4': (51, False, 1124), 'cviam4': (58, False, 1126),
    'cmm5': (59, False, 1128), 'crpm': (96, False, 1130),
    # These are also present in the public template, without Nikon catalog rows.
    'ctunm': (20, True, None), 'conom': (88, False, None),
    'chvtrm': (98, False, None),
}
SCOPE = (
    'Compare actual mask geometry in all four public Nikon mark domains after exact recognition '
    'of one Open PDKs 6 um seal boundary. All 31 mask purposes are checked through hierarchy. '
    'The domain is the source octagon, not its bounding box; the surrounding PDM seal legitimately '
    'fills the four corners outside that octagon. No cell name grants acceptance. Missing seal '
    'context, unsupported data and mismatching marks remain explicit. A match proves public '
    'template integrity only: generated-mask definitions, required chip/scribe placement and '
    'foundry acceptance of the 56 associated catalog records remain unqualified.'
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def units(layout):
    """Exact nanometre conversion; never round a placement or a source vertex."""
    nm_per_unit = Fraction(str(layout.dbu)) * 1000
    require(nm_per_unit > 0, 'Invalid alignment database unit.')

    def convert(nm):
        value = Fraction(nm) / nm_per_unit
        require(value.denominator == 1, 'Alignment template is not representable on this database grid.')
        return int(value)

    return convert


def template(layout):
    """4 um octagon and its positive cross, in layout database units."""
    import klayout.db as k
    u = units(layout)
    domain = k.Region(k.Polygon([k.Point(u(x), u(y)) for x, y in (
        (0, 1170), (0, 2830), (1170, 4000), (2830, 4000),
        (4000, 2830), (4000, 1170), (2830, 0), (1170, 0))]))
    cross = k.Region()
    for box in ((1750, 2250, 2250, 3200), (800, 1750, 3200, 2250),
                (1750, 800, 2250, 1750)):
        cross.insert(k.Box(*(u(n) for n in box)))
    return domain, cross.merged()


def seal_region(layout, box):
    """The complete source 81:1 boundary: rectangle minus a chamfered hole."""
    import klayout.db as k
    u = units(layout); inset = u(6000); corner = u(12985)
    x, y, right, upper = box.left, box.bottom, box.right, box.top
    require(box.width() > 2*corner and box.height() > 2*corner,
            'Seal is too small for the public corner template.')
    hole = k.Region(k.Polygon([k.Point(a, b) for a, b in (
        (x+corner, y+inset), (right-corner, y+inset),
        (right-inset, y+corner), (right-inset, upper-corner),
        (right-corner, upper-inset), (x+corner, upper-inset),
        (x+inset, upper-corner), (x+inset, y+corner))]))
    return k.Region(box) - hole


def _raw(layout, pair):
    import klayout.db as k
    region = k.Region(); unsupported = 0; count = 0
    it = layout.top_cell().begin_shapes_rec(layout.layer(*pair))
    while not it.at_end():
        shape = it.shape(); transform = it.trans(); count += 1
        if (not (shape.is_box() or shape.is_polygon() or shape.is_simple_polygon())
                or transform.mag != 1 or transform.angle % 90 != 0):
            unsupported += 1
        else:
            polygon = shape.polygon
            if polygon.area() <= 0:
                unsupported += 1
            else:
                region.insert(polygon.transformed(transform))
        it.next()
    return region.merged(), dict(raw_shapes=count, unsupported=unsupported)


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells()) == 1, 'Alignment checking requires one top cell.')
    census = {}; regions = {}
    for name, pair in [('seal', (81, 1)), *((name, (v[0], 0)) for name, v in MASKS.items())]:
        regions[name], census[name] = _raw(layout, pair)
    result = dict(census=census, context='unrecognized-seal', bounds=None, marks=[])
    if any(row['unsupported'] for row in census.values()):
        result['context'] = 'unsupported-mask-data'; return result
    if regions['seal'].is_empty():
        result['context'] = 'missing-seal-context'; return result
    try:
        domain, cross = template(layout); u = units(layout)
        boundary = regions['seal']; box = boundary.bbox()
        if not (boundary ^ seal_region(layout, box)).is_empty():
            return result
    except ValueError:
        result['context'] = 'unsupported-template-grid-or-size'; return result
    result['context'] = 'public-four-corner-seal'
    result['bounds'] = [box.left, box.bottom, box.right, box.top]
    offsets = [(box.left+u(1000), box.bottom+u(1000)),
               (box.right-u(5000), box.bottom+u(1000)),
               (box.left+u(1000), box.top-u(5000)),
               (box.right-u(5000), box.top-u(5000))]
    for index, (x, y) in enumerate(offsets):
        window = domain.moved(x, y); plus = cross.moved(x, y); minus = window - plus
        rows = {}
        for name, (_, negative, _) in MASKS.items():
            actual = regions[name] & window
            expected_shape = minus if negative else plus
            opposite = plus if negative else minus
            missing = expected_shape - actual; extra = actual - expected_shape
            if actual.is_empty(): state = 'missing'
            elif (actual ^ opposite).is_empty(): state = 'reversed'
            elif missing.is_empty() and extra.is_empty(): state = 'match'
            else: state = 'damaged'
            # is_empty(), not rounded area, determines success at diagonal edges.
            rows[name] = dict(state=state, missing_area_dbu2=missing.area(),
                              extra_area_dbu2=extra.area())
        result['marks'].append(dict(index=index, origin_dbu=[x, y], masks=rows))
    return result


def expected(measurements, top, digest):
    require(isinstance(measurements, dict) and set(measurements) == {'census', 'context', 'bounds', 'marks'},
            'Incomplete alignment measurements.')
    census = measurements['census']
    require(isinstance(census, dict) and set(census) == {'seal', *MASKS}, 'Incomplete alignment census.')
    for row in census.values():
        require(isinstance(row, dict) and set(row) == {'raw_shapes', 'unsupported'} and
                all(type(n) is int and n >= 0 for n in row.values()) and
                row['unsupported'] <= row['raw_shapes'], 'Invalid alignment census.')
    context = measurements['context']; marks = measurements['marks']; bounds = measurements['bounds']
    require(context in ('missing-seal-context', 'unrecognized-seal', 'unsupported-mask-data',
                        'unsupported-template-grid-or-size', 'public-four-corner-seal'), 'Invalid alignment context.')
    if context == 'public-four-corner-seal':
        require(isinstance(bounds, list) and len(bounds) == 4 and all(type(n) is int for n in bounds)
                and bounds[0] < bounds[2] and bounds[1] < bounds[3], 'Invalid public seal bounds.')
        require(not any(row['unsupported'] for row in census.values()) and census['seal']['raw_shapes'] > 0,
                'Unsupported public seal census.')
        require(isinstance(marks, list) and len(marks) == 4, 'Expected four alignment marks.')
        for index, mark in enumerate(marks):
            require(isinstance(mark, dict) and set(mark) == {'index', 'origin_dbu', 'masks'} and
                    type(mark['index']) is int and mark['index'] == index, 'Invalid alignment mark order.')
            require(isinstance(mark['origin_dbu'], list) and len(mark['origin_dbu']) == 2 and
                    all(type(n) is int for n in mark['origin_dbu']), 'Invalid alignment origin.')
            require(isinstance(mark['masks'], dict) and mark['masks'].keys() == MASKS.keys(), 'Incomplete alignment masks.')
            for value in mark['masks'].values():
                require(isinstance(value, dict) and set(value) == {'state', 'missing_area_dbu2', 'extra_area_dbu2'} and
                        value['state'] in ('match', 'missing', 'reversed', 'damaged') and
                        all(type(value[n]) is int and value[n] >= 0 for n in ('missing_area_dbu2', 'extra_area_dbu2')),
                        'Invalid alignment mask measurement.')
                require(value['state'] != 'match' or value['missing_area_dbu2'] == value['extra_area_dbu2'] == 0,
                        'Contradictory alignment match.')
    else:
        require(marks == [] and bounds is None, 'Unrecognized seal cannot have accepted alignment windows.')
    matched = sum(v['state'] == 'match' for mark in marks for v in mark['masks'].values())
    findings = sum(v['state'] != 'match' for mark in marks for v in mark['masks'].values())
    rows = []
    for name, (_, _, first) in MASKS.items():
        if first is None: continue
        for offset, operation in ((0, 'polarity'), (1, 'presence')):
            rows.append(dict(id='r'+str(first+offset), rule=name+'.nikon', operation=operation,
                             disposition='unreviewed', reason='template-does-not-establish-foundry-mask-and-placement-policy'))
    return dict(schema=1, recipe=RECIPE, source=SOURCE, scope=SCOPE, top=top, gds_sha256=digest,
                qualified=False, chunk_complete=False, measurements=measurements,
                status=('template-mismatch' if findings else 'public-template-match') if marks else 'review-required',
                matched_mask_windows=matched, mismatched_mask_windows=findings, rows=rows, unreviewed=56)


def audit(path):
    import klayout.db as k
    path = Path(path); digest = file_digest(path); layout = k.Layout(); layout.read(str(path))
    result = expected(measure(layout), layout.top_cell().name, digest)
    require(file_digest(path) == digest, 'Layout changed during alignment checking.')
    return result


def evaluate(report, digest, top):
    require(isinstance(report, dict), 'Missing public alignment evidence. Recheck Finish.')
    require(report == expected(report.get('measurements'), top, digest),
            'Changed public alignment evidence. Recheck Finish.')
    return report


def validate_saved(report, path):
    actual = audit(path); evaluate(report, actual['gds_sha256'], actual['top'])
    require(report == actual, 'Public alignment evidence differs from actual layout. Recheck Finish.')
    return report
