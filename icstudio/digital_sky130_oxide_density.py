"""Measure two explicitly identified public metal-growth density profiles.

Adapted by IC Design Studio on 2026-10-15 from Tiny Tapeout's Apache-2.0
met_density_tiled.drc (DLindley's July/September 2024 notes). Original source,
license and exact revision are retained in tests/fixtures/sky130-tt-density-v1.
Studio uses exact integer areas, physical nm growth, independent declared bounds,
inclusive window endpoints, and separately labelled clipped observations.
This is not a foundry signoff deck or a promotion of the older error catalog.
"""
from pathlib import Path

from .model import file_digest

RECIPE = 'sky130-public-oxide-density-v1'
SOURCE = dict(repository='https://github.com/TinyTapeout/tinytapeout-10',
    revision='46f0a2f45c3b1fcc27aac7acb7faa054631d9955',
    path='sky130_tapeout_drc/met_density_tiled.drc', license='Apache-2.0',
    sha256='89a82a47299d668511d0af8a16bd3f7c5da35375eaf4bca6224637446d4786f1')
WINDOW_NM, STEP_NM, MINIMUM_PERCENT = 700_000, 70_000, 80
LAYERS = dict(m1=((68, 20), (36, 28)), m2=((69, 20), (41, 28)),
              m3=((70, 20), (34, 28)), m4=((71, 20), (51, 28)))
PROFILES = {
    'tinytapeout-margin': dict(m1=425, m2=375, m3=600, m4=550),
    'skywater-growth-reported-by-tinytapeout': dict(m1=600, m2=600, m3=1150, m4=1150),
}
SCOPE = ('Public Tiny Tapeout metal-growth density observations, using drawn metal and native '
    'fill on four layers. The first profile uses the upstream checker values; the second uses '
    'the values attributed to SkyWater in its comments, not a separately authenticated foundry '
    'specification. Integer 80% comparisons are made on full 700 um windows every 70 um from '
    'the explicitly declared lower-left corner. Exact endpoint windows are included. Clipped '
    'edge windows are diagnostics only. Geometry is grown before clipping, preserving external '
    'contributors, holes, hierarchy and overlapping unions. A small block never gets a vacuous '
    'pass. These measurements do not establish complete-chip context, final-mask construction, '
    'the applicability of this newer 80% profile to the pinned PDK, or m5/ViaTop policy. No '
    'catalog disposition or tapeout qualification is changed.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def windows(bounds):
    if bounds is None:
        return []
    require(isinstance(bounds, list) and len(bounds) == 4 and all(type(n) is int for n in bounds)
            and bounds[0] < bounds[2] and bounds[1] < bounds[3],
            'Density bounds must be four integer nm coordinates with positive area.')
    left, bottom, right, top = bounds
    count = ((right-left+STEP_NM-1)//STEP_NM)*((top-bottom+STEP_NM-1)//STEP_NM)
    require(count <= 100_000, 'Density window count exceeds the supported limit.')
    result = []
    for x in range(left, right, STEP_NM):
        for y in range(bottom, top, STEP_NM):
            w = [x, y, min(x+WINDOW_NM, right), min(y+WINDOW_NM, top)]
            result.append(dict(bounds_nm=w, area_nm2=(w[2]-x)*(w[3]-y),
                kind='full' if w[2]-x == w[3]-y == WINDOW_NM else 'clipped-diagnostic'))
    return result


def expected(measurements, top, digest):
    require(isinstance(measurements, dict) and set(measurements) == {'bounds_nm', 'layers'},
            'Missing public oxide-density measurements.')
    samples = windows(measurements['bounds_nm']); layers = measurements['layers']
    require(isinstance(layers, dict) and layers.keys() == LAYERS.keys(), 'Incomplete oxide-density layers.')
    observations = {}
    for metal, value in layers.items():
        require(isinstance(value, dict) and set(value) == {'raw_shapes', 'areas_nm2'} and
                isinstance(value['raw_shapes'], list) and len(value['raw_shapes']) == 2 and
                all(type(n) is int and n >= 0 for n in value['raw_shapes']) and
                isinstance(value['areas_nm2'], dict) and value['areas_nm2'].keys() == PROFILES.keys(),
                'Invalid oxide-density operand census.')
        observations[metal] = {}
        for profile, areas in value['areas_nm2'].items():
            require(isinstance(areas, list) and len(areas) == len(samples), 'Incomplete oxide-density windows.')
            result = []
            for sample, area in zip(samples, areas):
                require(type(area) is int and 0 <= area <= sample['area_nm2'] and
                        (any(value['raw_shapes']) or area == 0), 'Invalid grown-metal area.')
                result.append(dict(**sample, grown_metal_area_nm2=area,
                    below_minimum=100*area < MINIMUM_PERCENT*sample['area_nm2']))
            observations[metal][profile] = result
    full = sum(w['kind'] == 'full' for w in samples)
    summaries = {}
    for profile in PROFILES:
        rows = [r for m in observations.values() for r in m[profile]]
        failures = sum(r['kind'] == 'full' and r['below_minimum'] for r in rows)
        summaries[profile] = dict(full_window_findings=failures,
            clipped_window_findings=sum(r['kind'] != 'full' and r['below_minimum'] for r in rows),
            status='full-window-findings' if failures else 'sampled-full-windows-pass' if full else 'no-full-windows')
    return dict(schema=1, recipe=RECIPE, source=SOURCE, scope=SCOPE, qualified=False,
        chunk_complete=False, acceptance_established=False, status='review-required',
        top=top, gds_sha256=digest, minimum_percent=MINIMUM_PERCENT, growth_nm=PROFILES,
        operands={m:[list(p) for p in pairs] for m, pairs in LAYERS.items()},
        window_nm=WINDOW_NM, step_nm=STEP_NM, full_windows=full, clipped_windows=len(samples)-full,
        measurements=measurements, observations=observations, summaries=summaries,
        context='declared-bounds' if samples else 'bounds-not-supplied')


def measure(layout, bounds=None):
    import klayout.db as k
    samples = windows(bounds)
    require(len(layout.top_cells()) == 1, 'Oxide density requires one top cell.')
    top = layout.top_cell()
    if samples:
        require(abs(layout.dbu-.001) < 1e-12, 'Oxide density requires exact 1 nm database units.')
        for index in {top.cell_index(), *top.called_cells()}:
            for instance in layout.cell(index).each_inst():
                t = instance.cplx_trans
                require(t.mag == 1 and t.angle % 90 == 0, 'Unsupported oxide-density transform.')

    def read(pair):
        region, count = k.Region(), 0
        iterator = top.begin_shapes_rec(layout.layer(*pair))
        while not iterator.at_end():
            count += 1
            if samples:
                shape = iterator.shape()
                require(not shape.is_text(), 'Text on an oxide-density operand cannot establish its area.')
                if shape.is_path():
                    p = shape.path; points = list(p.each_point())
                    require(p.width > 0 and p.width % 2 == 0 and not p.is_round() and len(points) >= 2 and
                        all(a != b and (a.x == b.x or a.y == b.y) for a,b in zip(points, points[1:])),
                        'Inexact oxide-density path.')
                    polygon = p.polygon()
                else:
                    require(shape.is_box() or shape.is_polygon() or shape.is_simple_polygon(),
                            'Unsupported oxide-density shape.')
                    polygon = shape.polygon
                require(polygon.area() > 0 and all(e.p1.x == e.p2.x or e.p1.y == e.p2.y for e in polygon.each_edge()),
                        'Oxide density requires nonempty Manhattan geometry.')
                region.insert(polygon.transformed(iterator.trans()))
            iterator.next()
        return region.merged(), count

    layers = {}
    for metal, pairs in LAYERS.items():
        drawing, nd = read(pairs[0]); fill, nf = read(pairs[1])
        conductor = (drawing | fill).merged()
        areas = {}
        for profile, growth in PROFILES.items():
            grown = conductor.sized(growth[metal]).merged() if samples else k.Region()
            areas[profile] = [(grown & k.Region(k.Box(*s['bounds_nm']))).area() for s in samples]
        layers[metal] = dict(raw_shapes=[nd, nf], areas_nm2=areas)
    return dict(bounds_nm=bounds, layers=layers)


def audit(path, bounds=None):
    import klayout.db as k
    path = Path(path); digest = file_digest(path); layout = k.Layout(); layout.read(str(path))
    result = expected(measure(layout, bounds), layout.top_cell().name, digest)
    require(file_digest(path) == digest, 'Layout changed during oxide-density measurement.')
    return result


def evaluate(report, digest, top):
    require(isinstance(report, dict), 'Missing public oxide-density evidence. Recheck Finish.')
    require(report == expected(report.get('measurements'), top, digest),
            'Changed public oxide-density evidence. Recheck Finish.')
    return report


def validate_saved(report, path, bounds=None):
    actual = audit(path, bounds)
    evaluate(report, actual['gds_sha256'], actual['top'])
    require(report == actual, 'Public oxide-density evidence differs from the actual layout or declared bounds.')
    return report
