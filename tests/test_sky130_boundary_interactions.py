import copy
import csv
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

import klayout.db as k
from icstudio import digital_sky130_boundary_interactions as checks

ROOT = Path(__file__).resolve().parents[1]


class BoundaryInteractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'layout.gds'
        self.layout = k.Layout(); self.layout.dbu = .001; self.top = self.layout.create_cell('control')

    def shapes(self, name, cell=None):
        return (cell or self.top).shapes(self.layout.layer(*(checks.LAYERS | checks.BOUNDARIES)[name]))

    def box(self, name, bounds, cell=None):
        self.shapes(name, cell).insert(k.Box(*bounds))

    def audit(self):
        self.layout.write(str(self.path)); return checks.audit(self.path)

    def test_all_module_targets_detect_one_nm_crossings_and_allow_containment_and_touch(self):
        self.box('module', (0,0,10000,10000))
        for key, check in checks.CHECKS.items():
            if check['boundary'] != 'module': continue
            name = check['target']
            for box, expected in (((0,0,10000,10000),0), ((-1000,0,0,1000),0),
                                  ((10000,0,11000,1000),0), ((9999,0,11000,1000),1),
                                  ((-1,0,1000,1000),1), ((0,-1,1000,1000),1),
                                  ((0,9999,1000,11000),1), ((-1000,-1000,11000,11000),1)):
                with self.subTest(layer=name, bounds=box):
                    self.shapes(name).clear(); self.box(name,box)
                    self.assertEqual(self.audit()['measurements']['violations'][key], expected)
            self.shapes(name).clear()

    def test_all_seal_overlap_targets_fail_even_if_fully_inside(self):
        self.box('seal', (0,0,10000,10000))
        for key, check in checks.CHECKS.items():
            if check['operation'] != 'overlap': continue
            name = check['target']
            for box, expected in (((-1000,0,0,1000),0), ((-1000,0,1,1000),1), ((0,0,1000,1000),1)):
                with self.subTest(layer=name, bounds=box):
                    self.shapes(name).clear(); self.box(name,box)
                    self.assertEqual(self.audit()['measurements']['violations'][key], expected)
            self.shapes(name).clear()

    def test_seal_diffusion_is_straddling_not_blanket_overlap(self):
        self.box('seal', (0,0,10000,10000))
        for box, count in (((1000,1000,2000,2000),0), ((-1,1000,2000,2000),1)):
            self.shapes('diff').clear(); self.box('diff',box)
            self.assertEqual(self.audit()['measurements']['violations']['r381'],count)

    def test_holes_are_boundaries_and_not_filled_bounding_boxes(self):
        ring = k.Polygon(k.Box(0,0,10000,10000))
        ring.insert_hole([k.Point(2000,2000),k.Point(2000,8000),k.Point(8000,8000),k.Point(8000,2000)])
        self.shapes('module').insert(ring)
        self.box('poly',(3000,3000,4000,4000)); self.assertEqual(self.audit()['violations'],0)
        self.shapes('poly').clear(); self.box('poly',(1000,3000,4000,4000))
        self.assertEqual(self.audit()['measurements']['violations']['r1415'],1)

    def test_connected_fragments_cannot_conceal_a_crossing(self):
        self.box('module',(0,0,10000,10000))
        self.box('poly',(-1000,1000,0,2000)); self.box('poly',(0,1000,1000,2000))
        r=self.audit(); self.assertEqual(r['measurements']['layers']['poly']['components'],1)
        self.assertEqual(r['measurements']['violations']['r1415'],1)

    def test_multiple_modules_are_checked_individually(self):
        self.box('module',(0,0,10000,10000)); self.box('module',(20000,0,30000,10000))
        self.box('poly',(5000,1000,25000,2000))
        self.assertEqual(self.audit()['measurements']['violations']['r1415'],2)

    def test_ambiguous_boundary_seams_duplicates_and_overlaps_are_rejected(self):
        for name in checks.BOUNDARIES:
            for box in ((0,0,10000,10000),(10000,0,20000,10000),(9999,0,20000,10000),(10000,10000,20000,20000)):
                self.shapes(name).clear(); self.box(name,(0,0,10000,10000)); self.box(name,box)
                with self.subTest(name=name,box=box), self.assertRaisesRegex(ValueError,'Touching or overlapping'):
                    self.audit()
            self.shapes(name).clear()

    def test_hierarchy_arrays_reflections_and_rotations_preserve_violations(self):
        child=self.layout.create_cell('module')
        self.box('module',(0,0,10000,10000),child); self.box('poly',(9999,1000,11000,2000),child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.M90,1000,2000),
                                       k.Vector(30000,0),k.Vector(0,30000),2,3))
        r=self.audit(); self.assertEqual(r['measurements']['violations']['r1415'],6)
        self.assertEqual(r['measurements']['layers']['module']['components'],6)

    def test_missing_boundary_never_implies_chip_qualification(self):
        self.box('diff',(0,0,1000,1000)); r=self.audit()
        self.assertEqual(len(r['rows']),44); self.assertEqual(r['violations'],0)
        self.assertFalse(r['qualified']); self.assertFalse(r['chunk_complete'])
        self.assertEqual(next(x for x in r['rows'] if x['id']=='r1408')['disposition'],'executed-reviewed')
        self.assertEqual(next(x for x in r['rows'] if x['id']=='r1409')['disposition'],'absent-operand')

    def test_texts_on_published_drawing_text_purposes_have_no_area(self):
        self.box('module',(0,0,10000,10000)); self.box('seal',(20000,0,30000,10000))
        for name in checks.TEXT_ALLOWED:self.shapes(name).insert(k.Text('annotation',k.Trans(10000,0)))
        r=self.audit(); self.assertEqual(r['violations'],0)
        self.assertTrue(all(x['disposition']=='absent-operand' for x in r['rows']))
        for name in checks.TEXT_ALLOWED:self.assertEqual(r['measurements']['layers'][name]['texts'],1)
        self.shapes('module').insert(k.Text('unexpected',k.Trans()))
        with self.assertRaisesRegex(ValueError,'shape'):self.audit()

    def test_exact_paths_match_polygons_and_inexact_paths_are_rejected(self):
        self.box('module',(0,0,10000,10000))
        path=k.Path([k.Point(-1000,1000),k.Point(1000,1000)],200)
        self.shapes('poly').insert(path); a=self.audit()['measurements']
        self.shapes('poly').clear(); self.shapes('poly').insert(path.polygon())
        self.assertEqual(self.audit()['measurements'],a)
        for path in (k.Path([k.Point(0,0),k.Point(1000,0)],201),
                     k.Path([k.Point(0,0),k.Point(1000,1000)],200)):
            self.shapes('poly').clear(); self.shapes('poly').insert(path)
            with self.assertRaisesRegex(ValueError,'path'):self.audit()

    def test_unsupported_polygons_transforms_and_units_are_not_rounded(self):
        self.shapes('poly').insert(k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(0,1000)]))
        with self.assertRaisesRegex(ValueError,'Manhattan'):self.audit()
        self.shapes('poly').clear(); child=self.layout.create_cell('child'); self.box('poly',(0,0,1000,1000),child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.ICplxTrans(1,45,False,0,0)))
        with self.assertRaisesRegex(ValueError,'transform'):self.audit()
        self.top.clear_insts(); self.top.insert(k.CellInstArray(child.cell_index(),k.ICplxTrans(2,0,False,0,0)))
        with self.assertRaisesRegex(ValueError,'transform'):self.audit()
        self.top.clear_insts(); self.layout.dbu=.005
        with self.assertRaisesRegex(ValueError,'1 nm'):self.audit()

    def test_changed_reports_and_rehashed_geometry_cannot_reuse_pass(self):
        self.box('module',(0,0,10000,10000)); self.box('poly',(0,0,1000,1000)); r=self.audit()
        self.assertEqual(checks.validate_saved(r,self.path),r)
        for key in ('rows','source','measurements','scope'):
            bad=copy.deepcopy(r); bad.pop(key)
            with self.assertRaises(ValueError):checks.evaluate(bad,r['gds_sha256'],'control')
        bad=copy.deepcopy(r); bad['measurements']['violations']['r1415']=True
        with self.assertRaises(ValueError):checks.evaluate(bad,r['gds_sha256'],'control')
        self.shapes('poly').clear(); self.box('poly',(-1,0,1000,1000)); self.layout.write(str(self.path))
        r['gds_sha256']=hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'actual layout'):checks.validate_saved(r,self.path)
        bad=self.audit()
        with self.assertRaisesRegex(ValueError,'checks failed'):checks.evaluate(bad,bad['gds_sha256'],'control')

    def test_primary_sources_bind_each_exact_catalog_message_and_purpose(self):
        with zipfile.ZipFile(ROOT/'tests/fixtures/sky130-filled-references-v1.zip') as z:
            raw={p:z.read('sources/'+p) for p in checks.SOURCE['files']}
        for name,value in raw.items():self.assertEqual(hashlib.sha256(value).hexdigest(),checks.SOURCE['files'][name])
        catalog={r['ID']:r for r in csv.DictReader(io.StringIO(raw['docs/rules/errors.csv'].decode()))}
        layers=list(csv.DictReader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
        for name,pair in checks.LAYERS.items():
            found=[r for r in layers if r['Layer name']==name and 'drawing' in r['Purpose'].split(', ')]
            self.assertEqual([r['GDS layer:datatype'] for r in found],['%s:%s'%pair])
            self.assertEqual('text' in found[0]['Purpose'].split(', '),name in checks.TEXT_ALLOWED)
        for key,check in checks.CHECKS.items():
            target=check['target']; expected=(target+' drawn layer cannot straddle areaid:ModuleCut' if check['boundary']=='module'
                else target+(' must not straddle SEALID' if check['operation']=='straddle' else ' must not overlap SEALID'))
            self.assertEqual(catalog[key]['Name'],check['rule']); self.assertEqual(catalog[key]['Description'],expected)
        c4b=raw['docs/rules/layers/table-c4b-layer-description.csv'].decode()
        self.assertIn('areaid.mt{81:10},areaid module cut',c4b)
        self.assertIn('areaid.sl{81:1},areaid sealring',c4b)
        self.assertEqual(len(checks.CHECKS),44)


if __name__=='__main__':unittest.main()
