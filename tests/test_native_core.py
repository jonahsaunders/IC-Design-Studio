"""Regression coverage for the Windows Bad Image report."""
import ctypes
import math
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch
from icstudio.native_core import load_native_core, native_library_name
from icstudio.model import example
from icstudio.simulation import run


class NativeCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def pe(self, machine=0x8664):
        header=bytearray(64);header[:2]=b'MZ';struct.pack_into('<I',header,60,64)
        (self.root/'iccore.dll').write_bytes(header+b'PE\0\0'+struct.pack('<H',machine))
    def test_windows_never_loads_linux_or_macos_files(self):
        for name in ('libiccore.so','libiccore.dylib'):(self.root/name).write_bytes(b'foreign binary')
        loader=Mock();self.assertIsNone(load_native_core([self.root],'win32',loader));loader.assert_not_called()
    def test_windows_rejects_foreign_file_renamed_dll(self):
        (self.root/'iccore.dll').write_bytes(b'\x7fELF'+b'\0'*100)
        loader=Mock();self.assertIsNone(load_native_core([self.root],'win32',loader));loader.assert_not_called()
    def test_windows_selects_matching_pe(self):
        self.pe(0x8664 if ctypes.sizeof(ctypes.c_void_p)==8 else 0x14c);library=Mock();loader=Mock(return_value=library)
        with patch('icstudio.native_core.platform.machine',return_value='AMD64'):
            self.assertIs(load_native_core([self.root],'win32',loader),library)
        loader.assert_called_once_with(str(self.root/'iccore.dll'))
        self.assertEqual(len(library.ic_solve.argtypes),4)
    def test_windows_rejects_wrong_architecture(self):
        self.pe(0x14c if ctypes.sizeof(ctypes.c_void_p)==8 else 0x8664);loader=Mock()
        with patch('icstudio.native_core.platform.machine',return_value='AMD64'):
            self.assertIsNone(load_native_core([self.root],'win32',loader))
        loader.assert_not_called()
    def test_linux_and_macos_choose_only_their_file(self):
        for name in ('libiccore.so','libiccore.dylib','iccore.dll'):(self.root/name).write_bytes(b'test')
        for target,name in [('linux','libiccore.so'),('darwin','libiccore.dylib')]:
            loader=Mock(return_value=Mock());load_native_core([self.root],target,loader);loader.assert_called_once_with(str(self.root/name))
    def test_load_error_or_missing_entry_uses_fallback(self):
        (self.root/'libiccore.so').write_bytes(b'test')
        for loader in [Mock(side_effect=OSError('bad binary')),Mock(return_value=object())]:
            self.assertIsNone(load_native_core([self.root],'linux',loader))
    def test_windows_without_native_core_runs_rc_transient(self):
        (self.root/'libiccore.so').write_bytes(b'\x7fELF');loader=Mock()
        core=load_native_core([self.root],'win32',loader);p=example()
        with patch('icstudio.simulation.CORE',core):result=run(p,p['top'],p['analysis'])
        loader.assert_not_called();self.assertEqual(len(result['x']),501)
        self.assertTrue(all(math.isfinite(v) for v in result['traces']['vout']))
        self.assertGreater(max(result['traces']['vout']),1.5)
        self.assertLess(max(result['traces']['vout']),1.8)

if __name__=='__main__':unittest.main()
