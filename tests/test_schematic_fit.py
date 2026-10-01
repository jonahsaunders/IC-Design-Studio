"""Run schematic framing regressions in an isolated Qt process."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(importlib.util.find_spec('PySide6'),'PySide6 is required for schematic fitting')
class SchematicFitRegressionTests(unittest.TestCase):
    def test_imported_symbol_framing(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,'-m','tests.gui_schematic_fit','-v'],cwd=root,
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Ran 7 tests',result.stderr)


if __name__=='__main__':unittest.main()
