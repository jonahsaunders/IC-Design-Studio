"""Physical coil formats, recognition text and actual crossing-wire controls."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import klayout.db as k
from icstudio import ihp_inductor_lvs as ind
from icstudio import ihp_klayout_lvs as ihp
from icstudio.layout_verification import verification_stream, reference
from scripts.qualify_ihp_inductor_layouts import stream, selected, fault_detected, SOURCE_SHA

SOURCES = Path(__file__).resolve().parents[1]/'icstudio/assets/qualification/ihp-inductors'


class IhpInductorLvsTests(unittest.TestCase):
    def test_tool_errors_and_missing_findings_cannot_count_as_detected_faults(self):
        with tempfile.TemporaryDirectory() as tmp:
            for fault in ('winding-open','lead-open','turn-short','reference-turns'):
                result=dict(status='failed',drc_count=0,stages=[dict(name=n,status='passed') for n in ('preflight','layout_export','drc','integrity')]+[
                    dict(name='lvs_extraction',status='failed',error='Tool crashed'),dict(name='lvs',status='failed',error='Tool crashed')])
                self.assertFalse(fault_detected(result,Path(tmp),fault,['A','B','S']))
            result['stages'][-2]['error']='IHP inductor recognition/wiring audit failed; see inductor-wiring.json.'
            self.assertFalse(fault_detected(result,Path(tmp),'turn-short',['A','B','S']))
            result['stages'][-2]['status']='passed'
            result['stages'][-1]['error']='Netgen did not establish a unique match with equivalent connected pins and no property errors. See lvs/lvs.log.'
            log=Path(tmp)/'lvs/lvs.log';log.parent.mkdir()
            for text,expected in [('tool stopped',False),('Netlists match uniquely.',False),('Final result: Top level cell failed pin matching.',True)]:
                log.write_text(text)
                self.assertEqual(fault_detected(result,Path(tmp),'reference-terminal',['A','B','S']),expected)

    def test_physical_cdl_preserves_all_terminals_parameters_and_multiplicity(self):
        for model in SOURCE_SHA:
            text=selected(model)['text']; converted,changes=ind.geometry(text)
            self.assertIn('XICSTUDIO_IND_L1 ',converted)
            self.assertEqual(changes[0]['terminal_count'],ind.MODELS[model])
            self.assertEqual(reference(converted,'coil_coupon')['ports'],selected(model)['ports'])
            self.assertEqual(ind.geometry(converted)[0],converted)
            self.assertIn('m=2',ind.geometry(text.replace('m=1','m=2'))[0])
        simple='L1 A B S inductor w=2u s=2.1u d=25.35u nr_r=1'
        self.assertTrue(ind.geometry(simple)[0].endswith('m=1\n'))
        for bad in (simple.replace('A B S','A B'),simple.replace('w=2u','w=0'),
                    simple.replace('nr_r=1','nr_r=1.5'),simple+' w=4u',simple+' extra=2',
                    simple.replace('w=2u','w={width}'),simple.replace('w=2u','w=nan'),
                    simple.replace('nr_r=1',''),simple+' m=2.5'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):ind.geometry(bad)
        with self.assertRaises(ValueError):ind.geometry(simple+'\nXICSTUDIO_IND_L1 A B S other\n')
        ordinary='L1 A B 1n\n';self.assertEqual(ind.geometry(ordinary),(ordinary,[]))
        ordinary='L1 inductor B 1n\n';self.assertEqual(ind.geometry(ordinary),(ordinary,[]))
        self.assertIn(' inductor B S inductor ',ind.geometry(simple.replace('A B S','inductor B S'))[0])

    def test_real_mask_connectivity_and_every_recognition_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'coil.gds'
            for model in SOURCE_SHA:
                for angle in (0,90,180,270):
                    for fault in (None,'winding-open','missing-recognition','missing-role','duplicate-role',
                                  *(['missing-cross-vias','turn-short'] if model=='inductor3' else [])):
                        with self.subTest(model=model,angle=angle,fault=fault):
                            stream(SOURCES/(model+'.gds'),path,model,angle,fault)
                            proof=ind.winding_proof(path,'coil_coupon')
                            self.assertEqual(proof['passed'],fault is None,proof)
                            if fault is None:
                                self.assertEqual(proof['coils'][0]['model'],model)
                                self.assertEqual(proof['coils'][0]['metal_components'],1)
                                self.assertEqual(proof['coils'][0]['winding_cycles'],0)
                            elif fault=='turn-short':
                                self.assertEqual(proof['coils'][0]['winding_cycles'],1)

    def test_failed_wire_proof_prevents_abstract_native_union(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'coil.gds'
            stream(SOURCES/'inductor3.gds',source,'inductor3',fault='missing-cross-vias')
            with patch('icstudio.engines.execute') as engine:
                with self.assertRaisesRegex(ValueError,'wiring audit failed'):
                    ihp.extract('klayout',source,'coil_coupon',['A','C','B','S'],{},root/'out')
                engine.assert_not_called()

    def test_redundant_via_cuts_at_one_junction_do_not_create_a_winding_loop(self):
        # This checks topology only: divide each existing cut into two cuts
        # within the same contacted metal overlap. DRC checks cut dimensions.
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'coil.gds'
            stream(SOURCES/'inductor3.gds',source,'inductor3')
            before=ind.winding_proof(source,'coil_coupon')['coils'][0]
            ly=k.Layout();ly.read(str(source));shapes=ly.top_cell().shapes(ly.find_layer(133,0))
            cuts=[s.bbox() for s in shapes.each()];shapes.clear()
            for b in cuts:
                x=(b.left+b.right)//2
                shapes.insert(k.Box(b.left,b.bottom,x-1,b.top))
                shapes.insert(k.Box(x+1,b.bottom,b.right,b.top))
            ly.write(str(source));proof=ind.winding_proof(source,'coil_coupon')
            self.assertTrue(proof['passed'],proof)
            after=proof['coils'][0]
            self.assertEqual(after['crossing_vias'],2*before['crossing_vias'])
            self.assertEqual(after['contacted_overlap_islands'],before['contacted_overlap_islands'])
            self.assertEqual(after['winding_cycles'],0)

    def test_removed_device_marker_cannot_hide_a_coil(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'coil.gds';stream(SOURCES/'inductor.gds',source,'inductor')
            ly=k.Layout();ly.read(str(source));ly.top_cell().shapes(ly.find_layer(27,0)).clear();ly.write(str(source))
            result=ind.winding_proof(source,'coil_coupon')
            self.assertFalse(result['passed'])
            self.assertIn('orphan-inductor-recognition',{r['kind'] for r in result['failures']})

    def test_recognition_labels_survive_without_becoming_electrical_ports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'coil.gds';target=root/'engine.gds'
            stream(SOURCES/'inductor3.gds',source,'inductor3')
            r=verification_stream(source,'coil_coupon',['A','C','B','S'],target,
                                  pin_layers={(126,2),(134,2),(8,2)},recognition_label=ind.recognition_label)
            self.assertEqual(r['retained_recognition_labels'],4)
            self.assertTrue(ind.winding_proof(target,'coil_coupon')['passed'])
            ly=k.Layout();ly.read(str(source));c=ly.top_cell()
            for layer in (126,134,8):
                i=ly.find_layer(layer,2)
                if i is not None:c.shapes(i).clear()
            ly.write(str(source))
            with self.assertRaisesRegex(ValueError,'Missing top-level'):
                verification_stream(source,'coil_coupon',['LA','LC','LB'],target,pin_layers=set(),recognition_label=ind.recognition_label)
        self.assertFalse(ind.recognition_label(8,25,'LA'))
        self.assertFalse(ind.recognition_label(63,0,'sub!'))

    def test_private_corrections_keep_the_pinned_public_bundle_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);entry,record=ihp.extraction_assets(root)
            self.assertTrue(entry.is_file());self.assertEqual(len(record['additional_corrections']),4)
            ihp.assets()  # Original source hashes still hold.
            with self.assertRaisesRegex(ValueError,'Unexpected public'):
                ind.extractor_roles(root)  # Refuse already-modified or unrelated sources.


if __name__=='__main__':unittest.main()
