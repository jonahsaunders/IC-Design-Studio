"""Recoverable collaboration metadata and conservative conflict proposals, without Qt."""
import json
import math
from pathlib import Path

from .layout_collaboration import FIELDS, _entities
from .live_protocol import LiveError, apply_changes, changes, server_url
from .model import clone


def recent_sessions(directory, cancelled=lambda: False):
    """Read journals in a worker; return display metadata without credentials."""
    root = Path(directory)
    if not root.exists():
        return []
    results = []
    for path in root.glob('*.json'):
        if cancelled():
            break
        try:
            if path.is_symlink() or path.stat().st_size > 64 * 1024 * 1024:
                continue
            state = json.loads(path.read_text(encoding='utf-8'))
            if state.get('schema') != 1:
                continue
            info = state['info']
            if info.get('role') not in ('owner', 'view', 'edit'):
                raise ValueError('Invalid saved role')
            results.append(dict(path=str(path), name=str(state['project']['name'])[:120],
                                server=server_url(state['server']), role=info['role'],
                                editor=str(info['name'])[:80], modified=path.stat().st_mtime,
                                attention=bool(state.get('pending') or state.get('conflict'))))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            results.append(dict(path=str(path), name='Saved session needs recovery',
                                server='', role='', editor='', modified=0, attention=True))
    return sorted(results, key=lambda r: r['modified'], reverse=True)


def conflict_rows(conflict, current):
    if not conflict or not conflict.get('proposed'):
        raise LiveError('This operation has no geometry preview. Save a local copy or use the shared version.')
    rows = changes(conflict['before'], conflict['proposed'])
    cells = {c['id']: c for c in current['cells']}
    return [dict(row, shared=_entities(cells.get(row['cell'], {}), row['field']).get(row['key'])) for row in rows]


def translation(before, after):
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None
    if before.get('kind') not in ('rect', 'polygon', 'path'):
        return None
    if any(before.get(k) or after.get(k) for k in ('generated_device', 'pcell_id')):
        return None
    if {k: v for k, v in before.items() if k not in ('points', 'holes')} != {
            k: v for k, v in after.items() if k not in ('points', 'holes')}:
        return None
    a = [before['points'], *before.get('holes', [])]
    b = [after['points'], *after.get('holes', [])]
    if len(a) != len(b) or any(len(x) != len(y) for x, y in zip(a, b)):
        return None
    offsets = {(q[0] - p[0], q[1] - p[1]) for x, y in zip(a, b) for p, q in zip(x, y)}
    return next(iter(offsets)) if len(offsets) == 1 else None


def reapply_conflict(conflict, current):
    """Reapply a complete transaction; never overwrite a changed foreign value.

    Plain shape translations can be applied to the shared shape's current
    geometry. Other overlapping edits require manual review in a separate copy.
    """
    revised = []
    for row in conflict_rows(conflict, current):
        old, proposed, shared = row['before'], row['after'], row.pop('shared')
        if shared == proposed:
            continue
        if shared == old:
            revised.append(dict(row, before=shared))
            continue
        offset = translation(old, proposed) if row['field'] == 'shapes' else None
        if offset is None or shared is None or shared.get('kind') != old.get('kind'):
            raise LiveError('An overlapping change needs manual editing. Save your version as a separate copy to continue.')
        if shared.get('generated_device') or shared.get('pcell_id'):
            raise LiveError('Generated geometry changed. Save your version as a separate copy and review the whole device.')
        moved = clone(shared)
        dx, dy = offset
        moved['points'] = [[x + dx, y + dy] for x, y in shared['points']]
        if 'holes' in shared:
            moved['holes'] = [[[x + dx, y + dy] for x, y in hole] for hole in shared['holes']]
        revised.append(dict(row, before=shared, after=moved))
    return apply_changes(current, revised)


def reservation_rows(project, info, timestamp):
    cells = {c['id']: c for c in project['cells']}
    leases = info.get('leases', [])
    result = []
    for lease in leases:
        try:
            cid, field, key = json.loads(lease['resource'])
            remaining = math.ceil(lease['expires'] - timestamp)
            if remaining <= 0:
                continue
            cell = cells.get(cid, {})
            owner = 'You' if lease['actor'] == info.get('actor') else lease.get('name', 'Another editor')
            if field == '*':
                scope = 'Whole cell · connected or generated geometry'
            elif field == 'net':
                scope = 'Net ' + key
            else:
                obj = _entities(cell, field).get(key, {}) if field in FIELDS else {}
                scope = (obj.get('layer', '') + ' ' + obj.get('kind', field.replace('layout_', '').replace('_', ' '))).strip()
                if obj.get('net'):
                    scope += ' · net ' + obj['net']
            result.append(dict(cell=cell.get('name', 'Cell'), scope=scope, owner=owner,
                               seconds=remaining, mine=lease['actor'] == info.get('actor')))
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    return result
