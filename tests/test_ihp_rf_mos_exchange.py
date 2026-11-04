"""IHP RF physical selectors survive generated Xschem exchange."""
import tempfile, unittest
from pathlib import Path
from icstudio.model import example,clone,save_project,load_project,file_digest
from icstudio.catalog import create_device,parameter_values
from icstudio.interchange import export_xschem
from icstudio.xschem_io import import_package,records,properties
from scripts.qualify_standard_mos import load_technology
from icstudio.pdk_import import template_values

VIEWS={'sg13_lv_rf_nmos':('sg13_lv_nmos','rfnmos'),'sg13_lv_rf_pmos':('sg13_lv_pmos','rfpmos'),
       'sg13_hv_rf_nmos':('sg13_hv_nmos','rfnmoshv'),'sg13_hv_rf_pmos':('sg13_hv_pmos','rfpmoshv')}
class ExchangeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.tech=load_technology('ihp-sg13g2')[0]
 def fixture(self):
  p=example('empty');p['pdk']=clone(self.tech);c=p['cells'][0];c['devices']=[];c['ports']=[]
  names=list(VIEWS)+['sg13_lv_nmos','sg13_lv_pmos','sg13_hv_nmos','sg13_hv_pmos']
  for i,name in enumerate(names):
   d=create_device(self.tech,'sg13g2_pr/'+name+'.sym',name);d.update(x=i*180,y=0)
   d['nets']={pin:f'n{i}_{pin}' for pin in ('d','g','s','b')};d['params'].update(w='2u',l='1u')
   c['devices'].append(d)
  return p
 def components(self,path):
  return {properties(r[6])['name']:properties(r[6]) for r in records(next(path.glob('*.sch')).read_text())
          if r[0]=='C' and 'model=' in r[6]}
 def test_all_eight_views_export_import_reexport_and_saved_revision(self):
  p=self.fixture();before=clone(p);lock=clone(p['pdk']['package_lock'])
  with tempfile.TemporaryDirectory() as td:
   folder=Path(td);export_xschem(p,folder/'first');parts=self.components(folder/'first')
   q,_=import_package(folder/'first')
   self.assertEqual(p,before);self.assertEqual(q['pdk']['package_lock'],lock)
   save_project(q,folder/'saved.icproj');q=load_project(folder/'saved.icproj')
   export_xschem(q,folder/'second');again=self.components(folder/'second')
   for d in p['cells'][0]['devices']:
    name=d['name'];props=parts['X_'+name];binding=self.tech['simulation']['catalog'][d['model_ref']['device']]
    after=next(a for a in q['cells'][0]['devices'] if a['model_ref']==d['model_ref'])
    self.assertEqual(after['nets'],d['nets']);self.assertEqual(parameter_values(binding,after),parameter_values(binding,d))
    if name in VIEWS:
     compact,selector=VIEWS[name]
     self.assertEqual(props.get('lvs_model'),selector)
     self.assertEqual(props['model'],compact)
     self.assertEqual(again['X_X_'+name].get('lvs_model'),selector)
    else:self.assertNotIn('lvs_model',props)
   self.assertNotIn('lvs_model',(folder/'first/simulation.cir').read_text())
 def test_selector_tamper_is_rejected_for_every_rf_view(self):
  for name,(_,selector) in VIEWS.items():
   with self.subTest(name=name),tempfile.TemporaryDirectory() as td:
    folder=Path(td);export_xschem(self.fixture(),folder)
    sch=next(folder.glob('*.sch'));text=sch.read_text()
    # Inject on current output as well, so this demonstrates the existing import gap.
    line=next(line for line in text.splitlines() if 'name=X_'+name+' ' in line)
    changed=line.replace('lvs_model="'+selector+'"','lvs_model="rfnmos_wrong"') if 'lvs_model=' in line else line[:-1]+' lvs_model="rfnmos_wrong"}'
    sch.write_text(text.replace(line,changed))
    with self.assertRaisesRegex(ValueError,'LVS selector changed'):import_package(folder)
 def test_legacy_export_without_selector_remains_readable_then_repairs_export(self):
  import re
  with tempfile.TemporaryDirectory() as td:
   folder=Path(td);export_xschem(self.fixture(),folder/'legacy')
   sch=next((folder/'legacy').glob('*.sch'));sch.write_text(re.sub(r' lvs_model="[^"]+"','',sch.read_text()))
   q,_=import_package(folder/'legacy');export_xschem(q,folder/'repaired')
   for name,(_,selector) in VIEWS.items():self.assertEqual(self.components(folder/'repaired')['X_X_'+name].get('lvs_model'),selector)
 def test_changed_public_metadata_fails_before_export(self):
  for name in VIEWS:
   for target in ('binding','instance'):
    p=self.fixture();d=next(d for d in p['cells'][0]['devices'] if d['name']==name)
    symbol=p['pdk']['simulation']['catalog'][d['model_ref']['device']]['symbol'] if target=='binding' else d['symbol']
    symbol['attributes']['template']=symbol['attributes']['template'].replace('lvs_model='+VIEWS[name][1],'lvs_model=wrong')
    with self.subTest(name=name,target=target),tempfile.TemporaryDirectory() as td:
     with self.assertRaisesRegex(ValueError,'source-defined LVS selector'):export_xschem(p,td)
if __name__=='__main__':unittest.main(verbosity=2)
