import unittest,tempfile
from pathlib import Path
from icstudio import wiring,net_labels
from icstudio.model import example,clone,validate,save_project,load_project,History,device
from icstudio.interchange import spice,export_xschem
from icstudio.xschem_io import import_package

class LabelTests(unittest.TestCase):
    def cell(self):
        p=example('empty');c=p['cells'][0];c.update(wires=[],junctions=[]);return p,c
    def test_wire_label_joins_remote_pin_and_survives_save(self):
        p,c=self.cell();w,_=wiring.add_wire(c,[[0,0],[100,0]],p)
        d=device('R','R1',300,150);d['net_labels']={};c['devices'].append(d);wiring.rebuild(c,p)
        ident=net_labels.add(c,'out',{'kind':'wire','id':w,'point':[50,0]},p)
        net_labels.add(c,'out',{'kind':'pin','id':d['id'],'pin':'p'},p)
        self.assertEqual(c['wires'][0]['net'],d['nets']['p']);self.assertEqual(net_labels.describe(c,'out',p)['conductors'],2)
        net_labels.rename(c,ident,'signal',p,True);self.assertEqual(d['nets']['p'],'signal');self.assertIn('R1 signal ',spice(p))
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'labels.icproj';save_project(p,f);self.assertEqual(load_project(f)['cells'][0],c)
            export_xschem(p,Path(td)/'x');other,_=import_package(Path(td)/'x');self.assertEqual(other['cells'][0]['devices'][0]['nets']['p'],'signal')
    def test_crossing_label_belongs_to_one_wire(self):
        p,c=self.cell();a,_=wiring.add_wire(c,[[0,50],[100,50]],p);b,_=wiring.add_wire(c,[[50,0],[50,100]],p)
        net_labels.add(c,'out',{'kind':'wire','id':a,'point':[50,50]},p)
        self.assertEqual(c['wires'][0]['net'],'out');self.assertNotEqual(c['wires'][1]['net'],'out')
    def test_ground_then_wire_then_delete_undo(self):
        p,c=self.cell();g=net_labels.add(c,'0',{'kind':'point','point':[100,100]},p,'ground');wiring.add_wire(c,[[0,100],[100,100]],p)
        self.assertEqual(c['wires'][0]['net'],'0');h=History(p);h.commit(lambda p:p['cells'][0]['labels'].clear());self.assertNotEqual(h.project['cells'][0]['wires'][0]['net'],'0');h.undo();self.assertEqual(h.project['cells'][0]['wires'][0]['net'],'0');h.redo();self.assertNotEqual(h.project['cells'][0]['wires'][0]['net'],'0')
    def test_artwork_moves_without_changing_net(self):
        p,c=self.cell();ident,_=wiring.add_wire(c,[[0,0],[100,0]],p);label=net_labels.add(c,'VDD',{'kind':'wire','id':ident,'point':[40,0]},p)
        c['labels'][0]['offset']=[200,200];validate(p);self.assertEqual(c['wires'][0]['net'],'VDD')
        old=clone(c);c['wires'][0]['points']=[[0,30],[100,30]];net_labels.reconcile(c,old,p);self.assertEqual(c['labels'][0]['anchor']['point'],[40,30]);validate(p)
        c['wires']=[];net_labels.reconcile(c,old,p);self.assertFalse(c['labels'])
    def test_conflict_and_invalid_attachment_are_transactional(self):
        p,c=self.cell();ident,_=wiring.add_wire(c,[[0,0],[100,0]],p);net_labels.add(c,'VDD',{'kind':'wire','id':ident,'point':[40,0]},p);h=History(p);before=clone(h.project)
        with self.assertRaises(ValueError):h.commit(lambda p:net_labels.add(p['cells'][0],'out',{'kind':'wire','id':ident,'point':[60,0]},p))
        self.assertEqual(h.project,before);self.assertFalse(h.undo_stack)
        c['labels'][0]['anchor']['point']=[50,50]
        with self.assertRaises(ValueError):validate(p)
    def test_pin_follows_rotation_and_pin_inspector_renames_label(self):
        p,c=self.cell();d=device('R','R1',100,100);d['net_labels']={};c['devices'].append(d);wiring.rebuild(c,p)
        net_labels.add(c,'in',{'kind':'pin','id':d['id'],'pin':'p'},p);d['rotation']=90;self.assertEqual(net_labels.point(c['labels'][0],c,p),[150,100])
        wiring.set_label(c,d['id'],'p','renamed',p);self.assertEqual(c['labels'][0]['name'],'renamed');self.assertEqual(d['nets']['p'],'renamed')
