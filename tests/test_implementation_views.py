"""Captured implementation integrity, interface mapping and real SPICE behavior."""
import os
import tempfile
import unittest
from pathlib import Path

from icstudio.model import example, device, uid, clone, validate, History, save_project, load_project
from icstudio.implementation_views import capture, get, stage, subcircuits
from icstudio.testbenches import create, deck, simulate, compare_implementation, spice_testbench


def fixture(native=False):
    p=example('empty');bench=p['cells'][0];bench['name']='divider_bench'
    dut={'id':uid(),'name':'divider','ports':['in','out','vss'],'devices':[
        device('R','R1',value='1k',nets={'p':'in','n':'out'}),
        device('R','R2',value='1k',nets={'p':'out','n':'vss'})],'shapes':[]}
    p['cells'].append(dut)
    bench['devices']=[device('V','VDD',value='1',nets={'p':'supply','n':'0'}),
        device('X','XDUT',cell=dut['id'],nets={'in':'supply','out':'output','vss':'0'})]
    p['analysis']['type']='op'
    if native:p['spice']={'version':1,'assets':{},'library_lock':{}}
    t=create(p,bench['id'],'divider_op');t['probes']=['output'];t['measurements']=[{'name':'output','kind':'voltage','node':'output','min':'.4','max':'.6'}]
    p['testbenches']=[t]
    text='* reversed and uppercase port order\n.subckt physical VSS OUT IN\nR1 IN OUT 1k\nR2 OUT VSS 1k\n.ends physical\n'
    view=capture(p,dut['id'],'post_layout',text,'physical','rc','extracted.spice')
    p['implementation_views']=[view];t['implementation_view']=view['id'];validate(p)
    return p,t,view


class ImplementationViews(unittest.TestCase):
    def test_export_uses_selected_interface_and_preserves_models(self):
        for native in (False,True):
            with self.subTest(native=native),tempfile.TemporaryDirectory() as tmp:
                p,t,v=fixture(native);text=spice_testbench(p,t,tmp)
                self.assertIn('XDUT 0 output supply physical',text)
                self.assertIn(v['netlist'].rstrip(),text)
                self.assertNotIn('__studio_dut_definition__',text)
                self.assertNotIn('.subckt divider',text)
                if native:self.assertTrue((Path(tmp)/'model-files.json').is_file())

    def test_locked_pdk_relocation_keeps_view_current(self):
        p,t,v=fixture();p['pdk']['package_lock']={'id':'reference','revision':'1','files':{'models.spice':'a'*64}}
        p['pdk']['package_root']='C:/original/models'
        v=capture(p,t['dut_cell'],'portable',v['netlist'],'physical');p['implementation_views']=[v];t['implementation_view']=v['id']
        p['pdk']['package_root']='D:/relocated/models';get(p,v['id'])
        p['pdk']['package_lock']['files']['models.spice']='b'*64
        with self.assertRaisesRegex(ValueError,'stale'):get(p,v['id'])

    def test_reordered_ports_use_named_connections_and_selected_top(self):
        p,t,v=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path,pins,top=stage(p,v['id'],t['dut_cell'],tmp)
            text=deck(p,t,path,pins,subcircuit_name=top)
            self.assertIn('XDUT 0 output supply physical',text)
            self.assertEqual(path.read_text(),v['netlist'])

    def test_model_environment_is_preserved_for_native_extracted_fixture(self):
        p,t,v=fixture(True)
        dut=next(c for c in p['cells'] if c['id']==t['dut_cell'])
        dut['spice_statements']=['.param device_scale=2']
        p['implementation_views']=[capture(p,dut['id'],'native_view',v['netlist'],'physical')]
        t['implementation_view']=p['implementation_views'][0]['id']
        with tempfile.TemporaryDirectory() as tmp:
            path,pins,top=stage(p,t['implementation_view'],t['dut_cell'],tmp)
            text=deck(p,t,path,pins,subcircuit_name=top)
            self.assertIn('.param device_scale=2',text)
            self.assertNotIn('.subckt divider',text)
            self.assertIn('XDUT 0 output supply physical',text)
            self.assertTrue((Path(tmp)/'model-files.json').is_file())

    def test_persistence_undo_and_stale_detection(self):
        p,t,v=fixture();history=History(p)
        history.commit(lambda q:q['cells'][1]['devices'][0].update(value='2k'))
        with self.assertRaisesRegex(ValueError,'stale'):get(history.project,v['id'])
        history.undo();self.assertEqual(get(history.project,v['id'])['sha256'],v['sha256'])
        # Stimulus changes are valid comparisons with the same extracted DUT.
        history.commit(lambda q:q['cells'][0]['devices'][0].update(value='2'))
        get(history.project,v['id'])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'relocated.icproj';save_project(history.project,path)
            self.assertEqual(get(load_project(path),v['id'])['netlist'],v['netlist'])
        for mutate in (
            lambda q:q['pdk'].update(revision='changed'),
            lambda q:q['cells'][1]['shapes'].append({'id':uid(),'kind':'rect','layer':'metal1','points':[[0,0],[100,100]]}),
            lambda q:q['cells'][1]['devices'][0]['nets'].update(n='wrong')):
            changed=clone(p);mutate(changed)
            with self.assertRaisesRegex(ValueError,'stale'):get(changed,v['id'])

    def test_tampering_and_unsafe_or_ambiguous_netlists_are_rejected(self):
        p,t,v=fixture();v['netlist']=v['netlist'].replace('1k','2k')
        with self.assertRaisesRegex(ValueError,'checksum'):validate(p)
        for text in ('.include other.spice', '.subckt x a b\n.control\nshell whoami\n.endc\n.ends x',
                     '.subckt x a A\n.ends x', '.subckt x a b\n.ends y',
                     '.subckt x a b\n.subckt y a b\n.ends y\n.ends x'):
            with self.assertRaises(ValueError):subcircuits(text)

    def test_native_and_catalog_results_compare_without_relabelling_failures(self):
        executable=os.environ.get('ICSTUDIO_TEST_NGSPICE')
        if not executable:self.skipTest('Set ICSTUDIO_TEST_NGSPICE for numerical verification.')
        for native in (False,True):
            with self.subTest(native=native),tempfile.TemporaryDirectory() as tmp:
                p,t,v=fixture(native);result=compare_implementation(p,t,executable,tmp)
                self.assertAlmostEqual(result['traces']['output'][0],.5,places=10)
                self.assertEqual(result['implementation_comparison']['status'],'passed')
                self.assertAlmostEqual(result['implementation_comparison']['measurements'][0]['delta'],0,places=10)
            with tempfile.TemporaryDirectory() as tmp:
                p,t,v=fixture(native)
                bad=capture(p,t['dut_cell'],'bad',v['netlist'].replace('R2 OUT VSS 1k','R2 OUT VSS 9k'),'physical')
                p['implementation_views'].append(bad);t['implementation_view']=bad['id']
                result=compare_implementation(p,t,executable,tmp)
                self.assertEqual(result['implementation_comparison']['status'],'failed')
                self.assertTrue(result['implementation_comparison']['measurements'][0]['regressed'])


if __name__=='__main__':unittest.main()
