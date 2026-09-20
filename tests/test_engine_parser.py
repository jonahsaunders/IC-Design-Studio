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
 def test_wide_extracted_noise_matrix_streams_with_bounded_total_values(self):
  count=20743
  header='Title: extracted noise\nFlags: real\nNo. Variables: '+str(count)+'\nNo. Points: 2\nVariables:\n'
  header+=' 0 frequency frequency\n'+''.join(' '+str(i)+' onoise.r'+str(i)+' voltage-density\n' for i in range(1,count))
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'wide.raw';path.write_text(header+'Values:\n0 10\n'+' 1e-9\n'*(count-1)+'1 100\n'+' 2e-9\n'*(count-1))
   names,rows,is_complex=parse_raw(path)
   self.assertEqual(len(names),count);self.assertEqual(rows[0][-1],1e-9);self.assertEqual(rows[1][-1],2e-9);self.assertFalse(is_complex)
   path.write_text(header.replace('No. Points: 2','No. Points: 1000')+'Values:\n')
   with self.assertRaisesRegex(ValueError,'dimensions'):parse_raw(path)
 def test_truncated_values_report_a_readable_failure(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'short.raw';path.write_text('Flags: real\nNo. Variables: 2\nNo. Points: 1\nVariables:\n 0 time time\n 1 v(out) voltage\nValues:\n0 0\n')
   with self.assertRaisesRegex(ValueError,'Incomplete'):parse_raw(path)
if __name__=='__main__':unittest.main()
