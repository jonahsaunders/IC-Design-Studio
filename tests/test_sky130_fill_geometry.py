import unittest
import klayout.db as k

from scripts.sky130_fill_geometry import check, METALS


def boxes(*values):
    region = k.Region()
    for value in values:
        region.insert(k.Box(*value))
    return region


class FillGeometryTests(unittest.TestCase):
    def result(self, regions):
        report = check(regions, boxes((0, 0, 100000, 100000)))
        self.assertFalse(report['qualified'])
        return {r['check']: r['violations'] for r in report['checks']}

    def test_fom_spacing_includes_dummy_fill_purpose(self):
        for gap, failed in ((395, True), (400, False), (405, False)):
            with self.subTest(gap=gap):
                r = self.result({(23, 28): boxes((1000, 1000, 1500, 1500), (1500+gap, 1000, 2000+gap, 1500))})
                self.assertEqual(bool(r['fom.spacing']), failed)

    def test_nonstandard_clipped_waffle_is_rejected(self):
        r = self.result({(23, 28): boxes((1000, 1000, 1500, 1495))})
        self.assertGreater(r['fom.shape'], 0)
        self.assertGreater(r['fom.width'], 0)

    def test_implant_spacing_and_overlap(self):
        for left, failed in ((1495, True), (1625, True), (1630, False)):
            with self.subTest(left=left):
                r = self.result({(23, 28): boxes((1000, 1000, 1500, 1500)),
                                 (93, 44): boxes((left, 1000, left+500, 1500))})
                self.assertEqual(bool(r['fom.implant']), failed)

    def test_well_enclosure_and_outside_spacing(self):
        for x, failed in ((1175, True), (1180, False), (3335, True), (3340, False)):
            with self.subTest(x=x):
                r = self.result({(64, 20): boxes((1000, 1000, 3000, 3000)),
                                 (23, 28): boxes((x, 1500, x+500, 2000))})
                self.assertEqual(bool(r['fom.well']), failed)

    def test_nitride_keepout(self):
        for gap, failed in ((995, True), (1000, False)):
            with self.subTest(gap=gap):
                r = self.result({(23, 28): boxes((1000, 1000, 1500, 1500)),
                                 (61, 20): boxes((1500+gap, 1000, 3000+gap, 2000))})
                self.assertEqual(bool(r['fom.nsm']), failed)

    def test_every_metal_rejects_below_minimum_width(self):
        for name, (pair, _, width, _, _) in METALS.items():
            with self.subTest(name=name):
                r = self.result({pair: boxes((1000, 1000, 1000+width-5, 11000))})
                self.assertGreater(r[name+'.width'], 0)

    def test_every_metal_checks_fill_to_fill_spacing(self):
        for name, (pair, _, _, spacing, _) in METALS.items():
            for gap in (spacing-5, spacing):
                with self.subTest(name=name, gap=gap):
                    r = self.result({pair: boxes((1000, 1000, 3000, 3000), (3000+gap, 1000, 5000+gap, 3000))})
                    self.assertEqual(bool(r[name+'.spacing']), gap < spacing)

    def test_floating_m3_and_m4_minimum_area(self):
        for name in ('m3', 'm4'):
            pair = METALS[name][0]
            for height in (795, 800):
                with self.subTest(name=name, height=height):
                    r = self.result({pair: boxes((1000, 1000, 1300, 1000+height))})
                    self.assertEqual(bool(r[name+'.area']), height < 800)

    def test_huge_fill_uses_wider_spacing(self):
        for gap, failed in ((140, True), (275, True), (280, False)):
            with self.subTest(gap=gap):
                r = self.result({(36, 28): boxes((1000, 1000, 5000, 5000), (5000+gap, 2000, 6000+gap, 3000))})
                self.assertEqual(bool(r['m1.wide_spacing']), failed)
                self.assertEqual(r['m1.spacing'], 0)

    def test_same_layer_signal_overlap_is_not_a_pass(self):
        r = self.result({(36, 28): boxes((1000, 1000, 2000, 2000)), (68, 20): boxes((1500, 1500, 2500, 2500))})
        self.assertGreater(r['m1.signal_clearance'], 0)

    def test_grid_extent_and_unsupported_profile(self):
        r = self.result({(23, 28): boxes((-1, 1000, 499, 1500)), (75, 20): boxes((5000, 5000, 6000, 6000))})
        self.assertGreater(r['grid.(23, 28)'], 0)
        self.assertGreater(r['extent.(23, 28)'], 0)
        self.assertGreater(r['profile.high_voltage'], 0)

    def test_li_aspect_ratio_without_contacts(self):
        r = self.result({(56, 28): boxes((1000, 1000, 1250, 3505))})
        self.assertEqual(r['li.aspect'], 1)


if __name__ == '__main__':
    unittest.main()
