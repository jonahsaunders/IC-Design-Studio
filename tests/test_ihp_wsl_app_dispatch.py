"""Mocked dispatcher only: never starts Qt, WSL, a runtime or a native job."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import probe_ihp_wsl_research_app as p
from scripts import audit_ihp_wsl_research_app as a
from scripts.prepare_ihp_wsl_app_contract import SELECTION,sha
class DispatchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.out=self.root/'attempt';self.projects=self.root/'projects';self.projects.mkdir()
  rows=[]
  for route,i in SELECTION:
   key=f'{route}-{i}';file=self.projects/(key+'.icproj');file.write_text('{}');rows.append(dict(case=key,project=file.name,sha256=sha(file)))
  (self.projects/'projects.json').write_text(json.dumps({'cases':rows}));self.contract={'native_adapter_ready':True,'projects_manifest_sha256':sha(self.projects/'projects.json')}
 def invoke(self):return p.run(None,None,None,None,self.projects,self.out,None)
 def test_draft_fails_before_adapter(self):
  with patch.object(p,'preflight',return_value={'native_adapter_ready':False}),patch.object(p,'studio_adapter') as adapter,self.assertRaises(ValueError):self.invoke()
  adapter.assert_not_called();receipt=json.loads((self.root/'attempt.launch.json').read_text());self.assertFalse(receipt['launch_requested']);self.assertIn('NO_NATIVE_LAUNCH',receipt['status'])
 def test_preflight_error_retained(self):
  with patch.object(p,'preflight',side_effect=ValueError('bad authorization')),self.assertRaisesRegex(ValueError,'authorization'):self.invoke()
  self.assertIn('bad authorization',(self.root/'attempt.dispatch-failure.json').read_text())
 def test_dispatch_and_audit_each_once(self):
  def adapter(*args):
   args[-1].update(launch_requested=True,status='EXECUTED_PENDING_INDEPENDENT_NATIVE_AUDIT');(self.root/'attempt.launch.json').write_text('fixture only')
  result={'qualified':False,'installed_acceptance':False,'fixture_only':True}
  with patch.object(p,'preflight',return_value=self.contract),patch.object(p,'studio_adapter',side_effect=adapter) as call,patch.object(a,'audit_native',return_value=result) as audit:
   self.assertEqual(self.invoke(),result)
  self.assertEqual(call.call_count,1);self.assertEqual(audit.call_count,1);self.assertEqual(json.loads((self.root/'attempt.audit.json').read_text()),result)
 def test_native_uncertainty_not_overwritten(self):
  def adapter(*args):
   args[-1].update(launch_requested=True);(self.root/'attempt.launch.json').write_text('ORIGINAL UNKNOWN NATIVE RECEIPT');raise RuntimeError('lost final receipt')
  with patch.object(p,'preflight',return_value=self.contract),patch.object(p,'studio_adapter',side_effect=adapter) as call,patch.object(a,'audit_native') as audit,self.assertRaises(RuntimeError):self.invoke()
  self.assertEqual(call.call_count,1);audit.assert_not_called();self.assertEqual((self.root/'attempt.launch.json').read_text(),'ORIGINAL UNKNOWN NATIVE RECEIPT');self.assertTrue(json.loads((self.root/'attempt.dispatch-failure.json').read_text())['launch_requested'])
 def test_audit_failure_preserves_receipt(self):
  def adapter(*args):
   args[-1].update(launch_requested=True,status='EXECUTED_PENDING_INDEPENDENT_NATIVE_AUDIT');(self.root/'attempt.launch.json').write_text('FINAL NATIVE RECEIPT')
  with patch.object(p,'preflight',return_value=self.contract),patch.object(p,'studio_adapter',side_effect=adapter),patch.object(a,'audit_native',side_effect=ValueError('raw mismatch')),self.assertRaisesRegex(ValueError,'raw mismatch'):self.invoke()
  self.assertEqual((self.root/'attempt.launch.json').read_text(),'FINAL NATIVE RECEIPT');self.assertFalse((self.root/'attempt.audit.json').exists())
 def test_fresh_attempt_refuses_retry(self):
  (self.root/'attempt.launch.json').write_text('prior')
  with patch.object(p,'preflight') as pre,self.assertRaisesRegex(ValueError,'Fresh'):self.invoke()
  pre.assert_not_called();self.assertEqual((self.root/'attempt.launch.json').read_text(),'prior')
 def test_manifest_change_prevents_dispatch(self):
  (self.projects/'projects.json').write_text('{}')
  with patch.object(p,'preflight',return_value=self.contract),patch.object(p,'studio_adapter') as adapter,self.assertRaisesRegex(ValueError,'manifest'):self.invoke()
  adapter.assert_not_called()
