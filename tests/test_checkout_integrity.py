"""Recorded library hashes must survive Windows Git checkout settings."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('git'),'Git is required to exercise checkout conversion.')
class CheckoutIntegrityTests(unittest.TestCase):
    def test_locked_sources_survive_windows_line_ending_settings(self):
        paths=['icstudio/assets/exchange/xschem/COPYRIGHT',
               'examples/gf180-bandgap/5vfullv2-original.sch']
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);repo=root/'repository';repo.mkdir();checkout=root/'checkout';checkout.mkdir()
            def git(*args):
                subprocess.run(['git','-C',str(repo),'-c','core.autocrlf=true',*args],check=True,capture_output=True)
            git('init')
            shutil.copyfile(ROOT/'.gitattributes',repo/'.gitattributes')
            for name in paths:
                target=repo/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
            git('add','.')
            git('checkout-index','--all','--prefix='+checkout.as_posix()+'/')
            for name in paths:
                with self.subTest(path=name):
                    self.assertEqual(hashlib.sha256((checkout/name).read_bytes()).hexdigest(),
                                     hashlib.sha256((ROOT/name).read_bytes()).hexdigest())


if __name__=='__main__':unittest.main()
