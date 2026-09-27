import json
from pathlib import Path
import tempfile
import unittest
import klayout.db as db
from icstudio.layout_verification import reference,verification_stream,run
from icstudio.model import example


class LayoutVerificationTests(unittest.TestCase):
    def test_legacy_labels_and_repeated_child_labels_do_not_merge_local_nets(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);ly=db.Layout();ly.dbu=.001
            top=ly.create_cell('top');child=ly.create_cell('child');metal=ly.layer(68,20);label=ly.layer(68,5)
            child.shapes(metal).insert(db.Box(0,0,100,100));child.shapes(label).insert(db.Text('local',db.Trans(50,50)))
            top.insert(db.CellInstArray(child.cell_index(),db.Trans(),db.Vector(1000,0),db.Vector(0,0),3,1))
            top.shapes(label).insert(db.Text('IN',db.Trans(50,50)));top.shapes(label).insert(db.Text('OUT',db.Trans(2050,50)))
            ly.write(str(root/'original.gds'))
            r=verification_stream(root/'original.gds','top',['IN','OUT'],root/'engine.gds',pin_layers={(68,16)})
            actual=db.Layout();actual.read(str(root/'engine.gds'));c=actual.cell('top')
            self.assertEqual(list(c.each_inst()),[])
            self.assertEqual(sorted(s.text.string for s in c.shapes(actual.layer(68,5)).each()),['IN','OUT'])
            self.assertEqual(db.Region(c.shapes(actual.layer(68,20))).area(),30000)
            self.assertEqual(r['removed_noninterface_labels'],1)
            with self.assertRaisesRegex(ValueError,'Missing top-level'):
                verification_stream(root/'original.gds','top',['IN','missing'],root/'absent.gds',pin_layers={(68,16)})
            top.shapes(ly.layer(68,16)).insert(db.Text('UNEXPECTED',db.Trans(50,50)));ly.write(str(root/'extra.gds'))
            with self.assertRaisesRegex(ValueError,'extra explicit'):
                verification_stream(root/'extra.gds','top',['IN','OUT'],root/'extra-out.gds',pin_layers={(68,16)})

    def test_reference_requires_real_interface_and_closed_sources(self):
        text='.subckt dut a b\nR1 a b 1k\n.ends\n'
        self.assertEqual(reference(text,'dut')['ports'],['a','b'])
        for other in (text+'.include missing.spice\n',text.replace('a b\n','a A\n'),text.replace('R1 a b 1k','')):
            with self.assertRaises(ValueError):reference(other,'dut')

    def test_missing_runtime_is_reported_as_blocked_without_simulation(self):
        p=example('empty');ref=reference('.subckt dut a b\nR1 a b 1k\n.ends','dut')
        with tempfile.TemporaryDirectory() as td:
            r=run(p,p['top'],td,{},ref,blocked_reason='Install the physical runtime')
            self.assertEqual(r['status'],'blocked');self.assertEqual(len(r['stages']),6)
            self.assertEqual(r['stages'][0]['error'],'Install the physical runtime')
            self.assertTrue(all(s['status']=='not_run' for s in r['stages'][1:]))

    def test_varactor_default_is_omitted_only_in_lvs_with_multiplicity_retained(self):
        from icstudio.native_spice import render
        def device(vm,model='sky130_fd_pr__cap_var_lvt'):
            return {'native_spice':{'type':'device','tokens':[{'kind':'literal','value':f'XC1 a b c {model} W=2 L=1 VM={vm} m=3'}]}}
        self.assertIn('VM=1',render(device('1')))
        self.assertNotIn('VM=',render(device('1'),mode='lvs'))
        self.assertIn('m=3',render(device('1'),mode='lvs'))
        self.assertIn('VM=2',render(device('2'),mode='lvs'))
        self.assertIn('VM=1',render(device('1','unknown_model'),mode='lvs'))


if __name__=='__main__':unittest.main()
