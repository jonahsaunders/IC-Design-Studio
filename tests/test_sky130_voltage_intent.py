import copy
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from scripts import sky130_voltage_intent_review as r


class VoltageIntentTests(unittest.TestCase):
    def layout(self):
        layout=k.Layout();layout.dbu=.001;top=layout.create_cell('control')
        top.shapes(layout.layer(68,20)).insert(k.Box(0,0,1000,1000))
        return layout,top

    def checked(self):
        return dict(status='nominal-voltage-contract-consistent',power_net_hv=[],qualified=False)

    def test_conditional_scope_is_explicit(self):
        layout,_=self.layout();result=r.decisions(r.measure(layout),self.checked())
        self.assertEqual(set(result),set(r.RULES))
        self.assertTrue(all(d['disposition']=='absent-operand' and
                            d['condition']=='declared-nominal-reference-voltage-contract' for d in result.values()))

    def test_each_nonempty_raw_selector_reopens_all_three(self):
        for pair in r.LAYERS.values():
            layout,top=self.layout();top.shapes(layout.layer(*pair)).insert(k.Box(0,0,1000,1000))
            self.assertTrue(all(d['disposition']=='execution-review-required'
                                for d in r.decisions(r.measure(layout),self.checked()).values()))

    def test_raw_text_and_exception_labels_survive_transformed_arrays(self):
        for pair in r.LAYERS.values():
            layout,top=self.layout();child=layout.create_cell('child')
            child.shapes(layout.layer(*pair)).insert(k.Text('raw selector',k.Trans(5,5)))
            top.insert(k.CellInstArray(child.cell_index(),k.Trans(1,True,100,200),k.Vector(500,0),k.Vector(0,500),2,2))
            measured=r.measure(layout)
            self.assertEqual(measured['raw_layers'][next(n for n,p in r.LAYERS.items() if p==pair)],4)
        for label in r.LABELS:
            layout,top=self.layout();child=layout.create_cell('child')
            child.shapes(layout.layer(64,5)).insert(k.Text(' '+label.upper()+' ',k.Trans()))
            top.insert(k.CellInstArray(child.cell_index(),k.Trans(1,True,100,200)))
            measured=r.measure(layout)
            self.assertEqual(measured['exception_labels'][label],1)
            self.assertTrue(all(d['disposition']=='execution-review-required' for d in r.decisions(measured,self.checked()).values()))

    def test_empty_tags_without_checked_contract_never_pass(self):
        layout,_=self.layout();measured=r.measure(layout)
        for key,value in (('status','unchecked'),('power_net_hv',['VDD']),('qualified',True)):
            changed=self.checked();changed[key]=value
            with self.assertRaises(ValueError):r.decisions(measured,changed)

    def test_missing_or_invalid_measurement_rejected(self):
        layout,_=self.layout();measured=r.measure(layout)
        for value in (True,-1,'0',0.0):
            changed=copy.deepcopy(measured);changed['raw_layers']['hvi']=value
            with self.assertRaises(ValueError):r.decisions(changed,self.checked())
        for category,key in (('raw_layers','hvi'),('exception_labels','hv_bb')):
            changed=copy.deepcopy(measured);del changed[category][key]
            with self.assertRaises(ValueError):r.decisions(changed,self.checked())

    def test_unsupported_geometry_cannot_vanish(self):
        layout,top=self.layout()
        top.shapes(layout.layer(75,20)).insert(k.Path([k.Point(0,0),k.Point(100,0)],0))
        with self.assertRaises(ValueError):r.measure(layout)

    def test_actual_source_binding_and_changed_source(self):
        with TemporaryDirectory() as td:
            folder=Path(td)/'inputs';r.previous.marker.nsm.fixture.unpack(r.previous.marker.nsm.fixture.BUNDLE,folder)
            inventory=r.read(r.ROOT/r.previous.marker.nsm.geometry.previous.PERIPHERY)
            proof=r.source_proof(folder/'sources',inventory)
            self.assertEqual(set(proof['parents']),set(r.RULES))
            path=folder/'sources/docs/rules/hv.rst';path.write_bytes(path.read_bytes()+b'\nchanged\n')
            with self.assertRaises(ValueError):r.source_proof(folder/'sources',inventory)

    def test_changed_captured_file_is_rejected(self):
        with TemporaryDirectory() as td:
            path=Path(td)/'capture';path.write_bytes(b'original')
            digest=hashlib.sha256(b'original').hexdigest()
            self.assertEqual(r.authenticated(path,digest),b'original')
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):r.authenticated(path,digest)


if __name__=='__main__':unittest.main()
