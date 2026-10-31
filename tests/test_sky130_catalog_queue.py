import copy
import unittest

from scripts import sky130_catalog_queue as q


class CatalogQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = q.RetainedReader()
        cls.catalog, cls.cases = q.reconstruct(cls.reader)

    def test_every_reference_reconstructs_without_coverage_promotion(self):
        for case in self.cases:
            self.assertEqual(case['counts'], {'executed-reviewed': 356, 'absent-operand': 320, 'unreviewed': 880})
            batches = q.partition([r for r in case['rows'] if r['disposition'] == 'unreviewed'])
            queued = [r for b in batches for r in b['records']]
            self.assertEqual(len(queued), 880)
            self.assertEqual(len({r['id'] for r in queued}), 880)
            self.assertEqual({r['disposition'] for r in queued}, {'unreviewed'})
        self.assertEqual(q.build()['new_coverage_decisions'], 0)

    def test_missing_or_overlapping_batch_is_rejected(self):
        rows = [r for r in self.cases[0]['rows'] if r['disposition'] == 'unreviewed']
        with self.assertRaisesRegex(ValueError, 'Unassigned'):
            q.partition(rows, q.BATCHES[1:])
        extra = ('overlap', 'Ambiguous assignment', ((0,0),), (), 'Invalid')
        with self.assertRaisesRegex(ValueError, 'multiply assigned'):
            q.partition(rows, q.BATCHES + (extra,))

    def test_resolved_and_duplicate_records_cannot_enter_queue(self):
        rows = self.cases[0]['rows']
        with self.assertRaisesRegex(ValueError, 'unreviewed record exactly once'):
            q.partition(rows)
        open_row = next(r for r in rows if r['disposition'] == 'unreviewed')
        with self.assertRaisesRegex(ValueError, 'unreviewed record exactly once'):
            q.partition([open_row, open_row])

    def test_decision_cannot_rewrite_source_identity_or_overlap(self):
        rows = self.cases[0]['rows']
        open_row = next(r for r in rows if r['disposition'] == 'unreviewed')
        decision = dict(id=open_row['id'], disposition='absent-operand')
        with self.assertRaisesRegex(ValueError, 'changed catalog record'):
            q.apply_decisions(rows, [dict(decision, rule='unrelated')], self.catalog)
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            q.apply_decisions(rows, [decision, decision], self.catalog)
        self.assertEqual(open_row['disposition'], 'unreviewed')

    def test_stale_input_and_path_escape_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Changed retained input'):
            self.reader.read(q.CHECKPOINT, '0' * 64)
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.reader.read('../outside.json')

    def test_missing_reordered_or_duplicated_rows_are_rejected(self):
        original = self.cases[0]['rows']
        for rows in (original[:-1], list(reversed(original)), [original[1], *original[1:]]):
            with self.assertRaisesRegex(ValueError, 'catalog record'):
                q.validate_rows(rows, self.catalog)
        changed = copy.deepcopy(original)
        changed[0]['record'] += 1
        with self.assertRaisesRegex(ValueError, 'catalog record'):
            q.validate_rows(changed, self.catalog)


if __name__ == '__main__':
    unittest.main()
