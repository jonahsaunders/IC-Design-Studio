"""Run Qt signal regression checks in a fresh application process."""
import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is required for menu signal regression')
class StudentHubMenuRegressionTests(unittest.TestCase):
    def test_more_menu_callbacks_and_text_sizes(self):
        root = Path(__file__).resolve().parents[1]
        env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}
        result = subprocess.run([sys.executable, '-m', 'tests.gui_student_hub_menu', '-v'],
                                cwd=root, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Ran 2 tests', result.stderr)


if __name__ == '__main__':
    unittest.main()
