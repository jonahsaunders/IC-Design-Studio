import unittest
import klayout.db as k
from scripts.sky130_wide_metal import check


def region(*boxes):
    r=k.Region()
    for box in boxes:r.insert(k.Box(*box))
    return r.merged()


def result(masks,name):
    return next(c for c in check(masks)['checks'] if c['rule']==name+'.wide_spacing')


class WideMetalTests(unittest.TestCase):
    def test_strict_three_micrometre_width_and_length(self):
        for width in (2995,3000,3005):
            for length in (2995,3000,3005):
                m=region((0,0,width,length),(width+200,0,width+1000,1000))
                row=result({(68,20):m},'m1')
                with self.subTest(width=width,length=length):
                    self.assertEqual(row['huge_regions']>0,width>3000 and length>3000)
                    self.assertEqual(row['violations']>0,width>3000 and length>3000)

    def test_all_wide_thresholds_and_mixed_fill(self):
        for name,pair,fill,distance in (('m1',(68,20),(36,28),280),('m2',(69,20),(41,28),280),
                                        ('m3',(70,20),(34,28),400),('m4',(71,20),(51,28),400)):
            for delta in (-5,0,5):
                wide=region((0,0,4000,4000));other=region((4000+distance+delta,0,8000,4000))
                for fill_wide in (False,True):
                    masks={fill:wide,pair:other} if fill_wide else {pair:wide,fill:other}
                    with self.subTest(name=name,delta=delta,fill_wide=fill_wide):
                        self.assertEqual(result(masks,name)['violations']>0,delta<0)

    def test_wide_notch_is_not_only_an_inter_polygon_check(self):
        for distance,pair,name in ((280,(68,20),'m1'),(400,(70,20),'m3')):
            for delta in (-5,0,5):
                m=region((0,0,9000,9000))-region((4500,4500,4500+distance+delta,10000))
                self.assertEqual(result({pair:m},name)['violations']>0,delta<0)

    def test_nearby_attached_feature_uses_large_spacing(self):
        for distance,pair,name in ((280,(68,20),'m1'),(400,(70,20),'m3')):
            for delta in (-5,0,5):
                # The neighbor is farther than the wide rule from the main
                # rectangle, but too close to the nearby attached branch.
                shape=region((0,0,4000,4000),(4000,1000,8000,1500))
                other=region((4000+distance+5,1500+distance+delta,5000,3000))
                for trans in (k.Trans.R0,k.Trans.R90,k.Trans.R180,k.Trans.R270):
                    masks={pair:(shape|other).transformed(trans)}
                    with self.subTest(name=name,delta=delta,trans=str(trans)):
                        self.assertEqual(result(masks,name)['violations']>0,delta<0)

    def test_far_attached_feature_does_not_reclassify_entire_wire(self):
        for distance,pair,name in ((280,(68,20),'m1'),(400,(70,20),'m3')):
            shape=region((0,0,4000,4000),(4000,1000,12000,1500))
            other=region((4000+3*distance,1500+distance-5,11000,3000))
            self.assertEqual(result({pair:shape|other},name)['violations'],0)

    def test_thin_l_shape_is_not_huge_just_because_its_bbox_is_large(self):
        shape=region((0,0,10000,500),(0,0,500,10000),(700,700,1200,1200))
        row=result({(68,20):shape},'m1')
        self.assertEqual(row['huge_regions'],0);self.assertEqual(row['violations'],0)

    def test_diagonal_corner_spacing_is_euclidean(self):
        wide=region((0,0,4000,4000))
        for offset in (195,200):
            other=region((4000+offset,4000+offset,6000,6000))
            self.assertEqual(result({(68,20):wide|other},'m1')['violations']>0,offset==195)

    def test_unsupported_non_manhattan_geometry_is_not_silently_checked(self):
        triangle=k.Region(k.Polygon([k.Point(0,0),k.Point(4000,0),k.Point(0,4000)]))
        report=check({(68,20):triangle})
        self.assertEqual(report['status'],'FAIL');self.assertFalse(report['qualified'])
        self.assertGreater(next(c['violations'] for c in report['checks'] if c['rule']=='profile.manhattan.m1'),0)


if __name__=='__main__':unittest.main()
