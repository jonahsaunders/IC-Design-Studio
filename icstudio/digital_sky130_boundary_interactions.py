"""Check explicit drawn-layer module crossings and seal-ring interactions.

These checks do not establish that a chip has the required frame or seal ring.
Enclosure, spacing, mask generation and package-layer aliases remain separate.
"""
from pathlib import Path

from .model import file_digest

RECIPE = 'sky130-boundary-interactions-v1'
SOURCE = dict(revision='7198cf647113f56041e02abf3eb623692820c5e1', files={
    'docs/rules/errors.csv': 'd613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv': 'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    'docs/rules/layers/table-c4b-layer-description.csv': 'dcfeb27a76171a67ca6a905bdc6deab0ca4d801f5970a76b1ce90aebb97bb21f',
    'docs/rules/periphery/p018-x_dotdash.csv': '0efaf5099bc464a782f0c05a2850673ae940272c16fa22ec519057171f2f1567'})
LAYERS = dict(nwell=(64,20), diff=(65,20), dnwell=(64,18), tap=(65,44), lvtn=(125,44),
    hvtp=(78,44), hvi=(75,20), tunm=(80,20), poly=(66,20), npc=(95,20), nsdm=(93,44),
    psdm=(94,20), licon1=(66,44), li1=(67,20), mcon=(67,44), met1=(68,20), via=(68,44),
    met2=(69,20), vhvi=(74,21), via2=(69,44), met3=(70,20), via3=(70,44), met4=(71,20),
    via4=(71,44), met5=(72,20), nsm=(61,20), pad=(76,20), ldntm=(11,44), hvntm=(125,20),
    pnp=(82,44), capacitor=(82,64), ncm=(92,44), inductor=(82,24), rpm=(86,20), hvtr=(18,20))
BOUNDARIES = dict(module=(81,10), seal=(81,1))
TEXT_ALLOWED = frozenset(('diff','poly','li1','met1','met2','met3','met4','met5','pad'))
# Preserve the literal catalog IDs; five package operands lack published drawing purposes.
MODULE_IDS = (*range(1407,1436), 1437,1438,1439,1441,1443,1444)
CHECKS = {'r'+str(i): dict(rule='scribe.7', target=name, boundary='module', operation='straddle')
          for i,name in zip(MODULE_IDS, LAYERS)}
CHECKS['r381'] = dict(rule='x.23b', target='diff', boundary='seal', operation='straddle')
CHECKS.update({'r'+str(382+i): dict(rule='x.23c', target=name, boundary='seal', operation='overlap')
              for i,name in enumerate(('tap','poly','li1','met1','met2','met3','met4','met5'))})
SCOPE = ('Thirty-five published drawn-layer purposes are checked for straddling each supplied module-cut '
         'polygon on 81:10. Diffusion is checked for straddling seal 81:1; tap, poly, li1 and met1-met5 '
         'are checked for positive-area seal overlap. Targets are merged connected regions. Boundary polygons '
         'must be disjoint and non-touching so merging cannot hide an internal boundary. Manhattan polygons '
         'and exact orthogonal paths are supported. Missing boundary geometry does not establish chip/frame '
         'completeness or waive any enclosure or spacing requirement. Five package-layer scribe records remain separate.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def expected(measurements, top, digest):
    require(isinstance(measurements, dict) and set(measurements) == {'layers','violations'},
            'Missing SKY130 boundary-interaction measurements.')
    layers, counts = measurements['layers'], measurements['violations']
    require(isinstance(layers, dict) and layers.keys() == (LAYERS | BOUNDARIES).keys() and
            isinstance(counts, dict) and counts.keys() == CHECKS.keys(), 'Incomplete SKY130 boundary-interaction counts.')
    for name, values in layers.items():
        require(isinstance(values, dict) and set(values) == {'raw_shapes','texts','components'} and
                all(type(v) is int and v >= 0 for v in values.values()) and
                values['texts'] <= values['raw_shapes'] and
                (values['components'] > 0) == (values['raw_shapes'] > values['texts']) and
                (values['texts'] == 0 or name in TEXT_ALLOWED), 'Invalid SKY130 boundary-interaction census.')
    require(all(type(v) is int and v >= 0 for v in counts.values()), 'Invalid SKY130 boundary-interaction findings.')
    rows = []
    for key, check in CHECKS.items():
        target, boundary = (layers[check[k]]['components'] for k in ('target','boundary'))
        require(counts[key] <= target*boundary, 'Inconsistent SKY130 boundary-interaction findings.')
        rows.append(dict(id=key, **check, target_components=target, boundary_components=boundary,
                         violations=counts[key], disposition='failed' if counts[key] else
                         'absent-operand' if not target else 'executed-reviewed'))
    total = sum(counts.values())
    return dict(schema=1, recipe=RECIPE, source=SOURCE, scope=SCOPE, qualified=False, chunk_complete=False,
                top=top, gds_sha256=digest, measurements=measurements, rows=rows, violations=total,
                status='FAIL' if total else 'selected-boundary-interactions-pass')


def measure(layout):
    import klayout.db as k
    require(len(layout.top_cells()) == 1 and abs(layout.dbu-.001) < 1e-12,
            'SKY130 boundary interactions require one top and a 1 nm database unit.')
    top = layout.top_cell()
    for index in {top.cell_index(), *top.called_cells()}:
        for instance in layout.cell(index).each_inst():
            t = instance.cplx_trans
            require(t.mag == 1 and t.angle % 90 == 0, 'Unsupported SKY130 boundary-interaction transform.')
    regions, census = {}, {}
    for name, pair in (LAYERS | BOUNDARIES).items():
        polygons = []; raw = texts = 0
        iterator = top.begin_shapes_rec(layout.layer(*pair))
        while not iterator.at_end():
            shape = iterator.shape(); raw += 1
            if shape.is_text() and name in TEXT_ALLOWED:
                texts += 1; iterator.next(); continue
            if shape.is_path():
                path = shape.path; points = list(path.each_point())
                require(path.width > 0 and path.width % 2 == 0 and not path.is_round() and len(points) >= 2 and
                        all(a != b and (a.x == b.x or a.y == b.y) for a,b in zip(points,points[1:])),
                        'Inexact SKY130 boundary-interaction path: '+name)
                polygon = path.polygon()
            else:
                require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(),
                        'Unsupported SKY130 boundary-interaction shape: '+name)
                polygon = shape.polygon
            require(polygon.area() > 0 and all(e.p1.x == e.p2.x or e.p1.y == e.p2.y for e in polygon.each_edge()),
                    'SKY130 boundary interactions require nonempty Manhattan polygons: '+name)
            polygons.append(polygon.transformed(iterator.trans())); iterator.next()
        region = k.Region(polygons)
        if name in BOUNDARIES:
            # Keep each marker, including its holes. Reject duplicate, touching or
            # overlapping markers instead of dissolving a meaningful module seam.
            prior = k.Region()
            for polygon in polygons:
                require(prior.interacting(k.Region(polygon)).is_empty(),
                        'Touching or overlapping SKY130 boundary polygons require review: '+name)
                prior.insert(polygon)
            regions[name] = polygons
        else:
            regions[name] = list(region.merged().each())
        census[name] = dict(raw_shapes=raw, texts=texts, components=len(regions[name]))
    counts = {}
    for key, check in CHECKS.items():
        count = 0
        for boundary in regions[check['boundary']]:
            area = k.Region(boundary)
            for polygon in regions[check['target']]:
                target = k.Region(polygon)
                if not (target & area).is_empty():
                    count += int(check['operation'] == 'overlap' or not (target-area).is_empty())
        counts[key] = count
    return dict(layers=census, violations=counts)


def audit(path):
    import klayout.db as k
    path = Path(path); digest = file_digest(path); layout = k.Layout(); layout.read(str(path))
    report = expected(measure(layout), layout.top_cell().name, digest)
    require(file_digest(path) == digest, 'SKY130 layout changed during boundary-interaction checking.')
    return report


def evaluate(report, digest, top):
    require(isinstance(report, dict), 'Missing SKY130 boundary-interaction evidence. Recheck Finish.')
    require(report == expected(report.get('measurements'), top, digest),
            'Changed or incomplete SKY130 boundary-interaction evidence. Recheck Finish.')
    require(report['violations'] == 0, 'SKY130 boundary-interaction checks failed.')
    return report


def validate_saved(report, path):
    actual = audit(path)
    evaluate(report, actual['gds_sha256'], actual['top'])
    require(report == actual, 'SKY130 boundary-interaction evidence differs from the actual layout. Recheck Finish.')
    return report
