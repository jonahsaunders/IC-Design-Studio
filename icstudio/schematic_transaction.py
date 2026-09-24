"""Bounded capture transforms on an already validated local document.

Only presentation geometry and its attached wire paths may change. Any change
to a device's named connections falls back to the complete transaction, which
also checks saved benches, specifications and other electrical references.
"""
import math
import re

from . import capture_ops, wiring


def _same(a, b):
    """JSON equality including numeric types, matching reversible history."""
    if a is b: return True
    if type(a) is not type(b): return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(value, b[key]) for key, value in a.items())
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and a == b == 0:
        return math.copysign(1, a) == math.copysign(1, b)
    return a == b


def _object_ids(project):
    result = {project['id']}
    fields = ('devices', 'shapes', 'annotations', 'layout_instances',
              'layout_pins', 'buses', 'wires', 'labels')
    for cell in project['cells']:
        result.add(cell['id'])
        for field in fields:
            result.update(obj['id'] for obj in cell.get(field, []))
    result.update(bench['id'] for bench in project.get('testbenches', []))
    return result


def _working_cell(original):
    """Copy exactly the containers written by a non-copy capture transform.

    Geometry edits replace coordinate lists. Connectivity rebuilding mutates
    each device's nets and replaces terminal/net identity dictionaries and the
    cell ledger. Parameters, symbols, physical data and the previous ledger are
    read-only throughout this command and can remain shared with the document.
    """
    cell = {**original, 'devices': [{**d, 'nets': dict(d['nets'])} for d in original['devices']]}
    for field in ('wires', 'annotations'):
        if field in original: cell[field] = [dict(obj) for obj in original[field]]
    if 'labels' in original:
        cell['labels'] = [{**label, 'anchor': dict(label['anchor'])} for label in original['labels']]
    return cell


def propose(project, cid, ids, dx=0, dy=0, *, stretch=True, mirror=False):
    """Return an isolated, validated geometry transform, or None for fallback."""
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 2e7 for v in (dx, dy)):
        raise ValueError('Invalid schematic position.')
    if type(stretch) is not bool or type(mirror) is not bool:
        raise ValueError('Invalid schematic transform.')
    original = next(c for c in project['cells'] if c['id'] == cid)
    chosen = set(ids)
    supported = {obj['id'] for field in ('devices', 'wires', 'labels', 'annotations')
                 for obj in original.get(field, [])}
    if not chosen or not chosen <= supported: return None
    for field in ('devices', 'annotations'):
        for obj in original.get(field, []):
            if obj['id'] in chosen and any(abs(obj.get(axis, 0) + delta) > 1e7 for axis, delta in (('x', dx), ('y', dy))):
                raise ValueError('Invalid schematic position.' if field == 'devices' else 'Invalid annotation position.')
    cell = _working_cell(original)
    cells = [cell if c is original else c for c in project['cells']]
    candidate = {**project, 'cells': cells}
    capture_ops.transform(candidate, cid, chosen, dx, dy, stretch=stretch, mirror=mirror,_before=original)
    # The command cannot edit names, values, symbols, ports, hierarchy, process
    # bindings, physical geometry, constraints or analysis settings. Validate
    # the fields it can write, and require exact named electrical equivalence.
    for d in cell['devices']:
        if any(not isinstance(d[axis], (int, float)) or not math.isfinite(d[axis])
               or abs(d[axis]) > 1e7 for axis in ('x', 'y')):
            raise ValueError('Invalid schematic position.')
    for note in cell.get('annotations', []):
        if any(not math.isfinite(float(note.get(axis, 0)))
               or abs(float(note.get(axis, 0))) > 1e7 for axis in ('x', 'y')):
            raise ValueError('Invalid annotation position.')
    # Existing IDs were validated before the command. Only newly introduced
    # branch wires need a project-wide collision check; don't scan the layout
    # on the common path where every object retains its identity.
    previous_ids = {obj['id'] for field in ('wires', 'labels') for obj in original.get(field, [])}
    created = {obj['id'] for field in ('wires', 'labels') for obj in cell.get(field, [])} - previous_ids
    occupied = _object_ids(project) - previous_ids if created else set()
    seen = set()
    def objid(value):
        if not isinstance(value, str) or not re.fullmatch('[a-zA-Z0-9_-]{1,80}', value) or value in seen or value in occupied:
            raise ValueError('Invalid or duplicate object ID.')
        seen.add(value)
    # transform just rebuilt connectivity, after repairing label attachments.
    # No writes intervene, so validate its schema without rebuilding it again.
    wiring.validate_wiring_structure(cell, objid, candidate)
    if any(before['nets'] != after['nets'] for before, after in zip(original['devices'], cell['devices'])):
        return None
    # Share unmodified rows as well as physical data. Delta creation, undo and
    # view updates can then visit just the branches this gesture changed.
    for field in ('devices', 'wires', 'labels', 'annotations'):
        if field not in cell: continue
        old = {obj['id']: obj for obj in original.get(field, [])}
        cell[field] = [old[obj['id']] if obj['id'] in old and _same(obj, old[obj['id']]) else obj for obj in cell[field]]
    for field, value in list(cell.items()):
        if field in original and _same(value, original[field]): cell[field] = original[field]
    return candidate
