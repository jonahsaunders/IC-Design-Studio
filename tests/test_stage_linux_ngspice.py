"""Pinned runtime input, source/license retention and corrupted-cache boundaries."""
import copy
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import sys
import unittest
from unittest.mock import patch
import zipfile

from scripts import stage_linux_ngspice as stage
from scripts import stage_linux_ngspice_manifest as runtime_manifest


class LinuxRuntimeInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.archive = stage.ROOT / stage.ARCHIVE

    @staticmethod
    def locked(code=5):
        error = PermissionError(errno.EACCES, 'injected Windows sharing lock')
        error.winerror = code
        return error

    def test_transient_windows_locks_retry_verified_source_and_publish(self):
        real = stage.os.rename
        for code in (5, 32, 33):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'result'; calls = []
                def rename(source, target):
                    calls.append((Path(source), Path(target)))
                    if len(calls) < 3: raise self.locked(code)
                    return real(source, target)
                with patch.object(sys, 'platform', 'win32'), patch.object(stage.os, 'rename', side_effect=rename), patch.object(stage.time, 'sleep') as sleep:
                    stage.stage(self.archive, output)
                self.assertEqual(len(calls), 3); self.assertEqual(len(set(calls)), 1)
                self.assertEqual([c.args[0] for c in sleep.call_args_list], [.01, .02])
                self.assertEqual(stage.sha(output / 'runtime/ngspice'), stage.ENGINE_SHA256)
                stage.verify(output)

    def test_persistent_and_unrelated_rename_errors_fail_closed(self):
        for error, attempts, delays in ((self.locked(), 6, [.01, .02, .04, .08, .15]),
                                         (OSError(errno.ENOSPC, 'disk full'), 1, []),
                                         (PermissionError(errno.EACCES, 'unclassified access failure'), 1, []),
                                         (self.locked(87), 1, [])):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'result'
                with patch.object(sys, 'platform', 'win32'), patch.object(stage.os, 'rename', side_effect=error) as rename, patch.object(stage.time, 'sleep') as sleep:
                    with self.assertRaises(OSError) as caught: stage.stage(self.archive, output)
                self.assertIs(caught.exception, error); self.assertEqual(rename.call_count, attempts)
                self.assertEqual([c.args[0] for c in sleep.call_args_list], delays); self.assertFalse(output.exists())

    def test_competing_output_and_replaced_source_never_publish(self):
        for kind in ('destination', 'source', 'bytes'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'result'; calls = []
                def rename(source, target):
                    calls.append((source, target))
                    if kind == 'destination':
                        Path(target).mkdir(); (Path(target) / 'other').write_bytes(b'keep')
                    elif kind == 'source':
                        replacement = Path(source).with_name('retained-source')
                        os.replace(source, replacement); Path(source).mkdir()
                    else:
                        (Path(source) / 'runtime/ngspice').write_bytes(b'changed')
                    raise self.locked()
                with patch.object(sys, 'platform', 'win32'), patch.object(stage.os, 'rename', side_effect=rename), patch.object(stage.time, 'sleep'):
                    with self.assertRaises((ValueError, FileExistsError)): stage.stage(self.archive, output)
                self.assertEqual(len(calls), 1)
                if kind == 'destination': self.assertEqual((output / 'other').read_bytes(), b'keep')
                else: self.assertFalse(output.exists())

    def test_non_windows_rename_remains_single_attempt(self):
        error = self.locked()
        with tempfile.TemporaryDirectory() as tmp, patch.object(sys, 'platform', 'linux'), patch.object(stage.os, 'rename', side_effect=error) as rename, patch.object(stage.time, 'sleep') as sleep:
            with self.assertRaises(OSError) as caught: stage.stage(self.archive, Path(tmp) / 'result')
        self.assertIs(caught.exception, error); rename.assert_called_once(); sleep.assert_not_called()

    def test_staging_and_destination_parent_substitution_reject(self):
        for kind in ('staging-parent', 'destination-parent'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); source_parent = root / 'source-parent'; source_parent.mkdir()
                target_parent = root / 'target-parent'; target_parent.mkdir()
                source = source_parent / 'ready'; source.mkdir(); target = target_parent / 'result'
                def substitute(*args):
                    parent = source_parent if kind == 'staging-parent' else target_parent
                    os.replace(parent, root / 'retained-parent'); parent.mkdir()
                    if kind == 'staging-parent': (parent / 'ready').mkdir()
                    raise self.locked()
                with patch.object(sys, 'platform', 'win32'), patch.object(stage.os, 'rename', side_effect=substitute) as rename, patch.object(stage.time, 'sleep'):
                    with self.assertRaisesRegex(ValueError, 'changed during publication'):
                        stage.publish(source, target)
                rename.assert_called_once(); self.assertFalse(target.exists())

    @unittest.skipUnless(os.name == 'nt', 'Native Windows directory-sharing semantics')
    def test_real_short_lived_reader_lock_releases_before_retry(self):
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle; close.argtypes = [wintypes.HANDLE]; close.restype = wintypes.BOOL
        real = stage.os.rename; real_sleep = stage.time.sleep; handle = None; calls = []; denied = []; delays = []
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'result'
            def rename(source, target):
                nonlocal handle
                calls.append((source, target))
                if len(calls) == 1:
                    handle = create(str(Path(source) / 'runtime/ngspice'), 0x80000000, 3, None, 3, 128, None)
                    if handle == ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
                try: return real(source, target)
                except OSError as exc: denied.append(getattr(exc, 'winerror', None)); raise
            def release(delay):
                nonlocal handle
                delays.append(delay)
                if handle is not None:
                    self.assertTrue(close(handle)); handle = None
                real_sleep(delay)
            try:
                with patch.object(stage.os, 'rename', side_effect=rename), patch.object(stage.time, 'sleep', side_effect=release):
                    stage.stage(self.archive, output)
            finally:
                if handle is not None: close(handle)
            self.assertGreaterEqual(len(calls), 2); self.assertLessEqual(len(calls), 6)
            self.assertEqual(len(denied), len(calls) - 1); self.assertIn(denied[0], (5, 32, 33))
            self.assertEqual(delays, [.01, .02, .04, .08, .15][:len(delays)])
            self.assertIsNone(handle)
            stage.verify(output)

    def test_exact_archive_stages_and_retains_all_sources_and_licenses(self):
        output = self.root / 'runtime-input'
        engine = stage.stage(self.archive, output)
        self.assertEqual(stage.sha(engine), stage.ENGINE_SHA256)
        self.assertEqual(stage.stage(self.archive, output), engine)
        files = stage.deployment_files(output)
        self.assertIn('sources/ngspice-47.tar.gz', files)
        self.assertIn('sources/capacitor-multiplier.patch', files)
        self.assertIn('licenses/ngspice/COPYING', files)
        final = self.root / 'final'
        final.mkdir()
        for name, path in files.items():
            dest = final / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        verified = stage.verify_deployed(final)
        self.assertEqual(verified['ngspice'], stage.ENGINE_SHA256)
        self.assertEqual(len(verified), 35)
        (final / 'licenses/ngspice/COPYING').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            stage.verify_deployed(final)

    def test_changed_archive_fails_before_output_creation(self):
        bad = self.root / 'bad.zip'
        bad.write_bytes(b'not the pinned runtime')
        out = self.root / 'out'
        with self.assertRaisesRegex(ValueError, 'Unreviewed Linux runtime archive'):
            stage.stage(bad, out)
        self.assertFalse(out.exists())

    def test_schema_two_binds_exact_deployment_and_retained_provenance(self):
        source = self.root / 'source'
        engine = stage.stage(self.archive, source)
        self.assertEqual(runtime_manifest.source_hash(engine), stage.ENGINE_SHA256)
        final = self.root / 'final'
        final.mkdir()
        for name, path in stage.deployment_files(source).items():
            dest = final / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        record = runtime_manifest.stage(final, stage.ENGINE_SHA256)
        self.assertEqual(record['schema'], 2)
        self.assertEqual(record['source_archive_sha256'], stage.ARCHIVE_SHA256)
        self.assertEqual(record['source_manifest_sha256'], stage.MANIFEST_SHA256)
        self.assertEqual(record['source_engine_sha256'], record['final_engine_sha256'])
        self.assertEqual(record['files'], stage.verify_deployed(final))
        self.assertEqual(record, json.loads((final / 'runtime-manifest.json').read_bytes()))
        self.assertEqual(runtime_manifest.stage(final, stage.ENGINE_SHA256), record)
        (final / 'sources/capacitor-multiplier.patch').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            runtime_manifest.stage(final, stage.ENGINE_SHA256)
        self.assertEqual(record, json.loads((final / 'runtime-manifest.json').read_bytes()))

    def test_source_identity_requires_complete_reviewed_inputs(self):
        source = self.root / 'source'
        engine = stage.stage(self.archive, source)
        (source / 'licenses/ngspice/COPYING').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Changed runtime input'):
            runtime_manifest.source_hash(engine)

    def test_generated_output_removes_only_exact_legacy_windows_inputs(self):
        source = self.root / 'source'
        stage.stage(self.archive, source)
        final = self.root / 'final'
        final.mkdir()
        for name, path in stage.deployment_files(source).items():
            dest = final / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        notice = final / 'COPYING.txt'
        content = b'Exact prior Windows notice fixture'
        notice.write_bytes(content)
        known = {'COPYING.txt': hashlib.sha256(content).hexdigest()}
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            stage.verify_deployed(final)
        with patch.object(stage, 'LEGACY_WINDOWS_FILES', known):
            self.assertEqual(len(stage.finalize_deployed(final)), 35)
        self.assertFalse(notice.exists())
        self.assertEqual(len(stage.verify_deployed(final)), 35)
        self.assertTrue((final / 'licenses/ngspice/COPYING').is_file())

    def test_unknown_or_changed_generated_legacy_file_is_never_removed(self):
        source = self.root / 'source'
        stage.stage(self.archive, source)
        final = self.root / 'final'
        final.mkdir()
        for name, path in stage.deployment_files(source).items():
            dest = final / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        notice = final / 'COPYING.txt'
        notice.write_bytes(b'Unknown notice')
        with self.assertRaisesRegex(ValueError, 'no legacy files removed'):
            stage.finalize_deployed(final)
        self.assertEqual(notice.read_bytes(), b'Unknown notice')
        with patch.object(stage, 'LEGACY_WINDOWS_FILES', {'COPYING.txt': stage.sha(notice)}):
            extra = final / 'unknown'
            extra.write_bytes(b'Unreviewed extra')
            with self.assertRaisesRegex(ValueError, 'no legacy files removed'):
                stage.finalize_deployed(final)
            self.assertTrue(notice.is_file())
            self.assertEqual(extra.read_bytes(), b'Unreviewed extra')

    def test_changed_cached_engine_or_extra_member_cannot_be_reused(self):
        out = self.root / 'out'
        engine = stage.stage(self.archive, out)
        original = engine.read_bytes()
        engine.write_bytes(original + b'changed')
        with self.assertRaisesRegex(ValueError, 'Changed runtime input'):
            stage.stage(self.archive, out)
        self.assertEqual(engine.read_bytes(), original + b'changed')
        engine.write_bytes(original)
        (out / 'injected-input').write_bytes(b'additional')
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            stage.stage(self.archive, out)

    def test_manifest_substitution_and_linked_inputs_reject(self):
        out = self.root / 'out'
        stage.stage(self.archive, out)
        manifest = out / 'manifest.json'
        manifest.write_bytes(manifest.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'Unreviewed runtime manifest'):
            stage.verify(out)
        original = Path.is_junction
        with patch.object(Path, 'is_junction', lambda p: p == out or original(p)):
            with self.assertRaisesRegex(ValueError, 'Linked runtime input'):
                stage.verify(out)

    def test_duplicate_member_rejected_even_with_matching_outer_archive_digest(self):
        altered = self.root / 'duplicate.zip'
        with zipfile.ZipFile(self.archive) as src, zipfile.ZipFile(altered, 'w') as dst:
            for member in src.infolist():
                dst.writestr(copy.copy(member), src.read(member.filename))
            with self.assertWarns(UserWarning):
                dst.writestr('runtime/ngspice', src.read('runtime/ngspice'))
        with patch.object(stage, 'ARCHIVE_SHA256', stage.sha(altered)):
            with self.assertRaisesRegex(ValueError, 'Duplicate runtime member'):
                stage.stage(altered, self.root / 'out')
        self.assertFalse((self.root / 'out').exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX execute bits are checked on native Linux.')
    def test_final_engine_execute_bit_cannot_be_lost(self):
        source = self.root / 'input'
        stage.stage(self.archive, source)
        final = self.root / 'final'
        final.mkdir()
        for name, path in stage.deployment_files(source).items():
            dest = final / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        stage.verify_deployed(final)
        (final / 'ngspice').chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'not executable'):
            stage.verify_deployed(final)


if __name__ == '__main__':
    unittest.main()
