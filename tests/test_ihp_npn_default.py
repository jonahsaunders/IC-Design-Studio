"""Default NPN rule selection, immutable prior packages and exact rebuilding."""
import json,tempfile,unittest
from pathlib import Path
from icstudio.model import file_digest,save_project,load_project
from icstudio.pdks import PDKRegistry
from icstudio.project_hub import inventory,build_project
from icstudio.interoperability import tool_asset
from icstudio.ihp_npn_rules import corrected,RELATIVE_PATH
from scripts.ihp_npn_source import previous_npn,BASE,PROMOTED,REVISION
from scripts.prepare_ihp_npn_default import prepare,TECH,ENTRY,RULE,ORIGINAL,REPLACEMENT
from scripts.qualify_ihp_npn_layouts import load_package
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'icstudio/assets/pdks/ihp-sg13g2'


class IHPNpnDefaultTests(unittest.TestCase):
    def test_selected_entry_changes_only_reviewed_traversal_and_retains_original_assets(self):
        tech,identity=load_package(SOURCE)
        self.assertEqual(identity['manifest_sha256'],PROMOTED)
        self.assertEqual(tool_asset(tech,'magic','technology'),SOURCE/ENTRY)
        self.assertEqual((SOURCE/ENTRY).read_bytes().replace(REPLACEMENT,ORIGINAL),(SOURCE/TECH).read_bytes())
        self.assertEqual((SOURCE/RULE).read_bytes(),corrected((SOURCE/RELATIVE_PATH).read_bytes()))
        with previous_npn(SOURCE) as old:
            self.assertEqual(file_digest(old/'package.json'),BASE)
            old_package=json.loads((old/'package.json').read_bytes())
            self.assertEqual(tech['simulation'],old_package['technology']['simulation'])
            for name,h in old_package['files'].items():self.assertEqual(file_digest(SOURCE/name),h,name)

    def test_rebuild_is_exact_and_previous_qualification_recipe_remains_exact(self):
        from scripts.prepare_ihp_npn_qualification import prepare as historical
        with tempfile.TemporaryDirectory() as tmp,previous_npn(SOURCE) as old:
            root=Path(tmp);r=prepare(SOURCE,root/'rebuilt')
            self.assertEqual(r['manifest_sha256'],PROMOTED)
            self.assertEqual((root/'rebuilt/package.json').read_bytes(),(SOURCE/'package.json').read_bytes())
            historical(old,root/'old');historical(SOURCE,root/'new')
            self.assertEqual((root/'old/package.json').read_bytes(),(root/'new/package.json').read_bytes())
            for path in (root/'old').rglob('*'):
                if path.is_file():self.assertEqual(path.read_bytes(),(root/'new'/path.relative_to(root/'old')).read_bytes())

    def test_saved_tap_revision_is_preserved_while_fresh_projects_select_new_rules(self):
        with tempfile.TemporaryDirectory() as tmp,previous_npn(SOURCE) as old:
            root=Path(tmp);registry=PDKRegistry(root/'registry');key=registry.install(old/'package.json')
            old_row=next(r for r in inventory(registry)[0] if r['key']==key)
            p=build_project(registry,old_row,'Saved IHP tap project','empty')['project'];save_project(p,root/'saved.icproj')
            new_row=next(r for r in inventory(registry)[0] if r['id']=='ihp-sg13g2' and r['status']=='Available offline')
            fresh=build_project(registry,new_row,'Fresh IHP project','empty')['project']
            self.assertEqual(fresh['pdk']['revision'],REVISION)
            self.assertEqual(tool_asset(fresh['pdk'],'magic','technology').name,Path(ENTRY).name)
            reopened=load_project(root/'saved.icproj');self.assertEqual(reopened['pdk']['package_lock'],p['pdk']['package_lock'])
            self.assertEqual(registry.verify(key)['revision'],'c0a32344f73be40d')
            self.assertEqual(tool_asset(reopened['pdk'],'magic','technology',TECH).name,Path(TECH).name)

    def test_changed_derived_asset_is_rejected_before_rebuilding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prepare(SOURCE,root/'copy');(root/'copy'/RULE).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Changed current IHP NPN'):prepare(root/'copy',root/'out')
            self.assertFalse((root/'out').exists())
            with self.assertRaisesRegex(ValueError,'Changed IHP NPN qualification asset'):load_package(root/'copy')

    def test_wrong_manifest_and_existing_output_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'package.json').write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'exact reviewed'):prepare(root,root/'out')
            self.assertFalse((root/'out').exists())
            with self.assertRaisesRegex(ValueError,'new IHP'):prepare(SOURCE,root)
            prepare(SOURCE,root/'copy');path=root/'copy/package.json';p=json.loads(path.read_bytes());p['technology']['revision']='changed'
            path.write_text(json.dumps(p),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'intact, versioned'):load_package(root/'copy')


if __name__=='__main__':unittest.main()
