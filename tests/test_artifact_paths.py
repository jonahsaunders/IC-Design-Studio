"""Job artifacts keep portable identities across real filesystem aliases."""
import ctypes
import os
from pathlib import Path
import tempfile
import unittest

from icstudio.digital_flow import artifact
from icstudio.model import file_digest


class ArtifactPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='artifact-paths-')
        self.addCleanup(self.tmp.cleanup)
        self.parent=Path(self.tmp.name).resolve()
        self.root=self.parent/'long job directory';self.root.mkdir()
        self.path=self.root/'verification'/'long evidence filename.json'
        self.path.parent.mkdir();self.path.write_bytes(b'{"checked":true}')

    def alias(self):
        if os.name!='nt':
            alias=self.parent/'job-alias';alias.symlink_to(self.root,target_is_directory=True)
            return alias
        short=ctypes.WinDLL('kernel32',use_last_error=True).GetShortPathNameW
        short.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint32]
        short.restype=ctypes.c_uint32
        length=short(str(self.root),None,0)
        if not length:self.skipTest('Windows volume has no short-name aliases')
        buffer=ctypes.create_unicode_buffer(length)
        if not short(str(self.root),buffer,length):self.skipTest('Windows volume has no short-name aliases')
        alias=Path(buffer.value)
        if os.path.normcase(str(alias))==os.path.normcase(str(self.root)):
            self.skipTest('Windows directory has no short-name alias')
        return alias

    def test_short_job_root_and_full_artifact_path(self):
        record=artifact(self.alias(),self.path)
        self.assertEqual(record,dict(path='verification/long evidence filename.json',
                                    sha256=file_digest(self.path),bytes=16))

    def test_full_job_root_and_aliased_artifact_path(self):
        self.assertEqual(artifact(self.root,self.alias()/'verification'/self.path.name),
                         artifact(self.root,self.path))

    def test_relative_and_outside_paths(self):
        nested=self.root/'verification'/'..'/'verification'/self.path.name
        self.assertEqual(artifact(self.root,nested),artifact(self.root,self.path))
        outside=self.parent/'outside.json';outside.write_bytes(b'not job evidence')
        with self.assertRaises(ValueError):artifact(self.root,outside)
        with self.assertRaises(ValueError):artifact(self.root,self.root/'..'/'outside.json')

    def test_empty_artifact_requires_explicit_allowance(self):
        self.path.write_bytes(b'')
        with self.assertRaisesRegex(ValueError,'did not produce'):artifact(self.root,self.path)
        self.assertEqual(artifact(self.root,self.path,allow_empty=True)['bytes'],0)


if __name__=='__main__':unittest.main()
