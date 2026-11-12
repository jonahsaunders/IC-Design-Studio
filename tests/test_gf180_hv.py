import json,tempfile,unittest
from pathlib import Path
from icstudio.model import clone,file_digest
from icstudio.catalog import create_device,parameter_values
from icstudio.pdk_import import scan_local
from icstudio.pdks import PDKRegistry,model_lines
from icstudio.gf180_hv import MODEL_PATH,MODEL_SHA256,MODELS,CORNERS,constrain
from scripts.gf180_hv_source import BASE,PROMOTED,previous_hv
from scripts.prepare_gf180_hv import prepare,SOURCE
ROOT=Path(__file__).resolve().parents[1]


class GF180HighVoltageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);cls.packages={}
        for target in BASE:
            dest=cls.root/target;prepare(ROOT/'icstudio/assets/pdks'/target,dest)
            cls.packages[target]=json.loads((dest/'package.json').read_bytes())
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def technology(self,target='gf180mcuD'):
        package=self.packages[target];tech=clone(package['technology'])
        tech.update(package_root=str(self.root/target),package_lock={k:package[k] for k in ('id','revision','files')});return tech

    def test_exact_original_source_and_reproducible_packages(self):
        self.assertEqual(file_digest(SOURCE),MODEL_SHA256)
        for target in BASE:
            with self.subTest(target=target),previous_hv(ROOT/'icstudio/assets/pdks'/target) as old:
                original=json.loads((old/'package.json').read_bytes());current=self.packages[target]
                self.assertEqual(file_digest(self.root/target/'package.json'),PROMOTED[target])
                for rel,h in original['files'].items():self.assertEqual(file_digest(self.root/target/rel),h)
                a=clone(original['technology']);b=clone(current['technology']);a.pop('revision');b.pop('revision')
                self.assertEqual(b['simulation']['includes'].pop(),dict(path=MODEL_PATH,sections=CORNERS))
                for model in MODELS:
                    self.assertTrue(a['simulation']['catalog'].pop('symbols/'+model+'.sym')['unavailable'])
                    self.assertFalse(b['simulation']['catalog'].pop('symbols/'+model+'.sym')['unavailable'])
                self.assertEqual(a,b)

    def test_geometry_multiplicity_and_single_finger_contract(self):
        tech=self.technology()
        for model in MODELS:
            key='symbols/'+model+'.sym';entry=tech['simulation']['catalog'][key]
            self.assertEqual(entry['pin_order'],['d','g','s','b']);self.assertEqual(entry['model'],model)
            for w,l in (('4u','.6u'),('50u','20u'),('25u','.6u')):
                d=create_device(tech,key,'DUT');d['params'].update(w=w,l=l);d['model_params']['m']=100
                v=parameter_values(entry,d);self.assertEqual(v['nf'],1);self.assertEqual(v['m'],100)
                self.assertGreater(v['ad'],v['as']);self.assertGreater(v['pd'],v['ps'])
            for parameter,value in (('w','3.999u'),('w','50.001u'),('l','.599u'),('l','20.001u'),('nf',2),('m',0),('m',101)):
                with self.subTest(model=model,parameter=parameter,value=value),self.assertRaises(ValueError):
                    d=create_device(tech,key,'BAD');d['params' if parameter in ('w','l') else 'model_params'][parameter]=value;parameter_values(entry,d)

    def test_all_supported_corners_load_both_libraries_without_internal_sections(self):
        tech=self.technology()
        for corner,section in CORNERS.items():
            lines=model_lines(tech,corner)
            hv=[s for s in lines if 'smbb000149.spice' in s]
            self.assertEqual(len(hv),1);self.assertTrue(hv[0].endswith(' '+section))
            self.assertTrue(any('design.ngspice' in s for s in lines));self.assertTrue(any('sm141064.ngspice' in s for s in lines))
        scanned=scan_local(self.root/'gf180mcuD')
        hv=next(i for i in scanned['technology']['simulation']['includes'] if i['path']==MODEL_PATH)
        self.assertEqual(hv['sections'],CORNERS)

    def test_missing_corner_and_changed_model_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bad=root/'model';bad.write_bytes(SOURCE.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'Changed public'):prepare(ROOT/'icstudio/assets/pdks/gf180mcuD',root/'no-output',bad)
            self.assertFalse((root/'no-output').exists())
            dest=root/'package';prepare(ROOT/'icstudio/assets/pdks/gf180mcuD',dest)
            p=dest/MODEL_PATH;p.write_bytes(p.read_bytes().replace(b'.lib ff\n',b'.lib missing_ff\n'))
            with self.assertRaisesRegex(ValueError,'Missing GF180 high-voltage corner'):scan_local(dest)
            with self.assertRaisesRegex(ValueError,'Changed current GF180'):
                prepare(dest,root/'invalid-rebuild')

    def test_saved_old_package_and_new_package_coexist(self):
        for target in BASE:
            with tempfile.TemporaryDirectory() as tmp,previous_hv(ROOT/'icstudio/assets/pdks'/target) as old:
                reg=PDKRegistry(Path(tmp));old_key=reg.install(old/'package.json');new_key=reg.install(self.root/target/'package.json')
                self.assertNotEqual(old_key,new_key)
                old_tech=reg.technology(old_key);new_tech=reg.technology(new_key)
                self.assertEqual(reg.verify(old_key)['revision'],json.loads((old/'package.json').read_bytes())['revision'])
                with self.assertRaises(ValueError):create_device(old_tech,'symbols/nfet_10v0_asym.sym','OLD')
                self.assertEqual(create_device(new_tech,'symbols/nfet_10v0_asym.sym','NEW')['model_ref']['revision'],new_tech['revision'])


if __name__=='__main__':unittest.main()
