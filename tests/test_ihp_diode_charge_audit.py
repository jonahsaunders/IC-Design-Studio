from pathlib import Path
import tempfile
import unittest

from scripts.ihp_diode_charge_audit import audit


class DiodeChargeAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.curve = Path(temp.name)/'curve.txt'; self.log = Path(temp.name)/'engine.log'
        self.log.write_text('No. of Data Rows : 3\n')
        self.header = 'v-sweep i(VBIAS) @dtest[charge] @dtest[cd] @dtest[vd]\n'
        self.good = self.header+'0.01 -1e-14 -2e-17 2e-15 -0.01\n0.02 -2e-14 -4e-17 2e-15 -0.02\n0.03 -3e-14 -6e-17 2e-15 -0.03\n'
        self.curve.write_text(self.good)

    def check(self):
        return audit(self.curve, self.log, .01, .03)

    def test_linear_charge_is_consistent_but_not_qualified(self):
        result = self.check()
        self.assertEqual(result['status'], 'charge-consistency-pass')
        self.assertLess(result['relative_error'], 1e-14)
        self.assertFalse(result['qualified'])

    def test_charge_jump_fails_despite_finite_positive_capacitance(self):
        self.curve.write_text(self.good.replace('-4e-17', '-8e-17').replace('-6e-17', '-1e-16'))
        self.assertEqual(self.check()['status'], 'charge-consistency-failed')

    def test_final_scalar_repeated_as_a_vector_is_rejected(self):
        self.curve.write_text(self.good.replace('-0.01', '-0.03').replace('-0.02', '-0.03'))
        with self.assertRaisesRegex(ValueError, 'advance'): self.check()

    def test_opposite_interior_errors_cannot_cancel_at_the_endpoints(self):
        self.curve.write_text(self.good.replace('-4e-17', '-5e-17'))
        result = self.check()
        self.assertLess(result['relative_error'], 1e-14)
        self.assertGreater(result['maximum_cumulative_relative_error'], .2)
        self.assertEqual(result['status'], 'charge-consistency-failed')

    def test_missing_interval_aborted_and_wrong_vectors_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'declared interval'): audit(self.curve, self.log, .01, .04)
        self.log.write_text('dc simulation(s) aborted\n')
        with self.assertRaisesRegex(ValueError, 'complete'): self.check()
        self.log.write_text('No. of Data Rows : 3\n')
        self.curve.write_text(self.good.replace('@dtest[cd]', '@dtest[gd]'))
        with self.assertRaisesRegex(ValueError, 'vectors'): self.check()

    def test_nonfinite_negative_or_nonmonotone_data_are_rejected(self):
        for text in (self.good.replace('2e-15', 'nan', 1), self.good.replace('2e-15', '-2e-15', 1),
                     self.good.replace('0.02 -2e-14', '0.01 -2e-14')):
            self.curve.write_text(text)
            with self.assertRaises(ValueError): self.check()
