"""Physical false-pass controls for the bounded SKY130 RF n-well route."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio import sky130_rf_verification as rf
from icstudio.layout_verification import run
from icstudio.model import example
from scripts.qualify_sky130_rf_layouts import stream, selected, FAULTS, SIZES


class Sky130RfVerificationTests(unittest.TestCase):
    def test_metal_only_proof_accepts_rotations_and_rejects_every_physical_fault(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'coupon.gds'
            for w,l in SIZES:
                for angle in (0,90,180,270):
                    for fault in (None,*[f for f in FAULTS if not f.startswith('reference-')]):
                        with self.subTest(w=w,l=l,angle=angle,fault=fault):
                            stream(path,w,l,angle,fault);result=rf.contacts(path,'rf_coupon',['A','K'])
                            self.assertEqual(result['passed'],fault is None,result)
                            if fault is None:
                                self.assertEqual(result['terminal_roles'],dict(anode='A',cathode='K'))
                                self.assertAlmostEqual(result['junction']['area_um2'],w*l)
                                self.assertAlmostEqual(result['junction']['perimeter_um'],2*(w+l))

    def test_contact_failure_prevents_native_body_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'coupon.gds';stream(path,2,2,fault='anode-mcon')
            with patch.object(rf,'_execute') as engine:
                with self.assertRaisesRegex(ValueError,'contact audit failed'):
                    rf.extract('klayout',path,'rf_coupon',['A','K'],{},root/'out')
                engine.assert_not_called()
            self.assertFalse(json.loads((root/'out/contacts.json').read_text())['passed'])

    def test_reference_comparison_checks_geometry_polarity_model_and_complete_graph(self):
        text=selected(2,2)['text']
        self.assertTrue(rf.compare(text,text,'rf_coupon')['unique_match'])
        for fault in ('reference-area','reference-perimeter','reference-polarity','reference-model'):
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                rf.compare(selected(2,2,fault)['text'],text,'rf_coupon')
        for bad in (text.replace('area=4','area=4 m=2'),text.replace('perim=8','area=8'),
                    text.replace('area=4','area=NaN'),text.replace('area=4','area={w*l}'),
                    text.replace('XD A K','XD A A'),text.replace('.ends','R1 A K 1k\n.ends'),
                    text.replace('.ends','.param hidden=1\n.ends'),text.replace('XD A K','D1 A K')):
            with self.subTest(bad=bad),self.assertRaises(ValueError):rf.compare(bad,text,'rf_coupon')

    def test_native_units_and_no_extra_devices(self):
        text='.subckt rf_coupon A K\nD$1 A K rf_ps2nw A=4P P=8U\n.ends rf_coupon\n'
        result=rf.circuit(text,'rf_coupon',native=True)
        self.assertEqual(result['area_um2'],4);self.assertEqual(result['perimeter_um'],8)
        for bad in (text.replace('rf_ps2nw','unknown'),text.replace('P=8U','P=8U M=2'),
                    text.replace('P=8U',''),text.replace('.ends','D$2 A K rf_ps2nw A=4P P=8U\n.ends')):
            with self.assertRaises(ValueError):rf.circuit(bad,'rf_coupon',native=True)

    def test_zero_findings_without_completed_deck_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'coupon.gds';stream(path,2,2)
            with patch.object(rf,'_execute',return_value='Partial run'):
                with self.assertRaisesRegex(ValueError,'did not complete'):
                    rf.drc('klayout',path,'rf_coupon',{},root/'drc')

    def test_wrong_process_cannot_select_rf_route(self):
        p=example('empty')
        with tempfile.TemporaryDirectory() as tmp:
            r=run(p,p['top'],tmp,{},selected(2,2),lvs_extractor='sky130-rf-nwell-klayout')
            self.assertEqual(r['status'],'blocked');self.assertIn('SKY130A',r['error'])


if __name__=='__main__':unittest.main()
