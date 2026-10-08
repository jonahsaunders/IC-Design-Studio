"""Measure GF180 C/D fill and execute explicitly bounded supplemental checks.

This supplements the pinned native deck, which does not implement all fill
rules. Passing these checks is not complete fill qualification. Unimplemented
requirements remain in the report and prevent a successful qualification exit.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import file_digest

LAYERS = {'comp': 22, 'poly': 30, 'm1': 34, 'm2': 36, 'm3': 42, 'm4': 46, 'm5': 81}
MANUAL = ROOT / 'examples/gf180-fill-manual-lock.json'
COVERAGE_MANUAL = ROOT / 'examples/gf180-fill-coverage-lock.json'
LAYER_NAMES = {'comp': 'COMP', 'poly': 'Poly2',
               **{f'm{i}': f'Metal{i}' for i in range(1, 6)}}
WINDOW_NM = 200_000
WINDOW_STEP_NM = 100_000
MAX_WINDOWS_PER_LAYER = 100_000
WELLS = {'Nwell': (21, 0), 'DNWELL': (12, 0),
         'LVPWELL': (204, 0), 'Dualgate': (55, 0)}
MARKERS = {'RES_MK': (110, 5), 'NDMY': (111, 5), 'IND_MK': (151, 5),
           'Pad': (37, 0), 'MTPMARK': (122, 5), 'PMNDMY': (152, 5),
           'FuseTop': (75, 0), 'POLYFUSE': (220, 0),
           'FuseWindow_D': (96, 1), 'OTP_MK': (173, 5)}
# Drawn-layer table and note 13: vendor implant layers, explicitly unsupported
# by the pinned PDK revision. They are not aliases for MTPMARK (122/5).
UNSUPPORTED_MEMORY = {'MCELL_FEOL_MK': (11, 17), 'YMTP_MK': (86, 17)}
# The manual's DCF.1b/1d and PL.8/Mn.4 global limits. Metal5 is also
# MetalTop in C/D's 5LM stack: never count MT.3 as a sixth physical layer.
LIMITS = {'comp': (25, 70), 'poly': (14, 100),
          **{name: (30, 100) for name in ('m1', 'm2', 'm3', 'm4', 'm5')}}
OPEN_REQUIREMENTS = [
    'Declared die/prime-die/scribe scope verified against the complete-chip floorplan',
    'DCF.1a empty-field coverage and local COMP density',
    'DCF/DPF scribe/frame scope and COMP-to-pad RF guideline',
    'DCF exclusion-edge tie/fill rows',
    'Embedded-memory fill coverage beyond supported MTPMARK; vendor implant layers are unsupported',
    'Required drawing patterns and offsets (DCF.2a/3, DPF.2a/3, DM.2a/9/10)',
    'Foundry acceptance limits for local metal density and clipped die-edge windows',
    'Independent full native geometry, antenna and final-layout LVS',
    'Post-fill extraction, timing and foundry acceptance',
]


def verify_layer_map(variant):
    """Bind supplemental rule operands to the selected bundled PDK's map."""
    path = ROOT / f'icstudio/assets/pdks/gf180mcu{variant}/libs.tech/klayout/gf180mcu.lyp'
    sources = {item.text for item in ET.parse(path).iter('source')}
    conductors = {LAYER_NAMES[key] + suffix: (number, datatype)
                  for key, number in LAYERS.items() for datatype, suffix in ((0, ''), (4, '_Dummy'))}
    for name, (number, datatype) in {**WELLS, **MARKERS, **UNSUPPORTED_MEMORY, **conductors}.items():
        if f'{name} {number}/{datatype}@1' not in sources:
            raise ValueError(f'The selected PDK layer map does not identify {name} as {number}/{datatype}.')
    return path


def region(layout, top, number, datatype):
    import klayout.db as k
    index = layout.find_layer(number, datatype)
    return k.Region() if index is None else k.Region(top.begin_shapes_rec(index)).merged()


def area2(shapes):
    """Twice the merged integer-coordinate area, retaining half-grid areas."""
    return sum(p.area2() for p in shapes.each())


def metal_density_windows(shapes, bounds):
    """Measure the declared 200 um / 100 um grid without inventing local limits.

    Edge windows are explicitly clipped to the declared die and reported with
    their actual area. This is a reproducible measurement policy, not a foundry
    acceptance rule. Neither low values nor absent full windows become passes.
    """
    import klayout.db as k
    nx = (bounds.width() + WINDOW_STEP_NM - 1) // WINDOW_STEP_NM
    ny = (bounds.height() + WINDOW_STEP_NM - 1) // WINDOW_STEP_NM
    if nx * ny > MAX_WINDOWS_PER_LAYER:
        raise ValueError('Declared footprint exceeds the metal-density window budget.')
    rows = []
    for y in range(bounds.bottom, bounds.top, WINDOW_STEP_NM):
        for x in range(bounds.left, bounds.right, WINDOW_STEP_NM):
            nominal = k.Box(x, y, x + WINDOW_NM, y + WINDOW_NM)
            clipped = nominal & bounds
            covered2 = area2((shapes & k.Region(clipped)).merged())
            denominator2 = 2 * clipped.area()
            rows.append(dict(bounds_um=[v / 1000 for v in
                (clipped.left, clipped.bottom, clipped.right, clipped.top)],
                complete_window=clipped == nominal, area_um2=clipped.area()/1e6,
                material_area_um2=covered2/2e6, measured_percent=100*covered2/denominator2))
    return dict(status='measured_acceptance_unqualified', window_um=200, step_um=100,
        anchor_um=[bounds.left/1000, bounds.bottom/1000],
        edge_policy='Clip each anchored window to the fixed die; divide by the clipped area. Foundry edge acceptance remains unqualified.',
        local_limits_percent=None, full_windows=sum(r['complete_window'] for r in rows),
        partial_windows=sum(not r['complete_window'] for r in rows), windows=rows)


def inspect(gds, bounds_um, *, top_name, variant):
    """Inspect written geometry, including entirely absent material layers.

    Bounds must come from the fixed design footprint, not from a selected area
    with convenient density. All geometry must fit inside the declared area;
    empty die margins must remain in the density denominator.
    """
    import klayout.db as k
    if variant not in ('C', 'D'):
        raise ValueError('Only the GF180 C/D five-metal stacks are supported.')
    layer_map = verify_layer_map(variant)
    if len(bounds_um) != 4 or any(not math.isfinite(v) or
            not math.isclose(v * 1000, round(v * 1000), abs_tol=1e-7, rel_tol=0) for v in bounds_um):
        raise ValueError('Declare four finite footprint coordinates on the 1 nm database grid.')
    bounds = k.Box(*(round(v * 1000) for v in bounds_um))
    if bounds_um[2] <= bounds_um[0] or bounds_um[3] <= bounds_um[1]:
        raise ValueError('The footprint must have positive width and height.')
    gds = Path(gds); before = file_digest(gds)
    layout = k.Layout(); layout.read(str(gds))
    tops = list(layout.top_cells())
    if layout.dbu != .001 or len(tops) != 1 or tops[0].name != top_name:
        raise ValueError('Require one declared top cell and 1 nm database units.')
    top = tops[0]
    extent = top.bbox()
    if extent.empty() or (extent & bounds) != extent:
        raise ValueError('The fixed design footprint does not contain the full layout extent.')
    if any(not region(layout, top, 53, datatype).is_empty() for datatype in (0, 4)):
        raise ValueError('Unexpected sixth metal in the selected five-metal stack.')
    circuit = {name: region(layout, top, number, 0) for name, number in LAYERS.items()}
    dummy = {name: region(layout, top, number, 4) for name, number in LAYERS.items()}
    wells = {name: region(layout, top, *pair) for name, pair in WELLS.items()}
    markers = {name: region(layout, top, *pair) for name, pair in MARKERS.items()}
    checks = []

    def check(rule, layer, count, **details):
        checks.append(dict(rule=rule, layer=layer, status='failed' if count else 'passed',
                           violations=int(count), **details))

    for name, pair in UNSUPPORTED_MEMORY.items():
        shapes = region(layout, top, *pair)
        check('unsupported-memory-layer', name, shapes.count(), category='coverage',
              source='Drawn-layer definition note 13',
              reason='Vendor-specific implant geometry is unsupported in the pinned PDK revision; it cannot inherit MTPMARK fill checks.')

    # Apply the manual's minimum size to each named marker independently.
    # OR-ing them first can hide a narrow NDMY inside a wider PMNDMY (or vice
    # versa), even though they control different kinds of dummy material.
    for name in ('NDMY', 'PMNDMY'):
        check('DE.2', name, markers[name].width_check(800).count(),
              minimum_um=.8, metric='Euclidean', material='same-layer merged polygons')
    check('DE.4', 'NDMY', markers['NDMY'].space_check(20000).count(),
          minimum_um=20., metric='Euclidean', includes_notches=True)

    exclusion_geometry = []; oversized = unsupported = 0
    for polygon in markers['NDMY'].each():
        box = polygon.bbox(); doubled_area = polygon.area2()
        large = doubled_area > 2 * 15_000 * 1_000_000
        rectangular = polygon.is_box()
        # The >15000 um2 exception requires one rectangle dimension <=80 um.
        # Do not infer a width or side convention for arbitrary large polygons.
        unsupported += int(large and not rectangular)
        bad = large and rectangular and min(box.width(), box.height()) > 80000
        oversized += int(bad)
        exclusion_geometry.append(dict(area_um2=doubled_area/2e6,
            dimensions_um=[box.width()/1000, box.height()/1000], rectangular=rectangular,
            status='unqualified_nonrectangular_exception' if large and not rectangular
                else 'failed' if bad else 'passed'))
    check('DE.3', 'NDMY', oversized, maximum_area_um2=15000.,
          large_rectangle_maximum_short_side_um=80.,
          interpretation='For area strictly greater than 15000 um2, at least one rectangle dimension must be at most 80 um.')
    check('DE.3-geometry-coverage', 'NDMY', unsupported, category='coverage',
          reason='Large nonrectangular exclusion regions need a qualified interpretation of the side-length exception.')

    density = {}; windows = {}
    for name in LAYERS:
        combined = (circuit[name] + dummy[name]).merged()
        material2 = area2(combined); denominator2 = 2 * bounds.area()
        percent = 100 * material2 / denominator2
        lower, upper = LIMITS[name]
        exclusive = name.startswith('m')
        minimum_ok = (100*material2 > lower*denominator2 if exclusive
                      else 100*material2 >= lower*denominator2)
        density[name] = dict(circuit_percent=100*area2(circuit[name])/denominator2,
            dummy_percent=100*area2(dummy[name])/denominator2, total_percent=percent,
            limits_percent=[lower, upper], lower_limit_inclusive=not exclusive)
        check('global-density', name, int(not minimum_ok or 100*material2 > upper*denominator2),
              measured_percent=percent, lower_limit_inclusive=not exclusive)
        if exclusive:
            windows[name] = metal_density_windows(combined, bounds)
        size = 5000 if name == 'comp' else 5600 if name == 'poly' else 2000
        spacing = 1900 if name == 'comp' else 1100 if name == 'poly' else 980
        size_rule = 'DCF.1c/10' if name == 'comp' else 'DPF.1/10' if name == 'poly' else 'DM.1'
        spacing_rule = 'DCF.2b' if name == 'comp' else 'DPF.2b' if name == 'poly' else 'DM.2b'
        invalid = offgrid = 0
        for polygon in dummy[name].each():
            box = polygon.bbox()
            invalid += int(box.width() != size or box.height() != size or polygon.area() != size*size)
            offgrid += int(any(p.x % 5 or p.y % 5 for p in polygon.each_point_hull()))
        check(size_rule, name, invalid, expected_size_um=size/1000, polygons=dummy[name].count())
        check('5-nm-grid', name, offgrid)
        check(spacing_rule, name, dummy[name].space_check(spacing).count(), minimum_um=spacing/1000)
    # Poly fill is optional, so unmatched COMP is allowed. Every actual dummy
    # poly square must coincide with a COMP square expanded 0.3 um per side.
    unmatched = (dummy['poly'] - dummy['comp'].sized(300)).merged()
    extra = (dummy['comp'].sized(300).interacting(dummy['poly']) - dummy['poly']).merged()
    check('DPF.1-enclosure', 'poly', unmatched.count()+extra.count())

    def separation(rule, name, target, distance):
        overlap = (dummy[name] & circuit[target]).merged()
        pairs = dummy[name].separation_check(circuit[target], distance)
        check(rule, name, overlap.count()+pairs.count(), circuit_layer=target, minimum_um=distance/1000)

    separation('DCF.4', 'comp', 'comp', 3500)
    separation('DCF.5', 'comp', 'poly', 1500)
    separation('DPF.4', 'poly', 'comp', 3200)
    separation('DPF.5', 'poly', 'poly', 5000)
    separation('DPF.12', 'poly', 'm1', 2000)
    separation('DPF.13', 'poly', 'm2', 2000)
    for name in ('m1', 'm2', 'm3', 'm4', 'm5'):
        separation('DM.3', name, name, 2000)

    # The table names adjacent metal layers generally; its diagram identifies
    # adjacent dummy metal. Require clearance to the union of circuit and dummy
    # material, which satisfies either reading. M1's previous layer is Poly2.
    stack = ('poly', 'm1', 'm2', 'm3', 'm4', 'm5')
    for index, name in enumerate(stack[1:], 1):
        adjacent = [('DM.5/7', stack[index-1])]
        if index + 1 < len(stack): adjacent.append(('DM.4/6', stack[index+1]))
        for rule, target in adjacent:
            target_region = (circuit[target] + dummy[target]).merged()
            overlap = (dummy[name] & target_region).merged()
            pairs = dummy[name].separation_check(target_region, 1000)
            check(rule, name, overlap.count() + pairs.count(), adjacent_layer=target,
                  minimum_um=1., target_material='union of circuit and dummy',
                  overlap_regions=overlap.count(), separation_pairs=pairs.count(),
                  interpretation='Conservative union covers both the general table wording and the dummy-only diagram.')

    # A dummy may lie inside or outside a well, but it must not cross or
    # approach either side of its boundary.  A well is not an exclusion area.
    for name, prefix, distances in (
            ('comp', 'DCF', (1300, 4000, 1300, 1300)),
            ('poly', 'DPF', (1000, 2000, 1000, 1000))):
        for suffix, (well_name, well), distance in zip('abcd', wells.items(), distances):
            inside = dummy[name].inside(well)
            crossing = dummy[name].interacting(well) - inside
            inner_pairs = well.enclosing_check(inside, distance)
            outer_pairs = dummy[name].separation_check(well, distance)
            check(f'{prefix}.6{suffix}', name,
                  crossing.count() + inner_pairs.count() + outer_pairs.count(),
                  boundary_layer=well_name, minimum_um=distance/1000,
                  boundary_regions=well.count())

    def exclude(rule, name, marker_name, distance):
        target = markers[marker_name]
        # Include overlap explicitly; separation alone does not detect a
        # dummy completely contained within an exclusion marker.
        overlap = (dummy[name] & target).merged()
        pairs = dummy[name].separation_check(target, distance)
        check(rule, name, overlap.count() + pairs.count(),
              exclusion_layer=marker_name, minimum_um=distance/1000,
              exclusion_regions=target.count())

    for rule, marker, distance in (
            ('DCF.8a', 'RES_MK', 3500), ('DCF.11a', 'NDMY', 3500),
            ('DCF.12/13-exclusion', 'IND_MK', 3000)):
        exclude(rule, 'comp', marker, distance)
    for rule, marker, distance in (
            ('DPF.8', 'RES_MK', 19700), ('DPF.9', 'Pad', 6700),
            ('DPF.11', 'NDMY', 29700), ('DPF.14/15', 'IND_MK', 3000),
            ('DPF.16/17', 'MTPMARK', 3000), ('DPF.18/19', 'PMNDMY', 8000)):
        exclude(rule, 'poly', marker, distance)
    for name in ('m1', 'm2', 'm3', 'm4', 'm5'):
        for marker in ('FuseTop', 'POLYFUSE', 'FuseWindow_D', 'PMNDMY', 'MTPMARK', 'OTP_MK'):
            exclude('DM.8', name, marker, 6000)
    if file_digest(gds) != before:
        raise ValueError('The input changed while it was being measured.')
    failed = [c for c in checks if c['status'] == 'failed']
    open_requirements = list(OPEN_REQUIREMENTS)
    if not (markers['NDMY'] + markers['PMNDMY']).is_empty():
        open_requirements.append('DE.1 design justification for using exclusion markers')
    if unsupported:
        open_requirements.append('DE.3 side-length exception for large nonrectangular exclusion regions')
    return dict(schema=4, status='failed' if failed else 'checks_passed_coverage_incomplete',
        qualified=False, variant=variant, metal_stack='5LM_1TM',
        scope='Supplemental density measurements, dummy geometry, clearances, well/marker exclusions, exclusion-marker geometry and unsupported memory-layer detection only.',
        gds_sha256=before, checker_sha256=file_digest(Path(__file__)),
        manual_lock_sha256=file_digest(MANUAL), klayout_python_version=k.__version__,
        coverage_manual_lock_sha256=file_digest(COVERAGE_MANUAL),
        layer_map_sha256=file_digest(layer_map),
        top=top_name, bounds_um=list(bounds_um), area_um2=bounds.area()/1e6,
        geometry_extent_um=[v/1000 for v in (extent.left, extent.bottom, extent.right, extent.top)],
        density=density, metal_density_windows=windows, exclusion_geometry=exclusion_geometry,
        checks=checks, failed_checks=len(failed), unqualified_requirements=open_requirements)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gds', type=Path, required=True)
    parser.add_argument('--top', required=True)
    parser.add_argument('--bounds', type=float, nargs=4, required=True, metavar=('X0','Y0','X1','Y1'))
    parser.add_argument('--variant', choices=('C','D'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError('Choose a new report path; retain prior evidence.')
    report = inspect(args.gds, args.bounds, top_name=args.top, variant=args.variant)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({'status':report['status'], 'failed_checks':report['failed_checks'], 'qualified':False}))
    return 1 if report['failed_checks'] else 2


if __name__ == '__main__': raise SystemExit(main())
