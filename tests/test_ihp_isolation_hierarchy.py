"""Repeated physical cells must not merge their device-local body connections."""
from pathlib import Path
import tempfile
import unittest
import klayout.db as k
from icstudio.ihp_isolation_lvs import recognition_inventory,recognition_label
from icstudio.ihp_tap_lvs import recognition_label as tap_label
from icstudio.layout_verification import verification_stream
from scripts.qualify_ihp_isolation_hierarchy import PORTS,FAULTS,audit,selected,stream


class IsolationHierarchyTests(unittest.TestCase):
    def test_repeated_cell_keeps_both_recognition_sets_and_only_top_conductor_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for rotation in (0,90,180,270):
                path=root/f'r{rotation}.gds';stream(path,rotation)
                ly=k.Layout();ly.read(str(path));top=ly.top_cell();instances=list(top.each_inst())
                self.assertEqual(top.name,'pair');self.assertEqual(len(instances),2)
                self.assertEqual(instances[0].cell_index,instances[1].cell_index)
                target=root/f'flat{rotation}.gds'
                proof=verification_stream(path,'pair',PORTS,target,pin_layers={(8,2)},
                    recognition_label=lambda a,b,t:recognition_label(a,b,t) or tap_label(a,b,t))
                self.assertGreaterEqual(proof['removed_noninterface_labels'],5)
                self.assertEqual(len(recognition_inventory(target,'pair')),2)
                flat=k.Layout();flat.read(str(target));cell=flat.top_cell()
                self.assertEqual({s.text.string for s in cell.shapes(flat.layer(8,2)).each() if s.is_text()},set(PORTS))
                self.assertEqual(sum(s.is_text() and s.text.string=='sub!' for s in cell.shapes(flat.layer(63,0)).each()),2)

    def test_audit_requires_two_complete_distinct_body_graphs(self):
        text='.SUBCKT pair '+' '.join(PORTS)+'\n'
        for i in (1,2):
            text+=f'M{i} D{i} G{i} S{i} body{i} sg13_lv_nmos L=.13u W=.15u AS=.1005p AD=.1005p PS=1.34u PD=1.34u rfmode=0\n'
            text+=f'D{i} body{i} NW{i} B isolbox a=36p p=24u\nR{i} S{i} body{i} ptap1 A=.6084p P=3.12u\n'
        text+='.ENDS pair\n'
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'native.cir';path.write_text(text);proof=audit(path)
            self.assertEqual(proof['device_count'],6);self.assertEqual(proof['independent_bodies'],['body1','body2'])
            bad=[text.replace('body2','body1'),text.replace('R2 S2 body2','R2 S2 body1'),
                 text.replace('D2 body2 NW2','D2 body2 NW1'),text.replace('D2 G2 S2','D2 G1 S2'),
                 text.replace('R2 S2 body2 ptap1 A=.6084p P=3.12u\n',''),text.replace('A=.6084p','A=.7p'),
                 text+'Xextra unexpected device x=1\n']
            for altered in bad:
                path.write_text(altered)
                with self.subTest(altered=altered),self.assertRaises(ValueError):audit(path)

    def test_controls_change_only_the_explicit_reference_contract(self):
        baseline=selected()
        self.assertEqual(baseline['ports'],list(PORTS))
        for fault in FAULTS:
            changed=selected(fault);self.assertEqual(changed['ports'],baseline['ports'])
            self.assertNotEqual(changed['sha256'],baseline['sha256'])
        with self.assertRaises(ValueError):selected('unreviewed')


if __name__=='__main__':unittest.main()
