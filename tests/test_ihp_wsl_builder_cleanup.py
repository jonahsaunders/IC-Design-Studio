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
   with patch.object(b,'source_guard',return_value=policy),patch.object(b,'verify',return_value=(evidence,{})),patch.object(b.shutil,'disk_usage',return_value=R(free=40*1024**3)),patch.object(b,'stage_context',side_effect=stage),patch.object(b,'cache_identity',return_value={'sha256':'c'}),patch.object(b,'context_identity',return_value={'sha256':'c'}),patch.object(b.subprocess,'run',side_effect=process),patch.object(b,'pack_filesystem',side_effect=lambda src,dst:dst.write_bytes(b'archive')),patch.object(b,'verify_host',return_value={'synthetic':True}),patch.object(b,'prepare',side_effect=prepared):
    b.build(evidence,out,root/'policy','p')
   result=json.loads((out/'result.json').read_text());done=json.loads((out/'completion.json').read_text())
   self.assertFalse(result['pmos_executed']);self.assertIsNone(done['failure']);self.assertFalse(done['cleanup_failed'])
   create=next(x for x in calls if x[:2]==['docker','create']);self.assertEqual(create[-1],'sha256:private')
   collect=next(x for x in calls if x[:2]==['docker','run']);self.assertIn('sha256:private',collect);self.assertIn('--base-archive-sha256',collect)
   self.assertEqual(done['cleanup']['collector']['status'],'absent');self.assertEqual(done['cleanup']['export_container']['status'],'removed')
 def test_historical_policy_not_reused(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);p=root/'policy';p.write_text(json.dumps({'review_state':'APPROVED_FOR_BUILD_ONLY','scope':'REVIEWED_SAME_RUN_WSL_RESEARCH_BUILD_NO_PMOS'}))
   with self.assertRaisesRegex(ValueError,'Historical policy'):b.source_guard(p,b.file_sha(p))
if __name__=='__main__':unittest.main()
