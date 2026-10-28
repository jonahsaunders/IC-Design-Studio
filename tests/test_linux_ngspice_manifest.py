"""Focused packaging and existing ESD runtime-manifest boundary tests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import stage_linux_ngspice_manifest as stage
from icstudio import esd_desktop_probe as probe


def fixture_sha(path):
    data = Path(path).read_bytes()
    if data == b'\x7fELF reviewed engine': return stage.ENGINE_SHA256
    if data == b'reviewed initializer': return stage.SPINIT_SHA256
    return hashlib.sha256(data).hexdigest()


class LinuxManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'ngspice').write_bytes(b'\x7fELF reviewed engine')
        (self.root/'spinit').write_bytes(b'reviewed initializer')
        (self.root/'COPYING.txt').write_bytes(b'license')
        # The tracked Windows metadata is replaced, not treated as Linux membership.
        (self.root/'runtime-manifest.json').write_text('{"files":{"ngspice.exe":"windows"}}')
        self.hash_patch = patch.object(stage, 'sha', side_effect=fixture_sha)
        self.hash_patch.start()
        self.addCleanup(self.hash_patch.stop)

    def test_exact_final_inventory_and_retained_support_changes_rejected(self):
        self.assertEqual(stage.source_hash(self.root/'ngspice'), stage.ENGINE_SHA256)
        record = stage.stage(self.root, stage.ENGINE_SHA256)
        self.assertEqual(record, json.loads((self.root/'runtime-manifest.json').read_text()))
        self.assertEqual(set(record['files']), {'ngspice', 'spinit', 'COPYING.txt'})
        self.assertEqual((record['schema'], record['platform']), (1, 'linux'))
        self.assertEqual(record['source_engine_sha256'], record['final_engine_sha256'])
        with patch.object(probe, 'file_digest', side_effect=fixture_sha):
            self.assertEqual(probe.runtime_identity(self.root/'ngspice', None, True)['files'], record['files'])
            (self.root/'COPYING.txt').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Runtime payload differs'):
                probe.runtime_identity(self.root/'ngspice', None, True)

    def test_missing_or_changed_reviewed_files_fail(self):
        for name in ('ngspice', 'spinit'):
            for content in (None, b'changed'):
                with self.subTest(name=name, content=content):
                    target = self.root/name
                    old = target.read_bytes()
                    if content is None: target.unlink()
                    else: target.write_bytes(content)
                    with self.assertRaises(ValueError):
                        stage.stage(self.root, stage.ENGINE_SHA256)
                    target.write_bytes(old)
        with self.assertRaises(ValueError):
            stage.stage(self.root, '0'*64)
        (self.root/'ngspice').write_bytes(b'changed')
        with self.assertRaises(ValueError): stage.source_hash(self.root/'ngspice')

    def test_linked_support_is_rejected(self):
        original = Path.is_symlink
        with patch.object(Path, 'is_symlink', lambda p: p.name == 'COPYING.txt' or original(p)):
            with self.assertRaisesRegex(ValueError, 'Linked or non-file'):
                stage.stage(self.root, stage.ENGINE_SHA256)

    def test_existing_windows_manifest_membership_is_still_required(self):
        windows = self.root/'ngspice.exe'
        windows.write_bytes(b'Windows executable')
        (self.root/'runtime-manifest.json').write_text(json.dumps({'files': {
            'ngspice.exe': fixture_sha(windows), 'COPYING.txt': fixture_sha(self.root/'COPYING.txt')}}))
        with patch.object(probe, 'file_digest', side_effect=fixture_sha):
            self.assertIn('ngspice.exe', probe.runtime_identity(windows, None, True)['files'])
            (self.root/'COPYING.txt').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Runtime payload differs'):
                probe.runtime_identity(windows, None, True)
            (self.root/'runtime-manifest.json').write_text('{"files":{}}')
            with self.assertRaisesRegex(ValueError, 'absent from runtime manifest'):
                probe.runtime_identity(windows, None, True)


if __name__ == '__main__': unittest.main()
