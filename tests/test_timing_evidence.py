"""Timing verdicts must account for all required evidence, not just sampled paths."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from icstudio.digital_reports import timing_report


class TimingEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.write('timing_paths.tsv', 'setup\ta\tb\t2\ta|b\nhold\ta\tb\t0.1\ta|b\n')
        self.write('timing_checks.txt', '')
        self.write('timing_units.txt', ' time 1ns\n capacitance 1pF\n')
        self.write('timing_totals.txt', 'tns 0.00\n')
        self.write('timing_hold_totals.txt', 'tns 0.00\n')
        self.write('electrical_checks.txt', '')

    def write(self, name, text):
        (self.root / name).write_text(text, encoding='utf-8')

    def test_complete_clean_evidence_passes(self):
        self.assertEqual(timing_report(self.root)['status'], 'PASS')

    def test_negative_total_slack_fails_even_if_reported_paths_pass(self):
        self.write('timing_totals.txt', 'tns max -1.25\n')
        report = timing_report(self.root)
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['summary']['setup_total_negative_slack_ns'], -1.25)

    def test_missing_setup_or_hold_paths_is_incomplete(self):
        for kind in ('setup', 'hold'):
            with self.subTest(kind=kind):
                self.write('timing_paths.tsv', f'{kind}\ta\tb\t2\ta|b\n')
                report = timing_report(self.root)
                self.assertEqual(report['status'], 'INCOMPLETE')
                self.assertTrue(report['incomplete_reasons'])

    def test_missing_auxiliary_reports_is_incomplete(self):
        for name in ('timing_totals.txt', 'timing_hold_totals.txt', 'timing_paths.tsv', 'electrical_checks.txt', 'timing_checks.txt', 'timing_units.txt'):
            with self.subTest(name=name):
                original = (self.root / name).read_text()
                (self.root / name).unlink()
                report = timing_report(self.root)
                self.assertEqual(report['status'], 'INCOMPLETE')
                self.assertTrue(any(name in reason for reason in report['incomplete_reasons']))
                self.write(name, original)

    def test_invalid_total_slack_cannot_pass(self):
        for text in ('', 'tns nan', 'tns inf', 'tns 1.2', 'tns -1.2ns', 'tns 0\ntns -2'):
            with self.subTest(text=text):
                self.write('timing_totals.txt', text)
                self.assertEqual(timing_report(self.root)['status'], 'INCOMPLETE')

    def test_unrecognized_or_nonfinite_path_is_rejected(self):
        for line in ('other\ta\tb\t2\ta|b', 'setup\t\tb\t2\ta|b', 'setup\ta\tb\tnan\ta|b'):
            with self.subTest(line=line):
                self.write('timing_paths.tsv', line + '\n')
                with self.assertRaises(ValueError):
                    timing_report(self.root)

    def test_engine_errors_in_reports_cannot_pass(self):
        for name in ('timing_checks.txt', 'electrical_checks.txt'):
            with self.subTest(name=name):
                self.write(name, 'Error: cannot analyze this design\n')
                self.assertEqual(timing_report(self.root)['status'], 'INCOMPLETE')
                self.write(name, '')

    def test_hold_total_slack_fails_independently(self):
        self.write('timing_hold_totals.txt', 'tns min -0.25\n')
        report = timing_report(self.root)
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['summary']['hold_total_negative_slack_ns'], -0.25)

    def test_setup_diagnostics_need_review(self):
        for diagnostic in ('Warning: combinational loop detected', 'Warning: generated clock has no master',
                           'Warning: multiple clocks on register', 'Warning: unexpected engine diagnostic'):
            with self.subTest(diagnostic=diagnostic):
                self.write('timing_checks.txt', diagnostic)
                self.assertEqual(timing_report(self.root)['status'], 'INCOMPLETE')

    def test_known_failure_is_retained_with_missing_evidence(self):
        self.write('timing_paths.tsv', 'setup\ta\tb\t-2\ta|b\n')
        report = timing_report(self.root)
        self.assertEqual(report['status'], 'FAIL')
        self.assertTrue(report['incomplete_reasons'])

    def test_wrong_or_missing_time_units_cannot_be_labelled_nanoseconds(self):
        for units in ('', 'time 1ps', 'time 1us'):
            with self.subTest(units=units):
                self.write('timing_units.txt', units)
                self.assertEqual(timing_report(self.root)['status'], 'INCOMPLETE')

    def test_later_corners_cannot_borrow_first_corners_clean_state(self):
        from icstudio.digital_implementation import timing
        # Exercise the real corner loop and aggregation with captured report
        # fixtures. This is not external-engine or process qualification.
        runner = SimpleNamespace(root=self.root, config={'timing_corners': ['tt', 'ss', 'ff']},
                                 platform={'corner': 'tt'}, settings={}, tools={'sta': 'fixture'}, artifacts={})

        def command(*args, **kwargs):
            self.write('timing_checks.txt', 'Warning: missing input_delay' if runner.timing_corner == 'ss' else '')
            self.write('electrical_checks.txt', 'max slew VIOLATED' if runner.timing_corner == 'ff' else '')
            self.write('timing_hold_totals.txt', 'tns -0.5' if runner.timing_corner == 'ff' else 'tns 0')
            self.write('timing_full.txt', 'fixture')
            self.write('power.txt', 'Total 0.1 0.1 0.1 0.3')

        runner.command = command
        runner.add_artifact = lambda *args, **kwargs: None
        runner.save_json = lambda *args: None
        with patch('icstudio.digital_implementation.mapped', return_value={}), \
                patch('icstudio.digital_implementation.timing_script', return_value='fixture'):
            data = timing(runner)
        report = data['timing']
        self.assertEqual(data['verdict'], 'FAIL')
        self.assertEqual([c['status'] for c in report['corners']], ['PASS', 'INCOMPLETE', 'FAIL'])
        self.assertTrue(report['unconstrained'])
        self.assertEqual(report['electrical_status'], 'FAIL')
        self.assertEqual(report['summary']['hold_total_negative_slack_ns'], -0.5)
        self.assertTrue(any(reason.startswith('ss:') for reason in report['incomplete_reasons']))
        self.assertIn('ss: Missing clock', data['summary'])
