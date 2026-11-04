"""Conservative proof of unavailable COMP fill space, without sampling sites.

A nonempty result is not placement acceptance. Boundary/scribe scope, wells,
markers, drawing patterns, density and complete DCF.1a coverage are separate.
"""
from __future__ import annotations

SIDE_NM = 5000
UNDERBOUND_MARGIN_NM = 5
MAX_RECTANGLES = 200_000


def forbidden_origins(shapes, distance_nm):
    """Underestimate the strictly forbidden origins of a 5 um square.

    For each source rectangle, subtracting the dummy square gives the exact
    overlap-forbidden origin rectangle. Its Minkowski sum with an L1 diamond
    of radius d-5nm is strictly inside the Euclidean d clearance keepout.
    Minkowski addition distributes over the union of source rectangles.
    Thus legal origins cannot be removed by this construction. The 5 nm
    margin also keeps exact-limit legal sites away from polygon boundaries.
    """
    import klayout.db as k
    rectangles = shapes.decompose_trapezoids_to_region()
    if rectangles.count() > MAX_RECTANGLES:
        raise ValueError('COMP site analysis exceeds the rectangle budget.')
    if sum(p.area2() for p in rectangles.each()) != sum(p.area2() for p in shapes.each()):
        raise ValueError('Rectangle decomposition did not preserve the material area.')
    result = k.Region(); count = 0
    for polygon in rectangles.each():
        if not polygon.is_box():
            raise ValueError('COMP site absence is unqualified for non-Manhattan circuit material.')
        box = polygon.bbox()
        left, bottom, right, top = box.left-SIDE_NM, box.bottom-SIDE_NM, box.right, box.top
        d = distance_nm-UNDERBOUND_MARGIN_NM
        result.insert(k.Polygon([k.Point(left-d,bottom), k.Point(left,bottom-d),
            k.Point(right,bottom-d), k.Point(right+d,bottom), k.Point(right+d,top),
            k.Point(right,top+d), k.Point(left,top+d), k.Point(left-d,top)]))
        count += 1
    return result.merged(), count


def inspect_space(comp, poly, bounds):
    """Analyze every possible square origin in the declared rectangular scope.

    Emptiness proves there is no legal square under just DCF.4/5; additional
    rules cannot create a legal site. A nonempty complement overapproximates
    possible origins and cannot establish that any particular site is legal.
    Degenerate origin domains remain unqualified rather than losing line or
    point solutions in area-only polygon operations.
    """
    import klayout.db as k
    result = dict(dummy_size_nm=SIDE_NM, bounds_nm=[bounds.left,bounds.bottom,bounds.right,bounds.top],
        clearance_nm=dict(circuit_comp=3500, circuit_poly=1500),
        strict_clearance_underestimate_margin_nm=UNDERBOUND_MARGIN_NM,
        qualified=False, no_legal_square_proven=False,
        scope='Absence under DCF.4/5 circuit clearances only; a nonempty complement is not legal-site, boundary or complete DCF.1a acceptance.')
    if bounds.width() <= 0 or bounds.height() <= 0:
        raise ValueError('The declared COMP analysis scope must have positive area.')
    if min(bounds.width(), bounds.height()) < SIDE_NM:
        return dict(result, status='no_legal_square_footprint', no_legal_square_proven=True)
    if min(bounds.width(), bounds.height()) == SIDE_NM:
        return dict(result, status='unqualified_degenerate_origin_domain',
                    reason='Line or point origin domains need a separate exact analysis.')
    try:
        c, count_c = forbidden_origins(comp, 3500)
        p, count_p = forbidden_origins(poly, 1500)
    except ValueError as exc:
        return dict(result, status='unqualified_geometry', reason=str(exc))
    domain = k.Region(k.Box(bounds.left,bounds.bottom,bounds.right-SIDE_NM,bounds.top-SIDE_NM))
    possible = (domain-(c+p)).merged()
    return dict(result,
        status='no_legal_square_from_circuit_clearances' if possible.is_empty() else 'possible_origins_unqualified',
        no_legal_square_proven=possible.is_empty(),
        circuit_rectangles=dict(comp=count_c, poly=count_p),
        possible_origin_regions=possible.count(),
        possible_origin_area_um2=sum(p.area2() for p in possible.each())/2e6,
        possible_origin_boxes_nm=[[b.left,b.bottom,b.right,b.top] for b in (p.bbox() for p in possible.each())])
