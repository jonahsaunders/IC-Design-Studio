import unittest
from scripts.check_ihp_lvs import port_match


class IHPPortTests(unittest.TestCase):
    def test_spice_case_is_preserved_without_losing_the_bit_identity(self):
        self.assertTrue(port_match([dict(layout='n0001',reference='N0001',status='Match')],['N0001']))

    def test_native_match_cannot_hide_an_unpaired_output(self):
        self.assertFalse(port_match([dict(layout='N1',reference=None,status='Match')],['N1']))

    def test_native_match_cannot_hide_swapped_outputs(self):
        self.assertFalse(port_match([dict(layout='N1',reference='N2',status='Match'),
                                    dict(layout='N2',reference='N1',status='Match')],['N1','N2']))

    def test_missing_or_repeated_ports_are_rejected(self):
        pair=dict(layout='N1',reference='N1',status='Match')
        self.assertFalse(port_match([pair],['N1','N2']))
        self.assertFalse(port_match([pair,pair],['N1','N2']))
