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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import file_digest

LAYERS = {'comp': 22, 'poly': 30, 'm1': 34, 'm2': 36, 'm3': 42, 'm4': 46, 'm5': 81}
MANUAL = ROOT / 'examples/gf180-fill-manual-lock.json'
# The manual's DCF.1b/1d and PL.8/Mn.4 global limits. Metal5 is also
# MetalTop in C/D's 5LM stack: never count MT.3 as a sixth physical layer.
LIMITS = {'comp': (25, 70), 'poly': (14, 100),
          **{name: (30, 100) for name in ('m1', 'm2', 'm3', 'm4', 'm5')}}
OPEN_REQUIREMENTS = [
    'Declared die/prime-die/scribe scope verified against the complete-chip floorplan',
    'DCF.1a empty-field coverage and local COMP density',
    'DCF/DPF well-boundary, marking-layer, scribe, pad and exclusion rules',
    'DCF exclusion-edge tie/fill rows',
    'DM.4-7 adjacent-layer separation and overlap interpretation',
    'DM.8 exclusion regions and clearance',
    'Required drawing patterns and offsets (DCF.2a/3, DPF.2a/3, DM.2a/9/10)',
    '200 x 200 um metal windows at 100 um steps and foundry edge treatment',
    'Independent full native geometry, antenna and final-layout LVS',
    'Post-fill extraction, timing and foundry acceptance',
]


def region(layout, top, number, datatype):
    import klayout.db as k
    index = layout.find_layer(number, datatype)
    return k.Region() if index is None else k.Region(top.begin_shapes_rec(index)).merged()


def inspect(gds, bounds_um, *, top_name, variant):
    """Inspect written geometry, including entirely absent material layers.

    Bounds must come from the fixed design footprint, not from a selected area
    with convenient density. All geometry must fit inside the declared area;
    empty die margins must remain in the density denominator.
    """
    import klayout.db as k
    if variant not in ('C', 'D'):
        raise ValueError('Only the GF180 C/D five-metal stacks are supported.')
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
    checks = []

    def check(rule, layer, count, **details):
        checks.append(dict(rule=rule, layer=layer, status='failed' if count else 'passed',
                           violations=int(count), **details))

    density = {}
    for name in LAYERS:
        combined = (circuit[name] + dummy[name]).merged()
        percent = 100 * combined.area() / bounds.area()
        lower, upper = LIMITS[name]
        density[name] = dict(circuit_percent=100*circuit[name].area()/bounds.area(),
            dummy_percent=100*dummy[name].area()/bounds.area(), total_percent=percent,
            limits_percent=[lower, upper])
        check('global-density', name, int(not lower <= percent <= upper), measured_percent=percent)
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
    if file_digest(gds) != before:
        raise ValueError('The input changed while it was being measured.')
    failed = [c for c in checks if c['status'] == 'failed']
    return dict(schema=1, status='failed' if failed else 'checks_passed_coverage_incomplete',
        qualified=False, variant=variant, metal_stack='5LM_1TM',
        scope='Supplemental global-density, dummy-size/grid/spacing and selected circuit-clearance checks only.',
        gds_sha256=before, checker_sha256=file_digest(Path(__file__)),
        manual_lock_sha256=file_digest(MANUAL), klayout_python_version=k.__version__,
        top=top_name, bounds_um=list(bounds_um), area_um2=bounds.area()/1e6,
        geometry_extent_um=[v/1000 for v in (extent.left, extent.bottom, extent.right, extent.top)],
        density=density, checks=checks, failed_checks=len(failed),
        unqualified_requirements=list(OPEN_REQUIREMENTS))


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
