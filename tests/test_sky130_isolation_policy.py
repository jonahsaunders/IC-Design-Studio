import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from scripts import sky130_isolation_policy as r
from scripts import sky130_voltage_intent_review as previous


class IsolationPolicyTests(unittest.TestCase):
    def fixture(self):
        layout=k.Layout();layout.dbu=.001;top=layout.create_cell('control')
        top.shapes(layout.layer(65,20)).insert(k.Box(0,0,1000,500))
        top.shapes(layout.layer(66,20)).insert(k.Box(400,-100,600,600))
        return layout,top

    def test_mode_is_explicit_and_boolean(self):
        layout,_=self.fixture()
        for value in (None,{},False,{'nfet_in_dnwell':None},{'nfet_in_dnwell':0},
                      {'nfet_in_dnwell':'false'},{'nfet_in_dnwell':False,'skip':True}):
            with self.assertRaises(ValueError):r.check(layout,value)

    def test_bulk_records_failure_measurements_without_claiming_pass(self):
        layout,_=self.fixture();result=r.check(layout,{'nfet_in_dnwell':False})
        self.assertEqual(result['status'],'NOT_REQUESTED')
        self.assertEqual(result['measured_noncontained_gates'],1)
        self.assertEqual(result['disposition'],'declared-option-not-required')
        self.assertFalse(result['enforced']);self.assertFalse(result['qualified'])

    def test_enabled_isolation_pass_and_missing_or_partial_well_fail(self):
        for box,status in ((None,'FAIL'),(k.Box(400,0,599,500),'FAIL'),(k.Box(399,-1,601,501),'PASS'),
                           (k.Box(400,0,600,500),'PASS')):
            with self.subTest(box=box):
                layout,top=self.fixture()
                if box is not None:top.shapes(layout.layer(64,18)).insert(box)
                result=r.check(layout,{'nfet_in_dnwell':True})
                self.assertEqual(result['status'],status)
                self.assertTrue(result['enforced'])

    def test_pfet_is_not_an_nfet_target(self):
        layout,top=self.fixture();top.shapes(layout.layer(64,20)).insert(k.Box(-100,-200,1100,800))
        result=r.check(layout,{'nfet_in_dnwell':True})
        self.assertEqual(result['status'],'PASS');self.assertEqual(result['measurement']['nfet_gates'],0)
        self.assertEqual(result['measurement']['pfet_gates'],1)

    def test_dnwell_hole_does_not_establish_enclosure(self):
        layout,top=self.fixture();well=k.Polygon(k.Box(-100,-100,1100,600))
        well.insert_hole(k.Box(450,200,550,300));top.shapes(layout.layer(64,18)).insert(well)
        self.assertEqual(r.check(layout,{'nfet_in_dnwell':True})['status'],'FAIL')

    def test_union_of_adjacent_well_polygons_covers_gate(self):
        layout,top=self.fixture()
        for box in (k.Box(300,-100,500,600),k.Box(500,-100,700,600)):
            top.shapes(layout.layer(64,18)).insert(box)
        result=r.check(layout,{'nfet_in_dnwell':True})
        self.assertEqual(result['status'],'PASS');self.assertEqual(result['measurement']['dnwell_polygons'],1)

    def test_transformed_array_checks_every_gate(self):
        layout,child=self.fixture();top=layout.create_cell('array')
        top.insert(k.CellInstArray(child.cell_index(),k.Trans(1,True,1000,2000),k.Vector(2000,0),k.Vector(0,2000),2,2))
        result=r.check(layout,{'nfet_in_dnwell':True})
        self.assertEqual(result['measurement']['nfet_gates'],4)
        self.assertEqual(result['measured_noncontained_gates'],4)

    def test_raw_text_is_recorded_but_cannot_enclose_a_gate(self):
        layout,top=self.fixture();top.shapes(layout.layer(64,18)).insert(k.Text('dnwell',k.Trans(400,100)))
        result=r.check(layout,{'nfet_in_dnwell':True})
        self.assertEqual(result['status'],'FAIL');self.assertEqual(result['measurement']['raw_dnwell_texts'],1)
        self.assertEqual(result['measurement']['dnwell_polygons'],0)

    def test_bulk_mode_cannot_silence_unsupported_geometry(self):
        layout,top=self.fixture()
        top.shapes(layout.layer(64,18)).insert(k.Path([k.Point(0,0),k.Point(1000,0)],0))
        with self.assertRaises(ValueError):r.check(layout,{'nfet_in_dnwell':False})

    def test_gate_straddling_well_needs_review(self):
        layout,top=self.fixture();top.shapes(layout.layer(64,20)).insert(k.Box(500,-100,1100,600))
        with self.assertRaises(ValueError):r.check(layout,{'nfet_in_dnwell':True})

    def test_invalid_measurement_is_rejected(self):
        layout,_=self.fixture();measurement=r.measure(layout)
        for value in (True,-1,2,'0',0.0):
            changed=copy.deepcopy(measurement);changed['nfet_not_contained']=value
            with self.assertRaises(ValueError):r.evaluate(changed,{'nfet_in_dnwell':False})

    def test_published_source_binding(self):
        with TemporaryDirectory() as td:
            folder=Path(td)/'inputs';fixture=previous.previous.marker.nsm.fixture;fixture.unpack(fixture.BUNDLE,folder)
            inventory=previous.read(r.ROOT/'docs/qualification/sky130-rule-inventory.json')
            proof=r.source_proof(folder/'sources',inventory)
            self.assertEqual(proof['rule']['id'],r.RULE_ID)
            path=folder/'sources'/r.SOURCE;path.write_bytes(path.read_bytes()+b'changed')
            with self.assertRaises(ValueError):r.source_proof(folder/'sources',inventory)


if __name__=='__main__':unittest.main()
