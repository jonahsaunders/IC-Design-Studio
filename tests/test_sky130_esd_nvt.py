"""Corrected public ESD binding: reproducibility, finite bins and saved identity."""
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest
import icstudio
from icstudio.catalog import create_device, parameter_values
from icstudio.catalog_migration import instance_name
from icstudio.interchange import export_xschem, spice
from icstudio.model import clone, example, file_digest, load_project, save_project
from icstudio.pdks import PDKRegistry
from icstudio.project_hub import build_project, inventory
from icstudio.xschem_io import import_package
from scripts.prepare_sky130_esd_nvt import prepare, BASE, KEY, MODEL, PREFIX, SOURCES

ROOT = Path(icstudio.__file__).resolve().parents[1]
EXPECTED = '5315d2d6ad7618047eeeb48a15f81f221e6f42864647208acfb65124ee5c9c7a'


class CorrectedESDTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='esd-binding-')
        cls.folder = Path(cls.tmp.name)
        cls.source = ROOT / 'icstudio/assets/pdks/sky130A'
        cls.package = cls.folder / 'candidate'
        cls.result = prepare(cls.source, cls.package)
        cls.old = json.loads((cls.source/'package.json').read_bytes())
        cls.new = json.loads((cls.package/'package.json').read_bytes())
        cls.tech = clone(cls.new['technology'])
        cls.tech.update(package_root=str(cls.package), package_lock={k:cls.new[k] for k in ('id','revision','files')})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_exact_candidate_preserves_original_assets_and_other_bindings(self):
        self.assertEqual(self.result['manifest_sha256'], EXPECTED)
        self.assertEqual(file_digest(self.source/'package.json'), BASE)
        for name, expected in self.old['files'].items():
            self.assertEqual(file_digest(self.package/name), expected, name)
        old, new = clone(self.old['technology']), clone(self.new['technology'])
        self.assertEqual({k for k,v in old['simulation']['catalog'].items() if new['simulation']['catalog'][k]!=v}, {KEY})
        new['simulation']['catalog'][KEY] = old['simulation']['catalog'][KEY]
        self.assertEqual(new['simulation']['includes'].pop(), {'path':PREFIX+MODEL+'.pm3.spice'})
        old.pop('revision');new.pop('revision');self.assertEqual(old,new)
        for name, source in ((MODEL+'.pm3.spice','esd_nfet_05v0_nvt.pm3.spice'),('nfet_g5v0d10v5_nvt_esd.sym','corrected.sym'),('LICENSE.xschem','LICENSE.xschem'),('LICENSE.skywater','LICENSE.skywater')):
            self.assertEqual((self.package/(PREFIX+name)).read_bytes(), (SOURCES/source).read_bytes())

    def test_fresh_defaults_and_all_supported_bin_centers(self):
        binding = self.tech['simulation']['catalog'][KEY]
        for length in (.9,2.,4.):
            for mult in (1,3):
                d=create_device(self.tech,KEY,'M1')
                self.assertEqual(d['params']['w'],'10u');self.assertEqual(d['params']['l'],'2u')
                d['params']['l']=f'{length}u';d['model_params']['mult']=mult
                values=parameter_values(binding,d)
                self.assertEqual((values['w'],values['l'],values['nf'],values['mult']),(10,length,1,mult))
                self.assertEqual(values['ad'],2.9);self.assertEqual(values['pd'],20.58)
        for dimension,value in (('w','10.1u'),('w','0'),('l','.900000001u'),('l','1u'),('l','nan')):
            d=create_device(self.tech,KEY,'M1');d['params'][dimension]=value
            with self.subTest(dimension=dimension,value=value), self.assertRaises(ValueError):parameter_values(binding,d)
        for key,value in (('nf',2),('mult',0),('mult',-1)):
            d=create_device(self.tech,KEY,'M1');d['model_params'][key]=value
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):parameter_values(binding,d)

    def test_saved_and_xschem_roundtrip_keep_model_sizes_and_ordered_four_nets(self):
        p=example('empty');p['pdk']=clone(self.tech);p['cells'][0]['devices']=[]
        for i,length in enumerate((.9,2.,4.)):
            for j,mult in enumerate((1,3)):
                d=create_device(self.tech,KEY,f'M{i}{j}',x=i*300,y=j*300)
                d['params']['l']=f'{length}u';d['model_params']['mult']=mult
                d['nets']={pin:f'{pin}{i}{j}' for pin in 'dgsb'};p['cells'][0]['devices'].append(d)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);save_project(p,folder/'input.icproj');saved=load_project(folder/'input.icproj')
            self.assertEqual(saved['pdk'],p['pdk']);self.assertEqual(saved['cells'],p['cells'])
            export_xschem(saved,folder/'exchange');q,_=import_package(folder/'exchange')
            binding=self.tech['simulation']['catalog'][KEY]
            for d in p['cells'][0]['devices']:
                after=next(row for row in q['cells'][0]['devices'] if row['name']==instance_name(d,binding))
                self.assertEqual(after['nets'],d['nets']);self.assertEqual(after['model_ref'],d['model_ref'])
                actual,expected=parameter_values(binding,after),parameter_values(binding,d)
                self.assertEqual(set(actual),set(expected))
                self.assertEqual(actual['l'],expected['l'])
                for key,value in expected.items():
                    self.assertTrue(math.isclose(actual[key],value,rel_tol=1e-14,abs_tol=0),key)
            self.assertEqual(spice(saved).count(MODEL+' '),6)

    def test_existing_project_is_still_unavailable_without_explicit_import(self):
        p=example('empty');p['pdk']=clone(self.old['technology'])
        p['pdk'].update(package_root=str(self.source),package_lock={k:self.old[k] for k in ('id','revision','files')})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.icproj';save_project(p,path)
            self.assertEqual(load_project(path)['pdk'],p['pdk'])
            with self.assertRaises(ValueError):create_device(p['pdk'],KEY,'M1')
        proof=json.loads((self.package/'ICSTUDIO-ESD-NVT-CANDIDATE.json').read_bytes())
        for field in ('default_promoted','qualified','chunk_complete'):self.assertIs(proof[field],False)

    def test_explicit_import_and_project_selection_use_the_corrected_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry=PDKRegistry(Path(tmp)/'registry')
            key=registry.install(self.package/'package.json')
            rows,notes=inventory(registry)
            self.assertFalse(notes)
            selected=next(row for row in rows if row['key']==key)
            p=build_project(registry,selected,'Corrected ESD','empty')['project']
            self.assertEqual(p['pdk']['revision'],self.new['revision'])
            d=create_device(p['pdk'],KEY,'M1')
            self.assertEqual(d['model_ref']['revision'],self.new['revision'])
            self.assertEqual(p['pdk']['simulation']['catalog'][KEY]['model'],MODEL)
            registry.verify(key)

    def test_rejects_modified_public_source_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);shutil.copytree(SOURCES,folder/'sources')
            path=folder/'sources/corrected.sym';path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'Changed public ESD source'):prepare(self.source,folder/'out',folder/'sources')
            self.assertFalse((folder/'out').exists())

    def test_rejects_unknown_or_changed_package_and_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);unknown=folder/'unknown';unknown.mkdir();(unknown/'package.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'exact reviewed'):prepare(unknown,folder/'out')
            self.assertFalse((folder/'out').exists())
            shutil.copytree(self.source,folder/'changed')
            asset=folder/'changed'/next(iter(self.old['files']));asset.write_bytes(asset.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'Changed or unsafe'):prepare(folder/'changed',folder/'out')
            self.assertFalse((folder/'out').exists())
            before=(self.package/'package.json').read_bytes()
            with self.assertRaisesRegex(ValueError,'new output'):prepare(self.source,self.package)
            self.assertEqual((self.package/'package.json').read_bytes(),before)
            with self.assertRaisesRegex(ValueError,'separate'):prepare(self.source,self.source/'child')


if __name__=='__main__':unittest.main()
