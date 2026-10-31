import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from icstudio.klayout_runtime_probe import check_result, qualify


class KLayoutRuntimeProbeTests(unittest.TestCase):
    def report(self, path, count=0, category='runtime.width'):
        items = ''.join('<item><category>' + category + '</category></item>' for _ in range(count))
        path.write_text('<report-database><top-cell>runtime_probe</top-cell>'
                        '<categories><category><name>runtime.width</name></category></categories>'
                        '<items>' + items + '</items></report-database>')

    def test_native_counts_and_executed_operator_must_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'report.lyrdb'
            self.report(report, 1)
            good = 'PROBE_KLAYOUT 1 1 KLayout 0.30.5\n'
            self.assertEqual(check_result(good, report, 1)['markers'], 1)
            for log, expected in [('PROBE_KLAYOUT 1 0 KLayout 0.30.5\n', 1),
                                  ('PROBE_KLAYOUT 0 0 KLayout 0.30.5\n', 0), (good, 0)]:
                with self.subTest(log=log, expected=expected), self.assertRaises(ValueError):
                    check_result(log, report, expected)

    def test_missing_malformed_and_empty_reports_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'report.lyrdb'
            log = 'PROBE_KLAYOUT 0 0 KLayout 0.30.5\n'
            with self.assertRaisesRegex(ValueError, 'omitted or damaged'):
                check_result(log, report, 0)
            for text in ('<broken', '<report-database/>', '<unrelated/>'):
                report.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError):
                    check_result(log, report, 0)

    def test_wrong_rule_duplicate_or_missing_execution_marker_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'report.lyrdb'
            self.report(report, 1, 'different.rule')
            log = 'PROBE_KLAYOUT 1 1 KLayout 0.30.5\n'
            with self.assertRaisesRegex(ValueError, 'unexpected rule category'):
                check_result(log, report, 1)
            for bad in ('KLayout 0.30.5', log + log, 'ERROR: missing Ruby interface'):
                with self.assertRaisesRegex(ValueError, 'actual Ruby rule control'):
                    check_result(bad, report, 1)

    def test_engine_failure_keeps_log_and_cannot_publish_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'probe'
            def fail(args, cwd, **kwargs):
                kwargs['on_line']('ERROR: uninitialized constant RBA::EdgePairToEdgeOperator')
                raise RuntimeError('Engine failed')
            with patch('icstudio.klayout_runtime_probe.execute', side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, 'Engine failed'):
                    qualify('broken-klayout', root)
            self.assertIn('EdgePairToEdgeOperator', (root / 'legal.log').read_text())
            self.assertTrue((root / 'legal-command.json').is_file())
            self.assertFalse((root / 'checks.json').exists())


if __name__ == '__main__':
    unittest.main()
