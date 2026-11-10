"""Require real physical checks from one explicitly selected frozen candidate."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import file_digest


def candidate_commit(expected, root=ROOT):
    """Authenticate HEAD without the unrelated, fallible working-tree UI query."""
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{40}', expected):
        raise ValueError('Select a full lowercase 40-character candidate commit.')
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    # Keep the existing Git deadline. A timeout/error fails explicitly rather
    # than becoming an "unknown" source identity after an expensive GUI run.
    actual = subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=root, env=env, text=True,
        stderr=subprocess.PIPE, timeout=3).strip()
    if actual != expected:
        raise ValueError(f'Physical acceptance checkout {actual!r} differs from candidate {expected}.')
    return actual


def validate_report(report, expected_commit, executable_sha256):
    if not isinstance(expected_commit, str) or not re.fullmatch('[0-9a-f]{40}', expected_commit):
        raise ValueError('Select a full lowercase 40-character candidate commit.')
    if report.get('status') != 'passed' or report.get('frozen') is not True:
        raise ValueError('Installed physical acceptance did not pass in a frozen application.')
    build = report.get('build', {})
    if (build.get('commit') != expected_commit or build.get('dirty') is not False
            or build.get('frozen') is not True):
        raise ValueError(f'Installed physical build {build!r} differs from clean frozen candidate {expected_commit}.')
    if report.get('executable_sha256') != executable_sha256:
        raise ValueError('Installed physical evidence belongs to a different executable.')


def verify(executable, pdk, out, expected_commit):
    candidate_commit(expected_commit)
    executable = Path(executable).resolve(strict=True)
    pdk = Path(pdk).resolve(strict=True)
    out = Path(out).resolve()
    # A failed/retried invocation must never consume an earlier passing report.
    out.mkdir(parents=True, exist_ok=False)
    before = file_digest(executable)
    command = [str(executable), '--physical-acceptance', '--managed',
               '--pdk', str(pdk), '--out', str(out/'probe')]
    receipt = dict(schema=1, status='failed', expected_commit=expected_commit,
                   executable=str(executable), executable_sha256=before,
                   command=command, scope='Selected installed physical workflow; not full device-family qualification.')
    try:
        env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}
        with (out/'launcher.log').open('wb') as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                           timeout=1200, check=True)
        report_path = out/'probe/report.json'
        report = json.loads(report_path.read_text(encoding='utf-8'))
        receipt['reported_build'] = report.get('build')
        receipt['report_sha256'] = file_digest(report_path)
        validate_report(report, expected_commit, before)
        if file_digest(executable) != before:
            raise ValueError('Installed executable changed during physical acceptance.')
        candidate_commit(expected_commit)
        receipt['status'] = 'passed'
    except Exception as error:
        receipt['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        (out/'acceptance.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    return receipt


def main(arguments=None):
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ('executable', 'pdk', 'out'):
        ap.add_argument('--'+key, type=Path, required=True)
    ap.add_argument('--expected-commit', required=True)
    args = ap.parse_args(arguments)
    verify(args.executable, args.pdk, args.out, args.expected_commit)
    print('Packaged DRC/LVS, fault navigation and repair passed for '+args.expected_commit+'.')


if __name__ == '__main__':
    main()
