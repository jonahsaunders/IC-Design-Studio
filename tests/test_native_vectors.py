"""Native arrays retain editable capture while emitting exact scalar circuits."""
import tempfile
import unittest
import os
import re
import shutil
import subprocess
from unittest.mock import patch
from pathlib import Path
from icstudio.model import clone, device, example, flatten, History, load_project, save_project, uid, validate
from icstudio.native_vectors import signals, ports, devices, expand_device, configure_array
from icstudio.interchange import spice
from icstudio.native_spice import netlist
from icstudio.symbol_io import default_symbol
from icstudio import wiring


def ladder():
    p=example('empty');c=p['cells'][0]
    c['devices']=[device('V','V1',0,0,value='3',nets={'p':'tap[3]','n':'0'}),
                  device('R','Rbank',200,0,value='1k',array={'start':2,'end':0},nets={'p':'tap[3:1]','n':'tap[2:0]'}),
                  device('R','Rload',400,0,value='1k',nets={'p':'tap[0]','n':'0'})]
    p['analysis']['type']='op'
    return p


def hierarchy():
    p=example('empty');top=p['cells'][0]
    child={'id':uid(),'name':'pair','ports':['p[1:0]','supply'],'shapes':[],
           'parameters':{'resistance':'1k'},'devices':[
               device('R','Rb',array={'start':0,'end':1},value='{resistance}',nets={'p':'p[1:0]','n':'supply'})]}
    child['symbol']=default_symbol(child['ports']);p['cells'].append(child)
    top['devices']=[device('X','Xbank',cell=child['id'],array={'start':3,'end':2},
                           parameters={'resistance':'2k'},nets={'p[1:0]':'data[7:4]','supply':'VDD'},
                           rotation=90,mirror=True,symbol=clone(child['symbol']))]
    p['global_nets']=['VDD','bias[1:0]']
    return p


class NativeVectorTests(unittest.TestCase):
    def test_ordered_ranges_slices_and_limits(self):
        self.assertEqual(signals('data[7:5], data[1], data[3:4]'),['data[7]','data[6]','data[5]','data[1]','data[3]','data[4]'])
        for value in ('a[128:0]','a[0:3:2]','2*a[3:0]','[tcleval foo]','a[foo]','a[-1:2]','a[3:0],','a[9999999999]'):
            with self.subTest(value=value),self.assertRaises(ValueError):signals(value)
        for value in (['a[2:0]','a[1]'],['a[2:0]','A[1]'],['0']):
            with self.subTest(value=value),self.assertRaises(ValueError):ports(value)

    def test_array_series_ladder_matches_hand_calculation_and_both_emitters(self):
        p=ladder();validate(p);expected=[('Rbank__2',{'p':'tap[3]','n':'tap[2]'}),('Rbank__1',{'p':'tap[2]','n':'tap[1]'}),('Rbank__0',{'p':'tap[1]','n':'tap[0]'})]
        self.assertEqual([(d['name'],d['nets']) for d in flatten(p) if d['name'].startswith('Rbank')],expected)
        from icstudio.simulation import run
        result=run(p,p['top'],p['analysis'])
        for name,value in [('tap[3]',3),('tap[2]',2.25),('tap[1]',1.5),('tap[0]',.75)]:
            self.assertAlmostEqual(result['traces'][name][-1],value,7)
        generic=spice(p)
        with tempfile.TemporaryDirectory() as tmp:
            q=clone(p);q['spice']={'version':1,'assets':{}}
            native=netlist(q,tmp)
        for name,nets in expected:
            for text in (generic,native):self.assertIn(name+' '+nets['p']+' '+nets['n']+' ',text)
        self.assertEqual(p['cells'][0]['devices'][1]['array'],{'start':2,'end':0})

    def test_nested_vector_ports_chunk_in_declared_order_and_resolve_parameters(self):
        p=hierarchy();validate(p);rows=flatten(p)
        self.assertEqual([d['name'] for d in rows],['Xbank__3/Rb__0','Xbank__3/Rb__1','Xbank__2/Rb__0','Xbank__2/Rb__1'])
        self.assertEqual([d['nets'] for d in rows],[{'p':f'data[{i}]','n':'VDD'} for i in (7,6,5,4)])
        self.assertTrue(all(float(d['value'])==2000 for d in rows))
        self.assertIn('.global VDD bias[1] bias[0]',spice(p))
        p['cells'][0]['devices'][0]['parameters']={};p['cells'][1].pop('parameters');p['cells'][1]['devices'][0]['value']='1k'
        text=spice(p,hierarchical=True)
        self.assertIn('.subckt pair p[1] p[0] supply',text)
        self.assertIn('Xbank__3 data[7] data[6] VDD pair',text)
        self.assertIn('Xbank__2 data[5] data[4] VDD pair',text)
        with tempfile.TemporaryDirectory() as tmp:
            p['spice']={'version':1,'assets':{}};text=netlist(p,tmp)
            self.assertIn('Xbank__3 data[7] data[6] VDD pair',text)

    def test_scalar_and_whole_port_broadcast_are_explicit(self):
        p=hierarchy();item=p['cells'][0]['devices'][0];item['nets']['p[1:0]']='input[0:1]'
        rows=expand_device(item,p)
        self.assertEqual(rows[0]['nets'],rows[1]['nets'])
        item['nets']['p[1:0]']='input'
        with self.assertRaisesRegex(ValueError,'connection width 1'):validate(p)

    def test_collision_width_and_program_arrays_fail_before_netlisting(self):
        p=ladder();p['cells'][0]['devices'].append(device('R','Rbank__1'))
        with self.assertRaisesRegex(ValueError,'collides'):validate(p)
        p=ladder();p['cells'][0]['devices'][1]['nets']['p']='tap[5:1]'
        with self.assertRaisesRegex(ValueError,'connection width 5'):validate(p)
        item=device('R','P');item.update(array={'start':0,'end':1},native_spice={'type':'program'})
        with self.assertRaisesRegex(ValueError,'programs cannot'):expand_device(item)
        for spec in ({'start':True,'end':2},{'start':0,'end':128},{'start':-1,'end':0}):
            with self.subTest(spec=spec),self.assertRaises(ValueError):expand_device(device('R','Rb',array=spec))

    def test_save_reopen_history_and_rotation_keep_compact_and_stable_member_ids(self):
        p=ladder();wiring.migrate(p['cells'][0],p);h=History(p);before=clone(h.project)
        ids=[d['id'] for d in flatten(h.project)]
        h.commit(lambda q:q['cells'][0]['devices'][1].update(rotation=180,mirror=True))
        self.assertEqual([d['id'] for d in flatten(h.project)],ids)
        h.undo();self.assertEqual(h.project['cells'],before['cells']);h.redo()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'vectors.icproj';save_project(h.project,path);q=load_project(path)
            self.assertEqual(q['cells'],h.project['cells']);self.assertEqual([d['id'] for d in flatten(q)],ids)

    def test_bus_labels_and_scalar_taps_connect_only_the_named_bit(self):
        p=ladder();c=p['cells'][0];wiring.migrate(c,p)
        rows=flatten(p)
        self.assertEqual(next(d for d in rows if d['name']=='Rload')['nets']['p'],'tap[0]')
        self.assertEqual(len({d['nets']['p'] for d in rows}),4)
        from icstudio.net_labels import add
        # A scalar device may not consume a whole bus by a coincident label.
        p=example('empty');c=p['cells'][0];c['devices']=[device('R','R1',nets={'p':'in','n':'0'})];wiring.migrate(c,p)
        wiring.set_label(c,c['devices'][0]['id'],'p','',p)
        with self.assertRaisesRegex(ValueError,'connection width 4'):
            add(c,'data[3:0]',{'kind':'pin','id':c['devices'][0]['id'],'pin':'p'},p)

    def test_wire_merge_rejects_bus_to_scalar_width_change(self):
        p=ladder();c=p['cells'][0];wiring.migrate(c,p)
        a=c['devices'][1];b=c['devices'][2];positions=wiring.pins(c,p)
        with self.assertRaisesRegex(ValueError,'scalar and bus'):
            wiring.add_wire(c,[positions[(a['id'],'p')],positions[(b['id'],'p')]],p)

    def test_unlabelled_array_and_bus_pins_get_distinct_floating_members(self):
        p=hierarchy();c=p['cells'][0]
        c['wires']=[];c['junctions']=[];c['labels']=[]
        for item in c['devices']:item['net_labels']={}
        wiring.rebuild(c,p);validate(p)
        self.assertEqual(len(signals(c['devices'][0]['nets']['p[1:0]'])),4)
        self.assertEqual(len({d['nets']['p'] for d in flatten(p)}),4)
        original=clone(c['devices'][0]['nets']);wiring.rebuild(c,p)
        self.assertEqual(c['devices'][0]['nets'],original)
        from icstudio.electrical_rules import check
        self.assertFalse(any(i['code']=='ERC.BUS.WIDTH' for i in check(p,p['top'])))

    def test_native_terminal_tokens_expand_vector_interface(self):
        p=hierarchy();item=p['cells'][0]['devices'][0]
        item['native_spice']={'version':1,'type':'device','parameters':{},'tokens':[
            {'kind':'instance'},{'kind':'literal','value':' '},{'kind':'terminal','value':'p[1:0]'},
            {'kind':'literal','value':' '},{'kind':'terminal','value':'supply'},
            {'kind':'literal','value':' '},{'kind':'cell'}]}
        p['spice']={'version':1,'assets':{}}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn('Xbank__2 data[5] data[4] VDD pair',netlist(p,tmp))

    def test_saved_testbench_expands_dut_ports_and_fixture_probes(self):
        from icstudio.testbenches import create, deck, native_subcircuit
        p=hierarchy();top=p['cells'][0];item=top['devices'][0];item.pop('array');item.pop('parameters');item['nets']['p[1:0]']='data[1:0]'
        top['devices'].append(device('V','VDD',700,0,value='1',nets={'p':'VDD','n':'0'}))
        bench=create(p,p['top']);bench['analysis']['type']='op';p['testbenches']=[bench];validate(p)
        self.assertEqual(bench['probes'],['VDD','data[0]','data[1]'])
        self.assertIn('.subckt pair p[1] p[0] supply',native_subcircuit(p,item['cell']))
        text=deck(p,bench,'/tmp/vector-dut.spice',ports=['supply','p[0]','p[1]'])
        self.assertIn('Xbank VDD data[0] data[1] pair',text)

    def test_real_ngspice_native_array_ladder(self):
        executable=os.environ.get('ICSTUDIO_TEST_NGSPICE') or shutil.which('ngspice')
        if not executable:self.skipTest('ngspice is not installed')
        p=ladder();p['spice']={'version':1,'assets':{}}
        p['cells'][0]['spice_statements']=['.op']
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'saved.icproj';save_project(p,path);q=load_project(path)
            netlist(q,tmp)
            result=subprocess.run([executable,'-b',str(Path(tmp)/'source.cir')],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            rows=dict(re.findall(r'^\s*(tap\[\d+\])\s+([\d.eE+-]+)\s*$',result.stdout,re.M))
            self.assertEqual(set(rows),{'tap[0]','tap[1]','tap[2]','tap[3]'},result.stdout)
            for index,expected in enumerate((.75,1.5,2.25,3)):self.assertAlmostEqual(float(rows[f'tap[{index}]']),expected,7)
            from icstudio.engines import run_ngspice
            result=run_ngspice(q,q['top'],q['analysis'],executable,Path(tmp)/'worker')
            for index,expected in enumerate((.75,1.5,2.25,3)):
                self.assertAlmostEqual(result['traces'][f'tap[{index}]'][-1],expected,7)

    def test_sources_and_operating_aliases_use_member_names(self):
        from icstudio.analysis_sources import source_names
        from icstudio.native_analysis import sources
        from icstudio.operating_data import native_save
        from icstudio.analog_debug import contexts,operating_rows
        p=hierarchy();c=p['cells'][1]
        c['devices'].append(device('V','Vbias',array={'start':1,'end':0},nets={'p':'bias[1:0]','n':'0'}))
        self.assertEqual(source_names(p),['Xbank__3/Vbias__1','Xbank__3/Vbias__0','Xbank__2/Vbias__1','Xbank__2/Vbias__0'])
        self.assertEqual(sources(p,c['id']),[('Vbias__1','Vbias__1','V'),('Vbias__0','Vbias__0','V')])
        self.assertEqual([v['path'] for v in contexts(p,p['top'])],['','Xbank__3/','Xbank__2/'])
        directive,aliases=native_save(p,p['top'])
        self.assertEqual(aliases['v.xbank__3.vbias__1'],'Xbank__3/Vbias__1')
        rows=operating_rows(p,p['top'],{'operating_point':{'bias[1]':1.8}})
        self.assertEqual(next(r['voltages']['p'] for r in rows if r['name']=='Xbank__3/Vbias__1'),1.8)

    def test_empty_array_hierarchy_expansion_is_bounded(self):
        from icstudio.analysis_sources import source_names
        from icstudio.analog_debug import contexts
        p=example('empty');child=clone(p['cells'][0]);child.update(id=uid(),name='empty_child');p['cells'].append(child)
        p['cells'][0]['devices']=[device('X','Xempty',cell=child['id'],nets={},array={'start':0,'end':127})]
        with patch('icstudio.layout_limits.MAX_FLAT_DEVICES',10):
            with self.assertRaisesRegex(ValueError,'occurrence'):flatten(p)
            with self.assertRaisesRegex(ValueError,'occurrence'):contexts(p,p['top'])
        with patch('icstudio.analysis_sources.MAX_FLAT_DEVICES',10):
            with self.assertRaisesRegex(ValueError,'occurrence'):source_names(p)


if __name__=='__main__':unittest.main()
