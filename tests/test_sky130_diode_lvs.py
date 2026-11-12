from pathlib import Path
import tempfile
import unittest
import klayout.db as k
from scripts.sky130_diode_lvs import CELL,MODEL,enrich_reference,reference_dimensions,verify_library


FIXTURE=Path(__file__).parent/'fixtures/sky130-diode-reference'
SPICE=(FIXTURE/(CELL+'.spice')).read_bytes()
GDS=FIXTURE/(CELL+'.gds')
EMPTY='.SUBCKT '+CELL+' DIODE VGND VNB VPB VPWR\n.ENDS '+CELL


class DiodeReferenceTests(unittest.TestCase):
    def test_independent_views_agree(self):
        result=verify_library(SPICE,GDS,GDS)
        self.assertEqual(result['area_um2'],'0.4347')
        self.assertEqual(result['perimeter_um'],'2.64')
        self.assertTrue(result['polygon_layers_equal'])

    def test_missing_changed_and_repeated_master_are_rejected(self):
        for text in ('',EMPTY+'\n'+EMPTY,EMPTY.replace('DIODE VGND','VGND DIODE'),EMPTY.replace('\n.ENDS','\nR1 DIODE VGND 1\n.ENDS')):
            with self.subTest(text=text),self.assertRaises(ValueError):enrich_reference(text,SPICE)

    def test_source_cannot_be_modified(self):
        with self.assertRaisesRegex(ValueError,'Unreviewed'):
            reference_dimensions(SPICE.replace(b'perim=2.64',b'perim=2.65'))

    def test_other_reference_content_remains_identical(self):
        before='* independent circuit\n.SUBCKT TOP A B\nM0 A B A A nfet W=1 L=0.15\n.ENDS\n'
        updated=enrich_reference(before+EMPTY,SPICE)
        self.assertTrue(updated.startswith(before))
        self.assertIn('D0 VNB DIODE '+MODEL+' A=0.4347 P=2.64',updated)

    def test_native_reader_preserves_area_perimeter_and_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'reference.cir';path.write_text('* reader scale control\n.options scale=1e-6\n'+enrich_reference(EMPTY,SPICE))
            net=k.Netlist();net.read(str(path),k.NetlistSpiceReader());cell=net.circuit_by_name(CELL.upper())
            devices=list(cell.each_device());self.assertEqual(len(devices),1);device=devices[0]
            self.assertEqual(device.net_for_terminal('A').name,'VNB')
            self.assertEqual(device.net_for_terminal('C').name,'DIODE')
            self.assertAlmostEqual(device.parameter('A'),.4347,places=12)
            self.assertAlmostEqual(device.parameter('P'),2.64,places=12)

    def test_changed_installed_masks_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout=k.Layout();layout.read(str(GDS));cell=layout.top_cell()
            cell.shapes(layout.layer(65,20)).clear();path=Path(tmp)/'broken.gds';layout.write(str(path))
            with self.assertRaisesRegex(ValueError,'masks differ'):verify_library(SPICE,GDS,path)


if __name__=='__main__':unittest.main()
