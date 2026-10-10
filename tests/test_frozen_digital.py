"""Frozen acceptance must be fresh, package-bound and complete on either OS."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from icstudio.model import clone, digest, file_digest
from scripts import verify_frozen_digital as verifier


class FrozenDigitalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.exe = self.root / 'application/ICDesignStudio.exe'
        self.exe.parent.mkdir()
        self.exe.write_bytes(b'fixture executable')
        self.payload = self.exe.parent / '_internal/icstudio/assets/runtime/digital'
        self.sources = self.payload / 'backend/icstudio'
        self.sources.mkdir(parents=True)
        (self.sources / 'digital_runtime.py').write_bytes(b'# fixture backend\n')
        self.state = self.root / 'state'
        self.evidence = self.state / 'checks/new-run'
        self.evidence.mkdir(parents=True)
        self.out = self.root / 'output'
        platforms = ['sky130hd', 'gf180', 'ihp-sg13g2']
        corners = {name: {'library_corners': ['typical'], 'interconnect_corners': []} for name in platforms}
        self.manifest = {'schema': 1, 'archive': 'runtime.tar.gz', 'sha256': 'a' * 64,
                         'platforms': platforms, 'platform_corners': corners,
                         'tools': ['magic', 'netgen', 'ngspice']}
        self.write(self.payload / 'manifest.json', self.manifest)
        self.ready = self.state / ('ready-' + self.manifest['sha256'] + '.json')
        self.record = {'runtime': {'kind': 'wsl' if os.name == 'nt' else 'linux', 'sha256': 'a' * 64},
                       'backend': digest({'digital_runtime.py': file_digest(self.sources / 'digital_runtime.py')}),
                       'manifest': digest(self.manifest), 'platforms': platforms, 'platform_corners': corners,
                       'evidence': str(self.evidence), 'checked': 'fresh'}
        stages = ('mapped', 'equivalence', 'fault-detected', 'timing', 'floorplan',
                  'gds', 'extracted-timing', 'physical-equivalence')
        names = ['icarus', 'verilator-coverage'] + [n + '/' + s for n in platforms for s in stages]
        self.report = {'status': 'PASS', 'runtime': self.record['runtime'], 'platforms': platforms,
                       'platform_corners': corners, 'checks': [
                           {'name': name, 'verdict': 'FAIL' if name.endswith('/fault-detected') else 'PASS'}
                           for name in names]}
        self.write(self.evidence / 'physical-tools/result.json', {'silicon_report': {'status': 'passed'}})
        self.state_patch = patch.object(verifier, 'state_root', return_value=self.state)
        self.state_patch.start()
        self.addCleanup(self.state_patch.stop)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def runner(self, command, **kwargs):
        kwargs['stdout'].write(b'{"message":"Ready. All installation checks passed."}\n')
        self.write(self.ready, self.record)
        self.write(self.evidence / 'report.json', self.report)
        return subprocess.CompletedProcess(command, 0)

    def test_complete_fresh_package_checks_use_bounded_deadline_and_no_source_override(self):
        # An unrelated, newer Ready record must never select another runtime.
        self.write(self.state / ('ready-' + 'b' * 64 + '.json'), {'unrelated': True})
        with patch.dict(os.environ, {'ICSTUDIO_DIGITAL_PAYLOAD': 'source checkout', 'ICSTUDIO_DIGITAL_NATIVE': '1'}), \
                patch.object(verifier.subprocess, 'run', side_effect=self.runner) as run:
            result = verifier.verify(self.exe, self.out)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(len(result['checks']), 26)
        self.assertEqual(result['executable_sha256'], file_digest(self.exe))
        self.assertEqual(result['backend_sha256'], self.record['backend'])
        self.assertEqual(result['acceptance_report_sha256'], file_digest(self.evidence / 'report.json'))
        self.assertGreater(run.call_args.kwargs['timeout'], 25 * 60)
        self.assertLessEqual(run.call_args.kwargs['timeout'], 3600)
        self.assertNotIn('ICSTUDIO_DIGITAL_PAYLOAD', run.call_args.kwargs['env'])
        self.assertNotIn('ICSTUDIO_DIGITAL_NATIVE', run.call_args.kwargs['env'])

    def test_stale_ready_replaces_old_success_with_failed_receipt(self):
        self.write(self.ready, self.record)
        self.write(self.out / 'report.json', {'status': 'PASS'})
        with patch.object(verifier.subprocess, 'run', side_effect=self.runner):
            with self.assertRaisesRegex(ValueError, 'fresh Ready'):
                verifier.verify(self.exe, self.out)
        self.assertEqual(json.loads((self.out / 'report.json').read_text())['status'], 'FAIL')

    def test_wrong_archive_backend_manifest_platforms_corners_and_os_are_rejected(self):
        original = clone(self.record)
        for fault in ('archive', 'backend', 'manifest', 'platforms', 'corners', 'os'):
            with self.subTest(fault=fault):
                self.ready.unlink(missing_ok=True)
                self.record = clone(original)
                if fault == 'archive': self.record['runtime']['sha256'] = 'b' * 64
                elif fault == 'backend': self.record['backend'] = 'old backend'
                elif fault == 'manifest': self.record['manifest'] = 'old manifest'
                elif fault == 'platforms': self.record['platforms'] = ['sky130hd']
                elif fault == 'corners': self.record['platform_corners'] = {}
                else: self.record['runtime']['kind'] = 'linux' if os.name == 'nt' else 'wsl'
                with patch.object(verifier.subprocess, 'run', side_effect=self.runner), self.assertRaises(ValueError):
                    verifier.verify(self.exe, self.out)

    def test_missing_check_false_fault_pass_missing_corner_and_failed_physical_are_rejected(self):
        original = clone(self.report)
        for fault in ('missing', 'duplicate', 'fault-pass', 'timing-fail', 'corners', 'physical'):
            with self.subTest(fault=fault):
                self.ready.unlink(missing_ok=True)
                self.report = clone(original)
                if fault == 'missing': self.report['checks'].pop()
                elif fault == 'duplicate': self.report['checks'].append(self.report['checks'][0])
                elif fault == 'fault-pass': self.report['checks'][4]['verdict'] = 'PASS'
                elif fault == 'timing-fail': self.report['checks'][8]['verdict'] = 'FAIL'
                elif fault == 'corners': self.report['platform_corners'] = {}
                else: self.write(self.evidence / 'physical-tools/result.json', {'silicon_report': {'status': 'failed'}})
                with patch.object(verifier.subprocess, 'run', side_effect=self.runner), self.assertRaises(ValueError):
                    verifier.verify(self.exe, self.out)

    def test_changed_executable_or_backend_during_setup_is_rejected(self):
        for path in (self.exe, self.sources / 'digital_runtime.py'):
            with self.subTest(path=path):
                self.ready.unlink(missing_ok=True)
                original = path.read_bytes()
                def changed(*args, **kwargs):
                    result = self.runner(*args, **kwargs)
                    path.write_bytes(original + b' changed')
                    return result
                with patch.object(verifier.subprocess, 'run', side_effect=changed), self.assertRaisesRegex(ValueError, 'changed during'):
                    verifier.verify(self.exe, self.out)
                path.write_bytes(original)

    def test_timeout_signals_new_owned_job_and_retains_failure(self):
        active = self.state / 'active-check.json'
        folder = self.evidence / 'gf180/gds'
        folder.mkdir(parents=True)
        def timeout(*args, **kwargs):
            self.write(active, {'directory': str(folder)})
            raise subprocess.TimeoutExpired(args[0], 0.1)
        with patch.object(verifier.subprocess, 'run', side_effect=timeout), self.assertRaises(subprocess.TimeoutExpired):
            verifier.verify(self.exe, self.out, timeout=0.1)
        self.assertTrue((folder / 'digital-cancel').is_file())
        self.assertEqual(json.loads((self.out / 'report.json').read_text())['status'], 'FAIL')
        self.assertFalse(self.ready.exists())

    def test_timeout_does_not_signal_old_or_outside_jobs(self):
        outside = self.root / 'unrelated'
        outside.mkdir()
        active = self.state / 'active-check.json'
        self.write(active, {'directory': str(self.evidence)})
        verifier.cancel_active(self.state, active.read_bytes())
        self.assertFalse((self.evidence / 'digital-cancel').exists())
        self.write(active, {'directory': str(outside)})
        verifier.cancel_active(self.state, None)
        self.assertFalse((outside / 'digital-cancel').exists())

    def test_missing_packaged_backend_fails_before_starting_application(self):
        (self.sources / 'digital_runtime.py').unlink()
        with patch.object(verifier.subprocess, 'run') as run, self.assertRaisesRegex(ValueError, 'missing its digital backend'):
            verifier.verify(self.exe, self.out)
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
