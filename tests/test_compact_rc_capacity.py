"""Explicit RC capacity stays bounded and survives export authentication."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio.compact_rc import build, records, audit, source_budget, CURRENT_SUM, ANCHORED_CURRENT_SUM, SERIES_VOLTAGE
from icstudio.magic_rc import normalize, finalize, contract, MAX_CAPACITORS
from icstudio.rc_islands import prune
from tests.test_magic_rc import ORIGINAL, RESISTANCE


class CompactCapacityTests(unittest.TestCase):
    def test_explicit_source_budget_preserves_both_encodings_and_conservation(self):
        ground = {'A': 1., 'VSS': 0.}
        weights = {'A': {'A': 1.}, 'VSS': {'VSS': 1.}}
        for encoding, needed in ((CURRENT_SUM, 6), (ANCHORED_CURRENT_SUM, 6), (SERIES_VOLTAGE, 4)):
            with self.subTest(encoding=encoding), patch('icstudio.compact_rc.MAX_SOURCES', 3):
                with self.assertRaisesRegex(ValueError, f'requires 2 capacitors and {needed} sources'):
                    build(ground, {}, weights, 'VSS', physical_nodes=weights, max_capacitors=2, encoding=encoding)
                model = build(ground, {}, weights, 'VSS', physical_nodes=weights, max_capacitors=2,
                              encoding=encoding, max_sources=needed)
                self.assertEqual(model['max_sources'], needed)
                with self.assertRaisesRegex(ValueError, 'budget'): records(model['text'], weights)
                self.assertEqual(len(records(model['text'], weights, max_sources=needed)[1]), 2)
                self.assertEqual(audit(model['text'], {'A': 'A', 'VSS': 'VSS'}, ground, {}, 'VSS',
                                       max_sources=needed)['status'], 'passed')
                with self.assertRaisesRegex(ValueError, 'budget'):
                    audit(model['text'], {'A': 'A', 'VSS': 'VSS'}, ground, {}, 'VSS', max_sources=needed-1)

    def test_capacity_is_recorded_and_used_in_finalization_contraction_and_islands(self):
        with tempfile.TemporaryDirectory() as tmp, patch('icstudio.compact_rc.MAX_SOURCES', 1):
            root = Path(tmp)
            (root / 'top.ext').write_text(ORIGINAL)
            (root / 'top.res.ext').write_text(RESISTANCE)
            report = normalize(root, 'top', coupling_representation='compact', max_sources=100)
            self.assertEqual(report['compact_model']['max_sources'], 100)
            source = '.subckt top IN VSS\nR0 N.n0 N.t0 10\nR1 IN IN.t0 20\n.ends\n'
            (root / 'extracted.spice').write_text(source, newline='\n')
            report = finalize(root, 'top')
            text = (root / 'extracted.spice').read_bytes().decode('utf-8')
            self.assertEqual(contract(text, report), '.subckt top IN VSS\n.ends\n')
            kept = prune(root / 'extracted.spice', root / 'electrical.spice', normalization=report)
            self.assertFalse(kept['removed_resistors'])
            for invalid in (1, 1_000_001):
                report['compact_model']['max_sources'] = invalid
                with self.assertRaisesRegex(ValueError, 'budget'): contract(text, report)

    def test_invalid_budgets_reject_before_files_are_read_or_written(self):
        for value in (False, True, 0, -1, 1.5, '100', 1_000_001):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'budget'):
                source_budget(value)
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'budget'):
                normalize('does-not-exist', 'top', max_sources=value)
        for value in (False, 0, MAX_CAPACITORS + 1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'budget'):
                normalize('does-not-exist', 'top', max_capacitors=value)

    def test_excessive_serialized_capacity_is_rejected_before_export_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'top.ext').write_text(ORIGINAL)
            (root / 'top.res.ext').write_text(RESISTANCE)
            report = normalize(root, 'top', coupling_representation='compact')
            report['compact_model']['max_sources'] = 1_000_001
            (root / 'rc-normalization.json').write_text(json.dumps(report))
            source = '.subckt top IN VSS\nR0 N.n0 N.t0 10\nR1 IN IN.t0 20\n.ends\n'
            (root / 'extracted.spice').write_text(source, newline='\n')
            with self.assertRaisesRegex(ValueError, 'budget'): finalize(root, 'top')
            self.assertEqual((root / 'extracted.spice').read_text(), source)
            self.assertFalse((root / 'raw-export.spice').exists())


if __name__ == '__main__':
    unittest.main()
