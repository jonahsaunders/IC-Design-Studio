"""Reconstructed source-only project/readback controls; no GUI/native launch."""
import json,tempfile,unittest
from pathlib import Path
from scripts.materialize_ihp_pmos_measured_v3 import materialize
from scripts.prepare_ihp_wsl_research_projects import prepare,split_deck,LIB
from icstudio.model import load_project
from icstudio.native_analysis import deck
class Projects(unittest.TestCase):
 def test_all_original_twenty_projects_and_protocol(self):
  repo=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);e=root/'e';materialize(repo/'docs/qualification/ihp-pmos-measured-reference-v3/evidence-compact.zip',repo/'packaging/ngspice/ngspice-linux47-corrected-v1.zip',e)
   out=root/'projects';r=prepare(e,out);old=e/'measured-v3/attempt-1';original=json.loads((old/'run.json').read_text())
   self.assertEqual([x['case'] for x in r['cases']],[f"{x['route']}-{x['gate_index']}" for x in original['runs']]);self.assertEqual(len(r['cases']),20)
   for row in r['cases']:
    p=load_project(out/row['project']);sources,statements=split_deck((old/'runs'/row['case']/'input.cir').read_text())
    self.assertEqual(p['cells'][0]['spice_statements'],statements);self.assertNotIn('simulation_runtime',p)
    self.assertEqual(p['analysis']['timeout'],90);self.assertFalse(p['analysis']['dc_startup'])
    text,_=deck(p,p['top'],p['analysis'],root/'not-run')
    science=[x for x in text.splitlines() if x and not x.startswith('*') and x!='.end']
    rendered=[' '.join(x.split()[:3])+' DC '+x.split()[3]+' AC 0' for x in sources]
    self.assertEqual(science,statements+rendered+['.temp 27','.dc VD 0 -1.35 -0.05'])
   with self.assertRaises(ValueError):prepare(e,out)
 def test_unexpected_controls_and_accuracy_rejected(self):
  for text in ['.control\npre_osdi evil\n.endc','invalid',' .option loosened']:
   with self.assertRaises(ValueError):split_deck(text)

# Additional independently reviewed source-protocol mutation controls.
import unittest
from scripts.prepare_ihp_wsl_research_projects import split_deck,LIB
DECK='''* fixture
.control
pre_osdi runtime/psp103.osdi
pre_osdi runtime/psp103_nqs.osdi
.endc
.lib "pdk/libs.tech/ngspice/models/cornerMOSlv.lib" mos_tt
.option reltol=1e-8 abstol=1e-16 vntol=1e-13
.option gminsteps=0 srcsteps=0
XDUT d g s b sg13_lv_pmos w=2u l=0.13u m=1
VD d 0 0
VG g 0 -0.5
VS s 0 0
VB b 0 0
.temp 27
.dc VD 0 -1.35 -0.05
.end
'''
class ProjectSourceTests(unittest.TestCase):
 def test_exact_statements_and_sources(self):
  sources,statements=split_deck(DECK);self.assertEqual(len(sources),4);self.assertEqual(statements[0],LIB);self.assertIn('XDUT d g s b sg13_lv_pmos w=2u l=0.13u m=1',statements)
 def test_control_injection(self):
  with self.assertRaisesRegex(ValueError,'Unexpected control'):split_deck(DECK.replace('pre_osdi runtime/psp103.osdi','shell bad'))
 def test_changed_sweep(self):
  with self.assertRaisesRegex(ValueError,'sweep'):split_deck(DECK.replace('-0.05','-0.01'))
 def test_changed_accuracy(self):
  with self.assertRaisesRegex(ValueError,'accuracy'):split_deck(DECK.replace('1e-8','1e-4'))
 def test_duplicate_dut(self):
  with self.assertRaisesRegex(ValueError,'DUT count'):split_deck(DECK+'XDUT d g s b duplicate\n')
 def test_missing_source(self):
  with self.assertRaisesRegex(ValueError,'Source count'):split_deck(DECK.replace('VB b 0 0\n',''))

if __name__=='__main__':unittest.main()
