"""Exact waffle-drop density predicates on caller-selected full windows.

This adds numerical coverage without inventing a foundry window lattice,
cell exclusion policy, or final-mask construction. Nonempty drop layers
remain unreviewed for acceptance; the numerical observations are separate.
"""
from pathlib import Path

from .model import file_digest

RECIPE = 'sky130-waffle-window-predicates-v1'
WINDOW_NM = 700_000
AREA_NM2 = WINDOW_NM ** 2
LAYERS = {
    'm1': dict(drop=(62, 24), drawing=(68, 20), fill=(36, 28)),
    'm2': dict(drop=(105, 52), drawing=(69, 20), fill=(41, 28)),
    'm3': dict(drop=(107, 24), drawing=(70, 20), fill=(34, 28)),
    'm4': dict(drop=(112, 4), drawing=(71, 20), fill=(51, 28)),
}
# Every predicate is independent: the source says ANY. At a shared endpoint
# both adjacent bands apply, and at 100% the 70% requirement also applies.
BANDS = ((100, 100, 70), (80, 100, 65), (60, 80, 60),
         (50, 60, 50), (40, 50, 40), (30, 40, 30))
SOURCE = dict(revision='7198cf647113f56041e02abf3eb623692820c5e1', files={
    'docs/rules/periphery/p038-m1_dotdash.csv': '3cd3bb93c13b72f75113ac4fa78e344ae185cf758c489858323fddc0273a5675',
    'docs/rules/periphery/p040-m2_dotdash.csv': 'edd28e2d9e3740575bf9e44df7dd31ab6443b376ff6e8978c2b9210647a5d24e',
    'docs/rules/periphery/p042-m3_dotdash.csv': '6dc78a855fd347f0c9c0625316cbbadd7c2923a14b5552ce505b62df12639f55',
    'docs/rules/periphery/p044-m4_dotdash.csv': 'f25981fd9accb2426482320aa5c648c718f418c7a17546de0265c122565cef06',
    'docs/rules/errors.csv': 'd613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
    'docs/rules/gds_layers.csv': 'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5'},
    native_fill=dict(path='tests/fixtures/sky130-metal-width-native.tech',
        sha256='5ee53b96094fe144145bf1216627672747366ec9bef9f2f848304a9a0c77427e'))
SCOPE = ('Six independent required waffle-drop predicates per metal m1-m4, with exact integer-area '
    'comparisons on explicitly supplied 700 by 700 um windows. Drawing and native fill are unioned '
    'before intersection; holes, overlapping shapes and hierarchy are preserved. These are numerical '
    'observations of drawn-plus-fill metal, not an oxide metric or acceptance of a generated final mask. '
    'No window origin, step, boundary clipping or small-cell exclusion is inferred. Nonempty drop '
    'operands remain unreviewed even when every sampled window passes, or no full window is supplied. '
    'Only an empty raw drop layer proves the corresponding 12 catalog antecedents absent everywhere. '
    'No previously absent catalog records become newly executed from these observations.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def predicates(drop_area_nm2, metal_area_nm2, area_nm2=AREA_NM2):
    require(type(area_nm2) is int and area_nm2 == AREA_NM2 and
            all(type(n) is int and 0 <= n <= area_nm2 for n in (drop_area_nm2, metal_area_nm2)),
            'Density predicates require exact nonnegative areas in a full 700 um window.')
    result = []
    for low, high, minimum in BANDS:
        selected = low * area_nm2 <= 100 * drop_area_nm2 <= high * area_nm2
        result.append(dict(coverage_percent=[low, high], minimum_metal_percent=minimum,
                           antecedent=selected,
                           below_minimum=100 * metal_area_nm2 < minimum * area_nm2,
                           triggered=selected and 100 * metal_area_nm2 < minimum * area_nm2))
    return result


def validate_windows(windows):
    require(isinstance(windows, list), 'Explicit density windows must be a list.')
    for bounds in windows:
        require(isinstance(bounds, list) and len(bounds) == 4 and all(type(n) is int for n in bounds) and
                bounds[2] - bounds[0] == bounds[3] - bounds[1] == WINDOW_NM,
                'Density windows must be exact full 700 um squares in integer nm; no edge clips.')
    require(len({tuple(b) for b in windows}) == len(windows), 'Duplicate density windows.')


def expected(measurements, top, digest):
    require(isinstance(measurements, dict) and set(measurements) == {'windows_nm', 'layers'},
            'Missing waffle-window measurements.')
    windows = measurements['windows_nm']; validate_windows(windows)
    layers = measurements['layers']
    require(isinstance(layers, dict) and layers.keys() == LAYERS.keys(), 'Incomplete density layer census.')
    rows, observations = [], {}
    for index, name in enumerate(LAYERS):
        layer = layers[name]
        require(isinstance(layer, dict) and set(layer) == {'raw_drop_shapes', 'drop_texts', 'samples'} and
                all(type(layer[key]) is int and layer[key] >= 0 for key in ('raw_drop_shapes', 'drop_texts')) and
                layer['drop_texts'] <= layer['raw_drop_shapes'] and isinstance(layer['samples'], list) and
                len(layer['samples']) == len(windows), 'Invalid density operand census.')
        observations[name] = []
        for bounds, sample in zip(windows, layer['samples']):
            require(isinstance(sample, dict) and set(sample) == {'drop_area_nm2', 'metal_area_nm2'},
                    'Incomplete density window areas.')
            values = predicates(**sample)
            require(layer['raw_drop_shapes'] > 0 or sample['drop_area_nm2'] == 0,
                    'An absent drop layer cannot have area.')
            observations[name].append(dict(bounds_nm=bounds, area_nm2=AREA_NM2, **sample, predicates=values))
        absent = layer['raw_drop_shapes'] == 0
        for offset in range(6):
            for key in (f'r{1210+6*index+offset}', f's{44+6*index+offset}'):
                rows.append(dict(id=key, rule=f'{name}.x.1',
                    disposition='absent-operand' if absent else 'unreviewed',
                    reason='empty-raw-waffle-drop' if absent else 'window-and-cell-policy-unqualified'))
    pending = sum(r['disposition'] == 'unreviewed' for r in rows)
    return dict(schema=1, recipe=RECIPE, source=SOURCE, scope=SCOPE, qualified=False, chunk_complete=False,
        acceptance_established=False, top=top, gds_sha256=digest, measurements=measurements,
        rows=rows, unreviewed=pending, observations=observations,
        triggered_observations=sum(p['triggered'] for values in observations.values() for w in values for p in w['predicates']),
        window_policy='caller-selected-full-windows' if windows else 'not-supplied',
        status='review-required' if pending else 'waffle-antecedents-absent')


def measure(layout, windows=None):
    import klayout.db as k
    windows = [] if windows is None else windows; validate_windows(windows)
    require(len(layout.top_cells()) == 1, 'Density requires one top cell.')
    top = layout.top_cell()
    if windows:
        require(abs(layout.dbu - .001) < 1e-12, 'Density area measurement requires 1 nm database units.')
        for index in {top.cell_index(), *top.called_cells()}:
            for instance in layout.cell(index).each_inst():
                transform = instance.cplx_trans
                require(transform.mag == 1 and transform.angle % 90 == 0, 'Unsupported density transform.')

    def region(pair, drop=False):
        result = k.Region(); it = top.begin_shapes_rec(layout.layer(*pair))
        while not it.at_end():
            shape = it.shape()
            if shape.is_text():
                require(not drop, 'Text on a waffle-drop operand cannot establish its area.')
                it.next(); continue
            if shape.is_path():
                path = shape.path; points = list(path.each_point())
                require(path.width > 0 and path.width % 2 == 0 and not path.is_round() and len(points) >= 2 and
                        all(a != b and (a.x == b.x or a.y == b.y) for a, b in zip(points, points[1:])),
                        'Inexact density path.')
                polygon = path.polygon()
            else:
                require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(), 'Unsupported density shape.')
                polygon = shape.polygon
            require(polygon.area() > 0 and all(e.p1.x == e.p2.x or e.p1.y == e.p2.y for e in polygon.each_edge()),
                    'Density area requires nonempty Manhattan geometry.')
            result.insert(polygon.transformed(it.trans())); it.next()
        return result.merged()

    layers = {}
    for name, pairs in LAYERS.items():
        raw = texts = 0; it = top.begin_shapes_rec(layout.layer(*pairs['drop']))
        while not it.at_end():
            raw += 1; texts += int(it.shape().is_text()); it.next()
        samples = []
        if windows:
            drop = region(pairs['drop'], drop=True)
            metal = (region(pairs['drawing']) + region(pairs['fill'])).merged()
            for bounds in windows:
                window = k.Region(k.Box(*bounds))
                samples.append(dict(drop_area_nm2=(drop & window).area(), metal_area_nm2=(metal & window).area()))
        layers[name] = dict(raw_drop_shapes=raw, drop_texts=texts, samples=samples)
    return dict(windows_nm=windows, layers=layers)


def audit(path, windows=None):
    import klayout.db as k
    path = Path(path); digest = file_digest(path); layout = k.Layout(); layout.read(str(path))
    report = expected(measure(layout, windows), layout.top_cell().name, digest)
    require(file_digest(path) == digest, 'Layout changed during density measurement.')
    return report


def evaluate(report, digest, top):
    require(isinstance(report, dict), 'Missing waffle-window evidence. Recheck Finish.')
    require(report == expected(report.get('measurements'), top, digest), 'Changed waffle-window evidence. Recheck Finish.')
    return report


def validate_saved(report, path):
    require(isinstance(report, dict), 'Missing waffle-window evidence. Recheck Finish.')
    evaluate(report, report.get('gds_sha256'), report.get('top'))
    actual = audit(path, report['measurements']['windows_nm'])
    require(report == actual, 'Waffle-window evidence differs from the actual layout. Recheck Finish.')
    return report
