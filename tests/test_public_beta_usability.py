"""Isolate QWidget regressions from tests using QCoreApplication."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Requires PySide6')
class PublicBetaUsabilityRegressionTests(unittest.TestCase):
    def test_student_and_mixed_signal_recovery_controls(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, '-m', 'tests.gui_public_beta_usability', '-v'],
            cwd=root, env={**os.environ, 'QT_QPA_PLATFORM':'offscreen'}, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('Ran 8 tests', result.stderr)


if __name__ == '__main__': unittest.main()
