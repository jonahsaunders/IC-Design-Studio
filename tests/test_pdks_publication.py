"""Bounded Windows directory publication; no administrator rights required."""
import ctypes
import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from icstudio import pdks
from icstudio.model import example,file_digest,io_path


def denial(code=5):
    error=PermissionError(errno.EACCES,'injected Windows directory lock');error.winerror=code;return error


class PDKPublicationTests(unittest.TestCase):
    def paths(self,root):
        stage=root/'_install_owned';stage.mkdir();(stage/'asset').write_bytes(b'verified immutable bytes')
        return stage,root/'package@revision'

    def package(self,root):
        source=root/'source';source.mkdir();(source/'model.spice').write_bytes(b'.model d D\n')
        manifest=dict(schema=1,id='package',revision='revision',technology=example('empty')['pdk'],
                      files={'model.spice':file_digest(source/'model.spice')})
        (source/'package.json').write_text(json.dumps(manifest));return source

    def test_supported_temporary_locks_retry_same_directory_then_publish_verified_bytes(self):
        real=pdks.os.rename
        for code in (5,32,33):
            with self.subTest(code=code),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);source=self.package(root);registry=pdks.PDKRegistry(root/'registry');attempts=[]
                def publish(stage,target):
                    attempts.append((Path(stage),Path(target)))
                    self.assertEqual(file_digest(stage/'model.spice'),file_digest(source/'model.spice'))
                    if len(attempts)<3:raise denial(code)
                    return real(stage,target)
                with patch.object(sys,'platform','win32'),patch('icstudio.pdks.os.rename',side_effect=publish),patch('icstudio.pdks.time.sleep') as sleep:
                    key=registry.install(source/'package.json')
                self.assertEqual(len(attempts),3);self.assertEqual(len(set(attempts)),1)
                self.assertEqual([call.args[0] for call in sleep.call_args_list],[.01,.02])
                self.assertEqual(registry.verify(key)['id'],'package');self.assertEqual([p.name for p in registry.root.iterdir()],[key])

    def test_persistent_lock_exhausts_and_does_not_publish_partial_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.package(root);registry=pdks.PDKRegistry(root/'registry')
            with patch.object(sys,'platform','win32'),patch('icstudio.pdks.os.rename',side_effect=denial()) as rename,patch('icstudio.pdks.time.sleep') as sleep:
                with self.assertRaises(PermissionError):registry.install(source/'package.json')
            self.assertEqual(rename.call_count,6);self.assertEqual([c.args[0] for c in sleep.call_args_list],[.01,.02,.04,.08,.15])
            self.assertEqual(list(registry.root.iterdir()),[]);self.assertEqual((source/'model.spice').read_bytes(),b'.model d D\n')

    def test_unrelated_error_is_not_retried_or_transformed(self):
        for error in (OSError(errno.ENOSPC,'disk full'),OSError(errno.EIO,'disk I/O error'),PermissionError(errno.EACCES,'real permission failure without Windows code'),denial(87)):
            with tempfile.TemporaryDirectory() as tmp:
                stage,target=self.paths(Path(tmp))
                with patch.object(sys,'platform','win32'),patch('icstudio.pdks.os.rename',side_effect=error) as rename,patch('icstudio.pdks.time.sleep') as sleep:
                    with self.assertRaises(OSError) as caught:pdks._publish_directory(stage,target)
                self.assertIs(caught.exception,error);rename.assert_called_once();sleep.assert_not_called();self.assertTrue(stage.is_dir());self.assertFalse(target.exists())

    def test_existing_and_competing_destinations_are_never_removed(self):
        for empty in (True,False):
            with self.subTest(empty=empty),tempfile.TemporaryDirectory() as tmp:
                stage,target=self.paths(Path(tmp));calls=[]
                def competing(*args):
                    calls.append(args);target.mkdir()
                    if not empty:(target/'competitor').write_bytes(b'keep')
                    raise denial()
                with patch.object(sys,'platform','win32'),patch('icstudio.pdks.os.rename',side_effect=competing),patch('icstudio.pdks.time.sleep'):
                    with self.assertRaises(FileExistsError):pdks._publish_directory(stage,target)
                self.assertEqual(len(calls),1);self.assertTrue(stage.is_dir());self.assertTrue(target.is_dir())
                if not empty:self.assertEqual((target/'competitor').read_bytes(),b'keep')
                with patch.object(sys,'platform','win32'),patch('icstudio.pdks.os.rename') as rename:
                    with self.assertRaises(FileExistsError):pdks._publish_directory(stage,target)
                rename.assert_not_called()

    def test_stage_replacement_between_attempts_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);stage,target=self.paths(root);original=root/'retained-original'
            with patch.object(sys,'platform','win32'),patch('icstudio.pdks.os.rename') as rename,patch('icstudio.pdks.time.sleep'):
                real_replace=os.replace
                def substitute_direct(*args):
                    real_replace(stage,original);stage.mkdir();(stage/'other').write_text('not original');raise denial()
                rename.side_effect=substitute_direct
                with self.assertRaisesRegex(ValueError,'changed during publication'):pdks._publish_directory(stage,target)
            rename.assert_called_once();self.assertEqual((original/'asset').read_bytes(),b'verified immutable bytes');self.assertFalse(target.exists())

    def test_symlink_stage_destination_and_parent_are_rejected_before_rename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);real=root/'real';real.mkdir();(real/'asset').write_bytes(b'keep');link=root/'linked'
            try:link.symlink_to(real,target_is_directory=True)
            except OSError as exc:
                if getattr(exc,'winerror',None)==1314:self.skipTest('Windows symlink creation privilege is unavailable; ordinary junction test remains required.')
                raise
            stage=root/'stage';stage.mkdir();(stage/'asset').write_bytes(b'keep')
            for source,target in ((link,root/'destination'),(stage,link),(link/'asset',root/'destination')):
                with patch.object(sys,'platform','win32'),patch('icstudio.pdks.os.rename') as rename:
                    with self.assertRaisesRegex(ValueError,'symbolic link or junction'):pdks._publish_directory(source,target)
                rename.assert_not_called()
            self.assertEqual((real/'asset').read_bytes(),b'keep')

    @unittest.skipUnless(os.name=='nt','Native Windows ordinary-user junction fixture')
    def test_real_junction_and_junction_substitution_do_not_redirect_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();outside=root/'outside';outside.mkdir();(outside/'keep').write_bytes(b'unchanged')
            stage,target=self.paths(root);link=root/'linked'
            def junction(path):
                result=subprocess.run(['cmd','/c','mklink','/J',str(path),str(outside)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            junction(link)
            with patch('icstudio.pdks.os.rename') as rename:
                with self.assertRaisesRegex(ValueError,'junction'):pdks._publish_directory(stage,link)
                rename.assert_not_called()
            def competing(*args):junction(target);raise denial()
            with patch('icstudio.pdks.os.rename',side_effect=competing) as rename,patch('icstudio.pdks.time.sleep'):
                with self.assertRaisesRegex(ValueError,'junction'):pdks._publish_directory(stage,target)
            rename.assert_called_once();self.assertEqual((outside/'keep').read_bytes(),b'unchanged');self.assertTrue(stage.is_dir())

    @unittest.skipUnless(os.name=='nt','Native Windows directory-sharing semantics')
    def test_real_short_lived_asset_reader_lock_releases_before_directory_retry(self):
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        create=kernel.CreateFileW;create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE];create.restype=wintypes.HANDLE
        close=kernel.CloseHandle;close.argtypes=[wintypes.HANDLE];close.restype=wintypes.BOOL
        real=pdks.os.rename;handle=None;denied=[];attempts=[]
        with tempfile.TemporaryDirectory() as tmp:
            stage,target=self.paths(Path(tmp))
            def rename(source,destination):
                nonlocal handle
                attempts.append((source,destination))
                if len(attempts)==1:
                    handle=create(str(source/'asset'),0x80000000,3,None,3,128,None)  # Reader without FILE_SHARE_DELETE.
                    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
                try:return real(source,destination)
                except OSError as exc:denied.append(getattr(exc,'winerror',None));raise
            def release(delay):
                nonlocal handle
                self.assertEqual(delay,.01);self.assertTrue(close(handle));handle=None
            try:
                with patch('icstudio.pdks.os.rename',side_effect=rename),patch('icstudio.pdks.time.sleep',side_effect=release):pdks._publish_directory(stage,target)
            finally:
                if handle is not None:close(handle)
            self.assertEqual(len(attempts),2);self.assertEqual(len(denied),1);self.assertIn(denied[0],(5,32,33))
            self.assertEqual((target/'asset').read_bytes(),b'verified immutable bytes');self.assertFalse(stage.exists())

    def test_non_windows_keeps_original_single_replace_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage,target=self.paths(Path(tmp));error=denial()
            with patch.object(sys,'platform','linux'),patch('icstudio.pdks.os.replace',side_effect=error) as replace,patch('icstudio.pdks.os.rename') as rename,patch('icstudio.pdks.time.sleep') as sleep:
                with self.assertRaises(PermissionError) as caught:pdks._publish_directory(stage,target)
            self.assertIs(caught.exception,error);replace.assert_called_once_with(io_path(stage),io_path(target));rename.assert_not_called();sleep.assert_not_called()

    def test_local_registration_uses_the_same_safe_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.package(root);manifest=json.loads((source/'package.json').read_bytes());manifest['source_root']=str(source)
            registry=pdks.PDKRegistry(root/'registry');real=pdks.os.rename;attempts=[]
            def rename(stage,target):
                attempts.append((stage,target))
                if len(attempts)==1:raise denial(32)
                return real(stage,target)
            with patch.object(sys,'platform','win32'),patch('icstudio.pdk_import.scan_local',return_value=manifest),patch('icstudio.pdks.os.rename',side_effect=rename),patch('icstudio.pdks.time.sleep'):
                key=registry.register_local(source)
            self.assertEqual(len(attempts),2);self.assertEqual(registry.verify(key)['source_root'],str(source))


if __name__=='__main__':unittest.main()
