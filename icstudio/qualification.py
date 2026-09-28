"""One hash-bound archive status for gallery, workflow and generated docs.

Archive evidence never substitutes for executing the current document's tests.
An edited example keeps its provenance but loses its archive match.
"""
import json
from pathlib import Path

from .model import digest, file_digest, load_project


def root_path(root=None):
    if root is None:
        from .getting_started import resource_root
        root = resource_root()
    return Path(root).resolve()


def bounded(root, name):
    path = (root/name).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Qualification evidence must stay inside the application resources.')
    return path


def catalog(root=None):
    root = root_path(root)
    data = json.loads((root/'examples/qualification.json').read_text(encoding='utf-8'))
    if data.get('schema') != 1 or not isinstance(data.get('references'), dict):
        raise ValueError('Unsupported reference qualification catalog.')
    return data['references']


def content_identity(project):
    return digest({k: v for k, v in project.items()
                   if k not in ('id', 'revision', 'modified', 'reference_origin')})


def status(reference_id, project=None, root=None):
    root = root_path(root)
    record = catalog(root).get(reference_id)
    if record is None:
        return None
    errors = []
    for name, expected in record['files'].items():
        try:
            if file_digest(bounded(root, name)) != expected:
                errors.append('Changed evidence: '+name)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    # Assertions are evaluated against the retained reports, not just labels in
    # this catalog. A missing or changed result cannot silently stay qualified.
    for check in record['checks']:
        if check['status'] not in ('Passed', 'Failed', 'Blocked', 'Not run'):
            errors.append('Unknown qualification state: '+check['status'])
        if check['status'] == 'Passed' and not check.get('assertions'):
            errors.append('Passing check has no evidence assertions: '+check['name'])
        for assertion in check.get('assertions', []):
            name = assertion['file']
            try:
                if name not in record['files']:
                    raise ValueError('Unbound evidence: '+name)
                value = json.loads(bounded(root, name).read_text(encoding='utf-8'))
                for key in assertion['path']:
                    value = value[key]
                if value != assertion['equals']:
                    raise ValueError('Evidence assertion changed: '+check['name'])
            except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                errors.append(str(exc))
    if record['source'] not in record['files']:
        errors.append('The source project is not bound to this evidence.')
    if project is not None:
        try:
            if content_identity(project) != content_identity(load_project(bounded(root, record['source']))):
                errors.append('This copy differs from the archived reference. Run its saved tests again.')
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    checks = [{**check, 'status': 'Stale' if errors else check['status']} for check in record['checks']]
    return dict(title=record['title'], summary=record['summary'], checks=checks,
                errors=errors, valid=not errors, signoff=False)


def project_status(project, root=None):
    origin = project.get('reference_origin', {})
    if not isinstance(origin, dict) or not isinstance(origin.get('id'), str):
        return None
    return status(origin['id'], project, root)


def markdown(record):
    if record is None:
        return ''
    lines = ['**Archived qualification · '+record['title']+'**', '', record['summary'], '']
    if record['errors']:
        lines += ['**Stale evidence:** '+'; '.join(record['errors']), '']
    lines += ['| Check | Status | Scope |', '|---|---|---|']
    lines += ['| '+check['name']+' | '+check['status']+' | '+check['scope']+' |' for check in record['checks']]
    lines += ['', 'Archive results apply to the recorded source and tools. They do not qualify edits, packaged releases or fabrication signoff.']
    return '\n'.join(lines)


def documentation(root=None):
    root = root_path(root)
    return ('# Reference qualification\n\nGenerated from `examples/qualification.json`. '
            'Run `python scripts/update_qualification.py` after reviewing evidence changes.\n\n'+
            '\n\n'.join(markdown(status(key, root=root)) for key in catalog(root))+'\n')
