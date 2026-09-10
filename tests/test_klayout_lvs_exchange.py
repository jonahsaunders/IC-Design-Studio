"""Extract geometry, compare an independent SPICE reference, retain .lvsdb."""
import tempfile
import unittest
from pathlib import Path
import klayout.db as db
from icstudio.klayout_lvs import read_database,locations
from icstudio.model import example,uid


def resistor_database(directory,resistance=800):
    ly=db.Layout();ly.dbu=.001;cell=ly.create_cell('TEST');ri=ly.layer(1,0);ci=ly.layer(2,0);li=ly.layer(2,1)
    cell.shapes(ri).insert(db.Box(100,0,900,100))
    for x,name in ((0,'A'),(900,'B')):
        cell.shapes(ci).insert(db.Box(x,0,x+100,100));cell.shapes(li).insert(db.Text(name,db.Trans(x+50,50)))
    lvs=db.LayoutVsSchematic(db.RecursiveShapeIterator(ly,cell,[]))
    resistor=lvs.make_layer(ri,'resistor');metal=lvs.make_layer(ci,'metal');labels=lvs.make_text_layer(li,'labels')
    lvs.extract_devices(db.DeviceExtractorResistor('RES',100),{'R':resistor,'C':metal})
    lvs.connect(metal);lvs.connect(metal,labels);lvs.extract_netlist();lvs.netlist().make_top_level_pins()
    reference=directory/'reference.spice';reference.write_text(f'* independent reference\n.subckt TEST A B\nR1 A B {resistance}\n.ends\n')
    netlist=db.Netlist();netlist.read(str(reference),db.NetlistSpiceReader());lvs.reference=netlist
    lvs.compare(db.NetlistComparer());path=directory/'comparison.lvsdb';lvs.write(str(path));return path


class KLayoutLVSExchangeTests(unittest.TestCase):
    def test_real_extraction_and_independent_reference_detect_value_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);matched=read_database(resistor_database(root));self.assertTrue(matched['matched'],matched)
            nets=[r for r in matched['rows'] if r['kind']=='net'];self.assertEqual(len(nets),2);self.assertTrue(all(r['boxes_um'] for r in nets))
            self.assertTrue(any(r['kind']=='device' and r['schematic']=='1' for r in matched['rows']))
            broken=read_database(resistor_database(root,900));self.assertFalse(broken['matched']);self.assertTrue(any(r['status']!='Match' for r in broken['rows']))

    def test_occurrences_include_rotation_arrays_and_bounded_traversal(self):
        p=example('empty');child={'id':uid(),'name':'TEST','ports':[],'devices':[],'shapes':[]};p['cells'].append(child)
        p['cells'][0]['layout_instances']=[{'id':uid(),'name':'U','cell':child['id'],'x':2000,'y':3000,'rotation':90,'nx':2,'ny':1,'a':[5000,0],'b':[0,0]}]
        points=locations(p,{'cell':'TEST','boxes_um':[[0,0,.1,.1]]})
        self.assertEqual(len(points),2);self.assertEqual(points[0]['boxes_nm'],[[1900,3000,2000,3100]])
        self.assertEqual(points[1]['boxes_nm'],[[6900,3000,7000,3100]])
        p['cells'][0]['layout_instances'][0]['nx']=10001
        with self.assertRaisesRegex(ValueError,'smaller'):locations(p,{'cell':'TEST','boxes_um':[]})


if __name__=='__main__':unittest.main()
