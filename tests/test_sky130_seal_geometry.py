import copy, json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import klayout.db as k
from icstudio import digital_sky130_seal_geometry as checks


class SealGeometryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'test.gds'
        self.layout = k.Layout(); self.layout.dbu = .001; self.top = self.layout.create_cell('control')

    def shapes(self, cell=None): return (cell or self.top).shapes(self.layout.layer(*checks.PAIR))
    def box(self, bounds, cell=None): self.shapes(cell).insert(k.Box(*bounds))
    def ring(self, width=6000, offset=(0,0), cell=None):
        x,y = offset; p = k.Polygon(k.Box(x,y,x+100000,y+100000))
        p.insert_hole(list(k.Polygon(k.Box(x+width,y+width,x+100000-width,y+100000-width)).each_point_hull()))
        self.shapes(cell).insert(p)
    def audit(self): self.layout.write(str(self.path)); return checks.audit(self.path)
    def states(self, r): return {row['id']:row['disposition'] for row in r['rows']}

    def test_absence_is_not_complete_seal_qualification(self):
        r = self.audit(); self.assertEqual(self.states(r), {'r379':'absent-operand','r392':'absent-operand'})
        self.assertFalse(r['qualified']); self.assertFalse(r['chunk_complete']); checks.validate_saved(r,self.path)

    def test_ring_exact_width_and_1nm_above_pass(self):
        for width in (6000,6001):
            self.shapes().clear(); self.ring(width); r = self.audit()
            self.assertEqual(self.states(r), {'r379':'executed-reviewed','r392':'executed-reviewed'})
            checks.validate_saved(r,self.path)

    def test_ring_wall_1nm_below_limit_fails(self):
        self.ring(5999); r = self.audit(); self.assertEqual(self.states(r)['r392'],'failed')
        with self.assertRaises(ValueError): checks.evaluate(r,r['gds_sha256'],'control')

    def test_single_narrow_wall_cannot_hide_behind_large_bbox(self):
        p=k.Polygon(k.Box(0,0,100000,100000))
        p.insert_hole(list(k.Polygon(k.Box(5999,6000,94000,94000)).each_point_hull()))
        self.shapes().insert(p); self.assertEqual(self.states(self.audit())['r392'],'failed')

    def test_origin_uses_lower_left_not_center(self):
        for xy in ((1,0),(0,1),(-1,0),(0,-1),(-50000,-50000)):
            self.shapes().clear(); self.ring(offset=xy); r=self.audit()
            self.assertEqual(self.states(r)['r379'],'failed')
            self.assertEqual(self.states(r)['r392'],'executed-reviewed')

    def test_array_translation_is_measured_in_top_coordinates(self):
        child=self.layout.create_cell('child'); self.ring(offset=(-20000,-30000),cell=child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(20000,30000)))
        self.assertEqual(self.states(self.audit())['r379'],'executed-reviewed')

    def test_reflection_rotation_preserve_width_and_transformed_origin(self):
        child=self.layout.create_cell('child'); self.ring(cell=child)
        for trans in (k.Trans(k.Trans.R90,100000,0),k.Trans(k.Trans.M90,100000,0)):
            self.top.clear_insts(); self.top.insert(k.CellInstArray(child.cell_index(),trans))
            self.assertEqual(self.states(self.audit()),{'r379':'executed-reviewed','r392':'executed-reviewed'})

    def test_fragments_merge_across_cells_before_width_check(self):
        for name,y in (('a',0),('b',3000)):
            child=self.layout.create_cell(name);self.box((0,0,10000,3000),child)
            self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(0,y)))
        r=self.audit(); self.assertEqual(r['measurements']['components'],1)
        self.assertEqual(self.states(r)['r392'],'executed-reviewed')

    def test_duplicate_overlapping_and_fractured_ring_geometry_is_merged(self):
        for b in ((0,0,100000,6000),(0,94000,100000,100000),(0,0,6000,100000),(94000,0,100000,100000)):
            self.box(b);self.box(b)
        r=self.audit(); self.assertEqual(r['measurements']['components'],1)
        self.assertEqual(r['measurements']['area_nm2'],2256000000)
        self.assertEqual(self.states(r)['r392'],'executed-reviewed')

    def test_disconnected_and_corner_touching_markers_leave_origin_unresolved(self):
        for xy in ((10000,10000),(6000,6000)):
            self.shapes().clear();self.box((0,0,6000,6000));self.box((*xy,xy[0]+6000,xy[1]+6000))
            r=self.audit(); self.assertEqual(self.states(r),{'r379':'unreviewed','r392':'executed-reviewed'})
            self.assertEqual(r['unreviewed'],1); checks.evaluate(r,r['gds_sha256'],'control')

    def test_multiple_array_instances_do_not_share_an_origin_claim(self):
        child=self.layout.create_cell('child');self.ring(cell=child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(),k.Vector(200000,0),k.Vector(0,200000),2,2))
        r=self.audit();self.assertEqual(r['measurements']['components'],4)
        self.assertEqual(self.states(r)['r379'],'unreviewed')

    def test_exact_path_and_polygon_have_identical_measurements(self):
        p=k.Path([k.Point(0,3000),k.Point(100000,3000)],6000)
        self.shapes().insert(p);a=self.audit()['measurements'];self.shapes().clear()
        self.shapes().insert(p.polygon());self.assertEqual(a,self.audit()['measurements'])
        self.assertEqual(self.states(self.audit())['r392'],'executed-reviewed')

    def test_ambiguous_areaid_name_on_81_7_is_not_seal(self):
        self.top.shapes(self.layout.layer(81,7)).insert(k.Box(1,1,5,5))
        self.assertTrue(all(v=='absent-operand' for v in self.states(self.audit()).values()))

    def test_unsupported_shapes_units_and_transforms_fail_closed(self):
        for shape in (k.Text('seal',k.Trans()),k.Path([k.Point(0,0),k.Point(10000,0)],5999),
                      k.Polygon([k.Point(0,0),k.Point(10000,0),k.Point(0,10000)])):
            self.shapes().insert(shape)
            with self.assertRaises(ValueError):self.audit()
            self.shapes().clear()
        self.layout.dbu=.002
        with self.assertRaises(ValueError):checks.measure(self.layout)
        self.layout.dbu=.001;child=self.layout.create_cell('child');self.ring(cell=child)
        for trans in (k.ICplxTrans(2,0,False,0,0),k.ICplxTrans(1,45,False,0,0)):
            self.top.insert(k.CellInstArray(child.cell_index(),trans))
            with self.assertRaises(ValueError):self.audit()
            self.top.clear_insts()

    def test_rehashed_stale_geometry_cannot_bypass_saved_validation(self):
        self.ring(); r=self.audit();self.shapes().clear();self.ring(5999)
        r['gds_sha256']=self.audit()['gds_sha256']
        with self.assertRaises(ValueError):checks.validate_saved(r,self.path)

    def test_reports_cannot_omit_or_promote_checks(self):
        r=self.audit()
        for edit in (lambda x:x['rows'].pop(),lambda x:x['measurements'].update(raw_shapes=True),
            lambda x:x['measurements'].update(width_findings=1),lambda x:x.update(qualified=True),
            lambda x:x['measurements'].update(bounds_nm=[0,0,1,1])):
            bad=copy.deepcopy(r);edit(bad)
            with self.assertRaises(ValueError):checks.evaluate(bad,r['gds_sha256'],'control')
        with self.assertRaises(ValueError):checks.evaluate(None,r['gds_sha256'],'control')

    def test_exact_source_binding_includes_manual_na_and_finite_catalog(self):
        from scripts import sky130_seal_geometry_review as review
        with TemporaryDirectory() as td:
            folder=Path(td)/'inputs';review.delivery.fixture.unpack(review.delivery.fixture.BUNDLE,folder)
            catalog=json.loads((review.ROOT/review.delivery.queue.CATALOG).read_bytes())
            proof=review.source_proof(folder/'sources',catalog);self.assertEqual(len(proof['bindings']),2)
            next(r for r in catalog['rows'] if r['id']=='r392')['description']='No width requirement'
            with self.assertRaises(ValueError):review.source_proof(folder/'sources',catalog)


if __name__=='__main__':unittest.main()
