import math
import unittest
from scripts.ihp_fill_reduction import reduce_floating, solve


class IHPFillReductionTests(unittest.TestCase):
    def test_one_float_has_analytic_series_capacitance(self):
        r=reduce_floating({'signal':1.,'fill':2.},{('signal','fill'):3.},{'fill'})
        self.assertAlmostEqual(r['ground_f']['signal'],1.+6./5.)
        self.assertFalse(r['coupling_f'])

    def test_large_lattice_preserves_symmetry_and_constant_solution(self):
        # A grounded chain with uniform boundary injection has x=1/2 exactly.
        # This exercises a component larger than the old dense solver's limit.
        n=700; rows=[[] for _ in range(n)]; diag=[2.]*n
        for i in range(n-1):
            rows[i].append((i+1,-3.));rows[i+1].append((i,-3.));diag[i]+=3;diag[i+1]+=3
        x, count, residual=solve(diag,rows,[1.]*n)
        self.assertLess(max(abs(v-.5) for v in x),1e-10)
        self.assertLess(residual,1e-11)
        self.assertGreater(count,1)

    def test_capacitance_scaling_and_mutual_conservation(self):
        for scale in (1.,1e-18,1e6):
            r=reduce_floating({'a':0.,'b':0.,'f':2*scale},
                              {('a','f'):3*scale,('b','f'):5*scale},{'f'})
            self.assertAlmostEqual(r['ground_f']['a']/scale,.6)
            self.assertAlmostEqual(r['ground_f']['b']/scale,1.)
            self.assertAlmostEqual(r['coupling_f'][0]['value_f']/scale,1.5)

    def test_invalid_matrix_and_declared_missing_nodes_rejected(self):
        for ground,caps,floats in [({'s':1},{},['unknown']),({'s':math.nan},{},[]),
                                  ({'s':1,'f':1},{('s','f'):-1},['f']),
                                  ({'s':1,'f':1},{('s','s'):1},['f'])]:
            with self.subTest(ground=ground),self.assertRaises(ValueError):
                reduce_floating(ground,caps,floats)
        with self.assertRaises(ValueError):solve([2.,2.],[[(1,-1.)],[]],[1.,1.])
        with self.assertRaises(ValueError):solve([1.,1.],[[(1,-2.)],[(0,-2.)]],[1.,1.])

    def test_oversize_observable_component_is_not_silently_omitted(self):
        nodes={str(n):1. for n in range(1025)};nodes['signal']=0.
        caps={(str(i),str(i+1)):1. for i in range(1024)};caps['0','signal']=1.
        with self.assertRaisesRegex(ValueError,'fixed budget'):
            reduce_floating(nodes,caps,set(nodes)-{'signal'})
