"""Stage offline documentation for desktop distributions. Source archives retain the evidence tree."""
import json
import shutil
from pathlib import Path


# The installed SKY130 MiM, metal-resistor and parallel-array electrical
# checks read these exact references from the installed resource directory.
INSTALLED_ELECTRICAL_REFERENCES = (
    'docs/qualification/sky130-li-sources-v1/res_generic-table0.rst',
    'docs/qualification/sky130-metal-resistors-linked-v1.json',
    'docs/qualification/sky130-mim-sources-v1/LICENSE',
    'docs/qualification/sky130-mos-bias-sources-v1/device-details.rst',
)


def document_paths(root):
    """Return paths for offline guides, gallery evidence and installed checks."""
    docs = root / 'docs'
    paths = {path for pattern in ('*.md', '*.json', '*.png') for path in docs.glob(pattern)}
    for folder in ('images', 'screenshots'):
        paths.update(path for path in (docs / folder).rglob('*') if path.is_file())
    catalog = json.loads((root / 'examples/qualification.json').read_text(encoding='utf-8'))
    references = set(INSTALLED_ELECTRICAL_REFERENCES)
    references.update(name for record in catalog['references'].values()
                      for name in record['files'] if name.startswith('docs/'))
    for name in references:
        path = (root / name).resolve()
        if not path.is_relative_to(docs.resolve()) or not path.is_file():
            raise ValueError('Missing or invalid desktop documentation: ' + name)
        paths.add(path)
    return sorted(path.relative_to(root) for path in paths)


def stage_documents(root, destination):
    root = Path(root).resolve()
    for relative in document_paths(root):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)
