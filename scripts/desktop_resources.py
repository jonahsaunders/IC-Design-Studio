"""Stage offline documentation for desktop distributions. Source archives retain the evidence tree."""
import json
import shutil
from pathlib import Path


def document_paths(root):
    """Return repository-relative paths. Gallery evidence follows the same catalog as the app."""
    docs = root / 'docs'
    paths = {path for pattern in ('*.md', '*.json', '*.png') for path in docs.glob(pattern)}
    for folder in ('images', 'screenshots'):
        paths.update(path for path in (docs / folder).rglob('*') if path.is_file())
    catalog = json.loads((root / 'examples/qualification.json').read_text(encoding='utf-8'))
    for record in catalog['references'].values():
        for name in record['files']:
            if name.startswith('docs/'):
                path = (root / name).resolve()
                if not path.is_relative_to(docs.resolve()) or not path.is_file():
                    raise ValueError('Missing or invalid gallery documentation: ' + name)
                paths.add(path)
    return sorted(path.relative_to(root) for path in paths)


def stage_documents(root, destination):
    root = Path(root).resolve()
    for relative in document_paths(root):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)

