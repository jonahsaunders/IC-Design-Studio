"""Run the application navigation matrix in its own isolated Qt process."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is required for workspace navigation')
class WorkspaceTransitionRegressionTests(unittest.TestCase):
    def test_workspace_routes_and_example_launches(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, '-m', 'tests.gui_workspace_transitions', '-v'],
            cwd=root, env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
            capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS 272 ordered workspace transitions', result.stdout)
        self.assertIn('PASS 26 Student Hub / RTL to gallery example transitions', result.stdout)


if __name__ == '__main__':
    unittest.main()
