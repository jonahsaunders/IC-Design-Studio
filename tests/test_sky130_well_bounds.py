import copy,json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import klayout.db as k
from icstudio import digital_sky130_well_bounds as checks


class WellBoundTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'test.gds'
        self.layout=k.Layout();self.layout.dbu=.001;self.top=self.layout.create_cell('control')

    def shapes(self,name,cell=None):return (cell or self.top).shapes(self.layout.layer(*checks.LAYERS[name]))
    def box(self,name,bounds,cell=None):self.shapes(name,cell).insert(k.Box(*bounds))
    def audit(self):self.layout.write(str(self.path));return checks.audit(self.path)
    def row(self,r,key):return next(x for x in r['rows'] if x['id']==key)
    def holes(self,gap=840):
        ring=k.Polygon(k.Box(0,0,10000,10000))
        for b in ((1000,1000,2000,2000),(2000+gap,1000,3000+gap,2000)):
            ring.insert_hole(list(k.Polygon(k.Box(*b)).each_point_hull()))
        self.shapes('pwbm').insert(ring)

    def test_empty_targets_are_not_process_qualification(self):
        r=self.audit();self.assertEqual(r['unreviewed'],0)
        self.assertTrue(all(x['disposition']=='absent-operand' for x in r['rows']))
        self.assertFalse(r['qualified']);self.assertFalse(r['chunk_complete']);checks.validate_saved(r,self.path)

    def test_all_three_nonempty_bounds_pass_at_exact_limits(self):
        self.holes();self.box('pwde',(1000,1000,2000,2000));self.box('dnwell',(0,0,3000,3000))
        self.box('uhvi',(0,0,10000,10000));r=self.audit()
        self.assertEqual(r['measurements']['holes'],2)
        self.assertTrue(all(x['disposition']=='executed-reviewed' and x['witness_area_nm2']==0 for x in r['rows']))
        checks.validate_saved(r,self.path)

    def test_1nm_pwde_enclosure_failure_on_each_side_of_each_required_layer(self):
        self.box('pwde',(1000,1000,2000,2000))
        for name in ('dnwell','uhvi'):
            for bounds in ((1,0,3000,3000),(0,1,3000,3000),(0,0,2999,3000),(0,0,3000,2999)):
                for context in ('dnwell','uhvi'):
                    self.shapes(context).clear();self.box(context,bounds if context==name else (0,0,3000,3000))
                row=self.row(self.audit(),'r923');self.assertEqual(row['disposition'],'unreviewed')
                self.assertGreater(row['witness_area_nm2'],0)

    def test_missing_enclosing_layers_never_waive_present_targets(self):
        self.box('pwde',(0,0,1000,1000));self.box('pwbm',(0,0,1000,1000))
        r=self.audit()
        for key in ('r923','r931'):self.assertEqual(self.row(r,key)['disposition'],'unreviewed')
        self.box('uhvi',(-1000,-1000,2000,2000))
        self.assertEqual(self.row(self.audit(),'r923')['disposition'],'unreviewed')

    def test_hole_spacing_1nm_failure_and_exact_equality(self):
        for gap,status in ((839,'unreviewed'),(840,'executed-reviewed'),(841,'executed-reviewed')):
            self.shapes('pwbm').clear();self.holes(gap)
            self.assertEqual(self.row(self.audit(),'r924')['disposition'],status)

    def test_pwbm_enclosure_1nm_failure_and_exact_equality(self):
        self.box('pwbm',(0,0,1000,1000));self.box('uhvi',(0,0,1000,1000))
        self.assertEqual(self.row(self.audit(),'r931')['disposition'],'executed-reviewed')
        self.shapes('uhvi').clear();self.box('uhvi',(0,0,999,1000))
        self.assertEqual(self.row(self.audit(),'r931')['disposition'],'unreviewed')

    def test_square_diagonal_spacing_is_conservative(self):
        ring=k.Polygon(k.Box(0,0,10000,10000))
        for b in ((1000,1000,2000,2000),(2700,2700,3700,3700)):
            ring.insert_hole(list(k.Polygon(k.Box(*b)).each_point_hull()))
        self.shapes('pwbm').insert(ring);r=self.audit()
        self.assertEqual(self.row(r,'r924')['reason'],'sufficient-bound-not-proven');self.assertNotIn('violations',r)

    def test_merged_pwbm_ring_is_a_hole_but_open_notch_is_not(self):
        for b in ((0,0,5000,1000),(0,1000,1000,5000),(4000,1000,5000,5000)):
            self.box('pwbm',b)
        self.assertEqual(self.audit()['measurements']['holes'],0)
        self.box('pwbm',(1000,4000,4000,5000))
        r=self.audit();self.assertEqual(r['measurements']['holes'],1)
        self.assertEqual(self.row(r,'r924')['disposition'],'absent-operand')

    def test_nested_hole_hulls_do_not_hide_close_spacing(self):
        outer=k.Polygon(k.Box(0,0,10000,10000))
        outer.insert_hole(list(k.Polygon(k.Box(1000,1000,9000,9000)).each_point_hull()))
        inner=k.Polygon(k.Box(2000,2000,8000,8000))
        inner.insert_hole(list(k.Polygon(k.Box(2100,2100,7900,7900)).each_point_hull()))
        self.shapes('pwbm').insert(outer);self.shapes('pwbm').insert(inner)
        r=self.audit();self.assertEqual(r['measurements']['holes'],2)
        self.assertEqual(self.row(r,'r924')['disposition'],'unreviewed')

    def test_holes_in_enclosing_regions_are_preserved(self):
        self.box('pwde',(1000,1000,2000,2000));self.box('pwbm',(1000,1000,2000,2000))
        self.box('dnwell',(0,0,4000,4000));ring=k.Polygon(k.Box(0,0,4000,4000))
        ring.insert_hole(list(k.Polygon(k.Box(1500,1500,1600,1600)).each_point_hull()))
        self.shapes('uhvi').insert(ring);r=self.audit()
        for key in ('r923','r931'):self.assertEqual(self.row(r,key)['disposition'],'unreviewed')

    def test_all_holes_before_uhvi_selection_and_no_named_exemptions(self):
        self.holes(839);self.box('uhvi',(0,0,1,1))
        self.top.name='LOWVTID_exempt'
        r=self.audit()
        for key in ('r924','r931'):self.assertEqual(self.row(r,key)['disposition'],'unreviewed')

    def test_reflected_array_and_merged_inputs(self):
        child=self.layout.create_cell('child');self.box('pwde',(0,0,500,1000),child);self.box('pwde',(500,0,1000,1000),child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.M90,5000,5000),k.Vector(10000,0),k.Vector(0,10000),2,2))
        for name in ('dnwell','uhvi'):self.box(name,(0,0,20000,20000))
        r=self.audit();self.assertEqual(r['measurements']['layers']['pwde']['components'],4)
        self.assertEqual(self.row(r,'r923')['disposition'],'executed-reviewed')

    def test_exact_paths_match_polygon_conversion(self):
        path=k.Path([k.Point(0,0),k.Point(1000,0)],200)
        self.shapes('pwbm').insert(path);a=self.audit()['measurements'];self.shapes('pwbm').clear()
        self.shapes('pwbm').insert(path.polygon());self.assertEqual(a,self.audit()['measurements'])

    def test_unsupported_text_paths_geometry_and_units_fail_closed(self):
        for name in checks.LAYERS:
            for shape in (k.Text('geometry?',k.Trans()),k.Path([k.Point(0,0),k.Point(1000,0)],199),
                          k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(0,1000)])):
                self.shapes(name).insert(shape)
                with self.assertRaises(ValueError):self.audit()
                self.shapes(name).clear()
        self.layout.dbu=.002
        with self.assertRaises(ValueError):checks.measure(self.layout)

    def test_scaled_or_rotated_instances_and_multiple_tops_rejected(self):
        child=self.layout.create_cell('child');self.box('pwbm',(0,0,1000,1000),child)
        for trans in (k.ICplxTrans(2,0,False,0,0),k.ICplxTrans(1,45,False,0,0)):
            self.top.insert(k.CellInstArray(child.cell_index(),trans))
            with self.assertRaises(ValueError):self.audit()
            self.top.clear_insts()
        with self.assertRaises(ValueError):self.audit()

    def test_stale_report_rebound_to_changed_layout_rejected(self):
        r=self.audit();self.box('pwde',(0,0,1000,1000));r['gds_sha256']=self.audit()['gds_sha256']
        with self.assertRaises(ValueError):checks.validate_saved(r,self.path)

    def test_incomplete_changed_or_falsely_qualified_evidence_rejected(self):
        r=self.audit()
        for edit in (lambda x:x['rows'].pop(),lambda x:x['rows'].append(x['rows'][0]),
            lambda x:x['measurements']['bounds'].update(r923=1),lambda x:x['measurements'].update(holes=True),
            lambda x:x['measurements']['layers']['pwde'].update(components=1),lambda x:x.update(qualified=True)):
            changed=copy.deepcopy(r);edit(changed)
            with self.assertRaises(ValueError):checks.evaluate(changed,r['gds_sha256'],'control')
        with self.assertRaises(ValueError):checks.evaluate(None,r['gds_sha256'],'control')

    def test_source_catalog_and_manual_context_are_bound(self):
        from scripts import sky130_well_bound_review as review
        with TemporaryDirectory() as td:
            folder=Path(td)/'inputs';review.delivery.fixture.unpack(review.delivery.fixture.BUNDLE,folder)
            catalog=json.loads((review.ROOT/review.delivery.queue.CATALOG).read_bytes())
            proof=review.source_proof(folder/'sources',catalog);self.assertEqual(len(proof['bindings']),3)
            next(r for r in catalog['rows'] if r['id']=='r923')['description']='wrong target'
            with self.assertRaises(ValueError):review.source_proof(folder/'sources',catalog)


if __name__=='__main__':unittest.main()
