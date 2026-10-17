"""Keep recommended window parameters separate from required fill checks."""
from copy import deepcopy
import json
import unittest

from scripts import sky130_density_rule_scope as scope


class DensityScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads((scope.ROOT / scope.geometry.previous.PERIPHERY).read_bytes())
        checkpoint = json.loads((scope.ROOT / scope.geometry.previous.CHECKPOINT).read_bytes())
        cls.reviews = json.loads((scope.ROOT / checkpoint['data']['path']).read_bytes())
        cls.bindings = scope.bindings(cls.inventory)

    def test_only_eight_exact_recommended_parent_parameters_are_bound(self):
        expected = {f'm{metal}.pd.{suffix}' for metal in range(1, 5) for suffix in ('2a', '2b')}
        self.assertEqual({row['rule'] for row in self.bindings.values()}, expected)
        self.assertEqual(len(self.bindings), 8)
        self.assertTrue(all(row['disposition'] == 'advisory' for row in self.bindings.values()))
        self.assertTrue(all(row['parameter']['unit'] == '' for row in self.bindings.values() if row['rule'].endswith('2b')))

    def test_changed_parent_flags_or_child_semantics_cannot_inherit_scope(self):
        for target, field, value in (
            ('m1.pd.1', 'flags', ['RC', 'AL']),
            ('m2.pd.2a', 'description', 'Independent required density window'),
            ('m3.pd.2b', 'unit', 'µm'),
            ('m4.pd.2a', 'value', '600'),
        ):
            with self.subTest(target=target):
                inventory = deepcopy(self.inventory)
                next(row for row in inventory['rule_rows'] if row['rule'] == target)[field] = value
                with self.assertRaisesRegex(ValueError, 'captured source'):
                    scope.bindings(inventory)

    def test_required_rc_fill_and_every_unrelated_row_remain_byte_equal(self):
        for review in self.reviews:
            original = deepcopy(review['rows'])
            changed = scope.apply(original, self.bindings)
            for before, after in zip(original, changed):
                if before['id'] in self.bindings:
                    self.assertEqual(after['disposition'], 'advisory')
                    self.assertNotIn('execution', after)
                else:
                    self.assertEqual(before, after)
            for metal in range(1, 5):
                row = next(row for row in changed if row['rule'] == f'm{metal}.-')
                self.assertEqual(row['disposition'], 'absent-operand')
                self.assertTrue(row['witnesses'])
            self.assertEqual(original, review['rows'])

    def test_nonadvisory_parent_or_already_reviewed_child_is_rejected(self):
        child_id, binding = next(iter(self.bindings.items()))
        for source_id, disposition in ((binding['parent'], 'execution-review-required'),
                                       (child_id, 'executed-reviewed')):
            rows = deepcopy(self.reviews[0]['rows'])
            next(row for row in rows if row['id'] == source_id)['disposition'] = disposition
            with self.assertRaisesRegex(ValueError, 'unrelated coverage'):
                scope.apply(rows, self.bindings)

    def test_updated_counts_never_promote_recommendations_to_execution(self):
        report = scope.build()
        for case in report['cases']:
            self.assertEqual(case['counts']['execution-review-required'], 14)
            self.assertEqual(case['counts']['advisory'], 36)
            self.assertEqual(case['counts']['executed-reviewed'], 135)
            self.assertEqual(case['counts']['definition-required'], 1)
            self.assertEqual(case['error_counts']['unreviewed'], 1161)
            for row in case['rows']:
                if 'execution_reconciliation' in row:
                    self.assertEqual(row['reason'], row['execution_reconciliation']['reason'])
        self.assertFalse(report['chunk_complete'])
        self.assertFalse(report['qualified'])


if __name__ == '__main__':
    unittest.main()
