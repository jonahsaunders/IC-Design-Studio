"""Test the same missing-stdio condition as the windowed frozen worker."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(os.name=='nt','Windows inherited pipe test')
class WindowedWorkerTests(unittest.TestCase):
    def test_pythonw_restores_inherited_output_pipes(self):
        pythonw=Path(sys.executable).with_name('pythonw.exe')
        self.assertTrue(pythonw.is_file(),'The Windows build must provide pythonw for the windowed worker check')
        code='from icstudio.windows_stdio import connect; connect(); import sys; print("worker progress",flush=True); print("worker error",file=sys.stderr,flush=True)'
        result=subprocess.run([str(pythonw),'-c',code],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('worker progress',result.stdout)
        self.assertIn('worker error',result.stderr)
