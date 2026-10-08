"""Written GDS controls for checks missing from the pinned native GF180 deck."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import klayout.db as k
from scripts import check_gf180_fill as fill


class FillChecksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.layout = k.Layout(); self.layout.dbu = .001
        self.top = self.layout.create_cell('coupon')
        self.shape(63, 0, (0, 0, 100000, 100000))

    def shape(self, layer, datatype, box):
        self.top.shapes(self.layout.layer(layer, datatype)).insert(k.Box(*box))

    def inspect(self, bounds=(0, 0, 100, 100), variant='C'):
        path = self.root/'coupon.gds'; self.layout.write(str(path))
        return fill.inspect(path, bounds, top_name='coupon', variant=variant)

    def failed(self, report, rule, layer):
        return any(x['rule'] == rule and x['layer'] == layer and x['status'] == 'failed' for x in report['checks'])

    def test_absent_layers_are_density_failures(self):
        report = self.inspect()
        self.assertEqual(report['failed_checks'], 7)
        self.assertTrue(all(self.failed(report, 'global-density', n) for n in fill.LAYERS))
        self.assertFalse(report['qualified'])

    def test_correct_size_controls_and_corresponding_faults(self):
        for layer, name, size, rule in [(22,'comp',5000,'DCF.1c/10'),
                (30,'poly',5600,'DPF.1/10'),(34,'m1',2000,'DM.1')]:
            with self.subTest(layer=name):
                self.layout.clear_layer(self.layout.layer(layer,4))
                self.shape(layer,4,(50000,50000,50000+size,50000+size))
                self.assertFalse(self.failed(self.inspect(),rule,name))
                self.layout.clear_layer(self.layout.layer(layer,4))
                self.shape(layer,4,(50000,50000,51000,51000))
                self.assertTrue(self.failed(self.inspect(),rule,name))

    def test_dummy_poly_must_match_comp_but_comp_can_exist_alone(self):
        self.shape(22,4,(50000,50000,55000,55000))
        self.assertFalse(self.failed(self.inspect(),'DPF.1-enclosure','poly'))
        self.shape(30,4,(49700,49700,55300,55300))
        self.assertFalse(self.failed(self.inspect(),'DPF.1-enclosure','poly'))
        self.layout.clear_layer(self.layout.layer(22,4))
        self.assertTrue(self.failed(self.inspect(),'DPF.1-enclosure','poly'))

    def test_metal_spacing_limit_and_overlap_are_detected(self):
        self.shape(34,4,(20000,20000,22000,22000))
        for gap, failed in [(2000,False),(1995,True),(0,True),(-1000,True)]:
            with self.subTest(gap=gap):
                self.layout.clear_layer(self.layout.layer(34,0))
                self.shape(34,0,(22000+gap,20000,26000+gap,22000))
                self.assertEqual(self.failed(self.inspect(),'DM.3','m1'),failed)

    def test_dummy_spacing_and_grid_faults_are_detected(self):
        self.shape(34,4,(20000,20000,22000,22000))
        self.shape(34,4,(22975,20000,24975,22000))
        self.assertTrue(self.failed(self.inspect(),'DM.2b','m1'))
        self.shape(81,4,(20001,20000,22001,22000))
        self.assertTrue(self.failed(self.inspect(),'5-nm-grid','m5'))

    def test_density_is_union_of_circuit_and_dummy_including_poly(self):
        self.shape(30,0,(10000,10000,15000,15000))
        self.shape(30,4,(10000,10000,15600,15600))
        self.assertAlmostEqual(self.inspect()['density']['poly']['total_percent'],.3136)

    def test_empty_die_margins_remain_in_density_denominator(self):
        self.shape(34,0,(0,0,60000,50000))
        report=self.inspect(bounds=(0,0,200,200))
        self.assertAlmostEqual(report['density']['m1']['total_percent'],7.5)
        self.assertEqual(report['geometry_extent_um'],[0,0,100,100])

    def test_extent_and_stack_mismatch_rejected(self):
        for bounds in [(0,0,50,50),(0,0,100.0001,100),(0,0,float('nan'),100),(100,0,0,100)]:
            with self.subTest(bounds=bounds), self.assertRaises(ValueError): self.inspect(bounds)
        with self.assertRaisesRegex(ValueError,'five-metal'): self.inspect(variant='A')
        self.shape(53,0,(10000,10000,15000,15000))
        with self.assertRaisesRegex(ValueError,'sixth metal'): self.inspect()

    def test_density_passing_layout_does_not_claim_complete_qualification(self):
        for layer in fill.LAYERS.values(): self.shape(layer,0,(0,0,60000,50000))
        for variant in ('C','D'):
            report=self.inspect(variant=variant)
            self.assertEqual(report['status'],'checks_passed_coverage_incomplete')
            self.assertFalse(report['qualified']); self.assertTrue(report['unqualified_requirements'])

    def test_well_clearance_applies_inside_outside_and_across_boundary(self):
        for variant in ('C', 'D'):
            for dummy_layer, name, size, prefix, distances in (
                    (22, 'comp', 5000, 'DCF', (1300, 4000, 1300, 1300)),
                    (30, 'poly', 5600, 'DPF', (1000, 2000, 1000, 1000))):
                self.shape(dummy_layer, 4, (40000,40000,40000+size,40000+size))
                for suffix, well_layer, distance in zip('abcd', (21,12,204,55), distances):
                    examples = [
                        ('outside-limit', (20000,20000,40000-distance,80000), False),
                        ('outside-short', (20000,20000,40005-distance,80000), True),
                        ('inside-limit', (40000-distance,40000-distance,
                                          40000+size+distance,40000+size+distance), False),
                        ('inside-short', (40005-distance,40000-distance,
                                          40000+size+distance,40000+size+distance), True),
                        ('crossing', (20000,20000,42000,80000), True),
                        ('touching', (20000,20000,40000,80000), True),
                    ]
                    for label, box, expected in examples:
                        with self.subTest(variant=variant, dummy=name, well=well_layer, case=label):
                            self.layout.clear_layer(self.layout.layer(well_layer,0))
                            self.shape(well_layer,0,box)
                            self.assertEqual(self.failed(self.inspect(variant=variant),
                                f'{prefix}.6{suffix}',name),expected)
                    self.layout.clear_layer(self.layout.layer(well_layer,0))
                self.layout.clear_layer(self.layout.layer(dummy_layer,4))

    def test_well_hole_boundary_is_checked(self):
        self.shape(22,4,(40000,40000,45000,45000))
        for gap, expected in ((1300,False),(1295,True)):
            with self.subTest(gap=gap):
                index=self.layout.layer(21,0);self.layout.clear_layer(index)
                ring=k.Region(k.Box(20000,20000,80000,80000))-k.Region(
                    k.Box(40000-gap,40000-gap,45000+gap,45000+gap))
                self.top.shapes(index).insert(ring)
                self.assertEqual(self.failed(self.inspect(),'DCF.6a','comp'),expected)

    def test_diagonal_well_clearance_uses_physical_distance(self):
        self.shape(22,4,(20000,20000,25000,25000))
        # The perpendicular distance to x+y=c is delta/sqrt(2).
        # Both controls stay on the 5 nm grid and bracket 1.3 um.
        for inside in (True,False):
            for delta,expected in ((1840,False),(1830,True)):
                with self.subTest(inside=inside,delta=delta):
                    c=50000+delta if inside else 40000-delta
                    index=self.layout.layer(21,0);self.layout.clear_layer(index)
                    self.top.shapes(index).insert(k.Polygon([k.Point(0,0),k.Point(c,0),k.Point(0,c)]))
                    self.assertEqual(self.failed(self.inspect(),'DCF.6a','comp'),expected)

    def test_marker_clearances_and_contained_fill_are_detected(self):
        # Independent expected distances from the pinned DCF/DPF/DM tables.
        cases=[
            (22,'comp',5000,'DCF.8a','RES_MK',110,5,3500),
            (22,'comp',5000,'DCF.11a','NDMY',111,5,3500),
            (22,'comp',5000,'DCF.12/13-exclusion','IND_MK',151,5,3000),
            (30,'poly',5600,'DPF.8','RES_MK',110,5,19700),
            (30,'poly',5600,'DPF.9','Pad',37,0,6700),
            (30,'poly',5600,'DPF.11','NDMY',111,5,29700),
            (30,'poly',5600,'DPF.14/15','IND_MK',151,5,3000),
            (30,'poly',5600,'DPF.16/17','MTPMARK',122,5,3000),
            (30,'poly',5600,'DPF.18/19','PMNDMY',152,5,8000),
        ]
        for number,name in ((34,'m1'),(36,'m2'),(42,'m3'),(46,'m4'),(81,'m5')):
            for marker,layer,datatype in (('FuseTop',75,0),('POLYFUSE',220,0),
                    ('FuseWindow_D',96,1),('PMNDMY',152,5),('MTPMARK',122,5),('OTP_MK',173,5)):
                cases.append((number,name,2000,'DM.8',marker,layer,datatype,6000))
        for variant in ('C','D'):
            for number,name,size,rule,marker,layer,datatype,distance in cases:
                self.shape(number,4,(20000,20000,20000+size,20000+size))
                right=20000+size
                for label,box,expected in (
                        ('limit',(right+distance,20000,right+distance+7000,27000),False),
                        ('short',(right+distance-5,20000,right+distance+6995,27000),True),
                        ('touch',(right,20000,right+7000,27000),True),
                        ('contained',(19000,19000,right+1000,20000+size+1000),True)):
                    with self.subTest(variant=variant, dummy=name, rule=rule, marker=marker, case=label):
                        index=self.layout.layer(layer,datatype);self.layout.clear_layer(index)
                        self.shape(layer,datatype,box)
                        checks=[c for c in self.inspect(variant=variant)['checks']
                                if c['rule']==rule and c['layer']==name and c.get('exclusion_layer')==marker]
                        self.assertEqual(len(checks),1)
                        self.assertEqual(checks[0]['status']=='failed',expected)
                self.layout.clear_layer(self.layout.layer(layer,datatype))
                self.layout.clear_layer(self.layout.layer(number,4))

    def test_wrong_layer_identity_cannot_be_reported_as_absent(self):
        with mock.patch.dict(fill.MARKERS, {'NDMY': (111, 0)}):
            with self.assertRaisesRegex(ValueError,'layer map'):
                self.inspect()


if __name__ == '__main__': unittest.main()
