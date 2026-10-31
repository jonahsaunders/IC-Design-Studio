import copy
import json
from pathlib import Path
import unittest

from scripts.sky130_rule_inventory import manual_rows, references, validate_unreviewed


ROOT = Path(__file__).resolve().parents[1]


class ManualInventoryTests(unittest.TestCase):
    def test_multiline_description_keeps_one_record(self):
        data = b'Name,Description,Flags,Value,Unit\n(m1.1),"Width\nincluding notches",AL,0.14,um\n'
        rows = manual_rows(data, 'rules.csv')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['record'], 1)
        self.assertEqual(rows[0]['description'], 'Width\nincluding notches')
        self.assertEqual(rows[0]['coverage'], 'unestablished')

    def test_rejects_missing_column(self):
        with self.assertRaises(ValueError):
            manual_rows(b'Name,Description\n(m1.1),Width\n', 'rules.csv')

    def test_rejects_unknown_rule_name(self):
        with self.assertRaises(ValueError):
            manual_rows(b'Name,Description,Flags,Value,Unit\nm1.1,Width,,.14,um\n', 'rules.csv')

    def test_rejects_empty_section(self):
        with self.assertRaises(ValueError):
            manual_rows(b'Name,Description,Flags,Value,Unit\n', 'rules.csv')

    def test_commented_rule_remains_visible(self):
        hits = references('nwell.4', b'# nwell.4 disabled\nnwell.output("nwell.4")\n')
        self.assertEqual([r['comment'] for r in hits], [True, False])

    def test_mentions_do_not_match_other_rules(self):
        hits = references('m1.1', b'm1.1a\nm1.10\nmet1.1\nm1.1\n')
        self.assertEqual([r['line'] for r in hits], [3, 4])

    def test_xml_deck_keeps_code_line_coordinates(self):
        hits = references('poly.1', b'<?xml version="1.0"?><klayout-macro><text># poly.1 omitted</text></klayout-macro>')
        self.assertEqual(hits, [dict(line=1, comment=True, text='# poly.1 omitted')])

    def test_non_numeric_section_requires_manual_review(self):
        self.assertEqual(references('m1.-', b'm1.1 m1.2'), [])


class CapturedInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads((ROOT / 'docs/qualification/sky130-rule-inventory.json').read_text(encoding='utf-8'))

    def test_complete_capture_stays_unqualified(self):
        result = validate_unreviewed(self.record)
        self.assertEqual(result['manual_rows'], 601)
        self.assertFalse(result['qualified'])
        self.assertEqual(result['required_rule_coverage'], 'unestablished')

    def test_cannot_drop_manual_rule(self):
        record = copy.deepcopy(self.record)
        record['rule_rows'].pop()
        with self.assertRaises(ValueError):
            validate_unreviewed(record)

    def test_cannot_promote_text_hit_to_coverage(self):
        record = copy.deepcopy(self.record)
        record['rule_rows'][0]['coverage'] = 'passed'
        with self.assertRaises(ValueError):
            validate_unreviewed(record)

    def test_cannot_claim_process_qualification(self):
        record = copy.deepcopy(self.record)
        record['qualified'] = True
        with self.assertRaises(ValueError):
            validate_unreviewed(record)

    def test_rejects_changed_source_identity(self):
        record = copy.deepcopy(self.record)
        record['rule_rows'][0]['source_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            validate_unreviewed(record)


if __name__ == '__main__':
    unittest.main()
