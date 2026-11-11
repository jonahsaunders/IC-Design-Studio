"""Reconstructed consumer regressions; no prepared host or native acceptance."""
import json,tempfile,unittest
from pathlib import Path
from scripts import check_ihp_wsl_prepared as c
class Prepared(unittest.TestCase):
 def fixture(self,root):
  payload=root/'experimental-payload';payload.mkdir();(payload/'runtime.tar.gz').write_bytes(b'archive')
  host={'base_archive_sha256':'b'*64};(root/'host-contract.json').write_bytes(c.encoded(host));h=c.file_sha(root/'host-contract.json')
  manifest={'archive':'runtime.tar.gz','bytes':7,'sha256':c.file_sha(payload/'runtime.tar.gz'),'experimental_research':{'base_archive_sha256':'b'*64,'host_contract_sha256':h}}
  (payload/'manifest.json').write_bytes(c.encoded(manifest))
  r={'status':'PREPARED_PENDING_WINDOWS_NATIVE_REVIEW','qualified':False,'pmos_executed':False,'policy_sha256':'a'*64,'payload_manifest_sha256':c.file_sha(payload/'manifest.json'),'host_contract_sha256':h,'base_archive_sha256':'b'*64}
  done={'failure':None,'cleanup_failed':False,'pmos_executed':False,'source_policy_sha256':'a'*64,'cleanup':{'collector':{'status':'absent'},'export_container':{'status':'removed'}}}
  (root/'result.json').write_bytes(c.encoded(r));(root/'completion.json').write_bytes(c.encoded(done));return r,done
 def test_clean_preparation_is_not_native_authorization(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);self.fixture(root);r=c.check(root);self.assertFalse(r['native_authorized']);self.assertFalse(r['qualified'])
 def test_archive_missing_or_changed_rejects(self):
  for value in (None,b'changed',b'short'):
   with self.subTest(value=value),tempfile.TemporaryDirectory() as t:
    root=Path(t);self.fixture(root);p=root/'experimental-payload/runtime.tar.gz'
    if value is None:p.unlink()
    else:p.write_bytes(value)
    with self.assertRaises(ValueError):c.check(root)
 def test_completion_failure_rejects(self):
  for key,value in [('failure','timeout'),('cleanup_failed',True),('source_policy_sha256','x')]:
   with tempfile.TemporaryDirectory() as t:
    root=Path(t);r,d=self.fixture(root);d[key]=value
    with self.assertRaises(ValueError):c.check_records(r,d)
 def test_host_base_mismatch_rejects(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);r,d=self.fixture(root);r['base_archive_sha256']='wrong';(root/'result.json').write_bytes(c.encoded(r))
   with self.assertRaises(ValueError):c.check(root)
if __name__=='__main__':unittest.main()
