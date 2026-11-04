"""Source-defined physical selectors, including capacitor and ambiguous imports."""
from pathlib import Path
import tempfile, unittest
from icstudio.catalog import create_device
from icstudio.interchange import export_xschem
from icstudio.model import clone,example
from icstudio.xschem_io import import_package,properties,records
from scripts.qualify_standard_mos import load_technology

class SelectorReviewTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.tech=load_technology('ihp-sg13g2')[0]
 def fixture(self,view):
  p=example('empty');p['pdk']=clone(self.tech)
  d=create_device(self.tech,'sg13g2_pr/'+view+'.sym','DUT')
  d['nets']={pin:'n'+str(i) for i,pin in enumerate(d['nets'])}
  p['cells'][0]['devices']=[d];return p
 def test_rf_capacitor_retains_separate_physical_selector(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);p=self.fixture('cap_rfcmim');export_xschem(p,folder/'first')
   line=next(r for r in records((folder/'first/top.sch').read_text()) if r[0]=='C' and 'model=' in r[6])
   self.assertEqual(properties(line[6])['model'],'cap_rfcmim')
   self.assertEqual(properties(line[6]).get('lvs_model'),'rfcmim')
   q,_=import_package(folder/'first');export_xschem(q,folder/'second')
   self.assertIn('lvs_model="rfcmim"',(folder/'second/top.sch').read_text())
   self.assertEqual(q['pdk']['package_lock'],p['pdk']['package_lock'])
 def test_ambiguous_external_selectors_rejected_in_either_order(self):
  for view,selector in (('sg13_lv_rf_nmos','rfnmos'),('cap_rfcmim','rfcmim')):
   for values in ((selector,'wrong'),('wrong',selector),(selector,selector)):
    with self.subTest(view=view,values=values),tempfile.TemporaryDirectory() as tmp:
     folder=Path(tmp);export_xschem(self.fixture(view),folder)
     path=folder/'top.sch';text=path.read_text();line=next(x for x in text.splitlines() if 'name=X_DUT ' in x)
     import re
     changed=re.sub(r' lvs_model="[^"]*"','',line)
     changed=changed[:-1]+''.join(' lvs_model="'+v+'"' for v in values)+'}'
     path.write_text(text.replace(line,changed))
     with self.assertRaisesRegex(ValueError,'LVS selector'):import_package(folder)
 def test_lookalike_format_placeholder_is_not_a_physical_selector(self):
  for view in ('sg13_lv_rf_nmos','cap_rfcmim'):
   p=self.fixture(view);d=p['cells'][0]['devices'][0]
   d['symbol']['attributes']['lvs_format']=d['symbol']['attributes']['lvs_format'].replace('@lvs_model','@lvs_model_shadow')
   with self.subTest(view=view),tempfile.TemporaryDirectory() as tmp:
    with self.assertRaisesRegex(ValueError,'source-defined LVS selector'):export_xschem(p,tmp)

if __name__=='__main__':unittest.main()
