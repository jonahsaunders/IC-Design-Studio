"""Bounded source feedback with timings; never a substitute for release acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
UNIT_MODULES = (
    'test_ci_candidate', 'test_ci_feedback', 'test_reference_toolchain', 'test_checkout_integrity',
    'test_core', 'test_lifecycle', 'test_workflows', 'test_project_pdk',
    'test_pdk_templates', 'test_student_physical', 'test_layout_verification',
    'test_digital_bundle', 'test_digital_runtime', 'test_digital_rc',
    'test_release_acceptance', 'test_release_evidence', 'test_release_intent',
    'test_pdk_qualification_matrix', 'test_ihp_hv_mos_layouts', 'test_sky130_li_linked',
    'test_resistor_layout_qualification', 'test_sky130_metal_resistor_layouts',
    'test_sky130_li_resume', 'test_sky130_mim_passive_corners', 'test_sky130_mim_passive_audit',
)


def check_syntax(root=ROOT):
    files = sorted(path for folder in ('icstudio', 'scripts', 'tests')
                   for path in (root / folder).glob('*.py'))
    for path in files:
        compile(path.read_bytes(), str(path), 'exec')
    return len(files)


def source_identity(root=ROOT):
    files = [path for folder in ('icstudio', 'scripts', 'tests')
             for path in (root / folder).glob('*.py')]
    files += list((root / '.github/workflows').glob('*.yml'))
    files += list(root.glob('requirements*.txt'))
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


def stages():
    return [
        ('unit-contracts', [sys.executable, '-m', 'unittest',
                            *('tests.' + name for name in UNIT_MODULES), '-v']),
        ('release-contracts', [sys.executable, 'scripts/check_release.py']),
        ('menu-smoke', [sys.executable, 'tests/gui_menu_audit.py']),
        ('project-hub-smoke', [sys.executable, 'tests/gui_project_hub.py']),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/ci-feedback')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update(QT_QPA_PLATFORM='offscreen', PYTHONPATH=str(ROOT / 'tests'), PYTHONUTF8='1')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, env=env, text=True).strip()
    if env.get('GITHUB_SHA') and commit != env['GITHUB_SHA']:
        raise ValueError('The feedback checkout must match the GitHub event SHA, including PR/merge-queue merge commits.')
    report = {'schema': 1, 'commit': commit, 'event': env.get('GITHUB_EVENT_NAME', 'local'),
              'scope': __doc__, 'release_acceptance': False, 'stages': [], 'status': 'running',
              'source_files_sha256': source_identity()}
    started = time.monotonic()
    def save():
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    try:
        report['syntax_files'] = check_syntax()
        save()
        for name, command in stages():
            step_start = time.monotonic()
            print('Running ' + name, flush=True)
            with (args.output / (name + '.log')).open('w', encoding='utf-8') as log:
                try:
                    result = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                            stderr=subprocess.STDOUT, timeout=300)
                    returncode = result.returncode
                except subprocess.TimeoutExpired:
                    returncode = 124
            report['stages'].append({'name': name, 'returncode': returncode,
                                    'elapsed_seconds': round(time.monotonic() - step_start, 3)})
            save()
            if returncode:
                print((args.output / (name + '.log')).read_text(encoding='utf-8'), flush=True)
                raise RuntimeError(f'{name} failed with exit code {returncode}; see the retained log.')
        if source_identity() != report['source_files_sha256']:
            raise RuntimeError('Source files changed during feedback; keep this run as invalid and run the final sources again.')
        report['status'] = 'passed'
    except Exception as exc:
        report.update(status='failed', error=str(exc), first_failure_seconds=round(time.monotonic() - started, 3))
        raise
    finally:
        save()
        print(json.dumps({k: v for k, v in report.items() if k != 'source_files_sha256'}, indent=2), flush=True)


if __name__ == '__main__':
    main()
