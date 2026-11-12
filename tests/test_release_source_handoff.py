"""Exercise the real handoff source validation through release packaging."""
from pathlib import Path
import ast,hashlib,importlib.util,os,platform,sys,unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
REPO=HERE.parent if (HERE.parent/'icstudio').is_dir() else HERE.parent/'IC-Design-Studio'
REPO=Path(os.environ.get('ICSTUDIO_TEST_SOURCE_ROOT',str(REPO)))
PAYLOAD=HERE/'prepare_release_payload.py' if (HERE/'prepare_release_payload.py').is_file() else REPO/'scripts/prepare_release_payload.py'
sys.path.insert(0,str(REPO))
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
t=module('handoff_fixture',HERE/'test_desktop_acceptance_handoff.py')
h=t.h;payload=module('draft_payload',PAYLOAD)
# Preserve the original acceptance validators through the job split. An intended
# future validator change requires an explicit review/update of this baseline.
ORIGINAL_VALIDATORS={
 'checksum':'30eea373bc21da8a7cdfeb0afeff90cd423aeb4362593fc41d1c252a95dfc2e4',
 'require':'0f4163611ce0bc40358ee49a9ef0fc10b5a6a2c2f0ec03bd30dfdc6b54a6af7f',
 'validate_desktop_report':'20d072460fd64ffb72c8cd2de0f8731bfcde3d9f2bec47e51dfaba767c0be01a',
 'validate_installer':'627cf8d54547a3efd91082c141046f532a3b555887aa42b3104ab338f039133e',
 'verify_distribution':'91064873dfddf262a90b48d288d8c369a226e6879e16755d394105d45537bb95'}
class SourceArchiveTests(unittest.TestCase):
 def setUp(self):
  self.fixture=t.HandoffTests();self.fixture.setUp();self.root=self.fixture.root
  self.fixture.ident['machine']=platform.machine()
  self.env=patch.dict(os.environ,{'GITHUB_SHA':self.fixture.commit,'GITHUB_RUN_ID':'42','GITHUB_RUN_ATTEMPT':'1','RUNNER_OS':self.fixture.ident['os']});self.env.start()
  self.modules=patch.dict(sys.modules,{'scripts.desktop_acceptance_handoff':h});self.modules.start()
  self.old_root=payload.ROOT;payload.ROOT=self.root
  self.fixture.prepare_restore();self.fixture.restore();self.out=self.root/'release';self.out.mkdir()
 def tearDown(self):
  payload.ROOT=self.old_root;self.modules.stop();self.env.stop();self.fixture.tearDown()
 def test_verified_source_copied_exactly(self):
  actual=payload.release_source(self.out,self.fixture.ident['os'],self.root/h.SOURCE)
  self.assertEqual(actual.read_bytes(),(self.root/h.SOURCE).read_bytes())
 def test_wrong_candidate_rejected(self):
  os.environ['GITHUB_SHA']='0'*40
  with self.assertRaises(ValueError):payload.release_source(self.out,'Windows',self.root/h.SOURCE)
 def test_wrong_run_rejected(self):
  os.environ['GITHUB_RUN_ID']='43'
  with self.assertRaises(ValueError):payload.release_source(self.out,'Windows',self.root/h.SOURCE)
 def test_missing_ready_rejected(self):
  (self.root/h.READY).unlink()
  with self.assertRaises(FileNotFoundError):payload.release_source(self.out,'Windows',self.root/h.SOURCE)
 def test_wrong_source_path_rejected(self):
  p=self.root/'other.zip';p.write_bytes((self.root/h.SOURCE).read_bytes())
  with self.assertRaises(ValueError):payload.release_source(self.out,'Windows',p)
 def test_rehashed_manifest_source_drift_rejected(self):
  record=h.load(self.fixture.folder/h.MANIFEST);record['source']['sha256']='0'*64;self.fixture.save(record)
  with self.assertRaises(ValueError):payload.release_source(self.out,'Windows',self.root/h.SOURCE)
 def test_no_source_argument_keeps_legacy_generator(self):
  def generate(out):
   p=out/'generated.zip';p.write_bytes(b'legacy source');return p
  with patch.object(payload,'source_archive',side_effect=generate) as writer:
   p=payload.release_source(self.out,'Linux')
  writer.assert_called_once_with(self.out);self.assertEqual(p.read_bytes(),b'legacy source')
 def test_all_existing_validation_functions_unchanged(self):
  after=ast.parse(PAYLOAD.read_text())
  actual={x.name:hashlib.sha256(ast.dump(x).encode()).hexdigest() for x in after.body if isinstance(x,ast.FunctionDef)}
  self.assertEqual({k:actual[k] for k in ORIGINAL_VALIDATORS},ORIGINAL_VALIDATORS)
 def test_prepare_keeps_installer_distribution_and_evidence_gates(self):
  tree=ast.parse(PAYLOAD.read_text());prepare=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='prepare')
  names={n.func.id for n in ast.walk(prepare) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
  self.assertTrue({'validate_installer','verify_distribution','release_source'}<=names)
if __name__=='__main__':unittest.main()

