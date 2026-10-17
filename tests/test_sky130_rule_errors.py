import copy
import json
from pathlib import Path
import unittest

from scripts.sky130_rule_errors import parse, validate


class ErrorInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1]/'docs/qualification/sky130-error-rule-inventory.json'
        cls.record = json.loads(path.read_text(encoding='utf-8'))

    def test_preserves_dummy_rules_missing_from_periphery(self):
        self.assertEqual(validate(self.record)['error_records'], 1556)
        row = next(r for r in self.record['rows'] if r['id'] == 'r1258')
        self.assertEqual(row['rule'], 'fomdmy.2')
        self.assertEqual(row['description'], '0.4 min. spacing/notch of fomDummyDRC')
        self.assertEqual(row['periphery_candidates'], [])

    def test_preserves_multiline_and_duplicate_rule_names(self):
        data = b'ID,Name,Description\nr1,x.1,"first\nline"\nr2,x.1,second\n'
        rows = parse(data)
        self.assertEqual([r['id'] for r in rows], ['r1', 'r2'])
        self.assertEqual(rows[0]['description'], 'first\nline')

    def test_rejects_missing_or_duplicate_records(self):
        for suffix in ('r1,x.1,ok\nr1,x.2,again\n', 'r1,x.1,\n', 'r1,x.1\n', ''):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                parse(('ID,Name,Description\n'+suffix).encode())

    def test_rejects_omission_reordering_and_changed_threshold(self):
        for mutation in ('omit', 'reorder', 'change'):
            record = copy.deepcopy(self.record)
            if mutation == 'omit':
                record['rows'].pop()
            elif mutation == 'reorder':
                record['rows'].reverse()
            else:
                next(r for r in record['rows'] if r['id'] == 'r1258')['description'] = '0.27 min. spacing'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate(record)

    def test_rejects_coverage_inferred_from_catalog_text(self):
        record = copy.deepcopy(self.record)
        record['rows'][0]['coverage'] = 'passed'
        with self.assertRaises(ValueError):
            validate(record)

    def test_rejects_false_summary_or_qualification(self):
        for field, value in (('qualified', True), ('counts', {}), ('source_sha256', '0'*64)):
            record = copy.deepcopy(self.record)
            record[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(record)


if __name__ == '__main__':
    unittest.main()
