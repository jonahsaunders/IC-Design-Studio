"""Measure SKY130 metal occupancy on the published 700/70 um window lattice.

This is deliberately not an oxide-density acceptance check. The public rules
give an oxide metric, while this module measures raw drawn-plus-fill metal.
Full windows and edge clips are kept separate; small blocks never obtain a
vacuous pass. Die bounds must be supplied explicitly, never inferred from
the geometry whose density is being measured.
"""
import argparse
import hashlib
import json
from pathlib import Path

import klayout.db as k

from scripts.sky130_grid_geometry import source_metadata

WINDOW_NM = 700_000
STEP_NM = 70_000
METALS = {
    'm1': ((68, 20), (36, 28)),
    'm2': ((69, 20), (41, 28)),
    'm3': ((70, 20), (34, 28)),
    'm4': ((71, 20), (51, 28)),
}


def windows(die):
    """Origin anchored at declared die lower-left, full windows plus clips.

    Anchoring/edge policy is an explicit diagnostic convention, not an
    inferred upstream oxide algorithm. Integer bounds preserve exact areas.
    """
    if (len(die) != 4 or any(type(value) is not int for value in die)
            or die[2] <= die[0] or die[3] <= die[1]):
        raise ValueError('Die must have four integer nm bounds and positive area.')
    left, bottom, right, top = die
    for x in range(left, right, STEP_NM):
        for y in range(bottom, top, STEP_NM):
            bounds = (x, y, min(x + WINDOW_NM, right), min(y + WINDOW_NM, top))
            yield bounds, bounds[2] - x == WINDOW_NM and bounds[3] - y == WINDOW_NM


def check(regions, die):
    source = source_metadata()
    samples = list(windows(die))
    die_region = k.Region(k.Box(*die))
    full_count = sum(full for _, full in samples)
    layers = []
    for metal, pairs in METALS.items():
        # Union before area calculation: overlapping fill and conductor must
        # never be double counted. Regions retain hierarchy and polygon holes.
        conductor = k.Region()
        for pair in pairs:
            raw = regions.get(pair, k.Region()).dup()
            raw.merged_semantics = False
            if any(edge.dx() and edge.dy() for edge in raw.edges().each()):
                raise ValueError('Exact integer-area diagnostic requires Manhattan metal: ' + metal)
            conductor += raw
        conductor.merge()
        rows = []
        for bounds, full in samples:
            window = k.Region(k.Box(*bounds))
            area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
            occupied = (conductor & window).area()
            rows.append(dict(bounds_nm=list(bounds), kind='full' if full else 'clipped',
                             area_nm2=area, metal_area_nm2=occupied,
                             metal_fraction=occupied / area))
        layers.append(dict(metal=metal, operands=[list(pair) for pair in pairs],
                           outside_die_area_nm2=(conductor - die_region).area(), windows=rows))
    blockers = ['Oxide-density operand construction and acceptance semantics are not defined by this metal-occupancy diagnostic.']
    if full_count == 0:
        blockers.append('Declared block is smaller than a 700 um window; parent-chip context is required for full-window coverage.')
    if any(row['outside_die_area_nm2'] for row in layers):
        blockers.append('Measured metal extends outside the declared die bounds.')
    return dict(schema=1, status='BLOCKED', qualified=False, sources=source,
                metric='drawn_plus_fill_metal_occupancy', geometry_profile='Manhattan metal only', die_nm=list(die),
                window_nm=WINDOW_NM, step_nm=STEP_NM,
                full_windows=full_count, clipped_windows=len(samples) - full_count,
                layers=layers, blockers=blockers,
                source_limits='m1-m4.pd.1 name oxide pattern density; .pd.2a gives 700 um; '
                              '.pd.2b gives 70 with an empty unit. The 70 um step and '
                              'die-origin/clipped-edge policy are explicit diagnostic conventions. '
                              'Metal occupancy is neither oxide density nor the prior whole-die density screen.')


def audit(path, die):
    path = Path(path)
    layout = k.Layout()
    layout.read(str(path))
    if len(layout.top_cells()) != 1 or abs(layout.dbu - .001) > 1e-12:
        raise ValueError('Expected one top cell and a 1 nm database unit.')
    # Refuse complex transforms and non-exact paths before integer Region
    # construction can snap them. Ordinary off-grid integer polygons remain
    # measurable; their grid errors are separately retained.
    from scripts.sky130_grid_geometry import check as check_grid
    grid = check_grid(layout)
    unsupported = [row for row in grid['checks'] if row['rule'] in {
        'profile.transforms', 'profile.path_semantics', 'profile.shape_semantics'} and row['violations']]
    if unsupported:
        raise ValueError('Geometry cannot be measured without snapping: ' + str(unsupported))
    regions = {}
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        regions[(info.layer, info.datatype)] = k.Region(layout.top_cell().begin_shapes_rec(index))
    result = check(regions, die)
    result.update(gds_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), top=layout.top_cell().name,
                  checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  geometry_reader_sha256=hashlib.sha256((Path(__file__).with_name('sky130_grid_geometry.py')).read_bytes()).hexdigest(),
                  grid_status=grid['status'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gds', type=Path)
    parser.add_argument('--die-nm', type=int, nargs=4, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit(args.gds, args.die_nm)
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end='')
    # Measurement success is not rule acceptance, even for fully covered die.
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
