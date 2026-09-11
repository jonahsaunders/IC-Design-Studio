import tempfile
import unittest
from pathlib import Path
from icstudio.analog import reference
from icstudio.analog_bank import generate
from icstudio.analog_constraints import findings
from icstudio.model import clone, History, validate
from icstudio.physical import connectivity
from icstudio.interchange import export_layout
from icstudio.testbenches import spice_testbench
from test_silicon import technology


class AnalogBankTests(unittest.TestCase):
    def test_references_are_connected_constrained_and_exportable(self):
        for kind in ('current_mirror','differential_pair','amplifier'):
            with self.subTest(kind=kind):
                p,cid,key=reference(technology(),kind);generate(p,cid)
                self.assertEqual(connectivity(p,cid)['issues'],[])
                self.assertEqual(findings(p,cid),[])
                c=next(c for c in p['cells'] if c['id']==cid)
                self.assertTrue(c['analog_constraints'])
                self.assertEqual({v['name'] for v in c['layout_ports']},set(c['ports']))
                for bench in p['testbenches']:self.assertIn('.subckt',spice_testbench(p,bench))
                with tempfile.TemporaryDirectory() as tmp:export_layout(p,Path(tmp)/'reference.gds')

    def test_faults_and_regeneration_are_reviewable_and_undoable(self):
        p,cid,key=reference(technology(),'amplifier');generate(p,cid);h=History(p)
        def fault(q):
            c=next(c for c in q['cells'] if c['id']==cid)
            shape=next(s for s in c['shapes'] if s.get('generated_device')==c['devices'][0]['id'] and s['layer']=='poly')
            shape['points'][1][0]+=50
        h.commit(fault,'Change gate geometry');self.assertTrue(findings(h.project,cid));before=clone(h.project)
        h.commit(lambda q:generate(q,cid,True),'Regenerate analog layout');self.assertFalse(findings(h.project,cid))
        h.undo();self.assertEqual(h.project['cells'],before['cells'])
        with self.assertRaisesRegex(ValueError,'empty layout'):generate(h.project,cid)

    def test_saved_plans_do_not_break_fixture_netlist_subsets(self):
        from icstudio.test_plans import sources
        p,cid,key=reference(technology(),'amplifier')
        p['test_plans']=[dict(id='plan',name='Amplifier',entries=sources(p),corners=['nominal'],temperatures=[27],voltages=[])]
        validate(p);text=spice_testbench(p,p['testbenches'][1]);self.assertIn('AC 1',text)


if __name__=='__main__':unittest.main()
