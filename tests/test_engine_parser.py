import tempfile,unittest
from pathlib import Path
from icstudio.engines import parse_raw,tcl_word
class EngineParserTests(unittest.TestCase):
 def test_ngspice_real_header(self):
  raw='Title: fixture\nPlotname: Transient Analysis\nFlags: real\nNo. Variables: 2\nNo. Points: 2\nVariables:\n 0 time time\n 1 v(out) voltage\nValues:\n0 0\n 1.8\n1 0.1\n 0.9\n'
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'fixture.raw';path.write_text(raw);names,rows,complex_data=parse_raw(path);self.assertEqual(names,['time','v(out)']);self.assertEqual(rows,[[0,1.8],[.1,.9]]);self.assertFalse(complex_data)
 def test_ngspice_complex_header(self):
  raw='Title: fixture\nPlotname: AC Analysis\nFlags: complex\nNo. Variables: 2\nNo. Points: 1\nVariables:\n 0 frequency frequency\n 1 v(out) voltage\nValues:\n0 1000,0\n 0.5,-0.5\n'
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'fixture.raw';path.write_text(raw);_,rows,is_complex=parse_raw(path);self.assertTrue(is_complex);self.assertEqual(rows[0][1],.5-.5j)
 def test_literal_tcl_path(self):self.assertEqual(tcl_word('/a b/$x[cmd]'),'"/a b/\\$x\\[cmd\\]"')
if __name__=='__main__':unittest.main()
