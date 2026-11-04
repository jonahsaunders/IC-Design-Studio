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
        for pair in ((74,22),(81,57),(81,63)):
            self.assertGreater(counts({pair:region((0,0,500,500))})['profile.'+str(pair)],0)

    def test_diffusion_and_tap_enclosure_boundaries(self):
        for active in ((65,20),(65,44)):
            for in_well in (False,True):
                is_n=(active==(65,20))!=in_well;implant=(93,44) if is_n else (94,20)
                rule='n/psd.'+('5a' if active==(65,20) else '5b')+('.n' if is_n else '.p')
                for margin in (120,125,130):
                    masks={active:region((0,0,1000,1000)),implant:region((-margin,-margin,1000+margin,1000+margin))}
                    if in_well:masks[(64,20)]=region((-2000,-2000,3000,3000))
                    with self.subTest(active=active,in_well=in_well,margin=margin):
                        self.assertEqual(counts(masks)[rule]>0,margin<125)

    def test_butting_edge_allows_zero_but_not_missing_enclosure(self):
        masks={(65,20):region((0,0,1000,1000)),(65,44):region((1000,0,1500,1000)),
               (93,44):region((-130,-130,1000,1130)),(94,20):region((1000,-130,1630,1130))}
        self.assertEqual(check(masks)['status'],'PASS')
        broken={**masks,(93,44):region((-130,-130,995,1130))}
        self.assertGreater(counts(broken)['n/psd.6.n'],0)
        self.assertGreater(counts(broken)['n/psd.9.n'],0)

    def test_partial_butting_does_not_exempt_whole_edge(self):
        masks={(65,20):region((0,0,1000,1000)),(65,44):region((1000,250,1500,750)),
               (93,44):region((-130,-130,1000,1130)),(94,20):region((1000,120,1630,880))}
        self.assertGreater(counts(masks)['n/psd.5a.n'],0)
        self.assertEqual(counts(masks)['n/psd.6.n'],0)

    def test_opposite_active_spacing_boundaries(self):
        for gap in (125,130,135):
            masks={(93,44):region((0,0,500,500)),(65,44):region((500+gap,0,1500,500))}
            with self.subTest(gap=gap):self.assertEqual(counts(masks)['n/psd.7.n']>0,gap<130)

    def test_corner_spacing_uses_euclidean_distance(self):
        for offset in (90,95):
            masks={(93,44):region((0,0,500,500)),(65,44):region((500+offset,500+offset,1500,1500))}
            with self.subTest(offset=offset):self.assertEqual(counts(masks)['n/psd.7.n']>0,offset==90)

    def test_missing_implant_cannot_escape_edge_checks(self):
        masks={(65,20):region((0,0,1000,1000)),(65,44):region((1000,0,1500,1000))}
        self.assertEqual(check(masks)['status'],'FAIL')
        self.assertGreater(counts(masks)['n/psd.9.n'],0)
        self.assertGreater(counts(masks)['n/psd.6.n'],0)


if __name__=='__main__':unittest.main()
