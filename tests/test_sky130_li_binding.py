import json,tempfile,unittest
from pathlib import Path
from icstudio import sky130_li_binding as binding
from icstudio.model import clone
from icstudio.pdks import PDKRegistry
from icstudio.interchange import spice
from scripts.prepare_sky130_li_qualification import prepare,KEY
from scripts.qualify_catalog_interfaces import one
from scripts.qualify_sky130_li import fixture,compare
from scripts.sky130_li_source import previous_li
ROOT=Path(__file__).resolve().parents[1]


class Sky130LiBindingTests(unittest.TestCase):
    def test_mapping_requires_exact_symbol_and_model_sources(self):
        root=ROOT/'icstudio/assets/pdks/sky130A';symbol=(root/'libs.tech/xschem'/KEY).read_bytes();model=(root/'libs.tech/ngspice/sky130_fd_pr__model__r+c.model.spice').read_bytes()
        self.assertEqual(binding.reviewed_model(symbol,model),'sky130_fd_pr__res_generic_l1')
        for s,m in ((symbol+b'\n',model),(symbol,model+b'\n')):
            with self.assertRaises(ValueError):binding.reviewed_model(s,m)

    def test_package_changes_only_reviewed_binding_and_keeps_old_revision(self):
        source=self.enterContext(previous_li(ROOT/'icstudio/assets/pdks/sky130A'));before=json.loads((source/'package.json').read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);out=folder/'package';record=prepare(source,out);after=json.loads((out/'package.json').read_bytes())
            self.assertNotEqual(record['revision'],before['revision']);self.assertEqual({n:h for n,h in after['files'].items() if n in before['files']},before['files'])
            a=clone(before['technology']);b=clone(after['technology']);a.pop('revision');b.pop('revision')
            old=a['simulation']['catalog'].pop(KEY);new=b['simulation']['catalog'].pop(KEY);self.assertEqual(a,b)
            self.assertTrue(old['unavailable']);self.assertFalse(new.get('unavailable'));self.assertEqual(new['model'],binding.MODEL)
            registry=PDKRegistry(folder/'registry');key=registry.install(out/'package.json');tech=registry.technology(key)
            self.assertEqual(one(tech,KEY,folder/'interface')['status'],'PASS')
            text=spice(fixture(tech,'dc'))
            fields=next(line.split() for line in text.splitlines() if line.startswith('R_Doutg3m3 '))
            self.assertEqual(fields[1:4],['input','outg3m3','sky130_fd_pr__res_generic_l1'])
            self.assertEqual(dict(v.split('=',1) for v in fields[4:]),dict(w='2',l='5',m='3'))
            self.assertNotIn('sky130_fd_pr__res_generic_li ',text)
            self.assertEqual(before,json.loads((source/'package.json').read_bytes()))
            with self.assertRaises(ValueError):prepare(source,out)

    def test_comparator_rejects_missing_phase_incomplete_sweep_and_wrong_voltage(self):
        from scripts.qualify_sky130_li import points
        x=[i*.000025 for i in range(41)];good=dict(x=x,traces={r['tag']:[v*.5 for v in x] for r in points()})
        self.assertEqual(compare(good,good,'dc')['status'],'PASS')
        wrong=clone(good);wrong['traces']['outg0m1']=[v*.9 for v in wrong['traces']['outg0m1']]
        self.assertEqual(compare(wrong,good,'dc')['status'],'MISMATCH')
        bad=clone(good);bad['x']=bad['x'][:-1]
        with self.assertRaises(ValueError):compare(bad,good,'dc')
        ac=dict(x=[100*10**(i/5) for i in range(26)],traces={r['tag']:[.5]*26 for r in points()})
        with self.assertRaises(ValueError):compare(ac,ac,'ac')


if __name__=='__main__':unittest.main()
