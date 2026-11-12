"""Device identity is required in addition to absent enclosing layers."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import klayout.db as k
from scripts import sky130_device_intent_review as review


class DeviceIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.folder=Path(cls.temp.name)/'inputs'
        f=review.previous.previous.marker.nsm.fixture;cls.manifest=f.unpack(f.BUNDLE,cls.folder)

    def layout(self):
        ly=k.Layout();ly.dbu=.001;cell=ly.create_cell('TOP')
        def add(pair,box):cell.shapes(ly.layer(*pair)).insert(k.Box(*box))
        add((65,20),(0,0,1000,1000));add((65,20),(3000,0,4000,1000))
        add((66,20),(400,-300,600,1300));add((66,20),(3400,-300,3600,1300))
        add((64,20),(2700,-300,4300,1300));add((78,44),(3200,-200,3800,1200))
        return ly

    def models(self):return {review.NFET:1,review.PFET:1}

    def test_table_identity_and_created_masks_are_explicit(self):
        proof=review.source_proof(self.folder/'sources')
        self.assertEqual(proof['device_rows']['pmos']['hvtr.dg'],'-')
        self.assertEqual(proof['device_rows']['pmos']['lvtn:dg'],'C')
        self.assertEqual(proof['mask_rows']['pmos']['NCM'],'C')
        self.assertEqual(proof['mask_rows']['pmos']['LVTNM'],'C')

    def test_known_device_types_and_complete_geometry_allow_only_two_decisions(self):
        result=review.decisions(review.measure(self.layout()),self.models())
        self.assertEqual(result['hvtr_3']['disposition'],'absent-operand')
        self.assertEqual(result['licon_19']['disposition'],'absent-operand')
        self.assertEqual(result['retained_generated_mask_obligations'],['lvtn.4b','ncm.3'])

    def test_native_model_substitution_does_not_inherit_hd_coverage(self):
        measured=review.measure(self.layout())
        for model in ('sky130_fd_pr__pfet_01v8_lvt','pmedlvtrf','xchvnwc','sky130_fd_pr__nfet_g5v0d10v5'):
            models=self.models();models[model]=models.pop(review.PFET)
            with self.assertRaises(ValueError):review.decisions(measured,models)

    def test_missing_or_extra_native_mos_is_rejected(self):
        measured=review.measure(self.layout())
        for model in (review.NFET,review.PFET):
            for value in (0,2):
                models=self.models();models[model]=value
                with self.assertRaises(ValueError):review.decisions(measured,models)

    def test_missing_hvtp_cannot_establish_the_high_vt_device(self):
        ly=self.layout();ly.top_cell().shapes(ly.layer(78,44)).clear()
        with self.assertRaises(ValueError):review.decisions(review.measure(ly),self.models())

    def test_hvtp_over_nmos_is_rejected(self):
        ly=self.layout();ly.top_cell().shapes(ly.layer(78,44)).insert(k.Box(200,-200,800,1200))
        with self.assertRaises(ValueError):review.decisions(review.measure(ly),self.models())

    def test_partial_well_gate_cannot_be_split_into_apparently_valid_devices(self):
        ly=self.layout();ly.top_cell().shapes(ly.layer(64,20)).insert(k.Box(300,500,700,1500))
        measured=review.measure(ly)
        self.assertEqual(measured['straddling_gates'],1)
        with self.assertRaises(ValueError):review.decisions(measured,self.models())

    def test_each_varactor_indicator_prevents_its_absence_decision(self):
        for pair in ((75,20),(125,44),(65,44)):
            ly=self.layout();ly.top_cell().shapes(ly.layer(*pair)).insert(k.Box(400,-100,600,0))
            result=review.decisions(review.measure(ly),self.models())
            self.assertEqual(result['licon_19']['disposition'],'execution-review-required')

    def test_raw_marker_text_in_hierarchy_is_not_discarded(self):
        for pair,key in (((18,20),'hvtr_3'),((75,20),'licon_19'),((125,44),'licon_19')):
            ly=self.layout();child=ly.create_cell('MARKER');child.shapes(ly.layer(*pair)).insert(k.Text('present',k.Trans(0,0)))
            ly.cell('TOP').insert(k.CellInstArray(child.cell_index(),k.Trans(k.Trans.R90,100,200)))
            result=review.decisions(review.measure(ly),self.models())
            self.assertEqual(result[key]['disposition'],'execution-review-required')

    def test_empty_geometry_invalid_counts_and_unknown_models_fail_closed(self):
        measured=review.measure(self.layout())
        for value in (None,False,0.0,-1):
            changed=deepcopy(measured);changed['nfet_gates']=value
            with self.assertRaises(ValueError):review.decisions(changed,self.models())
        for models in ({},{review.NFET:1,review.PFET:1,'unknown':1}):
            with self.assertRaises(ValueError):review.decisions(measured,models)

    def test_unknown_shape_transform_and_purpose_are_rejected(self):
        ly=self.layout();child=ly.create_cell('CHILD');child.shapes(ly.layer(65,20)).insert(k.Box(0,0,100,100))
        ly.cell('TOP').insert(k.CellInstArray(child.cell_index(),k.ICplxTrans(1.5,0,False,0,0)))
        with self.assertRaises(ValueError):review.measure(ly)
        ly=self.layout();ly.top_cell().shapes(ly.layer(199,199)).insert(k.Box(0,0,10,10))
        with self.assertRaises(ValueError):review.measure(ly)

    def test_changed_tables_and_source_legends_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            for name in review.HASHES:(folder/name).write_bytes((review.TABLES/name).read_bytes())
            (folder/'table-f2a-lvs.tsv').write_bytes((folder/'table-f2a-lvs.tsv').read_bytes()+b'\n')
            with patch.object(review,'TABLES',folder),self.assertRaises(ValueError):review.source_proof(self.folder/'sources')

    def test_native_capture_hash_mismatch_is_rejected_before_interpretation(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);gds=folder/'layout.gds';native=folder/'layout.ext'
            self.layout().write(str(gds));native.write_text('untrusted native output')
            with self.assertRaisesRegex(ValueError,'accepted capture'):review.audit(gds,native,'0'*64)

    def test_final_gds_census_is_exhaustive(self):
        expected={'counter':(1120,1120),'uart':(8500,8502),'apb':(8571,8572)}
        for entry in self.manifest['cases']:
            layout=k.Layout();layout.read(str(self.folder/entry['gds']));measured=review.measure(layout)
            n,p=expected[entry['case']]
            self.assertEqual((measured['nfet_gates'],measured['pfet_gates']),(n,p))
            self.assertEqual(measured['gates'],n+p)
            self.assertEqual(review.decisions(measured,{review.NFET:n,review.PFET:p})['hvtr_3']['disposition'],'absent-operand')


if __name__=='__main__':unittest.main()
