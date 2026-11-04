import json,math,pathlib,shutil,tempfile,unittest
from scripts.qualification_sky130_mos_voltage import QualificationVoltageContract,DEFAULT_PACKAGE,HERE
class VoltageContractTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.q=QualificationVoltageContract()
 def point(self,**kw):return {'vds':1,'vgs':1,'vbs':0,'temperature_c':27,**kw}
 def test_inventory_and_exact_alias_bindings(self):
  inventory=self.q.model_inventory();self.assertEqual(len(inventory),17);self.assertEqual(sum(bool(x['catalog_bindings']) for x in inventory),16);self.assertEqual(len(self.q.aliases),40)
  for key,model in self.q.aliases.items():
   r=self.q.screen(self.point(catalog_key=key));self.assertEqual(r['model'],model);self.assertEqual(r['catalog_binding']['model_source'],self.q.lock['models'][model]['aliases'][key]['model_source']);self.assertFalse(r['simulator_restriction'])
 def test_public_only_model_has_no_invented_catalog_alias(self):
  key='sky130_fd_pr__esd_pfet_g5v0d10v5';r=self.q.screen(self.point(model=key,vds=-1,vgs=-1));self.assertEqual(r['catalog_status'],'public_source_only');self.assertIsNone(r['catalog_binding']);self.assertTrue(r['package_model_files'])
  with self.assertRaises(ValueError):self.q.screen(self.point(catalog_key='sky130_fd_pr/esd_pfet_g5v0d10v5.sym'))
 def test_ambiguity_cannot_select_unreviewed_models(self):
  for model in ('sky130_fd_pr__esd_nfet_01v8','sky130_fd_pr__esd_nfet_05v0_nvt','sky130_fd_pr__esd_nfet_g5v0d10v5','sky130_fd_pr__esd_nfet_g5v0d10v5_nvt'):
   with self.assertRaises(ValueError):self.q.screen(self.point(model=model))
  with self.assertRaises(ValueError):self.q.screen(self.point(model='nfet_01v8'))
  with self.assertRaises(ValueError):self.q.screen(self.point(model='sky130_fd_pr__nfet_01v8',catalog_key='sky130_fd_pr/nfet_01v8.sym'))
 def test_exact_conditional_and_source_relative_sign(self):
  model='sky130_fd_pr__nfet_g5v0d16v0';self.assertEqual(self.q.screen(self.point(model=model,vds=16,vgs=0))['three_axis_status'],'WITHIN_DOCUMENTED_LIMITS');self.assertEqual(self.q.screen(self.point(model=model,vds=16,vgs=math.nextafter(0,1)))['three_axis_status'],'OUTSIDE_DOCUMENTED_LIMITS')
  model='sky130_fd_pr__pfet_g5v0d16v0';self.assertEqual(self.q.screen(self.point(model=model,vds=-16,vgs=0))['three_axis_status'],'WITHIN_DOCUMENTED_LIMITS');self.assertEqual(self.q.screen(self.point(model=model,vds=-16,vgs=-.001))['three_axis_status'],'OUTSIDE_DOCUMENTED_LIMITS')
 def test_evidence_domains_are_distinct(self):
  hist=self.q.screen(self.point(model='sky130_fd_pr__nfet_01v8'));self.assertEqual(hist['historical_native_bias']['status'],'discrete_samples');self.assertEqual(hist['historical_native_bias']['revision'],'1901822ae8f81ae1');self.assertNotEqual(hist['historical_native_bias']['revision'],hist['package_revision']);self.assertEqual(hist['current_package_native_coverage'],'NOT_ESTABLISHED');self.assertEqual(hist['point_was_natively_exercised'],'NOT_ESTABLISHED')
  isolated=self.q.screen(self.point(model='sky130_fd_pr__nfet_20v0_iso'));self.assertEqual(isolated['all_terminal_voltage_status'],'NOT_ESTABLISHED');self.assertEqual(isolated['historical_native_bias']['status'],'not_in_this_bias_record');self.assertIsNone(isolated['historical_native_bias']['axis_spans_v'])
  self.assertEqual(hist['absolute_maximum_ratings'],'NOT_ESTABLISHED');self.assertEqual(hist['pcell_geometry_bounds'],'NOT_ASSESSED');self.assertEqual(hist['temperature_validity_status'],'NOT_ESTABLISHED');self.assertFalse(hist['qualified'])
 def test_fact_schema_signed_terminal_source_and_explicit_unknowns(self):
  for row in self.q.model_inventory():
   self.assertFalse(row['qualified']);self.assertIsNone(row['unresolved']['absolute_ratings']['value']);self.assertIsNone(row['unresolved']['temperature_validity']['value']);self.assertIsNone(row['unresolved']['pcell_geometry']['value'])
   for fact in row['published_facts']:
    self.assertEqual(fact['semantic_kind'],'model_validity');self.assertEqual(fact['units'],'V');self.assertTrue(fact['lower_inclusive'] and fact['upper_inclusive']);self.assertIn(fact['relation'],('V(d)-V(s)','V(g)-V(s)','V(b)-V(s)'));self.assertEqual(len(fact['source']['sha256']),64);self.assertEqual(len(fact['source']['lines']),2)
 def test_invalid_numbers_and_extra_inputs_rejected(self):
  for value in (True,'1',None,float('inf'),float('nan')):
   with self.assertRaises(ValueError):self.q.screen(self.point(model='sky130_fd_pr__nfet_01v8',vds=value))
  with self.assertRaises(ValueError):self.q.screen(self.point(model='sky130_fd_pr__nfet_01v8',sub=0))
 def test_locked_package_model_and_symbol_tampering_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   dst=pathlib.Path(tmp);shutil.copyfile(DEFAULT_PACKAGE/'package.json',dst/'package.json');paths=set()
   for row in self.q.lock['models'].values():
    paths.update(row['package_model_files']);paths.update(b['symbol_source'] for b in row['aliases'].values())
   for rel in paths:
    p=dst/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(DEFAULT_PACKAGE/rel,p)
   QualificationVoltageContract(dst)
   key='sky130_fd_pr/nfet_01v8.sym';binding=self.q.lock['models']['sky130_fd_pr__nfet_01v8']['aliases'][key]
   for rel in (binding['model_source'],binding['symbol_source'],'package.json'):
    p=dst/rel;data=p.read_bytes();p.write_bytes(data+b'\n* changed\n')
    with self.assertRaises(ValueError):QualificationVoltageContract(dst)
    p.write_bytes(data)
 def test_contract_or_public_source_tamper_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   dst=pathlib.Path(tmp);shutil.copytree(HERE/'sources',dst/'sources')
   for name in ('catalog-source-lock.json','source-lock.json','gap-acceptance-table.json'):shutil.copyfile(HERE/name,dst/name)
   for rel in ('catalog-source-lock.json','source-lock.json','gap-acceptance-table.json','sources/device-details.rst'):
    p=dst/rel;data=p.read_bytes();p.write_bytes(data+b'changed')
    with self.assertRaises(ValueError):QualificationVoltageContract(DEFAULT_PACKAGE,dst)
    p.write_bytes(data)
if __name__=='__main__':unittest.main(verbosity=2)
