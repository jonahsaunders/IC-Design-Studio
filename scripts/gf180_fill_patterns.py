"""Verify a declared GF180 staggered drawing recipe against written polygons.

The recipe is one implementation of DCF.2a/3, DPF.2a/3 and DM.2a/10. It
does not enumerate every legal foundry pattern. Membership permits holes left
by blockages; empty-field coverage must be checked separately. In particular,
the drawing space is an axial placement space, not a Euclidean DRC threshold.
"""
from __future__ import annotations

LAYERS = ('comp', 'poly', 'm1', 'm2', 'm3', 'm4', 'm5')
RECIPE = 'alternating-stagger-v1'


def dimensions(layer):
    """Return square side, placement pitch and stagger, in integer nanometres."""
    if layer == 'comp': return 5000, 8000, 1600
    if layer == 'poly': return 5600, 8000, 1600
    if layer in LAYERS[2:]: return 2000, 3200, 500
    raise ValueError('Unsupported dummy layer in the drawing recipe.')


def validate_plan(plan):
    if (not isinstance(plan, dict) or set(plan) != {'schema', 'recipe', 'layers'}
            or type(plan['schema']) is not int or plan['schema'] != 1
            or plan['recipe'] != RECIPE or not isinstance(plan['layers'], dict)
            or not plan['layers'] or set(plan['layers']) - set(LAYERS)):
        raise ValueError('Require schema 1, alternating-stagger-v1 and explicit supported layer recipes.')
    for layer, entry in plan['layers'].items():
        if not isinstance(entry, dict) or set(entry) != {'origin_nm', 'stagger_sign'}:
            raise ValueError(f'{layer}: declare origin_nm and stagger_sign only.')
        origin, signs = entry['origin_nm'], entry['stagger_sign']
        if (not isinstance(origin, list) or len(origin) != 2
                or any(type(v) is not int or abs(v) > 2_000_000_000 or v % 5 for v in origin)):
            raise ValueError(f'{layer}: origin_nm must contain two integer coordinates on the 5 nm grid.')
        if (not isinstance(signs, list) or len(signs) != 2
                or any(type(v) is not int or v not in (-1, 1) for v in signs)):
            raise ValueError(f'{layer}: stagger_sign must contain two integers, each -1 or 1.')
    return plan


def phases(layer, entry):
    """Global lower-left residues for the four sites in a 2-pitch period.

    x = origin_x + column*pitch + (row modulo 2)*sign_x*stagger
    y = origin_y + row*pitch + (column modulo 2)*sign_y*stagger

    Negative indices are allowed. Signs and a translated origin also describe
    the cardinal rotations/reflections of this square drawing pattern.
    """
    _, pitch, stagger = dimensions(layer)
    ox, oy = entry['origin_nm']; sx, sy = entry['stagger_sign']
    period = 2*pitch
    return {((ox+i*pitch+j*sx*stagger) % period,
             (oy+j*pitch+i*sy*stagger) % period)
            for i in (0, 1) for j in (0, 1)}


def inspect_pattern(shapes, layer, entry):
    size, pitch, stagger = dimensions(layer)
    residues = phases(layer, entry); period = 2*pitch
    failures = 0; examples = []; counts = {point: 0 for point in residues}
    for polygon in shapes.each():
        box = polygon.bbox(); point = (box.left % period, box.bottom % period)
        valid = (polygon.is_box() and box.width() == size and box.height() == size
                 and point in residues)
        if valid:
            counts[point] += 1
        else:
            failures += 1
            if len(examples) < 16:
                examples.append([box.left, box.bottom, box.right, box.top])
    return dict(violations=failures, polygons=shapes.count(),
        size_um=size/1000, placement_space_um=(pitch-size)/1000,
        pitch_um=pitch/1000, stagger_um=stagger/1000,
        origin_nm=entry['origin_nm'], stagger_sign=entry['stagger_sign'],
        period_nm=period,
        phase_counts=[dict(lower_left_residue_nm=list(point), polygons=counts[point])
                      for point in sorted(counts)],
        mismatch_examples_nm=examples,
        scope='Membership in the declared alternating staggered recipe; omitted sites and empty-field coverage are not accepted by this check.')


def inspect_adjacent(lower, upper):
    """Recognize a literal 0.5 um axial translation of the complete arrays.

    DM.9 in the pinned manual specifies 0.5 um and forbids exact replication.
    This implementation selects an axial translation of that length. It does
    not infer acceptance of diagonal, rotated or otherwise different arrays.
    Compare every phase, including sites absent because of blockages. Metadata
    origins alone are insufficient: stagger signs and phase equivalence matter.
    Call only after both written arrays pass their declared recipe checks.
    """
    a, b = phases('m1', lower), phases('m1', upper)
    period = 2 * dimensions('m1')[1]
    offsets = [list((dx, dy)) for dx, dy in ((-500, 0), (0, -500), (0, 500), (500, 0))
               if {((x+dx) % period, (y+dy) % period) for x, y in a} == b]
    replicated = a == b
    return dict(status='replicated_pattern' if replicated else
                'declared_axial_offset_passed' if offsets else 'offset_acceptance_unqualified',
                recipe='whole-array-axial-500nm-v1', offset_nm=500,
                matching_translations_nm=offsets,
                lower_phases_nm=[list(p) for p in sorted(a)],
                upper_phases_nm=[list(p) for p in sorted(b)], period_nm=period,
                scope='Exact 0.5 um axial translation of the complete declared staggered arrays; other nonreplicated arrangements are unqualified by this recipe.')
