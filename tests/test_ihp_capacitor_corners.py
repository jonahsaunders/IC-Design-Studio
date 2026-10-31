import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from icstudio.model import clone, example, History, save_project, load_project
from icstudio.catalog import create_device
from icstudio.ihp_capacitor_corners import add_profiles, CHOICES, CAP, KEY, labels
from icstudio.interchange import spice
from icstudio.pdks import model_lines, stage_model_deck
from scripts.qualify_standard_mos import load_technology

class IHPCapacitorCorners(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.tech=load_technology('ihp-sg13g2')[0]

    def test_exact_sections_old_keys_and_lock(self):
        old=clone(self.tech);new=add_profiles(old)
        self.assertEqual(old,self.tech);self.assertEqual(new['package_lock'],old['package_lock'])
        self.assertEqual(add_profiles(new),new);self.assertEqual(set(labels(new)),set(CHOICES))
        for original,updated in zip(old['simulation']['includes'],new['simulation']['includes']):
            for k,v in original['sections'].items():self.assertEqual(updated['sections'][k],v)
            for key,(section,_) in CHOICES.items():
                self.assertEqual(updated['sections'][key],section if original['path']==CAP else original['sections']['nominal'])
        for k in ('nominal','slow','fast'):self.assertEqual(model_lines(old,k),model_lines(new,k))
        with self.assertRaisesRegex(ValueError,'Missing model section'):model_lines(old,'cap_bcs')

    def test_labels_do_not_certify_a_changed_mapping(self):
        t=add_profiles(self.tech);item=t['simulation']['includes'][1]
        item['sections']['nominal']='dio_ss'
        for key in CHOICES:item['sections'][key]='dio_ss'
        self.assertEqual(labels(t),{})
        with self.assertRaises(ValueError):add_profiles(t)

    def test_conflicts_and_tampered_lock_fail(self):
        for mutation in ('include','alias','lock','revision','provenance'):
            t=clone(self.tech)
            if mutation=='include':t['simulation']['includes'][1]['sections']['nominal']='dio_ss'
            if mutation=='alias':t['simulation']['includes'][1]['sections'][next(iter(CHOICES))]='dio_tt'
            if mutation=='lock':t['package_lock']['files'][CAP]='0'*64
            if mutation=='revision':t['package_lock']['revision']='other'
            if mutation=='provenance':t[KEY]={'scope':'changed'}
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):add_profiles(t)
        from icstudio import pdks
        original=pdks.file_digest
        with patch.object(pdks,'file_digest',side_effect=lambda path: '0'*64 if str(path).replace('\\','/').endswith(CAP) else original(path)):
            with self.assertRaisesRegex(ValueError,'missing or changed'):add_profiles(self.tech)

    def test_save_reopen_undo_and_staged_mixed_family_deck(self):
        p=example('empty');p['pdk']=clone(self.tech)
        p['cells'][0]['devices']=[create_device(p['pdk'],'sg13g2_pr/cap_cmim.sym','C1'),create_device(p['pdk'],'sg13g2_pr/sg13_lv_nmos.sym','M1')]
        history=History(p);history.commit(lambda q:q.update(pdk=add_profiles(q['pdk'])))
        self.assertEqual(history.project['analysis'].get('corner','nominal'),p['analysis'].get('corner','nominal'))
        history.undo();self.assertNotIn(KEY,history.project['pdk']);history.redo()
        key='icstudio_cap_bcs_others_nominal';history.commit(lambda q:q['analysis'].update(corner=key))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'project.icproj';save_project(history.project,path);restored=load_project(path)
            self.assertEqual(restored['analysis']['corner'],key);self.assertEqual(restored['pdk'][KEY],history.project['pdk'][KEY])
            text=spice(restored,settings=restored['analysis']);staged=stage_model_deck(restored['pdk'],text,root/'stage')
            self.assertIn('cap_bcs',staged);self.assertIn('mos_tt',staged)
            self.assertIn('cap_cmim',staged);self.assertIn('sg13_lv_nmos',staged)
            for item in restored['pdk']['simulation']['includes']:
                self.assertIn(' '+item['sections'][key],staged)

if __name__=='__main__':unittest.main()
