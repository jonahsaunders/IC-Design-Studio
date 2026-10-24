"""Execute selected VPP geometry checks and measure density operands.

Density observations do not resolve the unpublished special-cell selectors.
They never confer density acceptance, even when every observed ratio is within
the ordinary threshold. Other VPP geometry and connectivity remain separate.
"""
from pathlib import Path

from .model import file_digest

RECIPE = 'sky130-vpp-selected-geometry-v1'
SOURCE = dict(revision='7198cf647113f56041e02abf3eb623692820c5e1', files={
    'docs/rules/errors.csv': 'd613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv': 'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/periphery/p037-vpp_dotdash.csv': '1836055617d1b99c5d84028dfa6ff43555aaf7b9249c6747415ef5e6c0be9ef6'})
LAYERS = dict(capacitor=(82, 64), nwell=(64, 20), dnwell=(64, 18),
              poly=(66, 20), diff=(65, 20), met3=(70, 20), met4=(71, 20), met5=(72, 20))
CHECKS = {'r1145': 'vpp.1', 'r1151': 'vpp.4', 'r1152': 'vpp.4', 'r1153': 'vpp.8'}
LIMITS = {'met3': (1, 4, 'maximum'), 'met4': (3, 10, 'maximum'),
          'met5': (2, 5, 'maximum'), 'gate': (87, 100, 'minimum')}
SCOPE = ('Selected rules on merged capacitor drawing 82:64: 1.43 um minimum width, '
         'no straddling nwell or dnwell, and 1.5 um enclosure for capacitors overlapping nwell. '
         'An outside-nwell capacitor leaves the enclosure requirement unreviewed; missing nwell never proves exemption. '
         'Manhattan polygons and exact orthogonal paths. '
         'Density operands are measured per connected capacitor region without selecting device '
         'exceptions or claiming density acceptance. Other VPP rules remain separate.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def expected(measured, top, digest):
    require(isinstance(measured, dict) and set(measured) == {'raw_shapes', 'components', 'violations', 'density', 'nwell_context'},
            'Missing SKY130 VPP measurements.')
    raw, counts, components = measured['raw_shapes'], measured['violations'], measured['components']
    require(isinstance(raw, dict) and raw.keys() == LAYERS.keys() and
            isinstance(counts, dict) and counts.keys() == CHECKS.keys() and
            all(type(v) is int and v >= 0 for v in [components, *raw.values(), *counts.values()]),
            'Incomplete or invalid SKY130 VPP measurement counts.')
    require(isinstance(measured['density'], list) and len(measured['density']) == components and
            (raw['capacitor'] > 0) == (components > 0), 'Inconsistent SKY130 capacitor census.')
    context = measured['nwell_context']
    require(isinstance(context, dict) and set(context) == {'contained', 'outside', 'straddling'} and
            all(type(v) is int and v >= 0 for v in context.values()) and sum(context.values()) == components,
            'Invalid SKY130 VPP nwell context.')
    observations = []
    for item in measured['density']:
        require(isinstance(item, dict) and set(item) == {'bounds_nm', 'area_nm2', 'covered_nm2'},
                'Incomplete SKY130 VPP density operands.')
        bounds, area, covered = item['bounds_nm'], item['area_nm2'], item['covered_nm2']
        require(isinstance(bounds, list) and len(bounds) == 4 and all(type(v) is int for v in bounds) and
                bounds[0] < bounds[2] and bounds[1] < bounds[3] and type(area) is int and
                0 < area <= (bounds[2]-bounds[0])*(bounds[3]-bounds[1]) and
                isinstance(covered, dict) and covered.keys() == LIMITS.keys() and
                all(type(v) is int and 0 <= v <= area for v in covered.values()),
                'Invalid SKY130 VPP density areas.')
        observations.append(dict(bounds_nm=bounds, area_nm2=area, ratios={
            name: dict(numerator_nm2=covered[name], denominator_nm2=area,
                       ordinary_limit=[n, d], comparison=kind,
                       within_ordinary_limit=(covered[name]*d <= area*n if kind == 'maximum'
                                              else covered[name]*d >= area*n))
            for name, (n, d, kind) in LIMITS.items()}))
    require(components > 0 or not any(counts.values()), 'Absent VPP geometry has nonzero findings.')
    total = sum(counts.values())
    return dict(schema=1, recipe=RECIPE, source=SOURCE, scope=SCOPE, qualified=False, chunk_complete=False,
                top=top, gds_sha256=digest, measurements=measured, violations=total,
                status='FAIL' if total else 'review-required' if context['outside'] else 'selected-vpp-geometry-pass',
                rows=[dict(id=key, rule=rule, violations=counts[key],
                           disposition=('absent-operand' if components == 0 else
                                        'failed' if counts[key] else
                                        'unreviewed' if key == 'r1153' and context['outside'] else 'executed-reviewed'))
                      for key, rule in CHECKS.items()],
                density=dict(status='measurement-only', acceptance_established=False, observations=observations,
                             unresolved_rules=['vpp.5a', 'vpp.5b', 'vpp.5c', 'vpp.11']))


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells()) == 1 and abs(layout.dbu-.001) < 1e-12,
            'SKY130 VPP checks require one top and a 1 nm database unit.')
    top = layout.top_cell()
    for index in {top.cell_index(), *top.called_cells()}:
        for instance in layout.cell(index).each_inst():
            t = instance.cplx_trans
            require(t.mag == 1 and t.angle % 90 == 0, 'Unsupported SKY130 VPP hierarchy transform.')
    regions, raw = {}, {}
    for name, pair in LAYERS.items():
        region = k.Region(); raw[name] = 0
        iterator = top.begin_shapes_rec(layout.layer(*pair))
        while not iterator.at_end():
            shape = iterator.shape(); raw[name] += 1
            # These published purposes combine drawing and text. Labels have
            # no area and must not become either metal or a geometry failure.
            if shape.is_text() and name in ('poly', 'met3', 'met4', 'met5'):
                iterator.next(); continue
            if shape.is_path():
                path = shape.path; points = list(path.each_point())
                require(path.width > 0 and path.width % 2 == 0 and not path.is_round() and len(points) >= 2 and
                        all(a != b and (a.x == b.x or a.y == b.y) for a, b in zip(points, points[1:])),
                        'SKY130 VPP path cannot be converted without boundary rounding: '+name)
                polygon = path.polygon()
            else:
                require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(),
                        'SKY130 VPP operands require polygons: '+name)
                polygon = shape.polygon
            require(all(edge.p1.x == edge.p2.x or edge.p1.y == edge.p2.y for edge in polygon.each_edge()),
                    'SKY130 VPP operands require Manhattan boundaries: '+name)
            require(polygon.area() > 0, 'Empty SKY130 VPP operand.')
            region.insert(polygon.transformed(iterator.trans())); iterator.next()
        regions[name] = region.merged()
    cap, well, deep = (regions[name] for name in ('capacitor', 'nwell', 'dnwell'))
    polygons = sorted(cap.each(), key=lambda p: (p.bbox().left, p.bbox().bottom, p.bbox().right, p.bbox().top, p.to_s()))
    def straddles(region):
        return sum(not (k.Region(p) & region).is_empty() and not (k.Region(p)-region).is_empty()
                   for p in polygons)
    selected = k.Region(); context = dict(contained=0, outside=0, straddling=0)
    for p in polygons:
        region = k.Region(p)
        if (region & well).is_empty(): context['outside'] += 1
        else:
            selected.insert(p)
            context['contained' if (region-well).is_empty() else 'straddling'] += 1
    counts = dict(r1145=cap.width_check(1430).count(), r1151=straddles(well), r1152=straddles(deep),
                  r1153=(selected-well).count()+well.enclosing_check(selected, 1500).count())
    density = []
    for polygon in polygons:
        region = k.Region(polygon); bounds = polygon.bbox()
        coverage = {name: (region & regions[name]).area() for name in ('met3', 'met4', 'met5')}
        coverage['gate'] = (region & regions['poly'] & regions['diff']).area()
        density.append(dict(bounds_nm=[bounds.left, bounds.bottom, bounds.right, bounds.top],
                            area_nm2=region.area(), covered_nm2=coverage))
    return dict(raw_shapes=raw, components=len(polygons), violations=counts, density=density, nwell_context=context)


def audit(path):
    import klayout.db as k
    path = Path(path); digest = file_digest(path); layout = k.Layout(); layout.read(str(path))
    measured = measure(layout)
    report = expected(measured, layout.top_cell().name, digest)
    require(file_digest(path) == digest, 'SKY130 layout changed during VPP measurement.')
    return report


def evaluate(report, digest, top):
    require(isinstance(report, dict), 'Missing SKY130 VPP evidence. Recheck Finish.')
    require(report == expected(report.get('measurements'), top, digest),
            'Changed or incomplete SKY130 VPP evidence. Recheck Finish.')
    require(report['violations'] == 0, 'SKY130 VPP geometry checks failed.')
    return report


def validate_saved(report, path):
    actual = audit(path)
    evaluate(report, actual['gds_sha256'], actual['top'])
    require(report == actual, 'SKY130 VPP evidence differs from the actual layout. Recheck Finish.')
    return report
