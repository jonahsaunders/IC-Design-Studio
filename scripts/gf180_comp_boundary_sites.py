"""Prove whether any COMP square fits a declared rectangular reference die.

Supports one complete prime die surrounded immediately by a rectangular
scribe ring. It deliberately does not infer a ring or accept partial streets,
frame cells, SLM regions or a replacement density denominator.
"""
from __future__ import annotations
from scripts import gf180_comp_sites


def inspect(comp, poly, bounds, loaded):
    import klayout.db as k
    from scripts.gf180_fill_boundaries import verify_sources
    verify_sources(loaded)
    base = dict(qualified=False, no_legal_square_proven=False,
                boundary_plan_sha256=loaded['plan_sha256'],
                floorplan_source_sha256=loaded['source_sha256'])
    entries = loaded['regions']
    if (len(entries) != 1 or entries[0][0]['kind'] != 'prime_die'
            or not (entries[0][1] ^ k.Region(bounds)).is_empty()
            or loaded['plan']['frame_cells']):
        return dict(base, status='unqualified_boundary_scope',
                    reason='Require exactly the complete original prime-die footprint and no frame cells.')
    scribe = loaded['scribe']; outer = scribe.bbox()
    if (outer.left >= bounds.left or outer.bottom >= bounds.bottom or
            outer.right <= bounds.right or outer.top <= bounds.top or
            not (scribe ^ (k.Region(outer)-k.Region(bounds))).is_empty()):
        return dict(base, status='unqualified_scribe_geometry',
                    reason='Require a complete rectangular scribe ring immediately outside every die edge.')
    # For this verified ring, Euclidean distance to the streets is the minimum
    # axis distance to one of the four die edges. Thus DCF.7a's 26 um bound
    # restricts the WHOLE square to this rectangle, including exact equality.
    inset = 26000
    coords = [bounds.left+inset, bounds.bottom+inset, bounds.right-inset, bounds.top-inset]
    if coords[2] <= coords[0] or coords[3] <= coords[1]:
        proof = dict(status='no_legal_square_after_scribe_clearance', no_legal_square_proven=True)
    else:
        proof = gf180_comp_sites.inspect_space(comp, poly, k.Box(*coords))
    verify_sources(loaded)
    return dict(base, status='no_legal_comp_square_in_declared_prime_die' if proof['no_legal_square_proven']
                else 'possible_sites_require_fill', no_legal_square_proven=proof['no_legal_square_proven'],
                original_bounds_nm=[bounds.left,bounds.bottom,bounds.right,bounds.top],
                scribe_bounds_nm=[outer.left,outer.bottom,outer.right,outer.top],
                dcf7a_minimum_nm=inset, admissible_whole_square_bounds_nm=coords,
                circuit_clearance_proof=proof,
                scope='Absence of any legal 5 um COMP square in the entire declared prime die under DCF.4/5/7a. The original die and density denominator remain unchanged. This is not foundry approval of the reference floorplan.')
