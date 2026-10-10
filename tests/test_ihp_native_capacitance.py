from pathlib import Path
import tempfile
import unittest
from scripts.ihp_native_capacitance import read_capacitors,reduce_capacitors,write_capacitors

try:
    import numpy as np
    import scipy
except ImportError:
    np=None


class NativeCapacitorParsingTests(unittest.TestCase):
    def parse(self,text):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'native.spice';p.write_text(text);return read_capacitors(p)

    def test_units_zero_and_native_float_annotation(self):
        result=self.parse('C0 S G 1f\nC1 FILL008_0 G 0 ; **FLOATING\nC2 S A 2e-18\n')
        self.assertEqual(result['edges_af'],[('S','G',1000.),('S','A',2.)])
        self.assertEqual(result['zero_capacitors'],1)

    def test_non_numeric_negative_ambiguous_and_duplicate_records_reject(self):
        for text in ('C0 S G {value}\n','C0 S G -1f\n','C0 S G 1f\nC0 S A 2f\n',
                     'C0 S G 1f\nC1 s A 2f\n','C0 S S 1f\n','C0 S G 1f surprise\n'):
            with self.subTest(text=text),self.assertRaises(ValueError):self.parse(text)

    def test_included_capacitor_network_cannot_be_silently_omitted(self):
        with self.assertRaisesRegex(ValueError,'self-contained'):
            self.parse('C0 S G 1f\n.include another-network.spice\n')
        self.assertEqual(len(self.parse('  C0 S G 1f\n')['edges_af']),1)


@unittest.skipUnless(np is not None,'Optional NumPy/SciPy reference solver dependencies unavailable')
class NativeCapacitorReductionTests(unittest.TestCase):
    def graph(self):
        return dict(nodes=['S','G','FILL008_0','FILL001_0'],edges_af=[('S','FILL008_0',2.),('FILL008_0','G',3.),('FILL008_0','FILL001_0',5.),('FILL001_0','G',7.)],source_sha256='0'*64)

    def test_series_network_keeps_active_junction_explicit(self):
        result=reduce_capacitors(self.graph(),'G',relative_charge_error=0)
        self.assertEqual(result['floating_metal_nodes'],1);self.assertEqual(result['active_junction_nodes'],1)
        self.assertAlmostEqual(result['ground_af']['S'],.6)
        self.assertAlmostEqual(result['ground_af']['FILL001_0'],8.5)
        self.assertAlmostEqual(result['couplings_af'][0][2],1.)

    def test_disconnected_float_is_reported_without_artificial_leakage(self):
        graph=self.graph();graph['nodes']+=['FILL008_1','FILL008_2'];graph['edges_af'].append(('FILL008_1','FILL008_2',1.))
        result=reduce_capacitors(graph,'G')
        self.assertEqual((result['floating_metal_nodes'],result['observable_metal_nodes']),(3,1))
        self.assertNotIn('FILL008_1',result['ground_af'])

    def test_verified_capacitor_graph_is_used_directly(self):
        # The caller supplies a graph checked against the flat native extraction.
        # Reduction preserves its original node identities and ground terms.
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'native.spice';p.write_text('C0 S G 0\nC1 A G 2f\n')
            result=reduce_capacitors(read_capacitors(p),'G')
            self.assertEqual(result['ground_af'],{'A':2000.,'S':0.})

    def test_sparsification_preserves_diagonal_and_row_budget(self):
        graph=dict(nodes=['S','A','G'],edges_af=[('S','G',100.),('A','G',100.),('S','A',.005)],source_sha256='0'*64)
        result=reduce_capacitors(graph,'G')
        self.assertEqual(result['couplings_af'],[])
        for c in result['ground_af'].values():self.assertAlmostEqual(c,100.005)
        with self.assertRaises(ValueError):reduce_capacitors(graph,'G',relative_charge_error=.001)

    def test_written_network_roundtrips_and_does_not_overwrite(self):
        result=reduce_capacitors(self.graph(),'G',relative_charge_error=0)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'reduced.spice';write_capacitors(result,path)
            reread=reduce_capacitors(read_capacitors(path),'G',relative_charge_error=0)
            for node,c in result['ground_af'].items():self.assertAlmostEqual(c,reread['ground_af'][node])
            with self.assertRaises(ValueError):write_capacitors(result,path)


if __name__=='__main__':unittest.main()
