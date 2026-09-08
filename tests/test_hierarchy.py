import math,tempfile,unittest
from pathlib import Path
from icstudio.model import clone,validate,History,save_project,load_project,device
from icstudio.ring_oscillator import reference,generate
from icstudio.physical_cells import audit,terminals,transform_selection,ports
from icstudio.physical import connectivity
from icstudio.testbenches import measure,deck,native_subcircuit
from icstudio.sky130_layout import specification,generate_inverter
from icstudio.interchange import export_layout
from icstudio.import_review import propose_layout_change
from icstudio.layout import kdb
from test_silicon import technology


class HierarchyTests(unittest.TestCase):
    def design(self):
        p,cid,tbid=reference(technology());generate(p,cid);return p,cid,p['testbenches'][0]
    def test_saved_bench_survives_save_and_checks_references(self):
        p,cid,t=self.design()
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'saved.icproj';save_project(p,f);q=load_project(f);self.assertEqual(q['testbenches'],p['testbenches'])
        for change in (lambda q:q['testbenches'][0].update(dut_cell='missing'),lambda q:q['testbenches'][0]['initial_conditions'].update(unknown='1'),lambda q:q['testbenches'][0]['measurements'][0].update(node='missing'),lambda q:q['testbenches'][0]['analysis'].update(step='0')):
            q=clone(p);change(q)
            with self.assertRaises(ValueError):validate(q)
    def test_frequency_requires_settled_complete_cycles_and_obeys_limits(self):
        p,cid,t=self.design();t=clone(t);t['analysis'].update(stop='10n');t['measurements']=t['measurements'][:1];t['measurements'][0].update(start='2n',stop='10n',min_cycles=5)
        xs=[i*1e-11 for i in range(1001)];ys=[.9+.9*math.sin(2*math.pi*x/1e-9) for x in xs];r={'x':xs,'traces':{'out':ys}}
        m=measure(r,t);self.assertEqual(m['status'],'passed');self.assertAlmostEqual(m['measurements'][0]['value']/1e9,1)
        self.assertEqual(measure({'x':xs,'traces':{'out':[.9]*len(xs)}},t)['status'],'failed');t['measurements'][0]['max']='500meg';self.assertEqual(measure(r,t)['status'],'failed')
    def test_before_after_use_same_configurable_fixture(self):
        p,cid,t=self.design();bench=next(c for c in p['cells'] if c['id']==t['bench_cell']);next(d for d in bench['devices'] if d['name']=='VDD')['value']='1.6';t['analysis']['temperature']='85';t['initial_conditions']['n2']='1.6'
        a=deck(p,t,'/tmp/schematic.spice');b=deck(p,t,'/tmp/extracted.spice',next(c['ports'] for c in p['cells'] if c['id']==cid))
        self.assertEqual(a.replace('schematic.spice','extracted.spice'),b);self.assertIn('DC 1.6',a);self.assertIn('.temp 85',a);self.assertIn('v(n2)=1.6',a);self.assertIn('.tran 2e-12 8e-09 uic',a)
        ref=native_subcircuit(p,cid);self.assertEqual(ref.count('sky130_fd_pr__nfet_01v8 w='),3);self.assertNotIn('.lib',ref)
    def test_nontransient_measurement_windows_and_descending_sweep(self):
        t={'analysis':{'type':'dc','stop':'8n'},'probes':['out'],'measurements':[{'name':'voltage','kind':'voltage','node':'out','at':'-0.5'},{'name':'range','kind':'range','node':'out','min':'-1','max':'1'}]}
        r=measure({'x':[1,0,-1],'traces':{'out':[1,0,-1]}},t);self.assertEqual(r['status'],'passed');self.assertEqual(r['measurements'][0]['value'],-.5);self.assertEqual(r['measurements'][1]['minimum'],-1)
        t['analysis']['type']='ac';t['measurements']=t['measurements'][1:];self.assertEqual(measure({'x':[10,1000],'traces':{'out':[1,.1]}},t)['status'],'passed')
    def test_physical_recipe_resolves_cell_parameter_defaults(self):
        p,cid,t=self.design();c=next(c for c in p['cells'] if c['name']=='inverter');c['parameters']={'wn':'1u','wp':'2u'}
        for d in c['devices']:d['params']['w']='{wn}' if d['kind']=='NMOS' else '{wp}'
        generate_inverter(p,c['id'],True);self.assertFalse(audit(p,cid));c['parameters']['wn']='1.5u';self.assertTrue(audit(p,cid))
    def test_hierarchy_connections_and_mapped_labels(self):
        p,cid,t=self.design();self.assertFalse(audit(p,cid));self.assertFalse(connectivity(p,cid)['issues']);self.assertEqual(len(terminals(p,cid)),12)
        c=next(c for c in p['cells'] if c['id']==cid);self.assertEqual(len(c['layout_instances']),3);self.assertEqual(len({i['cell'] for i in c['layout_instances']}),1)
    def test_instance_transform_moves_ports_and_undo_restores_connection(self):
        p,cid,t=self.design();c=next(c for c in p['cells'] if c['id']==cid);ident=c['layout_instances'][0]['id'];before=terminals(p,cid);h=History(p)
        h.commit(lambda p:transform_selection(p,cid,[ident],dx=10000,rotation=90,mirror=True),'Move/rotate/mirror');after=terminals(h.project,cid)
        for a,b in zip(before[:4],after[:4]):self.assertEqual(b['point'],[10000+a['point'][1],a['point'][0]])
        self.assertTrue(connectivity(h.project,cid)['issues']);self.assertFalse(any(i['code']=='LVS.UNLANDED' for i in connectivity(h.project,cid)['issues']));h.undo();self.assertEqual(terminals(h.project,cid),before);self.assertFalse(connectivity(h.project,cid)['issues'])
    def test_instance_parameter_variants_and_missing_placements_reported(self):
        p,cid,t=self.design();c=next(c for c in p['cells'] if c['id']==cid);c['layout_instances'].pop();self.assertTrue(any(i['code']=='LAYOUT.MISSING' for i in audit(p,cid)))
        p,cid,t=self.design();c=next(c for c in p['cells'] if c['id']==cid);child=next(c for c in p['cells'] if c['name']=='inverter');child['parameters']={'size':'1'};c['devices'][0]['parameters']={'size':'2'};self.assertTrue(any(i['code']=='LAYOUT.PARAMETERS' for i in audit(p,cid)))
    def test_multifinger_total_width_and_stale_geometry(self):
        p,cid,t=self.design();c=next(c for c in p['cells'] if c['name']=='inverter')
        for d in c['devices']:d['params']['w']='2u';d['model_params']['nf']='4'
        self.assertTrue(audit(p,cid));generate_inverter(p,c['id'],True);self.assertFalse(audit(p,cid));self.assertFalse(connectivity(p,c['id'])['issues'])
        for d in c['devices']:
            gates=[s for s in c['shapes'] if s.get('device_id')==d['id'] and s['layer']=='poly' and s['points'][1][0]-s['points'][0][0]==150]
            self.assertEqual(len(gates),4)
        c['devices'][0]['params']['w']='1u'
        with self.assertRaises(ValueError):specification(p['pdk'],c['devices'][0])
    def test_external_instance_move_preserves_identity_in_both_formats(self):
        for suffix in ('.gds','.oas'):
            p,cid,t=self.design();c=next(c for c in p['cells'] if c['id']==cid);old=c['layout_instances'][0]
            with tempfile.TemporaryDirectory() as td:
                f=Path(td)/('layout'+suffix);export_layout(p,f);q,_=propose_layout_change(p,f);self.assertEqual(q,p)
                db=kdb();ly=db.Layout();ly.read(str(f));i=next(i for i in ly.cell(c['name']).each_inst() if i.property(126)=='icstudio:'+old['id']);i.cplx_trans=db.ICplxTrans(1,90,False,old['x']+5000,old['y']);ly.write(str(f));q,notes=propose_layout_change(p,f);moved=next(i for cc in q['cells'] if cc['id']==cid for i in cc['layout_instances'] if i['id']==old['id']);self.assertEqual(moved['device_id'],old['device_id']);self.assertEqual(moved['rotation'],90);self.assertEqual(len(q['cells']),len(p['cells']))
    def test_magic_pin_datatype_retains_named_physical_interfaces(self):
        p,cid,t=self.design();db=kdb()
        # The test technology needs the same explicitly mapped pin layers as SKY130.
        for gds in (68,69):
            source=next(l for l in p['pdk']['layers'] if l['gds']==gds and l['datatype']==5);p['pdk']['layers'].append({**clone(source),'name':source['name']+'_pin','datatype':16})
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'magic-ports.gds';export_layout(p,f);ly=db.Layout();ly.read(str(f))
            for c in ly.each_cell():
                for gds in (68,69):
                    src=ly.layer(gds,5);dst=ly.layer(gds,16)
                    for s in list(c.shapes(src).each()):
                        if s.is_text():c.shapes(dst).insert(s.text);s.delete()
            ly.write(str(f));q,notes=propose_layout_change(p,f);self.assertFalse(audit(q,cid));self.assertFalse(connectivity(q,cid)['issues'])
            self.assertEqual(sorted(ports(q,cid),key=lambda r:r['name']),sorted(ports(p,cid),key=lambda r:r['name']))
    def test_whole_footprint_translation_keeps_terminal_assignments(self):
        p,cid,t=self.design();c=next(c for c in p['cells'] if c['name']=='inverter');d=c['devices'][0];ids=[s['id'] for s in c['shapes'] if s.get('generated_device')==d['id']];old=clone(c['layout_pins']);transform_selection(p,c['id'],ids,dx=500,dy=1000)
        for a,b in zip(old,c['layout_pins']):self.assertEqual(b['point'],[a['point'][0]+500,a['point'][1]+1000] if a['device_id']==d['id'] else a['point'])

if __name__=='__main__':unittest.main()
