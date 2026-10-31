"""Reject missing controls, hidden negative C and changes to the physical input."""
import copy
import unittest

from scripts.ihp_shielding_audit import compare


def capture(corrected):
    groups = []
    for metal in (1, 2, 3):
        for rotation in (0, 90, 180, 270):
            cases = []
            for index, state in enumerate(('separate', 'upper-pair', 'all')):
                ground = 60. if corrected or index < 2 else -2.
                cases.append(dict(state=state, connected_regions=3-index,
                                  local_geometry_unchanged=True, gds_sha256='a'*64,
                                  terms_af={'initial-edge': 156., 'ground-side-halo': ground-156.},
                                  local_fringe_ground_af=ground))
            groups.append(dict(lower_metal=metal, upper_metal=metal+2,
                               rotation_degrees=rotation, cases=cases))
    return dict(groups=groups)


class ShieldingAuditTests(unittest.TestCase):
    def setUp(self):
        self.before, self.after = capture(False), capture(True)

    def test_complete_native_correction(self):
        result = compare(self.before, self.after)
        self.assertEqual(result['local_controls'], 12)
        self.assertEqual(result['maximum_corrected_spread_af'], 0)

    def test_missing_and_duplicate_orientations_fail(self):
        self.after['groups'].pop()
        with self.assertRaisesRegex(ValueError, 'coverage'):
            compare(self.before, self.after)
        self.after['groups'].append(copy.deepcopy(self.after['groups'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            compare(self.before, self.after)

    def test_clamping_reported_negative_value_fails(self):
        self.after = capture(False)
        self.after['groups'][0]['cases'][2]['local_fringe_ground_af'] = 0
        with self.assertRaisesRegex(ValueError, 'signed native terms'):
            compare(self.before, self.after)

    def test_unfixed_signed_native_terms_fail(self):
        with self.assertRaisesRegex(ValueError, 'negative or depends'):
            compare(self.before, capture(False))

    def test_changed_mask_or_initial_ground_fails(self):
        self.after['groups'][0]['cases'][0]['gds_sha256'] = 'b'*64
        with self.assertRaisesRegex(ValueError, 'changed geometry'):
            compare(self.before, self.after)

    def test_missing_physical_or_connectivity_verification_fails(self):
        self.after['groups'][0]['cases'][2]['connected_regions'] = 2
        with self.assertRaisesRegex(ValueError, 'connectivity'):
            compare(self.before, self.after)

    def test_nan_native_term_fails(self):
        self.after['groups'][0]['cases'][2]['terms_af']['ground-side-halo'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'invalid native'):
            compare(self.before, self.after)

    def test_an_unexercised_defect_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, 'not exercised'):
            compare(capture(True), self.after)


if __name__ == '__main__':
    unittest.main()
