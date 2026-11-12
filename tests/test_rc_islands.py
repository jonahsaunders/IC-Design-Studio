import tempfile
from pathlib import Path
import unittest
from icstudio.rc_islands import prune
from scripts.qualify_gf180_fill_coupling import range_um
from icstudio.gf180_rc import sparse_solver


class RCIslandTests(unittest.TestCase):
    def test_sparse_solver_is_applied_to_diagnostic_end_at_eof(self):
        for ending in ('.end','.end\n','.END\r\n'):
            deck='* test\n.tran 100n 500u uic\n.ic v(vref)=0\n'+ending
            result=sparse_solver(deck)
            self.assertIn('.tran 100n 500u uic\n.ic v(vref)=0\n.option klu',result)
            self.assertIn('set num_threads=1',result)
            self.assertNotIn('\nrun\n',result)
        with self.assertRaises(ValueError):sparse_solver('* no end')

    def test_only_unobservable_resistor_components_are_removed(self):
        text='''* preserve observable graph verbatim
.subckt top PORT GND
Rport PORT p 1
Rcap a b 2
C1 b c 1f
Rdevice d e 3
X1 e z model w=1
Rfloating F1 F2 4
Rfloating2 f2 f3 5
.ends top
'''
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'raw.spice';target=Path(tmp)/'electrical.spice';source.write_text(text)
            r=prune(source,target)
            self.assertEqual(r['removed_resistors'],['rfloating','rfloating2'])
            self.assertEqual(r['components'],1)
            self.assertEqual(source.read_text(),text)
            self.assertEqual(target.read_text(),text.replace('Rfloating F1 F2 4\n','').replace('Rfloating2 f2 f3 5\n',''))
            with self.assertRaises(ValueError):prune(source,target)

    def test_unsupported_elements_and_hierarchy_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            for n,body in enumerate(('L1 a b 1n','.subckt inner a b','* no preceding statement\n+ continuation','R1 a b -1','R1 a b 1\nr1 floating island 2')):
                source=Path(tmp)/str(n);source.write_text('.subckt top a b\n'+body+'\n.ends\n')
                with self.subTest(body=body),self.assertRaises(ValueError):prune(source,Path(tmp)/(str(n)+'.out'))

    def test_wrapped_port_remains_an_observable_anchor(self):
        text='.subckt top a b\n+ wrapped_port\nRkeep wrapped_port internal 1\nRdrop disconnected other 2\n.ends\n'
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'raw.spice';target=Path(tmp)/'electrical.spice'
            source.write_text(text, newline='\n')
            report=prune(source,target)
            self.assertEqual(report['removed_resistors'],['rdrop'])
            self.assertEqual(target.read_text(),text.replace('Rdrop disconnected other 2\n',''))

    def test_range_requires_both_bounded_micron_declarations(self):
        text='extract\n units microns\n sidehalo 8\n fringeshieldhalo 8\nend\n'
        self.assertEqual(range_um(text),8)
        for invalid in (text.replace('microns','lambda'),text.replace(' sidehalo 8\n',''),text.replace('sidehalo 8','sidehalo 0')):
            with self.assertRaises(ValueError):range_um(invalid)
