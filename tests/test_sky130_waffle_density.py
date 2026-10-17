"""An explicit density selector must actually be empty before exclusion."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import klayout.db as k
from scripts import sky130_waffle_density_review as review


class WaffleDensityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.folder=Path(cls.temp.name)/'inputs';review.marker.nsm.fixture.unpack(review.marker.nsm.fixture.BUNDLE,cls.folder)
        cls.catalog=json.loads((review.ROOT/review.marker.nsm.geometry.previous.CATALOG).read_bytes())
        cls.inventory=json.loads((review.ROOT/review.marker.nsm.geometry.previous.PERIPHERY).read_bytes())
        cls.geometry=json.loads(review.marker.nsm.geometry.OUTPUT.read_bytes())
        cls.nsm=json.loads(review.marker.nsm.OUTPUT.read_bytes());cls.previous=json.loads(review.marker.OUTPUT.read_bytes())
        cls.manual=json.loads(review.marker.nsm.scope.OUTPUT.read_bytes())

    def inputs(self,name='counter'):
        pick=lambda data:next(r for r in data['cases'] if r['case']==name)
        return (review.preceding(pick(self.geometry),pick(self.nsm),pick(self.previous)),
                deepcopy(pick(self.manual)),review.audit(self.folder/name/'filled.gds'))

    def reconcile(self,*args):return review.reconcile(self.catalog,self.inventory,*args)

    def test_exact_sources_bind_only_48_literal_records(self):
        proof=review.source_proof(self.folder/'sources',self.inventory,self.catalog)
        self.assertEqual(len(proof['bindings']),48)
        self.assertNotIn('r1141',proof['bindings'])
        self.assertEqual(proof['bindings']['r1210']['pair'],[62,24])
        self.assertEqual(proof['bindings']['s67']['pair'],[112,4])

    def test_all_three_references_preserve_every_other_decision(self):
        bindings=review.bindings(self.catalog,self.inventory)
        for name in ('counter','uart','apb'):
            old,manual,measured=self.inputs(name);result=self.reconcile(old,manual,measured)
            self.assertEqual(result['counts'],{'unreviewed':977,'executed-reviewed':356,'absent-operand':223})
            for before,after in zip(old['rows'],result['rows']):
                if before['id'] in bindings:self.assertEqual(after['disposition'],'absent-operand')
                else:self.assertEqual(before,after)
            self.assertEqual(manual['counts']['execution-review-required'],17)

    def test_each_nonempty_layer_reopens_all_its_twelve_records(self):
        bindings=review.bindings(self.catalog,self.inventory);old,manual,measured=self.inputs()
        for pair in review.PAIRS:
            changed=deepcopy(measured);changed['counts'][str(pair)]=1
            result=self.reconcile(old,manual,changed);rows={r['id']:r for r in result['rows']}
            for key,binding in bindings.items():
                self.assertEqual(rows[key]['disposition'],'unreviewed' if binding['pair']==list(pair) else 'absent-operand')

    def test_raw_shapes_and_text_in_rotated_arrays_never_disappear(self):
        for pair in review.PAIRS:
            for kind in ('box','polygon','path','zero-width-path','text'):
                layout=k.Layout();layout.dbu=.001;top=layout.create_cell('TOP');child=layout.create_cell('CHILD')
                shapes=child.shapes(layout.layer(*pair))
                if kind=='box':shapes.insert(k.Box(0,0,10,10))
                elif kind=='polygon':shapes.insert(k.Polygon([k.Point(0,0),k.Point(10,0),k.Point(5,10)]))
                elif kind=='text':shapes.insert(k.Text('present',k.Trans(0,0)))
                else:shapes.insert(k.Path([k.Point(0,0),k.Point(10,0)],0 if kind=='zero-width-path' else 2))
                top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.R90,100,200),k.Vector(40,0),k.Vector(0,40),2,3))
                self.assertEqual(review.measure(layout)['counts'][str(pair)],6)

    def test_invalid_counts_and_changed_identity_fail_closed(self):
        old,manual,measured=self.inputs()
        for key in measured['counts']:
            for value in (None,False,0.0,-1):
                changed=deepcopy(measured);changed['counts'][key]=value
                with self.assertRaises(ValueError):self.reconcile(old,manual,changed)
        for key in ('gds_sha256','top','checker_sha256'):
            changed=deepcopy(measured);changed[key]='stale'
            with self.assertRaises(ValueError):self.reconcile(old,manual,changed)

    def test_missing_or_false_parent_witness_is_not_accepted(self):
        old,manual,measured=self.inputs()
        for value in ({},{'(62, 24)':False},{'(62, 24)':1}):
            changed=deepcopy(manual);next(r for r in changed['rows'] if r['rule']=='m1.-')['witnesses']=value
            with self.assertRaises(ValueError):self.reconcile(old,changed,measured)

    def test_source_or_catalog_changes_require_new_review(self):
        bad=deepcopy(self.catalog);next(r for r in bad['rows'] if r['id']=='r1210')['description']='different'
        with self.assertRaises(ValueError):review.bindings(bad,self.inventory)
        source=self.folder/'sources/docs/rules/periphery/p038-m1_dotdash.csv';original=source.read_bytes()
        try:
            source.write_bytes(original+b'\n')
            with self.assertRaises(ValueError):review.source_proof(self.folder/'sources',self.inventory,self.catalog)
        finally:source.write_bytes(original)


if __name__=='__main__':unittest.main()
