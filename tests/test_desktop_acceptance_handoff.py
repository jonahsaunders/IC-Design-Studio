"""Actual tar/source/Git round trips and adversarial transfer controls; no EDA execution."""
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,sys,tarfile,tempfile,unittest,zipfile
HERE=Path(__file__).resolve().parent
REPO=HERE.parent if (HERE.parent/'icstudio').is_dir() else HERE.parent/'IC-Design-Studio'
REPO=Path(os.environ.get('ICSTUDIO_TEST_SOURCE_ROOT',str(REPO)))
HELPER=HERE/'desktop_acceptance_handoff.py' if (HERE/'desktop_acceptance_handoff.py').is_file() else REPO/'scripts/desktop_acceptance_handoff.py'
spec=importlib.util.spec_from_file_location('handoff',HELPER);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
class HandoffTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='desktop-handoff-')
  self.root=Path(self.temp.name).resolve()/'root';self.root.mkdir()
  def write(name,data):
   p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data if isinstance(data,bytes) else data.encode());return p
  self.write=write
  write('main.py','print("candidate")\n');write('LICENSE','test license\n')
  write('.github/workflows/build-desktop.yml','name: test\njobs:\n  package:\n    steps:\n      - uses: actions/upload-artifact@v4\n        with:\n          name: desktop-source-diagnostics-${{ runner.os }}\n          path: |\n            build/source-evidence\n            build/other-probe/*.json\n            build/digital-state/checks/**/report.json\n')
  asset=b'locked tech';package={'id':'sky130A','revision':'test','files':{'technology':hashlib.sha256(asset).hexdigest()}}
  package_bytes=json.dumps(package).encode()
  write('examples/sky130-qualification-lock.json',json.dumps({'id':'sky130A','revision':'test','manifest_sha256':hashlib.sha256(package_bytes).hexdigest()}))
  self.run_git('init','--quiet');self.run_git('add','main.py','LICENSE','.github','examples');self.run_git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')
  self.commit=self.run_git('rev-parse','HEAD')
  self.ident=dict(candidate=self.commit,run_id='42',attempt='1',os='Windows' if os.name=='nt' else 'Linux',machine='fixture',workspace=self.root.as_posix())
  self.identity=lambda root:dict(self.ident)
  exe='ICDesignStudio.exe' if os.name=='nt' else 'ICDesignStudio'
  write('dist/ICDesignStudio/'+exe,b'fixture executable')
  write('dist/ICDesignStudio/_internal/data',b'engine payload')
  payload='dist/ICDesignStudio/_internal/icstudio/assets/runtime/digital/'
  write(payload+'runtime.tar.gz',b'fixture runtime')
  write(payload+'manifest.json',json.dumps({'archive':'runtime.tar.gz','sha256':hashlib.sha256(b'fixture runtime').hexdigest()}))
  if os.name=='nt':
   write('dist/installers/IC-Design-Studio-0.0-Windows-x64-Setup.exe',b'fixture installer')
   write('dist/installers/IC-Design-Studio-0.0-Windows-x64-Portable.zip',b'fixture portable')
  write('build/physical-adapter/sky130A/package.json',package_bytes);write('build/physical-adapter/sky130A/technology',asset)
  write('build/source-evidence/report.json','{"status":"PASS"}')
  write('build/other-probe/receipt.json','{"scope":"source-only"}')
  write('build/digital-state/checks/old/report.json','{"status":"old"}')
  self.folder=self.root/'build/desktop-handoff'
 def tearDown(self):self.temp.cleanup()
 def run_git(self,*args):
  return subprocess.check_output(['git',*args],cwd=self.root,stderr=subprocess.DEVNULL,env={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}).decode().strip()
 def source_writer(self,root,dest):
  with zipfile.ZipFile(dest,'x') as z:
   for name in self.run_git('ls-files').splitlines():z.write(root/name,'IC-Design-Studio/'+name)
 def pack(self):
  return h.pack(self.root,self.folder,identity_fn=self.identity,source_writer=self.source_writer)
 def prepare_restore(self):
  rec=self.pack();self.clear_producer();return rec
 def clear_producer(self):
  shutil.rmtree(self.root/'dist')
  for name in ('physical-adapter','source-evidence','other-probe','desktop-handoff-source','digital-state'):
   shutil.rmtree(self.root/'build'/name)
 def restore(self):return h.restore(self.root,self.folder,identity_fn=self.identity)
 def manifest(self):return h.load(self.folder/h.MANIFEST)
 def save(self,record):(self.folder/h.MANIFEST).write_text(json.dumps(record),encoding='utf-8')
 def rewrite_tar(self,transform):
  path=self.folder/h.ARCHIVE
  with tarfile.open(path) as t:
   items=[(x,t.extractfile(x).read() if x.isfile() else None) for x in t.getmembers()]
  items=transform(items)
  with tarfile.open(path,'w',format=tarfile.PAX_FORMAT) as t:
   for x,b in items:t.addfile(x,io.BytesIO(b) if b is not None else None)
  rec=self.manifest();rec['archive'].update(sha256=h.sha(path),bytes=path.stat().st_size);self.save(rec)
 def reject(self):
  with self.assertRaises((ValueError,FileNotFoundError,KeyError,tarfile.TarError)):self.restore()
  self.assertFalse((self.root/h.READY).exists())
 def test_roundtrip_real_git_exact_files_and_source(self):
  old=self.prepare_restore();r=self.restore();self.assertEqual(r['status'],'PASS')
  self.assertEqual(h.collect(self.root,['dist/ICDesignStudio']),{k:v for k,v in old['files'].items() if k.startswith('dist/ICDesignStudio')})
  self.assertEqual(h.verified_source(self.root,self.root/h.SOURCE,identity_fn=self.identity),self.root/h.SOURCE)
  self.assertFalse((self.root/'build/digital-state').exists())
 def test_source_archive_remains_exact(self):
  old=self.prepare_restore();self.restore();self.assertEqual(h.sha(self.root/h.SOURCE),old['source']['sha256'])
 def generated_metadata(self,wrong=False):
  self.write('icstudio/simulation.py','ENGINE = "fixture"\n');self.write('icstudio/build_info.py','BUILD_COMMIT = "unknown"\n')
  self.run_git('add','icstudio');self.run_git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','metadata fixture')
  self.commit=self.run_git('rev-parse','HEAD');self.ident['candidate']=self.commit
  data=(self.root/'icstudio/simulation.py').read_bytes()
  fields=dict(ENGINE_SOURCE_HASH='0'*64 if wrong else hashlib.sha256(data).hexdigest(),WORKFLOW_SOURCE_HASH=hashlib.sha256(b'simulation.py'+data).hexdigest(),BUILD_COMMIT=self.commit,BUILD_BRANCH='fixture',BUILD_DIRTY=False)
  self.write('icstudio/build_info.py',''.join(k+' = '+repr(v)+'\n' for k,v in fields.items()))
 def test_generated_build_info_bound_to_exact_source(self):
  self.generated_metadata();self.prepare_restore();self.restore()
 def test_false_generated_source_hash_rejected(self):
  self.generated_metadata(wrong=True)
  with self.assertRaises(ValueError):self.pack()
 def test_actual_cli_pack_restore_with_existing_source_generator(self):
  self.write('scripts/desktop_acceptance_handoff.py',HELPER.read_bytes())
  self.write('scripts/release_archives.py',(REPO/'scripts/release_archives.py').read_bytes())
  self.write('icstudio/__init__.py',"__version__='0.0'\n")
  self.run_git('add','scripts','icstudio');self.run_git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','CLI fixture')
  commit=self.run_git('rev-parse','HEAD')
  env={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
  env.update(GITHUB_SHA=commit,GITHUB_RUN_ID='42',GITHUB_RUN_ATTEMPT='1',RUNNER_OS='Windows' if os.name=='nt' else 'Linux')
  for command in ('pack','restore'):
   result=subprocess.run([sys.executable,'-I','-B',str(self.root/'scripts/desktop_acceptance_handoff.py'),command,'--output' if command=='pack' else '--input',str(self.folder)],cwd=self.root,env=env,capture_output=True,timeout=30)
   self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
   self.assertEqual(json.loads(result.stdout)['candidate'],commit)
   if command=='pack':self.clear_producer()
  self.assertEqual(h.load(self.root/h.READY)['status'],'PASS')
 def test_existing_destination_never_overwritten(self):
  self.prepare_restore();self.write('dist/ICDesignStudio/owned',b'keep');self.reject();self.assertEqual((self.root/'dist/ICDesignStudio/owned').read_bytes(),b'keep')
 def test_preexisting_ready_rejected(self):
  self.prepare_restore();self.write(h.READY,'{}')
  with self.assertRaises(ValueError):self.restore()
 def test_stale_ready_runtime_not_replayed(self):
  self.prepare_restore();self.write('build/digital-state/ready.json','{}');self.reject()
 def test_wrong_candidate_rejected(self):
  self.prepare_restore();self.ident['candidate']='0'*40;self.reject()
 def test_wrong_run_rejected(self):
  self.prepare_restore();self.ident['run_id']='43';self.reject()
 def test_wrong_attempt_rejected(self):
  self.prepare_restore();self.ident['attempt']='2';self.reject()
 def test_wrong_host_rejected(self):
  self.prepare_restore();self.ident['os']='other';self.reject()
 def test_wrong_workspace_rejected(self):
  self.prepare_restore();self.ident['workspace']+='-other';self.reject()
 def test_wrong_machine_rejected(self):
  self.prepare_restore();self.ident['machine']='other';self.reject()
 def test_unknown_schema_rejected(self):
  self.prepare_restore();r=self.manifest();r['schema']=2;self.save(r);self.reject()
 def test_duplicate_json_rejected(self):
  self.prepare_restore();p=self.folder/h.MANIFEST;p.write_text(p.read_text().replace('"schema": 1','"schema": 1, "schema": 1'));self.reject()
 def test_outer_checksum_rejected(self):
  self.prepare_restore()
  with (self.folder/h.ARCHIVE).open('ab') as f:f.write(b'changed')
  self.reject()
 def test_inner_content_rejected_even_rehashed_archive(self):
  self.prepare_restore()
  def mutate(items):
   for i,(info,data) in enumerate(items):
    if info.name.endswith('/data'):items[i]=(info,b'X'*len(data))
   return items
  self.rewrite_tar(mutate);self.reject()
 def test_duplicate_tar_member_rejected(self):
  self.prepare_restore();self.rewrite_tar(lambda items:items+[items[-1]]);self.reject()
 def test_missing_member_rejected(self):
  self.prepare_restore();self.rewrite_tar(lambda items:items[:-1]);self.reject()
 def test_extra_member_rejected(self):
  self.prepare_restore()
  def mutate(items):
   x=tarfile.TarInfo('build/extra');x.size=1;return items+[(x,b'x')]
  self.rewrite_tar(mutate);self.reject()
 def test_parent_traversal_rejected_even_rehashed(self):
  self.prepare_restore();r=self.manifest();old='dist/ICDesignStudio/_internal/data';new='../escaped';r['files'][new]=r['files'].pop(old);self.save(r)
  def mutate(items):
   for i,d in items:
    if i.name==old:i.name=new
   return items
  self.rewrite_tar(mutate);self.reject();self.assertFalse((self.root.parent/'escaped').exists())
 def test_absolute_path_rejected(self):
  self.prepare_restore();r=self.manifest();r['files']['/absolute']=r['files'].pop('dist/ICDesignStudio/_internal/data');self.save(r);self.reject()
 def test_case_collision_rejected(self):
  self.prepare_restore();r=self.manifest();r['files']['DIST/ICDesignStudio']=r['files']['dist/ICDesignStudio'];self.save(r);self.reject()
 def test_special_mode_rejected(self):
  self.prepare_restore();r=self.manifest();r['files']['dist/ICDesignStudio']['mode']=0o4755;self.save(r);self.reject()
 def test_hardlink_rejected(self):
  self.prepare_restore()
  def mutate(items):
   for i,(x,b) in enumerate(items):
    if x.name.endswith('/data'):x.type=tarfile.LNKTYPE;x.linkname='main.py';items[i]=(x,None)
   return items
  self.rewrite_tar(mutate);self.reject()
 def test_bad_adapter_rejected_before_pack(self):
  self.write('build/physical-adapter/sky130A/technology',b'changed')
  with self.assertRaises(ValueError):self.pack()
 def test_bad_runtime_rejected_before_pack(self):
  self.write('dist/ICDesignStudio/_internal/icstudio/assets/runtime/digital/runtime.tar.gz',b'changed')
  with self.assertRaises(ValueError):self.pack()
 def test_changed_source_rejected_before_pack(self):
  self.write('main.py','different source\n')
  with self.assertRaises(ValueError):self.pack()
 def test_unsafe_source_zip_rejected(self):
  with zipfile.ZipFile(self.root/'bad.zip','w') as z:z.writestr('IC-Design-Studio/../../escape','x')
  with self.assertRaises(ValueError):h.source_zip(self.root/'bad.zip')
 def test_source_duplicate_case_rejected(self):
  with zipfile.ZipFile(self.root/'bad.zip','w') as z:z.writestr('IC-Design-Studio/main.py','x');z.writestr('IC-Design-Studio/MAIN.py','y')
  with self.assertRaises(ValueError):h.source_zip(self.root/'bad.zip')
 def test_source_corruption_after_restore_rejected(self):
  self.prepare_restore();self.restore()
  with (self.root/h.SOURCE).open('ab') as f:f.write(b'changed')
  with self.assertRaises(ValueError):h.verified_source(self.root,self.root/h.SOURCE,identity_fn=self.identity)
 @unittest.skipIf(os.name=='nt','POSIX symlink and mode transport exercised on Linux')
 def test_symlink_and_0664_mode_preserved(self):
  p=self.root/'dist/ICDesignStudio/_internal/data';p.chmod(0o664)
  (p.parent/'alias').symlink_to('data');old=self.prepare_restore();self.restore()
  self.assertEqual(p.stat().st_mode&0o777,0o664);self.assertTrue((p.parent/'alias').is_symlink())
 @unittest.skipIf(os.name=='nt','POSIX unsafe-link fixture exercised on Linux')
 def test_external_symlink_rejected_before_pack(self):
  (self.root/'dist/ICDesignStudio/_internal/escape').symlink_to('/etc/passwd')
  with self.assertRaises(ValueError):self.pack()
 @unittest.skipIf(os.name=='nt','POSIX input-link fixture exercised on Linux')
 def test_linked_manifest_input_rejected(self):
  self.prepare_restore();p=self.folder/h.MANIFEST;target=self.root/'retained-manifest.json';p.rename(target);p.symlink_to(target)
  self.reject()
 @unittest.skipIf(os.name=='nt','POSIX input-link fixture exercised on Linux')
 def test_linked_archive_input_rejected(self):
  self.prepare_restore();p=self.folder/h.ARCHIVE;target=self.root/'retained-payload.tar';p.rename(target);p.symlink_to(target)
  self.reject()



class FixturePathTests(unittest.TestCase):
 def test_aliased_temporary_directory_keeps_canonical_workspace_identity(self):
  from types import SimpleNamespace
  from unittest.mock import patch
  with tempfile.TemporaryDirectory(prefix='handoff-alias-') as tmp:
   actual=Path(tmp).resolve();alias_parent=actual/'alias';alias_parent.mkdir()
   lexical=alias_parent/'..'
   self.assertNotEqual(lexical,actual);self.assertEqual(lexical.resolve(),actual)
   fixture=HandoffTests()
   with patch.object(tempfile,'TemporaryDirectory',return_value=SimpleNamespace(name=str(lexical),cleanup=lambda:None)):
    fixture.setUp()
   try:
    self.assertEqual(fixture.root,(actual/'root').resolve())
    original=fixture.prepare_restore();restored=fixture.restore()
    self.assertEqual(restored['status'],'PASS')
    self.assertEqual(original['identity']['workspace'],fixture.root.as_posix())
    self.assertEqual(h.sha(fixture.root/h.SOURCE),original['source']['sha256'])
   finally:fixture.tearDown()

if __name__=='__main__':unittest.main()
