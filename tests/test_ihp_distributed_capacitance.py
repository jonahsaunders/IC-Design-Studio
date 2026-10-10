import unittest
from scripts.ihp_distributed_capacitance import prepare
from icstudio.compact_rc import records
from tests.test_compact_rc import solve_helpers


class DistributedFillCapacitanceTests(unittest.TestCase):
    def inputs(self):
        graph = dict(nodes=['A', 'B', 'FILL008_0', 'G'],
                     edges_af=[('A', 'G', 2.), ('A', 'FILL008_0', 3.),
                               ('B', 'FILL008_0', 5.), ('FILL008_0', 'G', 7.),
                               ('A', 'B', 11.)], source_sha256='0' * 64)
        weights = {'A': {'A0': .2, 'A1': .8}, 'B': {'B0': .3, 'B1': .7},
                   'FILL008_0': {'FILL008_0': 1.}, 'G': {'G': 1.}}
        return graph, weights

    def test_every_endpoint_matches_independent_expanded_schur_matrix(self):
        import numpy as np
        graph, weights = self.inputs()
        physical = [n for group in weights.values() for n in group]
        result = prepare(graph, 'G', weights, physical, relative_charge_error=0)
        ix = {n: i for i, n in enumerate(physical)}
        full = np.zeros((len(ix), len(ix)))
        for a, b, c in graph['edges_af']:
            for x, wx in weights[a].items():
                for y, wy in weights[b].items():
                    i, j = ix[x], ix[y]; v = c * wx * wy
                    full[i, i] += v; full[j, j] += v
                    full[i, j] -= v; full[j, i] -= v
        kept = [n for n in physical if not n.startswith('FILL')]
        ki = [ix[n] for n in kept]; fi = [ix['FILL008_0']]
        expected = full[np.ix_(ki, ki)] - full[np.ix_(ki, fi)] @ np.linalg.solve(
            full[np.ix_(fi, fi)], full[np.ix_(fi, ki)])
        helpers, caps = records(result['compact_text'], physical)
        for driven in kept:
            voltages = solve_helpers(helpers, {n: float(n == driven) for n in physical})
            actual = {n: 0. for n in kept}
            for _, pos, neg, value in caps:
                actual[pos] += float(value) * 1e18 * (voltages[pos] - voltages[neg])
            for a, b, value in result['corrections_af']:
                q = value * (voltages[a] - voltages[b])
                actual[a] += q; actual[b] -= q
            for n in kept:
                self.assertAlmostEqual(actual[n], expected[kept.index(n), kept.index(driven)], delta=1e-12)
        self.assertTrue(result['corrections_af'])
        # Omitting the same-net term is an actual matrix error, despite passing
        # a check that collapses all resistance endpoints to their parent net.
        self.assertGreater(max(c for a, b, c in result['corrections_af']), .01)

    def test_distributed_fill_or_substrate_is_rejected(self):
        for name in ('FILL008_0', 'G'):
            graph, weights = self.inputs()
            weights[name] = {name: .5, name + '.t0': .5}
            with self.assertRaises(ValueError):
                prepare(graph, 'G', weights, {n for w in weights.values() for n in w})

    def test_missing_physical_endpoint_is_rejected(self):
        graph, weights = self.inputs()
        with self.assertRaises(ValueError):
            prepare(graph, 'G', weights, {'G'})

    def test_additional_conductor_needs_complete_connection_exclusion(self):
        graph,weights=self.inputs()
        graph['nodes']=[n.replace('FILL008_0','POLY') for n in graph['nodes']]
        graph['edges_af']=[(a.replace('FILL008_0','POLY'),b.replace('FILL008_0','POLY'),c)
                           for a,b,c in graph['edges_af']]
        weights['POLY']={'POLY':1.};del weights['FILL008_0']
        physical={n for group in weights.values() for n in group}
        for connected in (None,physical,iter(physical)):
            with self.subTest(connected=connected),self.assertRaises(ValueError):
                prepare(graph,'G',weights,physical,capacitor_only_nodes=['POLY'],connected_nodes=connected)
        result=prepare(graph,'G',weights,physical,capacitor_only_nodes=['POLY'],connected_nodes=physical-{'POLY'})
        self.assertNotIn('POLY',result['weights'])
        self.assertTrue(result['corrections_af'])


if __name__ == '__main__':
    unittest.main()
