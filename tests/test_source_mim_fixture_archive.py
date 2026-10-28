"""Source archive includes only the exact reviewed public MiM fixture ZIP."""
import hashlib,importlib.util,os,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;TREE=HERE.parent;REPO=Path(os.environ['ICSTUDIO_TEST_SOURCE']) if 'ICSTUDIO_TEST_SOURCE' in os.environ else (TREE if (TREE/'icstudio').is_dir() else TREE.parent.parent/'IC-Design-Studio')
def module(name,path):
 previous=list(sys.path)
 try:
  if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
  spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 finally:sys.path[:]=previous
release=module('review_release',REPO/'scripts/release_archives.py');handoff=module('review_handoff',REPO/'scripts/desktop_acceptance_handoff.py')
FIXTURE='docs/qualification/sky130-mim-conditioning-v1/fixture-bundle.zip';CONTRACT='docs/SKY130_MIM_CONDITIONING.md';EXPECTED='c3f66bd57fdfcb95744061ae717142409ded07aa7c43cb4447a25feddd41c6c0'
class PublicFixtureArchiveTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='mim-source-');self.root=Path(self.tmp.name)/'source';self.root.mkdir();self.out=Path(self.tmp.name)/'out';self.out.mkdir();self.inputs={}
  def write(name,data):
   p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);self.inputs[name]=data
  write('main.py',b'print(1)\n');write('LICENSE',(REPO/'LICENSE').read_bytes());write(CONTRACT,b'finite source qualification\n');data=(TREE/FIXTURE).read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),EXPECTED);write(FIXTURE,data);release.ROOT=self.root
  rows=[]
  for name,data in self.inputs.items():rows.append(('100644 blob '+hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()+'\t'+name).encode()+b'\0')
  self.tree=b''.join(rows);self.revision='a'*40
 def tearDown(self):self.tmp.cleanup()
 def authenticate(self,path,tree=None):
  def fake(command,**kwargs):
   self.assertEqual(command,['git','ls-tree','-rz','--full-tree',self.revision]);self.assertFalse(any(k.upper().startswith('GIT_') for k in kwargs['env']));return self.tree if tree is None else tree
  with patch.object(handoff.subprocess,'check_output',side_effect=fake):return handoff.candidate_source(self.root,path,self.revision)
 def rewrite(self,path,change):
  dest=self.out/'altered.zip'
  with zipfile.ZipFile(path) as z,zipfile.ZipFile(dest,'w') as w:
   for name in z.namelist():
    if name=='IC-Design-Studio/'+FIXTURE and change=='missing':continue
    data=z.read(name)
    if name=='IC-Design-Studio/'+FIXTURE and change=='changed':data+=b'changed'
    w.writestr(name,data)
  return dest
 def test_archive_module_loading_restores_import_path(self):
  before=list(sys.path);module('isolated_release_check',REPO/'scripts/release_archives.py');self.assertEqual(sys.path,before)
 def test_source_and_repository_archives_include_exact_fixture(self):
  for repository in (False,True):
   with self.subTest(repository=repository):
    archive=release.source_archive(self.out,repository=repository)
    with zipfile.ZipFile(archive) as z:
     self.assertEqual(hashlib.sha256(z.read('IC-Design-Studio/'+FIXTURE)).hexdigest(),EXPECTED)
    checked=self.authenticate(archive);self.assertEqual(checked[FIXTURE],EXPECTED)
 def test_missing_and_changed_archived_fixture_rejected(self):
  archive=release.source_archive(self.out,repository=True)
  with self.assertRaisesRegex(ValueError,'Missing candidate source'):self.authenticate(self.rewrite(archive,'missing'))
  with self.assertRaisesRegex(ValueError,'Release source differs from candidate'):self.authenticate(self.rewrite(archive,'changed'))
 def test_fixture_missing_from_source_zip_is_rejected(self):
  (self.root/FIXTURE).unlink();archive=release.source_archive(self.out,repository=True)
  with self.assertRaisesRegex(ValueError,'Missing candidate source'):self.authenticate(archive)
if __name__=='__main__':unittest.main(verbosity=2)

