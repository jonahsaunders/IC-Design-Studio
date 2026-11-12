"""Keep document safety GUI regressions isolated from QCoreApplication tests."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class ProjectDataSafetyRegressionTests(unittest.TestCase):
    def test_real_desktop_open_and_folder_save_guards(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, '-m', 'tests.gui_project_data_safety', '-v'],
            cwd=root, env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
            capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Ran 64 tests', result.stderr)


if __name__ == '__main__':
    unittest.main()
