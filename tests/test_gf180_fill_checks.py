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
        for layer in fill.LAYERS.values(): self.shape(layer,0,(0,0,60000,52000))
        for variant in ('C','D'):
            report=self.inspect(variant=variant)
            self.assertEqual(report['status'],'checks_passed_coverage_incomplete')
            self.assertFalse(report['qualified']); self.assertTrue(report['unqualified_requirements'])

    def test_metal_global_density_is_strictly_greater_than_thirty_percent(self):
        for variant in ('C','D'):
            for name,layer in (('m1',34),('m2',36),('m3',42),('m4',46),('m5',81)):
                for delta,expected in ((-5,True),(0,True),(5,False)):
                    with self.subTest(variant=variant,layer=name,delta=delta):
                        self.layout.clear_layer(self.layout.layer(layer,0))
                        self.shape(layer,0,(0,0,60000+delta,50000))
                        report=self.inspect(variant=variant)
                        self.assertEqual(self.failed(report,'global-density',name),expected)
                        self.assertFalse(report['density'][name]['lower_limit_inclusive'])
                self.layout.clear_layer(self.layout.layer(layer,0))
            for name,layer,width in (('comp',22,50000),('poly',30,28000)):
                self.shape(layer,0,(0,0,width,50000))
                report=self.inspect(variant=variant)
                self.assertFalse(self.failed(report,'global-density',name))
                self.assertTrue(report['density'][name]['lower_limit_inclusive'])
                self.layout.clear_layer(self.layout.layer(layer,0))

    def test_density_keeps_half_database_unit_polygon_area(self):
        self.shape(34,0,(0,0,60000,50000))
        self.top.shapes(self.layout.layer(34,0)).insert(k.Polygon(
            [k.Point(70000,70000),k.Point(70001,70000),k.Point(70000,70001)]))
        report=self.inspect()
        self.assertGreater(report['density']['m1']['total_percent'],30)
        self.assertFalse(self.failed(report,'global-density','m1'))
        self.assertEqual(report['metal_density_windows']['m1']['windows'][0]['material_area_um2'],3000.0000005)

    def test_anchored_density_windows_match_independent_rectangle_union(self):
        self.layout.clear_layer(self.layout.layer(63,0))
        bounds=(10,20,460,370)
        self.shape(63,0,tuple(v*1000 for v in bounds))
        a=(10,20,210,220);b=(110,120,310,320);overlap=(110,120,210,220)
        for datatype,box in ((0,a),(4,b)):
            self.shape(34,datatype,tuple(v*1000 for v in box))
        def clipped_area(rect,window):
            return max(0,min(rect[2],window[2])-max(rect[0],window[0]))*max(0,min(rect[3],window[3])-max(rect[1],window[1]))
        for variant in ('C','D'):
            report=self.inspect(bounds=bounds,variant=variant)
            data=report['metal_density_windows']['m1']
            self.assertEqual(data['anchor_um'],[10,20])
            self.assertEqual((data['full_windows'],data['partial_windows']),(6,14))
            expected_bounds=[(x,y,min(x+200,460),min(y+200,370))
                for y in (20,120,220,320) for x in (10,110,210,310,410)]
            self.assertEqual([tuple(r['bounds_um']) for r in data['windows']],expected_bounds)
            for measured,window in zip(data['windows'],expected_bounds):
                area=clipped_area(a,window)+clipped_area(b,window)-clipped_area(overlap,window)
                self.assertEqual(measured['material_area_um2'],area)
                self.assertAlmostEqual(measured['measured_percent'],100*area/((window[2]-window[0])*(window[3]-window[1])))
            self.assertIsNone(data['local_limits_percent'])
            self.assertEqual(data['status'],'measured_acceptance_unqualified')
            self.assertTrue(all(r['measured_percent']==0 for r in report['metal_density_windows']['m5']['windows']))
            self.assertFalse(report['qualified'])

    def test_small_die_does_not_claim_a_full_density_window(self):
        report=self.inspect()
        for data in report['metal_density_windows'].values():
            self.assertEqual((data['full_windows'],data['partial_windows']),(0,1))
            self.assertEqual(data['windows'][0]['area_um2'],10000)
            self.assertEqual(data['status'],'measured_acceptance_unqualified')
        with mock.patch.object(fill,'MAX_WINDOWS_PER_LAYER',0):
            with self.assertRaisesRegex(ValueError,'window budget'):self.inspect()

    def test_adjacent_layer_spacing_includes_circuit_and_dummy_material(self):
        # Independent table order: Poly2, M1, M2, M3, M4, M5; no sixth metal.
        stack=[('poly',30),('m1',34),('m2',36),('m3',42),('m4',46),('m5',81)]
        for variant in ('C','D'):
            for index,(name,layer) in enumerate(stack[1:],1):
                adjacent=[('DM.5/7',stack[index-1])]
                if index<5:adjacent.append(('DM.4/6',stack[index+1]))
                self.shape(layer,4,(40000,40000,42000,42000))
                for rule,(other,target_layer) in adjacent:
                    for datatype in (0,4):
                        for label,gap,expected in (('limit',1000,False),('short',995,True),
                                ('touch',0,True),('overlap',-1000,True),('contained',-2500,True)):
                            with self.subTest(variant=variant,layer=name,target=other,datatype=datatype,case=label):
                                target=self.layout.layer(target_layer,datatype);self.layout.clear_layer(target)
                                box=(42000+gap,40000,44000+gap,42000)
                                if label=='contained':box=(39000,39000,43000,43000)
                                self.shape(target_layer,datatype,box)
                                self.assertEqual(self.failed(self.inspect(variant=variant),rule,name),expected)
                        self.layout.clear_layer(self.layout.layer(target_layer,datatype))
                self.layout.clear_layer(self.layout.layer(layer,4))

    def test_adjacent_layer_diagonal_clearance_and_nonadjacent_control(self):
        self.shape(34,4,(20000,20000,22000,22000))
        for datatype in (0,4):
            index=self.layout.layer(36,datatype)
            for delta,expected in ((1420,False),(1410,True)):
                with self.subTest(datatype=datatype,delta=delta):
                    self.layout.clear_layer(index);c=40000-delta
                    self.top.shapes(index).insert(k.Polygon([k.Point(0,0),k.Point(c,0),k.Point(0,c)]))
                    self.assertEqual(self.failed(self.inspect(),'DM.4/6','m1'),expected)
            self.layout.clear_layer(index)
        self.shape(42,4,(20000,20000,22000,22000))
        report=self.inspect()
        self.assertFalse(self.failed(report,'DM.4/6','m1'))
        self.assertFalse(self.failed(report,'DM.5/7','m1'))

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
        with mock.patch.dict(fill.LAYERS, {'m1': 36}):
            with self.assertRaisesRegex(ValueError,'layer map'):
                self.inspect()

    def test_unsupported_vendor_memory_layers_are_not_mtpmark_aliases(self):
        for variant in ('C','D'):
            for name,number in (('MCELL_FEOL_MK',11),('YMTP_MK',86)):
                for datatype,expected in ((0,False),(5,False),(17,True)):
                    with self.subTest(variant=variant,name=name,datatype=datatype):
                        self.shape(number,datatype,(10000,10000,15000,15000))
                        result=self.inspect(variant=variant)
                        self.assertEqual(self.failed(result,'unsupported-memory-layer',name),expected)
                        self.layout.clear_layer(self.layout.layer(number,datatype))
            self.shape(122,5,(10000,10000,15000,15000))
            result=self.inspect(variant=variant)
            self.assertFalse(any(c['status']=='failed' for c in result['checks']
                if c['rule']=='unsupported-memory-layer'))
            self.layout.clear_layer(self.layout.layer(122,5))
        with mock.patch.dict(fill.UNSUPPORTED_MEMORY,{'YMTP_MK':(86,0)}):
            with self.assertRaisesRegex(ValueError,'layer map'):self.inspect()

    def test_marker_width_is_per_layer_and_includes_narrow_legs(self):
        for variant in ('C','D'):
            for name,layer,other in (('NDMY',111,152),('PMNDMY',152,111)):
                for width,expected in ((795,True),(800,False),(805,False)):
                    for transpose in (False,True):
                        with self.subTest(variant=variant,name=name,width=width,transpose=transpose):
                            w,h=(5000,width) if transpose else (width,5000)
                            self.shape(layer,5,(10000,10000,10000+w,10000+h))
                            # A valid marker of the other type must not mask it.
                            self.shape(other,5,(9000,9000,16000,16000))
                            result=self.inspect(variant=variant)
                            self.assertEqual(self.failed(result,'DE.2',name),expected)
                            self.layout.clear_layer(self.layout.layer(layer,5))
                            self.layout.clear_layer(self.layout.layer(other,5))
                polygon=k.Polygon([k.Point(10000,10000),k.Point(15000,10000),
                    k.Point(15000,15000),k.Point(14000,15000),k.Point(14000,10795),k.Point(10000,10795)])
                self.top.shapes(self.layout.layer(layer,5)).insert(polygon)
                self.assertTrue(self.failed(self.inspect(variant=variant),'DE.2',name))
                self.layout.clear_layer(self.layout.layer(layer,5))

    def test_ndmy_spacing_boundary_notch_merge_and_pmndmy_independence(self):
        for variant in ('C','D'):
            for gap,expected in ((19995,True),(20000,False),(20005,False),(-1000,False)):
                with self.subTest(variant=variant,gap=gap):
                    self.shape(111,5,(10000,10000,15000,15000))
                    self.shape(111,5,(15000+gap,10000,20000+gap,15000))
                    self.assertEqual(self.failed(self.inspect(variant=variant),'DE.4','NDMY'),expected)
                    self.layout.clear_layer(self.layout.layer(111,5))
            self.shape(111,5,(10000,10000,15000,15000))
            self.shape(152,5,(16000,10000,21000,15000))
            self.assertFalse(self.failed(self.inspect(variant=variant),'DE.4','NDMY'))
            self.layout.clear_layer(self.layout.layer(111,5));self.layout.clear_layer(self.layout.layer(152,5))
            ring=k.Region(k.Box(10000,10000,50000,50000))-k.Region(k.Box(25000,20000,35000,45000))
            self.top.shapes(self.layout.layer(111,5)).insert(ring)
            self.assertTrue(self.failed(self.inspect(variant=variant),'DE.4','NDMY'))
            self.layout.clear_layer(self.layout.layer(111,5))

    def test_ndmy_area_exception_boundaries_union_and_large_nonrectangles(self):
        self.layout.clear_layer(self.layout.layer(63,0));self.shape(63,0,(0,0,400000,400000))
        for variant in ('C','D'):
            for width,height,expected in ((100000,150000,False),(100005,150000,True),
                    (80000,200000,False),(80005,200000,True),(200000,80000,False),
                    (200000,80005,True)):
                with self.subTest(variant=variant,width=width,height=height):
                    self.shape(111,5,(10000,10000,10000+width,10000+height))
                    result=self.inspect(bounds=(0,0,400,400),variant=variant)
                    self.assertEqual(self.failed(result,'DE.3','NDMY'),expected)
                    self.assertFalse(self.failed(result,'DE.3-geometry-coverage','NDMY'))
                    self.layout.clear_layer(self.layout.layer(111,5))
            # Two individually small rectangles merge into one invalid marker.
            self.shape(111,5,(10000,10000,90000,110000))
            self.shape(111,5,(80000,10000,180000,110000))
            self.assertTrue(self.failed(self.inspect(bounds=(0,0,400,400),variant=variant),'DE.3','NDMY'))
            self.layout.clear_layer(self.layout.layer(111,5))
            # Bounding area must not replace actual polygon area.
            shape=k.Region(k.Box(10000,10000,210000,210000))-k.Region(k.Box(20000,20000,200000,200000))
            self.top.shapes(self.layout.layer(111,5)).insert(shape)
            result=self.inspect(bounds=(0,0,400,400),variant=variant)
            self.assertFalse(self.failed(result,'DE.3','NDMY'))
            self.assertFalse(self.failed(result,'DE.3-geometry-coverage','NDMY'))
            self.layout.clear_layer(self.layout.layer(111,5))
            shape=k.Region(k.Box(10000,10000,210000,210000))-k.Region(k.Box(100000,100000,120000,120000))
            self.top.shapes(self.layout.layer(111,5)).insert(shape)
            result=self.inspect(bounds=(0,0,400,400),variant=variant)
            self.assertTrue(self.failed(result,'DE.3-geometry-coverage','NDMY'))
            self.assertEqual(result['exclusion_geometry'][0]['status'],'unqualified_nonrectangular_exception')
            self.assertFalse(result['qualified'])
            self.layout.clear_layer(self.layout.layer(111,5))


if __name__ == '__main__': unittest.main()
