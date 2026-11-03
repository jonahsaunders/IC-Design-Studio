"""Unit tests use fake bytes; they do not claim a compiled native build."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ci_windows_native_identity as identity


class WindowsNativeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in identity.INPUTS:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('fixture:' + name).encode())
        self.compiler = self.root / 'fake-cl.exe'
        self.compiler.write_bytes(b'fake compiler')
        self.receipt = identity.record(self.root, self.compiler)

    def test_verify_accepts_unchanged_inputs_without_writing(self):
        before = copy.deepcopy(self.receipt)
        identity.verify(self.root, self.receipt)
        self.assertEqual(before, self.receipt)

    def test_each_changed_or_missing_input_fails(self):
        for name in identity.INPUTS:
            path = self.root / name
            original = path.read_bytes()
            with self.subTest(name=name, mutation='changed'):
                path.write_bytes(original + b'changed')
                with self.assertRaises(ValueError):
                    identity.verify(self.root, self.receipt)
            with self.subTest(name=name, mutation='missing'):
                path.unlink()
                with self.assertRaises(ValueError):
                    identity.verify(self.root, self.receipt)
            path.write_bytes(original)

    def test_changed_or_missing_compiler_fails(self):
        self.compiler.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            identity.verify(self.root, self.receipt)
        self.compiler.unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            identity.verify(self.root, self.receipt)

    def test_bad_receipt_or_different_checkout_fails(self):
        for invalid in ({}, dict(self.receipt, schema=True), dict(self.receipt, compiler='relative')):
            with self.subTest(receipt=invalid), self.assertRaises(ValueError):
                identity.verify(self.root, invalid)
        with tempfile.TemporaryDirectory() as other, self.assertRaises((ValueError, FileNotFoundError)):
            identity.verify(other, self.receipt)

    @unittest.skipUnless(os.name == 'nt' and shutil.which('pwsh'), 'Windows PowerShell required')
    def test_verify_only_uses_receipt_without_building(self):
        source = Path(__file__).resolve().parents[1] / 'scripts'
        for name in ('ci_windows_native.ps1', 'ci_windows_native_identity.py'):
            shutil.copyfile(source / name, self.root / 'scripts' / name)
        receipt = identity.record(self.root, self.compiler)
        receipt_path = self.root / 'build/ci-native/identity.json'
        receipt_path.parent.mkdir(parents=True)
        receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
        env = os.environ.copy()
        env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
        cmd = ['pwsh', '-NoProfile', '-File', str(self.root / 'scripts/ci_windows_native.ps1'), '-VerifyOnly']
        binary = self.root / 'icstudio/iccore.dll'
        before = binary.read_bytes()
        self.assertEqual(subprocess.run(cmd, env=env, capture_output=True).returncode, 0)
        self.assertEqual(binary.read_bytes(), before)
        binary.write_bytes(b'changed binary')
        self.assertNotEqual(subprocess.run(cmd, env=env, capture_output=True).returncode, 0)
        self.assertEqual(binary.read_bytes(), b'changed binary')


if __name__ == '__main__':
    unittest.main()
