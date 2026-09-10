"""Protect the supplied quick bench and live formulas across native exchange."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from icstudio.model import clone

ROOT=Path(__file__).resolve().parents[1]


class BandgapCompatibilityTests(unittest.TestCase):
    def test_reduced_program_preserves_all_non_program_source_bytes(self):
        folder=ROOT/'examples/gf180-bandgap';meta=json.loads((folder/'compatibility-source.json').read_text(encoding='utf-8'))
        # Hash the actual bytes: default Windows decoding changes UTF-8
        # characters, and text mode can also normalize source line endings.
        reduced=(folder/'5vfullv2-compatibility.sch').read_bytes()
        # The uploaded revision only moved its code component from the earlier
        # tracked source. Device geometry, parameters and wiring are identical.
        original=(folder/'5vfullv2-original.sch').read_bytes().replace(b'C {devices/code_shown.sym} 2050 -680',b'C {devices/code_shown.sym} 2040 -720')
        self.assertEqual(hashlib.sha256(original).hexdigest(),meta['source_sha256'])
        self.assertEqual(hashlib.sha256(reduced).hexdigest(),meta['reduced_sha256'])
        def without_program(text):
            start=text.index(b'value="',text.index(b'{name=NGSPICE'))+len(b'value="');end=text.index(b'\n"}',start)
            return text[:start]+b'<PROGRAM>'+text[end:]
        self.assertEqual(without_program(original),without_program(reduced))

    def test_six_case_program_imports_offline_and_catalog_formulas_survive_exchange(self):
        from icstudio.xschem_compat import review_project
        from icstudio.native_migration import review
        from icstudio.catalog_migration import review as bind,emit
        from icstudio.catalog import parameter_values,binding_for
        from icstudio.pdks import PDKRegistry
        from icstudio.native_exchange import export_project,review_project as reimport
        from icstudio.xschem_runtime import netlist,prepare_program
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);record=review_project(ROOT/'examples/gf180-bandgap/5vfullv2-compatibility.sch')
            self.assertEqual(record['errors'],[]);p=record['candidate'];self.assertFalse(p['xschem_exchange']['unresolved'])
            text=netlist(p,root/'capture');program,count,_=prepare_program(text,root/'capture',{'probes':'v(vref)'})
            self.assertEqual(count,6);self.assertNotRegex(program,r'(?im)^\s*shell\s');self.assertNotIn('/foss/',program)
            registry=PDKRegistry(root/'registry');tech=registry.technology(registry.install(ROOT/'icstudio/assets/pdks/gf180mcuD/package.json'))
            result=bind(review(p)['candidate'],tech);self.assertEqual(result['converted'],60);self.assertEqual(result['unmatched'],0)
            native=result['candidate'];d=next(d for c in native['cells'] for d in c['devices'] if d['name']=='MTAIL')
            emitted=emit(d,tech);self.assertIn('l=6u w=28.91u',emitted);self.assertIn("ad='int((nf+1)/2) * w/nf * 0.18u'",emitted)
            exported=export_project(native,root/'export');back=reimport(Path(exported['directory'])/exported['top'])
            self.assertEqual(back['errors'],[]);returned=next(x for c in back['candidate']['cells'] for x in c['devices'] if x['id']==d['id'])
            binding=binding_for(tech,d);before=parameter_values(binding,d)
            for device in (d,returned):device['params']['w']=str(float(device['params']['w'])*2)
            expected=parameter_values(binding,d);actual=parameter_values(binding,returned)
            self.assertAlmostEqual(actual['ad']/before['ad'],2)
            for key in expected:
                if expected[key]:self.assertAlmostEqual(actual[key]/expected[key],1)
                else:self.assertEqual(actual[key],0)
            # An explicit external diffusion override still wins over a formula.
            text=Path(exported['directory'],exported['top']).read_text(encoding='utf-8');text=text.replace("ad=\"'int((nf+1)/2) * w/nf * 0.18u'\"",'ad="9e-12"')
            Path(exported['directory'],exported['top']).write_text(text,encoding='utf-8')
            edited=reimport(Path(exported['directory'])/exported['top']);self.assertEqual(edited['errors'],[])
            override=next(x for c in edited['candidate']['cells'] for x in c['devices'] if x['id']==d['id'])
            self.assertEqual(parameter_values(binding,override)['ad'],9e-12)

    def test_comparison_rejects_voltage_current_and_phase_changes(self):
        from scripts.verify_bandgap_compatibility import compare,CASES
        reference={name:{'x':[1.,2.],'traces':{'vref':[1.,1.]},'currents':{'i(vdd)':[1e-5,1e-5]},
                          'phase':{'vref':[0.,0.]},'current_phase':{'i(vdd)':[0.,0.]}} for name,_,_ in CASES}
        self.assertTrue(compare(reference,clone(reference))['passed'])
        for case,group,signal,value in [('startup','traces','vref',1.1),('dc-25C','currents','i(vdd)',2e-5),('psrr','phase','vref',15.)]:
            changed=clone(reference);changed[case][group][signal][1]=value
            self.assertFalse(compare(reference,changed)['passed'])
