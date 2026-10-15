from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as k
from scripts import sky130_standard_cell_wl_review as r


class StandardCellWlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.folder=Path(cls.temp.name)/'bundle';r.fixture.unpack(r.fixture.BUNDLE,cls.folder)
        cls.reader=r.queue.RetainedReader();cls.catalog,baselines=r.queue.reconstruct(cls.reader)
        prior=cls.reader.read(r.PREVIOUS,r.PREVIOUS_SHA)
        cls.rows=r.queue.apply_decisions(baselines[0]['rows'],prior['cases'][0]['new_error_decisions'],cls.catalog)
        cls.inventory=cls.reader.read(r.INVENTORY)
        cls.proof=r.source_proof(cls.folder/'sources',cls.catalog,cls.inventory)

    def layouts(self):
        library=k.Layout();library.dbu=.001;cell=library.create_cell('trusted')
        for pair,box in [((65,20),(0,0,600,400)),((66,20),(200,-200,350,600)),
                         ((65,20),(0,1000,600,1400)),((66,20),(200,800,350,1600)),
                         ((64,20),(-200,800,800,1600)),((81,4),(-300,-300,900,1700))]:
            cell.shapes(library.layer(*pair)).insert(k.Box(*box))
        layout=k.Layout();layout.dbu=.001;master=layout.create_cell('trusted')
        for i in library.layer_indexes():
            info=library.get_info(i)
            for shape in cell.shapes(i).each():master.shapes(layout.layer(info.layer,info.datatype)).insert(shape)
        top=layout.create_cell('control');top.insert(k.CellInstArray(master.cell_index(),k.Trans()))
        return layout,library,top,master

    def native(self,measurement):
        return dict(native_models={'sky130_fd_pr__nfet_01v8':measurement['nfet_gates'],
                                  'sky130_fd_pr__pfet_01v8_hvt':measurement['pfet_gates']},
                    measurement={**{name:measurement[name] for name in ('gates','nfet_gates','pfet_gates')},
                                 'straddling_gates':0})

    def test_exact_source_bindings_exclude_recognition_and_rf_dimensions(self):
        self.assertEqual(len(r.WL_IDS),90);self.assertEqual(len(self.proof['bindings']),95)
        self.assertFalse(set(self.proof['bindings'])&{'r537','r543','r544','r545','r705'})
        rf={row['id'] for row in self.catalog['rows'] if row['rule']=='diff.13'}
        self.assertEqual(len(rf),60);self.assertFalse(rf&set(self.proof['bindings']))

    def test_valid_library_cells_receive_explicit_exemption_not_execution(self):
        layout,library,_,_=self.layouts();m=r.measure(layout,library)
        self.assertEqual((m['gates'],m['nfet_gates'],m['pfet_gates']),(2,1,1))
        changes=r.decisions(m,self.native(m),self.proof['bindings'])
        rows=r.apply_decisions(self.rows,changes,self.catalog)
        self.assertEqual(dict(Counter(row['disposition'] for row in rows)),
                         {'executed-reviewed':356,'absent-operand':354,'unreviewed':756,r.EXEMPT:90})

    def test_nested_rotated_mirrored_arrays_preserve_gate_union_and_multiplicity(self):
        layout,library,top,master=self.layouts();top.clear_insts()
        middle=layout.create_cell('middle')
        middle.insert(k.CellInstArray(master.cell_index(),k.Trans(1,True,10000,10000),
                                      k.Vector(4000,0),k.Vector(0,4000),2,3))
        top.insert(k.CellInstArray(middle.cell_index(),k.Trans(3,False,20000,20000)))
        m=r.measure(layout,library)
        self.assertEqual(m['gates'],12);self.assertEqual(m['masters'][0]['instances'],6)
        self.assertEqual(m['weighted_library_gates'],12)

    def test_missing_or_partial_standard_cell_markers_fail_even_in_library(self):
        for partial in (False,True):
            layout,library,_,master=self.layouts()
            for design,cell in ((layout,master),(library,library.cell('trusted'))):
                shapes=cell.shapes(design.layer(81,4));shapes.clear()
                if partial:shapes.insert(k.Box(-300,-300,900,500))
            with self.assertRaisesRegex(ValueError,'own trusted'):r.measure(layout,library)

    def test_same_name_with_changed_geometry_or_device_marker_is_untrusted(self):
        for pair in ((66,20),(75,20),(64,20),(81,4),(68,20)):
            layout,library,_,master=self.layouts()
            master.shapes(layout.layer(*pair)).insert(k.Box(3000,3000,3400,3400))
            with self.assertRaisesRegex(ValueError,'Untrusted'):r.measure(layout,library)

    def test_unknown_master_and_top_level_marker_do_not_establish_trust(self):
        layout,library,top,master=self.layouts();master.name='spoofed'
        with self.assertRaisesRegex(ValueError,'Untrusted'):r.measure(layout,library)
        layout,library,top,_=self.layouts();top.shapes(layout.layer(81,4)).insert(k.Box(-1000,-1000,2000,3000))
        with self.assertRaisesRegex(ValueError,'Untrusted'):r.measure(layout,library)

    def test_overlapping_instances_cannot_hide_count_mismatch(self):
        layout,library,top,master=self.layouts();top.insert(k.CellInstArray(master.cell_index(),k.Trans()))
        with self.assertRaisesRegex(ValueError,'Gate union or count'):r.measure(layout,library)

    def test_gate_created_between_distinct_masters_fails_union_check(self):
        layout=k.Layout();library=k.Layout();layout.dbu=library.dbu=.001
        top=layout.create_cell('control')
        for name,pair,box in [('diff_only',(65,20),(0,0,600,400)),('poly_only',(66,20),(200,-200,350,600))]:
            for design in (layout,library):
                cell=design.create_cell(name);cell.shapes(design.layer(*pair)).insert(k.Box(*box))
                cell.shapes(design.layer(81,4)).insert(k.Box(-300,-300,900,1700))
            top.insert(k.CellInstArray(layout.cell(name).cell_index(),k.Trans()))
        with self.assertRaisesRegex(ValueError,'Gate union or count'):r.measure(layout,library)

    def test_normalized_dummy_label_on_any_purpose_reopens_only_dummy_rules(self):
        for pair in ((83,44),(68,20)):
            layout,library,top,_=self.layouts();labels=layout.create_cell('labels')
            labels.shapes(layout.layer(*pair)).insert(k.Text('  DuMmY_PoLy  ',k.Trans()))
            top.insert(k.CellInstArray(labels.cell_index(),k.Trans(2,False,10000,10000),
                                      k.Vector(4000,0),k.Vector(0,4000),2,2))
            m=r.measure(layout,library);self.assertEqual(m['dummy_poly_labels'],4)
            changes=r.decisions(m,self.native(m),self.proof['bindings'])
            self.assertEqual(Counter(c['disposition'] for c in changes),{r.EXEMPT:90,'unreviewed':5})
            with self.assertRaisesRegex(ValueError,'unsupported'):r.apply_decisions(self.rows,changes,self.catalog)

    def test_census_count_model_and_measurement_mismatches_fail(self):
        layout,library,_,_=self.layouts();m=r.measure(layout,library)
        for change in ('count','model','geometry','straddling'):
            native=self.native(m)
            if change=='count':native['native_models']['sky130_fd_pr__nfet_01v8']+=1
            elif change=='model':native['native_models']['unknown_rf_fet']=1
            elif change=='geometry':native['measurement']['gates']+=1
            else:native['measurement']['straddling_gates']=1
            with self.assertRaisesRegex(ValueError,'native census'):r.decisions(m,native,self.proof['bindings'])

    def test_unsupported_path_transform_purpose_and_units_fail(self):
        layout,library,top,_=self.layouts()
        top.shapes(layout.layer(68,20)).insert(k.Path([k.Point(0,0),k.Point(100,100)],3))
        with self.assertRaisesRegex(ValueError,'Unsupported geometry'):r.measure(layout,library)
        layout,library,top,master=self.layouts();top.clear_insts()
        top.insert(k.CellInstArray(master.cell_index(),k.ICplxTrans(1,45,False,0,0)))
        with self.assertRaisesRegex(ValueError,'Unsupported geometry'):r.measure(layout,library)
        layout,library,top,_=self.layouts();top.shapes(layout.layer(999,0)).insert(k.Box(0,0,10,10))
        with self.assertRaisesRegex(ValueError,'Unsupported geometry'):r.measure(layout,library)
        layout,library,_,_=self.layouts();library.dbu=.002
        with self.assertRaisesRegex(ValueError,'database unit'):r.measure(layout,library)

    def test_source_edit_is_rejected(self):
        path=self.folder/'sources'/r.PARENT;raw=path.read_bytes()
        try:
            path.write_bytes(raw+b'\n')
            with self.assertRaisesRegex(ValueError,'Changed standard-cell source'):
                r.source_proof(self.folder/'sources',self.catalog,self.inventory)
        finally:path.write_bytes(raw)

    def test_captured_job_and_library_bytes_are_both_authenticated(self):
        folder=Path(self.temp.name)/'captured';folder.mkdir()
        raw=json.dumps({'project':{'digital':{'platform':{'name':'sky130hd','files':[
            dict(path=r.LIBRARY,sha256=r.LIBRARY_SHA,bytes=r.LIBRARY_BYTES)]}}}}).encode()
        (folder/'input.json').write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'job input'):r.load_library(folder,'counter')
        path=folder/'platform'/r.LIBRARY;path.parent.mkdir(parents=True);path.write_bytes(b'changed library')
        with patch.dict(r.INPUTS,{'counter':r.queue.sha(raw)}):
            with self.assertRaisesRegex(ValueError,'standard-cell library'):r.load_library(folder,'counter')

    def test_missing_duplicate_unrelated_or_repeated_decisions_fail(self):
        layout,library,_,_=self.layouts();m=r.measure(layout,library)
        changes=r.decisions(m,self.native(m),self.proof['bindings'])
        for edited in (changes[:-1],changes[:-1]+[changes[0]],changes+[dict(id='r543',disposition=r.EXEMPT)]):
            with self.assertRaises(ValueError):r.apply_decisions(self.rows,edited,self.catalog)
        rows=r.apply_decisions(self.rows,changes,self.catalog)
        with self.assertRaisesRegex(ValueError,'Overlapping'):r.apply_decisions(rows,changes,self.catalog)


if __name__=='__main__':unittest.main()
