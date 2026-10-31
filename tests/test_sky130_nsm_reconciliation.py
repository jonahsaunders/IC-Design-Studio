"""A nitride-seal exclusion needs both source-defined operands to be empty."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import klayout.db as k

from scripts import sky130_nsm_reconciliation as review


class NsmReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.scratch.cleanup)
        cls.folder=Path(cls.scratch.name)/'inputs'
        cls.manifest=review.fixture.unpack(review.fixture.BUNDLE,cls.folder)
        cls.catalog=json.loads((review.ROOT/review.geometry.previous.CATALOG).read_bytes())
        cls.inventory=json.loads((review.ROOT/review.geometry.previous.PERIPHERY).read_bytes())
        cls.baseline=json.loads(review.geometry.OUTPUT.read_bytes())
        cls.corrected=json.loads(review.scope.OUTPUT.read_bytes())
        cls.proof=review.source_proof(cls.folder/'sources',cls.inventory,cls.catalog)

    def references(self,name='counter'):
        old=deepcopy(next(r for r in self.baseline['cases'] if r['case']==name))
        corrected=deepcopy(next(r for r in self.corrected['cases'] if r['case']==name))
        measurement=review.audit(self.folder/name/'filled.gds')
        return old,corrected,measurement

    def test_exact_sources_define_both_operands_and_only_38_records(self):
        self.assertEqual(self.proof['definition']['Defining algorithm'],'nsm.dg OR nsm.mk')
        self.assertEqual(self.proof['aliases'],[
            dict(name='nsm',purpose='drawing',pair=[61,20]),dict(name='cnsm',purpose='mask',pair=[22,0])])
        self.assertEqual(set(self.proof['bindings']),{'r'+str(i) for i in range(950,988)})
        self.assertEqual({b['parent'] for b in self.proof['bindings'].values()},
                         {review.SOURCE+'#'+str(i) for i in (1,2,3)})

    def test_three_exact_layouts_change_only_the_reviewed_records(self):
        for name in ('counter','uart','apb'):
            with self.subTest(case=name):
                old,corrected,measurement=self.references(name)
                saved=deepcopy(old);manual_saved=deepcopy(corrected)
                result=review.reconcile(self.catalog,old,corrected,measurement)
                self.assertEqual(result['counts'],{'unreviewed':1123,'executed-reviewed':356,'absent-operand':77})
                self.assertEqual(old,saved);self.assertEqual(corrected,manual_saved)
                for before,after in zip(old['rows'],result['rows']):
                    if before['id'] in self.proof['bindings']:
                        self.assertEqual(after['disposition'],'absent-operand')
                    else:self.assertEqual(after,before)
                self.assertEqual(corrected['counts']['execution-review-required'],17)

    def test_frame_diecut_and_hvtr_exclusions_stay_reopened(self):
        old,corrected,measurement=self.references()
        result=review.reconcile(self.catalog,old,corrected,measurement)
        rows={r['id']:r for r in result['rows']}
        for number in range(988,1024):self.assertEqual(rows['r'+str(number)]['disposition'],'unreviewed')
        for row in result['rows']:
            if row['id'].startswith('s'):self.assertEqual(row['disposition'],'unreviewed')
        for rule in ('nsm.3a','nsm.3b','hvtr.3'):
            self.assertEqual(next(r['disposition'] for r in corrected['rows'] if r['rule']==rule),'execution-review-required')

    def test_either_nonempty_operand_prevents_all_new_exclusions(self):
        old,corrected,measurement=self.references()
        for pair in review.PAIRS:
            with self.subTest(pair=pair):
                changed=deepcopy(measurement);changed['shape_counts'][str(pair)]=1
                result=review.reconcile(self.catalog,old,corrected,changed)
                self.assertEqual(result,old)

    def test_recursive_shape_types_and_array_instances_cannot_disappear(self):
        for pair in review.PAIRS:
            for kind in ('box','polygon','path','zero-width-path','text'):
                with self.subTest(pair=pair,kind=kind):
                    layout=k.Layout();layout.dbu=.001;top=layout.create_cell('TOP');child=layout.create_cell('CHILD')
                    shapes=child.shapes(layout.layer(*pair))
                    if kind=='box':shapes.insert(k.Box(0,0,10,10))
                    elif kind=='polygon':shapes.insert(k.Polygon([k.Point(0,0),k.Point(10,0),k.Point(5,10)]))
                    elif kind=='path':shapes.insert(k.Path([k.Point(0,0),k.Point(10,0)],2))
                    elif kind=='zero-width-path':shapes.insert(k.Path([k.Point(0,0),k.Point(10,0)],0))
                    else:shapes.insert(k.Text('nsm',k.Trans(0,0)))
                    top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.R90,100,200),k.Vector(40,0),k.Vector(0,40),2,3))
                    measured=review.measure(layout)
                    self.assertEqual(measured['shape_counts'][str(pair)],6)
                    self.assertFalse(review.is_absent(measured))
                    with tempfile.TemporaryDirectory() as td:
                        path=Path(td)/'control.gds';layout.write(str(path))
                        disk=review.audit(path)
                        self.assertEqual(disk['shape_counts'],measured['shape_counts'])
                        self.assertFalse(review.is_absent(disk))

    def test_wrong_purpose_does_not_change_exact_operand_definition(self):
        layout=k.Layout();layout.dbu=.001;top=layout.create_cell('TOP')
        for pair in ((61,21),(22,20),(81,11),(81,12)):
            top.shapes(layout.layer(*pair)).insert(k.Box(0,0,10,10))
        self.assertTrue(review.is_absent(review.measure(layout)))
        layout.create_cell('SECOND_TOP')
        with self.assertRaises(ValueError):review.measure(layout)

    def test_missing_boolean_fractional_negative_or_extra_measurements_fail(self):
        _,_,measurement=self.references()
        for bad in (None,False,True,0.0,-1):
            changed=deepcopy(measurement);changed['shape_counts']['(22, 0)']=bad
            with self.subTest(value=bad),self.assertRaises(ValueError):review.is_absent(changed)
        for fault in ('missing','extra'):
            changed=deepcopy(measurement)
            if fault=='missing':changed['shape_counts'].pop('(22, 0)')
            else:changed['shape_counts']['(61, 21)']=0
            with self.assertRaises(ValueError):review.is_absent(changed)

    def test_stale_case_top_gds_and_source_are_rejected(self):
        old,corrected,measurement=self.references()
        for key in ('top','gds_sha256','checker_sha256'):
            changed=deepcopy(measurement);changed[key]='changed'
            with self.subTest(key=key),self.assertRaises(ValueError):review.reconcile(self.catalog,old,corrected,changed)
        corrected['case']='different'
        with self.assertRaises(ValueError):review.reconcile(self.catalog,old,corrected,measurement)

    def test_parent_measurement_identity_and_catalog_changes_fail(self):
        old,corrected,measurement=self.references()
        for field,value in (('rule','wrong'),('record',10),('source_sha256','0'*64),
                            ('witnesses',{'(61, 20)':0}),('witnesses',{'(61, 20)':0,'(22, 0)':False})):
            bad=deepcopy(corrected);row=next(r for r in bad['rows'] if r['rule']=='nsm.3');row[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):review.reconcile(self.catalog,old,bad,measurement)
        catalog=deepcopy(self.catalog);next(r for r in catalog['rows'] if r['id']=='r952')['description']='wrong target'
        with self.assertRaises(ValueError):review.reconcile(catalog,old,corrected,measurement)
        for fault in ('missing','duplicate','count','already-reviewed'):
            bad=deepcopy(old)
            if fault=='missing':bad['rows'].pop()
            elif fault=='duplicate':bad['rows'].append(deepcopy(bad['rows'][0]))
            elif fault=='count':bad['counts']['unreviewed']-=1
            else:
                next(r for r in bad['rows'] if r['id']=='r950')['disposition']='absent-operand'
                bad['counts']=dict(Counter(r['disposition'] for r in bad['rows']))
            with self.subTest(fault=fault),self.assertRaises(ValueError):review.reconcile(self.catalog,bad,corrected,measurement)

    def test_changed_published_source_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)
            for name in (review.SOURCE,review.DEFINITION,review.MAPPING):
                path=source/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes((self.folder/'sources'/name).read_bytes())
            for name in (review.SOURCE,review.DEFINITION,review.MAPPING):
                path=source/name;original=path.read_bytes();path.write_bytes(original+b'\n')
                with self.subTest(source=name),self.assertRaises(ValueError):review.source_proof(source,self.inventory,self.catalog)
                path.write_bytes(original)


if __name__=='__main__':unittest.main()
