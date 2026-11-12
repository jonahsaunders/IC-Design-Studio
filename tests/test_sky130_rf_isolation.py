"""Prevent lost substrate terminals and false RF isolation connectivity passes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio import sky130_rf_isolation as rf
from icstudio.layout_verification import run
from icstudio.model import example
from scripts.qualify_sky130_rf_isolation import stream,selected,SIZES,PHYSICAL_FAULTS,REFERENCE_FAULTS


class Sky130RfIsolationTests(unittest.TestCase):
    def test_rotated_geometry_and_every_written_contact_fault(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'coupon.gds'
            for w,l in SIZES:
                for angle in (0,90,180,270):
                    for fault in (None,*PHYSICAL_FAULTS):
                        with self.subTest(w=w,l=l,angle=angle,fault=fault):
                            stream(path,w,l,angle,fault);result=rf.contacts(path,'rf_isolation',['A','K','S'])
                            # A narrow, fully contacted well is topologically
                            # valid; only the native process DRC may accept it.
                            self.assertEqual(result['passed'],fault in (None,'nwell-hole-spacing'),result)
                            if fault is None:
                                self.assertEqual(result['terminal_roles'],dict(anode='A',cathode='K',substrate='S'))
                                expected=rf.circuit(selected(w,l)['text'],'rf_isolation')['records']
                                for model in rf.MODELS:
                                    for key,value in result['geometry'][model].items():self.assertAlmostEqual(value,expected[model][key])

    def test_substrate_open_stops_native_body_joins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'coupon.gds';stream(path,2,2,fault='substrate-mcon')
            with patch.object(rf,'_execute') as engine:
                with self.assertRaisesRegex(ValueError,'contact audit failed'):
                    rf.extract('klayout',path,'rf_isolation',['A','K','S'],{},root/'out')
                engine.assert_not_called()
            self.assertFalse(json.loads((root/'out/contacts.json').read_text())['passed'])

    def test_entire_graph_geometry_and_no_electrical_model_substitution(self):
        text=selected(2,2)['text'];self.assertTrue(rf.compare(text,text,'rf_isolation')['unique_match'])
        self.assertFalse(rf.circuit(text,'rf_isolation')['simulation_models'])
        for fault in REFERENCE_FAULTS:
            with self.subTest(fault=fault),self.assertRaises(ValueError):rf.compare(selected(2,2,fault)['text'],text,'rf_isolation')
        for bad in (text.replace('perim=8','area=8'),text.replace('area=4','area=NaN'),
                    text.replace('area=4','area={w*l}'),text.replace('D2','D1'),
                    text.replace('.ends','R1 A K 1k\n.ends'),text.replace('.ends','.param hidden=1\n.ends'),
                    text.replace('D2 S K','D2 A K'),text.replace('D2 S K','D2 K S')):
            with self.subTest(bad=bad),self.assertRaises(ValueError):rf.compare(bad,text,'rf_isolation')

    def test_native_units_preserve_all_three_geometry_records(self):
        text='.subckt rf_isolation A K S\nD1 A K rf_pw2dn_geometry A=4p P=8u\nD2 S K isolation_dnwell_geometry A=17.64p P=16.8u\nD3 S K isolation_nwell_skirt_geometry A=7.36p P=36.8u\n.ends\n'
        got=rf.circuit(text,'rf_isolation',native=True)
        self.assertAlmostEqual(got['records'][rf.MODELS[1]]['area_um2'],17.64)
        self.assertAlmostEqual(got['records'][rf.MODELS[2]]['perimeter_um'],36.8)
        for bad in (text.replace(' P=16.8u',''),text.replace(' A=17.64p',' A=0'),text.replace('D3','X3')):
            with self.assertRaises(ValueError):rf.circuit(bad,'rf_isolation',native=True)

    def test_two_terminal_reference_and_wrong_process_rejected(self):
        text=selected(2,2)['text']
        with self.assertRaises(ValueError):rf.circuit(text.replace('.subckt rf_isolation A K S','.subckt rf_isolation A K'),'rf_isolation')
        p=example('empty')
        with tempfile.TemporaryDirectory() as tmp:
            result=run(p,p['top'],tmp,{},selected(2,2),lvs_extractor='sky130-rf-isolation-klayout')
            self.assertEqual(result['status'],'blocked');self.assertIn('SKY130A',result['error'])


if __name__=='__main__':unittest.main()
