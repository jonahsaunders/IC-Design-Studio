"""Bounded IHP resistor template, ECO and interface regression checks."""
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
from scripts.qualify_standard_mos import load_technology
from icstudio.catalog import create_device
from icstudio.model import clone,example
from icstudio.ihp_resistors import specification,geometry
from icstudio.ihp_layout import install_mos,regenerate_mos,audit
from icstudio.physical_cells import transform_selection

class IHPResistorEditorTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.tech=load_technology('ihp-sg13g2')[0]
 def device(self,model='rsil'):
  return create_device(self.tech,'sg13g2_pr/'+model+'.sym','R1')
 def test_reject_unsupported(self):
  for values in ({'physical_terminal_vias':1},{'physical_terminal_vias':'false'}):
   d=self.device();d.update(values)
   with self.assertRaises(ValueError):specification(self.tech,d)
  for model,params in [('rsil',{'w':'0.500001u'}),('rsil',{'m':'2'}),('rppd',{'b':'1'})]:
   d=self.device(model);d['model_params'].update(params)
   with self.assertRaises(ValueError):specification(self.tech,d)
 def test_identity_mutations(self):
  d=self.device();tech=clone(self.tech);tech['package_lock']['revision']='changed'
  with self.assertRaises(ValueError):specification(tech,d)
  from icstudio import ihp_resistors
  original=ihp_resistors.file_digest
  with patch.object(ihp_resistors,'file_digest',side_effect=lambda p:'changed' if p.name=='ihp-sg13g2-res.tcl' else original(p)):
   with self.assertRaises(ValueError):specification(self.tech,d)
  with patch.object(ihp_resistors,'TEMPLATE_HASH','changed'):
   with self.assertRaises(ValueError):specification(self.tech,d)
  with patch.object(ihp_resistors,'file_digest',side_effect=FileNotFoundError()):
   with self.assertRaises(ValueError):specification(self.tech,d)
  with patch.object(Path,'read_bytes',side_effect=FileNotFoundError()):
   with self.assertRaises(ValueError):specification(self.tech,d)
  original_read=Path.read_bytes
  def formatted(path):
   raw=original_read(path)
   return json.dumps(json.loads(raw),indent=4).encode() if path.name=='package.json' else raw
  with patch.object(Path,'read_bytes',formatted):specification(self.tech,d)
  def duplicate(path):
   raw=original_read(path)
   return b'{\"id\":\"ihp-sg13g2\",'+raw[1:] if path.name=='package.json' else raw
  with patch.object(Path,'read_bytes',duplicate):
   with self.assertRaises(ValueError):specification(self.tech,d)
  def nonfinite(path):
   raw=original_read(path)
   return b'{\"invalid\":NaN,'+raw[1:] if path.name=='package.json' else raw
  with patch.object(Path,'read_bytes',nonfinite):
   with self.assertRaises(ValueError):specification(self.tech,d)
  tech=clone(self.tech);tech['package_lock']['manifest_hash']='changed'
  with self.assertRaises(ValueError):specification(tech,d)
 def test_independent_footprints_and_stale_access(self):
  p=example('empty');p['pdk']=clone(self.tech);c=p['cells'][0];a=self.device();b=create_device(self.tech,'sg13g2_pr/rsil.sym','R2');c['devices']=[a,b]
  install_mos(p,c['id'],a['id']);install_mos(p,c['id'],b['id'],30000,0)
  self.assertFalse(c.get('layout_texts'));self.assertEqual(len(c['layout_pins']),6)
  a['physical_terminal_vias']=True;self.assertTrue(any(v['code']=='PDK.STALE' for v in audit(p,c['id'])))
  regenerate_mos(p,c['id'],a['id']);self.assertFalse(audit(p,c['id']))
  pins={v['pin']:v for v in c['layout_pins'] if v['device_id']==a['id']};self.assertEqual(pins['p']['layer'],'Metal2.drawing');self.assertEqual(pins['body']['layer'],'Metal1.drawing')
  self.assertTrue(all(v['layer']=='Metal1.drawing' for v in c['layout_pins'] if v['device_id']==b['id']))
  from icstudio.physical_cells import assign_port
  from icstudio.interchange import export_layout
  from icstudio.layout_import import read_layout
  c['ports']=list(a['nets'].values())+list(b['nets'].values())
  for pin in c['layout_pins']:
   device=a if pin['device_id']==a['id'] else b
   assign_port(p,c['id'],device['nets'][pin['pin']],pin['layer'],pin['point'])
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'two.gds';export_layout(p,path);q,_=read_layout(path)
   texts=[v['text'] for v in q['cells'][0]['layout_texts']]
   self.assertCountEqual(texts,c['ports'])
 def test_transformed_eco(self):
  p=example('empty');p['pdk']=clone(self.tech);c=p['cells'][0];d=self.device();c['devices']=[d];install_mos(p,c['id'],d['id'])
  ids=[s['id'] for s in c['shapes']];transform_selection(p,c['id'],ids,rotation=90)
  before={v['pin']:v['point'] for v in c['layout_pins']};regenerate_mos(p,c['id'],d['id']);after={v['pin']:v['point'] for v in c['layout_pins']};self.assertEqual(before,after)
if __name__=='__main__':unittest.main()
