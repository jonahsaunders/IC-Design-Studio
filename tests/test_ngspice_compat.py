import unittest
from icstudio.ngspice_compat import MARKER,convert,declare,legacy_symbol


class DiodeGeometryCompatibilityTests(unittest.TestCase):
    def test_declared_units_only_and_runtime_copy_is_idempotent(self):
        raw='D1 a 0 sky130_fd_pr__diode_pw2nd_05v5 area={size * 1e12} pj=3e6 m=4\n'
        untouched='D2 a 0 sky130_fd_pr__diode_pw2nd_05v5 area=2\n'
        source=declare(raw)+untouched
        converted,count=convert(source,'unscaled-explicit-area')
        self.assertEqual(count,1)
        self.assertIn('area={(size * 1e12)*1e-12} pj={(3e6)*1e-6} m=4',converted)
        self.assertIn(untouched,converted)
        self.assertEqual(convert(converted,'unscaled-explicit-area'),(converted,0))
        old,count=convert(source,'scales-explicit-area')
        self.assertIn(raw,old);self.assertEqual(count,1)

    def test_incomplete_or_ambiguous_geometry_fails_closed(self):
        for line in ('', '.end', 'D1 a 0 different area=1',
                     'D1 a 0 sky130_fd_pr__diode_pw2nd_05v5 pj=1',
                     'D1 a 0 sky130_fd_pr__diode_pw2nd_05v5 area=1 w=2'):
            with self.subTest(line=line),self.assertRaises(ValueError):
                convert(MARKER+'\n'+line,'unscaled-explicit-area')

    def test_symbol_identification_uses_a_declared_convention_not_instance_size(self):
        attrs={'type':'diode','format':'@name @pinlist sky130_fd_pr__@model area=@area',
               'template':'name=D1 model=diode_pw2nd_05v5 area=1e12'}
        self.assertTrue(legacy_symbol(attrs))
        self.assertFalse(legacy_symbol({**attrs,'template':'name=D1 area=1'}))
        self.assertFalse(legacy_symbol(attrs,{'model':'unqualified_model'}))
        self.assertFalse(legacy_symbol(attrs,{'format':'custom'}))


if __name__=='__main__':unittest.main()
