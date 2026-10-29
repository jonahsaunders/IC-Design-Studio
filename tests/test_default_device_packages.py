"""Default installation, reproducibility and unchanged corner semantics."""
import json,re,tempfile,unittest
from pathlib import Path
from icstudio.model import clone,file_digest,save_project,load_project
from icstudio.pdks import PDKRegistry,model_lines
from icstudio.project_hub import inventory,build_project
from scripts.prepare_default_device_packages import prepare
from scripts.device_qualification_source import PROMOTED,HISTORICAL_PROMOTED,PREVIOUS,REVISIONS,previous_devices
from scripts.sky130_qualification_source import original_package,BASE,BASE_MANIFEST,DEFAULT_MANIFEST

ROOT=Path(__file__).resolve().parents[1]


class DefaultDevicePackageTests(unittest.TestCase):
    def test_wrong_target_or_unknown_manifest_cannot_publish_a_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'result';unknown=root/'unknown';unknown.mkdir()
            (unknown/'package.json').write_bytes(b'{}')
            for source,target in [(unknown,'sky130A'),(ROOT/'icstudio/assets/pdks/gf180mcuD','gf180mcuC')]:
                with self.subTest(target=target),self.assertRaisesRegex(ValueError,'exact reviewed package'):
                    prepare(source,out,target)
                self.assertFalse(out.exists())

    def test_all_defaults_rebuild_exactly_and_do_not_rebind_saved_projects(self):
        for target in PROMOTED:
            with self.subTest(target=target),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);source=ROOT/'icstudio/assets/pdks'/target
                registry=PDKRegistry(root/'registry')
                with previous_devices(source) as previous:
                    self.assertEqual(file_digest(previous/'package.json'),PREVIOUS[target])
                    old_key=registry.install(previous/'package.json')
                    old_manifest=json.loads((previous/'package.json').read_bytes())
                rows,notes=inventory(registry);self.assertEqual(notes,[])
                old_row=next(r for r in rows if r['key']==old_key)
                old=build_project(registry,old_row,'Saved '+target,'empty')['project']
                save_project(old,root/'saved.icproj')
                row=next(r for r in rows if r['id']==target and r['status']=='Available offline')
                new=build_project(registry,row,'Fresh '+target,'empty')['project']
                installed=Path(new['pdk']['package_root'])
                self.assertEqual(new['pdk']['revision'],REVISIONS[target])
                self.assertEqual(json.loads((installed/'package.json').read_bytes()),json.loads((source/'package.json').read_bytes()))
                result=prepare(source,root/'rebuilt',target)
                self.assertEqual(result['manifest_sha256'],PROMOTED[target])
                self.assertEqual((root/'rebuilt/package.json').read_bytes(),(source/'package.json').read_bytes())
                package=json.loads((source/'package.json').read_bytes())
                for rel,h in package['files'].items():
                    self.assertEqual(file_digest(installed/rel),h)
                    self.assertEqual(file_digest(root/'rebuilt'/rel),h)
                for rel,h in old_manifest['files'].items():self.assertEqual(file_digest(installed/rel),h)
                reopened=load_project(root/'saved.icproj')
                self.assertEqual(reopened['pdk']['package_lock'],old['pdk']['package_lock'])
                self.assertEqual(registry.verify(old_key)['revision'],old_manifest['revision'])

    def test_default_catalogs_expose_the_reviewed_semantic_bindings(self):
        catalogs={t:json.loads((ROOT/'icstudio/assets/pdks'/t/'package.json').read_bytes())['technology']['simulation']['catalog'] for t in PROMOTED}
        sky=catalogs['sky130A']
        for kind in ('hvt','lvt'):
            e=sky['sky130_fd_pr/cap_var_'+kind+'.sym']
            self.assertEqual(e['model'],'icstudio_cap_var_'+kind+'_parallel')
            self.assertEqual(e['emit_parameters']['copies'],'vm')
        self.assertEqual(sky['sky130_fd_pr/vpp_cap.sym']['pin_order'],['c0','c1','sub','top'])
        self.assertNotIn('w',sky['sky130_fd_pr/vpp_cap.sym']['parameters'])
        for target in ('gf180mcuC','gf180mcuD'):
            self.assertEqual(catalogs[target]['symbols/nfet_06v0_nvt.sym']['model'],'nfet_06v0_nvt')
        ihp=catalogs['ihp-sg13g2']
        for name in ('nmoscl_2','nmoscl_4'):
            self.assertEqual(ihp['sg13g2_pr/'+name+'.sym']['pin_order'],['vdd','vss'])
        self.assertEqual(ihp['sg13g2_pr/sg13_svaricap.sym']['pin_order'],['g1','nw','g2','body'])
        self.assertFalse(ihp['sg13g2_pr/isolbox.sym']['unavailable'])
        self.assertEqual(ihp['sg13g2_pr/isolbox.sym']['parameters']['w']['exclusive_minimum'],'2.1u')

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
            self.assertEqual(new_row['revision'],REVISIONS['sky130A'])
            new=build_project(registry,new_row,'New project','empty')['project']
            self.assertNotEqual(new['pdk']['revision'],original['pdk']['revision'])
            reopened=load_project(root/'old.icproj')
            self.assertEqual(reopened['pdk']['revision'],original['pdk']['revision'])
            self.assertEqual(reopened['pdk']['package_lock'],original['pdk']['package_lock'])
            self.assertEqual(registry.verify(original_key)['revision'],'b1f441fabee1ed85')
            self.assertTrue((Path(new['pdk']['package_root'])/'ICSTUDIO-DEVICE-PACKAGE.json').is_file())

    def test_rebuild_matches_the_bundled_package_and_original_assets_remain_recoverable(self):
        source=ROOT/'icstudio/assets/pdks/sky130A'
        self.assertEqual(file_digest(source/'package.json'),PROMOTED['sky130A'])
        with original_package(source) as original,tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(file_digest(original/'package.json'),BASE_MANIFEST)
            out=Path(tmp)/'package';result=prepare(source,out,'sky130A')
            self.assertEqual(result['manifest_sha256'],PROMOTED['sky130A'])
            self.assertEqual((out/'package.json').read_bytes(),(source/'package.json').read_bytes())
            package=json.loads((out/'package.json').read_bytes())
            for rel,h in package['files'].items():self.assertEqual(file_digest(out/rel),h,rel)
            with self.assertRaisesRegex(ValueError,'new'):prepare(source,out,'sky130A')
            (out/'libs.tech/ngspice/sky130.lib.spice').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Changed current'):
                with original_package(out):pass

    def test_only_three_reviewed_npn_sections_change_and_other_selections_are_preserved(self):
        source=self.enterContext(previous_devices(ROOT/'icstudio/assets/pdks/sky130A'));original=json.loads((BASE/'package.json').read_bytes());current=json.loads((source/'package.json').read_bytes())
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


    def test_exact_rf_predecessor_still_reconstructs_and_rebuilds_the_current_default(self):
        from scripts.prepare_sky130_esd_nvt import predecessor
        current=ROOT/'icstudio/assets/pdks/sky130A'
        with predecessor(current) as rf,tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(file_digest(rf/'package.json'),HISTORICAL_PROMOTED['sky130A'])
            with previous_devices(rf) as older:self.assertEqual(file_digest(older/'package.json'),PREVIOUS['sky130A'])
            out=Path(tmp)/'current';record=prepare(rf,out,'sky130A')
            self.assertEqual(record['manifest_sha256'],PROMOTED['sky130A'])
            self.assertEqual((out/'package.json').read_bytes(),(current/'package.json').read_bytes())

    def test_changed_current_asset_cannot_be_hidden_by_predecessor_reconstruction(self):
        import shutil
        source=ROOT/'icstudio/assets/pdks/sky130A'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);copy=root/'copy';shutil.copytree(source,copy)
            rel='libs.tech/ngspice/sky130.lib.spice';(copy/rel).write_bytes((copy/rel).read_bytes()+b'\n* changed\n')
            with self.assertRaisesRegex(ValueError,'Changed current device asset'):
                with previous_devices(copy):pass
            with self.assertRaisesRegex(ValueError,'Changed current device asset'):prepare(copy,root/'rebuilt','sky130A')
            self.assertFalse((root/'rebuilt').exists())

if __name__=='__main__':unittest.main()

