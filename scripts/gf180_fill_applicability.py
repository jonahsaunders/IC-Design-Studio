"""Determine fill-rule applicability from actual, recursively merged operands.

Absence is an applicability result, never a waiver. Present unsupported
operands remain open; a bounding box is not accepted as a nonrectangular
marker's side-length interpretation. This does not accept DCF.1a coverage.
"""
from __future__ import annotations


def inspect(markers, dummy, unsupported_memory, channel):
    rows = []

    def record(rule, status, **details):
        rows.append(dict(rule=rule, status=status, **details))

    for rule, name in (('DCF.8b', 'RES_MK'), ('DCF.11b', 'NDMY'), ('DCF.13-row', 'IND_MK')):
        shapes = markers[name]
        large = sum(p.is_box() and min(p.bbox().width(), p.bbox().height()) > 80000
                    for p in shapes.each())
        nonrectangular = sum(not p.is_box() for p in shapes.each())
        if shapes.is_empty():
            status = 'not_applicable_absent_operand'
        elif channel.is_empty():
            status = 'not_applicable_no_channel_intersection'
        elif nonrectangular:
            status = 'unqualified_nonrectangular_marker'
        elif not large:
            status = 'not_applicable_threshold_not_exceeded'
        else:
            status = 'requires_exclusion_edge_row_check'
        record(rule, status, marker=name, polygons=shapes.count(),
               rectangular_markers_exceeding_both_80um_dimensions=large,
               nonrectangular_markers=nonrectangular,
               channel_intersections=channel.count(), threshold_um=80,
               threshold_comparison='both dimensions strictly greater than')

    record('DCF.9', 'not_applicable_absent_operand' if markers['Pad'].is_empty() or
           dummy['comp'].is_empty() else 'requires_rf_guideline_review',
           pad_polygons=markers['Pad'].count(), dummy_comp_polygons=dummy['comp'].count(),
           scope='The 7 um COMP-to-pad distance is an RF guideline, not a universal DRC rule.')
    for rule, material in (('DCF.7a/7b/7c/7d', 'comp'), ('DPF.1-prime-die/7', 'poly')):
        record(rule, 'not_applicable_absent_operand' if dummy[material].is_empty()
               else 'requires_declared_boundary_check', dummy_polygons=dummy[material].count(),
               scope='Actual dummy boundary distances only; this does not waive missing fill or floorplan coverage.')

    memory = {name: shapes.count() for name, shapes in unsupported_memory.items()}
    record('vendor-memory-fill', 'unsupported_operand_present' if any(memory.values())
           else 'not_applicable_absent_operand', layers=memory,
           scope='Only the unsupported vendor implant layers; supported MTPMARK checks run separately.')
    record('DE.1', 'not_applicable_absent_operand' if
           (markers['NDMY'] + markers['PMNDMY']).is_empty() else 'requires_design_justification',
           ndmy_polygons=markers['NDMY'].count(), pmndmy_polygons=markers['PMNDMY'].count())
    return dict(schema=1, rules=rows,
                scope='Source-backed applicability of conditional fill rules only; no complete fill or process qualification.')
