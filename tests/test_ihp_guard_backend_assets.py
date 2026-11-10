import json,os,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from icstudio import ihp_guard_routing as guard,ihp_resistors
from icstudio.ihp_resistor_assets import copy_assets,copy_guard_assets,copy_linked_manifest,ASSET_NAMES
from icstudio.model import clone,example,file_digest
from icstudio.catalog import create_device
from icstudio.physical_backend import stage
from scripts.qualify_standard_mos import load_technology

class GuardBackendAssetsTests(unittest.TestCase):
    def project(self):
        tech=load_technology('ihp-sg13g2')[0];p=example('empty');p['pdk']=clone(tech);d=create_device(tech,'sg13g2_pr/rsil.sym','R1');d['model_params'].update(w='2u',l='7u');d['physical_guard_routing']=guard.OPTION
        p['cells'][0]['devices']=[d];spec=ihp_resistors.specification(tech,d);p['cells'][0]['pdk_layouts']=[dict(device_id=d['id'],spec=spec,origin=[0,0])];return p,d,spec
    def test_additive_assets_and_staged_manifest(self):
        p,d,spec=self.project()
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);src=Path(guard.__file__).parent;dest=base/'backend';records=copy_assets(src,dest)
            self.assertEqual(set(records),ASSET_NAMES);self.assertEqual(file_digest(dest/'assets/qualification/ihp-guard-corner-safe/templates.json'),guard.TEMPLATE_HASH)
            actual=stage(dict(project=p,cell=p['top'],settings=dict(type='silicon')),base/'work','/native/work','/')
            tech=clone(actual['project']['pdk']);tech['package_root']=str(base/'work/pdk')
            with patch.object(guard,'__file__',str(dest/'ihp_guard_routing.py')),patch.object(ihp_resistors,'__file__',str(dest/'ihp_resistors.py')):
                self.assertEqual(ihp_resistors.specification(tech,d),spec)
                (dest/'assets/qualification/ihp-guard-corner-safe/templates.json').write_text('{}')
                with self.assertRaisesRegex(ValueError,'templates'):ihp_resistors.specification(tech,d)
    def test_missing_changed_and_linked_assets_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);src=base/'source';src.mkdir();dest=base/'backend'
            with self.assertRaisesRegex(ValueError,'Missing'):copy_guard_assets(src,dest)
            relative=Path('assets/qualification/ihp-guard-corner-safe');shutil.copytree(Path(guard.__file__).parent/relative,src/relative)
            path=src/relative/'templates.json';original=path.read_bytes();path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'Changed'):copy_guard_assets(src,dest)
            path.write_bytes(original);path.unlink()
            try:path.symlink_to(Path(guard.__file__).parent/relative/'templates.json')
            except OSError as exc:
                if os.name=='nt' and getattr(exc,'winerror',None) in (1,50,1314):self.skipTest('Ordinary-user symlink creation is unavailable on this Windows host.')
                raise
            with self.assertRaisesRegex(ValueError,'Linked'):copy_guard_assets(src,dest)
    def test_new_recipe_manifest_requires_original_registry(self):
        p,d,spec=self.project()
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);src=base/'registry';src.mkdir();source=Path(p['pdk']['package_root'])/'package.json';(src/'package.json').write_bytes(source.read_bytes())
            result=copy_linked_manifest(p,src,base/'pdk');self.assertEqual(result['sha256'],file_digest(source))
            (src/'package.json').unlink()
            with self.assertRaisesRegex(ValueError,'Missing'):copy_linked_manifest(p,src,base/'missing')

if __name__=='__main__':unittest.main()
