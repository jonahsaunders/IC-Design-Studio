import hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import prepare_ihp_wsl_app_contract as c
from scripts import probe_ihp_wsl_research_app as p
from scripts import audit_ihp_wsl_research_app as a
class ReconstructedAdmissionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def write(self,name,data):
  q=self.root/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_text(json.dumps(data));return q
 def payload(self):
  (self.root/'runtime.tar.gz').write_bytes(b'fixture')
  self.write('derivation.json',{'scope':'fixture'})
  self.write('manifest.json',{'archive':'runtime.tar.gz','bytes':7,'sha256':c.sha(self.root/'runtime.tar.gz'),'experimental_research':{'scope':'fixture'}})
 def test_selection_twenty_unique(self):self.assertEqual(len(set(c.SELECTION)),20)
 def test_payload_exact(self):
  self.payload();self.assertEqual(set(c.payload_identity(self.root)),set(c.PAYLOAD))
 def test_extra_backend_override_rejected(self):
  self.payload();self.write('backend.json',{})
  with self.assertRaisesRegex(ValueError,'three-file'):c.payload_identity(self.root)
 def test_changed_archive_rejected(self):
  self.payload();(self.root/'runtime.tar.gz').write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'Archive identity'):c.payload_identity(self.root)
 def test_changed_derivation_rejected(self):
  self.payload();self.write('derivation.json',{})
  with self.assertRaisesRegex(ValueError,'derivation'):c.payload_identity(self.root)
 def test_symlink_rejected(self):
  self.payload()
  if os.name!='nt':
   (self.root/'runtime.tar.gz').unlink();(self.root/'runtime.tar.gz').symlink_to(self.root/'manifest.json')
   with self.assertRaisesRegex(ValueError,'Linked'):c.payload_identity(self.root)
   return
  # Ordinary Windows users can create directory junctions without symlink privilege.
  # Use a separate parent so cleanup never recursively traverses the junction.
  before={n:(self.root/n).read_bytes() for n in c.PAYLOAD}
  with tempfile.TemporaryDirectory() as folder:
   link=Path(folder)/'payload-junction'
   try:
    subprocess.run(['cmd.exe','/c','mklink','/J',str(link),str(self.root)],check=True,capture_output=True,timeout=10)
    self.assertTrue(getattr(link.lstat(),'st_file_attributes',0)&0x400)
    with self.assertRaisesRegex(ValueError,'Linked'):c.payload_identity(link)
    with self.assertRaisesRegex(ValueError,'Linked'):c.regular(link/'runtime.tar.gz')
   finally:
    if os.path.lexists(link):os.rmdir(link)
   self.assertFalse(os.path.lexists(link))
  self.assertEqual(before,{n:(self.root/n).read_bytes() for n in c.PAYLOAD})
 def test_source_covers_assets_and_scripts(self):
  self.write('icstudio/asset.json',{});self.write('scripts/a.py',{});self.write('scripts/irrelevant.txt',{});self.write('icstudio/__pycache__/ignored.pyc',{})
  self.assertEqual(set(c.source_identity(self.root)),{'icstudio/asset.json','scripts/a.py'})
 def test_source_mutation_changes_map(self):
  q=self.write('scripts/a.py',{});before=c.source_identity(self.root);q.write_text('changed');self.assertNotEqual(before,c.source_identity(self.root))
 def test_actual_windows_gate(self):
  contract=self.write('c.json',{});auth=self.write('a.json',{})
  with patch.object(p.sys,'platform','linux'),self.assertRaisesRegex(ValueError,'Actual Windows'):p.preflight(contract,auth,self.root,self.root)
 def test_draft_not_native_permission(self):
  contract=self.write('c.json',{'review_state':'PENDING_INDEPENDENT_WINDOWS_ADAPTER_REVIEW'});auth=self.write('a.json',{})
  with patch.object(p.sys,'platform','win32'),self.assertRaisesRegex(ValueError,'review required'):p.preflight(contract,auth,self.root,self.root)
 def test_no_adapter_even_with_preflight_mock(self):
  with patch.object(p,'preflight',return_value={}),self.assertRaisesRegex(ValueError,'adapter review'):p.run(None,None,None,None,None,self.root/'attempt',None)
 def test_no_forged_native_acceptance(self):
  receipt=self.write('r.json',{'qualified':False,'status':'PASS'})
  with self.assertRaisesRegex(ValueError,'BLOCKED'):a.audit(receipt)
 def test_qualification_promotion_rejected(self):
  with self.assertRaisesRegex(ValueError,'promotion'):a.audit(self.write('r.json',{'qualified':True}))
if __name__=='__main__':unittest.main()

class StructuralReceiptTests(unittest.TestCase):
 def test_unsafe_paths(self):
  with tempfile.TemporaryDirectory() as root:
   for name in ('../escape','/absolute','x\\y','C:bad'):
    with self.subTest(name=name),self.assertRaises(ValueError):a.confined(root,name)
 def test_native_adapter_requires_review_before_qt(self):
  with tempfile.TemporaryDirectory() as root,patch.object(p,'preflight',return_value={'native_adapter_ready':False}),self.assertRaisesRegex(ValueError,'adapter review'):
   p.studio_adapter(None,None,None,None,{},Path(root)/'attempt',{})
 def test_receipt_mismatched_input_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   root=Path(root);(root/'physical-backend.json').write_text(json.dumps({'native_input_sha256':'0'*64}));(root/'physical-backend-input.json').write_text('{}')
   with self.assertRaisesRegex(ValueError,'input binding'):a.audit_job(root,{},[])

class RawReadbackTests(unittest.TestCase):
 def test_finite_grid_comparison_and_mutation(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'result.raw';path.write_text('Title: exact\nCommand: ngspice-47, test\n')
   grid=[-j/20 for j in range(28)];values={'i(v'+t+')':[0.0]*28 for t in 'dgsb'}
   reader=lambda _: (values,grid)
   self.assertEqual(a.compare_raw(path,path,'exact',reader,1e-16,1e-8)['terminal_comparisons'],112)
   with self.assertRaisesRegex(ValueError,'title'):a.compare_raw(path,path,'wrong',reader,1e-16,1e-8)
 def test_nonfinite_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'result.raw';path.write_text('Title: exact\nCommand: ngspice-47, test\n')
   values={'i(v'+t+')':[float('nan')]*28 for t in 'dgsb'}
   with self.assertRaisesRegex(ValueError,'Nonfinite'):a.compare_raw(path,path,'exact',lambda _:(values,[-j/20 for j in range(28)]),1e-16,1e-8)
 def test_incomplete_grid_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'result.raw';path.write_text('Title: exact\nCommand: ngspice-47, test\n')
   with self.assertRaisesRegex(ValueError,'grid'):a.compare_raw(path,path,'exact',lambda _:({},[0]),1e-16,1e-8)

class DraftContractTests(unittest.TestCase):
 def test_draft_never_grants_permission(self):
  import types,sys
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);source=root/'source';(source/'scripts').mkdir(parents=True);(source/'scripts/a.py').write_text('# fixture')
   prepared=root/'prepared';payload=prepared/'experimental-payload';payload.mkdir(parents=True);(payload/'runtime.tar.gz').write_bytes(b'fixture')
   def put(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
   put(payload/'manifest.json',dict(archive='runtime.tar.gz',bytes=7,sha256=c.sha(payload/'runtime.tar.gz'),experimental_research={},osdi={'ihp-sg13g2':{'models':[]}}))
   put(payload/'derivation.json',{});put(prepared/'host-contract.json',dict(scope='REVIEWED_NEW_WSL_HOST_BASELINE',qualified=False,dependencies={}))
   evidence=root/'evidence';put(evidence/'MANIFEST.json',{})
   put(evidence/'measured-v3/attempt-1/run.json',{'runs':[dict(route=r,gate_index=i,deadline_seconds=90) for r,i in c.SELECTION]})
   projects=root/'projects';cases=[]
   for r,i in c.SELECTION:
    key=f'{r}-{i}';put(evidence/f'measured-v3/attempt-1/runs/{key}/input.cir',{})
    put(projects/(key+'.icproj'),{});cases.append(dict(case=key,project=key+'.icproj',sha256=c.sha(projects/(key+'.icproj'))))
   put(projects/'projects.json',dict(qualified=False,deadline_seconds=90,pre_native_review_required=True,cases=cases))
   fake=types.ModuleType('scripts.check_ihp_wsl_prepared');fake.check=lambda _:dict(status='CLEAN_BUILD_PREPARATION_ONLY',native_authorized=False,bindings={})
   with patch.dict(sys.modules,{'scripts.check_ihp_wsl_prepared':fake}),patch.object(c,'verify',return_value=(evidence,{})):
    result=c.prepare(source,prepared,evidence,projects)
   self.assertFalse(result['native_authorized']);self.assertFalse(result['approved_managed_six_module_loading']);self.assertFalse(result['native_adapter_ready']);self.assertTrue(result['host_acceptance_pending']);self.assertEqual(result['max_jobs'],20);self.assertEqual(result['job_timeout_seconds'],90)
