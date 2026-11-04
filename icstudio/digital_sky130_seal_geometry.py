"""Check the published seal-marker origin and finite catalog width.

These checks do not establish that a layout contains a complete seal or chip.
Disconnected seal markers leave origin interpretation unresolved.
"""
from pathlib import Path
from .model import file_digest

RECIPE = 'sky130-seal-geometry-v1'
SOURCE = dict(revision='7198cf647113f56041e02abf3eb623692820c5e1', files={
    'docs/rules/errors.csv': 'd613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv': 'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/layers/table-c4b-layer-description.csv': 'dcfeb27a76171a67ca6a905bdc6deab0ca4d801f5970a76b1ce90aebb97bb21f',
    'docs/rules/periphery/p018-x_dotdash.csv': '0efaf5099bc464a782f0c05a2850673ae940272c16fa22ec519057171f2f1567'})
PAIR = (81, 1)
MIN_WIDTH_NM = 6000
CHECKS = {'r379': dict(rule='x.19', operation='lower-left-at-origin'),
          'r392': dict(rule='x.28', operation='minimum-width', minimum_nm=MIN_WIDTH_NM)}
SCOPE = ('Drawn areaid.sl on 81:1 is merged across reachable hierarchy. For a single connected marker, '
         'its lower-left bounding-box corner must be (0,0); disconnected markers require origin review. '
         'All merged seal geometry must meet the catalog minimum width of 6 um, including ring walls. '
         'The manual x.28 N/A is not treated as a waiver of finite error record r392. '
         'Absence is recorded separately and does not establish a complete seal or chip. '
         'No advanced-seal cell selector or diffusion-overlap exemption is inferred. '
         'Only Manhattan geometry, exact orthogonal paths and unit orthogonal hierarchy on a 1 nm grid are supported.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def expected(measurements, top, digest):
    m = measurements
    require(isinstance(m, dict) and set(m) == {'raw_shapes', 'components', 'area_nm2', 'bounds_nm', 'width_findings'},
            'Missing SKY130 seal measurements.')
    require(all(type(m[key]) is int and m[key] >= 0 for key in ('raw_shapes', 'components', 'area_nm2', 'width_findings')),
            'Invalid SKY130 seal counts.')
    require((m['raw_shapes'] > 0) == (m['components'] > 0) == (m['area_nm2'] > 0), 'Inconsistent SKY130 seal census.')
    bounds = m['bounds_nm']
    if m['components']:
        require(isinstance(bounds, list) and len(bounds) == 4 and all(type(v) is int for v in bounds) and
                bounds[0] < bounds[2] and bounds[1] < bounds[3] and
                m['area_nm2'] <= (bounds[2]-bounds[0])*(bounds[3]-bounds[1]), 'Invalid SKY130 seal bounds.')
    else:
        require(bounds is None and m['width_findings'] == 0, 'Unexpected empty SKY130 seal geometry.')
    origin = int(m['components'] == 1 and bounds[:2] != [0, 0])
    rows = []
    for key, check in CHECKS.items():
        count = origin if key == 'r379' else m['width_findings']
        state = ('absent-operand' if not m['components'] else 'unreviewed' if key == 'r379' and m['components'] != 1
                 else 'failed' if count else 'executed-reviewed')
        rows.append(dict(id=key, **check, components=m['components'], violations=count, disposition=state))
    violations = origin + m['width_findings']
    return dict(schema=1, recipe=RECIPE, source=SOURCE, scope=SCOPE, qualified=False, chunk_complete=False,
                top=top, gds_sha256=digest, measurements=m, rows=rows, violations=violations,
                unreviewed=sum(r['disposition'] == 'unreviewed' for r in rows),
                status='FAIL' if violations else 'selected-seal-geometry-reviewed')


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells()) == 1 and abs(layout.dbu-.001) < 1e-12,
            'SKY130 seal geometry requires one top and a 1 nm database unit.')
    top = layout.top_cell()
    for index in {top.cell_index(), *top.called_cells()}:
        for instance in layout.cell(index).each_inst():
            t = instance.cplx_trans
            require(t.mag == 1 and t.angle % 90 == 0, 'Unsupported SKY130 seal transform.')
    region = k.Region(); raw = 0
    iterator = top.begin_shapes_rec(layout.layer(*PAIR))
    while not iterator.at_end():
        shape = iterator.shape(); raw += 1
        if shape.is_path():
            path = shape.path; points = list(path.each_point())
            require(path.width > 0 and path.width % 2 == 0 and not path.is_round() and len(points) >= 2 and
                    all(a != b and (a.x == b.x or a.y == b.y) for a, b in zip(points, points[1:])),
                    'Inexact SKY130 seal path.')
            polygon = path.polygon()
        else:
            require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(), 'Unsupported SKY130 seal shape.')
            polygon = shape.polygon
        require(polygon.area() > 0 and all(e.p1.x == e.p2.x or e.p1.y == e.p2.y for e in polygon.each_edge()),
                'SKY130 seal geometry requires nonempty Manhattan polygons.')
        region.insert(polygon.transformed(iterator.trans())); iterator.next()
    # Corner contact must not collapse two independent seal markers into one.
    region.min_coherence = True
    region = region.merged()
    bounds = region.bbox()
    return dict(raw_shapes=raw, components=region.count(), area_nm2=region.area(),
                bounds_nm=None if region.is_empty() else [bounds.left, bounds.bottom, bounds.right, bounds.top],
                width_findings=region.width_check(MIN_WIDTH_NM).count())


def audit(path):
    import klayout.db as k
    path = Path(path); digest = file_digest(path); layout = k.Layout(); layout.read(str(path))
    report = expected(measure(layout), layout.top_cell().name, digest)
    require(file_digest(path) == digest, 'SKY130 layout changed during seal checking.')
    return report


def evaluate(report, digest, top):
    require(isinstance(report, dict), 'Missing SKY130 seal geometry evidence. Recheck Finish.')
    require(report == expected(report.get('measurements'), top, digest), 'Changed or incomplete SKY130 seal evidence. Recheck Finish.')
    require(report['violations'] == 0, 'SKY130 seal geometry checks failed.')
    return report


def validate_saved(report, path):
    actual = audit(path); evaluate(report, actual['gds_sha256'], actual['top'])
    require(report == actual, 'SKY130 seal evidence differs from the actual layout. Recheck Finish.')
    return report
