from pathlib import Path
import tempfile
import unittest
from scripts.check_ihp_flat_capacitance import audit,raw_capacitors,write_full_precision
from scripts.ihp_native_capacitance import read_capacitors


class FlatCapacitanceTests(unittest.TestCase):
    EXT='scale 1000 1 0.5\nnode "A" 0 163.059 0 0 m1\nnode "Y" 0 167.524 1 0 m1\nsubstrate "VSS" 0 0 0 1 m1\ncap "A" "Y" 46.0233\n'

    def check(self,spice,ext=None):
        with tempfile.TemporaryDirectory() as d:
            x=Path(d)/'cell.ext';s=Path(d)/'cell.spice';x.write_text(ext or self.EXT);s.write_text(spice)
            return audit(x,s)

    def test_native_rounding_is_allowed(self):
        self.assertTrue(self.check('C0 A VSS .16306f\nC1 Y VSS .16752f\nC2 Y A .04602f\n')['passed'])

    def test_mos_gate_capacitance_moved_to_drain_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'graph changed'):
            self.check('C0 Y VSS .33058f\nC1 Y A .04602f\n')

    def test_missing_and_invented_capacitors_are_rejected(self):
        for source in ('C0 A VSS .16306f\nC1 Y VSS .16752f\n',
                       'C0 A VSS .16306f\nC1 Y VSS .16752f\nC2 Y A .04602f\nC3 Z VSS .001f\n'):
            with self.subTest(source=source),self.assertRaises(ValueError):self.check(source)

    def test_zero_native_printing_does_not_justify_omitting_a_large_cap(self):
        small='scale 1000 1 0.5\nnode "A" 0 .8 0 0 m1\nsubstrate "VSS" 0 0 0 1 m1\n'
        self.assertTrue(self.check('C0 A VSS 0\n',small)['passed'])
        with self.assertRaises(ValueError):self.check('C0 A VSS 0\n',small.replace('0 .8','0 8'))

    def test_hierarchy_aliases_or_nonzero_substrate_cannot_be_ignored(self):
        for ext in (self.EXT+'use child child_0 1 0 0 0 1 0\n',self.EXT+'equiv "A" "Z"\n',
                    self.EXT.replace('"VSS" 0 0','"VSS" 0 1')):
            with self.subTest(ext=ext),self.assertRaises(ValueError):self.check('C0 A VSS .16306f\n',ext)

    def test_full_precision_retains_small_capacitors_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            x=Path(d)/'cell.ext';x.write_text(self.EXT.replace('163.059','.0037'))
            graph=raw_capacitors(x);target=Path(d)/'caps.spice';write_full_precision(graph,target)
            restored=read_capacitors(target)
            for before,after in zip(graph['edges_af'],restored['edges_af']):
                self.assertEqual(before[:2],after[:2]);self.assertAlmostEqual(before[2],after[2])
            with self.assertRaises(ValueError):write_full_precision(graph,target)

    def test_native_overlap_roundoff_is_bounded_and_reported(self):
        ext=self.EXT+'cap "Y" "VSS" -1e-12\n'
        r=self.check('C0 A VSS .16306f\nC1 Y VSS .16752f\nC2 Y A .04602f\n',ext)
        self.assertEqual(r['negative_roundoff_count'],1)
        self.assertEqual(r['negative_roundoff_total_af'],1e-12)
        with self.assertRaises(ValueError):self.check('C0 A VSS .16306f\n',ext.replace('-1e-12','-1e-5'))


if __name__=='__main__':unittest.main()
