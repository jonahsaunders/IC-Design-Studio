"""The independent runtime checker must reject plausible but incorrect results."""
import copy
import math
import unittest
from scripts.verify_ngspice_diode_sequences import validate, deck


class DiodeSequenceValidationTests(unittest.TestCase):
    def ac(self):
        variables = ['frequency', 'v(n1)', 'v(n3)', 'i(v1)', 'i(v3)']
        # Fixed analytical zero-bias values for the declared 4-area/8-edge model.
        rows = [[f, 1, 1, -1.082547451911472e-12-2j*math.pi*f*12e-12,
                 -3.247642355734415e-12-2j*math.pi*f*36e-12]
                for f in (1000*10**(i/5) for i in range(16))]
        return variables, rows, True

    def test_accepts_complete_analytical_sweep(self):
        self.assertEqual(validate(*self.ac(), 'ac1')['status'], 'PASS')

    def test_rejects_geometry_collapse_and_missing_multiplicity(self):
        for factor in (1e-6, 1e-12, 1/3):
            v, rows, c = self.ac()
            for row in rows:
                row[4] *= factor
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                validate(v, rows, c, 'ac2')

    def test_rejects_stale_results_after_explicit_geometry_change(self):
        for name in ('area', 'perimeter', 'multiplicity'):
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                validate(*self.ac(), name)

    def test_rejects_missing_sidewall_contribution(self):
        v, rows, c = self.ac()
        for row in rows:
            row[3] = complex(row[3].real, row[3].imag * 2/3)
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            validate(v, rows, c, 'ac1')

    def test_rejects_nonfinite_truncated_wrong_axis_and_wrong_stimulus(self):
        cases = []
        v, rows, c = self.ac()
        cases.append((v, rows[:-1], c))
        cases.append((v, rows, False))
        cases.append((['time', *v[1:]], rows, c))
        cases.append((v[:-1], rows, c))
        for column, value in ((0, 1001), (1, 0), (3, complex(float('nan'), 0)), (4, complex(0, float('inf')))):
            bad = copy.deepcopy(rows); bad[0][column] = value
            cases.append((v, bad, c))
        for case in cases:
            with self.assertRaises(ValueError):
                validate(*case, 'ac1')

    def test_rejects_nonzero_zero_bias_current(self):
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            validate(['v(n1)', 'v(n3)', 'i(v1)', 'i(v3)'], [[0, 0, 1e-9, 0]], False, 'op')

    def test_sequence_keeps_analysis_history_and_explicit_alterations(self):
        for mode in ('scales-explicit-area', 'unscaled-explicit-area'):
            text = deck(mode)
            self.assertNotIn('reset', text.lower())
            self.assertEqual(text.count('ac dec '), 6)
            self.assertIn('alter D3 m=2', text)
        with self.assertRaises(ValueError):
            deck('unknown')


if __name__ == '__main__':
    unittest.main()
