"""Enumerate every COMP site in a declared staggered array over a fixed block.

This implements a conservative whole-footprint drawing-site audit. It does
not sample a subset of sites or restrict the density denominator to the core.
All applicable site clearances must pass; boundary applicability still needs
an explicit chip/floorplan declaration. Missing sites are concrete witnesses,
not a claim that a missing chip-boundary interpretation has been resolved.
"""
from __future__ import annotations

from scripts import gf180_fill_patterns as patterns

MAX_SITES = 100000


def sites(bounds, entry):
    import klayout.db as k
    patterns.validate_plan(dict(schema=1, recipe=patterns.RECIPE, layers={'comp': entry}))
    side, pitch, _ = patterns.dimensions('comp'); period = 2*pitch
    result = []
    for px, py in sorted(patterns.phases('comp', entry)):
        x0 = bounds.left + (px-bounds.left) % period
        y0 = bounds.bottom + (py-bounds.bottom) % period
        nx = max(0, (bounds.right-side-x0)//period+1)
        ny = max(0, (bounds.top-side-y0)//period+1)
        if len(result) + nx*ny > MAX_SITES:
            raise ValueError('Whole-footprint COMP coverage exceeds the site budget.')
        result.extend(k.Box(x, y, x+side, y+side)
                      for y in range(y0, bounds.top-side+1, period)
                      for x in range(x0, bounds.right-side+1, period))
    return sorted(result, key=lambda b: (b.left, b.bottom))


def inspect(comp, poly, dummy, wells, markers, bounds, entry):
    import klayout.db as k
    boxes = sites(bounds, entry)
    array = k.Region()
    for box in boxes: array.insert(box)
    rejected = k.Region(); reasons = {}

    def separation(rule, target, distance):
        # Edge pairs alone miss complete containment. Keep the entire site
        # whenever overlap or any too-close edge pair identifies it.
        bad = array.interacting(target) + array.interacting(array.separation_check(target, distance).first_edges())
        bad.merge(); reasons[rule] = bad.count()
        return bad

    rejected += separation('DCF.4', comp, 3500)
    rejected += separation('DCF.5', poly, 1500)
    for rule, name, distance in (('DCF.6a', 'Nwell', 1300), ('DCF.6b', 'DNWELL', 4000),
                                 ('DCF.6c', 'LVPWELL', 1300), ('DCF.6d', 'Dualgate', 1300)):
        target = wells[name]
        # Sites wholly inside and wholly outside a well both need clearance
        # from the well boundary. Straddlers fail regardless of edge distance.
        inside = array.inside(target); outside = array.not_interacting(target)
        crossing = array - inside - outside
        bad = crossing + inside.interacting(inside.enclosed_check(target, distance).first_edges())
        bad += outside.interacting(outside.separation_check(target, distance).first_edges())
        bad.merge(); reasons[rule] = bad.count(); rejected += bad
    for rule, name, distance in (('DCF.8a', 'RES_MK', 3500), ('DCF.11a', 'NDMY', 3500),
                                 ('DCF.12/13', 'IND_MK', 3000)):
        rejected += separation(rule, markers[name], distance)
    # Pad is explicitly excluded from COMP generation by DCF.1a. Its optional
    # RF clearance is reported separately, never silently treated as a mask.
    pad = array.interacting(markers['Pad']); reasons['DCF.1a-Pad'] = pad.count(); rejected += pad
    rejected.merge()
    permitted = (array-rejected).merged()
    present = {tuple((b.left, b.bottom, b.right, b.top)) for p in dummy.each()
               if p.is_box() for b in (p.bbox(),)}
    missing = k.Region()
    for p in permitted.each():
        b = p.bbox()
        if (b.left, b.bottom, b.right, b.top) not in present: missing.insert(p)
    return dict(status='missing_unblocked_sites' if not missing.is_empty() else 'all_unblocked_sites_present',
        qualified=False, recipe=patterns.RECIPE, entry=entry,
        bounds_nm=[bounds.left, bounds.bottom, bounds.right, bounds.top],
        candidate_sites=len(boxes), rejected_sites=rejected.count(),
        rejection_counts_by_rule=reasons, unblocked_sites=permitted.count(),
        missing_sites=missing.count(),
        missing_boxes_nm=[[b.left, b.bottom, b.right, b.top]
                          for b in (p.bbox() for p in missing.each())],
        scope='Every declared whole-footprint COMP drawing site under circuit, well and exclusion clearances. Chip/scribe/frame boundaries, exclusion-edge rows and complete DCF.1a acceptance remain separate.'), missing
