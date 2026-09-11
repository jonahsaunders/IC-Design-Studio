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


def main():
    docs = ['docs/WORKFLOW_REVIEW_0.22.md', 'docs/SCHEMATIC_COLLABORATION.md', 'docs/PROFESSIONAL_WORKFLOWS.md', 'README.md', 'CONTRIBUTING.md', 'examples/README.md', 'docs/GETTING_STARTED.md', 'docs/LAYOUT_3D.md', 'docs/LIVE_COLLABORATION.md',
            'docs/PDK_GUIDE.md', 'docs/PROJECT_HUB.md', 'docs/ROADMAP.md', 'docs/DOWNLOADS.md',
            'docs/RELEASING.md', 'docs/RELEASE_STATUS.md', 'docs/LAYOUT_SCALE_AND_COLLABORATION.md', 'docs/RELEASE_0.22.md', 'docs/QUALIFICATION_0.22.md', 'docs/RELEASE_FOLLOWUPS.md', 'docs/RELEASE_0.21.md', 'docs/UPDATE_0.21.1.md', 'docs/UPDATE_0.22.md', 'docs/PRIORITIES_0.22.md', 'docs/STABILITY_0.22.md', 'docs/GESTURES_0.22.md', 'docs/DRAWING_0.22.md']
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
    tag = os.environ.get('GITHUB_REF', '')
    if tag.startswith('refs/tags/v') and tag != 'refs/tags/v' + __version__:
        errors.append('Release tag differs from application version: ' + tag)
    for entry in examples():
        try: validate(example_copy(entry))
        except Exception as exc: errors.append(entry['id'] + ': ' + str(exc))
    if errors: raise RuntimeError('\n'.join(errors))
    print(json.dumps({'version': __version__, 'status': 'passed', 'documents': len(docs),
                      'local_links': links, 'gallery_examples': len(examples())}, indent=2))


if __name__ == '__main__': main()
