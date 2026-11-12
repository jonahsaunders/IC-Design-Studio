"""New reconstructed builder tests; Docker never executes."""
import json,tempfile,unittest,subprocess
from pathlib import Path
from types import SimpleNamespace as R
from unittest.mock import patch
from scripts import build_ihp_wsl_research_base as b
class Builder(unittest.TestCase):
 def test_absence_vs_daemon_failure(self):
  with patch.object(b.subprocess,'run',return_value=R(returncode=1,stderr='No such object: owned',stdout='')) as run:
   self.assertEqual(b.cleanup_collector('owned','image')['status'],'absent');self.assertEqual(run.call_count,1)
  with patch.object(b.subprocess,'run',return_value=R(returncode=1,stderr='daemon unavailable',stdout='')):
   self.assertEqual(b.cleanup_collector('owned','image')['status'],'failed')
 def test_owned_only_cleanup(self):
  for actual in ['image','wrong']:
   calls=[R(returncode=0,stdout=json.dumps([{'Name':'/owned','Image':actual}]),stderr=''),R(returncode=0,stdout='owned',stderr='')]
   with patch.object(b.subprocess,'run',side_effect=calls) as run:
    result=b.cleanup_collector('owned','image');self.assertEqual(result['status'],'removed' if actual=='image' else 'failed')
    self.assertEqual(run.call_count,2 if actual=='image' else 1)
    if actual=='image':self.assertEqual(run.call_args.args[0],['docker','rm','--force','owned'])
 def test_timeout_preserved(self):
  with patch.object(b.subprocess,'run',side_effect=subprocess.TimeoutExpired(['docker'],10)):
   self.assertEqual(b.cleanup_collector('owned','image')['status'],'failed')
 def test_preflight_failure_retained_no_process(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);out=root/'out'
   with patch.object(b,'source_guard',side_effect=ValueError('unreviewed new policy')),patch.object(b.subprocess,'run') as run:
    with self.assertRaises(ValueError):b.build(root/'evidence',out,root/'policy','x')
    run.assert_not_called()
   r=json.loads((out/'completion.json').read_text());self.assertIn('unreviewed',r['failure']);self.assertFalse(r['pmos_executed']);self.assertEqual(r['cleanup']['collector']['status'],'not_started')
 def test_mocked_complete_builder_joins_and_cleanup(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);out=root/'out';evidence=root/'evidence';evidence.mkdir();calls=[]
   policy={'official_base':'ubuntu:24.04','build_context_sha256':'c','research_source_bindings':{}}
   def stage(path):path.mkdir();(path/'Dockerfile').write_text('FROM ubuntu:24.04\n')
   def process(argv,**kw):
    calls.append(argv);data=b'';rc=0;error=''
    if argv[:3]==['docker','image','inspect']:
     data=json.dumps([{'Id':'sha256:base' if argv[3]=='ubuntu:24.04' else 'sha256:private','Os':'linux','Architecture':'amd64','RepoDigests':['ubuntu@sha256:'+'a'*64]}]).encode()
    elif argv[:2]==['docker','create']:data=b'export-container\n'
    elif argv[:3]==['docker','container','inspect']:
     if argv[3]=='export-container':data=json.dumps([{'Image':'sha256:private'}]).encode()
     else:rc=1;error='No such object: '+argv[3]
    elif argv[:2]==['docker','export']:data=b'filesystem'
    elif argv[:2]==['docker','run']:
     report=out/'host-proof/receipt/report.json';report.parent.mkdir();image=json.loads((out/'image-receipt.json').read_text())
     report.write_text(json.dumps({'image':image,'build_inputs_sha256':b.file_sha(out/'build-inputs.json'),'base_archive_sha256':b.file_sha(out/'base-runtime.tar.gz')}))
    if hasattr(kw.get('stdout'),'write'):kw['stdout'].write(data)
    return R(returncode=rc,stdout=data.decode(),stderr=error)
   def prepared(base,bsha,e,out,host,hsha):out.mkdir();(out/'manifest.json').write_text('{}')
   with patch.object(b,'collector_user',return_value='1001:118'),patch.object(b,'source_guard',return_value=policy),patch.object(b,'verify',return_value=(evidence,{})),patch.object(b.shutil,'disk_usage',return_value=R(free=40*1024**3)),patch.object(b,'stage_context',side_effect=stage),patch.object(b,'cache_identity',return_value={'sha256':'c'}),patch.object(b,'context_identity',return_value={'sha256':'c'}),patch.object(b.subprocess,'run',side_effect=process),patch.object(b,'pack_filesystem',side_effect=lambda src,dst:dst.write_bytes(b'archive')),patch.object(b,'verify_host',return_value={'synthetic':True}),patch.object(b,'prepare',side_effect=prepared):
    b.build(evidence,out,root/'policy','p')
   result=json.loads((out/'result.json').read_text());done=json.loads((out/'completion.json').read_text())
   self.assertFalse(result['pmos_executed']);self.assertIsNone(done['failure']);self.assertFalse(done['cleanup_failed'])
   create=next(x for x in calls if x[:2]==['docker','create']);self.assertEqual(create[-1],'sha256:private')
   collect=next(x for x in calls if x[:2]==['docker','run']);self.assertIn('sha256:private',collect);self.assertIn('--base-archive-sha256',collect);self.assertEqual(collect[2:4],['--user','1001:118']);self.assertEqual(collect.count('--user'),1)
   self.assertEqual(json.loads((out/'build-inputs.json').read_text())['collector_host_user'],'1001:118')
   commands=json.loads((out/'commands.json').read_text());collector=next(x for x in commands if x['label']=='collect-signed-host-provenance');self.assertEqual(collector['timeout_seconds'],1800)
   self.assertIn('type=bind,src='+str(b.ROOT)+',dst=/research-tools,readonly',collect);self.assertIn('type=bind,src='+str(evidence/'measured-v3/attempt-1/engine/runtime')+',dst=/research-engine,readonly',collect)
   self.assertNotIn('--privileged',collect);self.assertNotIn('--cap-add',collect)
   self.assertEqual(done['cleanup']['collector']['status'],'absent');self.assertEqual(done['cleanup']['export_container']['status'],'removed')
 def test_historical_policy_not_reused(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);p=root/'policy';p.write_text(json.dumps({'review_state':'APPROVED_FOR_BUILD_ONLY','scope':'REVIEWED_SAME_RUN_WSL_RESEARCH_BUILD_NO_PMOS'}))
   with self.assertRaisesRegex(ValueError,'Historical policy'):b.source_guard(p,b.file_sha(p))


from types import SimpleNamespace
class CollectorUserTests(unittest.TestCase):
 def identity(self,uid=1001,gid=118,euid=None,egid=None,owner=None,platform='linux'):
  with patch.object(b.sys,'platform',platform),patch.object(b.os,'getuid',return_value=uid,create=True),patch.object(b.os,'getgid',return_value=gid,create=True),patch.object(b.os,'geteuid',return_value=uid if euid is None else euid,create=True),patch.object(b.os,'getegid',return_value=gid if egid is None else egid,create=True),patch.object(Path,'stat',return_value=SimpleNamespace(st_uid=uid if owner is None else owner)):
   return b.collector_user(Path('/fixture'))
 def test_numeric_host_user(self):self.assertEqual(self.identity(),'1001:118')
 def test_no_root_user_or_group(self):
  for fields in ({'uid':0},{'gid':0},{'uid':-1},{'gid':-1}):
   with self.subTest(fields=fields),self.assertRaisesRegex(ValueError,'Non-root'):self.identity(**fields)
 def test_no_boolean_identity(self):
  with self.assertRaises(ValueError):self.identity(uid=True)
 def test_reject_elevated_effective_identity(self):
  for fields in ({'euid':0},{'egid':0}):
   with self.subTest(fields=fields),self.assertRaisesRegex(ValueError,'effective'):self.identity(**fields)
 def test_reject_foreign_output_owner(self):
  with self.assertRaisesRegex(ValueError,'belong'):self.identity(owner=2222)
 def test_non_linux_fails_before_uid_calls(self):
  with patch.object(b.sys,'platform','win32'),patch.object(b.os,'getuid',create=True) as uid,self.assertRaisesRegex(ValueError,'Linux'):b.collector_user('/fixture')
  uid.assert_not_called()

if __name__=='__main__':unittest.main()
