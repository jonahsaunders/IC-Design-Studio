"""Finite corrected guard template identity and ordinary linked-device lifecycle."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import example,clone,save_project,load_project,design_digest
from icstudio.catalog import create_device
from icstudio.ihp_resistors import specification,geometry,TEMPLATE_HASH as LEGACY_HASH
from icstudio import ihp_guard_routing as guard
from icstudio.ihp_layout import install_mos,regenerate_mos,audit
from icstudio.physical_cells import transform_selection
from icstudio.sky130_devices_ui import body_tie_field,set_body_tie
from scripts.qualify_standard_mos import load_technology
from scripts.ihp_guard_corner_conditioner import mask_identity

class GuardAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.tech=load_technology('ihp-sg13g2')[0]
    def project(self,model='rsil',corner=True):
        p=example('empty');p['pdk']=clone(self.tech);c=p['cells'][0];d=create_device(p['pdk'],'sg13g2_pr/'+model+'.sym','R1');d['model_params'].update(w='2u',l='7u');c['devices']=[d]
        if corner:d['physical_guard_routing']=guard.OPTION
        return p,c,d
    def test_three_templates_match_reviewed_geometry(self):
        data=guard.templates(self.tech)
        for model in ('rsil','rppd','rhigh'):
            p,c,d=self.project(model);install_mos(p,c['id'],d['id']);spec=c['pdk_layouts'][0]['spec']
            self.assertEqual(spec['recipe'],guard.RECIPE);self.assertFalse(spec['guard_native_equivalence']);self.assertEqual(spec['template_sha256'],guard.TEMPLATE_HASH)
            self.assertEqual(mask_identity(p),data['templates'][model]['mask_sha256'])
            self.assertEqual({v['pin']:v['layer'] for v in c['layout_pins']},{'p':'Metal1.drawing','m':'Metal1.drawing','body':'Metal2.drawing'})
            self.assertEqual(audit(p,c['id']),[])
    def test_legacy_default_spec_unchanged(self):
        p,c,d=self.project(corner=False);spec=specification(p['pdk'],d)
        self.assertEqual(spec['recipe'],'ihp-resistor-selected-v1');self.assertEqual(spec['template_sha256'],LEGACY_HASH)
        self.assertFalse(any(k.startswith('guard_') for k in spec));self.assertNotIn('physical_guard_routing',d)
        fields=body_tie_field(p['pdk'],d);self.assertEqual(fields[1][2][0],guard.NATIVE_LABEL)
    def test_fails_closed_on_unsupported_combinations(self):
        for changes in ({'model_params':{'w':'0.5u','l':'0.5u'}},{'physical_terminal_vias':True},{'physical_guard_routing':'all100'},{'physical_guard_routing':True},{'physical_guard_routing':None}):
            p,c,d=self.project();d.update(changes)
            with self.assertRaises(ValueError):specification(p['pdk'],d)
    def test_template_and_source_tamper_rejected(self):
        p,c,d=self.project()
        with patch.object(guard,'TEMPLATE_HASH','wrong'):
            with self.assertRaisesRegex(ValueError,'templates'):specification(p['pdk'],d)
        with patch.object(guard,'CIFOUT_HASH','wrong'):
            with self.assertRaisesRegex(ValueError,'cut-array'):specification(p['pdk'],d)
    def test_rotated_regeneration_switch_and_save_reopen(self):
        for model in ('rsil','rppd','rhigh'):
            for angle in (0,90):
                p,c,d=self.project(model);install_mos(p,c['id'],d['id'],30000,10000)
                if angle:transform_selection(p,c['id'],[s['id'] for s in c['shapes']],rotation=angle)
                original={v['pin']:v['point'] for v in c['layout_pins']};orientation=clone(c['pdk_layouts'][0].get('orientation',{'rotation':0,'mirror':False}))
                for _ in range(2):
                    d.pop('physical_guard_routing');self.assertTrue(audit(p,c['id']));regenerate_mos(p,c['id'],d['id']);self.assertFalse(audit(p,c['id']))
                    d['physical_guard_routing']=guard.OPTION;self.assertTrue(audit(p,c['id']));regenerate_mos(p,c['id'],d['id']);self.assertEqual({v['pin']:v['point'] for v in c['layout_pins']},original)
                    self.assertEqual(c['pdk_layouts'][0].get('orientation'),orientation)
                with tempfile.TemporaryDirectory() as tmp:
                    path=Path(tmp)/'saved.icproj';save_project(p,path);q=load_project(path);self.assertFalse(audit(q,c['id']));self.assertEqual(q['cells'][0]['pdk_layouts'],c['pdk_layouts'])
    def test_template_producer_rejects_port_only_tamper(self):
        from scripts import build_ihp_guard_app_templates as producer
        from icstudio.model import file_digest
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'saved.icproj';data={'shapes':[], 'layout_ports':[{'name':'B','layer':'Metal2.drawing','point':[0,0]}]}
            path.write_text(json.dumps(data))
            with patch.object(producer,'SAVED_PROJECT_SHA256',{'rsil':file_digest(path)}):
                producer.verify_saved_source(path,'rsil')
                data['layout_ports'][0]['layer']='Metal1.drawing';path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'ports/labels'):producer.verify_saved_source(path,'rsil')
    def test_option_eco_digest_and_atomic_form_validation(self):
        p,c,d=self.project(corner=False);install_mos(p,c['id'],d['id']);before=design_digest(p)
        set_body_tie(p,c['id'],d['id'],{'terminal_access':'Metal1','guard_routing':guard.CORNER_LABEL});self.assertNotEqual(before,design_digest(p));self.assertTrue(audit(p,c['id']))
        prior=clone(d)
        with self.assertRaises(ValueError):set_body_tie(p,c['id'],d['id'],{'terminal_access':'Metal2','guard_routing':guard.CORNER_LABEL})
        self.assertEqual(d,prior)
        d['model_params']['w']='0.5u';self.assertTrue(audit(p,c['id']))
        with self.assertRaises(ValueError):regenerate_mos(p,c['id'],d['id'])

if __name__=='__main__':unittest.main()
