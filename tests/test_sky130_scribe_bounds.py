import copy,json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import klayout.db as k
from icstudio import digital_sky130_scribe_bounds as checks


class ScribeBoundTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'test.gds'
        self.layout=k.Layout();self.layout.dbu=.001;self.top=self.layout.create_cell('control')

    def shapes(self,name,cell=None):return (cell or self.top).shapes(self.layout.layer(*checks.LAYERS[name]))
    def box(self,name,bounds,cell=None):self.shapes(name,cell).insert(k.Box(*bounds))
    def audit(self):self.layout.write(str(self.path));return checks.audit(self.path)
    def row(self,r,name='diff'):return next(x for x in r['rows'] if x['target']==name)

    def test_empty_layers_are_separate_from_nonempty_bounds(self):
        r=self.audit();self.assertEqual(len(r['rows']),14);self.assertEqual(r['unreviewed'],0)
        self.assertTrue(all(x['disposition']=='absent-operand' for x in r['rows']))
        self.assertFalse(r['qualified']);self.assertFalse(r['chunk_complete']);checks.validate_saved(r,self.path)

    def test_all_fourteen_layers_pass_1nm_below_limit(self):
        for name in checks.LAYERS:self.box(name,(0,0,9999,10000))
        r=self.audit();self.assertTrue(all(x['disposition']=='executed-reviewed' and x['max_short_span_nm']==9999 for x in r['rows']))
        checks.validate_saved(r,self.path)

    def test_exact_10um_and_1nm_above_remain_candidates_on_every_layer(self):
        for name in checks.LAYERS:
            for size in (10000,10001):
                self.shapes(name).clear();self.box(name,(0,0,size,size));row=self.row(self.audit(),name)
                self.assertEqual(row['disposition'],'unreviewed');self.assertEqual(row['candidates'],1)
            self.shapes(name).clear()

    def test_either_axis_may_supply_the_global_bound(self):
        for bounds in ((0,0,100000,9999),(0,0,9999,100000)):
            self.shapes('diff').clear();self.box('diff',bounds)
            self.assertEqual(self.row(self.audit())['disposition'],'executed-reviewed')

    def test_far_apart_small_features_do_not_use_the_top_bbox(self):
        self.box('diff',(0,0,5000,5000));self.box('diff',(100000,100000,105000,105000))
        r=self.audit();self.assertEqual(r['measurements']['diff']['components'],2)
        self.assertEqual(self.row(r)['disposition'],'executed-reviewed')

    def test_abutting_fragments_are_merged_before_measuring(self):
        self.box('diff',(0,0,5000,10000));self.box('diff',(5000,0,10000,10000))
        r=self.audit();self.assertEqual(r['measurements']['diff']['components'],1)
        self.assertEqual(self.row(r)['disposition'],'unreviewed')

    def test_overlapping_fragments_and_duplicate_shapes_are_merged(self):
        for b in ((0,0,6000,10000),(4000,0,10000,10000),(0,0,6000,10000)):self.box('diff',b)
        r=self.audit();self.assertEqual(r['measurements']['diff']['area_nm2'],100000000)
        self.assertEqual(self.row(r)['candidates'],1)

    def test_corner_touching_fragments_do_not_hide_a_candidate(self):
        self.box('diff',(0,0,5000,5000));self.box('diff',(5000,5000,10000,10000))
        self.assertEqual(self.row(self.audit())['disposition'],'unreviewed')

    def test_thin_l_and_hollow_ring_are_unreviewed_not_violations(self):
        self.box('diff',(0,0,10000,100));self.box('diff',(0,0,100,10000))
        r=self.audit();self.assertEqual(self.row(r)['reason'],'wide-candidate-needs-context');self.assertNotIn('violations',r)
        self.shapes('diff').clear();ring=k.Polygon(k.Box(0,0,10000,10000))
        ring.insert_hole(list(k.Polygon(k.Box(100,100,9900,9900)).each_point_hull()))
        self.shapes('diff').insert(ring);self.assertEqual(self.row(self.audit())['disposition'],'unreviewed')

    def test_reachable_hierarchy_merges_across_cell_boundaries(self):
        a=self.layout.create_cell('a');b=self.layout.create_cell('b')
        self.box('diff',(0,0,5000,10000),a);self.box('diff',(0,0,5000,10000),b)
        self.top.insert(k.CellInstArray(a.cell_index(),k.Trans()));self.top.insert(k.CellInstArray(b.cell_index(),k.Trans(5000,0)))
        self.assertEqual(self.row(self.audit())['disposition'],'unreviewed')

    def test_reflected_arrays_preserve_disconnected_feature_sizes(self):
        child=self.layout.create_cell('child');self.box('diff',(0,0,9999,10000),child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.M90,0,0),k.Vector(30000,0),k.Vector(0,30000),2,2))
        r=self.audit();self.assertEqual(r['measurements']['diff']['components'],4)
        self.assertEqual(self.row(r)['disposition'],'executed-reviewed')

    def test_exact_paths_match_their_polygon_geometry(self):
        path=k.Path([k.Point(0,0),k.Point(100000,0)],9998)
        self.shapes('diff').insert(path);a=self.audit()['measurements'];self.shapes('diff').clear()
        self.shapes('diff').insert(path.polygon());self.assertEqual(a,self.audit()['measurements'])
        self.assertEqual(self.row(self.audit())['disposition'],'executed-reviewed')

    def test_published_text_purposes_cannot_supply_or_expand_geometry(self):
        for name in checks.TEXT_LAYERS:
            self.shapes(name).insert(k.Text('scribe_junction',k.Trans(100000,100000)))
        r=self.audit();self.assertTrue(all(x['disposition']=='absent-operand' for x in r['rows']))
        self.assertEqual(r['measurements']['met5']['texts'],1)

    def test_names_and_invented_boundary_context_do_not_promote_candidates(self):
        self.top.name='scribe_far_away_exempt';self.box('diff',(0,0,10000,10000))
        for pair in ((81,12),(81,11),(81,1)):
            self.top.shapes(self.layout.layer(*pair)).insert(k.Box(1000000,1000000,1010000,1010000))
        self.assertEqual(self.row(self.audit())['disposition'],'unreviewed')

    def test_unsupported_shapes_units_and_hierarchy_fail_closed(self):
        for name,shape in (('via',k.Text('not geometry',k.Trans())),
            ('diff',k.Path([k.Point(0,0),k.Point(1000,0)],199)),
            ('diff',k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(0,1000)]))):
            self.shapes(name).insert(shape)
            with self.assertRaises(ValueError):self.audit()
            self.shapes(name).clear()
        self.layout.dbu=.002
        with self.assertRaises(ValueError):checks.measure(self.layout)
        self.layout.dbu=.001;child=self.layout.create_cell('child');self.box('diff',(0,0,1000,1000),child)
        for trans in (k.ICplxTrans(2,0,False,0,0),k.ICplxTrans(1,45,False,0,0)):
            self.top.insert(k.CellInstArray(child.cell_index(),trans))
            with self.assertRaises(ValueError):self.audit()
            self.top.clear_insts()
        with self.assertRaises(ValueError):self.audit()

    def test_stale_report_rebound_to_changed_layout_is_rejected(self):
        self.box('diff',(0,0,9999,10000));r=self.audit()
        self.box('diff',(9999,0,10000,10000));r['gds_sha256']=self.audit()['gds_sha256']
        with self.assertRaises(ValueError):checks.validate_saved(r,self.path)

    def test_missing_changed_and_falsely_qualified_measurements_are_rejected(self):
        r=self.audit()
        for edit in (lambda x:x['rows'].pop(),lambda x:x['rows'].append(x['rows'][0]),
            lambda x:x['measurements']['diff'].update(candidates=1),lambda x:x['measurements']['diff'].update(max_short_span_nm=True),
            lambda x:x['measurements'].pop('via4'),lambda x:x.update(qualified=True)):
            changed=copy.deepcopy(r);edit(changed)
            with self.assertRaises(ValueError):checks.evaluate(changed,r['gds_sha256'],'control')
        with self.assertRaises(ValueError):checks.evaluate(None,r['gds_sha256'],'control')

    def test_exact_source_aliases_thresholds_and_catalog_records(self):
        from scripts import sky130_scribe_bound_review as review
        with TemporaryDirectory() as td:
            folder=Path(td)/'inputs';review.delivery.fixture.unpack(review.delivery.fixture.BUNDLE,folder)
            catalog=json.loads((review.ROOT/review.delivery.queue.CATALOG).read_bytes())
            proof=review.source_proof(folder/'sources',catalog);self.assertEqual(len(proof['bindings']),14)
            next(r for r in catalog['rows'] if r['id']=='r1376')['description']='wrong limit'
            with self.assertRaises(ValueError):review.source_proof(folder/'sources',catalog)


if __name__=='__main__':unittest.main()
