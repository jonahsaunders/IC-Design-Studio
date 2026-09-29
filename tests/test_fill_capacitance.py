import math
from pathlib import Path
import tempfile
import unittest

from icstudio.fill_capacitance import reduce_floating, from_ext


class FloatingFillTests(unittest.TestCase):
    def test_single_floating_conductor_adds_series_capacitance(self):
        result = reduce_floating({'SIGNAL': 2e-15, 'FILL': 3e-15}, {('SIGNAL', 'FILL'): 6e-15}, ['FILL'])
        self.assertAlmostEqual(result['ground_f']['SIGNAL'] / 1e-15, 4.)
        self.assertEqual(result['coupling_f'], [])
        self.assertEqual(result['components'][0]['status'], 'reduced')

    def test_fill_to_fill_path_and_ground_are_retained(self):
        result = reduce_floating({'S': 0., 'F1': 0., 'F2': 3e-15},
                                 {('S', 'F1'): 6e-15, ('F1', 'F2'): 3e-15}, ['F1', 'F2'])
        self.assertAlmostEqual(result['ground_f']['S'] / 1e-15, 1.2)
        self.assertLess(result['maximum_normalized_solve_residual'], 1e-12)

    def test_floating_bridge_creates_mutual_c_without_grounding_fill(self):
        result = reduce_floating({'A': 1e-15, 'B': 2e-15, 'F': 0.},
                                 {('A', 'F'): 12e-15, ('B', 'F'): 6e-15, ('A', 'B'): .5e-15}, ['F'])
        self.assertAlmostEqual(result['ground_f']['A'] / 1e-15, 1.)
        self.assertAlmostEqual(result['ground_f']['B'] / 1e-15, 2.)
        self.assertEqual([(v['a'], v['b']) for v in result['coupling_f']], [('A', 'B')])
        self.assertAlmostEqual(result['coupling_f'][0]['value_f'] / 1e-15, 4.5)

    def test_disconnected_fill_is_reported_without_a_singular_solve(self):
        result = reduce_floating({'A': 1., 'F1': 0., 'F2': 0.}, {('F1', 'F2'): 10.}, ['F1', 'F2'])
        self.assertEqual(result['ground_f'], {'A': 1.})
        self.assertEqual(result['components'][0]['status'], 'unobservable')

    def test_malformed_or_over_budget_matrices_fail_closed(self):
        for ground, caps, floats in (({'A': math.nan}, {}, []), ({'A': -1.}, {}, []),
                                    ({'A': 1.}, {('A', 'missing'): 1.}, []),
                                    ({'A': 1.}, {('A', 'A'): 1.}, []),
                                    ({'A': 1.}, {}, ['missing'])):
            with self.subTest(ground=ground, caps=caps), self.assertRaises(ValueError):
                reduce_floating(ground, caps, floats)
        with self.assertRaisesRegex(ValueError, 'budget'):
            reduce_floating({'S': 0., 'F1': 0., 'F2': 3.},
                            {('S', 'F1'): 6., ('F1', 'F2'): 3.}, ['F1', 'F2'], max_component=1)

    def test_ext_scale_and_explicit_substrate_coupling_are_preserved(self):
        content = ('scale 1000 2 100\nnode "SIGNAL" 0 1000 0 0 m1\n'
                   'node "FILL" 0 1000 10 0 m1\nsubstrate "VSS" 0 0 0 0 space\n'
                   'cap "SIGNAL" "FILL" 3000\ncap "FILL" "VSS" 500\n')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'top.ext'; path.write_text(content)
            result = from_ext(path, ['FILL'])
            self.assertAlmostEqual(result['ground_f']['SIGNAL'] / 1e-15, 4.)
            self.assertEqual(result['substrate_reference'], 'VSS')
            self.assertEqual(path.read_text(), content)
            self.assertEqual(len(result['source_sha256']), 64)
            path.write_text(content+'port "FILL" 1 10 0 10 0 m1\n')
            with self.assertRaisesRegex(ValueError, 'external port'):
                from_ext(path, ['FILL'])
            path.write_text(content+'fet legacy 0 0 1 1 1 1 "VSS" "SIGNAL" 1 0 "FILL" 1 0 "VSS" 1 0\n')
            with self.assertRaisesRegex(ValueError, 'modern device'):
                from_ext(path, ['FILL'])
            path.write_text(content+'node "FILL" 0 5000 10 0 m1\n')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                from_ext(path, ['FILL'])
            path.write_text(content+'cap "FILL" "VSS" -1\n')
            with self.assertRaisesRegex(ValueError, 'nonnegative'):
                from_ext(path, ['FILL'])


if __name__ == '__main__':
    unittest.main()
