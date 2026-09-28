"""A recovered file must agree with the write that was acknowledged."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from icstudio import recovery
from icstudio.model import clone, digest, example


class RecoveryReceiptTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.root=Path(folder.name);self.project=example('empty')

    def test_valid_old_file_replacement_is_detected_and_falls_back_explicitly(self):
        path=recovery.write(self.project,self.root);old=path.read_bytes()
        self.project.update(name='Latest',revision=1)
        recovery.write(self.project,self.root)
        receipt=recovery.verified_receipt(path)
        self.assertEqual(receipt['project_hash'],digest(self.project))
        self.assertEqual(receipt['revision'],1)
        path.write_bytes(old)
        with self.assertRaisesRegex(ValueError,'differs from acknowledged'):
            recovery.verified_receipt(path)
        restored,fallback=recovery.read(path)
        self.assertTrue(fallback)
        self.assertEqual(restored['revision'],0)

    def test_replacement_during_write_is_not_acknowledged(self):
        path=recovery.write(self.project,self.root);old=path.read_bytes()
        self.project.update(name='New',revision=1)
        original=recovery.atomic_write
        def replace(destination,data):
            original(destination,data)
            if Path(destination)==path:path.write_bytes(old)
        with patch('icstudio.recovery.atomic_write',side_effect=replace):
            with self.assertRaisesRegex(ValueError,'before its write could be verified'):
                recovery.write(self.project,self.root)
        self.assertEqual(recovery.verified_receipt(path)['revision'],0)

    def test_abrupt_exit_between_data_and_receipt_preserves_last_acknowledged_state(self):
        path=recovery.write(self.project,self.root)
        expected=clone(self.project)
        code="""
import json,os,sys
from pathlib import Path
from icstudio import recovery
p=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
p.update(name='Interrupted publication',revision=1)
write=recovery.atomic_write
def interrupted(path,data):
    write(path,data)
    if Path(path)==Path(sys.argv[1]):os._exit(17)
recovery.atomic_write=interrupted
recovery.write(p,Path(sys.argv[1]).parent)
"""
        result=subprocess.run([sys.executable,'-c',code,str(path)],capture_output=True,timeout=20)
        self.assertEqual(result.returncode,17,result.stderr.decode())
        restored,fallback=recovery.read(path)
        self.assertTrue(fallback);self.assertEqual(digest(restored),digest(expected))
        self.project.update(name='Retry after interruption',revision=2)
        recovery.write(self.project,self.root)
        restored,fallback=recovery.read(path)
        self.assertFalse(fallback);self.assertEqual(restored['revision'],2)

    def test_session_receipts_and_legacy_files_remain_independent(self):
        a=recovery.write(self.project,self.root/'a')
        self.project.update(name='Other session',revision=2)
        b=recovery.write(self.project,self.root/'b')
        self.assertNotEqual(recovery.verified_receipt(a)['write_id'],recovery.verified_receipt(b)['write_id'])
        self.assertEqual(recovery.read(a)[0]['revision'],0)
        a.with_suffix('.origin.json').write_text(json.dumps({'source':None}))
        self.assertEqual(recovery.read(a)[0]['revision'],0)
        recovery.clear(b)
        self.assertEqual(list(b.parent.iterdir()),[])

    def test_malformed_or_unknown_receipt_uses_verified_previous_snapshot(self):
        path=recovery.write(self.project,self.root)
        self.project.update(name='Latest',revision=1);recovery.write(self.project,self.root)
        for value in ([],{'receipt_schema':99}):
            path.with_suffix('.origin.json').write_text(json.dumps(value))
            restored,fallback=recovery.read(path)
            self.assertTrue(fallback);self.assertEqual(restored['revision'],0)
        self.project.update(name='Retry',revision=2);recovery.write(self.project,self.root)
        path.write_text('invalid JSON')
        restored,fallback=recovery.read(path)
        self.assertTrue(fallback);self.assertEqual(restored['revision'],0)

    def test_reader_returns_the_same_bytes_that_were_verified(self):
        path=recovery.write(self.project,self.root);old=path.read_bytes()
        self.project.update(name='Latest',revision=1);recovery.write(self.project,self.root)
        verify=recovery.verified_receipt
        def replaced(*args,**kwargs):
            result=verify(*args,**kwargs)
            path.write_bytes(old)
            return result
        with patch('icstudio.recovery.verified_receipt',side_effect=replaced):
            restored,fallback=recovery.read(path)
        self.assertFalse(fallback);self.assertEqual(restored['revision'],1)


if __name__=='__main__':unittest.main()
