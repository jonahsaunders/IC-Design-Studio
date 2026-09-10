import unittest,tempfile,math,json,os,sys,subprocess
from pathlib import Path
from unittest.mock import patch
from icstudio.model import *
from icstudio.simulation import run,solve,Circuit
from icstudio.layout import rect,boolean,drc,generate_mos,polygon,kdb
from icstudio.interchange import export_layout,import_layout,export_handoff,spice
from icstudio.sdk import apply_commands

class ModelTests(unittest.TestCase):
    def test_atomic_save_failure_preserves_original(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'设计 with spaces.icproj';p=example();save_project(p,path);before=path.read_bytes();p['name']='changed'
            with patch('icstudio.model.os.replace',side_effect=OSError('interrupted save')):
                with self.assertRaises(OSError):save_project(p,path)
            self.assertEqual(path.read_bytes(),before);self.assertEqual(load_project(path)['name'],'RC low-pass')
    def test_undo_redo_and_invalid_transaction(self):
        h=History(example());name=h.project['name'];h.commit(lambda p:p.update(name='changed'));self.assertEqual(h.project['revision'],1);h.undo();self.assertEqual(h.project['name'],name);self.assertEqual(h.project['revision'],2);h.redo();self.assertEqual(h.project['name'],'changed')
        before=digest(h.project)
        with self.assertRaises(ValueError):h.commit(lambda p:p['cells'][0]['devices'][1].update(value='0'))
        self.assertEqual(digest(h.project),before)
    def test_revision_hash_waiver(self):
        p=example();h=design_digest(p);p['waivers'].append({'reason':'review only'});self.assertEqual(design_digest(p),h)
    def test_hierarchy_and_recursive_rejection(self):
        p=example();sub=clone(p['cells'][0]);sub['id']=uid();sub['name']='filter';sub['ports']=['vin','vout'];sub['devices']=sub['devices'][1:]
        for d in sub['devices']:d['id']=uid()
        p['cells'].append(sub);p['cells'][0]['devices']=p['cells'][0]['devices'][:1]+[device('X','X1',cell=sub['id'],nets={'vin':'vin','vout':'vout'})];validate(p);r=run(p,p['top'],{**p['analysis'],'type':'op'});self.assertIn('vout',r['traces']);self.assertIn('.subckt filter vin vout',spice(p))
        sub['devices'].append(device('X','Xrec',cell=sub['id'],nets={'vin':'vin','vout':'vout'}))
        with self.assertRaises(ValueError):validate(p)
    def test_export_rejects_case_aliases_and_bad_geometry(self):
        p=example();p['cells'][0]['devices'][1]['nets']['p']='VIN'
        with self.assertRaises(ValueError):validate(p)
        p=example();p['cells'][0]['shapes']=[{**rect('metal1',0,0,100,100),'holes':[[[0,0],[1,1],[2**32,0]]]}]
        with self.assertRaises(ValueError):validate(p)
    def test_schema_rejected(self):
        p=example();p['schema']=999
        with self.assertRaises(ValueError):validate(p)
    def test_command_batch_is_atomic(self):
        p=example();h=digest(p)
        with self.assertRaises(ValueError):apply_commands(p,[{'type':'add_shape','cell_id':p['top'],'shape':rect('unknown',0,0,10,10)}])
        self.assertEqual(digest(p),h)

class SolverTests(unittest.TestCase):
    def test_pivoted_matrix(self):self.assertEqual(solve([[0.,1.],[1.,1.]],[2.,3.]),[1.,2.])
    def test_python_fallback(self):
        with patch('icstudio.simulation.CORE',None):self.assertEqual(solve([[0.,1.],[1.,1.]],[2.,3.]),[1.,2.])
    def test_divider_op(self):
        p=example();c=p['cells'][0];c['devices'][0]['source']['type']='dc';c['devices'][2]=device('R','R2',nets={'p':'vout','n':'0'});r=run(p,p['top'],{**p['analysis'],'type':'op'});self.assertAlmostEqual(r['traces']['vout'][0],.9,places=7)
    def test_rc_ac_analytic(self):
        p=example();s={**p['analysis'],'type':'ac','start':'100','end':'1meg','points':101};r=run(p,p['top'],s)
        for f,v in zip(r['x'],r['traces']['vout']):self.assertAlmostEqual(v,1/math.sqrt(1+(2*math.pi*f*1e4*1e-9)**2),places=7)
    def test_rc_transient_analytic(self):
        p=example();d=p['cells'][0]['devices'][0];d['source'].update(period='1',delay='1u');s={**p['analysis'],'stop':'60u','step':'50n'};r=run(p,p['top'],s)
        for i,t in enumerate(r['x']):
            if t>=2e-6:self.assertLess(abs(r['traces']['vout'][i]-1.8*(1-math.exp(-(t-1e-6)/1e-5))),.012)
    def test_inverter_dc_rails(self):
        p=example('inverter');s={**p['analysis'],'type':'dc','dc_step':'0.03'};r=run(p,p['top'],s);self.assertGreater(r['traces']['vout'][0],1.79);self.assertLess(r['traces']['vout'][-1],.01)
    def test_resistor_thermal_noise(self):
        p=example();s={**p['analysis'],'type':'noise','start':'1','end':'10','points':2};r=run(p,p['top'],s);expected=math.sqrt(4*1.380649e-23*300.15*1e4);self.assertAlmostEqual(r['traces']['vout'][0]/expected,1,places=6)
    def test_bad_sweep_bounds(self):
        p=example()
        with self.assertRaises(ValueError):run(p,p['top'],{**p['analysis'],'step':'0'})
        with self.assertRaises(ValueError):run(p,p['top'],{**p['analysis'],'type':'dc','dc_step':'-0.01'})
    def test_voltage_source_loop_reports_error(self):
        p=example();c=p['cells'][0];c['devices'].append(device('V','V2',nets={'p':'vin','n':'0'}))
        with self.assertRaises(ValueError):run(p,p['top'],{**p['analysis'],'type':'op'})

class LayoutTests(unittest.TestCase):
    def test_boolean_area_and_hole(self):
        a=rect('metal1',0,0,1000,1000);b=rect('metal1',250,250,500,500);r=boolean([a,b],'subtract');self.assertEqual(sum(polygon(s).area() for s in r),750000);self.assertTrue(r[0]['holes'])
    def test_gds_oasis_geometry_xor(self):
        db=kdb();p=example();p['cells'][0]['shapes']=boolean([rect('metal1',0,0,2000,2000),rect('metal1',500,500,500,500)],'subtract')
        with tempfile.TemporaryDirectory() as td:
            for ext in ('.gds','.oas'):
                file=Path(td)/('design'+ext);export_layout(p,file);ly=db.Layout();ly.read(str(file));self.assertEqual(ly.dbu,.001);r=db.Region(ly.top_cell().begin_shapes_rec(ly.layer(4,0)));expected=db.Region()
                for s in p['cells'][0]['shapes']:expected.insert(polygon(s))
                self.assertTrue((r^expected).is_empty());restored,_=import_layout(file);self.assertEqual(digest(restored),digest(p))
    def test_external_edit_reconciles_sidecar(self):
        db=kdb();p=example();p['cells'][0]['shapes']=[rect('metal1',0,0,1000,1000)]
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'changed.gds';export_layout(p,file);ly=db.Layout();ly.read(str(file));ly.top_cell().shapes(ly.layer(4,0)).insert(db.Box(2000,2000,3000,3000));ly.write(str(file));r,w=import_layout(file)
            self.assertEqual(len(r['cells'][0]['shapes']),2)
            self.assertEqual(r['cells'][0]['devices'],p['cells'][0]['devices'])
            self.assertIn(p['cells'][0]['shapes'][0]['id'],[s['id'] for s in r['cells'][0]['shapes']])
            self.assertFalse(any(s.get('device_id') for s in r['cells'][0]['shapes']))
    def test_drc_width_space_grid(self):
        p=example();p['cells'][0]['shapes']=[rect('metal1',0,0,100,1000),rect('metal1',151,0,100,1000)];codes={v['code'] for v in drc(p,p['top'])};self.assertTrue({'WIDTH','SPACE','GRID'}<=codes)
    def test_handoff_includes_loss_report(self):
        p=example()
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'handoff';export_handoff(p,dest);self.assertTrue((dest/'simulation.cir').exists());report=json.loads((dest/'preservation-report.json').read_text());self.assertIn('arbitrary-design DRC/LVS and extraction correctness',report['not_qualified']);self.assertIn('fabrication signoff',report['not_qualified'])
            with self.assertRaises(ValueError):export_handoff(p,dest)

if __name__=='__main__':unittest.main()
