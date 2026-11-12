import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from icstudio import digital_sky130_selected_targets as checks


class SelectedTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'input.gds';self.layout=k.Layout();self.layout.dbu=.001
        self.top=self.layout.create_cell('control')

    def shapes(self,name,cell=None):
        pair=checks.LAYERS[name] if isinstance(name,str) else name
        return (cell or self.top).shapes(self.layout.layer(*pair))

    def box(self,name,bounds=(0,0,1000,1000),cell=None):self.shapes(name,cell).insert(k.Box(*bounds))

    def audit(self):self.layout.write(str(self.path));return checks.audit(self.path)

    def pending(self,report):return {r['id'] for r in report['rows'] if r['disposition']=='unreviewed'}

    def test_empty_targets_are_sixteen_absences_not_numerical_execution(self):
        report=self.audit();self.assertEqual(len(report['rows']),16);self.assertEqual(report['unreviewed'],0)
        self.assertTrue(all(r['disposition']=='absent-operand' for r in report['rows']))
        self.assertFalse(report['qualified']);self.assertFalse(report['chunk_complete']);checks.validate_saved(report,self.path)

    def test_all_raw_purposes_count_every_shape_kind(self):
        for name in checks.LAYERS:
            expected={key for group in checks.GROUPS.values() if name in group['raw'] for key in group['ids']}
            for shape in (k.Box(0,0,100,100),k.Text('marker',k.Trans()),k.Path([k.Point(0,0),k.Point(100,0)],1)):
                self.shapes(name).clear();self.shapes(name).insert(shape)
                with self.subTest(name=name,shape=shape):self.assertEqual(self.pending(self.audit()),expected)
            self.shapes(name).clear()

    def test_missing_metal_cannot_waive_a_bondpad(self):
        self.box('pad');report=self.audit()
        self.assertEqual(self.pending(report),set(checks.GROUPS['bond_pad']['ids']))
        self.assertNotIn('violations',report)

    def test_missing_enclosing_implant_cannot_waive_hvi_target(self):
        self.box('hvi');self.box((65,20));self.assertIn('r1493',self.pending(self.audit()))

    def test_inductor_terminal_and_label_only_inputs_block_absence(self):
        for name in ('inductor_label','inductor_terminal1','inductor_terminal2','inductor_terminal3'):
            self.shapes(name).insert(k.Text('marker',k.Trans()))
            self.assertEqual(self.pending(self.audit()),set(checks.GROUPS['inductor']['ids']))
            self.shapes(name).clear()

    def test_candidate_cell_and_unicode_label_guards(self):
        for group,tokens in checks.HINTS.items():
            expected={key for subject in checks.GROUPS.values() if subject['hints']==group for key in subject['ids']}
            for token in tokens:
                self.top.name='prefix_'+token.upper()
                self.assertEqual(self.pending(self.audit()),expected)
                self.top.name='control';self.shapes((90,99)).insert(k.Text(' '.join(token.upper()),k.Trans()))
                self.assertEqual(self.pending(self.audit()),expected);self.shapes((90,99)).clear()

    def test_reachable_children_and_reflected_arrays(self):
        child=self.layout.create_cell('xind4_custom');self.box('inductor',cell=child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.M90,3000,5000),k.Vector(2000,0),k.Vector(0,2000),2,3))
        report=self.audit();self.assertEqual(report['measurements']['raw']['inductor'],6)
        self.assertEqual(report['measurements']['hints']['inductor']['cells'],1)
        self.assertEqual(self.pending(report),set(checks.GROUPS['inductor']['ids']))

    def test_pad_name_boundaries_distinguish_address_labels(self):
        for name in ('paddr','paddr[0]','PADDR[3]','bus_paddr[2]','padding','ＰＡＤＤＲ[0]'):
            self.assertFalse(checks.hint_matches(name,checks.HINTS['bond_pad']))
            self.top.name=checks.normalized(name);self.shapes((70,5)).insert(k.Text(name,k.Trans()))
            with self.subTest(name=name):self.assertEqual(self.audit()['unreviewed'],0)
            self.shapes((70,5)).clear()
        # Names cannot override an actual drawing or mask operand.
        self.top.name='paddr';self.box('pad')
        self.assertEqual(self.pending(self.audit()),set(checks.GROUPS['bond_pad']['ids']))

    def test_numbered_separated_and_compound_pad_names_still_block_absence(self):
        for name in ('pad','pad0','pad_io','inputpad','paddr_pad','Ｐ Ａ Ｄ 0','padPL',
                     'padCenter','padframe','padcell','padring','pads','padopening','bondpad'):
            self.assertTrue(checks.hint_matches(name,checks.HINTS['bond_pad']))
            for kind in ('cell','label'):
                # GDS structure names are ASCII; labels retain Unicode input.
                self.top.name=checks.normalized(name) if kind=='cell' else 'control'
                if kind=='label':self.shapes((70,5)).insert(k.Text(name,k.Trans()))
                with self.subTest(name=name,kind=kind):
                    self.assertEqual(self.pending(self.audit()),set(checks.GROUPS['bond_pad']['ids']))
                self.shapes((70,5)).clear()

    def test_one_nm_overlap_blocks_varactor_target_absence(self):
        self.box((66,20),(0,0,1000,1000));self.box((65,44),(999,0,1999,1000))
        report=self.audit();self.assertEqual(report['measurements']['poly_tap']['intersection_area_nm2'],1000)
        self.assertEqual(self.pending(report),{'r1476'})

    def test_touching_edges_and_one_nm_gap_have_empty_intersection(self):
        self.box((66,20),(0,0,1000,1000))
        for x in (1000,1001):
            self.shapes((65,44)).clear();self.box((65,44),(x,0,x+1000,1000))
            self.assertEqual(self.audit()['unreviewed'],0)

    def test_stronger_varactor_proof_retains_present_poly_tap_without_nwell(self):
        self.box((66,20));self.box((65,44));self.assertEqual(self.pending(self.audit()),{'r1476'})

    def test_poly_holes_are_preserved(self):
        ring=k.Polygon(k.Box(0,0,3000,3000))
        ring.insert_hole([k.Point(500,500),k.Point(500,2500),k.Point(2500,2500),k.Point(2500,500)])
        self.shapes((66,20)).insert(ring);self.box((65,44),(600,600,2400,2400))
        self.assertEqual(self.audit()['unreviewed'],0)
        self.box((65,44),(499,1000,500,2000));self.assertEqual(self.pending(self.audit()),{'r1476'})

    def test_exact_path_geometry(self):
        self.shapes((66,20)).insert(k.Path([k.Point(0,0),k.Point(1000,0)],200))
        self.box((65,44),(0,-100,1000,100));r=self.audit()
        self.assertEqual(r['measurements']['poly_tap']['intersection_area_nm2'],200000)

    def test_unsupported_geometry_units_and_transforms_rejected(self):
        for shape in (k.Path([k.Point(0,0),k.Point(1000,0)],199),
                      k.Polygon([k.Point(0,0),k.Point(1000,0),k.Point(500,500)])):
            self.shapes((66,20)).clear();self.shapes((66,20)).insert(shape)
            with self.assertRaises(ValueError):self.audit()
        self.shapes((66,20)).clear();self.shapes((65,44)).insert(k.Text('tap',k.Trans()))
        with self.assertRaises(ValueError):self.audit()
        self.shapes((65,44)).clear();self.layout.dbu=.002
        with self.assertRaises(ValueError):checks.measure(self.layout)
        self.layout.dbu=.001;child=self.layout.create_cell('child');self.box('pad',cell=child)
        self.top.insert(k.CellInstArray(child.cell_index(),k.ICplxTrans(2,0,False,0,0)))
        with self.assertRaises(ValueError):self.audit()

    def test_stale_rehashed_absence_report_rejected(self):
        before=self.audit();self.box('inductor');after=self.audit()
        before['gds_sha256']=after['gds_sha256']
        with self.assertRaises(ValueError):checks.validate_saved(before,self.path)

    def test_missing_duplicate_or_changed_reports_rejected(self):
        report=self.audit()
        for change in (lambda r:r['rows'].pop(),lambda r:r['rows'].append(r['rows'][0]),
                       lambda r:r['measurements']['raw'].pop('pad'),
                       lambda r:r['measurements']['raw'].update(pad=True),
                       lambda r:r.update(qualified=True)):
            altered=copy.deepcopy(report);change(altered)
            with self.assertRaises(ValueError):checks.evaluate(altered,report['gds_sha256'],report['top'])

    def test_source_binding_requires_exact_table_and_catalog(self):
        from scripts import sky130_selected_target_review as review
        with TemporaryDirectory() as td:
            folder=Path(td)/'inputs';review.delivery.fixture.unpack(review.delivery.fixture.BUNDLE,folder)
            catalog=json.loads((review.ROOT/review.delivery.queue.CATALOG).read_bytes())
            proof=review.source_proof(folder/'sources',catalog)
            self.assertEqual(set(proof['bindings']),set(review.LITERAL))
            next(r for r in catalog['rows'] if r['id']=='r1476')['description']='different target'
            with self.assertRaises(ValueError):review.source_proof(folder/'sources',catalog)


if __name__=='__main__':unittest.main()
