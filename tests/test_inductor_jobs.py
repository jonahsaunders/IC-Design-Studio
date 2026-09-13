"""Run widget lifecycle checks separately from existing QCoreApplication tests."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class WorkerProcessTests(unittest.TestCase):
    def test_qt_worker_lifecycle(self):
        root=Path(__file__).resolve().parents[1]
        env={**os.environ,'QT_QPA_PLATFORM':'offscreen','PYTHONPATH':str(root)}
        result=subprocess.run([sys.executable,str(root/'tests/gui_inductor_jobs.py'),'-v'],
                              cwd=root,env=env,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
