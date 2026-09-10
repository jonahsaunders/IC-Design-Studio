"""Inventory and exact-revision creation for fresh and existing installations."""
import json,tempfile,unittest,shutil
from pathlib import Path
from icstudio.model import clone,digest,save_project,load_project
from icstudio.pdks import PDKRegistry
from icstudio.project_hub import inventory,preview,build_project
from tests.test_pdk_templates import install_fixture


class ProjectHubTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.registry=PDKRegistry(self.root/'registry')

    def test_fresh_install_shows_bundled_packages_without_registering_them(self):
        rows,notes=inventory(self.registry);self.assertEqual(notes,[])
        self.assertEqual({r['id'] for r in rows if r['status']=='Available offline'},{'sky130A','gf180mcuD'})
        self.assertTrue(any(r['id']=='ihp-sg13g2' and r['status']=='Add installation' for r in rows))
        self.assertEqual(self.registry.entries(),[])

    def test_multiple_versions_and_unknown_future_processes_are_all_visible(self):
        path=install_fixture(self.root/'pdk','future-process');key=self.registry.install(path)
        manifest=json.loads(path.read_text());manifest['revision']='second';path.write_text(json.dumps(manifest));self.registry.install(path)
        rows,notes=inventory(self.registry,bundled=[]);self.assertEqual(notes,[])
        versions=[r for r in rows if r['id']=='future-process'];self.assertEqual({r['revision'] for r in versions},{'fixture','second'})
        row=next(r for r in versions if r['key']==key);result=build_project(self.registry,row,'Exact revision','inverter','1.2','nfet','pfet')
        self.assertEqual(result['project']['pdk']['package_lock']['revision'],'fixture')
        self.assertEqual(result['project']['analysis']['engine'],'ngspice')
        save_project(result['project'],self.root/'saved.icproj')
        self.assertEqual(load_project(self.root/'saved.icproj')['pdk']['package_lock']['revision'],'fixture')

    def test_install_selected_package_and_deduplicate_inventory(self):
        path=install_fixture(self.root/'pdk','local-package')
        included=[{'name':'local-package','path':str(path.parent)}]
        row=next(r for r in inventory(self.registry,included)[0] if r['id']=='local-package')
        before=digest(row);result=build_project(self.registry,row,'Created offline','empty')
        self.assertEqual(digest(row),before);self.assertEqual(result['project']['name'],'Created offline')
        rows=inventory(self.registry,included)[0];matching=[r for r in rows if r['id']=='local-package']
        self.assertEqual(len(matching),1);self.assertEqual(matching[0]['status'],'Installed')

    def test_missing_folder_and_damaged_metadata_stay_visible_without_breaking_inventory(self):
        path=install_fixture(self.root/'pdk','missing-package');key=self.registry.install(path)
        manifest_path=self.registry.root/key/'package.json';manifest=json.loads(manifest_path.read_text())
        manifest['source_root']=str(self.root/'gone');manifest_path.write_text(json.dumps(manifest))
        broken=self.registry.root/'bad@r1';broken.mkdir();(broken/'package.json').write_text('{')
        wrong=self.registry.root/'wrong@r1';wrong.mkdir();(wrong/'package.json').write_text('[]')
        rows,notes=inventory(self.registry,bundled=[])
        row=next(r for r in rows if r['key']==key);self.assertEqual(row['status'],'Folder missing')
        with self.assertRaisesRegex(ValueError,'locate'):preview(row)
        self.assertTrue(any(r['status']=='Needs repair' for r in rows));self.assertTrue(notes)

    def test_changed_files_or_changed_manifest_cannot_create_a_project(self):
        path=install_fixture(self.root/'pdk','locked');key=self.registry.install(path)
        row=next(r for r in inventory(self.registry,[])[0] if r['key']==key)
        model=self.registry.root/key/'models.spice';model.write_text('changed')
        with self.assertRaisesRegex(ValueError,'missing or changed'):build_project(self.registry,row,'Test','empty')
        shutil.copyfile(path.parent/'models.spice',model)
        installed=self.registry.root/key/'package.json';m=json.loads(installed.read_text());m['technology']['layers'][0]['gds']=99;installed.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'package changed'):build_project(self.registry,row,'Test','empty')

    def test_invalid_choices_do_not_install_and_generic_projects_need_no_pdk(self):
        path=install_fixture(self.root/'pdk','offline');included=[{'name':'offline','path':str(path.parent)}]
        rows,_=inventory(self.registry,included);row=next(r for r in rows if r['id']=='offline')
        for name,kind in (('','empty'),('Named','unavailable')):
            with self.assertRaises(ValueError):build_project(self.registry,row,name,kind)
        self.assertEqual(self.registry.entries(),[])
        generic=next(r for r in rows if r['key']=='generic');p=build_project(self.registry,generic,'Generic project','rc')['project']
        self.assertNotIn('package_lock',p['pdk']);self.assertEqual(p['analysis']['engine'],'builtin')

    def test_included_manifest_cannot_change_between_selection_and_install(self):
        path=install_fixture(self.root/'pdk','offline');row=next(r for r in inventory(self.registry,[{'path':str(path.parent)}])[0] if r['id']=='offline')
        m=json.loads(path.read_text());m['revision']='different';path.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'package changed'):build_project(self.registry,row,'Project','empty')
        self.assertEqual(self.registry.entries(),[])
