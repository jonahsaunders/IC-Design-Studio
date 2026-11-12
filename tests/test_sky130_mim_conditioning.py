import os,json,hashlib,shutil,tempfile,unittest,sys,zipfile,importlib.util
from pathlib import Path

def load_isolated():
 folder=Path(__file__).resolve().parents[1]/'scripts/qualification/sky130_mim_conditioning';missing=object();previous={key:sys.modules.get(key,missing) for key in ('replay','readback')}
 def load(name):
  spec=importlib.util.spec_from_file_location('_icstudio_mim_qualification_test_'+name,folder/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
 try:
  replay=load('replay');sys.modules['replay']=replay
  readback=load('readback');sys.modules['readback']=readback
  return replay,readback,load('audit_pilot'),load('build_fixture'),load('build_runtime_lock')
 finally:
  for key,value in previous.items():
   if value is missing:sys.modules.pop(key,None)
   else:sys.modules[key]=value
replay,readback,audit_pilot,build_fixture,build_runtime_lock=load_isolated()
@unittest.skipUnless(all(k in os.environ for k in ('MIM_TEST_FIXTURE','MIM_TEST_FIXTURE_SHA','MIM_TEST_V4_ROOT','MIM_TEST_CONTRACT','MIM_TEST_CONTRACT_SHA','MIM_TEST_RUNTIME','MIM_TEST_RUNTIME_SHA','MIM_TEST_ENGINE')),'external retained qualification evidence required')
class PortableTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.fixture=Path(os.environ['MIM_TEST_FIXTURE']);cls.pin=os.environ['MIM_TEST_FIXTURE_SHA'];cls.manifest=replay.load_fixture(cls.fixture,cls.pin)[1]
 def test_selection_and_pinned_fixture(self):
  self.assertEqual(len(self.manifest['decks']),40)
  for key in self.manifest['decks']:
   info=replay.validate_deck((self.fixture/key).read_bytes(),key);self.assertIn(info['profile'],('e1','e2'))
  with self.assertRaises(ValueError):replay.load_fixture(self.fixture,'0'*64)
 def test_unsupported_deck_and_scope_fail(self):
  key='decks/p1-r0-hl/e1.cir';data=(self.fixture/key).read_bytes()
  for mutation in (b'\n.noise v(app_p1) V_app_p1 dec 1 1k 10g\n',b'\n.tran 1n 1u\n',b'\n.op\n',b'\n.param mc_mm_switch=1\n',b'\n.temp 100\n',b'\nRextra app_p1 0 1\n'):
   with self.subTest(mutation=mutation),self.assertRaises(ValueError):replay.validate_deck(data+mutation,key)
  with self.assertRaises(ValueError):replay.validate_deck(data,'decks/p1-r0-hl/e3.cir')
 def test_corrupt_and_rehashed_fixture_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   clone=Path(temp)/'fixture';shutil.copytree(self.fixture,clone);manifest=json.loads((clone/'manifest.json').read_bytes());key='decks/p1-r0-hl/e1.cir';p=clone/key;p.write_bytes(p.read_bytes()+b'\n.noise x y\n')
   with self.assertRaises(ValueError):replay.load_fixture(clone,self.pin)
   manifest['decks'][key]=hashlib.sha256(p.read_bytes()).hexdigest();(clone/'manifest.json').write_text(json.dumps(manifest))
   with self.assertRaises(ValueError):replay.load_fixture(clone,self.pin)
 def test_strict_json_and_paths(self):
  for data in (b'{"a":1,"a":2}',b'{"x":NaN}',b'{"x":Infinity}',b'{"x":1e999}'):
   with self.subTest(data=data),self.assertRaises(ValueError):replay.strict_json(data)
  for path in ('../x','/absolute','a/../../b','x\\y','C:/unsafe'):
   with self.subTest(path=path),self.assertRaises(ValueError):replay.child(self.fixture,path)
 def test_source_transform_rejects_changed_bytes(self):
  p=self.fixture/'assets/shared-models/pdk-models/dfa418b7569a255978e276cf.spice';data=p.read_bytes();derived=replay.transform(data,p.name);self.assertIn(b'hs1 a q1 vs1 {r1}',derived)
  with self.assertRaises(ValueError):replay.transform(data+b'\n* changed',p.name)
 def test_runtime_lock_proposal_round_trip(self):
  engine=Path(os.environ['MIM_TEST_ENGINE']);reference=json.loads(Path(os.environ['MIM_TEST_RUNTIME']).read_bytes());extras=[]
  with tempfile.TemporaryDirectory() as temp:
   out=Path(temp)/'runtime.json';proposal=build_runtime_lock.build(engine,reference['spice_scripts'],out,extras);self.assertTrue(proposal['review_required']);_,lock=replay.load_runtime(out,proposal['runtime_lock_sha256'],engine);self.assertEqual(lock['engine_sha256'],reference['engine_sha256']);self.assertEqual(lock['files'],reference['files'])
 def test_output_and_runtime_guards(self):
  runtime=os.environ['MIM_TEST_RUNTIME'];runtime_sha=os.environ['MIM_TEST_RUNTIME_SHA'];engine=os.environ['MIM_TEST_ENGINE'];case='decks/p1-r0-hl/e1.cir'
  with self.assertRaises(ValueError):replay.replay(self.fixture,self.pin,runtime,'0'*64,engine,self.fixture/'must-not-exist',case)
  with self.assertRaises(ValueError):replay.replay(self.fixture,self.pin,runtime,runtime_sha,engine,self.fixture/'must-not-exist',case)
  self.assertFalse((self.fixture/'must-not-exist').exists())
  with tempfile.TemporaryDirectory() as temp:
   with self.assertRaises(ValueError):replay.replay(self.fixture,self.pin,runtime,runtime_sha,engine,Path(temp),case)
 def test_strict_raw_header_and_index_mutations(self):
  root=Path(os.environ['MIM_TEST_V4_ROOT']);row=json.loads((root/'summary.json').read_bytes())[0];raw=(root/row['case']['name']/row['profile']/'result.raw').read_text();readback.raw_data(raw.encode())
  changes=[('Plotname: AC Analysis','Plotname: Transient Analysis'),('Flags: complex','Flags: real'),('No. Variables: 61','No. Variables: 60'),('No. Points: 8','No. Points: 9'),('\t1\tv(app_p1)\tvoltage','\t2\tv(app_p1)\tvoltage'),('\t1\tv(app_p1)\tvoltage','\t1\tv(app_p1)\tcurrent'),('\n0\t\t','\n1\t\t')]
  for old,new in changes:
   self.assertIn(old,raw)
   with self.subTest(old=old),self.assertRaises(ValueError):readback.raw_data(raw.replace(old,new,1).encode())
  with self.assertRaises(ValueError):readback.raw_data((raw+'extra\n').encode())
 def test_fault_console_and_timing_controls(self):
  valid={'detections':{'cross':True,'missing':True,'width':True}};audit_pilot.check_faults('e2',valid)
  with self.assertRaises(ValueError):audit_pilot.check_faults('e2',{'detections':{'cross':True,'missing':False,'width':True}})
  log='Doing analysis at TEMP = 27.000000 and TNOM = 27.000000\nNo. of Data Columns : 61\nNo. of Data Rows : 8\n';audit_pilot.check_console(log)
  for bad in (log.replace('27.000000','28.000000',1),log.replace('Rows : 8','Rows : 7'),log+'Error: failure\n'):
   with self.assertRaises(ValueError):audit_pilot.check_console(bad)
  receipt={'start_utc':'2026-01-01T00:00:00+00:00','end_utc':'2026-01-01T00:00:01+00:00','elapsed_seconds':1.0};audit_pilot.check_timing(receipt)
  for bad in (dict(receipt,elapsed_seconds=float('nan')),dict(receipt,elapsed_seconds=60),dict(receipt,end_utc='2025-01-01T00:00:00+00:00'),dict(receipt,end_utc='2025-12-31T23:59:59.9+00:00',elapsed_seconds=.1)):
   with self.assertRaises(ValueError):audit_pilot.check_timing(bad)
 def test_scientific_reader_rejects_rehashed_data(self):
  root=Path(os.environ['MIM_TEST_V4_ROOT']);contract=Path(os.environ['MIM_TEST_CONTRACT']);pin=os.environ['MIM_TEST_CONTRACT_SHA'];self.assertEqual(readback.read_v4(root,contract,pin)['runs'],40)
  with tempfile.TemporaryDirectory() as temp:
   dst=Path(temp);records=json.loads((root/'summary.json').read_bytes())
   for r in records:
    name=r['case']['name'];profile=r['profile'];target=dst/name/profile/'result.raw';target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name/profile/'result.raw',target)
   row=records[0];p=dst/row['case']['name']/row['profile']/'result.raw';lines=p.read_text().splitlines();idx=lines.index('Values:');lines[idx+19]='\t1.0e-3,0.0';p.write_text('\n'.join(lines)+'\n');row['raw_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();(dst/'summary.json').write_text(json.dumps(records))
   with self.assertRaises(ValueError):readback.read_v4(dst,contract,pin)
class OfflinePortableTests(unittest.TestCase):
 def test_module_imports_restore_existing_aliases_and_path(self):
  import types
  sentinel_replay=types.ModuleType('sentinel_replay');sentinel_readback=types.ModuleType('sentinel_readback');missing=object();old={k:sys.modules.get(k,missing) for k in ('replay','readback')};path=list(sys.path)
  try:
   sys.modules['replay']=sentinel_replay;sys.modules['readback']=sentinel_readback;modules=load_isolated();self.assertEqual(len(modules),5);self.assertIs(sys.modules['replay'],sentinel_replay);self.assertIs(sys.modules['readback'],sentinel_readback);self.assertEqual(sys.path,path)
  finally:
   for key,value in old.items():
    if value is missing:sys.modules.pop(key,None)
    else:sys.modules[key]=value
 def test_strict_json_rejects_duplicate_and_nonfinite(self):
  for data in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}'):
   with self.assertRaises(ValueError):replay.strict_json(data)
 def test_reviewed_windows_runtime_requires_companion(self):
  with tempfile.TemporaryDirectory() as temp:
   engine=Path(temp)/'ngspice.exe';engine.write_bytes(b'fixture')
   with self.assertRaises(ValueError):build_runtime_lock.windows_companion(engine,'86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453')
   companion=Path(temp)/'libomp140.x86_64.dll';companion.write_bytes(b'fixture');self.assertEqual(build_runtime_lock.windows_companion(engine,'86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453'),companion)
 def test_invalid_relative_paths(self):
  for name in ('../escape','/absolute','a/../../b','x\\y','C:/unsafe'):
   with self.assertRaises(ValueError):replay.child(Path.cwd(),name)
 def test_public_bundle_rebuilds_exact_fixture(self):
  bundle=Path(__file__).resolve().parents[1]/'docs/qualification/sky130-mim-conditioning-v1/fixture-bundle.zip'
  with tempfile.TemporaryDirectory() as temp:
   out=Path(temp)/'fixture';result=build_fixture.build(bundle,'c3f66bd57fdfcb95744061ae717142409ded07aa7c43cb4447a25feddd41c6c0','1d433b5a3317b36bbcfaa8cf9037146a74256c76e5f40ba4f2aac35463631eed',out)
   self.assertEqual(result['files'],387)
   with self.assertRaises(ValueError):build_fixture.build(bundle,'0'*64,'1d433b5a3317b36bbcfaa8cf9037146a74256c76e5f40ba4f2aac35463631eed',Path(temp)/'rejected')
 def test_public_bundle_rejects_extra_rehashed_path(self):
  bundle=Path(__file__).resolve().parents[1]/'docs/qualification/sky130-mim-conditioning-v1/fixture-bundle.zip'
  with tempfile.TemporaryDirectory() as temp:
   altered=Path(temp)/'altered.zip'
   with zipfile.ZipFile(bundle) as source,zipfile.ZipFile(altered,'x',compression=zipfile.ZIP_DEFLATED) as target:
    for info in source.infolist():target.writestr(info.filename,source.read(info.filename))
    target.writestr('../escape',b'untrusted')
   digest=hashlib.sha256(altered.read_bytes()).hexdigest()
   with self.assertRaises(ValueError):build_fixture.build(altered,digest,'1d433b5a3317b36bbcfaa8cf9037146a74256c76e5f40ba4f2aac35463631eed',Path(temp)/'output')
   self.assertFalse((Path(temp)/'output').exists())
 def test_public_bundle_missing_or_oversized_manifest_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   for name,member,data in (('missing.zip','other',b'x'),('large.zip','manifest.json',b'x'*1000001)):
    bundle=Path(temp)/name
    with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_DEFLATED) as z:z.writestr(member,data)
    with self.assertRaises(ValueError):build_fixture.build(bundle,hashlib.sha256(bundle.read_bytes()).hexdigest(),'1d433b5a3317b36bbcfaa8cf9037146a74256c76e5f40ba4f2aac35463631eed',Path(temp)/(name+'-out'))
if __name__=='__main__':unittest.main(verbosity=2)


