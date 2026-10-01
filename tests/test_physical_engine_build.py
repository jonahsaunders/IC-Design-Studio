"""Exact engine sources survive transport failures without changing the pin."""
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_physical_engines import fetch_source


class PhysicalEngineSourceTests(unittest.TestCase):
    def setUp(self):
        self.entry = {'repository': 'https://primary.example/engine.git',
                      'repository_mirrors': ['https://mirror.example/engine.git'],
                      'commit': 'a' * 40}
        self.log = io.StringIO()

    def fetch(self):
        fetch_source(self.entry, ROOT, {}, self.log)

    def test_connection_failure_and_timeout_retry_the_same_commit(self):
        errors = [subprocess.CalledProcessError(128, 'git fetch'),
                  subprocess.TimeoutExpired('git fetch', 60), None]
        with patch('build_physical_engines.subprocess.run', side_effect=errors) as run, \
                patch('build_physical_engines.subprocess.check_output', return_value=self.entry['commit'] + '\n'), \
                patch('build_physical_engines.time.sleep') as sleep:
            self.fetch()
        self.assertEqual(run.call_count, 3)
        self.assertTrue(all(call.args[0][-2:] == [self.entry['repository'], self.entry['commit']]
                            for call in run.call_args_list))
        self.assertTrue(all(call.kwargs['timeout'] == 60 for call in run.call_args_list))
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

    def test_unavailable_primary_uses_only_a_declared_mirror(self):
        errors = [subprocess.CalledProcessError(128, 'git fetch')] * 3 + [None]
        with patch('build_physical_engines.subprocess.run', side_effect=errors) as run, \
                patch('build_physical_engines.subprocess.check_output', return_value=self.entry['commit'] + '\n'), \
                patch('build_physical_engines.time.sleep'):
            self.fetch()
        self.assertEqual(run.call_count, 4)
        self.assertEqual(run.call_args.args[0][-2:], [self.entry['repository_mirrors'][0], self.entry['commit']])
        self.assertIn('exit status 128', self.log.getvalue())

    def test_exhausted_sources_fail_and_preserve_the_transport_error(self):
        error = subprocess.CalledProcessError(128, 'git fetch')
        with patch('build_physical_engines.subprocess.run', side_effect=error) as run, \
                patch('build_physical_engines.subprocess.check_output') as verify, \
                patch('build_physical_engines.time.sleep'), \
                self.assertRaisesRegex(RuntimeError, 'Could not fetch pinned source') as caught:
            self.fetch()
        self.assertEqual(run.call_count, 6)
        verify.assert_not_called()
        self.assertIs(caught.exception.__cause__, error)

    def test_successful_fetch_of_a_different_commit_is_rejected(self):
        with patch('build_physical_engines.subprocess.run') as run, \
                patch('build_physical_engines.subprocess.check_output', return_value='b' * 40 + '\n'), \
                self.assertRaisesRegex(ValueError, 'Unexpected fetched source commit'):
            self.fetch()
        self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
