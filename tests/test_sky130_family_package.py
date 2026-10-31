import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from icstudio import digital_sky130_family_targets as family
from icstudio import digital_sky130_package_boundaries as package


def new_layout():
    layout=k.Layout();layout.dbu=.001;return layout,layout.create_cell('control')


def controls():
    """Retained nonempty examples; the tests below also probe modified evidence."""
    layout,top=new_layout();yield 'empty',layout
    for name,pair in family.LAYERS.items():
        layout,top=new_layout();top.shapes(layout.layer(*pair)).insert(k.Box(0,0,1,1))
        yield 'family_'+name,layout
    for name in ('sky130rf_nlowvt_W0p42_L0p15_2F_cell','sky130rf_pshort_W0p84_L0p15_2F','paddr','bondpad'):
        layout,top=new_layout();top.shapes(layout.layer(90,99)).insert(k.Text(name,k.Trans()))
        yield 'intent_'+name,layout
    for name,pair in package.LAYERS.items():
        for x in (9999,10000):
            layout,top=new_layout();top.shapes(layout.layer(81,10)).insert(k.Box(0,0,10000,10000))
            top.shapes(layout.layer(*pair)).insert(k.Box(x,1000,11000,2000))
            yield name+('_cross_1nm' if x==9999 else '_touch'),layout
    layout,top=new_layout();child=layout.create_cell('child')
    child.shapes(layout.layer(81,10)).insert(k.Box(0,0,10000,10000))
    child.shapes(layout.layer(85,44)).insert(k.Box(9999,0,11000,1000))
    top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.M90,1000,2000),k.Vector(30000,0),k.Vector(0,30000),2,3))
    yield 'reflected_array',layout


class FamilyPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'input.gds';self.layout,self.top=new_layout()

    def shapes(self,name,cell=None):
        pair=(family.LAYERS|package.LAYERS|package.BOUNDARIES)[name] if isinstance(name,str) else name
        return (cell or self.top).shapes(self.layout.layer(*pair))

    def box(self,name,bounds=(0,0,1000,1000),cell=None):self.shapes(name,cell).insert(k.Box(*bounds))
    def audit(self,checker=family):self.layout.write(str(self.path));return checker.audit(self.path)
    def pending(self,report):return {r['id'] for r in report['rows'] if r['disposition']=='unreviewed'}

    def test_empty_families_are_absent_without_numerical_or_qualification_claims(self):
        r=self.audit();self.assertEqual(len(r['rows']),38);self.assertEqual(r['unreviewed'],0)
        self.assertTrue(all(v['disposition']=='absent-operand' for v in r['rows']))
        self.assertFalse(r['qualified']);self.assertFalse(r['chunk_complete']);family.validate_saved(r,self.path)

    def test_every_family_raw_guard_counts_geometry_text_and_inexact_path(self):
        for name in family.LAYERS:
            expected={key for group in family.GROUPS.values() if name in group['raw'] for key in group['ids']}
            for shape in (k.Box(0,0,1,1),k.Text('marker',k.Trans()),k.Path([k.Point(0,0),k.Point(100,0)],1)):
                self.shapes(name).clear();self.shapes(name).insert(shape)
                with self.subTest(name=name,shape=shape):self.assertEqual(self.pending(self.audit()),expected)
            self.shapes(name).clear()

    def test_rf_intent_without_mandatory_implant_never_gets_an_absence(self):
        for token in family.HINTS['low_vt_rf']:
            for kind in ('cell','text'):
                self.top.name='prefix_'+token.upper() if kind=='cell' else 'control'
                if kind=='text':self.shapes((90,99)).insert(k.Text(' '.join(token.upper()),k.Trans()))
                with self.subTest(token=token,kind=kind):
                    self.assertEqual(self.pending(self.audit()),set(family.GROUPS['low_vt_rf']['ids']))
                self.shapes((90,99)).clear()

    def test_exact_catalog_rf_names_are_guarded_and_pshort_is_not_qualified(self):
        from scripts.sky130_family_package_review import RF_MODELS
        for suffix,_,_ in RF_MODELS:
            self.top.name='sky130rf_nlowvt_'+suffix+'_cell'
            self.assertEqual(self.audit()['unreviewed'],35)
        self.top.name='sky130rf_pshort_W0p84_L0p15_2F'
        r=self.audit();self.assertEqual(r['unreviewed'],35)
        self.assertNotIn('r680',{row['id'] for row in r['rows']})

    def test_missing_enclosing_metal_does_not_waive_present_pad(self):
        self.box('pad');self.assertEqual(self.pending(self.audit()),set(family.GROUPS['bond_pad']['ids']))

    def test_pad_address_names_do_not_replace_the_raw_guard(self):
        self.top.name='paddr';self.shapes((70,5)).insert(k.Text('PADDR[0]',k.Trans()))
        self.assertEqual(self.audit()['unreviewed'],0)
        self.box('pad');self.assertEqual(self.audit()['unreviewed'],3)

    def test_extra_top_is_rejected_and_connected_hierarchy_counts_all_instances(self):
        child=self.layout.create_cell('unused_nlowvt');self.box('lvtn',cell=child)
        with self.assertRaises(ValueError):self.audit()
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.M90,1000,2000),k.Vector(2000,0),k.Vector(0,2000),2,3))
        r=self.audit();self.assertEqual(r['measurements']['raw']['lvtn'],6)
        self.assertEqual(r['measurements']['hints']['low_vt_rf']['cells'],1);self.assertEqual(r['unreviewed'],35)

    def test_family_units_and_scaled_or_rotated_instances_fail_closed(self):
        child=self.layout.create_cell('child');self.box('lvtn',cell=child)
        for transform in (k.ICplxTrans(2,0,False,0,0),k.ICplxTrans(1,45,False,0,0)):
            self.top.clear_insts();self.top.insert(k.CellInstArray(child.cell_index(),transform))
            with self.assertRaises(ValueError):self.audit()
        self.top.clear_insts();self.layout.dbu=.002
        with self.assertRaises(ValueError):family.measure(self.layout)

    def test_all_five_package_purposes_detect_crossings_and_allow_touch_or_containment(self):
        self.box('module',(0,0,10000,10000))
        for key,check in package.CHECKS.items():
            name=check['target']
            for bounds,n in (((0,0,10000,10000),0),((-1000,0,0,1000),0),((9999,0,11000,1000),1),
                             ((-1,0,1000,1000),1),((0,-1,1000,1000),1),((0,9999,1000,11000),1)):
                self.shapes(name).clear();self.box(name,bounds)
                with self.subTest(name=name,bounds=bounds):self.assertEqual(self.audit(package)['measurements']['violations'][key],n)
            self.shapes(name).clear()

    def test_module_holes_are_not_replaced_by_bounding_boxes(self):
        ring=k.Polygon(k.Box(0,0,10000,10000));ring.insert_hole([k.Point(2000,2000),k.Point(2000,8000),k.Point(8000,8000),k.Point(8000,2000)])
        self.shapes('module').insert(ring);self.box('pmm',(3000,3000,4000,4000))
        self.assertEqual(self.audit(package)['violations'],0)
        self.box('pmm',(1000,3000,3000,4000));self.assertEqual(self.audit(package)['violations'],1)

    def test_fragmented_package_crossings_are_merged(self):
        self.box('module',(0,0,10000,10000));self.box('rdl',(-1000,0,0,1000));self.box('rdl',(0,0,1000,1000))
        r=self.audit(package);self.assertEqual(r['measurements']['layers']['rdl']['components'],1);self.assertEqual(r['violations'],1)

    def test_distinct_module_boundaries_are_all_checked(self):
        self.box('module',(0,0,10000,10000));self.box('module',(20000,0,30000,10000));self.box('bump',(5000,0,25000,1000))
        self.assertEqual(self.audit(package)['violations'],2)

    def test_duplicate_touching_and_overlapping_modules_rejected(self):
        for bounds in ((0,0,10000,10000),(10000,0,20000,10000),(9999,0,20000,10000),(10000,10000,20000,20000)):
            self.shapes('module').clear();self.box('module',(0,0,10000,10000));self.box('module',bounds)
            with self.assertRaises(ValueError):self.audit(package)

    def test_reflected_package_arrays_have_six_crossings(self):
        self.layout=next(layout for name,layout in controls() if name=='reflected_array')
        r=self.audit(package);self.assertEqual(r['violations'],6)

    def test_package_paths_are_exact_and_unsupported_data_is_rejected(self):
        self.box('module',(0,0,10000,10000));path=k.Path([k.Point(-1000,1000),k.Point(1000,1000)],200)
        self.shapes('pmm').insert(path);before=self.audit(package)['measurements']
        self.shapes('pmm').clear();self.shapes('pmm').insert(path.polygon());self.assertEqual(before,self.audit(package)['measurements'])
        for shape in (k.Text('data',k.Trans()),k.Path([k.Point(0,0),k.Point(1000,0)],199),
                      k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(0,1000)])):
            self.shapes('pmm').clear();self.shapes('pmm').insert(shape)
            with self.assertRaises(ValueError):self.audit(package)

    def test_missing_module_does_not_establish_complete_chip_geometry(self):
        self.box('pmm');r=self.audit(package);self.assertFalse(r['chunk_complete']);self.assertFalse(r['qualified'])
        self.assertEqual(r['rows'][0]['disposition'],'executed-reviewed')
        self.assertEqual(r['rows'][0]['boundary_components'],0)

    def test_bad_missing_or_duplicate_reports_rejected_for_both_modules(self):
        for checker in (family,package):
            r=self.audit(checker)
            for change in (lambda x:x['rows'].pop(),lambda x:x['rows'].append(x['rows'][0]),
                           lambda x:x.update(qualified=True),lambda x:x.pop('measurements'),lambda x:x.update(recipe='old')):
                bad=copy.deepcopy(r);change(bad)
                with self.assertRaises(ValueError):checker.evaluate(bad,r['gds_sha256'],r['top'])
            with self.assertRaises(ValueError):checker.evaluate(None,r['gds_sha256'],r['top'])

    def test_stale_rehashed_family_evidence_is_recomputed(self):
        before=self.audit();self.box('lvtn');after=self.audit();before['gds_sha256']=after['gds_sha256']
        with self.assertRaises(ValueError):family.validate_saved(before,self.path)

    def test_stale_rehashed_package_evidence_is_recomputed_and_failures_rejected(self):
        self.box('module',(0,0,10000,10000));self.box('pmm',(0,0,1000,1000));before=self.audit(package)
        self.shapes('pmm').clear();self.box('pmm',(-1,0,1000,1000));after=self.audit(package)
        before['gds_sha256']=after['gds_sha256']
        with self.assertRaises(ValueError):package.validate_saved(before,self.path)
        with self.assertRaises(ValueError):package.evaluate(after,after['gds_sha256'],after['top'])

    def test_all_retained_controls_have_expected_presence_or_crossing(self):
        count=0
        for name,layout in controls():
            layout.write(str(self.path));a=family.audit(self.path);b=package.audit(self.path);count+=1
            if name.endswith('_cross_1nm'):self.assertEqual(b['violations'],1)
            elif name=='reflected_array':self.assertEqual(b['violations'],6)
            else:self.assertEqual(b['violations'],0)
            if name.startswith('family_'):self.assertGreater(a['unreviewed'],0)
        self.assertEqual(count,29)

    def test_all_43_literal_source_bindings_and_installed_map_are_authenticated(self):
        from scripts import sky130_family_package_review as review
        folder=Path(self.temp.name)/'fixture';review.delivery.fixture.unpack(review.delivery.fixture.BUNDLE,folder)
        catalog=json.loads((review.ROOT/review.delivery.queue.CATALOG).read_bytes())
        proof=review.source_proof(folder/'sources',catalog)
        self.assertEqual(len(proof['bindings']),43);self.assertEqual(len(proof['package_drawings']),5)
        for key in ('r645','r679','r1312','r1436','r1446'):
            bad=copy.deepcopy(catalog);next(r for r in bad['rows'] if r['id']==key)['description']='different operand'
            with self.assertRaises(ValueError):review.source_proof(folder/'sources',bad)


if __name__=='__main__':unittest.main()
