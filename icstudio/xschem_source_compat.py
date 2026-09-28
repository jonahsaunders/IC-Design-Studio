"""Adapt the exact legacy vsource template in captured external workspaces.

New Xschem expands @savecurrent into a .save directive. Older standard symbols
use it as a Tcl boolean. Give that boolean a private name without changing
the expression, circuit values, source library, or arbitrary custom templates.
"""
from pathlib import Path
import re
from .model import atomic_write, file_digest
from .xschem_project import records, properties, record_text, quoted

LEGACY = 'tcleval([expr{@savecurrent?"@name@pinlist@value.saveI(?1@name)":"@name@pinlist@value"}])'
ATTRIBUTE = 'studio_legacy_savecurrent'


def legacy_source(attributes):
    return (attributes.get('type') == 'vsource' and
            re.sub(r'\s+', '', attributes.get('format', '').replace('\\', '')) == LEGACY)


def adapt(roots):
    roots = [Path(p).resolve() for p in roots]
    changed = {}; symbols = {}
    paths = sorted({p for root in roots for p in root.rglob('*.sym')})
    for path in paths:
        text = path.read_text(encoding='utf-8')
        try: attrs = next((properties(r[1]) for r in records(text) if r[0] == 'K'), {})
        except ValueError: continue  # Custom syntax is Xschem's responsibility.
        if not legacy_source(attrs): continue
        if ATTRIBUTE in text: raise ValueError('Reserved compatibility attribute in ' + str(path))
        symbols[path] = properties(attrs.get('template', '')).get('savecurrent', 'false')
        changed[str(path)] = {'before': file_digest(path), 'kind': 'legacy vsource symbol'}
        # Keep the original nested Tcl quoting byte for byte.
        atomic_write(path, text.replace('@savecurrent', '@' + ATTRIBUTE).replace('savecurrent=', ATTRIBUTE + '='))
        changed[str(path)]['after'] = file_digest(path)
    for path in sorted({p for root in roots for p in root.rglob('*.sch')}):
        text = path.read_text(encoding='utf-8'); rows = records(text); count = 0
        for row in rows:
            if row[0] != 'C': continue
            candidates = [path.parent / row[1]] + [root / row[1] for root in roots]
            resolved = next((p.resolve() for p in candidates if p.is_file()), None)
            if resolved not in symbols: continue
            props = properties(row[6])
            if 'format' in props: continue  # user override owns its semantics
            if ATTRIBUTE in props: raise ValueError('Reserved compatibility attribute in ' + str(path))
            value = props.get('savecurrent', symbols[resolved])
            if value not in ('false', 'true', '0', '1'):
                raise ValueError('Legacy source current probe must be a literal boolean: ' + props.get('name', '?'))
            row[6] += '\n' + ATTRIBUTE + '=' + quoted(value); count += 1
        if count:
            changed[str(path)] = {'before': file_digest(path), 'kind': 'legacy vsource instances', 'count': count}
            atomic_write(path, '\n'.join(record_text(row) for row in rows) + '\n')
            changed[str(path)]['after'] = file_digest(path)
    return changed
