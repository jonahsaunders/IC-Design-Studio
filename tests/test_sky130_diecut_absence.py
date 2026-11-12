import copy,json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import klayout.db as k
from icstudio import digital_sky130_diecut_absence as checks


def new_layout():
    layout=k.Layout();layout.dbu=.001;return layout,layout.create_cell('control')


def controls():
    for name in ('empty','physical_without_diecut','diecut_box','diecut_polygon','diecut_path','diecut_text',
                 'diecut_sliver','diecut_hole','diecut_nonmanhattan','diecut_rotated','diecut_array',
                 'unrelated_annotations','diecut_under_buildspace','diecut_under_testchip'):
        layout,top=new_layout();shapes=top.shapes(layout.layer(*checks.DIECUT))
        if name=='physical_without_diecut':
            for pair in ((64,20),(65,20),(68,20),(69,20),(70,20)):
                top.shapes(layout.layer(*pair)).insert(k.Box(0,0,10000,10000))
        elif name=='diecut_box':shapes.insert(k.Box(0,0,1000,1000))
        elif name=='diecut_polygon':shapes.insert(k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(1000,500),k.Point(500,500),k.Point(500,1000),k.Point(0,1000)]))
        elif name=='diecut_path':shapes.insert(k.Path([k.Point(0,0),k.Point(2000,0)],301))
        elif name=='diecut_text':shapes.insert(k.Text('annotation',k.Trans()))
        elif name=='diecut_sliver':shapes.insert(k.Box(0,0,1,10000))
        elif name=='diecut_hole':
            p=k.Polygon(k.Box(0,0,1000,1000));p.insert_hole(list(k.Polygon(k.Box(100,100,900,900)).each_point_hull()));shapes.insert(p)
        elif name=='diecut_nonmanhattan':shapes.insert(k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(0,1000)]))
        elif name in ('diecut_rotated','diecut_array','diecut_under_buildspace','diecut_under_testchip'):
            child=layout.create_cell({'diecut_under_buildspace':'sample_buildspace','diecut_under_testchip':'testchip_techCD_x'}.get(name,'child'))
            child.shapes(layout.layer(*checks.DIECUT)).insert(k.Box(0,0,1000,1000))
            if name=='diecut_array':top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.M90,0,0),k.Vector(2000,0),k.Vector(0,2000),2,3))
            else:top.insert(k.CellInstArray(child.cell_index(),k.ICplxTrans(2,45,True,10,20) if name=='diecut_rotated' else k.Trans()))
        elif name=='unrelated_annotations':
            for pair in ((81,1),(81,101),(81,3),(81,10)):top.shapes(layout.layer(*pair)).insert(k.Text('diecutCutAREA',k.Trans()))
        yield name,layout


class DiecutAbsenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'layout.gds';self.layout,self.top=new_layout()

    def audit(self):self.layout.write(str(self.path));return checks.audit(self.path)
    def shapes(self):return self.top.shapes(self.layout.layer(*checks.DIECUT))

    def test_empty_operand_proves_only_18_binary_absences(self):
        r=self.audit();self.assertEqual(len(r['rows']),18)
        self.assertTrue(all(row['disposition']=='absent-operand' for row in r['rows']))
        self.assertFalse(r['qualified']);self.assertFalse(r['chunk_complete']);checks.validate_saved(r,self.path)

    def test_present_shape_never_claims_a_spacing_or_overlap_pass(self):
        self.shapes().insert(k.Box(0,0,1000,1000));r=self.audit()
        self.assertEqual(r['unreviewed'],18);self.assertTrue(all(row['disposition']=='unreviewed' for row in r['rows']))
        checks.validate_saved(r,self.path)

    def test_text_is_presence_even_without_polygon_area(self):
        self.shapes().insert(k.Text('annotation',k.Trans()));r=self.audit()
        self.assertEqual(r['measurements'],dict(raw_diecut_shapes=1,diecut_texts=1));self.assertEqual(r['unreviewed'],18)

    def test_hierarchy_reflection_and_arrays_are_counted(self):
        layout=dict(controls())['diecut_array'];self.layout=layout;r=self.audit()
        self.assertEqual(r['measurements']['raw_diecut_shapes'],6);self.assertEqual(r['unreviewed'],18)

    def test_presence_does_not_depend_on_geometry_snapping(self):
        self.layout=dict(controls())['diecut_rotated'];r=self.audit()
        self.assertEqual(r['measurements']['raw_diecut_shapes'],1);self.assertEqual(r['unreviewed'],18)

    def test_other_geometry_cannot_be_invented_as_diecut_or_unknown_operand(self):
        self.layout=dict(controls())['physical_without_diecut'];r=self.audit()
        self.assertEqual(r['unreviewed'],0);self.assertEqual(r['measurements']['raw_diecut_shapes'],0)

    def test_other_marker_purposes_are_not_diecut_aliases(self):
        self.layout=dict(controls())['unrelated_annotations'];r=self.audit();self.assertEqual(r['unreviewed'],0)

    def test_buildspace_and_testchip_names_do_not_exempt_present_diecuts(self):
        for name in ('diecut_under_buildspace','diecut_under_testchip'):
            self.layout=dict(controls())[name];self.assertEqual(self.audit()['unreviewed'],18,name)

    def test_no_enclosure_companion_can_be_promoted(self):
        enclosures={f'r{i}' for i in range(988,1006)}|{'r1406','r927'}
        self.assertFalse(enclosures & checks.CHECKS.keys())
        self.assertEqual({v['operation'] for v in checks.CHECKS.values()},{'spacing'})

    def test_multiple_roots_are_rejected(self):
        self.layout.create_cell('other')
        with self.assertRaises(ValueError):checks.measure(self.layout)

    def test_changed_missing_and_boolean_census_is_rejected(self):
        r=self.audit()
        for change in (lambda x:x['rows'].pop(),lambda x:x['rows'].append(x['rows'][0]),lambda x:x.update(qualified=True),
                       lambda x:x['measurements'].update(raw_diecut_shapes=False),lambda x:x['measurements'].update(diecut_texts=1),
                       lambda x:x.pop('measurements')):
            altered=copy.deepcopy(r);change(altered)
            with self.assertRaises(ValueError):checks.evaluate(altered,r['gds_sha256'],r['top'])
        with self.assertRaises(ValueError):checks.evaluate(None,r['gds_sha256'],r['top'])

    def test_rehashed_stale_report_is_recomputed(self):
        before=self.audit();self.shapes().insert(k.Box(0,0,1000,1000));after=self.audit();before['gds_sha256']=after['gds_sha256']
        with self.assertRaises(ValueError):checks.validate_saved(before,self.path)

    def test_all_retained_controls_preserve_presence(self):
        count=0
        for name,layout in controls():
            self.layout=layout;r=self.audit();count+=1
            self.assertEqual(r['unreviewed'],18 if name.startswith('diecut_') else 0,name)
            checks.validate_saved(r,self.path)
        self.assertEqual(count,14)

    def test_source_binding_distinguishes_binary_rules_from_enclosure(self):
        from scripts import sky130_diecut_density_review as review
        folder=Path(self.temp.name)/'fixture';review.delivery.fixture.unpack(review.delivery.fixture.BUNDLE,folder)
        catalog=json.loads((review.ROOT/review.delivery.queue.CATALOG).read_bytes());proof=review.source_proof(folder/'sources',catalog)
        self.assertEqual(len(proof['bindings']),18);self.assertEqual(proof['diecut_marker']['GDS layer:datatype'],'81:11')
        next(r for r in catalog['rows'] if r['id']=='r1006')['description']='0.618 min. enclosure of q0nwellnotBuildSpace by diecutCutAREA'
        with self.assertRaises(ValueError):review.source_proof(folder/'sources',catalog)


if __name__=='__main__':unittest.main()
