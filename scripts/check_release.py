"""Check the current release's local documentation, gallery and tag version."""
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import __version__
from icstudio.getting_started import examples, example_copy
from icstudio.model import validate


def require_release_notes(version, root=ROOT):
    note_version = re.sub(r'^(\d+\.\d+)\.0\.dev(\d+)$', r'\1_DEV\2', version)
    notes = Path(root) / 'docs' / f'UPDATE_{note_version}.md'
    if not notes.is_file():
        raise ValueError('Missing release notes for the current version: ' + notes.name)
    return notes


def main():
    from scripts.update_qualification import update
    update(check=True)
    from scripts.check_pdk_qualification import MATRIX, read, validate as validate_matrix
    matrix = validate_matrix(read(MATRIX))
    docs = ['README.md', 'CONTRIBUTING.md', 'SIMULATION_SETUP.md', 'THIRD_PARTY_NOTICES.md']
    docs += [str(p.relative_to(ROOT)) for folder in ('docs', 'examples') for p in sorted((ROOT / folder).rglob('*.md'))]
    errors = []; links = 0
    for name in docs:
        path = ROOT / name
        if not path.is_file(): errors.append('Missing document: ' + name); continue
        text = path.read_text(encoding='utf-8')
        refs = re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)', text)
        refs += re.findall(r'(?:href|src)="([^"]+)"', text)
        for ref in refs:
            uri = urlsplit(ref)
            if uri.scheme or uri.netloc or not uri.path: continue
            target = (path.parent / unquote(uri.path)).resolve(); links += 1
            if not target.is_relative_to(ROOT) or not target.exists():
                errors.append(name + ': missing local target ' + ref)
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    if 'version-' + __version__ + '-' not in readme: errors.append('README badge differs from application version.')
    try:
        require_release_notes(__version__)
    except ValueError as exc:
        errors.append(str(exc))
    tag = os.environ.get('GITHUB_REF', '')
    if tag.startswith('refs/tags/v') and tag != 'refs/tags/v' + __version__:
        errors.append('Release tag differs from application version: ' + tag)
    for entry in examples():
        try: validate(example_copy(entry))
        except Exception as exc: errors.append(entry['id'] + ': ' + str(exc))
    if errors: raise RuntimeError('\n'.join(errors))
    print(json.dumps({'version': __version__, 'status': 'passed', 'documents': len(docs),
                      'local_links': links, 'gallery_examples': len(examples()),
                      'pdk_coverage': matrix}, indent=2))


if __name__ == '__main__': main()
