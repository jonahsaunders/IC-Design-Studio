"""Managed transfers preserve recipe resources and registry manifest identity."""
import json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import clone,example,file_digest
from icstudio.catalog import create_device
from icstudio import ihp_resistors
from icstudio.ihp_resistor_assets import copy_assets,copy_linked_manifest,ASSET_PATH,ASSET_NAMES
from icstudio.physical_backend import stage
from scripts.qualify_standard_mos import load_technology

class IhpResistorBackendAssetsTests(unittest.TestCase):
    def test_actual_template_transfer_and_staged_recipe_identity(self):
        tech=load_technology('ihp-sg13g2')[0];p=example('empty');p['pdk']=clone(tech)
        d=create_device(tech,'sg13g2_pr/rsil.sym','R1');spec=ihp_resistors.specification(tech,d)
        p['cells'][0]['devices']=[d];p['cells'][0]['pdk_layouts']=[dict(device_id=d['id'],spec=spec,origin=[0,0])]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=Path(ihp_resistors.__file__).parent;backend=root/'backend'
            records=copy_assets(source,backend);self.assertEqual(set(records),ASSET_NAMES)
            self.assertEqual(records['templates.json'],ihp_resistors.TEMPLATE_HASH)
            actual=stage(dict(project=p,cell=p['top'],settings=dict(type='silicon')),root/'work','/native/work','/')
            transferred=clone(actual['project']['pdk']);transferred['package_root']=str(root/'work/pdk')
            self.assertEqual(file_digest(root/'work/pdk/package.json'),file_digest(Path(tech['package_root'])/'package.json'))
            with patch.object(ihp_resistors,'__file__',str(backend/'ihp_resistors.py')):
                self.assertEqual(ihp_resistors.specification(transferred,d),spec)
                (backend/ASSET_PATH/'templates.json').write_text('{}')
                with self.assertRaisesRegex(ValueError,'templates'):ihp_resistors.specification(transferred,d)

    def test_manifest_reformat_is_preserved_but_semantic_mutation_rejected(self):
        tech=load_technology('ihp-sg13g2')[0];p=example('empty');p['pdk']=clone(tech)
        d=create_device(tech,'sg13g2_pr/rsil.sym','R1');spec=ihp_resistors.specification(tech,d)
        p['cells'][0]['pdk_layouts']=[dict(spec=spec)]
        original=json.loads((Path(tech['package_root'])/'package.json').read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'registry';source.mkdir();path=source/'package.json'
            path.write_text(json.dumps(original,indent=4))
            result=copy_linked_manifest(p,source,root/'native')
            self.assertEqual(result['sha256'],file_digest(path));self.assertEqual(result['semantic_sha256'],ihp_resistors.MANIFEST_SEMANTIC_HASH)
            changed=clone(original);changed['revision']='other';path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,'reviewed lock'):copy_linked_manifest(p,source,root/'wrong')
            path.unlink()
            with self.assertRaisesRegex(ValueError,'Missing'):copy_linked_manifest(p,source,root/'missing')

    def test_missing_or_changed_templates_block_staging_before_native_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();(source/'ihp_resistors.py').write_text('# recipe marker')
            with self.assertRaisesRegex(ValueError,'Missing'):copy_assets(source,root/'missing')
            shutil.copytree(Path(ihp_resistors.__file__).parent/ASSET_PATH,source/ASSET_PATH)
            (source/ASSET_PATH/'templates.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Changed'):copy_assets(source,root/'changed')
            (source/ASSET_PATH/'unexpected.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'inventory'):copy_assets(source,root/'extra')

if __name__=='__main__':unittest.main()
