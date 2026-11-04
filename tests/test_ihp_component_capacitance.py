import unittest
from unittest.mock import patch

from scripts.ihp_component_capacitance import reduce_components
from scripts.ihp_native_capacitance import reduce_capacitors

try:
    import numpy
    import scipy
except ImportError:
    numpy = None


@unittest.skipUnless(numpy is not None, 'Optional reference-solver dependencies unavailable')
class ComponentReductionTests(unittest.TestCase):
    def graph(self):
        return dict(nodes=['G','A','B','C','POLY','FILL008_1','FILL008_2','FILL008_3','FILL001_J'],
                    edges_af=[('A','G',2.),('A','B',3.),('A','FILL008_1',4.),('FILL008_1','B',5.),
                              ('FILL008_1','G',6.),('B','POLY',7.),('POLY','C',8.),
                              ('POLY','FILL001_J',9.),('FILL008_2','FILL008_3',10.)], source_sha256='0'*64)

    def test_independent_components_match_global_schur(self):
        graph = self.graph()
        actual = reduce_components(graph,'G',additional_floating_nodes=['POLY'])
        reference = reduce_capacitors(graph,'G',relative_charge_error=0,additional_floating_nodes=['POLY'])
        self.assertEqual(actual['ground_af'].keys(),reference['ground_af'].keys())
        for n, value in reference['ground_af'].items():
            self.assertAlmostEqual(actual['ground_af'][n],value,places=12)
        def mutual(r):return {(a,b):c for a,b,c in r['couplings_af']}
        self.assertEqual(mutual(actual).keys(),mutual(reference).keys())
        for pair, value in mutual(reference).items():
            self.assertAlmostEqual(mutual(actual)[pair],value,places=12)
        self.assertEqual(actual['observable_floating_nodes'],2)
        self.assertEqual(actual['active_junction_nodes'],1)
        self.assertEqual(len(actual['components']),3)

    def test_large_retained_inventory_never_becomes_one_dense_matrix(self):
        names=['N'+str(i) for i in range(5000)]
        graph=dict(nodes=['G',*names],edges_af=[(n,'G',1.) for n in names],source_sha256='1'*64)
        with patch('scripts.ihp_component_capacitance.reduce_capacitors',side_effect=AssertionError('Unexpected dense solve')):
            result=reduce_components(graph,'G')
        self.assertEqual(result['retained_nodes'],5000)
        self.assertEqual(result['largest_component_ports'],0)
        self.assertTrue(all(v==1 for v in result['ground_af'].values()))

    def test_component_limit_rejects_before_allocation(self):
        with patch('scripts.ihp_component_capacitance.reduce_capacitors',side_effect=AssertionError('Unexpected dense solve')):
            with self.assertRaisesRegex(ValueError,'dense port budget'):
                reduce_components(self.graph(),'G',additional_floating_nodes=['POLY'],max_component_ports=2)

    def test_output_and_float_classification_bounds_are_enforced(self):
        for options in ({'max_output_pairs':1},{'max_component_ports':4097},
                        {'additional_floating_nodes':['FILL001_J']},{'additional_floating_nodes':['G']},
                        {'additional_floating_nodes':['missing']}):
            with self.subTest(options=options),self.assertRaises(ValueError):
                reduce_components(self.graph(),'G',**options)

    def test_global_pruning_retains_diagonal_and_charge_budget(self):
        graph=dict(nodes=['G','A','B'],edges_af=[('A','G',100.),('B','G',100.),('A','B',.005)],source_sha256='2'*64)
        result=reduce_components(graph,'G',relative_charge_error=1e-4)
        self.assertEqual(result['couplings_af'],[])
        self.assertEqual(result['ground_af'],{'A':100.005,'B':100.005})

    def test_invalid_capacitor_and_duplicate_inventory_fail(self):
        for change in (dict(nodes=['G','A','A']), dict(edges_af=[('A','A',1.)]),
                       dict(edges_af=[('A','B',float('nan'))]),dict(edges_af=[('A','missing',1.)])):
            with self.subTest(change=change),self.assertRaises(ValueError):
                reduce_components({**self.graph(),**change},'G')


if __name__=='__main__':unittest.main()
