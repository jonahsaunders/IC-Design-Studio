"""Three-way design merge with explicit choices for overlapping edits."""
from dataclasses import dataclass

from .collaboration_document import FIELDS
from .model import clone, validate


MISSING = object()
KEYED_LISTS = {**{field: key for field, key in FIELDS.items() if key}, 'cells': 'id'}


@dataclass(frozen=True)
class Conflict:
    path: tuple
    label: str
    base: object
    current: object
    incoming: object


def ordered_keys(base, current, incoming):
    common = set(base) & set(current) & set(incoming)
    orders = [tuple(key for key in side if key in common) for side in (base, current, incoming)]
    if orders[1] == orders[2] or orders[2] == orders[0]:
        primary, other = current, incoming
    elif orders[1] == orders[0]:
        primary, other = incoming, current
    else:
        return None
    return dict.fromkeys([*primary, *other, *base])


def merge_design(base, current, incoming, choices=None):
    """Return a validated candidate or conflicts and an actionable validation error."""
    if not base['id'] == current['id'] == incoming['id']:
        raise ValueError('Merge branches of the same project.')
    choices = choices or {}
    conflicts = []

    def conflict(path, title, ancestor, ours, theirs):
        conflicts.append(Conflict(path, ' / '.join(title), ancestor, ours, theirs))
        return theirs if choices.get(path) == 'incoming' else ours

    def walk(path, title, ancestor, ours, theirs):
        if ours == theirs or theirs == ancestor:
            return ours
        if ours == ancestor:
            return theirs
        if all(isinstance(value, dict) for value in (ancestor, ours, theirs)):
            merged = {}
            for key in dict.fromkeys([*ours, *theirs, *ancestor]):
                a, b, c = (values.get(key, MISSING) for values in (ancestor, ours, theirs))
                # The connectivity ledger is derived by project validation.
                value = b if key == 'electrical' and len(path) == 2 and path[0] == 'cells' else walk(
                    (*path, key), (*title, key.replace('_', ' ').capitalize()), a, b, c)
                if value is not MISSING:
                    merged[key] = value
            return merged
        key_field = KEYED_LISTS.get(path[-1]) if path else None
        if key_field and all(isinstance(value, list) for value in (ancestor, ours, theirs)):
            records = []
            for sequence in (ancestor, ours, theirs):
                mapping = {item[key_field]: item for item in sequence if isinstance(item, dict) and key_field in item}
                if len(mapping) != len(sequence):
                    return conflict(path, title, ancestor, ours, theirs)
                records.append(mapping)
            keys = ordered_keys(*records)
            if keys is None:
                return conflict(path, title, ancestor, ours, theirs)
            merged = []
            for key in keys:
                a, b, c = (items.get(key, MISSING) for items in records)
                sample = next(value for value in (b, c, a) if value is not MISSING)
                name = sample.get('name') or sample.get('layer') or key
                value = walk((*path, key), (*title, name), a, b, c)
                if value is not MISSING:
                    merged.append(value)
            return merged
        return conflict(path, title, ancestor, ours, theirs)

    def content(project):
        return {key: value for key, value in project.items() if key not in ('modified', 'revision')}

    design = walk((), (), content(base), content(current), content(incoming))
    if any(choices.get(row.path) not in ('current', 'incoming') for row in conflicts):
        return None, conflicts, ''
    try:
        candidate = clone({**design, 'revision': current['revision'], 'modified': current['modified']})
        return validate(candidate), conflicts, ''
    except (ValueError, KeyError, TypeError) as exc:
        if conflicts:
            return None, conflicts, str(exc)
        fallback = Conflict((), 'Whole design', base, current, incoming)
        if choices.get(()) in ('current', 'incoming'):
            selected = current if choices[()] == 'current' else incoming
            return validate(clone(selected)), [fallback], ''
        return None, [fallback], 'The combined design needs review. ' + str(exc)
