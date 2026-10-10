from pathlib import Path
import tempfile
import unittest
from scripts.ihp_floating_poly import classify


class FloatingPolyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.ext=root/'native.ext';self.circuit=root/'circuit.spice'
        self.ext.write_text('node "S" 0 2 0 0 m1\nsubstrate "G" 0 0 0 0 psub\nnode "P" 0 3 1 1 p\nport "S" 1 0 0 m1\n')
        self.circuit.write_text('X0 S S G G sg13_lv_nmos w=1u l=.13u\n.include capacitance.spice\n')
        self.weights={n:{n:1.} for n in ('S','G','P')}

    def check(self):
        return classify(self.ext,self.circuit,self.weights)

    def test_only_unconnected_poly_is_selected(self):
        self.assertEqual(self.check()['nodes'],['P'])

    def test_gate_resistor_and_port_are_each_protected(self):
        for kind in ('gate','resistor','port'):
            with self.subTest(kind=kind):
                circuit='X0 S S G G sg13_lv_nmos w=1u l=.13u\n'
                ext=self.ext.read_text().split('port "P"')[0]
                if kind=='gate':circuit=circuit.replace('S S G G','S P G G')
                if kind=='resistor':circuit+='R0 P G 1\n'
                if kind=='port':ext+='port "P" 2 1 1 p\n'
                self.ext.write_text(ext);self.circuit.write_text(circuit)
                self.assertEqual(self.check()['nodes'],[])

    def test_unknown_device_and_hidden_include_are_rejected(self):
        for text in ('X0 S P G G other_model w=1u l=.13u\n','.include devices.spice\n'):
            self.circuit.write_text(text)
            with self.assertRaises(ValueError):self.check()

    def test_active_or_resistive_shape_cannot_be_assumed_floating_poly(self):
        for line in ('node "P" 0 3 1 1 ndiff','node "P" 1 3 1 1 p'):
            self.ext.write_text('node "S" 0 2 0 0 m1\nsubstrate "G" 0 0 0 0 psub\n'+line+'\n')
            with self.assertRaises(ValueError):self.check()
