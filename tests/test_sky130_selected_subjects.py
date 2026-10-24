import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from scripts import sky130_selected_subject_review as r


class SelectedSubjectsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=json.loads((r.ROOT/r.marker.nsm.geometry.previous.CATALOG).read_bytes())
        cls.inventory=json.loads((r.ROOT/r.marker.nsm.geometry.previous.PERIPHERY).read_bytes())
        cls.relations=r.bindings(cls.catalog,cls.inventory)

    def layout(self):
        layout=k.Layout();layout.dbu=.001;top=layout.create_cell('control')
        top.shapes(layout.layer(68,20)).insert(k.Box(0,0,1000,1000))
        return layout,top

    def test_reviewed_inventory_and_explicit_exclusions(self):
        self.assertEqual(len(self.relations),63)
        self.assertFalse(set(self.relations)&{'r416','r426','r496','r537','r705','r988','r1006','r1029','r1141'})
        self.assertEqual(self.relations['r495']['operands'],['hvi','areaid.hl'])

    def test_each_operand_reopens_all_dependent_records(self):
        layout,_=self.layout(); measurement=r.measure(layout)
        self.assertTrue(all(d['disposition']=='absent-operand' for d in r.decisions(measurement,self.relations).values()))
        for operand in measurement['counts']:
            with self.subTest(operand=operand):
                changed=copy.deepcopy(measurement);changed['counts'][operand]=1
                actual=r.decisions(changed,self.relations)
                for key,relation in self.relations.items():
                    self.assertEqual(actual[key]['disposition'],'unreviewed' if operand in relation['operands'] else 'absent-operand')

    def test_raw_text_and_zero_width_path_in_transformed_array(self):
        for pair in r.LAYERS.values():
            with self.subTest(pair=pair):
                layout,top=self.layout();child=layout.create_cell('child')
                shapes=child.shapes(layout.layer(*pair))
                shapes.insert(k.Text('not empty',k.Trans(5,5)))
                shapes.insert(k.Path([k.Point(10,10),k.Point(20,10)],0))
                top.insert(k.CellInstArray(child.cell_index(),k.Trans(1,True,100,200),k.Vector(500,0),k.Vector(0,500),2,2))
                # Unsupported raw paths must fail closed, not vanish in a Boolean.
                with self.assertRaises(ValueError):r.measure(layout)
                shapes.clear();shapes.insert(k.Text('not empty',k.Trans(5,5)))
                measured=r.measure(layout)
                name=next(name for name,value in r.LAYERS.items() if value==pair)
                self.assertEqual(measured['counts'][name],4)

    def test_varactor_boolean_operand_survives_hierarchy(self):
        layout,top=self.layout();child=layout.create_cell('child')
        child.shapes(layout.layer(66,20)).insert(k.Box(0,0,200,1000))
        child.shapes(layout.layer(65,44)).insert(k.Box(0,0,1000,200))
        top.insert(k.CellInstArray(child.cell_index(),k.Trans(1,True,5000,0)))
        measured=r.measure(layout)
        self.assertEqual(measured['counts']['poly_tap_intersections'],1)
        actual=r.decisions(measured,self.relations)
        self.assertEqual(actual['r829']['disposition'],'unreviewed')
        self.assertEqual(actual['r724']['disposition'],'unreviewed')

    def test_slotted_licon_requires_exact_merged_rectangle(self):
        layout,top=self.layout();layer=layout.layer(66,44)
        top.shapes(layer).insert(k.Box(0,0,190,1000))
        top.shapes(layer).insert(k.Box(0,1000,190,2000))
        top.shapes(layer).insert(k.Box(1000,0,3000,190))
        self.assertEqual(r.measure(layout)['counts']['slotted_licon'],2)

    def test_named_cell_selection_in_complete_hierarchy(self):
        for key,names in r.NAMED_CELL_GROUPS.items():
            if key not in {p for operands in r.CONDITIONS.values() for p in operands}:continue
            for name in names:
                layout,_=self.layout();layout.create_cell(name.replace('*','variant'))
                # Multiple top cells are unsupported; instantiate the candidate
                # to retain an unambiguous submitted hierarchy.
                top=layout.cell('control');child=layout.cell(name.replace('*','variant'))
                top.insert(k.CellInstArray(child.cell_index(),k.Trans()))
                self.assertEqual(r.measure(layout)['counts'][key],1)

    def test_invalid_measurements_fail_closed(self):
        layout,_=self.layout();measurement=r.measure(layout)
        for value in (True,-1,0.0,'0'):
            changed=copy.deepcopy(measurement);changed['counts']['hvi']=value
            with self.assertRaises(ValueError):r.decisions(changed,self.relations)
        changed=copy.deepcopy(measurement);del changed['counts']['hvi']
        with self.assertRaises(ValueError):r.decisions(changed,self.relations)

    def test_unsupported_transform_and_layer(self):
        layout,top=self.layout();child=layout.create_cell('child')
        child.shapes(layout.layer(66,20)).insert(k.Box(0,0,100,100))
        top.insert(k.CellInstArray(child.cell_index(),k.ICplxTrans(1,45,False,0,0)))
        with self.assertRaises(ValueError):r.measure(layout)
        layout,top=self.layout();top.shapes(layout.layer(999,999)).insert(k.Box(0,0,100,100))
        with self.assertRaises(ValueError):r.measure(layout)

    def test_changed_catalog_and_missing_unrelated_ledger_record(self):
        changed=copy.deepcopy(self.catalog);changed['rows'][495]['description']='different'
        with self.assertRaises(ValueError):r.bindings(changed,self.inventory)
        rows,_=r.baseline('counter',self.catalog)
        del rows[-1]
        with self.assertRaises(ValueError):r.validate_rows(rows,self.catalog)

    def test_failed_parent_cannot_be_discharged(self):
        rows,_=r.baseline('counter',self.catalog)
        manual=copy.deepcopy(next(c for c in json.loads(r.marker.nsm.scope.OUTPUT.read_bytes())['cases'] if c['case']=='counter'))
        parent=next(p for p in manual['rows'] if p['id']==self.relations['r495']['parent'])
        parent['disposition']='execution-review-required'
        from collections import Counter
        manual['counts']=dict(Counter(p['disposition'] for p in manual['rows']))
        layout,_=self.layout()
        with self.assertRaises(ValueError):r.reconcile(rows,self.catalog,self.relations,r.measure(layout),manual)

    def test_exact_reference_fixture_and_source_mutation(self):
        with TemporaryDirectory() as td:
            folder=Path(td)/'inputs';fixture=r.marker.nsm.fixture
            manifest=fixture.unpack(fixture.BUNDLE,folder)
            proof=r.source_proof(folder/'sources',self.catalog,self.inventory)
            for entry in manifest['cases']:
                layout=k.Layout();layout.read(str(folder/entry['gds']))
                decisions=r.decisions(r.measure(layout),proof['bindings'])
                self.assertTrue(all(d['disposition']=='absent-operand' for d in decisions.values()),entry['case'])
            source=folder/'sources/docs/rules/periphery/p047-hvnwell_dotdash.csv'
            source.write_bytes(source.read_bytes()+b'changed')
            with self.assertRaises(ValueError):r.source_proof(folder/'sources',self.catalog,self.inventory)


if __name__=='__main__':unittest.main()
