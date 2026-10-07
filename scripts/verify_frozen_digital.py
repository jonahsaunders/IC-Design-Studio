"""Exercise managed dispatch and require fresh evidence from the frozen application."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.digital_runtime import state_root
from icstudio.model import atomic_write, digest, file_digest
from scripts.check_digital_qualification import validate

# Three process profiles and independent SKY130 RC extraction take more than
# the old 1,100-second single-platform limit on the Windows CI runner. Keep the
# complete acceptance design and a bounded total deadline (CI allows 65 minutes).
SETUP_TIMEOUT = 3600


def snapshot(path):
    return path.read_bytes() if path.is_file() else None


def cancel_active(state, previous):
    """Signal only a new acceptance job beneath this verifier's state directory."""
    active = state / 'active-check.json'
    try:
        current = snapshot(active)
        if current is None or current == previous:
            return
        folder = Path(json.loads(current)['directory']).resolve()
        checks = (state / 'checks').resolve()
        if folder.is_relative_to(checks) and folder != checks and folder.is_dir():
            from icstudio.digital_backend import cancel
            cancel(folder)
    except (OSError, ValueError, KeyError, TypeError):
        pass


def check_acceptance(record, report, manifest, backend):
    validate({'sha256': manifest['sha256'], 'acceptance': record}, manifest,
             backend, 'Windows' if os.name == 'nt' else 'Linux')
    names = manifest.get('platforms', ['sky130hd'])
    if (report.get('status') != 'PASS' or report.get('runtime') != record['runtime']
            or report.get('platforms') != names
            or report.get('platform_corners') != record.get('platform_corners')):
        raise ValueError('Frozen digital acceptance is incomplete or belongs to another runtime.')
    stages = ('mapped', 'equivalence', 'fault-detected', 'timing', 'floorplan',
              'gds', 'extracted-timing', 'physical-equivalence')
    expected = ['icarus', 'verilator-coverage'] + [name + '/' + stage for name in names for stage in stages]
    checks = report.get('checks')
    if not isinstance(checks, list) or [c.get('name') for c in checks] != expected:
        raise ValueError('Frozen acceptance must retain every installation check exactly once.')
    for check in checks:
        name = check['name'].split('/')[-1]
        if name == 'fault-detected' and check.get('verdict') != 'FAIL':
            raise ValueError('Frozen acceptance did not detect the deliberate mapped fault.')
        if name in ('verilator-coverage', 'equivalence', 'extracted-timing', 'physical-equivalence') and check.get('verdict') != 'PASS':
            raise ValueError('Frozen acceptance has an unqualified check: ' + check['name'])


def verify(executable, out, timeout=SETUP_TIMEOUT):
    executable = Path(executable).resolve()
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / 'report.json'
    report_path.unlink(missing_ok=True)
    state = state_root().resolve()
    previous_active = snapshot(state / 'active-check.json')
    started = time.monotonic()
    try:
        if timeout <= 0:
            raise ValueError('The frozen setup deadline must be positive.')
        payload = executable.parent / '_internal/icstudio/assets/runtime/digital'
        manifest = json.loads((payload / 'manifest.json').read_text())
        if manifest.get('schema') != 1 or manifest.get('archive') != 'runtime.tar.gz':
            raise ValueError('The frozen application has an invalid digital manifest.')
        sources = payload / 'backend/icstudio'
        if not (sources / 'digital_runtime.py').is_file():
            raise ValueError('The frozen application is missing its digital backend.')
        backend_files = {p.name: file_digest(p) for p in sorted(sources.glob('*.py'))}
        backend = digest(backend_files)
        executable_sha = file_digest(executable)
        ready_path = state / ('ready-' + manifest['sha256'] + '.json')
        previous_ready = snapshot(ready_path)
        env = dict(os.environ)
        # A source-checkout override must never qualify a missing packaged runtime.
        env.pop('ICSTUDIO_DIGITAL_PAYLOAD', None)
        env.pop('ICSTUDIO_DIGITAL_NATIVE', None)
        with (out / 'setup.log').open('wb') as log:
            subprocess.run([str(executable), '--digital-setup'], env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout)
        if 'Ready.' not in (out / 'setup.log').read_text(encoding='utf-8', errors='replace'):
            raise ValueError('The frozen setup worker did not deliver its completion/progress stream.')
        current_ready = snapshot(ready_path)
        if current_ready is None or current_ready == previous_ready:
            raise ValueError('Frozen setup returned without fresh Ready evidence for this package.')
        record = json.loads(current_ready)
        evidence = Path(record['evidence']).resolve()
        if not evidence.is_relative_to(state / 'checks') or evidence == state / 'checks':
            raise ValueError('Frozen acceptance evidence is outside this installation state.')
        report_file = evidence / 'report.json'
        report = json.loads(report_file.read_text())
        check_acceptance(record, report, manifest, backend)
        if {'magic', 'netgen', 'ngspice'} <= set(manifest.get('tools', [])):
            physical_file = evidence / 'physical-tools/result.json'
            physical = json.loads(physical_file.read_text())
            if physical.get('silicon_report', {}).get('status') != 'passed':
                raise ValueError('Frozen physical tool acceptance did not pass.')
        if (file_digest(executable) != executable_sha
                or json.loads((payload / 'manifest.json').read_text()) != manifest
                or {p.name: file_digest(p) for p in sorted(sources.glob('*.py'))} != backend_files):
            raise ValueError('The frozen application changed during acceptance.')
        result = {'status': 'PASS', 'executable': str(executable), 'executable_sha256': executable_sha,
                  'manifest': manifest, 'backend_sha256': backend, 'installation': record,
                  'ready_sha256': file_digest(ready_path), 'acceptance_report_sha256': file_digest(report_file),
                  'checks': report['checks'], 'seconds': time.monotonic() - started, 'timeout_seconds': timeout}
        atomic_write(report_path, json.dumps(result, indent=2))
        return result
    except Exception as exc:
        if isinstance(exc, subprocess.TimeoutExpired):
            cancel_active(state, previous_active)
        atomic_write(report_path, json.dumps({'status': 'FAIL', 'executable': str(executable),
            'error': str(exc), 'seconds': time.monotonic() - started, 'timeout_seconds': timeout}, indent=2))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, default=ROOT / 'dist/ICDesignStudio' /
                        ('ICDesignStudio.exe' if os.name == 'nt' else 'ICDesignStudio'))
    parser.add_argument('--output', type=Path, default=ROOT / 'build/digital-frozen-evidence')
    parser.add_argument('--timeout', type=float, default=SETUP_TIMEOUT)
    args = parser.parse_args()
    result = verify(args.executable, args.output, args.timeout)
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'seconds': result['seconds']}))


if __name__ == '__main__':
    main()
