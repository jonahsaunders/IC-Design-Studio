import math
import unittest

from scripts.ihp_spatial_field import Endpoint, halo_moments, joint_weights
from scripts.ihp_spatial_mesh import Mesh


def wire(net, box=(0, 0, 10, 10), axis=1, layer=76):
    return dict(net=net, type=layer, split=0, axis=axis, box=list(box),
                a={net+'.a': 1.}, b={net+'.b': 1.})


class FieldIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = 'NET000002', 'NET000003'
        self.left = Endpoint(net=self.a, layer='Metal1')
        self.right = Endpoint(net=self.b, layer='Metal1')
        self.mesh = Mesh([wire(self.a), wire(self.b)], {76: 'Metal1'})

    def test_coincident_wires_preserve_spatial_correlation(self):
        weights = joint_weights(self.mesh, self.left, self.right, [0, 0, 10, 10])
        self.assertAlmostEqual(weights[self.a+'.a', self.b+'.a'], 1/3)
        self.assertAlmostEqual(weights[self.a+'.a', self.b+'.b'], 1/6)
        self.assertAlmostEqual(weights[self.a+'.b', self.b+'.b'], 1/3)
        self.assertNotAlmostEqual(weights[self.a+'.a', self.b+'.a'], .25)

    def test_orthogonal_wire_axes_factor(self):
        mesh = Mesh([wire(self.a), wire(self.b, axis=2)], {76: 'Metal1'})
        weights = joint_weights(mesh, self.left, self.right, [0, 0, 10, 10])
        for value in weights.values():
            self.assertAlmostEqual(value, .25)

    def test_joined_partitions_and_reciprocity(self):
        rows = [wire(self.a), wire(self.b, (0, 0, 5, 10)),
                wire(self.b, (5, 0, 10, 10))]
        rows[2]['a'] = {self.b+'.b': 1.}; rows[2]['b'] = {self.b+'.c': 1.}
        mesh = Mesh(rows, {76: 'Metal1'})
        ab = joint_weights(mesh, self.left, self.right, [0, 0, 10, 10])
        ba = joint_weights(mesh, self.right, self.left, [0, 0, 10, 10])
        for (a, b), value in ab.items():
            self.assertAlmostEqual(value, ba[b, a])
        self.assertAlmostEqual(sum(v for (a, b), v in ab.items() if b == self.b+'.b'), .5)

    def test_fringe_moments_match_independent_analytic_integrals(self):
        mass, moments = halo_moments(0, 10, .2)
        first = math.log(5)/(.4*10*math.atan(2))
        second = (10-math.atan(2)/.2)/(.2*100*math.atan(2))
        self.assertAlmostEqual(mass, math.atan(2), places=14)
        self.assertAlmostEqual(moments[1]+moments[2], first, places=14)
        self.assertAlmostEqual(moments[2], second, places=14)

    def test_fringe_weights_follow_kernel_and_edge_source(self):
        left = Endpoint(net=self.a, layer='Metal1', fixed={0: 0})
        weights = joint_weights(self.mesh, left, self.right, [0, 0, 10, 10], fringe=(0, 0, .2))
        first = math.log(5)/(.4*10*math.atan(2))
        self.assertAlmostEqual(weights[self.a+'.a', self.b+'.b'], first, places=14)
        self.assertNotIn((self.a+'.b', self.b+'.a'), weights)
        flipped = Endpoint(net=self.a, layer='Metal1', fixed={0: 10})
        reverse = joint_weights(self.mesh, flipped, self.right, [0, 0, 10, 10], fringe=(0, 10, .2))
        self.assertAlmostEqual(reverse[self.a+'.b', self.b+'.a'], first, places=14)

    def test_narrow_distant_and_steep_intervals_remain_positive(self):
        for near, far, mult in ((1000000, 1000001, 2), (0, 1, 10000), (10, 11, 1e-10)):
            with self.subTest(interval=(near, far, mult)):
                mass, moments = halo_moments(near, far, mult)
                self.assertGreater(mass, 0)
                self.assertTrue(all(v > 0 for v in moments))
                self.assertAlmostEqual(moments[0]+2*moments[1]+moments[2], 1)

    def test_line_and_point_support(self):
        ground = Endpoint(singleton='substrate')
        line = joint_weights(self.mesh, self.left, ground, [0, 0, 10, 0])
        self.assertEqual(line, {(self.a+'.a', 'substrate'): .5, (self.a+'.b', 'substrate'): .5})
        point = joint_weights(self.mesh, self.left, ground, [2, 0, 2, 0])
        self.assertEqual(point, {(self.a+'.a', 'substrate'): .8, (self.a+'.b', 'substrate'): .2})

    def test_signed_shield_subtraction_preserves_local_distribution(self):
        ground = Endpoint(singleton='substrate')
        full = joint_weights(self.mesh, self.left, ground, [0, 0, 10, 10])
        shield = joint_weights(self.mesh, self.left, ground, [0, 0, 5, 10])
        actual = {k: 100*full.get(k, 0)-50*shield.get(k, 0) for k in full}
        self.assertAlmostEqual(actual[self.a+'.a', 'substrate'], 12.5)
        self.assertAlmostEqual(actual[self.a+'.b', 'substrate'], 37.5)

    def test_missing_ambiguous_or_unsupported_geometry_fails(self):
        for box, fringe in (([0, 0, 11, 10], None), ([0, 0, 10, 10], (0, 5, .2)),
                            ([0, 0, 10, 10], (0, 0, 0)), ([0, 0, 0, 10], (0, 0, .2))):
            with self.subTest(box=box, fringe=fringe), self.assertRaises(ValueError):
                joint_weights(self.mesh, self.left, self.right, box, fringe=fringe)
        bad = wire(self.a); bad['a'], bad['b'] = bad['b'], bad['a']
        mesh = Mesh([wire(self.a), bad, wire(self.b)], {76: 'Metal1'})
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            joint_weights(mesh, self.left, self.right, [0, 0, 10, 10])


if __name__ == '__main__':
    unittest.main()
