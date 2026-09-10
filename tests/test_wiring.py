"""Electrical and persistence regressions for placed schematic conductors."""
import tempfile,unittest
from pathlib import Path
from icstudio.model import example,device,uid,clone,validate,save_project,load_project,flatten,History
from icstudio import wiring
from icstudio.interchange import spice,export_xschem


def circuit():
    p=example('empty');c=p['cells'][0];c.update(wires=[],junctions=[])
    c['devices']=[device('R','R1',100,150),device('C','C1',400,150),device('L','L1',250,300)]
    for d in c['devices']:d['net_labels']={}
    wiring.rebuild(c,p);return p,c


class WiringTests(unittest.TestCase):
    def test_routes_survive_save_netlist_and_wire_deletion(self):
        p,c=circuit();r,cap,l=c['devices'];points=[[100,100],[100,40],[400,40],[400,100]]
        ident,_=wiring.add_wire(c,points,p);self.assertEqual(c['wires'][0]['points'],points)
        self.assertEqual(r['nets']['p'],cap['nets']['p']);self.assertNotEqual(r['nets']['n'],cap['nets']['n'])
        wiring.set_label(c,r['id'],'p','signal',p);self.assertIn('R1 signal ',spice(p))
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'test.icproj';save_project(p,path);loaded=load_project(path)
            self.assertEqual(loaded['cells'][0]['wires'],c['wires'])
        h=History(p);h.commit(lambda p:p['cells'][0]['wires'].clear(),'Delete wire')
        a,b=h.project['cells'][0]['devices'][:2];self.assertNotEqual(a['nets']['p'],b['nets']['p'])
        h.undo();self.assertEqual(h.project['cells'][0]['devices'][0]['nets']['p'],h.project['cells'][0]['devices'][1]['nets']['p'])

    def test_t_branch_connects_all_pins_and_merges_named_net(self):
        p,c=circuit();r,cap,l=c['devices']
        wiring.add_wire(c,[[100,100],[400,100]],p)
        wiring.add_wire(c,[[250,250],[250,100]],p)
        self.assertEqual(len({d['nets']['p'] for d in c['devices']}),1)
        self.assertIn((250,100),wiring.junction_points(c,p))
        wiring.set_label(c,r['id'],'p','bus',p);wiring.set_label(c,cap['id'],'n','other',p)
        _,changes=wiring.add_wire(c,[[400,100],[450,100],[450,200],[400,200]],p)
        self.assertEqual(changes,['other']);self.assertEqual(cap['nets']['n'],'bus');self.assertEqual(l['nets']['p'],'bus')

    def test_crossings_are_not_junctions(self):
        p,c=circuit();c['devices']=[]
        a,_=wiring.add_wire(c,[[0,100],[200,100]],p);b,_=wiring.add_wire(c,[[100,0],[100,200]],p)
        g=wiring.graph(c,p);self.assertNotEqual(g[('wire',a)],g[('wire',b)]);self.assertNotIn((100,100),wiring.junction_points(c,p))
        c['junctions']=[[100,100]];g=wiring.graph(c,p);self.assertEqual(g[('wire',a)],g[('wire',b)]);self.assertIn((100,100),wiring.junction_points(c,p))
        wiring.rebuild(c,p);self.assertEqual(c['wires'][0]['net'],c['wires'][1]['net'])
        c['junctions']=[];g=wiring.graph(c,p);self.assertNotEqual(g[('wire',a)],g[('wire',b)])

    def test_moves_and_rotations_keep_connections_and_remote_bends(self):
        p,c=circuit();r,cap,_=c['devices'];wiring.add_wire(c,[[100,100],[100,40],[400,40],[400,100]],p)
        old=wiring.pins(c,p);r.update(x=140,rotation=90);wiring.keep_connections(c,old,p);validate(p)
        self.assertEqual(r['nets']['p'],cap['nets']['p']);self.assertIn([400,40],c['wires'][0]['points']);self.assertEqual(c['wires'][0]['points'][0],[190,150])
        pts=wiring.segment_drag([[0,0],[100,0]],0,30,40);self.assertEqual(pts,[[0,0],[0,40],[100,40],[100,0]])

    def test_legacy_migration_preserves_rc_and_inverter(self):
        for kind in ('rc','inverter'):
            p=example(kind);c=p['cells'][0];before=[clone(d['nets']) for d in c['devices']]
            wiring.migrate(c,p);validate(p);self.assertEqual([d['nets'] for d in c['devices']],before)
            self.assertIn('wires',c)

    def test_off_grid_pins_and_custom_hierarchy(self):
        p,c=circuit();c['devices'][0].update(x=103.5,y=155)
        wiring.add_wire(c,[[103.5,105],[103.5,40],[400,40],[400,100]],p);validate(p)
        self.assertEqual(c['devices'][0]['nets']['p'],c['devices'][1]['nets']['p'])
        child={'id':uid(),'name':'child','ports':['in'],'devices':[],'shapes':[],'symbol':{'pins':{'in':[-30,0]},'primitives':[]}}
        p['cells'].append(child);x=device('X','X1',300,40,cell=child['id'],nets={'in':'open'});c['devices'].append(x)
        wiring.rebuild(c,p);self.assertEqual(x['nets']['in'],c['devices'][0]['nets']['p'])

    def test_ground_is_explicit_and_label_can_be_removed(self):
        p,c=circuit();self.assertNotIn('0',{n for d in c['devices'] for n in d['nets'].values()})
        r,cap,_=c['devices'];wiring.set_label(c,r['id'],'n','0',p);wiring.set_label(c,cap['id'],'n','0',p)
        self.assertEqual(r['nets']['n'],cap['nets']['n']);wiring.set_label(c,cap['id'],'n','',p);self.assertNotEqual(r['nets']['n'],cap['nets']['n'])

    def test_external_export_and_import_use_wire_geometry(self):
        from icstudio.xschem_io import import_package
        p,c=circuit();wiring.add_wire(c,[[100,100],[100,40],[400,40],[400,100]],p)
        with tempfile.TemporaryDirectory() as td:
            export_xschem(p,td);file=Path(td)/'top.sch';text=file.read_text();self.assertIn('N 100 40 400 40',text)
            imported,report=import_package(file);cc=imported['cells'][0];self.assertEqual(cc['devices'][0]['nets']['p'],cc['devices'][1]['nets']['p'])
            file.write_text('\n'.join(line for line in text.splitlines() if not line.startswith('N 100 40 400 40'))+'\n')
            imported,report=import_package(file);cc=imported['cells'][0]
            # Both surviving pieces retain explicit exported net labels, as in Xschem.
            self.assertFalse(any(w['points']==[[100.,40.],[400.,40.]] for w in cc['wires']))

    def test_conflicting_moved_labels_are_rejected(self):
        p,c=circuit();r,cap,_=c['devices'];wiring.set_label(c,r['id'],'p','a',p);wiring.set_label(c,cap['id'],'p','b',p)
        c['wires']=[{'id':uid(),'points':[[100,100],[400,100]]}]
        with self.assertRaisesRegex(ValueError,'conflicting labels'):validate(p)

    def test_deleting_join_between_named_nets_does_not_leave_hidden_connection(self):
        p,c=circuit();r,cap,_=c['devices'];wiring.set_label(c,r['id'],'p','vin',p);wiring.set_label(c,cap['id'],'p','vout',p)
        ident,_=wiring.add_wire(c,[[100,100],[400,100]],p)
        self.assertEqual(r['nets']['p'],cap['nets']['p'])
        c['wires']=[];wiring.rebuild(c,p);self.assertNotEqual(r['nets']['p'],cap['nets']['p'])

    def test_moving_pin_at_branch_does_not_detach_other_conductors(self):
        p,c=circuit();r,cap,l=c['devices'];l['y']=150
        wiring.add_wire(c,[[100,100],[400,100]],p);wiring.add_wire(c,[[250,0],[250,100]],p)
        before=wiring.pins(c,p);l['y']=200;wiring.keep_connections(c,before,p);validate(p)
        self.assertEqual(len({d['nets']['p'] for d in c['devices']}),1)

if __name__=='__main__':unittest.main()
