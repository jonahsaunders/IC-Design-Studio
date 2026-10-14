"""Selected marker absence must not conceal a present enclosure target."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import klayout.db as k

from scripts import sky130_marker_reconciliation as review


class MarkerReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.scratch.cleanup)
        cls.folder=Path(cls.scratch.name)/'inputs';review.nsm.fixture.unpack(review.nsm.fixture.BUNDLE,cls.folder)
        cls.catalog=json.loads((review.ROOT/review.nsm.geometry.previous.CATALOG).read_bytes())
        cls.inventory=json.loads((review.ROOT/review.nsm.geometry.previous.PERIPHERY).read_bytes())
        cls.geometry=json.loads(review.nsm.geometry.OUTPUT.read_bytes())
        cls.nsm=json.loads(review.nsm.OUTPUT.read_bytes())
        cls.corrected=json.loads(review.nsm.scope.OUTPUT.read_bytes())
        cls.proof=review.source_proof(cls.folder/'sources',cls.inventory,cls.catalog)

    def references(self,name='counter'):
        old=next(r for r in self.geometry['cases'] if r['case']==name)
        nsm=next(r for r in self.nsm['cases'] if r['case']==name)
        corrected=deepcopy(next(r for r in self.corrected['cases'] if r['case']==name))
        return review.preceding(old,nsm),corrected,review.audit(self.folder/name/'filled.gds')

    def reconcile(self,old,manual,measurement,catalog=None):
        return review.reconcile(catalog or self.catalog,self.inventory,old,manual,measurement)

    def test_sources_bind_exactly_98_records_and_distinguish_installed_aliases(self):
        bindings=self.proof['bindings'];self.assertEqual(len(bindings),98)
        self.assertEqual(self.proof['aliases']['rdl']['source'],'installed')
        self.assertEqual(self.proof['aliases']['ccu1m']['source'],'installed')
        self.assertEqual(self.proof['aliases']['lvtn']['pair'],[125,44])
        self.assertEqual(bindings['r403']['proof'],'nwell_holes')
        self.assertEqual(bindings['r1276']['proof'],'rdl')
        self.assertEqual(self.proof['conditions']['rdl']['empty'],['rdl','pad','ccu1m'])
        self.assertIn('AND areaid.en',self.proof['definitions']['deFET_gate'])
        self.assertIn('rpm AND',self.proof['definitions']['prec_resistor'])
        self.assertFalse(set(bindings)&set(self.proof['exclusions']))

    def test_all_three_filled_references_change_only_the_explicit_decisions(self):
        for name in ('counter','uart','apb'):
            with self.subTest(case=name):
                old,manual,measured=self.references(name);old_copy=deepcopy(old);manual_copy=deepcopy(manual)
                result=self.reconcile(old,manual,measured)
                self.assertEqual(result['counts'],{'unreviewed':1025,'executed-reviewed':356,'absent-operand':175})
                self.assertEqual(old,old_copy);self.assertEqual(manual,manual_copy)
                self.assertEqual(manual['counts']['execution-review-required'],17)
                for before,after in zip(old['rows'],result['rows']):
                    if before['id'] in self.proof['bindings']:self.assertEqual(after['disposition'],'absent-operand')
                    else:self.assertEqual(after,before)

    def test_each_required_operand_independently_prevents_its_exclusions(self):
        old,manual,measured=self.references()
        for proof,(names,_) in review.PROOFS.items():
            for name in names:
                with self.subTest(proof=proof,operand=name):
                    changed=deepcopy(measured);changed['counts'][name]=1
                    result=self.reconcile(old,manual,changed);rows={r['id']:r for r in result['rows']}
                    for key,binding in self.proof['bindings'].items():
                        if binding['proof']==proof:self.assertEqual(rows[key]['disposition'],'unreviewed')

    def test_empty_encloser_never_hides_present_target(self):
        old,manual,measured=self.references()
        for key,target,encloser in (('r403','nwell_holes','dnwell'),('r1276','pad','rdl'),('r1064','hvi','hvntm')):
            changed=deepcopy(measured);changed['counts'][target]=1
            self.assertEqual(changed['counts'][encloser],0)
            result=self.reconcile(old,manual,changed)
            self.assertEqual(next(r['disposition'] for r in result['rows'] if r['id']==key),'unreviewed')

    def test_raw_markers_in_rotated_arrays_survive_shape_type_and_disk_roundtrip(self):
        for name,(pair,_,_,_) in review.LAYERS.items():
            if name=='nwell':continue
            for kind in ('box','polygon','path','zero-width-path','text'):
                with self.subTest(operand=name,kind=kind):
                    layout=k.Layout();layout.dbu=.001;top=layout.create_cell('TOP');child=layout.create_cell('CHILD')
                    shapes=child.shapes(layout.layer(*pair))
                    if kind=='box':shapes.insert(k.Box(0,0,10,10))
                    elif kind=='polygon':shapes.insert(k.Polygon([k.Point(0,0),k.Point(10,0),k.Point(5,10)]))
                    elif kind=='text':shapes.insert(k.Text('present',k.Trans(0,0)))
                    else:shapes.insert(k.Path([k.Point(0,0),k.Point(10,0)],0 if kind=='zero-width-path' else 2))
                    top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.R90,100,200),k.Vector(40,0),k.Vector(0,40),2,3))
                    measured=review.measure(layout);self.assertEqual(measured['counts'][name],6)
                    for proof,(names,_) in review.PROOFS.items():
                        if name in names:self.assertFalse(review.absent(measured,proof))
                    with tempfile.TemporaryDirectory() as td:
                        path=Path(td)/'marker.gds';layout.write(str(path))
                        self.assertEqual(review.audit(path)['counts'],measured['counts'])

    def test_nwell_holes_use_merged_material_not_empty_deep_well(self):
        layout=k.Layout();layout.dbu=.001;top=layout.create_cell('TOP');shapes=top.shapes(layout.layer(64,20))
        ring=k.Region(k.Box(0,0,100,100))-k.Region(k.Box(20,20,80,80));shapes.insert(ring)
        measured=review.measure(layout);self.assertEqual(measured['counts']['dnwell'],0)
        self.assertEqual(measured['counts']['nwell_holes'],1);self.assertFalse(review.absent(measured,'nwell_holes'))
        shapes.insert(k.Box(20,20,80,80))
        self.assertEqual(review.measure(layout)['counts']['nwell_holes'],0)
        shapes.clear();shapes.insert(ring-k.Region(k.Box(0,40,30,60)))
        self.assertEqual(review.measure(layout)['counts']['nwell_holes'],0)
        shapes.clear();child=layout.create_cell('CHILD');child.shapes(layout.layer(64,20)).insert(ring)
        top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.R90,100,200),k.Vector(150,0),k.Vector(0,150),2,3))
        self.assertEqual(review.measure(layout)['counts']['nwell_holes'],6)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'holes.gds';layout.write(str(path))
            self.assertEqual(review.audit(path)['counts']['nwell_holes'],6)

    def test_unsupported_hole_geometry_transform_grid_and_top_fail_closed(self):
        for fault in ('path','magnification','rotation','grid','top'):
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                layout=k.Layout();layout.dbu=.001;top=layout.create_cell('TOP')
                if fault=='path':top.shapes(layout.layer(64,20)).insert(k.Path([k.Point(0,0),k.Point(10,10)],3))
                elif fault in ('magnification','rotation'):
                    child=layout.create_cell('CHILD');child.shapes(layout.layer(64,20)).insert(k.Box(0,0,10,10))
                    transform=k.ICplxTrans(2 if fault=='magnification' else 1,45 if fault=='rotation' else 0,False,0,0)
                    top.insert(k.CellInstArray(child.cell_index(),transform))
                elif fault=='grid':layout.dbu=.002
                else:layout.create_cell('SECOND_TOP')
                review.measure(layout)

    def test_missing_extra_boolean_fractional_and_negative_measurements_fail(self):
        _,_,measured=self.references()
        for key in measured['counts']:
            for value in (None,False,0.0,-1):
                changed=deepcopy(measured);changed['counts'][key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):review.absent(changed,'dnwell')
        for fault in ('missing','extra'):
            changed=deepcopy(measured)
            if fault=='missing':changed['counts'].pop('nwell_holes')
            else:changed['counts']['unknown']=0
            with self.assertRaises(ValueError):review.absent(changed,'dnwell')

    def test_missing_wrong_or_fabricated_parent_witnesses_are_rejected(self):
        old,manual,measured=self.references()
        targets={b['parent'] for b in self.proof['bindings'].values()}
        for target in targets:
            for witness in ({},{'unexpected':0},{'unexpected':False}):
                changed=deepcopy(manual);next(r for r in changed['rows'] if r['id']==target)['witnesses']=witness
                with self.subTest(target=target,witness=witness),self.assertRaises(ValueError):self.reconcile(old,changed,measured)

    def test_stale_source_and_case_or_changed_complete_catalog_are_rejected(self):
        old,manual,measured=self.references()
        for key in ('top','gds_sha256','checker_sha256'):
            changed=deepcopy(measured);changed[key]='stale'
            with self.assertRaises(ValueError):self.reconcile(old,manual,changed)
        changed=deepcopy(manual);changed['case']='wrong'
        with self.assertRaises(ValueError):self.reconcile(old,changed,measured)
        for fault in ('missing','duplicate','count','identity','already-reviewed'):
            changed=deepcopy(old)
            if fault=='missing':changed['rows'].pop()
            elif fault=='duplicate':changed['rows'].append(deepcopy(changed['rows'][0]))
            elif fault=='count':changed['counts']['unreviewed']-=1
            elif fault=='identity':changed['rows'][0]['rule']='wrong'
            else:
                next(r for r in changed['rows'] if r['id']=='r393')['disposition']='absent-operand'
                changed['counts']=dict(Counter(r['disposition'] for r in changed['rows']))
            with self.subTest(fault=fault),self.assertRaises(ValueError):self.reconcile(changed,manual,measured)
        changed=deepcopy(self.catalog);next(r for r in changed['rows'] if r['id']=='r415')['description']='0.235 different threshold'
        with self.assertRaises(ValueError):self.reconcile(old,manual,measured,changed)

    def test_disputed_threshold_is_retained_without_choosing_a_number(self):
        conflict=self.proof['discrepancies'][0]
        self.assertEqual(conflict['status'],'numeric-disagreement-unresolved')
        self.assertTrue(next(r['description'] for r in self.catalog['rows'] if r['id']=='r415').startswith('0.19 '))
        self.assertEqual(next(r['value'] for r in self.inventory['rule_rows'] if r['rule']=='lvtn.3b'),'0.235')
        self.assertEqual((conflict['catalog_value_um'],conflict['periphery_value_um']),('0.19','0.235'))

    def test_changed_captured_source_and_derived_definitions_cannot_pass(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)
            for name in self.proof['files']:
                path=source/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes((self.folder/'sources'/name).read_bytes())
            for name in self.proof['files']:
                path=source/name;original=path.read_bytes();path.write_bytes(original+b'\n')
                with self.subTest(source=name),self.assertRaises(ValueError):review.source_proof(source,self.inventory,self.catalog)
                path.write_bytes(original)
        bad=deepcopy(review.DEFINITIONS);bad['deFET_gate']='poly'
        with patch.object(review,'DEFINITIONS',bad),self.assertRaises(ValueError):
            review.source_proof(self.folder/'sources',self.inventory,self.catalog)
        bad=deepcopy(review.LAYERS);bad['rdl']=((74,20),'rdl','mask','installed')
        with patch.object(review,'LAYERS',bad),self.assertRaises(ValueError):
            review.source_proof(self.folder/'sources',self.inventory,self.catalog)


if __name__=='__main__':unittest.main()
