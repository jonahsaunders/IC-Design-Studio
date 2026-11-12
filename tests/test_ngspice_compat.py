import hashlib,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from icstudio.ngspice_compat import MARKER,convert,declare,legacy_symbol


class DiodeGeometryCompatibilityTests(unittest.TestCase):
    def test_declared_units_only_and_runtime_copy_is_idempotent(self):
        raw='D1 a 0 sky130_fd_pr__diode_pw2nd_05v5 area={size * 1e12} pj=3e6 m=4\n'
        untouched='D2 a 0 sky130_fd_pr__diode_pw2nd_05v5 area=2\n'
        source=declare(raw)+untouched
        converted,count=convert(source,'unscaled-explicit-area')
        self.assertEqual(count,1)
        self.assertIn('area={(size * 1e12)*1e-12} pj={(3e6)*1e-6} m=4',converted)
        self.assertIn(untouched,converted)
        self.assertEqual(convert(converted,'unscaled-explicit-area'),(converted,0))
        old,count=convert(source,'scales-explicit-area')
        self.assertIn(raw,old);self.assertEqual(count,1)

    def test_incomplete_or_ambiguous_geometry_fails_closed(self):
        for line in ('', '.end', 'D1 a 0 different area=1',
                     'D1 a 0 sky130_fd_pr__diode_pw2nd_05v5 pj=1',
                     'D1 a 0 sky130_fd_pr__diode_pw2nd_05v5 area=1 w=2'):
            with self.subTest(line=line),self.assertRaises(ValueError):
                convert(MARKER+'\n'+line,'unscaled-explicit-area')

    def test_symbol_identification_uses_a_declared_convention_not_instance_size(self):
        attrs={'type':'diode','format':'@name @pinlist sky130_fd_pr__@model area=@area',
               'template':'name=D1 model=diode_pw2nd_05v5 area=1e12'}
        self.assertTrue(legacy_symbol(attrs))
        self.assertFalse(legacy_symbol({**attrs,'template':'name=D1 area=1'}))
        self.assertFalse(legacy_symbol(attrs,{'model':'unqualified_model'}))
        self.assertFalse(legacy_symbol(attrs,{'format':'custom'}))

    def test_catalog_units_require_the_locked_template_and_binding(self):
        from icstudio.ngspice_compat import legacy_catalog
        from scripts.qualify_standard_mos import load_technology
        tech,_=load_technology('sky130A');entry=tech['simulation']['catalog']['sky130_fd_pr/diode.sym']
        self.assertTrue(legacy_catalog(tech,entry))
        for field,value in [('prefix','X'),('model','other'),('source','other.sym'),('emit_parameters',{'area':'w'})]:
            bad=deepcopy(entry);bad[field]=value
            self.assertFalse(legacy_catalog(tech,bad),field)
        bad=deepcopy(tech);bad['package_lock']['files'][entry['source']]='0'*64
        self.assertFalse(legacy_catalog(bad,entry))

    def test_fresh_and_captured_catalog_paths_declare_area_without_changing_the_project(self):
        from scripts.qualify_standard_mos import load_technology
        from scripts.qualify_sky130_primitive_diodes import fixture
        from icstudio.interchange import spice
        from icstudio.native_spice import netlist
        from icstudio.catalog_migration import catalog_signature
        tech,_=load_technology('sky130A');p=fixture(tech)
        for d in p['cells'][0]['devices']:
            if d.get('model_ref'):d['model_params']['area']=1e8
        before=deepcopy(p);text=spice(p);self.assertEqual(text.count(MARKER),4);self.assertEqual(p,before)
        self.assertEqual(convert(text,'unscaled-explicit-area')[1],4)
        # Capture the real primitive model and a valid model-closure proof.
        entries={d['model_ref']['device']:tech['simulation']['catalog'][d['model_ref']['device']] for d in p['cells'][0]['devices'] if d.get('model_ref')}
        model=next(iter(entries.values()))['model_source'];contents=(Path(tech['package_root'])/model).read_text();h=hashlib.sha256(contents.encode()).hexdigest()
        p['spice']=dict(version=1,assets={h[:24]:dict(text=contents,sha256=h,name=model)},catalog_binding=dict(signature=catalog_signature(tech),models={key:[h] for key in entries}))
        captured=deepcopy(p)
        with tempfile.TemporaryDirectory() as tmp:
            text=netlist(p,Path(tmp)/'simulation');self.assertEqual(text.count(MARKER),4)
            lvs=netlist(p,Path(tmp)/'lvs',mode='lvs');self.assertNotIn(MARKER,lvs)
        self.assertEqual(p,captured)


if __name__=='__main__':unittest.main()
