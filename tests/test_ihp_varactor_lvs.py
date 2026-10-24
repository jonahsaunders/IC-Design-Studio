"""Four-terminal varactor preservation and strict physical fault accounting."""
from pathlib import Path
import tempfile
import unittest

import klayout.db as k
from icstudio import ihp_varactor_lvs as var
from icstudio import ihp_klayout_lvs as ihp
from icstudio.layout_verification import verification_stream
from scripts.qualify_ihp_varactor_layouts import stream, selected, detected


class VaractorLvsTests(unittest.TestCase):
    def test_four_nodes_geometry_and_multiplicity_survive_both_formats(self):
        for prefix in ('C','X'):
            original=f'{prefix}1 G1 W G2 S sg13_hv_svaricap w=3.74u l=.3u Nx=3 m=2'
            result,proof=var.geometry(original)
            self.assertIn(' G1 W G2 S sg13_hv_svaricap w=3.74u l=.3u nx=3 m=2',result)
            self.assertEqual(proof[0]['terminal_count'],4)
            self.assertEqual(var.geometry(result)[0],result)
        default='C1 A B C D sg13_hv_svaricap w=3.74u l=.3u'
        self.assertTrue(var.geometry(default)[0].endswith('nx=1 m=1\n'))
        ordinary='C1 A sg13_hv_svaricap 1p\n'
        self.assertEqual(var.geometry(ordinary),(ordinary,[]))

    def test_no_terminal_parameter_or_instance_collision_is_silently_discarded(self):
        base='C1 G1 W G2 S sg13_hv_svaricap w=3.74u l=.3u Nx=3 m=2'
        invalid=[base.replace('G1 W G2 S','G1 W'),base.replace('C1','R1'),
                 base+' w=8u',base+' Ny=2',base.replace('Nx=3','Nx=1.5'),base.replace('m=2','m=0'),
                 base.replace('w=3.74u','w={width}'),base.replace('w=3.74u','w=nan'),
                 base.replace(' l=.3u',''),base+'\nXICSTUDIO_VAR_C1 A B C D other']
        for text in invalid:
            with self.subTest(text=text),self.assertRaises(ValueError):var.geometry(text)

    def test_export_preserves_recognition_without_retaining_arbitrary_local_names(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);stream(folder/'input.gds','small',1)
            ly=k.Layout();ly.read(str(folder/'input.gds'));c=ly.top_cell()
            c.shapes(ly.layer(63,0)).insert(k.Text('private_local_net',k.Trans(0,0)))
            ly.write(str(folder/'input.gds'))
            proof=verification_stream(folder/'input.gds','varactor_coupon',['G1','W','G2','S'],folder/'out.gds',pin_layers={(8,2)},recognition_label=var.recognition_label)
            self.assertEqual(proof['retained_recognition_labels'],1)
            self.assertEqual(proof['removed_noninterface_labels'],1)
            self.assertEqual(len(var.recognition_inventory(folder/'out.gds','varactor_coupon')),1)
            self.assertFalse(var.recognition_label(63,1,'SVaricap'))
            self.assertFalse(var.recognition_label(63,0,'SVaricap_net'))

    def test_source_correction_is_exact_and_does_not_hide_missing_oxide(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            for size,w,l in [('small',3740,300),('large',9740,800)]:
                for nx in range(1,11):
                    stream(folder/'good.gds',size,nx);stream(folder/'bad.gds',size,nx,fault='missing-oxide')
                    good=k.Layout();good.read(str(folder/'good.gds'));bad=k.Layout();bad.read(str(folder/'bad.gds'))
                    for i in good.layer_indexes():
                        pair=good.get_info(i);j=bad.find_layer(pair)
                        a=k.Region(good.top_cell().shapes(i));b=k.Region(bad.top_cell().shapes(j)) if j is not None else k.Region()
                        if (pair.layer,pair.datatype)==(44,0):
                            self.assertTrue(b.is_empty());self.assertEqual(a.bbox(),k.Box(-100,-790,1150+nx*(500+2*l),w+1820))
                        else:self.assertTrue((a^b).is_empty())

    def test_gate_open_removes_all_contacts_to_one_actual_poly_component(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'open.gds';stream(path,'small',1,fault='gate-open')
            ly=k.Layout();ly.read(str(path));c=ly.top_cell()
            poly=min(k.Region(c.shapes(ly.layer(5,0))).merged().each(),key=lambda p:p.bbox().bottom)
            contacts=k.Region(c.shapes(ly.layer(6,0)))
            self.assertTrue((contacts&k.Region(poly)).is_empty())
            self.assertFalse(contacts.is_empty())

    def test_recognition_is_not_a_global_connection_in_private_deck(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);ihp.extraction_assets(folder)
            text=(folder/'rule_decks/cap_connections.lvs').read_text()
            self.assertNotIn('connect(varicap_ports, text_drw)',text)
            self.assertIn('connect(varicap_ports, cont_drw)',text)
            with self.assertRaises(ValueError):var.extractor_connections(folder)

    def test_process_errors_and_unrelated_drc_cannot_certify_fault_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            result=dict(status='failed',drc_count=1,stages=[dict(name=n,status='passed') for n in ('preflight','layout_export')]+[
                dict(name='lvs_extraction',status='failed',error='Tool crashed')])
            for fault in ('missing-oxide','missing-recognition','reference-width','gate-short'):
                self.assertFalse(detected(result,Path(temp),fault))


if __name__=='__main__':unittest.main()
