"""Supplement the pinned native deck for the original IHP digital block scope.

The authoritative source is SG13G2 Layout Rules Rev. 0.4, pages 24, 27,
37, 42 and 44 (printed numbers). This audit is deliberately not a chip-level
800 um window or seal/scribe qualification. Run the complete native deck too.
"""
import argparse
import hashlib
import json
from pathlib import Path

MANUAL_SHA256 = '66125e97386dd88ed058b50f4f8e8814c9633069e4060c2b19459d3e3e6450a2'
METALS = (8, 10, 30, 50, 67, 126, 134)


def audit_layout(layout):
    import klayout.db as k
    tops = list(layout.top_cells())
    if layout.dbu != .001 or len(tops) != 1:
        raise ValueError('Expected one IHP top on the 1 nm database grid.')
    top = tops[0]
    def region(layer, purpose=0):
        idx = layout.find_layer(layer, purpose)
        return k.Region() if idx is None else k.Region(top.begin_shapes_rec(idx)).merged()
    active, poly = region(1, 22), region(5, 22)
    nw, nbl, pb = region(31), region(32), region(46, 21)
    rows = []
    def record(rule, count, operands, minimum_nm=None, scope=None):
        applicable = all(not r.is_empty() for r in operands)
        rows.append(dict(rule=rule, status='fail' if count else ('pass' if applicable else 'not_applicable'),
                         violations=count, operand_polygons=[r.count() for r in operands],
                         **({'minimum_nm':minimum_nm} if minimum_nm is not None else {}),
                         **({'scope':scope} if scope else {})))
    def spacing(rule, a, b, nm):
        # Native separation checks alone need an explicit overlap check.
        count = a.separation_check(b, nm).count() + (a & b).count()
        record(rule, count, (a, b), nm)
    for layer, label in ((6, 'Cont'), (5, 'GatPoly')):
        spacing('AFil.c.'+label, active, region(layer), 1100)
    for well, label in ((nw, 'NWell'), (nbl, 'nBuLay')):
        # Both inside and outside edges matter. An entirely enclosed filler
        # must have the same clearance to the well edge as an outside filler.
        outside = active - well; inside = active & well
        count = outside.separation_check(well, 1000).count()
        count += (inside - well.sized(-1000)).count()
        record('AFil.d.'+label, count, (active, well), 1000)
    crossing = active.interacting(pb) - active.inside(pb)
    record('AFil.i.crossing', crossing.count(), (active, pb), 1500)
    inside = active.inside(pb)
    count=(active-pb).separation_check(pb,1500).count()+(inside-pb.sized(-1500)).count()
    record('AFil.i.clearance',count,(active,pb),1500)
    for mask, purpose, label in ((7, 21, 'nSD_block'), (28, 0, 'SalBlock')):
        enclosure = region(mask, purpose)
        record('AFil.j.'+label, (inside.sized(250)-enclosure).count(), (inside,), 250)
    for layer, label in ((31, 'NWell'), (32, 'nBuLay')):
        spacing('GFil.e.'+label, poly, region(layer), 1100)
    for layer in (1, 5, *METALS):
        fill = region(layer, 22); exclusion = region(layer, 23)
        record(f'exclusion.{layer}.nofill', (fill & exclusion).count(), (fill, exclusion))
        if layer in METALS:
            excluded = region(160) + region(layer, 24)
            record(f'exclusion.{layer}.metal', (fill & excluded).count(), (fill, excluded))
    bounds = top.bbox()
    boundary = region(39) + region(189) + region(235)
    record('scope.block_boundaries', boundary.count(), (boundary,),
           scope='Seal rings and either historical/current prBoundary mapping need a complete-chip review.')
    # Do not turn a small block's clipped window into a fictional 800 um chip
    # window. The native deck's tiles_stay_inside has no full window here.
    full_windows = bounds.width() >= 800000 and bounds.height() >= 800000
    record('scope.800um_chip_windows', int(full_windows), (k.Region(bounds),),
           scope='No complete 800 x 800 um window fits these reference blocks; chip integration is a later gate.')
    if not full_windows:
        rows[-1]['status'] = 'not_applicable'
    failures = [r['rule'] for r in rows if r['status']=='fail']
    return dict(schema=1, passed=not failures, qualified=False,
                scope='Supplemental fill-rule checks for the original sub-800 um digital blocks only.',
                authoritative_manual_sha256=MANUAL_SHA256,
                bounds_nm=[bounds.left,bounds.bottom,bounds.right,bounds.top],
                full_800um_windows_applicable=full_windows, checks=rows, failed_rules=failures)


def audit(gds, manual):
    import klayout.db as k
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    if sha(manual) != MANUAL_SHA256:
        raise ValueError('The IHP rule manual differs from the pinned revision.')
    layout = k.Layout(); layout.read(str(gds)); result = audit_layout(layout)
    result.update(gds_sha256=sha(gds), checker_sha256=sha(__file__))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gds', type=Path, required=True); p.add_argument('--manual', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    r = audit(a.gds, a.manual); a.output.write_text(json.dumps(r, indent=2)+'\n')
    print(json.dumps({k:r[k] for k in ('passed','qualified','failed_rules')}))
    raise SystemExit(0 if r['passed'] else 1)
