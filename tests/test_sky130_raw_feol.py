import unittest
import klayout.db as k
from scripts.sky130_raw_feol import check


def region(*boxes):
    result=k.Region()
    for box in boxes:result.insert(k.Box(*box))
    return result.merged()


def counts(masks):
    return {row['rule']:row['violations'] for row in check(masks)['checks']}


class RawFeolTests(unittest.TestCase):
    def test_absent_masks_do_not_infer_coverage(self):
        report=check({})
        self.assertEqual(report['status'],'PASS')
        self.assertFalse(report['qualified'])
        self.assertIn('separate',report['scope'])

    def test_missing_and_wrong_implants_are_rejected(self):
        n=region((0,0,500,500));p=region((2000,0,2500,500))
        masks={(65,20):n|p,(64,20):region((1500,-500,3000,1000)),
               (93,44):region((-200,-200,700,700)),(94,20):region((1800,-200,2700,700))}
        self.assertEqual(check(masks)['status'],'PASS')
        self.assertGreater(counts({**masks,(93,44):k.Region()})['n/psd.9.n'],0)
        self.assertGreater(counts({**masks,(93,44):masks[(94,20)]})['n/psd.8.n'],0)
        self.assertGreater(counts({**masks,(94,20):masks[(93,44)]})['n/psd.8.p'],0)

    def test_tap_doping_is_opposite_diffusion(self):
        masks={(65,44):region((0,0,500,500)),(94,20):region((-200,-200,700,700))}
        self.assertEqual(counts(masks)['n/psd.9.p'],0)
        self.assertGreater(counts({**masks,(94,20):k.Region()})['n/psd.9.p'],0)
        masks[(64,20)]=region((-1000,-1000,1000,1000))
        self.assertGreater(counts(masks)['n/psd.8.p'],0)
        masks[(93,44)]=masks.pop((94,20))
        self.assertEqual(counts(masks)['n/psd.9.n'],0)

    def test_width_and_notch_boundaries(self):
        for pair,prefix in (((93,44),'n/psd'),((94,20),'n/psd'),((78,44),'hvtp')):
            suffix='.n' if pair==(93,44) else '.p' if pair==(94,20) else ''
            for width in (375,380,385):
                with self.subTest(pair=pair,width=width):
                    self.assertEqual(counts({pair:region((0,0,width,2000))})[prefix+'.1'+suffix]>0,width<380)
            for gap in (375,380,385):
                # The notch is inside a single merged U polygon, not just a
                # gap between separate rectangles.
                u=region((0,0,500,2000),(500+gap,0,1000+gap,2000),(0,0,1000+gap,500))
                with self.subTest(pair=pair,gap=gap):
                    self.assertEqual(counts({pair:u})[prefix+'.2'+suffix]>0,gap<380)

    def test_area_and_hole_limits(self):
        for pair,rule,minimum,hole_rule in (((93,44),'n/psd.10a',265000,'n/psd.11.n'),
                ((94,20),'n/psd.10b',255000,'n/psd.11.p'),((78,44),'hvtp.5',265000,'hvtp.6')):
            for delta in (-5,0,5):
                box=(0,0,1000,minimum//1000+delta)
                with self.subTest(pair=pair,delta=delta):
                    self.assertEqual(counts({pair:region(box)})[rule]>0,delta<0)
                    ring=region((-1000,-1000,3000,3000))-region((0,0,1000,265+delta))
                    self.assertEqual(counts({pair:ring})[hole_rule]>0,delta<0)

    def test_hvtp_enclosure_and_outside_spacing_boundaries(self):
        base={(65,20):region((0,0,1000,1000)),(66,20):region((400,-100,550,1100)),
              (64,20):region((-2000,-2000,4000,4000))}
        for gap in (175,180,185):
            with self.subTest(gap=gap):
                inside={**base,(78,44):region((400-gap,-gap,550+gap,1000+gap))}
                self.assertEqual(counts(inside)['hvtp.3']>0,gap<180)
                outside={**base,(78,44):region((550+gap,-1000,3000,2000))}
                self.assertEqual(counts(outside)['hvtp.4']>0,gap<180)
        straddled={**base,(78,44):region((475,-1000,3000,2000))}
        self.assertGreater(counts(straddled)['hvtp.3'],0)

    def test_unsupported_profile_and_well_crossing_fail(self):
        self.assertGreater(counts({(75,20):region((0,0,500,500))})['profile.(75, 20)'],0)
        masks={(65,20):region((0,0,1000,1000)),(64,20):region((500,-100,2000,2000))}
        self.assertGreater(counts(masks)['profile.active_well_straddle'],0)
        self.assertGreater(counts({**masks,(65,44):masks[(65,20)]})['profile.active_overlap'],0)


if __name__=='__main__':unittest.main()
