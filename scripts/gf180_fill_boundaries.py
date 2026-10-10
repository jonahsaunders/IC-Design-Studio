"""Check fill clearances against an explicit, source-bound floorplan.

These checks do not infer scribe lines from a core, layout extent or guard-ring
marker. Rectangular regions are a supported declaration format, not a claim
that the source floorplan is complete or has received foundry acceptance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

KINDS = {'prime_die', 'frame', 'slm_etest', 'slm_reliability'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def box(values):
    import klayout.db as k
    if (not isinstance(values, list) or len(values) != 4
            or any(type(v) is not int or abs(v) > 2_000_000_000 for v in values)
            or values[2] <= values[0] or values[3] <= values[1]):
        raise ValueError('Boundary rectangles need four integer nm coordinates and positive area.')
    return k.Box(*values)


def load_plan(path, gds_sha256, top_name, bounds):
    """Validate identity, source provenance and supported geometric scope."""
    import klayout.db as k
    path = Path(path); before = digest(path)
    plan = json.loads(path.read_text(encoding='utf-8'))
    fields = {'schema', 'gds_sha256', 'top', 'floorplan_source', 'regions',
              'scribe_boxes_nm', 'frame_cells'}
    if (not isinstance(plan, dict) or set(plan) != fields
            or type(plan['schema']) is not int or plan['schema'] != 1
            or plan['gds_sha256'] != gds_sha256 or plan['top'] != top_name):
        raise ValueError('Require a schema 1 boundary declaration bound to this exact GDS and top.')
    source = plan['floorplan_source']
    if (not isinstance(source, dict) or set(source) != {'file', 'sha256'}
            or not isinstance(source['file'], str) or not source['file']
            or not isinstance(source['sha256'], str)
            or not re.fullmatch('[0-9a-f]{64}', source['sha256'])):
        raise ValueError('Declare the retained floorplan source file and SHA-256.')
    source_path = path.parent / source['file']
    if digest(source_path) != source['sha256']:
        raise ValueError('The declared floorplan source does not match its SHA-256.')
    if (not isinstance(plan['regions'], list) or not plan['regions']
            or not isinstance(plan['scribe_boxes_nm'], list) or not plan['scribe_boxes_nm']
            or not isinstance(plan['frame_cells'], list)):
        raise ValueError('Declare nonempty regions and scribe geometry, plus explicit frame_cells.')
    if len(plan['regions']) + len(plan['scribe_boxes_nm']) + len(plan['frame_cells']) > 10000:
        raise ValueError('Boundary declaration exceeds the 10000-rectangle budget.')
    scribe = k.Region()
    for values in plan['scribe_boxes_nm']: scribe.insert(box(values))
    scribe.merge()
    seen = set(); occupied = k.Region(); frame = k.Region(); regions = []
    for entry in plan['regions']:
        if (not isinstance(entry, dict) or set(entry) != {'name', 'kind', 'bounds_nm'}
                or not isinstance(entry['name'], str) or not entry['name']
                or entry['name'] in seen or not isinstance(entry['kind'], str)
                or entry['kind'] not in KINDS):
            raise ValueError('Boundary regions need unique names, supported kinds and bounds_nm.')
        shape = box(entry['bounds_nm']); area = k.Region(shape)
        if (shape & bounds) != shape or not (area & occupied).is_empty():
            raise ValueError('Boundary regions must be disjoint and inside the fixed layout footprint.')
        if entry['kind'] == 'prime_die':
            if not (area & scribe).is_empty():
                raise ValueError('A prime die cannot overlap the declared scribe material.')
        elif not (area - scribe).is_empty():
            raise ValueError('Frame and SLM regions must lie in the declared scribe area.')
        if entry['kind'] == 'frame': frame += area
        seen.add(entry['name']); occupied += area; regions.append((entry, area))
    cells = k.Region(); cell_extent = k.Region()
    for entry in plan['frame_cells']:
        if (not isinstance(entry, dict) or set(entry) != {'bounds_nm', 'non_et'}
                or type(entry['non_et']) is not bool):
            raise ValueError('Each frame cell needs bounds_nm and an explicit boolean non_et classification.')
        area = k.Region(box(entry['bounds_nm']))
        if not (area - frame).is_empty() or not (area & cell_extent).is_empty():
            raise ValueError('Frame cells must lie in frame regions and have disjoint declared footprints.')
        cell_extent += area
        if not entry['non_et']: cells += area
    if digest(path) != before or digest(source_path) != source['sha256']:
        raise ValueError('Boundary declaration or retained floorplan changed during loading.')
    return dict(plan=plan, plan_sha256=before, source_sha256=source['sha256'],
                regions=regions, scribe=scribe, frame_cells=cells.merged(),
                plan_path=path, source_path=source_path)


def verify_sources(loaded):
    if (digest(loaded['plan_path']) != loaded['plan_sha256']
            or digest(loaded['source_path']) != loaded['source_sha256']):
        raise ValueError('Boundary declaration or retained floorplan changed during inspection.')


def inspect_boundaries(dummy, loaded):
    """Measure complete polygons; never clip fill into a convenient region."""
    import klayout.db as k
    checks = []; classified = {name: k.Region() for name in ('comp', 'poly')}
    counts = []

    def check(rule, layer, count, **details):
        checks.append(dict(rule=rule, layer=layer, status='failed' if count else 'passed',
                           violations=int(count), **details))

    def separate(rule, name, shapes, target, distance, region_name):
        overlap = (shapes & target).merged().count()
        pairs = shapes.separation_check(target, distance).count()
        check(rule, name, overlap+pairs, minimum_um=distance/1000,
              region=region_name, polygons=shapes.count(), metric='Euclidean',
              overlap_regions=overlap, separation_pairs=pairs)

    for entry, area in loaded['regions']:
        selected = {name: dummy[name].inside(area) for name in classified}
        for name, shapes in selected.items(): classified[name] += shapes
        counts.append(dict(name=entry['name'], kind=entry['kind'],
                           **{name: shapes.count() for name, shapes in selected.items()}))
        if entry['kind'] == 'prime_die':
            # The pinned main table says 26 um; its appendix says 8 um.
            # Requiring 26 satisfies both numeric minima, without a waiver.
            separate('DCF.7a', 'comp', selected['comp'], loaded['scribe'], 26000, entry['name'])
            separate('DPF.7', 'poly', selected['poly'], loaded['scribe'], 25700, entry['name'])
        else:
            check('DPF.1-prime-die-scope', 'poly', selected['poly'].count(), region=entry['name'],
                  reason='The declared dummy-poly generation scope is prime die only.')
            rule = 'DCF.7b' if entry['kind'] == 'frame' else 'DCF.7d'
            check(rule, 'comp', area.enclosing_check(selected['comp'], 6000).count(),
                  minimum_um=6., region=entry['name'], polygons=selected['comp'].count(),
                  metric='Euclidean', scope='All edges of the declared rectangular region.')
            if entry['kind'] == 'frame':
                separate('DCF.7c', 'comp', selected['comp'], loaded['frame_cells'], 10000, entry['name'])
    for name, shapes in classified.items():
        missing = dummy[name].not_inside(shapes.merged())
        check('boundary-region-coverage', name, missing.count(),
              reason='Every actual dummy polygon must be wholly inside one declared region; crossing or unclassified polygons are not clipped.')
    return dict(status='failed' if any(c['violations'] for c in checks) else 'declared_boundary_checks_passed',
        qualified=False, plan_sha256=loaded['plan_sha256'],
        floorplan_source_sha256=loaded['source_sha256'], regions=counts, checks=checks,
        dcf7a_source_discrepancy=dict(main_table_um=26., appendix_um=8., enforced_minimum_um=26.),
        scope='Clearances to declared rectangular prime-die/frame/SLM regions and scribe geometry only. Source identity does not prove declaration completeness, physical guard-ring connectivity, reticle or package acceptance.')
