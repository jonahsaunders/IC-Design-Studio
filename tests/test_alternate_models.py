"""Source-listed alternatives must keep units, terminals and immutable identity."""
import json,re,tempfile,unittest
from contextlib import ExitStack
from pathlib import Path
from icstudio.model import clone,file_digest
from icstudio.catalog import create_device
from icstudio.interchange import spice
from icstudio.ngspice_compat import MODELS,MARKER,convert,legacy_catalog,legacy_symbol
from scripts.prepare_alternate_models import BASE,expand,alias_key,prepare
from scripts.alternate_model_source import base_models,PROMOTED
from scripts.inventory_device_models import inventory
from scripts.qualify_alternate_models import probes,fixture,compare_dc

ROOT=Path(__file__).resolve().parents[1]


class AlternateModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packages={};cls.reviews={};cls.roots={};cls.stack=ExitStack();cls.addClassCleanup(cls.stack.close)
        for target in BASE:
            root=cls.stack.enter_context(base_models(ROOT/'icstudio/assets/pdks'/target));cls.roots[target]=root
            cls.packages[target]=json.loads((root/'package.json').read_bytes())
            cls.reviews[target]=inventory(root)

    def expanded(self,target):
        package=clone(self.packages[target]);rows=expand(package,self.reviews[target])
        tech=clone(package['technology']);tech.update(package_root=str(self.roots[target]),package_lock={k:package[k] for k in ('id','revision','files')})
        return tech,rows

    def test_every_choice_has_a_unique_identity_or_explicit_missing_model(self):
        for target in BASE:
            tech,rows=self.expanded(target);old=self.packages[target]['technology']['simulation']['catalog'];cat=tech['simulation']['catalog']
            self.assertEqual({k:cat[k] for k in old},old)
            self.assertEqual(len(rows),25 if target=='sky130A' else 11)
            expected={r['key'] for f in (('diode','capacitor') if target=='sky130A' else ('capacitor',)) for r in probes(target,f)}
            self.assertEqual({r['device'] for r in rows if r['status']=='AVAILABLE'},expected)
            for row in rows:
                if row['status']=='UNAVAILABLE':
                    with self.assertRaisesRegex(ValueError,'definition is absent'):create_device(tech,row['device'],'DUT')
                else:
                    d=create_device(tech,row['device'],'DUT');self.assertEqual(d['model_ref']['device'],row['device'])

    def test_alternate_diodes_declare_units_on_both_runtime_conventions(self):
        tech,_=self.expanded('sky130A');rows=list(probes('sky130A','diode'));p=fixture(tech,rows,'diode',0,0);before=clone(p)
        text=spice(p);self.assertEqual(text.count(MARKER),28);self.assertEqual(before,p)
        for mode in ('scales-explicit-area','unscaled-explicit-area'):
            converted,count=convert(text,mode);self.assertEqual(count,28)
            self.assertEqual(convert(converted,mode),(converted,0))
        cat=tech['simulation']['catalog']
        for r in rows:
            entry=cat[r['key']];self.assertTrue(legacy_catalog(tech,entry))
            model=(Path(tech['package_root'])/entry['model_source']).read_text()
            self.assertRegex(model,r'(?im)^\+\s*level\s*=\s*3\.0')
            self.assertRegex(model,r'(?im)^\+\s*area\s*=\s*1\.0e\+12')
        self.assertEqual(len(MODELS),11)

    def test_missing_rf_models_and_other_conventions_cannot_use_conversion(self):
        tech,_=self.expanded('sky130A');entry=clone(tech['simulation']['catalog']['sky130_fd_pr/diode.sym'])
        for model in ('sky130_fd_pr__model__parasitic__rf_diode_ps2nw','other'):
            entry['model']=model;self.assertFalse(legacy_catalog(tech,entry))
            with self.assertRaises(ValueError):convert(MARKER+'\nD1 a b '+model+' area=1e12','unscaled-explicit-area')
        attrs=self.packages['sky130A']['technology']['simulation']['catalog']['sky130_fd_pr/diode.sym']['symbol']['attributes']
        for name in ('diode_pd2nw_05v5_hvt','model__parasitic__diode_ps2dn'):
            self.assertTrue(legacy_symbol(attrs,{'model':name}))
        self.assertFalse(legacy_symbol(attrs,{'model':'model__parasitic__rf_diode_ps2nw'}))

    def test_terminal_mutation_and_duplicate_expansion_fail_closed(self):
        for target in ('sky130A','gf180mcuC'):
            review=clone(self.reviews[target]);package=clone(self.packages[target])
            changed=next(r for r in review['alternatives'] if not r['current_default'] and r['definitions'] and r['prefix']=='X')
            for row in review['definitions']:
                if row['id'] in changed['definitions']:row['pins']=list(reversed(row['pins']))
            with self.assertRaisesRegex(ValueError,'Unreviewed'):expand(package,review)
            package=clone(self.packages[target]);expand(package,self.reviews[target])
            with self.assertRaisesRegex(ValueError,'already exists'):expand(package,self.reviews[target])

    def test_fixed_vpp_mapping_and_geometry_cannot_be_silently_replaced(self):
        tech,rows=self.expanded('sky130A');cat=tech['simulation']['catalog']
        for row in rows:
            if row['parent']!='sky130_fd_pr/vpp_cap.sym' or row['status']!='AVAILABLE':continue
            entry=cat[row['device']];self.assertEqual(entry['pin_order'],['c0','c1','sub','top'])
            self.assertEqual(set(entry['parameters']),{'mult'})
            self.assertEqual(row['terminal_contract'][:3],['c0','c1','b'])
            self.assertIn(row['terminal_contract'][-1],('m4','m5'))

    def test_unknown_package_or_existing_destination_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();(source/'package.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'exact reviewed'):prepare(source,root/'out')
            self.assertFalse((root/'out').exists())
            with self.assertRaisesRegex(ValueError,'already exists'):prepare(source,source)
            self.assertEqual((source/'package.json').read_bytes(),b'{}')

    def test_diode_comparison_rejects_missing_domain_and_terminal_faults(self):
        rows=list(probes('sky130A','diode'))[:1];tag=rows[0]['tag'];v=[-1e-15]*40+[-1e-3]
        good=dict(x=[-.2+i*.025 for i in range(41)],currents={'v'+tag+'p0':v,'v'+tag+'p1':[-a for a in v]})
        self.assertEqual(compare_dc(good,good,rows)['status'],'PASS')
        bad=clone(good);bad['currents']['v'+tag+'p0'][-1]*=2
        self.assertEqual(compare_dc(bad,good,rows)['status'],'MISMATCH')
        for key in ('x','currents'):
            bad=clone(good);bad[key]=[] if key=='x' else {}
            with self.assertRaises(ValueError):compare_dc(bad,good,rows)

    def test_cold_diode_sanity_requires_measurable_rectification_not_arbitrary_current(self):
        rows=list(probes('sky130A','diode'))[:1];tag=rows[0]['tag'];v=[-2e-13]*40+[-2e-8]
        data=dict(x=[-.2+i*.025 for i in range(41)],currents={'v'+tag+'p0':v,'v'+tag+'p1':[-a for a in v]})
        self.assertEqual(compare_dc(data,data,rows)['status'],'PASS')
        for values in ([0.0]*41,[-2e-8]*41,[-2e-13]*40+[-1e-13]):
            bad=clone(data);bad['currents']={'v'+tag+'p0':values,'v'+tag+'p1':[-a for a in values]}
            with self.assertRaises(ValueError):compare_dc(bad,bad,rows)

    def test_reproducible_packages_preserve_saved_revision_and_original_asset_bytes(self):
        from icstudio.pdks import PDKRegistry
        from icstudio.model import example,save_project,load_project
        for target in BASE:
            with self.subTest(target=target),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);source=ROOT/'icstudio/assets/pdks'/target
                result=prepare(source,root/'package');self.assertEqual(result['manifest_sha256'],PROMOTED[target])
                registry=PDKRegistry(root/'registry');old=registry.install(self.roots[target]/'package.json')
                p=example('empty');p['pdk']=registry.technology(old);save_project(p,root/'saved.icproj')
                new=registry.install(root/'package/package.json');self.assertNotEqual(old,new)
                self.assertEqual(load_project(root/'saved.icproj')['pdk']['package_lock'],p['pdk']['package_lock'])
                self.assertEqual(registry.verify(old)['revision'],self.packages[target]['revision'])
                for rel,h in self.packages[target]['files'].items():self.assertEqual(file_digest(root/'package'/rel),h)


if __name__=='__main__':unittest.main()
