"""Conservative SKY130 drawn-grid audit, without flattening or snapping.

The assumptions table specifies a 5 nm drawn grid. The periphery x.1 table
prints inconsistent ``mm`` units, so this profile is not a resolution of that
source discrepancy. Explicit x.1a mask/package purposes use a 1 nm grid.
No seal-ring exemption is taken. Unsupported path/transform semantics fail
closed before integer conversion can hide a fractional boundary.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import klayout.db as k

from scripts.sky130_global_geometry import layer_metadata, LAYER_MAP_SHA256

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / 'docs/qualification/sky130-grid-density-sources.json'
# Exact published purposes, not every purpose with a matching layer name.
FINE_GRID = {
    (28, 0), (33, 42), (33, 43), (33, 44),  # P1M mask/OPC
    (40, 0), (36, 0), (41, 0),             # via, MM1 and MM2 masks
    (85, 44), (74, 20), (77, 20), (127, 21), (127, 22),
}


def source_metadata():
    """Verify captured bytes against the existing, pinned source inventory."""
    from scripts.sky130_rule_inventory import validate_unreviewed
    inventory = json.loads((ROOT / 'docs/qualification/sky130-rule-inventory.json').read_text())
    validate_unreviewed(inventory)
    capture = json.loads(SOURCES.read_text())
    if capture['source_revision'] != inventory['source_revision']:
        raise ValueError('Source revision mismatch.')
    for path, row in capture['files'].items():
        expected = inventory['source_files'][path]
        digest = hashlib.sha256(row['content'].encode()).hexdigest()
        if digest != expected['sha256'] or row['sha256'] != digest or row['url'] != expected['url']:
            raise ValueError('Changed captured source: ' + path)
    required = {
        'docs/rules/assumptions/01-general.csv',
        'docs/rules/assumptions/04-physical.csv',
        'docs/rules/periphery/p018-x_dotdash.csv',
        'docs/rules/periphery/p038-m1_dotdash.csv',
        'docs/rules/periphery/p040-m2_dotdash.csv',
        'docs/rules/periphery/p042-m3_dotdash.csv',
        'docs/rules/periphery/p044-m4_dotdash.csv',
        'LICENSE',
    }
    if set(capture['files']) != required:
        raise ValueError('Incomplete captured grid/density sources.')
    return dict(revision=inventory['source_revision'],
                source_lock_sha256=inventory['source_lock_sha256'],
                capture_sha256=hashlib.sha256(SOURCES.read_bytes()).hexdigest(),
                files={name: row['sha256'] for name, row in capture['files'].items()})


def _points(polygon):
    yield from polygon.each_point_hull()
    for hole in range(polygon.holes()):
        yield from polygon.each_point_hole(hole)


def check(layout):
    source = source_metadata()
    known, _ = layer_metadata()
    if len(layout.top_cells()) != 1 or abs(layout.dbu - .001) > 1e-12:
        raise ValueError('Expected one top cell and a 1 nm database unit.')
    top = layout.top_cell()
    counts = Counter({name: 0 for name in (
        'profile.transforms', 'profile.path_semantics', 'profile.shape_semantics',
        'profile.known_purposes', 'profile.nonempty', 'grid.boundaries', 'grid.text_anchors')})
    details = []
    # A non-unit magnification or arbitrary rotation can create fractional
    # origins in a nested hierarchy. Reject it before using the integer
    # recursive iterator; checking the rounded result would be unsound.
    for cell_index in {top.cell_index(), *top.called_cells()}:
        cell = layout.cell(cell_index)
        for instance in cell.each_inst():
            transform = instance.cplx_trans
            if transform.mag != 1 or transform.angle % 90 != 0:
                counts['profile.transforms'] += 1
    if counts['profile.transforms']:
        return _result(counts, details, source, top.name, 0)
    geometry = 0
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        pair = (info.layer, info.datatype)
        grid = 1 if pair in FINE_GRID else 5
        stats = Counter(shapes=0, vertices=0, off_grid_vertices=0, texts=0, off_grid_texts=0)
        examples = []
        iterator = top.begin_shapes_rec(index)
        while not iterator.at_end():
            shape = iterator.shape()
            transform = iterator.trans()
            if pair not in known:
                counts['profile.known_purposes'] += 1
            if shape.is_text():
                point = transform * shape.text.trans.disp
                stats['texts'] += 1
                off_grid = point.x % grid != 0 or point.y % grid != 0
                stats['off_grid_texts'] += int(off_grid)
                if off_grid and len(examples) < 20:
                    examples.append(dict(kind='text', cell=iterator.cell().name,
                                         text=shape.text.string, position_nm=[point.x, point.y]))
            else:
                stats['shapes'] += 1
                geometry += 1
                polygon = None
                if shape.is_path():
                    path = shape.path
                    points = list(path.each_point())
                    unsupported = (path.width <= 0 or path.width % 2 != 0 or path.is_round()
                                   or len(points) < 2 or any(
                                       a == b or (a.x != b.x and a.y != b.y)
                                       for a, b in zip(points, points[1:])))
                    if unsupported:
                        counts['profile.path_semantics'] += 1
                    else:
                        # Orthogonal, even-width paths have exact integer
                        # boundaries; all other paths were rejected above.
                        polygon = path.polygon()
                elif shape.is_polygon() or shape.is_box() or shape.is_simple_polygon():
                    polygon = shape.polygon
                else:
                    counts['profile.shape_semantics'] += 1
                if polygon is not None:
                    for point in _points(polygon):
                        point = transform * point
                        stats['vertices'] += 1
                        off_grid = point.x % grid != 0 or point.y % grid != 0
                        stats['off_grid_vertices'] += int(off_grid)
                        if off_grid and len(examples) < 20:
                            examples.append(dict(kind='boundary', cell=iterator.cell().name,
                                                 position_nm=[point.x, point.y]))
            iterator.next()
        if stats['shapes'] or stats['texts']:
            details.append(dict(pair=list(pair), grid_nm=grid, examples=examples, **stats))
        counts['grid.boundaries'] += stats['off_grid_vertices']
        counts['grid.text_anchors'] += stats['off_grid_texts']
    counts['profile.nonempty'] = int(geometry == 0)
    return _result(counts, details, source, top.name, geometry)


def _result(counts, details, source, top, geometry):
    total = sum(counts.values())
    return dict(schema=1, status='FAIL' if total else 'PASS', qualified=False,
                profile='strict-drawn-grid', top=top, violations=total,
                checks=[dict(rule=key, violations=value) for key, value in sorted(counts.items())],
                layers=details, geometry_shapes=geometry, sources=source,
                layer_map_sha256=LAYER_MAP_SHA256,
                scope='5 nm drawn-grid diagnostic with explicit 1 nm mask/package purposes; no seal exemption. '
                      'Periphery unit discrepancy and unreviewed mask aliases remain open; this does not close x.1a/x.1b.')


def audit(path):
    path = Path(path)
    layout = k.Layout()
    layout.read(str(path))
    result = check(layout)
    result.update(gds_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gds', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit(args.gds)
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end='')
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
