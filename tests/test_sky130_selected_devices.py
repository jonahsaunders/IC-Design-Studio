import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from icstudio import digital_sky130_selected_devices as checks
from scripts import sky130_selected_device_review as review
from scripts import check_sky130_filled_replay as fixture

ROOT=Path(__file__).resolve().parents[1]


class SelectedDeviceTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'layout.gds'
        self.layout=k.Layout();self.layout.dbu=.001;self.top=self.layout.create_cell('control')

    def shapes(self,name,cell=None):
        pair=checks.SUBJECTS[name]['pair'] if name in checks.SUBJECTS else checks.LAYERS[name]
        return (cell or self.top).shapes(self.layout.layer(*pair))

    def box(self,name,bounds,cell=None):self.shapes(name,cell).insert(k.Box(*bounds))

    def audit(self):
        self.layout.write(str(self.path));return checks.audit(self.path)

    def gate(self,cell=None):
        self.box('poly',(0,0,1000,1000),cell);self.box('diff',(0,0,1000,1000),cell)

    def test_empty_device_prerequisites_are_36_absences_not_full_qualification(self):
        self.box('poly',(0,0,1000,1000));r=self.audit()
        self.assertEqual(len(r['rows']),36);self.assertTrue(all(x['disposition']=='absent-operand' for x in r['rows']))
        self.assertFalse(r['qualified']);self.assertFalse(r['chunk_complete']);self.assertEqual(checks.validate_saved(r,self.path),r)

    def test_every_raw_shape_kind_prevents_a_device_absence_claim(self):
        for name,selection in checks.SUBJECTS.items():
            for shape in (k.Box(0,0,100,100),k.Text('marker',k.Trans()),k.Path([k.Point(0,0),k.Point(100,0)],1)):
                self.shapes(name).clear();self.shapes(name).insert(shape);r=self.audit()
                with self.subTest(name=name,shape=str(shape)):
                    self.assertEqual(r['measurements']['subjects'][name]['raw_shapes'],1)
                    self.assertTrue(all(x['disposition']=='unreviewed' for x in r['rows'] if x['id'] in selection['ids']))
                    self.assertEqual(r['status'],'review-required')
            self.shapes(name).clear()

    def test_device_name_without_marker_still_requires_review(self):
        child=self.layout.create_cell('opaque');self.top.insert(k.CellInstArray(child.cell_index(),k.Trans()))
        for name,token in (('vpp','s8rf2_XCMVPP_renamed'),('pwell_resistor','custom_RESPW'),('pnp','sky130rf_PNP5x')):
            child.name=token;r=self.audit()
            self.assertEqual(r['measurements']['subjects'][name]['candidate_cells'],1)
            self.assertEqual(r['measurements']['subjects'][name]['raw_shapes'],0)
            self.assertTrue(all(x['disposition']=='unreviewed' for x in r['rows'] if x.get('subject')==name))

    def test_labels_on_any_purpose_and_unicode_variants_prevent_false_absence(self):
        shapes=self.top.shapes(self.layout.layer(999,17))
        for name,text in (('vpp','model Ｖ Ｐ Ｐ hidden'),('pwell_resistor','model PW RES'),('pnp','model p n p')):
            shapes.clear();shapes.insert(k.Text(text,k.Trans()));r=self.audit()
            self.assertEqual(r['measurements']['subjects'][name]['candidate_labels'],1)
            self.assertEqual(r['status'],'review-required')

    def test_renaming_does_not_remove_a_raw_device_candidate(self):
        child=self.layout.create_cell('opaque');self.box('vpp',(0,0,1000,1000),child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans()))
        self.assertEqual(self.audit()['measurements']['subjects']['vpp'],dict(raw_shapes=1,candidate_cells=0,candidate_labels=0))

    def test_tunm_exact_95nm_enclosure_and_94nm_on_every_edge(self):
        self.gate();self.box('tunm',(-95,-95,1095,1095));r=self.audit();self.assertEqual(r['violations'],0)
        self.assertEqual(next(x for x in r['rows'] if x['id']=='r453')['disposition'],'executed-reviewed')
        for bounds in ((-94,-95,1095,1095),(-95,-94,1095,1095),(-95,-95,1094,1095),(-95,-95,1095,1094)):
            self.shapes('tunm').clear();self.box('tunm',bounds)
            with self.subTest(bounds=bounds):self.assertGreater(self.audit()['measurements']['violations']['r453'],0)

    def test_tunm_crossing_fails_and_unselected_outside_gate_does_not_force_sonos(self):
        self.gate();self.box('tunm',(500,-100,1100,1100))
        self.assertGreater(self.audit()['measurements']['violations']['r453'],0)
        self.shapes('tunm').clear();self.box('tunm',(1000,0,2000,1000));r=self.audit()
        self.assertEqual(r['measurements']['gates'],1);self.assertEqual(r['measurements']['selected_gates'],0)
        self.assertEqual(r['violations'],0)

    def test_tunm_selection_uses_actual_gate_intersection(self):
        self.box('poly',(0,0,3000,1000));self.box('diff',(2000,-1000,3000,2000));self.box('tunm',(-95,-95,1095,1095))
        r=self.audit();self.assertEqual(r['measurements']['gates'],1);self.assertEqual(r['measurements']['selected_gates'],0)

    def test_sonos_intent_without_the_implant_cannot_claim_absence(self):
        self.gate();self.top.name='SONOS_control';r=self.audit()
        self.assertEqual(next(x for x in r['rows'] if x['id']=='r453')['disposition'],'unreviewed')
        self.top.name='control';self.top.shapes(self.layout.layer(999,1)).insert(k.Text('model nvssonos_e',k.Trans()))
        self.assertEqual(self.audit()['status'],'review-required')
        self.box('tunm',(-95,-95,1095,1095));r=self.audit()
        self.assertEqual(next(x for x in r['rows'] if x['id']=='r453')['disposition'],'executed-reviewed')
        self.box('poly',(5000,0,6000,1000));self.box('diff',(5000,0,6000,1000))
        self.assertEqual(self.audit()['status'],'review-required')

    def test_holes_cannot_be_hidden_by_enclosing_boxes(self):
        self.gate();p=k.Polygon(k.Box(-95,-95,1095,1095));p.insert_hole([k.Point(400,400),k.Point(400,600),k.Point(600,600),k.Point(600,400)])
        self.shapes('tunm').insert(p);self.assertGreater(self.audit()['measurements']['violations']['r453'],0)
        self.shapes('tunm').clear();self.box('hvntm',(0,0,1000,1000));self.shapes('hvi').insert(p)
        self.assertGreater(self.audit()['measurements']['violations']['r1061'],0)

    def test_hvntm_missing_hvi_partial_enclosure_and_exact_containment(self):
        self.box('hvntm',(0,0,1000,1000));self.assertGreater(self.audit()['measurements']['violations']['r1061'],0)
        for bounds,passes in (((0,0,1000,1000),True),((1,0,1000,1000),False),((0,0,999,1000),False)):
            self.shapes('hvi').clear();self.box('hvi',bounds)
            self.assertEqual(self.audit()['measurements']['violations']['r1061']==0,passes)

    def test_hierarchy_arrays_reflections_and_connected_fragments(self):
        child=self.layout.create_cell('implant');self.gate(child);self.box('tunm',(-94,-95,1095,1095),child)
        self.box('hvntm',(0,0,1000,1000),child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.M90,1000,2000),k.Vector(5000,0),k.Vector(0,5000),2,3))
        r=self.audit();self.assertEqual(r['measurements']['selected_gates'],6)
        self.assertEqual(r['measurements']['violations']['r1061'],6);self.assertGreaterEqual(r['measurements']['violations']['r453'],6)

    def test_exact_paths_and_drawing_text_semantics(self):
        path=k.Path([k.Point(0,500),k.Point(1000,500)],1000)
        self.shapes('poly').insert(path);self.box('diff',(0,0,1000,1000));self.box('tunm',(-95,-95,1095,1095))
        a=self.audit()['measurements'];self.shapes('poly').clear();self.shapes('poly').insert(path.polygon())
        self.assertEqual(self.audit()['measurements'],a)
        for name in ('poly','diff'):self.shapes(name).insert(k.Text('annotation',k.Trans()))
        r=self.audit();self.assertEqual(r['violations'],0);self.assertEqual(r['measurements']['gates'],1)

    def test_unsupported_shapes_transforms_and_units_fail(self):
        for shape in (k.Text('unexpected',k.Trans()),k.Path([k.Point(0,0),k.Point(1000,0)],201),
                      k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(0,1000)])):
            self.shapes('tunm').clear();self.shapes('tunm').insert(shape)
            with self.assertRaises(ValueError):self.audit()
        self.shapes('tunm').clear();child=self.layout.create_cell('child');self.box('hvntm',(0,0,1000,1000),child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.ICplxTrans(1,45,False,0,0)))
        with self.assertRaisesRegex(ValueError,'transform'):self.audit()

    def test_missing_changed_and_rehashed_reports_are_rejected(self):
        self.gate();self.box('tunm',(-95,-95,1095,1095));r=self.audit()
        for key in ('rows','source','measurements','scope'):
            bad=copy.deepcopy(r);bad.pop(key)
            with self.assertRaises(ValueError):checks.evaluate(bad,r['gds_sha256'],'control')
        for field in ('gates','selected_gates'):
            bad=copy.deepcopy(r);bad['measurements'][field]=True
            with self.assertRaises(ValueError):checks.evaluate(bad,r['gds_sha256'],'control')
        self.box('vpp',(0,0,1000,1000));self.layout.write(str(self.path));r['gds_sha256']=hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'actual layout'):checks.validate_saved(r,self.path)

    def test_selected_geometry_failure_cannot_be_accepted(self):
        self.box('hvntm',(0,0,1000,1000));r=self.audit()
        with self.assertRaisesRegex(ValueError,'geometry checks failed'):checks.evaluate(r,r['gds_sha256'],'control')

    def test_device_sources_and_rr_advisories_cannot_reclassify_required_rules(self):
        folder=Path(self.temp.name)/'fixture';fixture.unpack(fixture.BUNDLE,folder)
        catalog=json.loads((ROOT/'docs/qualification/sky130-error-rule-inventory.json').read_bytes())
        proof=review.source_proof(folder/'sources',catalog);self.assertEqual(len(proof['bindings']),36)
        self.assertEqual(len(proof['advisory_decisions']),8)
        rows=[dict(id=r['id'],rule=r['rule'],record=r['record'],disposition='unreviewed') for r in catalog['rows']]
        result=review.apply_advisories(rows,proof['advisory_decisions'],catalog)
        self.assertEqual(sum(r['disposition']=='advisory' for r in result),8)
        self.assertEqual(next(r for r in result if r['id']=='s11')['disposition'],'unreviewed')
        for change in ('required_flag','missing','wrong_record','unrelated'):
            bad=copy.deepcopy(proof['advisory_decisions'])
            if change=='required_flag':bad[0]['parent']['flags']=['RC']
            elif change=='missing':bad.pop()
            elif change=='wrong_record':bad[0]['parent']['id']='wrong#1'
            else:bad[0]['id']='s11'
            with self.assertRaises(ValueError):review.apply_advisories(rows,bad,catalog)
        with self.assertRaises(ValueError):review.apply_advisories(result,proof['advisory_decisions'],catalog)


if __name__=='__main__':unittest.main()
