"""Select an explicitly requested public release or the normal draft preview."""
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def public_release_requested(version, event_name, ref, event):
    inputs = event.get('inputs') or {}
    manual = event_name == 'workflow_dispatch' and inputs.get('publish_release') in (True, 'true')
    message = (event.get('head_commit') or {}).get('message') or ''
    stable = bool(re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', version))
    version_commit = (event_name == 'push' and ref == 'refs/heads/main' and stable
                      and message.splitlines()[:1] == ['Release ' + version])
    requested = manual or version_commit
    if requested:
        if ref != 'refs/heads/main':
            raise ValueError('Public releases must be prepared from main.')
        if not stable:
            raise ValueError('Public releases require a plain X.Y.Z version.')
    return requested


def main():
    from icstudio import __version__
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    public = public_release_requested(__version__, os.environ['GITHUB_EVENT_NAME'],
                                      os.environ['GITHUB_REF'], event)
    value = 'true' if public else 'false'
    with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as output:
        output.write('public=' + value + '\n')
    print('Public release requested.' if public else 'Preparing a draft preview.')


if __name__ == '__main__':
    main()
