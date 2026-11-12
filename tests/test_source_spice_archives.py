"""Small actual source ZIPs, exact locked SPICE bytes, and handoff hash rejection.

No Git writes: candidate tree metadata is an explicit fixture; the production
candidate_source still performs its original Git blob hash comparison.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parent if (HERE.parent/'scripts/release_archives.py').is_file() else HERE.parent/'IC-Design-Studio'
sys.path.insert(0,str(REPO))

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

SCRIPTS=HERE/'proposed/scripts' if (HERE/'proposed/scripts').is_dir() else REPO/'scripts'
r=module('proposed_release',SCRIPTS/'release_archives.py')
h=module('proposed_handoff',SCRIPTS/'desktop_acceptance_handoff.py')

class SpiceArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='zip-test-')
        self.root=Path(self.temp.name)/'source';self.root.mkdir()
        self.out=Path(self.temp.name)/'output';self.out.mkdir()
        self.expected={}
        def write(rel,data):
            p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            self.expected[rel]=data
        write('main.py',b'print("fixture")\n');write('LICENSE',(REPO/'LICENSE').read_bytes())
        self.bond='icstudio/assets/qualification/ihp-bondpad/'
        for p in (REPO/self.bond).iterdir():
            if p.is_file():write(self.bond+p.name,p.read_bytes())
        self.ihp='icstudio/assets/pdks/ihp-sg13g2/libs.tech/ngspice/models/sg13g2_esd.lib'
        self.npn='icstudio/assets/pdks/sky130A/libs.tech/ngspice/icstudio-npn-corners.lib'
        for rel in (self.ihp,self.npn):write(rel,(REPO/rel).read_bytes())
        write('native/import.lib',b'!<arch>\n\0compiled import library')
        write('native/module.dll',b'MZ\0binary fixture')
        write('tests/fixtures/unclassified/import.lib',b'!<arch>\n\0unclassified')
        r.ROOT=self.root
        self.archive=r.source_archive(self.out,repository=True)
        rows=[]
        for name,data in self.expected.items():
            digest=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            rows.append(('100644 blob '+digest+'\t'+name).encode()+b'\0')
        self.tree=b''.join(rows)
        self.candidate='a'*40
    def tearDown(self):self.temp.cleanup()
    def authenticate(self,path=None):
        def tree(command,**kwargs):
            self.assertEqual(command,['git','ls-tree','-rz','--full-tree',self.candidate])
            self.assertEqual(kwargs['cwd'],self.root)
            self.assertFalse(any(k.upper().startswith('GIT_') for k in kwargs['env']))
            return self.tree
        with patch.object(h.subprocess,'check_output',side_effect=tree):
            return h.candidate_source(self.root,path or self.archive,self.candidate)
    def rewrite(self,*,missing=None,changed=None):
        target=self.out/'modified.zip'
        with zipfile.ZipFile(self.archive) as source,zipfile.ZipFile(target,'w') as dest:
            for name in source.namelist():
                rel=name.removeprefix('IC-Design-Studio/')
                if rel==missing:continue
                data=source.read(name)
                dest.writestr(name,data+b'\n* changed\n' if rel==changed else data)
        return target
    def test_real_zip_retains_full_bondpad_lock_and_spice_sources(self):
        lock=json.loads((REPO/self.bond/'source-lock.json').read_bytes())
        with zipfile.ZipFile(self.archive) as z:
            for name,row in lock['files'].items():
                data=z.read('IC-Design-Studio/'+self.bond+name)
                self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'])
            self.assertEqual(z.read('IC-Design-Studio/'+self.ihp),self.expected[self.ihp])
            self.assertEqual(z.read('IC-Design-Studio/'+self.npn),self.expected[self.npn])
        checked=self.authenticate()
        self.assertIn(self.bond+'sg13g2_bondpad.lib',checked)
        self.assertIn(self.ihp,checked);self.assertIn(self.npn,checked)
        self.assertLess(self.archive.stat().st_size,200000)
    def test_compiled_and_unclassified_libraries_remain_excluded(self):
        with zipfile.ZipFile(self.archive) as z:
            for rel in ('native/import.lib','native/module.dll','tests/fixtures/unclassified/import.lib'):
                self.assertNotIn('IC-Design-Studio/'+rel,z.namelist())
        self.authenticate()
    def test_missing_locked_bondpad_library_rejected_by_candidate(self):
        with self.assertRaisesRegex(ValueError,'Missing candidate source'):
            self.authenticate(self.rewrite(missing=self.bond+'sg13g2_bondpad.lib'))
    def test_modified_library_rejected_without_relaxing_git_blob_hash(self):
        with self.assertRaisesRegex(ValueError,'Release source differs from candidate'):
            self.authenticate(self.rewrite(changed=self.bond+'sg13g2_bondpad.lib'))
    def test_missing_existing_ihp_model_rejected(self):
        with self.assertRaisesRegex(ValueError,'Missing candidate source'):
            self.authenticate(self.rewrite(missing=self.ihp))
    def test_missing_existing_npn_corner_rejected(self):
        with self.assertRaisesRegex(ValueError,'Missing candidate source'):
            self.authenticate(self.rewrite(missing=self.npn))

if __name__=='__main__':unittest.main(verbosity=2)
