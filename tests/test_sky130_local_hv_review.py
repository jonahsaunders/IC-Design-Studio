from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from scripts import sky130_local_hv_review as r


class LocalHvReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory(); cls.addClassCleanup(cls.temp.cleanup)
        cls.folder=Path(cls.temp.name)/'bundle'; r.fixture.unpack(r.fixture.BUNDLE,cls.folder)
        cls.reader=r.queue.RetainedReader(); cls.catalog,cls.baselines=r.queue.reconstruct(cls.reader)
        cls.inventory=cls.reader.read(r.INVENTORY)
        cls.proof=r.source_proof(cls.folder/'sources',cls.catalog,cls.inventory)
        cls.relations=cls.proof['bindings']
        cls.nominal=dict(status='nominal-voltage-contract-consistent',qualified=False,power_net_hv=[])

    def layout(self):
        layout=k.Layout(); layout.dbu=.001; top=layout.create_cell('control')
        top.shapes(layout.layer(68,20)).insert(k.Box(0,0,1000,1000))
        return layout,top

    def test_exact_bindings_exclude_hugepad_and_unrelated_requirements(self):
        self.assertEqual(len(self.relations),29)
        self.assertFalse(set(self.relations)&{'r900','r1047','r416','r537','r705','r988'})
        self.assertIsNone(self.relations['r1039']['parent'])
        self.assertIsNone(self.relations['r1046']['parent'])
        self.assertEqual(self.proof['aliases']['urpm']['pair'],[79,20])
        self.assertEqual(self.proof['definitions']['hugePad'],'pad.mk with width > 100um')

    def test_every_measured_operand_reopens_its_exact_dependents(self):
        layout,_=self.layout(); measured=r.measure(layout)
        self.assertTrue(all(d['disposition']=='absent-operand' for d in r.decisions(measured,self.relations,self.nominal).values()))
        for operand in measured['counts']:
            with self.subTest(operand=operand):
                changed=deepcopy(measured);changed['counts'][operand]=1
                actual=r.decisions(changed,self.relations,self.nominal)
                for key,relation in self.relations.items():
                    expected='unreviewed' if operand in relation['operands'] else 'absent-operand'
                    self.assertEqual(actual[key]['disposition'],expected)

    def test_empty_poly_resistor_purpose_cannot_hide_rpm_or_urpm(self):
        for pair in ((86,20),(79,20)):
            layout,top=self.layout();top.shapes(layout.layer(*pair)).insert(k.Box(0,0,500,500))
            measured=r.measure(layout);self.assertEqual(measured['counts']['poly.resistor'],0)
            actual=r.decisions(measured,self.relations,self.nominal)
            for key in ('r522','r528','r529','r530'):self.assertEqual(actual[key]['disposition'],'unreviewed')

    def test_raw_shapes_survive_hierarchy_and_array_transforms(self):
        for name,pair in r.LAYERS.items():
            with self.subTest(layer=name):
                layout,top=self.layout();child=layout.create_cell('child')
                child.shapes(layout.layer(*pair)).insert(k.Text('raw subject',k.Trans(5,5)))
                top.insert(k.CellInstArray(child.cell_index(),k.Trans(1,True,5000,5000),k.Vector(1000,0),k.Vector(0,1000),2,2))
                self.assertEqual(r.measure(layout)['counts'][name],4)

    def test_tap_corner_edge_and_overlap_all_prevent_absence(self):
        for box,expected in ((k.Box(1000,0,1500,1000),1),(k.Box(1000,1000,1500,1500),1),
                             (k.Box(500,500,1500,1500),1),(k.Box(1005,0,1500,1000),0)):
            layout,top=self.layout()
            top.shapes(layout.layer(65,20)).insert(k.Box(0,0,1000,1000))
            top.shapes(layout.layer(65,44)).insert(box)
            measured=r.measure(layout);self.assertEqual(measured['counts']['tap_interacting_diff'],expected)
            for key in ('r436','r437','r438','r439'):
                self.assertEqual(r.decisions(measured,self.relations,self.nominal)[key]['disposition'],
                                 'unreviewed' if expected else 'absent-operand')

    def test_normalized_labels_on_any_purpose_reopen_all_hv_subjects(self):
        for label in (' HV_BB ','HV_LV',' ShV_NwElL '):
            layout,top=self.layout();top.shapes(layout.layer(68,20)).insert(k.Text(label,k.Trans(5,5)))
            result=r.decisions(r.measure(layout),self.relations,self.nominal)
            for key,relation in self.relations.items():
                if relation['condition']=='nominal_hv':self.assertEqual(result[key]['disposition'],'unreviewed')

    def test_unsupported_geometry_cannot_disappear_in_boolean_operations(self):
        layout,top=self.layout()
        top.shapes(layout.layer(79,20)).insert(k.Path([k.Point(0,0),k.Point(100,0)],0))
        with self.assertRaisesRegex(ValueError,'Unsupported geometry'):r.measure(layout)
        layout,top=self.layout();child=layout.create_cell('fractional')
        child.shapes(layout.layer(65,20)).insert(k.Box(0,0,1000,1000))
        top.insert(k.CellInstArray(child.cell_index(),k.ICplxTrans(1.5,0,False,0,0)))
        with self.assertRaisesRegex(ValueError,'Unsupported geometry'):r.measure(layout)

    def test_incomplete_measurements_and_unverified_contract_rejected(self):
        layout,_=self.layout();good=r.measure(layout)
        for value in (-1,True,None):
            bad=deepcopy(good);bad['counts']['urpm']=value
            with self.assertRaises(ValueError):r.decisions(bad,self.relations,self.nominal)
        bad=deepcopy(good);bad['counts'].pop('shv_nwell_labels')
        with self.assertRaises(ValueError):r.decisions(bad,self.relations,self.nominal)
        for contract in ({},dict(self.nominal,qualified=True),dict(self.nominal,power_net_hv=['VDD'])):
            with self.assertRaises(ValueError):r.decisions(good,self.relations,contract)

    def test_changed_primary_definition_rejected_before_review(self):
        path=self.folder/'sources'/r.DEFINITION;before=path.read_bytes()
        try:
            path.write_bytes(before.replace(b'pad.mk with width > 100um',b'pad.dg with width > 100um'))
            with self.assertRaisesRegex(ValueError,'Changed local/HV source'):
                r.source_proof(self.folder/'sources',self.catalog,self.inventory)
        finally:path.write_bytes(before)


if __name__=='__main__':unittest.main()
