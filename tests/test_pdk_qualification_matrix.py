"""Coverage failures must not silently shrink the public qualification target."""
import copy
import unittest

from scripts.check_pdk_qualification import MATRIX, read, validate


class QualificationMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = read(MATRIX)

    def test_complete_inventory_is_bookkeeping_not_qualification(self):
        report = validate(self.matrix)
        self.assertEqual(report['status'], 'matrix_consistent')
        self.assertEqual(report['process_qualification'], 'unqualified')
        self.assertEqual(report['device_entries'], 255)

    def test_omitted_unavailable_device_is_rejected(self):
        matrix = copy.deepcopy(self.matrix)
        del matrix['device_requirements']['ihp-sg13g2']['sg13g2_pr/inductor.sym']
        with self.assertRaisesRegex(ValueError, 'Device omitted'):
            validate(matrix)

    def test_variant_c_evidence_cannot_remove_variant_d_requirement(self):
        matrix = copy.deepcopy(self.matrix)
        del matrix['requirements']['gf180mcuD:digital-profile']
        with self.assertRaisesRegex(ValueError, 'Requirement coverage'):
            validate(matrix)

    def test_stale_manifest_and_partial_device_test_are_rejected(self):
        matrix = copy.deepcopy(self.matrix)
        matrix['inventory']['gf180mcuC']['revision'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'inventory is stale'):
            validate(matrix)
        matrix = copy.deepcopy(self.matrix)
        matrix['device_requirements']['sky130A']['sky130_fd_pr/nfet_01v8.sym']['tests'].remove('device-physical')
        with self.assertRaisesRegex(ValueError, 'Incomplete device coverage'):
            validate(matrix)

    def test_smoke_result_cannot_be_promoted_to_qualified(self):
        matrix = copy.deepcopy(self.matrix)
        matrix['requirements']['sky130A:device-simulation']['status'] = 'passed'
        with self.assertRaisesRegex(ValueError, 'Unsupported qualification claim'):
            validate(matrix)

    def test_unavailable_model_cannot_be_promoted(self):
        matrix = copy.deepcopy(self.matrix)
        matrix['device_requirements']['ihp-sg13g2']['sg13g2_pr/inductor.sym']['status'] = 'partial'
        with self.assertRaisesRegex(ValueError, 'Unavailable device promoted'):
            validate(matrix)

    def test_changed_evidence_and_empty_acceptance_contract_are_rejected(self):
        matrix = copy.deepcopy(self.matrix)
        matrix['evidence']['gds-diagnostics']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Evidence changed'):
            validate(matrix)
        matrix = copy.deepcopy(self.matrix)
        matrix['tests']['ihp-rf']['expected_result'] = ''
        with self.assertRaisesRegex(ValueError, 'Missing test contract'):
            validate(matrix)


if __name__ == '__main__':
    unittest.main()
