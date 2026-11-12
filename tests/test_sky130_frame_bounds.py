import copy,json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import klayout.db as k
from icstudio import digital_sky130_frame_bounds as checks


class FrameBoundTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'test.gds'
        self.layout=k.Layout();self.layout.dbu=.001;self.top=self.layout.create_cell('control')

    def shapes(self,name,cell=None):return (cell or self.top).shapes(self.layout.layer(*(checks.LAYERS|checks.BOUNDARIES)[name]))
    def box(self,name,bounds,cell=None):self.shapes(name,cell).insert(k.Box(*bounds))
    def audit(self):self.layout.write(str(self.path));return checks.audit(self.path)
    def row(self,report,target='diff',boundary='frame'):
        return next(r for r in report['rows'] if r['target']==target and r['boundary']==boundary)
    def context(self):self.box('frame',(0,0,10000,10000));self.box('die',(7000,3000,8000,4000))

    def test_empty_subjects_do_not_claim_chip_completeness(self):
        r=self.audit();self.assertEqual(len(r['rows']),18);self.assertEqual(r['unreviewed'],0)
        self.assertTrue(all(x['disposition']=='absent-operand' and not x['evaluated'] for x in r['rows']))
        self.assertFalse(r['qualified']);self.assertFalse(r['chunk_complete']);checks.validate_saved(r,self.path)

    def test_missing_context_keeps_all_present_targets_unreviewed(self):
        for name in checks.LAYERS:self.box(name,(3000,3000,4000,4000))
        r=self.audit();self.assertEqual(r['unreviewed'],18)
        self.assertTrue(all(x['reason']=='missing-boundary-context' and x['witness_area_nm2'] is None for x in r['rows']))

    def test_exact_3um_bounds_pass_all_eighteen_nonempty_checks(self):
        self.context()
        for name in checks.LAYERS:self.box(name,(3000,3000,4000,4000))
        r=self.audit();self.assertTrue(all(x['disposition']=='executed-reviewed' for x in r['rows']))
        self.assertTrue(all(x['witness_area_nm2']==0 for x in r['rows']));checks.validate_saved(r,self.path)

    def test_1nm_enclosure_failures_for_every_layer_stay_unreviewed(self):
        self.context()
        for name in checks.LAYERS:
            self.box(name,(2999,3000,4000,4000));r=self.audit();row=self.row(r,name)
            self.assertEqual(row['reason'],'sufficient-bound-not-proven');self.assertGreater(row['witness_area_nm2'],0)
            self.assertEqual(self.row(r,name,'die')['disposition'],'executed-reviewed');self.shapes(name).clear()

    def test_1nm_spacing_failures_for_every_layer_stay_unreviewed(self):
        self.box('frame',(0,0,10000,10000));self.box('die',(6999,3000,8000,4000))
        for name in checks.LAYERS:
            self.box(name,(3000,3000,4000,4000));r=self.audit()
            self.assertEqual(self.row(r,name,'die')['reason'],'sufficient-bound-not-proven')
            self.assertEqual(self.row(r,name)['disposition'],'executed-reviewed');self.shapes(name).clear()

    def test_overlapping_or_contained_target_is_not_spaced_from_die(self):
        self.box('die',(0,0,10000,10000))
        for box in ((1000,1000,2000,2000),(9999,1000,11000,2000),(10000,1000,11000,2000)):
            self.shapes('diff').clear();self.box('diff',box)
            self.assertEqual(self.row(self.audit(),boundary='die')['disposition'],'unreviewed')

    def test_square_corner_bound_does_not_claim_euclidean_violation(self):
        self.box('diff',(0,0,1000,1000));self.box('die',(3500,3500,4500,4500))
        r=self.audit();self.assertEqual(self.row(r,boundary='die')['reason'],'sufficient-bound-not-proven')
        self.assertNotIn('violations',r);checks.evaluate(r,r['gds_sha256'],'control')

    def test_frame_holes_and_concave_corners_are_not_filled_in(self):
        ring=k.Polygon(k.Box(0,0,30000,30000))
        ring.insert_hole([k.Point(10000,10000),k.Point(10000,20000),k.Point(20000,20000),k.Point(20000,10000)])
        self.shapes('frame').insert(ring);self.box('diff',(6000,11000,7000,12000))
        self.assertEqual(self.row(self.audit())['disposition'],'executed-reviewed')
        self.shapes('diff').clear();self.box('diff',(6000,11000,7001,12000))
        self.assertEqual(self.row(self.audit())['disposition'],'unreviewed')

    def test_die_holes_preserve_real_clearance(self):
        ring=k.Polygon(k.Box(0,0,30000,30000))
        ring.insert_hole([k.Point(10000,10000),k.Point(10000,20000),k.Point(20000,20000),k.Point(20000,10000)])
        self.shapes('die').insert(ring);self.box('diff',(13000,13000,17000,17000))
        self.assertEqual(self.row(self.audit(),boundary='die')['disposition'],'executed-reviewed')
        self.shapes('diff').clear();self.box('diff',(12999,13000,17000,17000))
        self.assertEqual(self.row(self.audit(),boundary='die')['disposition'],'unreviewed')

    def test_merged_targets_and_reflected_hierarchy_are_measured(self):
        child=self.layout.create_cell('child');self.box('diff',(0,0,500,1000),child);self.box('diff',(500,0,1000,1000),child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.M90,5000,5000),k.Vector(10000,0),k.Vector(0,10000),2,2))
        self.box('frame',(0,0,20000,20000));r=self.audit()
        self.assertEqual(r['measurements']['layers']['diff']['components'],4)
        self.assertEqual(self.row(r)['disposition'],'executed-reviewed')

    def test_disjoint_frames_do_not_hide_an_uncovered_gap(self):
        self.box('frame',(0,0,10000,10000));self.box('frame',(20000,0,30000,10000))
        self.box('diff',(3000,3000,4000,4000));self.box('diff',(23000,3000,24000,4000))
        self.assertEqual(self.row(self.audit())['disposition'],'executed-reviewed')
        self.box('diff',(4000,3000,23000,4000));self.assertEqual(self.row(self.audit())['disposition'],'unreviewed')

    def test_touching_overlapping_and_duplicate_boundaries_rejected(self):
        for name in checks.BOUNDARIES:
            for second in ((10000,0,20000,10000),(9999,0,20000,10000),(0,0,10000,10000)):
                self.shapes(name).clear();self.box(name,(0,0,10000,10000));self.box(name,second)
                with self.assertRaisesRegex(ValueError,'Touching or overlapping'):self.audit()
            self.shapes(name).clear()

    def test_exact_paths_and_published_text_purposes(self):
        self.box('frame',(-5000,-5000,5000,5000));path=k.Path([k.Point(0,0),k.Point(1000,0)],200)
        self.shapes('diff').insert(path);a=self.audit()['measurements'];self.shapes('diff').clear();self.shapes('diff').insert(path.polygon())
        self.assertEqual(a,self.audit()['measurements'])
        self.shapes('diff').insert(k.Text('annotation',k.Trans()))
        self.assertEqual(self.audit()['measurements']['layers']['diff']['texts'],1)

    def test_names_and_blankings_do_not_apply_unreviewed_exemptions(self):
        self.top.name='s8Fab_crntic_example';self.context();self.box('diff',(0,0,1000,1000))
        self.assertEqual(self.row(self.audit())['disposition'],'unreviewed')

    def test_unsupported_shapes_units_and_transforms_are_rejected(self):
        for name,shape in (('tap',k.Text('bad',k.Trans())),('frame',k.Text('bad',k.Trans())),
                          ('diff',k.Path([k.Point(0,0),k.Point(1000,0)],199)),
                          ('diff',k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(0,1000)]))):
            self.shapes(name).insert(shape)
            with self.assertRaises(ValueError):self.audit()
            self.shapes(name).clear()
        self.layout.dbu=.002
        with self.assertRaises(ValueError):checks.measure(self.layout)
        self.layout.dbu=.001;child=self.layout.create_cell('child');self.box('diff',(0,0,1000,1000),child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.ICplxTrans(2,0,False,0,0)))
        with self.assertRaises(ValueError):self.audit()

    def test_stale_report_rebound_to_changed_layout_is_rejected(self):
        self.context();self.box('diff',(3000,3000,4000,4000));r=self.audit()
        self.box('diff',(0,0,1000,1000));r['gds_sha256']=self.audit()['gds_sha256']
        with self.assertRaises(ValueError):checks.validate_saved(r,self.path)

    def test_missing_duplicate_changed_and_false_execution_reports_rejected(self):
        self.box('diff',(0,0,1000,1000));r=self.audit()
        for edit in (lambda x:x['rows'].pop(),lambda x:x['rows'].append(x['rows'][0]),
            lambda x:x['measurements']['bounds']['r988'].update(evaluated=True),
            lambda x:x['measurements']['bounds']['r988'].update(witness_area_nm2=0),
            lambda x:x['measurements']['layers']['frame'].update(components=True),lambda x:x.update(qualified=True)):
            altered=copy.deepcopy(r);edit(altered)
            with self.assertRaises(ValueError):checks.evaluate(altered,r['gds_sha256'],'control')

    def test_exact_source_and_catalog_bindings(self):
        from scripts import sky130_frame_bound_review as review
        with TemporaryDirectory() as td:
            folder=Path(td)/'inputs';review.delivery.fixture.unpack(review.delivery.fixture.BUNDLE,folder)
            catalog=json.loads((review.ROOT/review.delivery.queue.CATALOG).read_bytes())
            proof=review.source_proof(folder/'sources',catalog);self.assertEqual(len(proof['bindings']),18)
            next(r for r in catalog['rows'] if r['id']=='r988')['description']='wrong target'
            with self.assertRaises(ValueError):review.source_proof(folder/'sources',catalog)


if __name__=='__main__':unittest.main()
