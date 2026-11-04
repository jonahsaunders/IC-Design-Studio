import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from icstudio import digital_sky130_metal_width_bounds as checks


def new_layout():
    layout=k.Layout();layout.dbu=.001;return layout,layout.create_cell('control')


def controls():
    layout,top=new_layout();yield 'empty',layout
    for name,layer in checks.LAYERS.items():
        limit=next(r['limit_nm'] for r in checks.CHECKS.values() if r['target']==name)
        for kind in ('below','exact','above','fill_only','joined_fill','overlap','mask_guard','thin_L','thin_ring'):
            layout,top=new_layout()
            def shapes(source='drawing'):return top.shapes(layout.layer(*layer[source]))
            if kind in ('below','exact','above'):
                width=limit+{'below':-1,'exact':0,'above':1}[kind]
                shapes().insert(k.Box(0,0,width,3*limit))
            elif kind=='fill_only':shapes('fill').insert(k.Box(0,0,limit,3*limit))
            elif kind=='joined_fill':
                shapes().insert(k.Box(0,0,limit//2+1,3*limit))
                shapes('fill').insert(k.Box(limit//2+1,0,limit+1,3*limit))
            elif kind=='overlap':
                for source in ('drawing','fill'):shapes(source).insert(k.Box(0,0,limit,3*limit))
            elif kind=='mask_guard':top.shapes(layout.layer(*layer['guards'][0])).insert(k.Text('marker',k.Trans()))
            elif kind=='thin_L':
                shapes().insert(k.Box(0,0,2*limit,1000));shapes().insert(k.Box(0,0,1000,2*limit))
            elif kind=='thin_ring':
                p=k.Polygon(k.Box(0,0,2*limit,2*limit))
                p.insert_hole(list(k.Polygon(k.Box(1000,1000,2*limit-1000,2*limit-1000)).each_point_hull()));shapes().insert(p)
            yield name+'_'+kind,layout
    layout,top=new_layout();child=layout.create_cell('child')
    child.shapes(layout.layer(70,20)).insert(k.Box(0,0,6000,18000))
    top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.M90,1000,2000),k.Vector(50000,0),k.Vector(0,50000),2,3))
    yield 'reflected_array',layout
    layout,top=new_layout();top.shapes(layout.layer(70,20)).insert(k.Path([k.Point(0,0),k.Point(18000,0)],6000))
    yield 'exact_path',layout
    layout,top=new_layout();shapes=top.shapes(layout.layer(70,20))
    shapes.insert(k.Box(0,0,3001,3001));shapes.insert(k.Box(3001,3001,6002,6002));yield 'corner_touch',layout
    layout,top=new_layout();shapes=top.shapes(layout.layer(70,20))
    shapes.insert(k.Box(0,0,3001,18000));shapes.insert(k.Box(3001,0,6001,18000));yield 'fragmented',layout


class MetalWidthBoundTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'layout.gds';self.layout,self.top=new_layout()

    def shapes(self,name='met3',source='drawing',cell=None):
        pair=checks.LAYERS[name][source] if isinstance(name,str) else name
        return (cell or self.top).shapes(self.layout.layer(*pair))

    def box(self,bounds,name='met3',source='drawing',cell=None):self.shapes(name,source,cell).insert(k.Box(*bounds))
    def audit(self):self.layout.write(str(self.path));return checks.audit(self.path)
    def row(self,report,name='met3'):return next(r for r in report['rows'] if r['target']==name)

    def test_empty_geometry_does_not_claim_numerical_execution(self):
        r=self.audit();self.assertEqual(len(r['rows']),3)
        self.assertTrue(all(row['disposition']=='absent-operand' for row in r['rows']))
        self.assertFalse(r['qualified']);self.assertFalse(r['chunk_complete']);checks.validate_saved(r,self.path)

    def test_each_source_threshold_is_inclusive_and_above_is_unreviewed_not_failed(self):
        for check in checks.CHECKS.values():
            name=check['target'];limit=check['limit_nm']
            for delta,expected in ((-1,'executed-reviewed'),(0,'executed-reviewed'),(1,'unreviewed')):
                self.shapes(name).clear();self.box((0,0,limit+delta,3*limit),name)
                with self.subTest(name=name,delta=delta):self.assertEqual(self.row(self.audit(),name)['disposition'],expected)
            self.shapes(name).clear()

    def test_native_fill_alone_is_measured(self):
        self.box((0,0,6001,18000),source='fill');r=self.audit()
        self.assertEqual(self.row(r)['disposition'],'unreviewed');self.assertEqual(r['measurements']['met3']['inputs']['fill']['area_nm2'],6001*18000)

    def test_drawing_and_fill_union_cannot_hide_an_excess_width(self):
        self.box((0,0,3001,18000));self.box((3001,0,6001,18000),source='fill')
        r=self.audit();self.assertEqual(self.row(r)['max_short_span_nm'],6001);self.assertEqual(self.row(r)['candidates'],1)

    def test_overlapping_drawing_and_fill_are_not_double_counted(self):
        self.box((0,0,6000,18000));self.box((0,0,6000,18000),source='fill')
        r=self.audit();v=r['measurements']['met3'];self.assertEqual(v['area_nm2'],6000*18000)
        self.assertEqual(sum(x['area_nm2'] for x in v['inputs'].values()),2*v['area_nm2'])

    def test_connected_hierarchy_is_merged_before_measuring(self):
        self.box((0,0,3001,18000));child=self.layout.create_cell('child')
        self.box((0,0,3000,18000),cell=child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(3001,0)))
        self.assertEqual(self.row(self.audit())['max_short_span_nm'],6001)

    def test_disjoint_features_do_not_use_one_global_bounding_box(self):
        self.box((0,0,6000,18000));self.box((100000,100000,106000,118000))
        row=self.row(self.audit());self.assertEqual(row['components'],2);self.assertEqual(row['disposition'],'executed-reviewed')

    def test_corner_touch_keeps_one_conservative_feature(self):
        self.box((0,0,3001,3001));self.box((3001,3001,6002,6002))
        row=self.row(self.audit());self.assertEqual(row['components'],1);self.assertEqual(row['disposition'],'unreviewed')

    def test_reflected_arrays_preserve_individual_widths(self):
        self.layout=next(layout for name,layout in controls() if name=='reflected_array')
        row=self.row(self.audit());self.assertEqual(row['components'],6)
        self.assertEqual(row['max_short_span_nm'],6000);self.assertEqual(row['disposition'],'executed-reviewed')

    def test_large_thin_shapes_stay_unreviewed_without_fabricating_a_violation(self):
        for name,layout in controls():
            if not name.endswith(('thin_L','thin_ring')):continue
            self.layout=layout;r=self.audit();self.assertEqual(r['unreviewed'],1);self.assertNotIn('violations',r)

    def test_holes_are_preserved_in_union_area(self):
        p=k.Polygon(k.Box(0,0,6000,18000));p.insert_hole(list(k.Polygon(k.Box(1000,1000,5000,17000)).each_point_hull()))
        self.shapes().insert(p);r=self.audit();self.assertEqual(r['measurements']['met3']['area_nm2'],6000*18000-4000*16000)

    def test_every_alternate_purpose_blocks_promotion_for_its_own_metal(self):
        for name,layer in checks.LAYERS.items():
            for pair in layer['guards']:
                for shape in (k.Box(0,0,1,1),k.Text('mask',k.Trans()),k.Path([k.Point(0,0),k.Point(1000,0)],1)):
                    self.shapes(pair).clear();self.shapes(pair).insert(shape);r=self.audit()
                    with self.subTest(name=name,pair=pair):
                        self.assertEqual(self.row(r,name)['reason'],'unsupported-metal-purpose');self.assertEqual(r['unreviewed'],1)
                self.shapes(pair).clear()

    def test_pins_labels_and_vias_are_not_treated_as_metal_area(self):
        for name,layer in checks.LAYERS.items():
            for datatype in (*checks.ANNOTATIONS,44):self.shapes((layer['drawing'][0],datatype)).insert(k.Box(0,0,100000,100000))
        self.assertTrue(all(r['disposition']=='absent-operand' for r in self.audit()['rows']))

    def test_text_on_documented_drawing_and_native_fill_purposes_has_no_area(self):
        for name in checks.LAYERS:
            for source in ('drawing','fill'):self.shapes(name,source).insert(k.Text('annotation',k.Trans()))
        r=self.audit();self.assertTrue(all(row['disposition']=='absent-operand' for row in r['rows']))
        self.assertTrue(all(d['texts']==1 for v in r['measurements'].values() for d in v['inputs'].values()))

    def test_exact_paths_match_their_polygons_and_inexact_paths_are_rejected(self):
        p=k.Path([k.Point(0,0),k.Point(18000,0)],6000);self.shapes().insert(p);before=self.audit()['measurements']
        self.shapes().clear();self.shapes().insert(p.polygon());self.assertEqual(before,self.audit()['measurements'])
        for path in (k.Path([k.Point(0,0),k.Point(18000,0)],6001),k.Path([k.Point(0,0),k.Point(1000,1000)],6000)):
            self.shapes().clear();self.shapes().insert(path)
            with self.assertRaises(ValueError):self.audit()

    def test_unsupported_polygons_units_and_transforms_are_not_rounded(self):
        self.shapes().insert(k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(0,1000)]))
        with self.assertRaises(ValueError):self.audit()
        self.shapes().clear();child=self.layout.create_cell('child');self.box((0,0,1000,1000),cell=child)
        for t in (k.ICplxTrans(2,0,False,0,0),k.ICplxTrans(1,45,False,0,0)):
            self.top.clear_insts();self.top.insert(k.CellInstArray(child.cell_index(),t))
            with self.assertRaises(ValueError):self.audit()
        self.top.clear_insts();self.layout.dbu=.002
        with self.assertRaises(ValueError):checks.measure(self.layout)

    def test_missing_duplicate_boolean_and_changed_evidence_is_rejected(self):
        self.box((0,0,6000,18000));r=self.audit()
        for change in (lambda x:x['rows'].pop(),lambda x:x['rows'].append(x['rows'][0]),lambda x:x.update(qualified=True),
            lambda x:x.pop('measurements'),lambda x:x['measurements']['met3'].update(candidates=True),
            lambda x:x['measurements']['met3']['guards'].pop(next(iter(x['measurements']['met3']['guards'])))):
            altered=copy.deepcopy(r);change(altered)
            with self.assertRaises(ValueError):checks.evaluate(altered,r['gds_sha256'],r['top'])
        with self.assertRaises(ValueError):checks.evaluate(None,r['gds_sha256'],r['top'])

    def test_rehashed_stale_geometry_is_independently_recomputed(self):
        self.box((0,0,6000,18000));before=self.audit();self.shapes().clear();self.box((0,0,6001,18000));after=self.audit()
        before['gds_sha256']=after['gds_sha256']
        with self.assertRaises(ValueError):checks.validate_saved(before,self.path)

    def test_all_retained_controls_have_expected_dispositions(self):
        count=0
        for name,layout in controls():
            self.layout=layout;r=self.audit();count+=1
            pending=name.endswith(('above','joined_fill','mask_guard','thin_L','thin_ring')) or name in ('corner_touch','fragmented')
            self.assertEqual(r['unreviewed'],int(pending),name);checks.validate_saved(r,self.path)
        self.assertEqual(count,32)

    def test_exact_catalog_drawn_fill_and_guard_sources_are_bound(self):
        from scripts import sky130_metal_width_review as review
        folder=Path(self.temp.name)/'fixture';review.delivery.fixture.unpack(review.delivery.fixture.BUNDLE,folder)
        catalog=json.loads((review.ROOT/review.delivery.queue.CATALOG).read_bytes());proof=review.source_proof(folder/'sources',catalog)
        self.assertEqual(set(proof['bindings']),{'r1340','r1341','r1342'})
        next(r for r in catalog['rows'] if r['id']=='r1342')['description']='6 min width of met3 under pad metal'
        with self.assertRaises(ValueError):review.source_proof(folder/'sources',catalog)


if __name__=='__main__':unittest.main()
