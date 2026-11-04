"""Storage recovery never broadens into source, runtime or evidence cleanup."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import ci_hosted_storage as storage


HOSTED = dict(GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted', RUNNER_OS='Linux')


class HostedStorageTests(unittest.TestCase):
    def test_cleanup_rejects_local_self_hosted_and_windows_before_deleting(self):
        for platform, env in (('win32', HOSTED), ('linux', {}),
                              ('linux', dict(HOSTED, RUNNER_ENVIRONMENT='self-hosted')),
                              ('linux', dict(HOSTED, RUNNER_OS='Windows')),
                              ('linux', dict(HOSTED, GITHUB_ACTIONS='false'))):
            with self.subTest(platform=platform, env=env), patch.object(storage.sys, 'platform', platform), \
                    patch.dict(os.environ, env, clear=True), patch.object(storage.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'GitHub-hosted Linux'):
                    storage.cleanup([])
                run.assert_not_called()

    def test_target_set_is_fixed_and_cannot_accept_workspace_cache_or_temp_paths(self):
        self.assertEqual(storage.UNUSED_SDKS,
                         ('/usr/share/dotnet', '/usr/local/lib/android', '/opt/ghc'))
        for target in ('/', '/tmp', '/home/runner/work', '/opt/hostedtoolcache',
                       '/usr/share/dotnet/..', '/usr/share/dotnet/', 'build/digital-state'):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'allowlisted'):
                storage.validate_target(target)

    def test_linked_leaf_and_ancestors_or_changed_layout_reject(self):
        for linked in ('/usr', '/usr/share', '/usr/share/dotnet'):
            with self.subTest(linked=linked), patch.object(storage.os.path, 'islink', side_effect=lambda p: p == linked):
                with self.assertRaisesRegex(ValueError, 'Linked SDK'):
                    storage.validate_target('/usr/share/dotnet')
        with patch.object(storage.os.path, 'islink', return_value=False), \
                patch.object(storage.os.path, 'realpath', return_value='/elsewhere'):
            with self.assertRaisesRegex(ValueError, 'resolves elsewhere'):
                storage.validate_target('/usr/share/dotnet')

    def test_missing_sdk_is_tolerated_but_regular_file_is_rejected(self):
        with patch.object(storage.os.path, 'islink', return_value=False), \
                patch.object(storage.os.path, 'realpath', side_effect=lambda p: p), \
                patch.object(storage.os.path, 'lexists', return_value=False):
            self.assertFalse(storage.validate_target('/opt/ghc'))
        with patch.object(storage.os.path, 'islink', return_value=False), \
                patch.object(storage.os.path, 'realpath', side_effect=lambda p: p), \
                patch.object(storage.os.path, 'lexists', return_value=True), \
                patch.object(storage.os.path, 'isdir', return_value=False):
            with self.assertRaisesRegex(ValueError, 'not a directory'):
                storage.validate_target('/opt/ghc')

    def test_entire_allowlist_is_validated_before_first_deletion(self):
        with patch.object(storage, 'require_hosted_linux'), \
                patch.object(storage, 'validate_target', side_effect=[True, ValueError('unsafe')]), \
                patch.object(storage.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'unsafe'):
                storage.cleanup([])
            run.assert_not_called()

    def test_cleanup_uses_exact_bounded_commands_and_records_absent_sdks(self):
        actions = []
        with patch.object(storage, 'require_hosted_linux'), \
                patch.object(storage, 'validate_target', side_effect=[True, False, True, True, False, True]), \
                patch.object(storage.os.path, 'lexists', return_value=False), \
                patch.object(storage.subprocess, 'run') as run:
            storage.cleanup(actions)
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ['sudo', '-n', 'rm', '-rf', '--one-file-system', '--', '/usr/share/dotnet'],
            ['sudo', '-n', 'rm', '-rf', '--one-file-system', '--', '/opt/ghc']])
        self.assertTrue(all(call.kwargs == dict(check=True, timeout=180) for call in run.call_args_list))
        self.assertEqual([a['status'] for a in actions], ['removed', 'absent', 'removed'])

    def test_failed_deletion_propagates_and_does_not_delete_later_targets(self):
        actions = []
        with patch.object(storage, 'require_hosted_linux'), \
                patch.object(storage, 'validate_target', return_value=True), \
                patch.object(storage.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['sudo'])) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                storage.cleanup(actions)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(actions, [dict(path='/usr/share/dotnet', status='started')])

    def rows(self):
        return [dict(label=name, available_bytes=12 * storage.GIB, available_inodes=100000)
                for name in ('workspace', 'temporary')]

    def test_capacity_checks_bytes_and_inodes_on_both_filesystems(self):
        storage.require_capacity(self.rows(), 12, 100000)
        for index in (0, 1):
            for field, message in (('available_bytes', 'bytes'), ('available_inodes', 'inodes')):
                rows = self.rows(); rows[index][field] -= 1
                with self.subTest(index=index, field=field), self.assertRaisesRegex(ValueError, message):
                    storage.require_capacity(rows, 12, 100000)

    def test_preflight_failure_and_report_only_keep_diagnostics_without_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'storage.json'
            for mode, expected in (('check', 1), ('report', 0)):
                with self.subTest(mode=mode), patch.object(storage.sys, 'platform', 'linux'), \
                        patch.object(storage, 'snapshot', return_value=self.rows()), \
                        patch.object(storage, 'cleanup') as cleanup, patch('builtins.print'):
                    self.assertEqual(storage.main([mode, '--out', str(out), '--min-free-gib', '13']), expected)
                    cleanup.assert_not_called()
                report = json.loads(out.read_text())
                self.assertEqual(report['before'], report['after'])
                self.assertEqual(report['status'], 'passed' if expected == 0 else 'failed')
                self.assertEqual(report['cleanup'], [])

    def test_cleanup_failure_still_records_before_after_and_error(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(storage.sys, 'platform', 'linux'), \
                patch.object(storage, 'snapshot', return_value=self.rows()), \
                patch.object(storage, 'cleanup', side_effect=ValueError('unsafe fixture')), patch('builtins.print'):
            out = Path(tmp) / 'failed.json'
            self.assertEqual(storage.main(['cleanup', '--out', str(out)]), 1)
            report = json.loads(out.read_text())
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['error'], 'unsafe fixture')
            self.assertEqual(report['before'], report['after'])

    def test_cleanup_timeout_preserves_diagnostics_and_stops_later_deletions(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(storage.sys, 'platform', 'linux'), \
                patch.object(storage, 'snapshot', return_value=self.rows()), \
                patch.object(storage, 'require_hosted_linux'), \
                patch.object(storage, 'validate_target', return_value=True), \
                patch.object(storage.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['sudo'], 180)) as run, \
                patch('builtins.print'):
            out = Path(tmp) / 'timeout.json'
            self.assertEqual(storage.main(['cleanup', '--out', str(out)]), 1)
            report = json.loads(out.read_text())
            self.assertEqual(report['status'], 'failed')
            self.assertIn('timed out', report['error'])
            self.assertEqual(report['before'], report['after'])
            self.assertEqual(run.call_count, 1)
            self.assertEqual(report['cleanup'], [dict(path='/usr/share/dotnet', status='started')])

    @unittest.skipUnless(hasattr(os, 'statvfs'), 'Native Linux statvfs diagnostics.')
    def test_actual_snapshot_reports_byte_and_inode_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = storage.snapshot(Path(tmp), Path(tmp))
        for row in rows:
            self.assertGreater(row['total_bytes'], row['available_bytes'])
            self.assertGreaterEqual(row['total_inodes'], row['available_inodes'])
            self.assertGreater(row['available_inodes'], 0)


if __name__ == '__main__':
    unittest.main()
