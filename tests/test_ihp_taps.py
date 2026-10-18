import json
from pathlib import Path
import tempfile
import unittest

from icstudio.catalog import create_device,parameter_values,import_emitted_parameters
from icstudio.catalog_migration import emitted_parameters
from icstudio.ihp_taps import SYMBOLS,constrain,declarative_symbol
from icstudio.model import clone
from icstudio.pdk_import import scan_local
from icstudio.symbol_io import import_symbol

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'icstudio/assets/pdks/ihp-sg13g2'


class IHPTapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=scan_local(SOURCE)
        cls.tech=cls.package['technology']
        cls.tech['package_lock']={k:cls.package[k] for k in ('id','revision','files')}

    def test_both_reviewed_symbols_have_explicit_terminals_and_static_format(self):
        for name in SYMBOLS:
            with self.subTest(model=name):
                entry=self.tech['simulation']['catalog']['sg13g2_pr/'+name+'.sym']
                self.assertEqual(entry['unavailable'],'')
                self.assertEqual(entry['category'],'Resistors')
                self.assertEqual(entry['pin_order'],['p','m'])
                self.assertEqual(entry['prefix'],'X')
                self.assertEqual(entry['model'],name)
                self.assertNotIn('tcleval',entry['symbol']['attributes']['format'])
                self.assertNotIn('*lvs_format',entry['symbol']['attributes'])

    def test_changed_source_remains_unsupported_and_no_tcl_executes(self):
        for name in SYMBOLS:
            raw=(SOURCE/'libs.tech/xschem/sg13g2_pr'/f'{name}.sym').read_bytes()+b'\n'
            text,notes=declarative_symbol(raw)
            self.assertEqual(notes,[])
            self.assertIn('tcleval',text)
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'changed.sym';path.write_bytes(raw)
                with self.assertRaisesRegex(ValueError,'Invalid declarative symbol attributes'):
                    import_symbol(path)

    def test_resistance_is_parallel_area_and_perimeter_conductance(self):
        for name in SYMBOLS:
            key='sg13g2_pr/'+name+'.sym';entry=self.tech['simulation']['catalog'][key]
            for w,l in ((.78e-6,.78e-6),(.78e-6,5e-6),(5e-6,.78e-6),(2e-6,2e-6),(10e-6,10e-6)):
                with self.subTest(model=name,w=w,l=l):
                    d=create_device(self.tech,key,'DUT');d['model_params'].update(w=w,l=l)
                    expected=1/(w*l/9.8e-10+2*(w+l)/9.8e-4)
                    self.assertAlmostEqual(parameter_values(entry,d)['emit_r']/expected,1,places=14)
                    emitted=emitted_parameters(d,self.tech)
                    self.assertIn('w*l',emitted['r'])
                    self.assertEqual(set(emitted),{'w','l','r'})

    def test_illegal_dimensions_and_resistance_override_are_rejected(self):
        key='sg13g2_pr/ntap1.sym';entry=self.tech['simulation']['catalog'][key]
        for overrides in ({'w':0},{'l':-1},{'w':'nan'},{'emit_r':42}):
            with self.subTest(overrides=overrides),self.assertRaises(ValueError):
                d=create_device(self.tech,key,'DUT');d['model_params'].update(overrides);parameter_values(entry,d)

    def test_roundtrip_numeric_resistance_retains_live_geometry_expression(self):
        key='sg13g2_pr/ptap1.sym';entry=self.tech['simulation']['catalog'][key]
        d=create_device(self.tech,key,'DUT');value=parameter_values(entry,d)['emit_r']
        import_emitted_parameters(entry,d,{'r':str(value),'w':'.78u','l':'.78u'})
        self.assertNotIn('emit_r',d['model_params'])
        d['model_params']['w']='2u'
        self.assertNotAlmostEqual(parameter_values(entry,d)['emit_r'],value)
        with self.assertRaises(ValueError):
            import_emitted_parameters(entry,d,{'r':'42'})
            parameter_values(entry,d)

    def test_model_or_formula_change_requires_review(self):
        entry=self.tech['simulation']['catalog']['sg13g2_pr/ntap1.sym']
        source=(SOURCE/'libs.tech/ngspice/models/resistors_mod.lib').read_bytes()
        with self.assertRaisesRegex(ValueError,'source revision'):
            constrain('ntap1',clone(entry['parameters']),source+b'\n')
        params=clone(entry['parameters']);params['emit_r']['default']='42'
        with self.assertRaisesRegex(ValueError,'resistance formula'):
            constrain('ntap1',params,source)

    def test_unrelated_crlf_symbols_keep_original_text_normalization(self):
        text,notes=declarative_symbol(b'K {template="a=1\r\nb=2"}\r\n')
        self.assertEqual(text,'K {template="a=1\nb=2"}\n')
        self.assertEqual(notes,[])

    def test_new_default_preserves_saved_revision_and_every_original_asset(self):
        from icstudio.model import file_digest,save_project,load_project
        from icstudio.pdks import PDKRegistry
        from icstudio.project_hub import build_project,inventory
        from scripts.ihp_tap_source import previous_taps,BASE,PROMOTED,REVISION
        from scripts.prepare_ihp_taps import prepare
        with tempfile.TemporaryDirectory() as tmp,previous_taps(SOURCE) as original:
            root=Path(tmp);registry=PDKRegistry(root/'registry')
            self.assertEqual(file_digest(original/'package.json'),BASE)
            old=json.loads((original/'package.json').read_bytes());key=registry.install(original/'package.json')
            rows,notes=inventory(registry);self.assertEqual(notes,[])
            row=next(r for r in rows if r['key']==key)
            project=build_project(registry,row,'Saved original','empty')['project']
            save_project(project,root/'saved.icproj')
            current=next(r for r in rows if r['id']=='ihp-sg13g2' and r['status']=='Available offline')
            self.assertEqual(current['revision'],REVISION)
            new=json.loads((SOURCE/'package.json').read_bytes())
            self.assertEqual({k:new['files'][k] for k in old['files']},old['files'])
            a=clone(old['technology']);b=clone(new['technology']);a.pop('revision');b.pop('revision')
            for model in SYMBOLS:
                device='sg13g2_pr/'+model+'.sym'
                self.assertTrue(a['simulation']['catalog'].pop(device)['unavailable'])
                self.assertFalse(b['simulation']['catalog'].pop(device)['unavailable'])
            self.assertEqual(a,b)
            self.assertEqual(load_project(root/'saved.icproj')['pdk']['package_lock'],project['pdk']['package_lock'])
            self.assertEqual(registry.verify(key)['revision'],old['revision'])
            out=root/'rebuilt';result=prepare(SOURCE,out)
            self.assertEqual(result['manifest_sha256'],PROMOTED)
            self.assertEqual((out/'package.json').read_bytes(),(SOURCE/'package.json').read_bytes())
            for rel,h in old['files'].items():self.assertEqual(file_digest(out/rel),h)
            asset=out/'libs.tech/ngspice/models/resistors_mod.lib';asset.write_bytes(asset.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'Changed current IHP tap asset'):
                prepare(out,root/'must-not-exist')
            self.assertFalse((root/'must-not-exist').exists())


if __name__=='__main__':unittest.main()
