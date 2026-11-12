import copy
from pathlib import Path
import tempfile
import unittest

from scripts.ihp_spatial_mesh import Mesh, resolve


def region(box=(0, 0, 10, 4), a=None, b=None, axis=1):
    return dict(net='NET000002', type=76, split=0, axis=axis, box=list(box),
                a={'NET000002.a': 1.} if a is None else a,
                b={'NET000002.b': 1.} if b is None else b)


class MeshInterpolationTests(unittest.TestCase):
    def mesh(self, regions):
        return Mesh(regions, {76: 'Metal1'})

    def test_local_position_and_full_wire_integrals(self):
        mesh = self.mesh([region()])
        self.assertEqual(mesh.average('NET000002', 'Metal1', [0, 0, 10, 4]),
                         {'NET000002.a': .5, 'NET000002.b': .5})
        for support in ([0, 0, 2, 4], [0, 0, 2, 0], [1, 0, 1, 0]):
            with self.subTest(support=support):
                weights = mesh.average('NET000002', 'Metal1', support)
                self.assertAlmostEqual(weights['NET000002.a'], .9)
                self.assertAlmostEqual(weights['NET000002.b'], .1)

    def test_joined_partitions_preserve_each_resistor_endpoint(self):
        first = region(); second = region((10, 0, 20, 4), {'NET000002.b': 1.}, {'NET000002.c': 1.})
        weights = self.mesh([first, second]).average('NET000002', 'Metal1', [0, 0, 20, 4])
        self.assertEqual(weights, {'NET000002.a': .25, 'NET000002.b': .5, 'NET000002.c': .25})
        self.assertEqual(self.mesh([first, second]).average('NET000002', 'Metal1', [10, 0, 10, 0]),
                         {'NET000002.b': 1.})

    def test_duplicate_equal_support_is_not_double_counted(self):
        first = region(); partial = region((0, 0, 5, 4), b={'NET000002.a': .5, 'NET000002.b': .5})
        self.assertEqual(self.mesh([first, partial]).average('NET000002', 'Metal1', [0, 0, 10, 4]),
                         {'NET000002.a': .5, 'NET000002.b': .5})

    def test_equal_midpoints_do_not_hide_conflicting_slopes(self):
        first = region(); reversed_basis = region(a=first['b'], b=first['a'])
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            self.mesh([first, reversed_basis]).average('NET000002', 'Metal1', [0, 0, 10, 4])

    def test_gaps_outside_support_and_wrong_ownership_fail(self):
        mesh = self.mesh([region()])
        for net, layer, box in [('NET000003', 'Metal1', [0, 0, 1, 1]),
                                 ('NET000002', 'Metal2', [0, 0, 1, 1]),
                                 ('NET000002', 'Metal1', [0, 0, 11, 4]),
                                 ('NET000002', 'Metal1', [5, 5, 5, 5])]:
            with self.subTest(box=box, net=net, layer=layer), self.assertRaises(ValueError):
                mesh.average(net, layer, box)
        with self.assertRaisesRegex(ValueError, 'Gap'):
            self.mesh([region((0, 0, 4, 4)), region((6, 0, 10, 4))]).average(
                'NET000002', 'Metal1', [0, 0, 10, 4])

    def test_unsupported_mesh_and_weight_corruption_fail(self):
        cases = [dict(split=1), dict(axis=3), dict(type=999), dict(box=[0, 0, 0, 4]),
                 dict(a={'NET000002.a': float('nan')}), dict(a={'NET000002.a': -1.}),
                 dict(a={'NET000002.a': .9}), dict(a={'NET000003.a': 1.}), dict(axis=0)]
        for changed in cases:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.mesh([{**region(), **changed}])

    def test_signed_native_extensions_require_equal_positive_coverage(self):
        constant = region(a={'NET000002.a': 1.}, b={'NET000002.a': 1.})
        negative = {**constant, 'sign': -1}
        self.assertEqual(self.mesh([constant, constant, negative]).average(
            'NET000002', 'Metal1', [0, 0, 10, 4]), {'NET000002.a': 1.})
        for regions in ([constant, negative], [negative], [region(), negative]):
            with self.subTest(regions=regions), self.assertRaises(ValueError):
                self.mesh(regions).average('NET000002', 'Metal1', [0, 0, 10, 4])


class NativeMeshLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.trace = Path(self.temp.name)/'mesh.tsv'; self.ext = Path(self.temp.name)/'r.ext'
        self.ext.write_text('rnode "NET000002.a" 0 1 0 0 m1\n'
                            'rnode "NET000002.b" 0 1 10 0 m1\n')
        self.rows = [self.event('init', 'p'), self.event('init', 'q'), self.event('init', 'r'),
                     self.event('area', 'p', 'p', typ=76, box=(0, 0, 10, 4)),
                     'transfer\tNET000002\tp\tq\tr\t0.25\t0.75\n',
                     self.event('name', 'q', name='NET000002.a'),
                     self.event('name', 'r', name='NET000002.b')]

    @staticmethod
    def event(kind, a, b='nil', name='@none', typ=0, box=(0, 0, 0, 0)):
        return '\t'.join(map(str, [kind, 'NET000002', a, b, name, typ, 0, 0, *box]))+'\n'

    def run_rows(self, rows=None):
        self.trace.write_text(''.join(self.rows if rows is None else rows))
        return resolve(self.trace, self.ext)

    def test_series_transfer_reaches_actual_named_nodes(self):
        result = self.run_rows()
        self.assertEqual(result['regions'][0]['a'], {'NET000002.a': .25, 'NET000002.b': .75})
        self.assertFalse(result['qualified'])

    def test_native_roundoff_is_retained_separately_from_unit_partition(self):
        self.rows[4] = self.rows[4].replace('0.25\t0.75', '0.25000001\t0.75000003')
        result = self.run_rows(); region = result['regions'][0]
        self.assertGreater(result['maximum_composed_unity_residue'], 0)
        self.assertNotEqual(sum(region['a_native'].values()), 1.)
        self.assertAlmostEqual(sum(region['a'].values()), 1.)

    def test_reused_address_does_not_rebind_old_region(self):
        self.rows.extend([self.event('init', 'p'), self.event('area', 'p', 'p', typ=76, box=(20, 0, 30, 4)),
                          self.event('move', 'q', 'p')])
        # Moving into a surviving named node is valid; the old p generation is
        # already eliminated and must keep its earlier 1:3 transfer.
        result = self.run_rows()
        self.assertEqual(result['regions'][0]['a']['NET000002.b'], .75)
        self.assertEqual(result['regions'][1]['a'], {'NET000002.a': 1.})

    def test_missing_transfers_names_and_malformed_events_fail(self):
        bad = [self.rows[:4]+self.rows[5:], self.rows[:-1], self.rows+['junk\n'],
               [line.replace('p\tq\tr', 'p\tp\tr') for line in self.rows],
               [line.replace('0.25\t0.75', '0.25\t0.76') for line in self.rows],
               [line.replace('0.25\t0.75', 'nan\t0.75') for line in self.rows]]
        for rows in bad:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.run_rows(rows)

    def test_cross_net_endpoint_and_final_node_reuse_fail(self):
        for rows in ([line.replace('NET000002.a', 'NET000003.a') for line in self.rows],
                     self.rows+[self.event('merge', 'r', 'q')]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.run_rows(rows)

    def test_native_auto_name_marker_is_removed_exactly_once(self):
        self.rows = [line.replace('NET000002', 'a_1_2#') for line in self.rows]
        self.rows = [line.replace('a_1_2#.a', 'a_1_2.a').replace('a_1_2#.b', 'a_1_2.b') for line in self.rows]
        self.ext.write_text(self.ext.read_text().replace('NET000002', 'a_1_2'))
        self.assertEqual(self.run_rows()['regions'][0]['a']['a_1_2.a'], .25)

    def test_signed_tail_is_recorded_but_nonconstant_inversion_rejected(self):
        self.rows[3] = self.rows[3].replace('76\t0\t0\t0\t0\t10\t4', '76\t0\t1\t10\t0\t0\t4')
        result = self.run_rows()
        self.assertEqual(result['signed_extension_regions'], 1)
        self.assertEqual(result['regions'][0]['box'], [0, 0, 10, 4])
        self.rows[3] = self.rows[3].replace('p\tp', 'p\tq')
        with self.assertRaisesRegex(ValueError, 'inverted'):
            self.run_rows()
