"""Ineffective public model dimensions cannot masquerade as editable geometry."""
import json,tempfile,unittest
from pathlib import Path
from icstudio.model import clone,example,load_project,save_project
from icstudio.catalog import create_device,parameter_values,validate_catalog
from icstudio.sky130_fixed_geometry import CONTRACTS,constrain
from scripts.prepare_sky130_fixed_geometry import prepare
from scripts.device_qualification_source import previous_devices
ROOT=Path(__file__).resolve().parents[1]


class FixedGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.result=prepare(ROOT/'icstudio/assets/pdks/sky130A',cls.root/'package')
        cls.package=json.loads((cls.root/'package/package.json').read_bytes())
        cls.tech=clone(cls.package['technology']);cls.tech.update(package_root=str(cls.root/'package'),package_lock={k:cls.package[k] for k in ('id','revision','files')})
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_all_seven_views_reject_changed_geometry_and_allow_parallel_copies(self):
        for key in self.result['changed_bindings']:
            entry=self.tech['simulation']['catalog'][key];d=create_device(self.tech,key,'M1')
            values=parameter_values(entry,d)
            self.assertEqual(values['w'],float(CONTRACTS[entry['model']][1]))
            for dimension in ('w','l'):
                for factor in (.5,1.000001,2):
                    q=clone(d)
                    if d['kind'] in ('NMOS','PMOS'):q['params'][dimension]=str(values[dimension]*factor*1e-6)
                    else:q['model_params'][dimension]=str(values[dimension]*factor)
                    with self.subTest(key=key,dimension=dimension,factor=factor),self.assertRaisesRegex(ValueError,'fixed'):
                        parameter_values(entry,q)
            d['model_params']['mult']=3
            self.assertEqual(parameter_values(entry,d)['mult'],3)

    def test_fixed_parameters_are_not_search_targets_and_cannot_be_changed_by_saved_study(self):
        from icstudio import analog_optimizer,studies
        p=example('empty');p['pdk']=clone(self.tech);c=p['cells'][0]
        c['devices']=[create_device(self.tech,k,'M'+str(i)) for i,k in enumerate(self.result['changed_bindings'])]
        targets=analog_optimizer.targets(p,c['id'])
        self.assertEqual(set(targets),{d['name']+'.model_params.mult' for d in c['devices']})
        for d in c['devices']:
            if d['kind'] not in ('NMOS','PMOS'):continue
            before=clone(d)
            with self.assertRaisesRegex(ValueError,'fixed'):studies.set_target(p,c['id'],d['name']+'.params.w','1u')
            self.assertEqual(d,before)

    def test_unknown_model_bytes_or_symbol_defaults_fail_closed(self):
        for model in CONTRACTS:
            e=next(e for e in self.tech['simulation']['catalog'].values() if e.get('model')==model)
            params=clone(e['parameters']);before=clone(params)
            with self.assertRaisesRegex(ValueError,'Unreviewed'):constrain(model,params,b'changed model')
            self.assertEqual(params,before)
            params['w']['default']='100'
            with self.assertRaisesRegex(ValueError,'Unexpected'):constrain(model,params,(self.root/'package'/e['model_source']).read_bytes())

    def test_new_import_recognizes_exact_source_contract(self):
        from icstudio.pdk_import import scan_local
        catalog=scan_local(ROOT/'icstudio/assets/pdks/sky130A')['technology']['simulation']['catalog']
        for key in self.result['changed_bindings']:
            self.assertFalse(catalog[key]['unavailable'])
            self.assertEqual(catalog[key]['parameters'],self.tech['simulation']['catalog'][key]['parameters'])

    def test_invalid_fixed_metadata_and_default_rejected(self):
        key=self.result['changed_bindings'][0]
        for changed in ({'fixed':'nan'},{'fixed':'0'},{'fixed':'-1'},{'default':'100'},{'maximum':'1'}):
            entry=clone(self.tech['simulation']['catalog'][key]);entry['parameters']['w'].update(changed)
            with self.subTest(changed=changed),self.assertRaises(ValueError):validate_catalog({'simulation':{'catalog':{key:entry}}})

    def test_handoff_preserves_contract_and_original_saved_revision(self):
        from icstudio.interchange import export_xschem
        from icstudio.xschem_io import import_package
        from icstudio.catalog_migration import instance_name
        from scripts.qualify_mos_variants import fixture
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=fixture(self.tech,'sky-hv','dc',[])
            save_project(p,root/'new.icproj');self.assertEqual(load_project(root/'new.icproj')['pdk']['package_lock'],p['pdk']['package_lock'])
            export_xschem(p,root/'exchange');q,_=import_package(root/'exchange')
            for d in p['cells'][0]['devices']:
                if not d.get('model_ref'):continue
                e=self.tech['simulation']['catalog'][d['model_ref']['device']]
                after=next(a for a in q['cells'][0]['devices'] if a['name']==instance_name(d,e))
                self.assertEqual(parameter_values(e,d),parameter_values(e,after))
            with previous_devices(ROOT/'icstudio/assets/pdks/sky130A') as source:
                old=json.loads((source/'package.json').read_bytes())
                oldtech=clone(old['technology']);oldtech.update(package_lock={k:old[k] for k in ('id','revision','files')},package_root=str(source))
                p=fixture(oldtech,'sky-hv','dc',[]);save_project(p,root/'old.icproj')
                self.assertEqual(load_project(root/'old.icproj')['pdk']['revision'],old['revision'])
                self.assertNotIn('fixed',oldtech['simulation']['catalog'][self.result['changed_bindings'][0]]['parameters']['w'])


if __name__=='__main__':unittest.main()
