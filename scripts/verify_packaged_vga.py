"""Run VGA qualification with an exact installed or extracted desktop executable."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import __version__
from icstudio.digital_vga import PRESET_IDS


def verify(executable, output, commit):
    executable, output = Path(executable).resolve(), Path(output).resolve()
    if not executable.is_file():
        raise ValueError('The packaged executable is missing: ' + str(executable))
    if output.exists():
        raise ValueError('Use a fresh VGA evidence directory: ' + str(output))
    output.mkdir(parents=True)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('ICSTUDIO_') and key not in ('PYTHONPATH', 'PYTHONHOME', 'PDK_ROOT')}
    # External HTTP(S) requests cannot succeed; loopback assets remain available.
    for key in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'all_proxy'):
        env[key] = 'http://127.0.0.1:9'
    env['NO_PROXY'] = env['no_proxy'] = '127.0.0.1,localhost'
    flags = '--disable-gpu --proxy-server=http://127.0.0.1:9 --proxy-bypass-list=127.0.0.1'
    env['QTWEBENGINE_CHROMIUM_FLAGS'] = flags
    env['QT_QUICK_BACKEND'] = 'software'
    command = [str(executable), '--vga-test', str(output / 'probe')]
    if os.name == 'nt':
        env['QT_QPA_PLATFORM'] = 'windows'
    else:
        env['QT_QPA_PLATFORM'] = 'xcb'
        command = ['xvfb-run', '-a', '-s', '-screen 0 1440x1000x24', *command]
    with (output / 'execution.log').open('wb') as log:
        result = subprocess.run(command, cwd=executable.parent, env=env,
                                stdout=log, stderr=subprocess.STDOUT, timeout=600)
    report_path = output / 'probe/vga-test.json'
    if result.returncode or not report_path.is_file():
        details = report_path.read_text() if report_path.is_file() else (output / 'execution.log').read_text(errors='replace')[-12000:]
        raise ValueError('Packaged VGA probe failed:\n' + details)
    report = json.loads(report_path.read_text())
    validate(report, commit)
    return report


def validate(report, commit):
    if not (report.get('status') == 'passed' and report.get('frozen') is True
            and report.get('version') == __version__ and report.get('build', {}).get('commit') == commit
            and report['build'].get('dirty') is False):
        raise ValueError('VGA evidence must come from the exact clean packaged version and commit')
    presets = report.get('presets', [])
    if len(presets) != 8 or {row['id'] for row in presets} != set(PRESET_IDS) or any(row['status'] != 'passed' for row in presets):
        raise ValueError('All eight packaged VGA presets must pass')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    report = verify(args.executable, args.output, commit)
    print(json.dumps({'status': report['status'], 'presets': len(report['presets']), 'commit': commit}))
