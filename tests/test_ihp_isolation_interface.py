"""IHP terminal punctuation must survive catalog creation and real exchange."""
import json,tempfile,unittest
from pathlib import Path
from icstudio.model import clone
from icstudio.catalog import validate_catalog,create_device,parameter_values
from icstudio.ihp_isolation import constrain
from scripts.prepare_ihp_isolation_qualification import prepare,ROOT
from scripts.qualify_catalog_interfaces import one
from scripts.device_qualification_source import previous_devices


class IsolationInterfaceTests(unittest.TestCase):
    def test_reviewed_binding_preserves_all_sources_and_roundtrips(self):
        source=self.enterContext(previous_devices(ROOT/'icstudio/assets/pdks/ihp-sg13g2'))
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'package';record=prepare(source,out)
            p=json.loads((out/'package.json').read_bytes());tech=clone(p['technology'])
            tech.update(package_root=str(out),package_lock={k:p[k] for k in ('id','revision','files')})
            row=one(tech,'sg13g2_pr/isolbox.sym',Path(tmp)/'exchange')
            self.assertEqual(row['status'],'PASS',row)
            old=json.loads((source/'package.json').read_bytes())
            self.assertEqual(p['files'],old['files'])
            self.assertNotEqual(p['revision'],old['revision'])
            self.assertEqual(record['files'],157)
            changed=clone(p['technology']);changed['revision']=old['revision']
            changed['simulation']['catalog']['sg13g2_pr/isolbox.sym']['unavailable']='Invalid model terminals.'
            entry=changed['simulation']['catalog']['sg13g2_pr/isolbox.sym']
            for name in ('w','l'):entry['parameters'][name].pop('exclusive_minimum')
            self.assertEqual(changed,old['technology'])
            binding=tech['simulation']['catalog']['sg13g2_pr/isolbox.sym']
            d=create_device(tech,'sg13g2_pr/isolbox.sym','DUT')
            for name in ('w','l'):
                for value in ('0','-1u','2u','2.1u'):
                    bad=clone(d);bad['model_params'][name]=value
                    with self.subTest(name=name,value=value),self.assertRaises(ValueError):
                        parameter_values(binding,bad)
            d['model_params'].update(w='2.101u',l='2.101u')
            self.assertGreater(parameter_values(binding,d)['w'],2.1e-6)

    def test_changed_equations_require_a_new_review(self):
        with self.assertRaisesRegex(ValueError,'model revision'):
            constrain({'w':{},'l':{}},b'changed model')

    def test_fresh_stock_import_recognizes_the_public_symbol_and_domain_guards(self):
        from icstudio.pdk_import import scan_local
        p=scan_local(ROOT/'icstudio/assets/pdks/ihp-sg13g2')
        entry=p['technology']['simulation']['catalog']['sg13g2_pr/isolbox.sym']
        self.assertFalse(entry['unavailable'])
        self.assertEqual(entry['pin_order'],['isosub','nwell','sub!'])
        for name in ('w','l'):self.assertEqual(entry['parameters'][name]['exclusive_minimum'],'2.1u')

    def test_terminal_punctuation_does_not_relax_model_or_parameter_names(self):
        p=json.loads((ROOT/'icstudio/assets/pdks/ihp-sg13g2/package.json').read_bytes())
        entry=clone(p['technology']['simulation']['catalog']['sg13g2_pr/isolbox.sym']);entry['unavailable']=''
        validate_catalog({'simulation':{'catalog':{'test':entry}}})
        for key,value in [('model','isolbox!'),('pin_order',['a','b','bad\n.end']),
                          ('parameters',{'l!':{'default':'3u'}}),('emit_parameters',{'l!':'l'})]:
            bad=clone(entry);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_catalog({'simulation':{'catalog':{'test':bad}}})


if __name__=='__main__':unittest.main()
