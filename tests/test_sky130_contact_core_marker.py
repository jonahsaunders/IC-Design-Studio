"""Supplemental contact checks keep the original audited test source immutable."""
import unittest
from tests.test_sky130_interconnect_geometry import region,counts


class CoreMarkerTests(unittest.TestCase):
    def test_core_marker_cannot_hide_an_uncovered_contact(self):
        # The public 2025 Tiny Tapeout deck excludes areaid:core from its
        # contact-coverage check. Studio must still detect missing drawn LI.
        # Test absent, enclosing and crossing core markers and a one-nm gap.
        ct=region((0,0,170,170))
        for core in (region(),region((-1000,-1000,1000,1000)),region((85,-1000,1000,1000))):
            for li,expected in ((ct,False),(region((1,0,170,170)),True),(region(),True)):
                with self.subTest(core=str(core),li=str(li)):
                    masks={(67,44):ct,(67,20):li,(81,2):core,(56,28):ct}
                    self.assertEqual(counts(masks)['ct.4']>0,expected)


if __name__ == "__main__": unittest.main()
