"""Additional conservative fill checks for the selected SKY130 HD block profile.

This closes omissions in fill-to-fill checks of the bundled native decks. It
does not replace those decks, establish density acceptance or qualify a PDK.
The dummy-FOM constraints are conservatively applied to the installed 23/28
waffle output as well; the public 22/23 dummy purpose remains unsupported here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import klayout.db as k

# Dimensions are nm, areas nm2. The source manual uses micrometres.
# Huge rectangular fill uses the additional wide-metal spacing. Clearance
# from fill to functional metal conservatively uses that larger limit.
METALS = {
    'li': ((56, 28), (67, 20), 170, 170, 56100),
    'm1': ((36, 28), (68, 20), 140, 140, 83000),
    'm2': ((41, 28), (69, 20), 140, 140, 67600),
    'm3': ((34, 28), (70, 20), 300, 300, 240000),
    'm4': ((51, 28), (71, 20), 300, 300, 240000),
    'm5': ((59, 28), (72, 20), 1600, 1600, 4000000),
}
WIDE = {'m1': 280, 'm2': 280, 'm3': 400, 'm4': 400}
FILL = {(23, 28)} | {v[0] for v in METALS.values()}
ABSENT = {
    'deep_nwell': (64, 18), 'high_voltage': (75, 20), 'pwell_resistor': (64, 13),
    'pad': (76, 20), 'photo_array': (81, 81), 'seal': (81, 1),
    'die_cut': (81, 11), 'frame': (81, 12), 'fuse': (71, 17),
    'manual_fom_dummy': (22, 23), 'fom_custom': (22, 20), 'fom_mask': (23, 0),
    'fom_add': (22, 21), 'fom_drop': (22, 22), 'fom_waffle_drop': (22, 24),
    'poly_fill': (28, 28),
}


def check(regions, die):
    """Check supplied hierarchical regions on a validated 1 nm database grid."""
    empty = k.Region()
    get = lambda pair: regions.get(pair, empty)
    rows = []
    def add(name, count, basis):
        rows.append(dict(check=name, violations=int(count), basis=basis))
    for name, pair in ABSENT.items():
        add('profile.'+name, get(pair).count(), 'Explicitly excluded from this block fill profile; never silently ignored.')
    for pair in sorted(FILL):
        fill = get(pair)
        add('extent.'+str(pair), (fill-die).count(), 'Original declared die; no enlarged density denominator.')
        add('grid.'+str(pair), sum(any(p.x % 5 or p.y % 5 for p in polygon.each_point_hull())
                                 or any(any(p.x % 5 or p.y % 5 for p in polygon.each_point_hole(h))
                                        for h in range(polygon.holes())) for polygon in fill.each()), 'x.1b: 5 nm grid')
    fom = get((23, 28))
    add('fom.width', fom.width_check(500).count(), 'errors.csv r1256 / fomdmy.1')
    add('fom.shape', sum(not p.is_box() or p.bbox().width() != p.bbox().height() or
                         p.bbox().width() not in (500, 1500, 2500, 4080) for p in fom.each()),
        'Selected recipe uses only the four published fom_waffles square sizes; below fomdmy.1a maximum.')
    add('fom.spacing', fom.space_check(400).count(), 'errors.csv r1258 / fomdmy.2')
    implants = get((93, 44)) | get((94, 20))
    add('fom.implant', (fom & implants).count()+fom.separation_check(implants, 130).count(),
        'errors.csv r1263-r1266 / fomdmy.7')
    well = get((64, 20))
    add('fom.well', (fom & (well.sized(340)-well.sized(-180))).count(),
        'errors.csv r1267-r1268 / fomdmy.8 and fomdmy.9')
    active = get((65, 20)) | get((65, 44)) | get((66, 20))
    add('fom.active_clearance', (fom & active.sized(500)).count(), 'Conservative 0.5 um active/poly keepout of the selected recipe.')
    nsm = get((61, 20)) | get((22, 0))
    add('fom.nsm', (fom & nsm).count()+fom.separation_check(nsm, 1000).count(), 'nsm.3')
    for name, (pair, drawn, width, spacing, area) in METALS.items():
        fill, signal = get(pair), get(drawn)
        add(name+'.width', fill.width_check(width).count(), name+'.1')
        add(name+'.area', sum(p.area() < area for p in fill.each()), name+('.4' if name == 'm5' else '.6'))
        add(name+'.spacing', fill.space_check(spacing).count(), name+' minimum fill-to-fill spacing')
        add(name+'.rectangular', sum(not p.is_box() for p in fill.each()), 'This fill profile supports rectangular shapes only.')
        if name in WIDE:
            huge = k.Region()
            for polygon in fill.each():
                if polygon.bbox().width() > 3000 and polygon.bbox().height() > 3000:
                    huge.insert(polygon)
            add(name+'.wide_spacing', huge.space_check(WIDE[name]).count()+
                huge.separation_check(fill-huge, WIDE[name]).count(),
                name+'.3: published huge-metal spacing; rectangular fills have no attached narrow features.')
        add(name+'.signal_clearance', (fill & signal).count()+fill.separation_check(signal, WIDE.get(name, spacing)).count(), name+' fill-to-drawn spacing, conservatively using the wide rule')
        if name == 'li':
            add('li.active_clearance', (fill & active.sized(200)).count(), 'Selected recipe 0.2 um active/poly keepout.')
            add('li.aspect', sum(not p.is_box() or max(p.bbox().width(), p.bbox().height()) >
                                10*min(p.bbox().width(), p.bbox().height()) for p in fill.each()), 'li.2: floating LI length/width <= 10')
    violations = sum(row['violations'] for row in rows)
    return dict(status='PASS' if not violations else 'FAIL', qualified=False, violations=violations, checks=rows,
                scope='Additional conservative fill geometry only. Native full DRC, density, antenna, connectivity and electrical checks are separate.')


def audit(source, filled, die_nm):
    layouts = []
    for path in (source, filled):
        layout = k.Layout(); layout.read(str(path))
        if len(layout.top_cells()) != 1 or abs(layout.dbu-.001) > 1e-12:
            raise ValueError('Fill audit requires one top and a 1 nm database grid.')
        layouts.append(layout)
    before, after = layouts
    if before.top_cell().name != after.top_cell().name:
        raise ValueError('Fill changed the design top.')
    pairs = {(l.get_info(i).layer, l.get_info(i).datatype) for l in layouts for i in l.layer_indexes()}
    regions = {}
    for pair in sorted(pairs):
        old = k.Region(before.top_cell().begin_shapes_rec(before.layer(*pair))).merged()
        new = k.Region(after.top_cell().begin_shapes_rec(after.layer(*pair))).merged()
        if pair not in FILL and not (old ^ new).is_empty():
            raise ValueError('Fill changed non-fill geometry: '+str(pair))
        if pair in FILL and not old.is_empty():
            raise ValueError('The independent baseline already contains fill.')
        def labels(layout):
            iterator = layout.top_cell().begin_shapes_rec(layout.layer(*pair)); values = []
            while not iterator.at_end():
                if iterator.shape().is_text():
                    values.append(iterator.shape().text.transformed(iterator.trans()).to_s())
                iterator.next()
            return sorted(values)
        if labels(before) != labels(after):
            raise ValueError('Fill changed annotations: '+str(pair))
        regions[pair] = new
    if (len(die_nm) != 4 or any(type(x) is not int for x in die_nm) or
            die_nm[0] >= die_nm[2] or die_nm[1] >= die_nm[3]):
        raise ValueError('Invalid declared die.')
    report = check(regions, k.Region(k.Box(*die_nm)))
    report.update(source_gds_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
                  gds_sha256=hashlib.sha256(Path(filled).read_bytes()).hexdigest(), die_nm=die_nm)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--filled', type=Path, required=True)
    parser.add_argument('--die-nm', type=int, nargs=4, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.source, args.filled, args.die_nm)
    args.output.write_bytes((json.dumps(report, indent=2)+'\n').encode())
    print(json.dumps(dict(status=report['status'], violations=report['violations'])))
    raise SystemExit(0 if report['status'] == 'PASS' else 1)
