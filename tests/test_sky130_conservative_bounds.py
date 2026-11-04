import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from icstudio import digital_sky130_conservative_bounds as checks
from scripts import sky130_conservative_bound_review as review
from scripts import check_sky130_filled_replay as fixture

ROOT=Path(__file__).resolve().parents[1]


class ConservativeBoundTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'layout.gds'
        self.layout=k.Layout();self.layout.dbu=.001;self.top=self.layout.create_cell('control')

    def shapes(self,name,cell=None):
        pair=checks.BLOCKS[name]['pair'] if name in checks.BLOCKS else checks.LAYERS[name]
        return (cell or self.top).shapes(self.layout.layer(*pair))

    def box(self,name,bounds,cell=None):self.shapes(name,cell).insert(k.Box(*bounds))

    def audit(self):
        self.layout.write(str(self.path));return checks.audit(self.path)

    def test_empty_shapes_are_22_absences_not_full_qualification(self):
        r=self.audit();self.assertEqual(len(r['rows']),22)
        self.assertTrue(all(x['disposition']=='absent-operand' for x in r['rows']))
        self.assertFalse(r['qualified']);self.assertFalse(r['chunk_complete']);checks.validate_saved(r,self.path)

    def test_exact_implant_widths_and_1nm_under_bound(self):
        for name,key in (('nsdm','r471'),('psdm','r487')):
            for width,expected in ((380,'executed-reviewed'),(379,'unreviewed')):
                self.shapes(name).clear();self.box(name,(0,0,width,2000));r=self.audit()
                self.assertEqual(next(x for x in r['rows'] if x['id']==key)['disposition'],expected)
                checks.evaluate(r,r['gds_sha256'],'control')

    def test_full_poly_spacing_bound_proves_both_narrower_limits(self):
        for distance,expected in ((210,'executed-reviewed'),(209,'unreviewed'),(175,'unreviewed'),(160,'unreviewed')):
            self.shapes('poly').clear();self.box('poly',(0,0,1000,1000));self.box('poly',(1000+distance,0,2000+distance,1000))
            r=self.audit()
            for row in r['rows']:
                if row['id'] in ('r520','r521'):
                    self.assertEqual(row['disposition'],expected)
                    self.assertEqual(row['bound']['nm'],210)
            # Failure of the stronger bound never claims a foundry-rule violation.
            self.assertNotIn('violations',r);self.assertTrue(all(x['disposition']!='failed' for x in r['rows']))

    def test_poly_holes_and_notches_are_checked(self):
        ring=k.Polygon(k.Box(0,0,3000,3000))
        ring.insert_hole([k.Point(500,500),k.Point(500,1500),k.Point(709,1500),k.Point(709,500)])
        self.shapes('poly').insert(ring);self.assertGreater(self.audit()['measurements']['bound_findings']['poly'],0)
        self.shapes('poly').clear()
        self.shapes('poly').insert(k.Polygon([k.Point(0,0),k.Point(3000,0),k.Point(3000,3000),k.Point(709,3000),
            k.Point(709,500),k.Point(500,500),k.Point(500,3000),k.Point(0,3000)]))
        self.assertGreater(self.audit()['measurements']['bound_findings']['poly'],0)

    def test_merged_implant_fragments_do_not_create_false_narrow_features(self):
        self.box('nsdm',(0,0,190,1000));self.box('nsdm',(190,0,380,1000))
        r=self.audit();self.assertEqual(r['measurements']['layers']['nsdm']['components'],1)
        self.assertEqual(r['measurements']['bound_findings']['nsdm'],0)

    def test_all_six_block_purposes_and_all_raw_shape_kinds_prevent_absence(self):
        for name,selection in checks.BLOCKS.items():
            for shape in (k.Box(0,0,100,100),k.Text('marker',k.Trans()),k.Path([k.Point(0,0),k.Point(100,0)],1)):
                self.shapes(name).clear();self.shapes(name).insert(shape);r=self.audit()
                with self.subTest(name=name,shape=str(shape)):
                    self.assertEqual(r['measurements']['blockages'][name],1)
                    self.assertTrue(all(x['disposition']=='unreviewed' for x in r['rows'] if x['id'] in selection['ids']))
                    self.assertEqual(r['status'],'review-required')
            self.shapes(name).clear()

    def test_magic_fill_exclusions_are_not_the_published_ip_block_purposes(self):
        self.top.shapes(self.layout.layer(62,24)).insert(k.Box(0,0,1000,1000))
        self.assertFalse(any(self.audit()['measurements']['blockages'].values()))
        self.box('met1',(0,0,1000,1000));self.assertEqual(self.audit()['measurements']['blockages']['met1'],1)

    def test_hierarchy_arrays_and_reflections(self):
        child=self.layout.create_cell('child');self.box('nsdm',(0,0,379,1000),child);self.box('met2',(0,0,100,100),child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.M90,1000,2000),k.Vector(5000,0),k.Vector(0,5000),2,3))
        r=self.audit();self.assertEqual(r['measurements']['layers']['nsdm']['components'],6)
        self.assertEqual(r['measurements']['blockages']['met2'],6)
        self.assertGreaterEqual(r['measurements']['bound_findings']['nsdm'],6)

    def test_exact_paths_and_permitted_poly_text(self):
        path=k.Path([k.Point(0,0),k.Point(1000,0)],380)
        self.shapes('nsdm').insert(path);a=self.audit()['measurements'];self.shapes('nsdm').clear();self.shapes('nsdm').insert(path.polygon())
        self.assertEqual(a,self.audit()['measurements'])
        self.shapes('poly').insert(k.Text('annotation',k.Trans()));r=self.audit()
        self.assertEqual(r['measurements']['layers']['poly'],dict(raw_shapes=1,texts=1,components=0))

    def test_unsupported_shapes_and_units_fail(self):
        for shape in (k.Text('unexpected',k.Trans()),k.Path([k.Point(0,0),k.Point(1000,0)],379),
                      k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(0,1000)])):
            self.shapes('nsdm').clear();self.shapes('nsdm').insert(shape)
            with self.assertRaises(ValueError):self.audit()
        self.shapes('nsdm').clear();self.layout.dbu=.005
        with self.assertRaisesRegex(ValueError,'1 nm'):self.audit()
        self.layout.dbu=.001;child=self.layout.create_cell('extra_top')
        with self.assertRaisesRegex(ValueError,'one top'):self.audit()

    def test_unsupported_instance_transforms_fail(self):
        child=self.layout.create_cell('child');self.box('nsdm',(0,0,1000,1000),child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.ICplxTrans(2,0,False,0,0)))
        with self.assertRaisesRegex(ValueError,'transform'):self.audit()

    def test_changed_reports_and_rehashed_layouts_cannot_retain_passes(self):
        self.box('nsdm',(0,0,380,1000));r=self.audit()
        for key in ('rows','source','measurements','scope'):
            bad=copy.deepcopy(r);bad.pop(key)
            with self.assertRaises(ValueError):checks.evaluate(bad,r['gds_sha256'],'control')
        bad=copy.deepcopy(r);bad['measurements']['bound_findings']['nsdm']=False
        with self.assertRaises(ValueError):checks.evaluate(bad,r['gds_sha256'],'control')
        self.box('met3',(0,0,1000,1000));self.layout.write(str(self.path));r['gds_sha256']=hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'actual layout'):checks.validate_saved(r,self.path)

    def test_sources_bind_only_explicit_limits_and_blockage_layers(self):
        folder=Path(self.temp.name)/'fixture';fixture.unpack(fixture.BUNDLE,folder)
        catalog=json.loads((ROOT/'docs/qualification/sky130-error-rule-inventory.json').read_bytes())
        proof=review.source_proof(folder/'sources',catalog);self.assertEqual(len(proof['bindings']),22)
        modified=copy.deepcopy(catalog);next(r for r in modified['rows'] if r['id']=='r520')['description']='wrong threshold'
        with self.assertRaises(ValueError):review.source_proof(folder/'sources',modified)
        path=folder/'sources/docs/rules/gds_layers.csv';path.write_bytes(path.read_bytes().replace(b'68:10',b'62:24'))
        with self.assertRaisesRegex(ValueError,'Changed'):review.source_proof(folder/'sources',catalog)


if __name__=='__main__':unittest.main()
