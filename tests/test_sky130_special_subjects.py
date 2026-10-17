import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from icstudio import digital_sky130_special_subjects as checks


class SpecialSubjectTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'layout.gds'
        self.layout=k.Layout();self.layout.dbu=.001;self.top=self.layout.create_cell('control')

    def shapes(self,name,cell=None):
        pair=(64,20) if name=='nwell' else checks.LAYERS[name] if isinstance(name,str) else name
        return (cell or self.top).shapes(self.layout.layer(*pair))

    def box(self,name,bounds=(0,0,1000,1000),cell=None):self.shapes(name,cell).insert(k.Box(*bounds))

    def audit(self):
        self.layout.write(str(self.path));return checks.audit(self.path)

    def pending(self,r):return {x['id'] for x in r['rows'] if x['disposition']=='unreviewed'}

    def test_empty_subjects_are_seven_absences_without_device_qualification(self):
        r=self.audit();self.assertEqual(len(r['rows']),7);self.assertEqual(r['unreviewed'],0)
        self.assertTrue(all(x['disposition']=='absent-operand' for x in r['rows']))
        self.assertFalse(r['qualified']);self.assertFalse(r['chunk_complete']);checks.validate_saved(r,self.path)

    def test_every_raw_purpose_and_shape_kind_prevents_its_proof(self):
        for name in checks.LAYERS:
            pending={key for group in checks.GROUPS.values() if name in group['raw'] for key in group['ids']}
            for shape in (k.Box(0,0,100,100),k.Text('marker',k.Trans()),k.Path([k.Point(0,0),k.Point(100,0)],1)):
                self.shapes(name).clear();self.shapes(name).insert(shape);r=self.audit()
                self.assertEqual(r['measurements']['raw'][name],1);self.assertEqual(self.pending(r),pending)
            self.shapes(name).clear()

    def test_missing_enclosing_uhvi_does_not_discharge_present_deep_well(self):
        self.box('dnwell');r=self.audit()
        self.assertEqual(r['measurements']['raw']['uhvi'],0);self.assertIn('r928',self.pending(r))
        self.assertNotIn('violations',r)

    def test_explicit_masks_cannot_hide_behind_absent_drawn_layers(self):
        for name,ids in (('cdnm',{'r928'}),('crpm',{'r1047','r1059','r1060'}),('cnwm',{'r922'})):
            self.box(name);self.assertEqual(self.pending(self.audit()),ids);self.shapes(name).clear()

    def test_uhvi_absence_proof_never_waives_present_uhvi(self):
        self.box((66,20));self.assertNotIn('r929',self.pending(self.audit()))
        self.box('uhvi');self.assertTrue({'r396','r929'}<=self.pending(self.audit()))

    def test_names_and_unicode_labels_prevent_missing_marker_absence(self):
        for group,tokens in checks.HINTS.items():
            ids={key for selection in checks.GROUPS.values() if selection['hints']==group for key in selection['ids']}
            for token in tokens:
                self.top.name='prefix_'+token.upper();r=self.audit();self.assertEqual(self.pending(r),ids)
                self.top.name='control';self.shapes((90,99)).clear()
                self.shapes((90,99)).insert(k.Text('prefix '+' '.join(token.upper())+' suffix',k.Trans()))
                self.assertEqual(self.pending(self.audit()),ids);self.shapes((90,99)).clear()

    def test_reachable_child_names_are_checked(self):
        child=self.layout.create_cell('xhrpoly_custom');self.box((90,99),cell=child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans()))
        r=self.audit();self.assertEqual(r['measurements']['hints']['resistor']['cells'],1)
        self.assertEqual(self.pending(r),{'r1047','r1059','r1060'})

    def test_explicit_nwell_hole_prevents_angle_subject_absence(self):
        ring=k.Polygon(k.Box(0,0,3000,3000));ring.insert_hole([k.Point(500,500),k.Point(500,2500),k.Point(2500,2500),k.Point(2500,500)])
        self.shapes('nwell').insert(ring);r=self.audit();self.assertEqual(r['measurements']['nwell']['holes'],1)
        self.assertEqual(self.pending(r),{'r922'})

    def test_holes_are_detected_after_merging_fragments(self):
        for bounds in ((0,0,3000,500),(0,2500,3000,3000),(0,500,500,2500),(2500,500,3000,2500)):
            self.box('nwell',bounds)
        self.assertEqual(self.audit()['measurements']['nwell']['holes'],1)
        self.box('nwell',(500,500,2500,2500));self.assertEqual(self.audit()['unreviewed'],0)

    def test_one_nm_opening_is_not_a_closed_hole(self):
        for bounds in ((0,0,3000,500),(0,2500,1499,3000),(1500,2500,3000,3000),(0,500,500,2500),(2500,500,3000,2500)):
            self.box('nwell',bounds)
        self.assertEqual(self.audit()['measurements']['nwell']['holes'],0)
        self.box('nwell',(1499,2500,1500,3000));self.assertEqual(self.audit()['measurements']['nwell']['holes'],1)

    def test_reflected_arrays_preserve_raw_counts_and_merged_holes(self):
        child=self.layout.create_cell('child');self.box('rpm',cell=child)
        ring=k.Polygon(k.Box(0,0,3000,3000));ring.insert_hole([k.Point(500,500),k.Point(500,2500),k.Point(2500,2500),k.Point(2500,500)])
        self.shapes('nwell',child).insert(ring)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.M90,1000,2000),k.Vector(5000,0),k.Vector(0,5000),2,3))
        r=self.audit();self.assertEqual(r['measurements']['raw']['rpm'],6);self.assertEqual(r['measurements']['nwell']['holes'],6)

    def test_exact_paths_match_polygons(self):
        path=k.Path([k.Point(0,0),k.Point(1000,0)],200);self.shapes('nwell').insert(path);a=self.audit()['measurements']
        self.shapes('nwell').clear();self.shapes('nwell').insert(path.polygon());self.assertEqual(a,self.audit()['measurements'])

    def test_unsupported_hole_geometry_units_and_transforms_fail(self):
        for shape in (k.Text('annotation',k.Trans()),k.Path([k.Point(0,0),k.Point(1000,0)],199),
                      k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(0,1000)])):
            self.shapes('nwell').clear();self.shapes('nwell').insert(shape)
            with self.assertRaises(ValueError):self.audit()
        self.shapes('nwell').clear();self.layout.dbu=.005
        with self.assertRaisesRegex(ValueError,'1 nm'):self.audit()
        self.layout.dbu=.001;child=self.layout.create_cell('extra_top');self.box('nwell',cell=child)
        with self.assertRaisesRegex(ValueError,'one top'):self.audit()
        self.top.insert(k.CellInstArray(child.cell_index(),k.ICplxTrans(2,0,False,0,0)))
        with self.assertRaisesRegex(ValueError,'transform'):self.audit()

    def test_missing_and_inconsistent_reports_fail(self):
        r=self.audit()
        for key in ('rows','source','measurements','scope'):
            bad=copy.deepcopy(r);bad.pop(key)
            with self.assertRaises(ValueError):checks.evaluate(bad,r['gds_sha256'],'control')
        for change in (lambda m:m['raw'].update(rpm=False),lambda m:m['nwell'].update(holes=1),lambda m:m['hints'].pop('dnwell')):
            bad=copy.deepcopy(r);change(bad['measurements'])
            with self.assertRaises(ValueError):checks.evaluate(bad,r['gds_sha256'],'control')

    def test_rehashed_added_subject_cannot_retain_an_absence(self):
        r=self.audit();self.box('cdnm');self.layout.write(str(self.path));r['gds_sha256']=hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'actual layout'):checks.validate_saved(r,self.path)

    def test_sources_bind_exact_records_without_waiving_na_or_selector_differences(self):
        from scripts import sky130_special_subject_review as review
        from scripts import check_sky130_filled_replay as fixture
        root=Path(__file__).resolve().parents[1];folder=Path(self.temp.name)/'fixture';fixture.unpack(fixture.BUNDLE,folder)
        catalog=json.loads((root/'docs/qualification/sky130-error-rule-inventory.json').read_bytes())
        proof=review.source_proof(folder/'sources',catalog);self.assertEqual(len(proof['bindings']),7)
        self.assertEqual(len(proof['discrepancies']),3)
        modified=copy.deepcopy(catalog);next(r for r in modified['rows'] if r['id']=='r1047')['description']='different target'
        with self.assertRaises(ValueError):review.source_proof(folder/'sources',modified)
        path=folder/'sources/docs/rules/layers/table-c3-device-lvs-other.csv';path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'Changed'):review.source_proof(folder/'sources',catalog)


if __name__=='__main__':unittest.main()
