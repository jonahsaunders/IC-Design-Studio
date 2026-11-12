"""New-instance corrections must not rewrite existing choices or PDK metadata."""
import json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.catalog import create_device,parameter_values
from icstudio.model import clone,digest,example,save_project,load_project,scalar
from icstudio.sky130_defaults import CONTRACTS,initial_dimensions
from tests.test_sky130_devices import technology
from scripts.qualify_sky130_mos_defaults import DEFAULTS,fixture,rows

class Sky130DefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.tech=technology()

    def test_seven_short_symbols_match_the_same_models_ordinary_public_defaults(self):
        before=digest(self.tech)
        expected={'nfet3_03v3_nvt':(1,.5),'nfet3_05v0_nvt':(1,.9),'nfet3_g5v0d10v5':(1,.5),
            'nfet3_g5v0d16v0':(5,.7),'pfet3_01v8_lvt':(1,.35),'pfet3_g5v0d10v5':(1,.5),'pfet3_g5v0d16v0':(5,.66)}
        self.assertEqual(set(CONTRACTS),{'sky130_fd_pr/'+n+'.sym' for n in expected})
        catalog=self.tech['simulation']['catalog']
        for name,wl in expected.items():
            key='sky130_fd_pr/'+name+'.sym';d=create_device(self.tech,key,'M1');values=parameter_values(catalog[key],d)
            other=catalog[key.replace('fet3_','fet_')];self.assertEqual(catalog[key]['model'],other['model'])
            self.assertEqual(set(d['nets']),{'d','g','s','b'})
            for k,value in zip(('w','l'),wl):
                self.assertAlmostEqual(values[k],value)
                self.assertEqual(scalar(other['parameters'][k]['default']),value)
            self.assertEqual(catalog[key]['parameters']['l']['default'],'0.15')
        self.assertEqual(digest(self.tech),before)

    def test_only_seven_fresh_instances_change_across_the_complete_catalog(self):
        changed=[];catalog=self.tech['simulation']['catalog']
        for key,entry in catalog.items():
            if entry.get('unavailable'):continue
            with patch('icstudio.sky130_defaults.initial_dimensions',return_value=None):old=create_device(self.tech,key,'DUT')
            new=create_device(self.tech,key,'DUT')
            for value in (old,new):value.pop('id')
            if old!=new:
                changed.append(key);self.assertEqual({k:v for k,v in old.items() if k!='params'},{k:v for k,v in new.items() if k!='params'})
                self.assertEqual({k:v for k,v in old['params'].items() if k not in ('w','l')},{k:v for k,v in new['params'].items() if k not in ('w','l')})
        self.assertEqual(set(changed),set(CONTRACTS))
        self.assertEqual(len(DEFAULTS),42);self.assertEqual(len(list(rows())),42)
        self.assertEqual(len([d for d in fixture(self.tech,'dc')['cells'][0]['devices'] if d.get('model_ref')]),42)

    def test_changed_source_bytes_cannot_receive_the_reviewed_correction(self):
        key=next(iter(CONTRACTS));entry=self.tech['simulation']['catalog'][key]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);tech=clone(self.tech);tech['package_root']=str(root)
            for name in CONTRACTS[key]['source_files']:
                dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(Path(self.tech['package_root'])/name,dest)
            self.assertIsNotNone(initial_dimensions(tech,key,entry))
            source=root/entry['source'];source.write_bytes(source.read_bytes()+b'\n# changed\n')
            with self.assertRaisesRegex(ValueError,'missing or changed'):create_device(tech,key,'DUT')

    def test_custom_bindings_and_unreviewed_revisions_keep_their_defaults(self):
        key=next(iter(CONTRACTS));tech=clone(self.tech);entry=tech['simulation']['catalog'][key]
        entry['parameters']['l']['default']='0.8';self.assertIsNone(initial_dimensions(tech,key,entry))
        self.assertAlmostEqual(scalar(create_device(tech,key,'DUT')['params']['l']),.8e-6)
        tech=clone(self.tech);source=next(iter(CONTRACTS[key]['source_files']));tech['package_lock']['files'][source]='0'*64
        self.assertIsNone(initial_dimensions(tech,key,tech['simulation']['catalog'][key]))

    def test_saved_and_exchanged_existing_geometry_is_never_repaired_implicitly(self):
        from icstudio.interchange import export_xschem
        from icstudio.xschem_io import import_package
        from icstudio.catalog_migration import instance_name
        before=digest(self.tech)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for i,key in enumerate(CONTRACTS):
                for j,geometry in enumerate((None,('1u','.15u'),('5u','2u'))):
                    p=example('empty');p['pdk']=clone(self.tech);d=create_device(self.tech,key,'M1');d['nets']=dict(d='D',g='G',s='S',b='B');p['cells'][0]['devices']=[d]
                    if geometry:d['params'].update(zip(('w','l'),geometry))
                    expected={k:scalar(d['params'][k]) for k in ('w','l')};entry=self.tech['simulation']['catalog'][key]
                    path=root/f'{i}-{j}.icproj';save_project(p,path);q=load_project(path);self.assertEqual(q['cells'],p['cells'])
                    exchange=root/f'{i}-{j}';export_xschem(q,exchange);loaded,_=import_package(exchange)
                    after=next(v for v in loaded['cells'][0]['devices'] if v['name']==instance_name(d,entry))
                    self.assertEqual(after['nets'],d['nets']);self.assertEqual(after['model_ref'],d['model_ref'])
                    for k,value in expected.items():self.assertAlmostEqual(scalar(after['params'][k]),value,places=15)
        self.assertEqual(digest(self.tech),before)

if __name__=='__main__':unittest.main()
