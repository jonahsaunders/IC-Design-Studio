"""Reserve space on disposable hosted Linux workers without touching evidence.

Only unused preinstalled Android, .NET and Haskell SDKs may be removed. Python,
Node, C/C++ tools, caches, the checkout, PDKs and qualification state stay intact.
Free-space floors are operational reserves, not measured peak-size guarantees.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


UNUSED_SDKS = ('/usr/share/dotnet', '/usr/local/lib/android', '/opt/ghc')
GIB = 1024 ** 3


def require_hosted_linux():
    if (sys.platform != 'linux' or os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'
            or os.environ.get('RUNNER_OS') != 'Linux'):
        raise ValueError('SDK cleanup is limited to disposable GitHub-hosted Linux workers.')


def validate_target(target):
    if target not in UNUSED_SDKS:
        raise ValueError('SDK cleanup target is not allowlisted: ' + target)
    # Reject linked ancestors as well as a linked leaf, even when a link resolves
    # back to the same spelling. Never follow a runner image's changed layout.
    parts = target.strip('/').split('/')
    if any(os.path.islink('/' + '/'.join(parts[:n])) for n in range(1, len(parts) + 1)):
        raise ValueError('Linked SDK cleanup path: ' + target)
    if os.path.realpath(target) != target:
        raise ValueError('SDK cleanup path resolves elsewhere: ' + target)
    if not os.path.lexists(target):
        return False
    if not os.path.isdir(target):
        raise ValueError('SDK cleanup target is not a directory: ' + target)
    return True


def cleanup(actions):
    require_hosted_linux()
    # Validate the entire fixed set before starting any destructive operation.
    for target in UNUSED_SDKS:
        validate_target(target)
    for target in UNUSED_SDKS:
        if not validate_target(target):
            actions.append(dict(path=target, status='absent'))
            continue
        action = dict(path=target, status='started')
        actions.append(action)
        subprocess.run(['sudo', '-n', 'rm', '-rf', '--one-file-system', '--', target],
                       check=True, timeout=180)
        if os.path.lexists(target):
            raise ValueError('SDK cleanup did not remove target: ' + target)
        action['status'] = 'removed'


def snapshot(workspace, temporary):
    rows = []
    for label, path in (('workspace', workspace), ('temporary', temporary)):
        path = Path(path).resolve(strict=True)
        info = os.statvfs(path)
        rows.append(dict(label=label, path=str(path), device=path.stat().st_dev,
                         total_bytes=info.f_blocks * info.f_frsize,
                         available_bytes=info.f_bavail * info.f_frsize,
                         total_inodes=info.f_files, available_inodes=info.f_favail))
    return rows


def require_capacity(rows, min_free_gib, min_free_inodes):
    for row in rows:
        if row['available_bytes'] < min_free_gib * GIB:
            raise ValueError(f"Insufficient bytes on {row['label']}: "
                             f"{row['available_bytes']} available, {min_free_gib * GIB} required.")
        if row['available_inodes'] < min_free_inodes:
            raise ValueError(f"Insufficient inodes on {row['label']}: "
                             f"{row['available_inodes']} available, {min_free_inodes} required.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('cleanup', 'check', 'report'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--min-free-gib', type=int, default=12)
    parser.add_argument('--min-free-inodes', type=int, default=100000)
    args = parser.parse_args(argv)
    if args.min_free_gib < 0 or args.min_free_inodes < 0:
        parser.error('Storage reserves cannot be negative.')
    report = dict(schema=1, mode=args.mode, status='failed',
                  timestamp=datetime.now(timezone.utc).isoformat(),
                  run_id=os.environ.get('GITHUB_RUN_ID'),
                  run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),
                  commit=os.environ.get('GITHUB_SHA'), cleanup=[])
    code = 1
    try:
        if sys.platform != 'linux':
            raise ValueError('Storage preflight requires Linux statvfs diagnostics.')
        workspace = Path(os.environ.get('GITHUB_WORKSPACE', os.getcwd()))
        temporary = Path(tempfile.gettempdir())
        report['before'] = snapshot(workspace, temporary)
        if args.mode == 'cleanup':
            cleanup(report['cleanup'])
        report['after'] = snapshot(workspace, temporary)
        if args.mode != 'report':
            report['required'] = dict(available_bytes=args.min_free_gib * GIB,
                                      available_inodes=args.min_free_inodes)
            require_capacity(report['after'], args.min_free_gib, args.min_free_inodes)
        report['status'] = 'passed'
        code = 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
        # A failed deletion should still retain post-failure filesystem evidence.
        if 'before' in report and 'after' not in report:
            try:
                report['after'] = snapshot(workspace, temporary)
            except OSError as diagnostic_error:
                report['diagnostic_error'] = str(diagnostic_error)
    text = json.dumps(report, indent=2) + '\n'
    # Console diagnostics survive even if the filesystem cannot store the file.
    print(text, end='', flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding='utf-8')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
