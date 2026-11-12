from collections import Counter
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as k
from scripts import sky130_grid_catalog_review as r


class GridCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.folder=Path(cls.temp.name)/'bundle';r.fixture.unpack(r.fixture.BUNDLE,cls.folder)
        cls.reader=r.queue.RetainedReader();cls.catalog,cls.baselines,cls.previous=r.reconstruct(cls.reader)
        cls.inventory=cls.reader.read(r.wl.INVENTORY)
        cls.geometry=cls.reader.read(r.GEOMETRY,r.GEOMETRY_SHA)
        cls.proof=r.source_proof(cls.folder/'sources',cls.catalog,cls.inventory,cls.geometry)
        cls.bindings=cls.proof['bindings']

    def layout(self):
        layout=k.Layout();layout.dbu=.001;top=layout.create_cell('control')
        top.shapes(layout.layer(81,4)).insert(k.Box(0,0,100,100))
        return layout,top

    def choose(self,layout):
        return {row['id']:row for row in r.decisions(r.measure(layout),self.bindings)}

    def test_exact_set_leaves_metop_aliases_and_parent_units_unresolved(self):
        self.assertEqual(len(self.bindings),105)
        self.assertFalse(set(self.bindings)&set(r.UNRESOLVED));self.assertEqual(len(r.UNRESOLVED),16)
        self.assertEqual(len([b for b in self.bindings.values() if b['scope']=='drawn-vertices']),35)
        self.assertEqual(self.proof['drawn_grid_source']['grid_nm'],5)
        self.assertEqual([row['unit'] for row in self.proof['periphery_discrepancy']],['mm','mm'])
        self.assertEqual(self.bindings['r108']['alias']['source'],'installed')
        self.assertEqual(self.bindings['r0']['alias']['source'],'published')

    def test_each_drawn_operand_passes_five_nm_and_fails_one_nm_shift(self):
        for key,binding in self.bindings.items():
            if binding['scope']!='drawn-vertices':continue
            with self.subTest(key=key):
                layout,top=self.layout();shapes=top.shapes(layout.layer(*binding['pair']))
                shapes.insert(k.Box(0,0,100,100))
                self.assertEqual(self.choose(layout)[key]['disposition'],'executed-reviewed')
                shapes.insert(k.Box(1,0,101,100))
                decision=self.choose(layout)[key]
                self.assertEqual(decision['disposition'],'unreviewed');self.assertEqual(decision['status'],'FAIL')
                self.assertGreater(decision['witness']['off_grid_vertices'],0)

    def test_each_non_drawn_subject_requires_complete_absence(self):
        for key,binding in self.bindings.items():
            if binding['scope']!='absence-only':continue
            with self.subTest(key=key):
                layout,top=self.layout()
                self.assertEqual(self.choose(layout)[key]['disposition'],'absent-operand')
                top.shapes(layout.layer(*binding['pair'])).insert(k.Box(0,0,100,100))
                decision=self.choose(layout)[key]
                self.assertEqual(decision['disposition'],'unreviewed');self.assertEqual(decision['status'],'NEEDS_REVIEW')

    def test_text_only_data_is_not_accepted_as_empty_geometry(self):
        for key in ('r15','r43','r59','r102','r108'):
            layout,top=self.layout();top.shapes(layout.layer(*self.bindings[key]['pair'])).insert(k.Text('label',k.Trans(1,1)))
            self.assertEqual(self.choose(layout)[key]['disposition'],'unreviewed')

    def test_text_anchor_failure_stays_separate_from_literal_vertex_check(self):
        layout,top=self.layout();shapes=top.shapes(layout.layer(68,20))
        shapes.insert(k.Box(0,0,100,100));shapes.insert(k.Text('port',k.Trans(1,1)))
        measured=r.measure(layout);self.assertEqual(measured['status'],'FAIL')
        decision=next(row for row in r.decisions(measured,self.bindings) if row['id']=='r15')
        self.assertEqual(decision['disposition'],'executed-reviewed')
        self.assertEqual(decision['witness']['off_grid_texts'],1)

    def test_nested_array_offset_cannot_hide_off_grid_vertices(self):
        layout,top=self.layout();child=layout.create_cell('child')
        child.shapes(layout.layer(65,20)).insert(k.Box(0,0,100,100))
        middle=layout.create_cell('middle');middle.insert(k.CellInstArray(child.cell_index(),k.Trans(1,True,200,300)))
        top.insert(k.CellInstArray(middle.cell_index(),k.Trans(),k.Vector(1001,0),k.Vector(0,1000),2,2))
        self.assertEqual(self.choose(layout)['r1']['witness']['off_grid_vertices'],8)

    def test_unsupported_transform_or_path_cannot_be_reconciled(self):
        layout,top=self.layout();child=layout.create_cell('child')
        child.shapes(layout.layer(65,20)).insert(k.Box(1,1,101,101))
        top.insert(k.CellInstArray(child.cell_index(),k.ICplxTrans(.5,0,False,0,0)))
        with self.assertRaisesRegex(ValueError,'Unsupported geometry'):self.choose(layout)
        layout,top=self.layout();top.shapes(layout.layer(65,20)).insert(k.Path([k.Point(0,0),k.Point(100,0)],11))
        with self.assertRaisesRegex(ValueError,'Unsupported geometry'):self.choose(layout)

    def test_missing_layer_or_check_and_duplicate_counts_fail(self):
        layout,top=self.layout();top.shapes(layout.layer(68,20)).insert(k.Box(0,0,100,100))
        measured=r.measure(layout)
        for change in ('layer','check','duplicate','grid'):
            edited=deepcopy(measured)
            if change=='layer':edited['layers'].pop()
            elif change=='check':edited['checks'].pop()
            elif change=='duplicate':edited['layers'].append(edited['layers'][0])
            else:next(row for row in edited['layers'] if row['pair']==[68,20])['grid_nm']=1
            with self.assertRaises(ValueError):r.decisions(edited,self.bindings)

    def test_changed_source_or_operand_mapping_fails(self):
        path=self.folder/'sources'/r.ASSUMPTIONS;raw=path.read_bytes()
        try:
            path.write_bytes(raw.replace(b'0.005',b'0.001'))
            with self.assertRaisesRegex(ValueError,'Changed grid source'):
                r.source_proof(self.folder/'sources',self.catalog,self.inventory,self.geometry)
        finally:path.write_bytes(raw)
        changed=deepcopy(self.geometry)
        for row in changed['new_error_bindings'].values():
            if row.get('operand')=='P1Mmk':row['pair']=[28,1]
        with self.assertRaises((ValueError,KeyError)):
            r.source_proof(self.folder/'sources',self.catalog,self.inventory,changed)

    def test_latest_checkpoint_preserves_explicit_wl_exemptions(self):
        self.assertTrue(all(case['counts']=={'unreviewed':756,'executed-reviewed':356,'absent-operand':354,r.wl.EXEMPT:90}
                            for case in self.baselines))
        layout,_=self.layout();changes=r.decisions(r.measure(layout),self.bindings)
        rows=r.queue.apply_decisions(self.baselines[0]['rows'],changes,self.catalog)
        counts=Counter(row['disposition'] for row in rows)
        self.assertEqual(counts[r.wl.EXEMPT],90);self.assertEqual(counts['unreviewed'],651)
        indexed={row['id']:row for row in rows}
        self.assertTrue(all(indexed[key]['disposition']=='unreviewed' for key in r.UNRESOLVED))


if __name__=='__main__':unittest.main()
