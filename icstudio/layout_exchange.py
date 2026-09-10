"""Three-way layout reconciliation with explicit conflicts and stale-input checks."""
import json
from pathlib import Path
from .model import clone, digest, design_digest, file_digest, load_project, validate

_ABSENT = {'__icstudio_absent__': True}


def review(project, path, choices=None):
    from .import_review import propose_layout_change
    path = Path(path).resolve(); side = Path(str(path) + '.icstudio.json')
    manifest = Path(str(path) + '.exchange.json')
    files = {str(path): file_digest(path)}
    if not side.is_file() or not manifest.is_file():
        raise ValueError('Three-way review needs the original .icstudio.json and .exchange.json alongside the layout. Export a new exchange package, or use geometry-only review for legacy files.')
    metadata = json.loads(manifest.read_text())
    if metadata.get('version') != 1 or metadata.get('baseline_hash') != file_digest(side):
        raise ValueError('The exchange baseline is missing or changed. Restore the original metadata files.')
    files.update({str(side): file_digest(side), str(manifest): file_digest(manifest)})
    base = load_project(side)
    if base['id'] != project['id']:
        raise ValueError('This layout belongs to a different project. Open its original project before reviewing edits.')
    if digest(base['pdk']) != digest(project['pdk']):
        raise ValueError('The project technology changed since export. Relink or export a new baseline before merging.')
    external, notes = propose_layout_change(base, path)
    conflicts = []; changes = []; choices = choices or {}
    def merge(before, current, after, location):
        if after == before: return clone(current)
        if current == before or current == after:
            changes.append({'path': location, 'change': 'external'})
            return clone(after)
        if all(isinstance(v, dict) and v != _ABSENT for v in (before, current, after)):
            result = {}
            for key in sorted(before.keys() | current.keys() | after.keys()):
                value = merge(before.get(key, _ABSENT), current.get(key, _ABSENT), after.get(key, _ABSENT), location + '/' + key)
                if value != _ABSENT: result[key] = value
            return result
        if all(isinstance(v, list) for v in (before, current, after)) and all(isinstance(row, dict) and 'id' in row for rows in (before, current, after) for row in rows):
            maps = [{row['id']: row for row in rows} for rows in (before, current, after)]
            if any(len(m) != len(rows) for m, rows in zip(maps, (before, current, after))):
                raise ValueError('Duplicate identities in exchange data.')
            result = []
            for key in dict.fromkeys([r['id'] for r in current] + [r['id'] for r in after]):
                value = merge(*(m.get(key, _ABSENT) for m in maps), location + '/' + key)
                if value != _ABSENT: result.append(value)
            return result
        choice = choices.get(location)
        if choice in ('current', 'external'):
            return clone(current if choice == 'current' else after)
        conflicts.append({'path': location, 'base': clone(before), 'current': clone(current), 'external': clone(after)})
        return clone(current)
    candidate = clone(project)
    candidate['cells'] = merge(base['cells'], project['cells'], external['cells'], '/cells')
    errors = []
    if not conflicts:
        try: validate(candidate)
        except (ValueError, KeyError) as exc: errors.append(str(exc))
    record = {'version': 1, 'source': str(path), 'files': files,
              'project_hash': digest(project), 'candidate': candidate,
              'conflicts': conflicts, 'changes': changes, 'notes': notes, 'errors': errors}
    record['candidate_hash'] = digest(candidate)
    return record


def apply(project, record):
    if record['conflicts'] or record['errors']:
        raise ValueError('Resolve every layout conflict and validation error before applying.')
    if digest(project) != record['project_hash']:
        raise ValueError('The project changed after review. Review the layout again.')
    if any(not Path(name).is_file() or file_digest(name) != expected for name, expected in record['files'].items()):
        raise ValueError('An exchange file changed after review. Review the layout again.')
    if digest(record['candidate']) != record['candidate_hash']:
        raise ValueError('The reviewed candidate changed. Review the layout again.')
    candidate = clone(record['candidate']); validate(candidate)
    project.clear(); project.update(candidate)
    return project
