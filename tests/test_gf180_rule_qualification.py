"""Missing native evidence must not qualify geometry even when reports look clean."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from scripts.qualify_gf180_rules import qualify, read_reports


class NativeRuleEvidenceTests(unittest.TestCase):
    def fixture(self, root, density=1):
        (root / 'drc').mkdir()
        for group, count in (('main', 0), ('antenna', 0), ('density', density)):
            (root / 'drc' / ('layout_' + group + '.lyrdb')).write_text(
                '<report-database><top-cell>counter</top-cell><categories/><items>' +
                '<item><category>density</category></item>' * count + '</items></report-database>')
        (root / 'engine.log').write_text('\n'.join(
            'checks on design ' + group + ' on cell counter:\n' + completion
            for group, completion in (
                ('main', 'native : main DRC Total Run time 1.234 seconds'),
                ('antenna', 'native : Antenna DRC total Run time: 1.234 seconds'),
                ('density', 'native : DRC Total Run time 1.234 seconds'))))

    def test_density_failure_is_explicit_and_clean_requires_zero_exit(self):
        for density in (0, 1):
            with self.subTest(density=density), tempfile.TemporaryDirectory() as td:
                root = Path(td); self.fixture(root, density)
                _, counts = read_reports(root, 'counter', density)
                self.assertEqual(counts, {'main': 0, 'antenna': 0, 'density': density})
                for code in (False, -1, 2, 1 - density):
                    with self.assertRaisesRegex(ValueError, 'exit code'):
                        read_reports(root, 'counter', code)

    def test_missing_duplicate_or_wrong_top_reports_are_rejected(self):
        for fault in ('missing', 'duplicate', 'wrong_top'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as td:
                root = Path(td); self.fixture(root)
                main = root / 'drc/layout_main.lyrdb'
                if fault == 'missing': main.unlink()
                elif fault == 'duplicate': (root / 'drc/duplicate_main.lyrdb').write_bytes(main.read_bytes())
                else: main.write_text(main.read_text().replace('counter', 'another'))
                with self.assertRaises(ValueError): read_reports(root, 'counter', 1)

    def test_partial_run_and_engine_exception_cannot_pass_with_empty_reports(self):
        for log in ('main DRC Total Run time 1 seconds',
                    'main DRC Total Run time 1 seconds\nTraceback (most recent call last)',
                    'ERROR: native rule aborted'):
            with self.subTest(log=log), tempfile.TemporaryDirectory() as td:
                root = Path(td); self.fixture(root, 0); (root / 'engine.log').write_text(log)
                with self.assertRaises(ValueError): read_reports(root, 'counter', 0)

    def test_main_completion_cannot_stand_in_for_density_completion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); self.fixture(root, 0)
            log = root / 'engine.log'
            log.write_text(log.read_text().replace('native : DRC Total Run time 1.234 seconds', ''))
            with self.assertRaisesRegex(ValueError, 'density'):
                read_reports(root, 'counter', 0)

    def test_changed_saved_inputs_or_missing_identity_stop_before_native_execution(self):
        from tests.test_digital_macro import DigitalMacroTests
        for fault in ('top', 'variant', 'missing_identity'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as td:
                root = Path(td); job, result = DigitalMacroTests().fixture(root)
                if fault == 'top': job['project']['digital']['top'] = 'changed'
                elif fault == 'variant': job['project']['digital']['platform']['orfs'] = {'variables': {'KVALUE': '11'}}
                else: result['digital_result'].pop('input_key')
                (root / 'input.json').write_text(json.dumps(job))
                (root / 'result.json').write_text(json.dumps(result))
                with patch('scripts.qualify_gf180_rules.verify_deck', return_value={}), \
                        patch('scripts.qualify_gf180_rules.subprocess.run') as native:
                    with self.assertRaises(ValueError):
                        qualify(root, root / 'unused-deck', root / 'evidence', 'C', 'geometry', 'python', 'klayout')
                    native.assert_not_called()
                self.assertEqual(json.loads((root / 'evidence/report.json').read_text())['status'], 'failed')


if __name__ == '__main__': unittest.main()
