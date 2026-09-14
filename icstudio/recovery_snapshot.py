"""Isolated JSON snapshots with reuse of equal, previously isolated subtrees.

Never retain a caller's dict or list, even when legacy code mutates it in place.
The preceding writer must finish before its snapshot is reused. Equality also
checks scalar types: JSON true, 1 and 1.0 must not become interchangeable.
"""
from .model import clone


def isolate(value, previous=None):
    if type(value) is not type(previous):
        return clone(value)
    if isinstance(value, dict):
        changed = None
        for key, child in value.items():
            old = previous.get(key)
            isolated = isolate(child, old)
            if key not in previous or isolated is not old:
                if changed is None: changed = dict(previous)
                changed[key] = isolated
        if previous.keys() != value.keys():
            if changed is None: changed = dict(previous)
            for key in previous.keys() - value.keys(): del changed[key]
        return previous if changed is None else changed
    if isinstance(value, list):
        if len(value) != len(previous):
            # Length changes are uncommon in drag workloads. Still isolate every
            # new member while reusing unchanged members at stable positions.
            return [isolate(child, previous[i] if i < len(previous) else None)
                    for i, child in enumerate(value)]
        changed = None
        for i, child in enumerate(value):
            isolated = isolate(child, previous[i])
            if isolated is not previous[i]:
                if changed is None: changed = list(previous)
                changed[i] = isolated
        return previous if changed is None else changed
    if isinstance(value, (str, int, float, bool, type(None))):
        return previous if value == previous else value
    return clone(value)
