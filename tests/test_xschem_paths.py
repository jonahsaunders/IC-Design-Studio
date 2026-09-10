import os,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.xschem_paths import library_folders,default_libraries,reference_folder,dependency_hint
from icstudio.xschem_project import review_schematic,apply_review,export_project
from tests.xschem_fixtures import amplifier


class XschemPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.path=amplifier(self.root/'input')
    def tearDown(self):self.tmp.cleanup()

    def test_install_folder_resolves_mixed_standard_references(self):
        install=self.root/'Program Files/xschem';lib=install/'share/xschem/xschem_library';lib.mkdir(parents=True)
        shutil.move(self.path.parent/'devices',lib/'devices')
        self.path.write_text(self.path.read_text().replace('devices/voltage.sym','voltage.sym'))
        r=review_schematic(self.path,[install]);self.assertEqual(r['errors'],[])
        found={d['reference']:d['path'] for d in r['dependencies']}
        self.assertEqual(found['voltage.sym'],str((lib/'devices/voltage.sym').resolve()))
        self.assertEqual(found['devices/code.sym'],str((lib/'devices/code.sym').resolve()))

    def test_explicit_library_order_wins_over_automatic_subfolders(self):
        first=self.root/'first';second=self.root/'second';(first/'devices').mkdir(parents=True);second.mkdir()
        folders=library_folders([first,second])
        self.assertLess(folders.index(str(second.resolve())),folders.index(str((first/'devices').resolve())))
        self.assertEqual(library_folders([first,first]),library_folders([first]))

    def test_windows_discovery_and_shared_directory(self):
        programs=self.root/'Program Files';devices=programs/'xschem/share/xschem/xschem_library/devices';devices.mkdir(parents=True)
        with patch.dict(os.environ,{'ProgramFiles':str(programs)},clear=True),patch('icstudio.xschem_paths.sys.platform','win32'),patch('icstudio.xschem_paths.shutil.which',return_value=None):
            self.assertIn(str(devices.resolve()),default_libraries())
        with patch.dict(os.environ,{'XSCHEM_SHAREDIR':str(devices.parents[1])},clear=True),patch('icstudio.xschem_paths.shutil.which',return_value=None):
            self.assertIn(str(devices.resolve()),default_libraries())

    def test_located_absolute_model_exports_portably_and_is_fingerprinted(self):
        original='/foss/pdks/example/models/nmos.spice'
        self.path.write_text(self.path.read_text().replace('models/nmos.spice',original))
        model=self.path.parent/'models/nmos.spice'
        r=review_schematic(self.path,file_locations={original:model});self.assertEqual(r['errors'],[])
        self.assertTrue(any(d['status']=='Located' and d['reference']==original for d in r['dependencies']))
        p=apply_review(r);out=self.root/'out';e=export_project(p,out)
        self.assertNotIn(original,(out/e['top']).read_text());self.assertEqual(review_schematic(out/e['top'])['errors'],[])
        model.write_text(model.read_text()+'\n* modified')
        with self.assertRaisesRegex(ValueError,'changed after review'):apply_review(r)

    def test_missing_explicit_location_does_not_fall_back(self):
        r=review_schematic(self.path,file_locations={'devices/voltage.sym':self.root/'gone.sym'})
        self.assertIsNone(r['candidate'])
        self.assertTrue(any(d['reference']=='devices/voltage.sym' and d['status']=='Missing' for d in r['dependencies']))

    def test_model_dependencies_visible_before_code_symbol_resolves(self):
        code=self.path.parent/'devices/code.sym';code.unlink()
        self.path.write_text(self.path.read_text().replace('.ac dec 20 10 10meg','.lib /foss/pdks/example/model.ngspice typical\n.control\nforeach v 1 2\nshell touch NEVER\nend\n.endc'))
        r=review_schematic(self.path)
        self.assertIsNone(r['candidate'])
        self.assertTrue(any(d['reference']=='/foss/pdks/example/model.ngspice' and d['status']=='Missing' for d in r['dependencies']))
        self.assertTrue(any('native setup conversion is not supported' in w for w in r['warnings']))
        self.assertFalse((self.path.parent/'NEVER').exists())

    def test_selected_symbol_infers_library_root_and_hints(self):
        selected=self.root/'pdk/symbols/nfet.sym'
        self.assertEqual(reference_folder('symbols/nfet.sym',selected),str((self.root/'pdk').resolve()))
        self.assertEqual(reference_folder('/foss/models/a.spice',selected),str(selected.parent.resolve()))
        self.assertIn('Locate selected file',dependency_hint('/foss/models/a.spice'))
        self.assertIn('containing symbols/',dependency_hint('symbols/nfet.sym'))

    def test_selecting_devices_folder_also_resolves_qualified_references(self):
        lib=self.root/'external';lib.mkdir();shutil.move(self.path.parent/'devices',lib/'devices')
        r=review_schematic(self.path,[lib/'devices']);self.assertEqual(r['errors'],[])

    def test_dynamic_symbol_is_visible_and_can_be_linked_for_native_migration(self):
        from icstudio.native_migration import review_path
        reference='$CUSTOM_LIBRARY/voltage.sym'
        self.path.write_text(self.path.read_text().replace('devices/voltage.sym',reference))
        record=review_path(self.path)
        self.assertIsNone(record['candidate'])
        self.assertTrue(any(d['reference']==reference and d['status']=='Missing' for d in record['dependencies']))
        location=str(self.path.resolve())+'::'+reference
        record=review_path(self.path,file_locations={location:self.path.parent/'devices/voltage.sym'})
        self.assertIsNotNone(record['candidate'],record['items'])

    def test_same_symbol_name_can_be_linked_separately_in_each_schematic(self):
        from icstudio.xschem_project import Reader
        one=self.root/'one';two=self.root/'two';one.mkdir();two.mkdir()
        first=one/'part.sym';second=two/'part.sym';first.write_text('first');second.write_text('second')
        parent1=one/'top.sch';parent2=two/'child.sch'
        reader=Reader(self.path,[one,two],None,{str(parent1.resolve())+'::part.sym':second})
        self.assertEqual(reader.resolve('part.sym',parent1,'Symbol'),second.resolve())
        self.assertEqual(reader.resolve('part.sym',parent2,'Symbol'),second.resolve())
        third=self.root/'replacement.sym';third.write_text('replacement')
        reader=Reader(self.path,[one,two],None,{str(parent2.resolve())+'::part.sym':third})
        self.assertEqual(reader.resolve('part.sym',parent1,'Symbol'),first.resolve())
        self.assertEqual(reader.resolve('part.sym',parent2,'Symbol'),third.resolve())
