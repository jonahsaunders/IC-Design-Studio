"""Default installation, reproducibility and unchanged corner semantics."""
import json,re,tempfile,unittest
from pathlib import Path
from icstudio.model import clone,file_digest,save_project,load_project
from icstudio.pdks import PDKRegistry,model_lines
from icstudio.project_hub import inventory,build_project
from scripts.prepare_sky130_device_package import prepare
from scripts.sky130_qualification_source import original_package,BASE,BASE_MANIFEST,DEFAULT_MANIFEST

ROOT=Path(__file__).resolve().parents[1]


class DefaultDevicePackageTests(unittest.TestCase):
    def test_new_sky130_projects_use_tested_fixes_and_saved_projects_keep_their_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);registry=PDKRegistry(root/'registry')
            with original_package(ROOT/'icstudio/assets/pdks/sky130A') as old:
                original_key=registry.install(old/'package.json')
            old_row=next(r for r in inventory(registry)[0] if r['key']==original_key)
            original=build_project(registry,old_row,'Existing project','empty')['project']
            save_project(original,root/'old.icproj')
            rows,notes=inventory(registry);self.assertEqual(notes,[])
            new_row=next(r for r in rows if r['id']=='sky130A' and r['status']=='Available offline')
            self.assertEqual(new_row['revision'],'2a8a8a7048ac324d')
            new=build_project(registry,new_row,'New project','empty')['project']
            self.assertNotEqual(new['pdk']['revision'],original['pdk']['revision'])
            reopened=load_project(root/'old.icproj')
            self.assertEqual(reopened['pdk']['revision'],original['pdk']['revision'])
            self.assertEqual(reopened['pdk']['package_lock'],original['pdk']['package_lock'])
            self.assertEqual(registry.verify(original_key)['revision'],'b1f441fabee1ed85')
            self.assertTrue((Path(new['pdk']['package_root'])/'ICSTUDIO-DEVICE-PACKAGE.json').is_file())

    def test_rebuild_matches_the_bundled_package_and_original_assets_remain_recoverable(self):
        source=ROOT/'icstudio/assets/pdks/sky130A'
        self.assertEqual(file_digest(source/'package.json'),DEFAULT_MANIFEST)
        with original_package(source) as original,tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(file_digest(original/'package.json'),BASE_MANIFEST)
            out=Path(tmp)/'package';result=prepare(source,out)
            self.assertEqual(result['manifest_sha256'],DEFAULT_MANIFEST)
            self.assertEqual((out/'package.json').read_bytes(),(source/'package.json').read_bytes())
            package=json.loads((out/'package.json').read_bytes())
            for rel,h in package['files'].items():self.assertEqual(file_digest(out/rel),h,rel)
            with self.assertRaisesRegex(ValueError,'new'):prepare(source,out)
            (out/'libs.tech/ngspice/sky130.lib.spice').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Changed current'):
                with original_package(out):pass

    def test_only_three_reviewed_npn_sections_change_and_other_selections_are_preserved(self):
        source=ROOT/'icstudio/assets/pdks/sky130A';original=json.loads((BASE/'package.json').read_bytes());current=json.loads((source/'package.json').read_bytes())
        self.assertEqual(current['technology']['simulation'],original['technology']['simulation'])
        rel='libs.tech/ngspice/sky130.lib.spice';old=(BASE/rel).read_bytes();new=(source/rel).read_bytes()
        additions=[]
        for section,npn in [('tt','t'),('ss','s'),('ff','f')]:
            addition=('* IC Design Studio: load the public NPN '+npn+' corner parameters.\n.lib "icstudio-npn-corners.lib" '+npn+'\n').encode();additions.append(addition)
            self.assertIn(('.lib '+section+'\n').encode()+addition,new)
        for addition in additions:new=new.replace(addition,b'')
        self.assertEqual(new,old)
        tech=clone(current['technology']);tech.update(package_root=str(source),package_lock={k:current[k] for k in ('id','revision','files')})
        for corner,section in original['technology']['simulation']['includes'][0]['sections'].items():
            self.assertTrue(model_lines(tech,corner)[0].endswith(' '+section),corner)


if __name__=='__main__':unittest.main()
