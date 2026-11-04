import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from icstudio import digital_platform as platform
from icstudio.model import file_digest


class WslPlatformCaptureTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / 'source.gds'
        self.target = root / 'target.gds'
        self.source.write_bytes(b'locked platform asset')
        self.record = {'path': 'source.gds', 'sha256': file_digest(self.source)}

    def run_retryable(self, copy=None, digest=None):
        with mock.patch.object(platform, '_wsl_capture_destination', return_value=True), \
             mock.patch.object(platform.time, 'sleep') as sleep, \
             mock.patch.object(platform.shutil, 'copy2', side_effect=copy or shutil.copyfile) as copier, \
             mock.patch.object(platform, 'file_digest', side_effect=digest or file_digest) as hasher, \
             contextlib.redirect_stderr(io.StringIO()) as warnings:
            platform._capture_file(self.source, self.target, self.record)
            return copier.call_count, hasher.call_count, sleep.call_count, warnings.getvalue()

    def test_windows_exact_unc_server_only(self):
        yes = [r'\\wsl.localhost\Ubuntu\file', r'\\?\UNC\wsl.localhost\Ubuntu\file',
               r'\\WSL.LOCALHOST\Ubuntu\file']
        no = [r'\\wsl.localhost.evil\Ubuntu\file', r'\\wsl.localhost@evil\Ubuntu\file',
              r'\\other\wsl.localhost\file', r'\\wsl$\Ubuntu\file',
              r'C:\wsl.localhost\Ubuntu\file', r'\\?\UNC\other\wsl.localhost\file']
        with mock.patch.object(platform.sys, 'platform', 'win32'):
            for value in yes:
                with self.subTest(value=value): self.assertTrue(platform._wsl_capture_destination(value))
            for value in no:
                with self.subTest(value=value): self.assertFalse(platform._wsl_capture_destination(value))
        with mock.patch.object(platform.sys, 'platform', 'linux'):
            for value in yes:
                self.assertFalse(platform._wsl_capture_destination(value))

    def test_copy_denial_retries_full_copy_and_hash(self):
        calls = []
        def copy(source, target):
            calls.append(1)
            if len(calls) == 1:
                shutil.copyfile(source, target)  # A complete target after an exception is not accepted.
                raise PermissionError('busy')
            shutil.copyfile(source, target)
        copies, hashes, sleeps, warning = self.run_retryable(copy=copy)
        self.assertEqual((copies, hashes, sleeps), (2, 2, 1))
        self.assertIn('retrying source.gds', warning)
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())

    def test_target_hash_denial_retries_copy_and_rechecks_source(self):
        calls = []
        def digest(path):
            calls.append(path)
            if len(calls) == 1: raise PermissionError('target locked')
            return file_digest(path)
        copies, hashes, sleeps, _ = self.run_retryable(digest=digest)
        self.assertEqual((copies, hashes, sleeps), (2, 3, 1))
        self.assertEqual(calls, [self.target, self.source, self.target])

    def test_permanent_denial_stops_after_three_attempts(self):
        with mock.patch.object(platform, '_wsl_capture_destination', return_value=True), \
             mock.patch.object(platform.time, 'sleep') as sleep, \
             mock.patch.object(platform.shutil, 'copy2', side_effect=PermissionError('busy')) as copier, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(PermissionError): platform._capture_file(self.source, self.target, self.record)
            self.assertEqual((copier.call_count, sleep.call_count), (3, 2))

    def test_checksum_mismatch_and_other_oserror_do_not_retry(self):
        for error in (None, OSError('disk error')):
            def copy(source, target):
                if error: raise error
                Path(target).write_bytes(b'wrong')
            with self.subTest(error=error), \
                 mock.patch.object(platform, '_wsl_capture_destination', return_value=True), \
                 mock.patch.object(platform.time, 'sleep') as sleep, \
                 mock.patch.object(platform.shutil, 'copy2', side_effect=copy) as copier:
                with self.assertRaises(OSError if error else ValueError):
                    platform._capture_file(self.source, self.target, self.record)
                self.assertEqual(copier.call_count, 1)
                sleep.assert_not_called()

    def test_source_changed_after_denial_is_not_retried(self):
        def copy(source, target):
            self.source.write_bytes(b'mutated')
            raise PermissionError('busy')
        with mock.patch.object(platform, '_wsl_capture_destination', return_value=True), \
             mock.patch.object(platform.time, 'sleep'), \
             mock.patch.object(platform.shutil, 'copy2', side_effect=copy) as copier, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'Platform changed during capture'):
                platform._capture_file(self.source, self.target, self.record)
            self.assertEqual(copier.call_count, 1)

    def test_other_destinations_do_not_retry_permission_error(self):
        with mock.patch.object(platform, '_wsl_capture_destination', return_value=False), \
             mock.patch.object(platform.time, 'sleep') as sleep, \
             mock.patch.object(platform.shutil, 'copy2', side_effect=PermissionError('busy')) as copier:
            with self.assertRaises(PermissionError): platform._capture_file(self.source, self.target, self.record)
            self.assertEqual(copier.call_count, 1)
            sleep.assert_not_called()

    def test_stage_verifies_before_capture(self):
        manifest = {'root': str(self.source.parent), 'files': [self.record]}
        with mock.patch.object(platform, 'verify', side_effect=ValueError('invalid platform')) as verify, \
             mock.patch.object(platform, '_capture_file') as capture:
            with self.assertRaisesRegex(ValueError, 'invalid platform'):
                platform.stage(manifest, self.target)
            verify.assert_called_once_with(manifest)
            capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()
