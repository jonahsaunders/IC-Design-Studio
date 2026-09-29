"""Create an attempt-specific draft without modifying older releases."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def preview_tag(version, branch, commit, run_id, attempt):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:[.-][A-Za-z0-9]+)*', version):
        raise ValueError('Invalid preview version.')
    if branch not in ('main', 'experimental'):
        raise ValueError('Only main and experimental produce automatic previews.')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Use the complete source commit SHA.')
    if any(not re.fullmatch(r'[1-9][0-9]*', str(value)) for value in (run_id, attempt)):
        raise ValueError('Use the GitHub run ID and positive run attempt.')
    # A failed asset upload can leave a partial draft. A rerun must get its own
    # identity rather than overwrite that draft or mix separately rebuilt assets.
    return f'{branch}-v{version}-{commit}-{run_id}-{attempt}'


def publish(directory, version, branch, commit, run_id, attempt, repository,
            *, root=ROOT, run=subprocess.run):
    from scripts.release_evidence import preflight_assets
    tag = preview_tag(version, branch, commit, run_id, attempt)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Use an explicit owner/repository for the preview.')
    note_version = re.sub(r'^(\d+\.\d+)\.0\.dev(\d+)$', r'\1_DEV\2', version)
    notes = Path(root) / 'docs' / f'UPDATE_{note_version}.md'
    if not notes.is_file():
        raise ValueError('Matching release notes are missing: ' + notes.name)
    assets = preflight_assets(directory)
    command = ['gh', 'release', 'create', tag, *[str(p.resolve()) for p in assets],
               '--repo', repository, '--draft', '--prerelease', '--target', commit,
               '--title', f'IC Design Studio {version} — {branch} preview ({run_id}/{attempt})',
               '--notes-file', str(notes.resolve())]
    run(command, check=True)
    return tag


def main():
    from icstudio import __version__
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--version', default=__version__)
    parser.add_argument('--branch', default=os.environ.get('RELEASE_BRANCH', ''))
    parser.add_argument('--commit', default=os.environ.get('RELEASE_COMMIT', ''))
    parser.add_argument('--run-id', default=os.environ.get('GITHUB_RUN_ID', ''))
    parser.add_argument('--attempt', default=os.environ.get('GITHUB_RUN_ATTEMPT', ''))
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY', ''))
    args = parser.parse_args()
    print(publish(args.directory, args.version, args.branch, args.commit,
                  args.run_id, args.attempt, args.repository))


if __name__ == '__main__':
    main()
