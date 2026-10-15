"""Fault controls for corrected-reference catalog replay and retained inputs."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import check_sky130_delivery_catalog as replay


class DeliveryCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.originals, _ = replay.reconstruct(replay.queue.RetainedReader())

    def delivery(self):
        original = self.originals[0]['rows']
        rows = deepcopy(original)
        for row in rows:
            if row['id'] in replay.BOUNDARY_IDS: row['disposition'] = 'executed-reviewed'
        return rows, original

    def test_complete_inventory_keeps_every_unresolved_record(self):
        rows, original = self.delivery()
        self.assertEqual(replay.check_result(rows, self.catalog, original),
                         {'executed-reviewed':424, 'absent-operand':593, 'unreviewed':441,
                          'standard-cell-wl-exempt':90, 'advisory':8})
        self.assertEqual(len(rows), 1556)

    def test_missing_duplicate_and_reordered_catalog_rejected(self):
        rows, original = self.delivery()
        for mutated in (rows[:-1], [rows[0], *rows[:-1]], [rows[1], rows[0], *rows[2:]]):
            with self.subTest(length=len(mutated)), self.assertRaises(ValueError):
                replay.check_result(mutated, self.catalog, original)

    def test_unresolved_required_rule_cannot_be_promoted_or_waived(self):
        for state in ('executed-reviewed', 'absent-operand', 'advisory', 'standard-cell-wl-exempt'):
            rows, original = self.delivery()
            next(r for r in rows if r['disposition']=='unreviewed')['disposition'] = state
            with self.subTest(state=state), self.assertRaises(ValueError):
                replay.check_result(rows, self.catalog, original)

    def test_previously_executed_check_cannot_disappear(self):
        rows, original = self.delivery()
        next(r for r in rows if r['disposition']=='executed-reviewed' and r['id'] not in replay.BOUNDARY_IDS)['disposition']='unreviewed'
        with self.assertRaises(ValueError): replay.check_result(rows, self.catalog, original)

    def test_each_delivered_boundary_prohibition_must_be_executed(self):
        for key in replay.BOUNDARY_IDS:
            rows, original = self.delivery()
            next(r for r in rows if r['id']==key)['disposition']='absent-operand'
            with self.subTest(key=key), self.assertRaises(ValueError):
                replay.check_result(rows, self.catalog, original)

    def test_changed_catalog_identity_rejected(self):
        for field in ('id', 'rule', 'record'):
            rows, original = self.delivery(); rows[0][field] = 'changed'
            with self.subTest(field=field), self.assertRaises(ValueError):
                replay.check_result(rows, self.catalog, original)

    def test_stage_requires_decisions_and_unique_provenance(self):
        rows, _ = self.delivery()
        with self.assertRaises(ValueError): replay.apply_rows(rows, [], self.catalog, 'missing', {})
        key = next(r['id'] for r in rows if r['disposition']=='unreviewed')
        with self.assertRaises(ValueError):
            replay.apply_rows(rows, [dict(id=key, disposition='absent-operand')], self.catalog, 'repeat', {key:'earlier'})

    def test_stages_cannot_overwrite_prior_checks(self):
        rows, _ = self.delivery()
        key = next(r['id'] for r in rows if r['disposition']=='executed-reviewed')
        with self.assertRaises(ValueError):
            replay.apply_rows(rows, [dict(id=key, disposition='absent-operand')], self.catalog, 'overwrite', {})

    def test_changed_or_missing_retained_bytes_rejected(self):
        with TemporaryDirectory() as td:
            path = Path(td)/'evidence'; path.write_bytes(b'original')
            expected = replay.sha(path)
            self.assertEqual(replay.checked(path, expected), b'original')
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError): replay.checked(path, expected)
            path.unlink()
            with self.assertRaises(FileNotFoundError): replay.checked(path, expected)

    def test_changed_latest_checkpoint_rejected(self):
        class Changed(replay.queue.RetainedReader):
            def read(self, name, expected=None):
                if name == replay.LATEST: expected = '0'*64
                return super().read(name, expected)
        with self.assertRaises(ValueError): replay.reconstruct(Changed())

    def test_missing_or_duplicate_reference_case_rejected(self):
        for cases in ([], [dict(case='counter'), dict(case='counter')]):
            with self.assertRaises(ValueError): replay.pick(dict(cases=cases), 'counter')

    def test_unknown_case_rejected_before_any_execution(self):
        with self.assertRaises(ValueError): replay.build(case='invented')

    def test_changed_source_bytes_rejected(self):
        with TemporaryDirectory() as td:
            folder = Path(td)/'inputs'; replay.fixture.unpack(replay.fixture.BUNDLE, folder)
            source = folder/'sources/docs/rules/errors.csv'
            source.write_bytes(source.read_bytes()+b'\nchanged')
            with self.assertRaises(ValueError): replay.special.source_proof(folder/'sources', self.catalog)


if __name__ == '__main__': unittest.main()
