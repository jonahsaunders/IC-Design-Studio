"""Public-style contact arrangements must not invent an orientation axis."""
import tempfile
from pathlib import Path
import unittest
import klayout.db as db
from icstudio.sky130_mim2_extract import electrodes
from icstudio.interchange import export_layout
from tests.test_sky130_mim2 import fixture


class MimContactTopologyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'input.gds'
        project,_,_=fixture(3,5,1);export_layout(project,self.path)

    def ring(self, fault=None):
        ly=db.Layout();ly.read(str(self.path));cell=ly.top_cell()
        cap=db.Region(cell.shapes(ly.layer(97,44)));box=cap.bbox()
        # A synthetic symmetric surround, not copied third-party layout data.
        cell.shapes(ly.layer(71,20)).clear()
        cell.shapes(ly.layer(71,20)).insert(box.enlarged(1000))
        shape=cell.shapes(ly.layer(71,44));inside=db.Region(shape)&cap;shape.clear();shape.insert(inside)
        x,y=(box.left+box.right)//2,(box.bottom+box.top)//2
        points=[(box.left-600,y),(box.right+600,y),(x,box.bottom-600),(x,box.top+600),
                (box.left-600,box.bottom-600),(box.right+600,box.bottom-600),
                (box.left-600,box.top+600),(box.right+600,box.top+600)]
        for i,(cx,cy) in enumerate(points):
            if fault=='missing' and i==0:continue
            if fault=='moved' and i==0:cy+=5
            shape.insert(db.Box(cx-100,cy-100,cx+100,cy+100))
        if fault=='asymmetric-bottom':cell.shapes(ly.layer(71,20)).insert(db.Box(box.left-1500,y-100,box.left,y+100))
        return ly

    def test_reflection_symmetric_ring_retains_explicit_native_axes_in_all_transforms(self):
        for mirror in (False,True):
            for angle in range(4):
                ly=self.ring();ly.top_cell().transform(db.Trans(angle,mirror,123000,-456000))
                path=self.root/f'ring-{angle}-{mirror}.gds';ly.write(str(path))
                _,rows=electrodes(path,ly.top_cell().name)
                self.assertEqual(len(rows),1);self.assertEqual(rows[0]['axis'],'native')
                self.assertIn('no unique',rows[0]['convention'])

    def test_incomplete_or_asymmetric_surround_cannot_receive_native_ring_exception(self):
        for fault in ('missing','moved','asymmetric-bottom'):
            ly=self.ring(fault);path=self.root/(fault+'.gds');ly.write(str(path))
            with self.subTest(fault=fault),self.assertRaisesRegex(ValueError,'exactly one axis'):
                electrodes(path,ly.top_cell().name)

    def test_collinear_contacts_can_touch_plate_end_lines_without_changing_axis(self):
        ly=db.Layout();ly.read(str(self.path));cell=ly.top_cell()
        cap=db.Region(cell.shapes(ly.layer(97,44)));box=cap.bbox()
        shape=cell.shapes(ly.layer(71,44));outside=list((db.Region(shape)-cap).each())
        x=outside[0].bbox().left
        shape.insert(db.Box(x,box.bottom-200,x+200,box.bottom))
        shape.insert(db.Box(x,box.top,x+200,box.top+200))
        path=self.root/'ends.gds';ly.write(str(path));_,rows=electrodes(path,cell.name)
        self.assertEqual(rows[0]['axis'],'x')
        # Moving a cut beyond the end line creates an ambiguous corner again.
        shape.insert(db.Box(x,box.top+205,x+200,box.top+405))
        path=self.root/'outside.gds';ly.write(str(path))
        with self.assertRaisesRegex(ValueError,'exactly one axis'):electrodes(path,cell.name)


if __name__=='__main__':unittest.main()
