import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SOURCE=Path(sys.argv[sys.argv.index('--source')+1]).resolve() if '--source' in sys.argv else Path(__file__).resolve().parents[2]/'IC-Design-Studio'
sys.path.insert(0,str(SOURCE))
CANDIDATE=Path(__file__).resolve().parents[1]
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,CANDIDATE/'scripts'/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
producer=module('external_producer','qualify_sky130_metal_hierarchy_electrical.py')
reader=module('external_reader','audit_sky130_metal_hierarchy_electrical.py')
NATIVE=b'* native retained shape\n.subckt res_pair A1 B1 A2 B2\nR0 B1 A1 sky130_fd_pr__res_generic_m1 w=2 l=5\nR1 A2 B2 sky130_fd_pr__res_generic_m1 w=2 l=5\n.ends\n'

class GuardTests(unittest.TestCase):
    def test_full_inventory(self):
        self.assertEqual(len(producer.cases()),50)
        self.assertEqual(len({c['name'] for c in producer.cases()}),50)
    def test_pilot_never_full(self):self.assertEqual(len(producer.cases(True)),5)
    def test_native_contract(self):producer.native_graph(NATIVE.decode(),'m1')
    def test_all_actual_controls(self):
        for fault in producer.FAULTS:
            changed=producer.mutate(NATIVE,'m1',fault)
            self.assertEqual(changed,reader.fault_bytes(NATIVE,fault))
            self.assertNotEqual(changed,NATIVE)
            with self.assertRaises(ValueError):producer.native_graph(changed.decode(),'m1')
    def test_native_width_rejected(self):
        with self.assertRaisesRegex(ValueError,'nets/width'):producer.native_graph(NATIVE.decode().replace('w=2','w=2.1'),'m1')
    def test_native_reversed_orientation_controls(self):
        data=NATIVE.replace(b'R1 A2 B2',b'R1 B2 A2')
        for fault in producer.FAULTS:self.assertEqual(producer.mutate(data,'m1',fault),reader.fault_bytes(data,fault))
    def test_native_port_order_rejected(self):
        with self.assertRaisesRegex(ValueError,'ordered interface'):producer.native_graph(NATIVE.decode().replace('A1 B1 A2 B2','B1 A1 A2 B2'),'m1')
    def test_native_model_rejected(self):
        with self.assertRaisesRegex(ValueError,'model'):producer.native_graph(NATIVE.decode(),'m2')
    def test_duplicate_native_name_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):producer.native_graph(NATIVE.decode().replace('R1 A2','R0 A2'),'m1')
    def test_independent_numeric_equations(self):
        spec=producer.contract()
        for model in producer.MODELS:
            for section in producer.SECTIONS:
                for width in (2,3):self.assertAlmostEqual(producer.resistance(spec,model,section,width),reader.resistance(spec['coefficients'][model][section],width),places=14)
    def test_conductance_reciprocity_and_kcl(self):
        values=producer.contract()['coefficients']['l1']['tt']
        for tag in producer.PATHS:
            matrix=reader.matrix(values,tag)
            for i in range(4):
                self.assertAlmostEqual(sum(matrix[i]),0)
                for j in range(4):self.assertEqual(matrix[i][j],matrix[j][i])
    def test_zero_crosspair(self):
        values=producer.contract()['coefficients']['m1']['tt']
        response=reader.currents(values,'native',[.001,0,0,0])
        self.assertEqual(response[2:],[0,0])
        self.assertNotEqual(reader.currents(values,'cross',[.001,0,0,0]),response)
    def test_full_contract_bound(self):self.assertEqual(producer.sha(CANDIDATE/producer.SPEC),reader.CONTRACT_SHA)
    def test_source_number_only_literal(self):
        self.assertEqual(reader.number('0.017u'),.017e-6)
        for value in ('nan','inf','{1+1}','1foo'):
            with self.assertRaises(ValueError):reader.number(value)
    def test_saved_data_must_be_finite(self):
        with self.assertRaises(ValueError):reader.compare_saved(float('nan'),1.)
    def test_native_raw_frequency_grid_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'result.raw';header='Title: sample\nPlotname: AC Analysis\nFlags: complex\nNo. Variables: 2\nNo. Points: 8\nVariables:\n0 frequency frequency grid=3\n1 v(a) voltage\nValues:\n'
            body=''.join(f'{i}\t{10**(i+3)},0\n\t0,0\n' for i in range(8));p.write_text(header+body)
            self.assertEqual(len(reader.raw(p,'sample','ac')[1]),8)
            p.write_text((header+body).replace('1 v(a)','0 v(a)'))
            with self.assertRaises(ValueError):reader.raw(p,'sample','ac')
    def test_nonfinite_native_voltage_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'result.raw';header='Title: sample\nPlotname: DC transfer characteristic\nFlags: real\nNo. Variables: 2\nNo. Points: 3\nVariables:\n0 v(v-sweep) voltage\n1 v(a) voltage\nValues:\n'
            p.write_text(header+'0 -0.001\n nan\n1 0\n 0\n2 0.001\n 0\n')
            with self.assertRaisesRegex(ValueError,'Nonfinite'):reader.raw(p,'sample','dc')

if __name__=='__main__':
    if '--source' in sys.argv:
        i=sys.argv.index('--source');del sys.argv[i:i+2]
    unittest.main()
