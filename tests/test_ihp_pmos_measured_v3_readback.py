import json,os,shutil,tempfile,unittest
from pathlib import Path
from scripts import materialize_ihp_pmos_measured_v3 as transport
from scripts import read_ihp_pmos_measured_v3 as reader
ROOT=Path(__file__).resolve().parents[1]
class PortableReadbackTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.parent=Path(cls.temp.name);cls.root=cls.parent/'relocated'
  cls.compact=ROOT/'docs/qualification/ihp-pmos-measured-reference-v3/evidence-compact.zip'
  cls.base=ROOT/'packaging/ngspice/ngspice-linux47-corrected-v1.zip'
  transport.materialize(cls.compact,cls.base,cls.root)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def mutate(self,rel,value):
  p=self.root/rel;old=p.read_bytes()
  try:
   p.write_bytes(value)
   with self.assertRaises(ValueError):reader.audit(self.root)
  finally:p.write_bytes(old)
 def test_relocation_complete_and_separate_labels(self):
  r=reader.audit(self.root)
  self.assertEqual(r['native_jobs'],20);self.assertEqual(r['native_points'],560)
  self.assertEqual(r['new_native_runs'],0);self.assertFalse(r['qualified']);self.assertFalse(r['independent_calibration'])
  self.assertEqual(r['original_numerical_audit'],'REJECTED_MULTIPLICITY_SCALING')
  self.assertEqual(r['source_aware_consistency'],'PASS')
  self.assertGreater(r['original_scaling_max_normalized'],1)
  self.assertLessEqual(r['source_aware_scaling_max_normalized'],1)
  self.assertEqual(len(r['residuals']['points']),140)
  self.assertEqual(r['measured_comparison_summary']['b']['zero_measured_count'],1)
 def test_manifest_tamper(self):self.mutate('MANIFEST.json',b'{}')
 def test_raw_tamper(self):self.mutate('measured-v3/attempt-1/runs/nominal-0/result.raw',b'changed')
 def test_source_law_tamper(self):self.mutate('source-aware-scaling-v1/sources/wrapper/sg13g2_moslv_mod.lib',b'changed')
 def test_contract_tamper(self):self.mutate('source-aware-scaling-v1/contract.json',b'{}')
 def test_missing_payload(self):
  p=self.root/'measured-v3/attempt-1/runs/nominal-0/result.raw';data=p.read_bytes();p.unlink()
  try:
   with self.assertRaises(ValueError):reader.audit(self.root)
  finally:p.write_bytes(data)
 def test_extra_payload(self):
  p=self.root/'extra';p.write_bytes(b'x')
  try:
   with self.assertRaises(ValueError):reader.audit(self.root)
  finally:p.unlink()
 def test_linked_payload(self):
  p=self.root/'link'
  try:p.symlink_to(self.root/'MANIFEST.json')
  except OSError as e:
   if os.name=='nt' and getattr(e,'winerror',None) in (1,50,1314):self.skipTest('Windows symlink creation unsupported')
   raise
  try:
   with self.assertRaises(ValueError):reader.audit(self.root)
  finally:p.unlink()
 def test_existing_destination_rejected(self):
  with self.assertRaisesRegex(ValueError,'Fresh'):transport.materialize(self.compact,self.base,self.root)
 def test_transport_tamper_prevents_output(self):
  p=self.parent/'bad.zip';p.write_bytes(b'invalid');out=self.parent/'never'
  with self.assertRaisesRegex(ValueError,'identity'):transport.materialize(p,self.base,out)
  self.assertFalse(out.exists())
 def test_base_tamper_prevents_output(self):
  p=self.parent/'bad-base.zip';p.write_bytes(b'invalid');out=self.parent/'never-base'
  with self.assertRaisesRegex(ValueError,'identity'):transport.materialize(self.compact,p,out)
  self.assertFalse(out.exists())
 def test_output_must_be_fresh(self):
  p=self.parent/'existing-output.json';p.write_text('preserve')
  with self.assertRaisesRegex(ValueError,'Fresh'):reader.write_output(self.root,p)
  self.assertEqual(p.read_text(),'preserve')
 def test_output_cannot_be_inside_evidence(self):
  with self.assertRaisesRegex(ValueError,'outside'):reader.write_output(self.root,self.root/'new-output.json')
  self.assertFalse((self.root/'new-output.json').exists())
 def test_import_whitelist_rejects_nonstdlib_reader(self):
  p=self.parent/'unreviewed.py';p.write_text('import os\n')
  with self.assertRaisesRegex(ValueError,'Unexpected'):reader.reviewed_module(p,'test_rejected')
 def test_windows311_reparse_attributes_rejected(self):
  from types import SimpleNamespace
  from unittest.mock import patch
  import stat
  fake=SimpleNamespace(st_mode=stat.S_IFDIR,st_file_attributes=0x400)
  with patch.object(Path,'lstat',return_value=fake):
   self.assertTrue(reader.is_linked(self.root));self.assertTrue(transport.is_linked(self.root))
   with self.assertRaisesRegex(ValueError,'Linked'):transport.unlinked(self.root)
if __name__=='__main__':unittest.main()
