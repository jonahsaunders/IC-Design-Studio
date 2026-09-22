"""Create an enlarged, density-filled Banba GDS without changing circuit masks.

GF180 dummy rules: DRM 13.1, 13.2 and 13.3. Fill is a physical finishing
operation; the editable circuit remains in banba-layout.icproj. The output
retains the circuit hierarchy and uses compact arrays for electrically
unconnected fill. This is not a complete chip floorplan or fabrication signoff.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import file_digest

SOURCE = ROOT/'examples/gf180-banba/layout/banba-layout.gds'
FILL_LAYERS = {'comp': (22, 4), 'poly': (30, 4), 'm1': (34, 4),
               'm2': (36, 4), 'm3': (42, 4), 'm4': (46, 4)}
BORDER = (63, 0)
EDGE = 30000
CORE_CLEARANCE = 20000
EXCLUSION_CLEARANCE = 30000
# FuseTop, POLYFUSE, FUSEWINDOW_D, PMNDMY, MTPMK, OTP_MK, NDMY,
# resistor recognition, and inductor recognition are also covered by the
# conservative all-circuit keepout below. Explicit exclusion gets 30 um.
EXCLUSIONS = [(75, 0), (220, 0), (96, 1), (152, 5), (122, 5),
              (86, 17), (173, 5), (111, 5), (110, 5), (151, 5)]


def region(layout, top, pair):
    import klayout.db as k
    index = layout.find_layer(*pair)
    return k.Region() if index is None else k.Region(top.begin_shapes_rec(index)).merged()


def source_regions(layout, top):
    return {(layout.get_info(i).layer, layout.get_info(i).datatype):
            region(layout, top, (layout.get_info(i).layer, layout.get_info(i).datatype))
            for i in layout.layer_indexes()}


def keepout(regions):
    import klayout.db as k
    occupied = k.Region()
    for shapes in regions.values():
        occupied += shapes
    blocked = occupied.merged().sized(CORE_CLEARANCE)
    for pair in EXCLUSIONS:
        blocked += regions.get(pair, k.Region()).sized(EXCLUSION_CLEARANCE)
    return blocked.merged()


def candidates(bounds, size, pitch, stagger, phase=0):
    import klayout.db as k
    result = k.Region()
    for iy, y in enumerate(range(bounds.bottom+EDGE, bounds.top-EDGE-size-stagger-phase+1, pitch)):
        for ix, x in enumerate(range(bounds.left+EDGE, bounds.right-EDGE-size-stagger-phase+1, pitch)):
            xx, yy = x+(iy % 2)*stagger+phase, y+(ix % 2)*stagger+phase
            result.insert(k.Box(xx, yy, xx+size, yy+size))
    return result


def insert_arrays(layout, top, name, selected, layers, pitch):
    """Losslessly compress complete tiles into rows; never clip a fill square."""
    import klayout.db as k
    tile = layout.create_cell('banba_fill_'+name)
    for pair, box in layers:
        tile.shapes(layout.layer(*pair)).insert(k.Box(*box))
    rows = defaultdict(list)
    for polygon in selected.each():
        box = polygon.bbox()
        rows[box.bottom].append(box.left)
    count = 0
    for y, xs in sorted(rows.items()):
        xs.sort()
        start = previous = xs[0]
        for x in xs[1:]+[None]:
            if x is None or x-previous != 2*pitch:
                n = (previous-start)//(2*pitch)+1
                top.insert(k.CellInstArray(tile.cell_index(), k.Trans(start, y),
                    k.Vector(2*pitch, 0), k.Vector(0, 0), n, 1))
                count += 1
                start = x
            previous = x
    return count


def inspect(source, output, bounds):
    """Independently inspect the written GDS, including rules absent upstream."""
    import klayout.db as k
    before, after = k.Layout(), k.Layout()
    before.read(str(source)); after.read(str(output))
    old, top = before.top_cell(), after.top_cell()
    if old.name != top.name or before.dbu != .001 or after.dbu != .001:
        raise ValueError('Top cell or 1 nm database unit changed.')
    original = source_regions(before, old)
    current = source_regions(after, top)
    for pair in set(original) | set(current):
        if pair not in FILL_LAYERS.values() and pair != BORDER:
            if not (original.get(pair, k.Region()) ^ current.get(pair, k.Region())).is_empty():
                raise ValueError('Circuit mask changed: '+str(pair))
    border = current.get(BORDER, k.Region())
    if not (border ^ k.Region(bounds)).is_empty() or top.bbox() != bounds:
        raise ValueError('The declared floorplan must equal the density denominator.')
    blocked = keepout(original)
    usable = k.Region(bounds.enlarged(-EDGE))
    fill = {}
    for name, pair in FILL_LAYERS.items():
        tiles = current.get(pair, k.Region())
        if tiles.is_empty():
            raise ValueError('Missing '+name+' fill.')
        size = 5000 if name == 'comp' else 5600 if name == 'poly' else 2000
        spacing = 1900 if name == 'comp' else 1100 if name == 'poly' else 980
        for tile in tiles.each():
            box = tile.bbox()
            if box.width() != size or box.height() != size or tile.area() != size*size:
                raise ValueError('Truncated or incorrectly sized '+name+' fill.')
            if any(v % 5 for v in (box.left, box.bottom, box.right, box.top)):
                raise ValueError('Off-grid '+name+' fill.')
        if not tiles.space_check(spacing).is_empty():
            raise ValueError('Dummy spacing violation in '+name+'.')
        if not (tiles - usable).is_empty() or not tiles.interacting(blocked).is_empty():
            raise ValueError('Fill entered an edge, circuit or process keepout: '+name)
        fill[name] = dict(tiles=tiles.count(), area_um2=tiles.area()/1e6)
    if not (current[FILL_LAYERS['poly']].sized(-300) ^ current[FILL_LAYERS['comp']]).is_empty():
        raise ValueError('Dummy poly must enclose its matching COMP by 0.3 um.')
    density = {}
    for name, pair in FILL_LAYERS.items():
        material = current[pair] + current.get((pair[0], 0), k.Region())
        density[name] = material.merged().area()/bounds.area()*100
    limits = {'comp': (25, 70), 'poly': (14, 100),
              'm1': (30, 100), 'm2': (30, 100), 'm3': (30, 100), 'm4': (30, 100)}
    failures = [name for name, (low, high) in limits.items() if not low <= density[name] <= high]
    if failures:
        raise ValueError('Insufficient fill floorplan for '+', '.join(failures)+': '+str(density))
    return dict(passed=True, core_masks_unchanged=True, fill=fill, density_percent=density,
                density_limits_percent=limits, area_mm2=bounds.area()/1e12,
                bounds_um=[v/1000 for v in (bounds.left, bounds.bottom, bounds.right, bounds.top)])


def build(source, directory, halo_um=600):
    import klayout.db as k
    source, directory = Path(source).resolve(), Path(directory).resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Choose an empty output directory.')
    directory.mkdir(parents=True, exist_ok=True)
    if (not math.isfinite(halo_um) or not 0 < halo_um <= 2000
            or not math.isclose(halo_um*1000, round(halo_um*1000), abs_tol=1e-7, rel_tol=0)
            or round(halo_um*1000) % 5):
        raise ValueError('Halo must be positive, on the 5 nm grid, and at most 2000 um.')
    layout = k.Layout(); layout.read(str(source)); top = layout.top_cell()
    if layout.dbu != .001 or top.name != 'banba_layout':
        raise ValueError('Expected the Banba layout at 1 nm database units.')
    regions = source_regions(layout, top)
    if any(pair in regions and not regions[pair].is_empty() for pair in [*FILL_LAYERS.values(), BORDER]):
        raise ValueError('Input already contains fill or a boundary; use the original circuit GDS.')
    bounds = top.bbox().enlarged(round(halo_um*1000))
    blocked = keepout(regions)
    poly = candidates(bounds, 5600, 8000, 1600).not_interacting(blocked)
    arrays = insert_arrays(layout, top, 'poly_comp', poly,
        [((30, 4), (0, 0, 5600, 5600)), ((22, 4), (300, 300, 5300, 5300))], 8000)
    for n, name in enumerate(('m1', 'm2', 'm3', 'm4')):
        selected = candidates(bounds, 2000, 3200, 500, n*500).not_interacting(blocked)
        arrays += insert_arrays(layout, top, name, selected, [(FILL_LAYERS[name], (0, 0, 2000, 2000))], 3200)
    top.shapes(layout.layer(*BORDER)).insert(bounds)
    output = directory/'banba-density.gds'
    options = k.SaveLayoutOptions(); options.gds2_write_timestamps = False
    layout.write(str(output), options)
    report = inspect(source, output, bounds)
    report.update(schema=1, source_sha256=file_digest(source), gds_sha256=file_digest(output),
                  generator_sha256=file_digest(__file__), halo_um=halo_um, arrays=arrays,
                  klayout_python_version=k.__version__,
                  original_area_mm2=before_area(source), signoff=False,
                  policy=dict(edge_um=30, circuit_clearance_um=20, exclusion_clearance_um=30,
                    poly_comp_pitch_um=8, poly_comp_stagger_um=1.6,
                    metal_pitch_um=3.2, metal_stagger_um=.5, adjacent_metal_offset_um=.5))
    (directory/'fill-validation.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def before_area(source):
    import klayout.db as k
    layout = k.Layout(); layout.read(str(source))
    return layout.top_cell().bbox().area()*layout.dbu**2/1e6


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--halo-um', type=float, default=600)
    a = parser.parse_args()
    print(json.dumps(build(a.source, a.out, a.halo_um), indent=2))
