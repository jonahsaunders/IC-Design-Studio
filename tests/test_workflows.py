import unittest,tempfile,json,math
from pathlib import Path
from unittest.mock import patch
from icstudio.model import example,clone,device,uid,validate,flatten,digest,design_digest,save_project,load_project,file_digest
from icstudio.studies import run_study,measure,cases
from icstudio.project_store import save_directory,load_directory
from icstudio.design_ops import bus_nets,connect_bus,value,flatten_layout,verilog
from icstudio.physical import route,erase,recipe_cell,regenerate,connectivity,capacitance_estimate,with_parasitics
from icstudio.layout import rect,polygon,kdb
from icstudio.interchange import spice,export_layout
from icstudio.simulation import run
from icstudio.pdks import PDKRegistry,model_lines
from icstudio.import_review import propose_layout_change
from icstudio.spatial import SpatialIndex

def physical_rc():
    p=example();c=p['cells'][0];c['shapes']=[rect('metal1',0,y,4000,400,net=net) for y,net in [(1000,'vin'),(3000,'vout'),(5000,'0')]]
    r,cap=c['devices'][1:];c['layout_pins']=[{'id':uid(),'device_id':d['id'],'pin':pin,'layer':'metal1','point':point} for d,pin,point in [(r,'p',[1000,1200]),(r,'n',[1000,3200]),(cap,'p',[3000,3200]),(cap,'n',[3000,5200])]]
    p['pdk']['parasitics']={'metal1':{'cap_f_per_um2':1e-14,'edge_f_per_um':1e-16}};return p

class WorkflowTests(unittest.TestCase):
    def test_parameterized_hierarchy_resolves_overrides(self):
        p=example('empty');top=p['cells'][0];sub={'id':uid(),'name':'load','ports':['p','n'],'parameters':{'resistance':'10k'},'devices':[device('R','R1',value='{resistance * 2}',nets={'p':'p','n':'n'})],'shapes':[]};p['cells'].append(sub);top['devices']=[device('V','V1',nets={'p':'vdd','n':'0'}),device('X','X1',cell=sub['id'],nets={'p':'vdd','n':'0'},parameters={'resistance':'5k'})];validate(p)
        self.assertEqual(float(flatten(p)[1]['value']),10000);self.assertIn('10000',spice(p));self.assertAlmostEqual(run(p,p['top'],{'type':'op'})['traces']['vdd'][0],1.8)
        top['devices'][1]['parameters']['resistance']='-1'
        with self.assertRaises(ValueError):validate(p)
    def test_expression_does_not_execute_code(self):
        for expression in ["{__import__('os').system('echo bad')}",'{(1).__class__}','{10**999999}']:
            with self.assertRaises(ValueError):value(expression)
        self.assertEqual(value('{r / 2}',{'r':1000}),500)
    def test_bus_connection_and_verilog(self):
        p=example('empty');c=p['cells'][0];c['devices']=[device('R','R'+str(i)) for i in range(4)];connect_bus(c,[d['id'] for d in c['devices']],'p','data[3:0]');validate(p)
        self.assertEqual(c['devices'][0]['nets']['p'],'data[3]');self.assertIn('\\data[3] ',verilog(p))
        with self.assertRaises(ValueError):bus_nets('data[500:0]')
    def test_sweep_is_immutable_and_changes_response(self):
        p=example();before=digest(p);settings={**p['analysis'],'type':'ac','start':'1000','end':'100000','points':10};spec={'kind':'sweep','target':'R1.value','values':['5k','10k','20k'],'measurement':{'trace':'vout','metric':'final'}}
        with tempfile.TemporaryDirectory() as td:r=run_study(p,p['top'],settings,spec,directory=td);self.assertTrue(all(Path(x['result_file']).is_file() for x in r['study_rows']))
        self.assertEqual(digest(p),before);self.assertGreater(r['traces']['vout'][0],r['traces']['vout'][-1]);self.assertEqual(r['design_hash'],design_digest(p))
    def test_monte_carlo_seed_and_sigma(self):
        p=example();spec={'kind':'monte_carlo','count':50,'seed':4,'variations':[{'target':'R1.value','relative_sigma':.05}]};a=cases(p,p['top'],spec);b=cases(p,p['top'],spec)
        self.assertEqual(a,b);self.assertNotEqual(a,cases(p,p['top'],{**spec,'seed':5}));self.assertTrue(all(7000<x[1]['R1.value']<13000 for x in a))
    def test_pvt_missing_corner_and_temperature_gate(self):
        p=example('inverter');spec={'kind':'pvt','target':'VDD.value','corners':['missing'],'voltages':[1.8],'temperatures':[27]}
        with self.assertRaises(ValueError):cases(p,p['top'],spec)
        with self.assertRaisesRegex(ValueError,'ngspice'):run(p,p['top'],{**p['analysis'],'type':'op','temperature':85})
        self.assertIn('.temp 85',spice(p,settings={**p['analysis'],'type':'op','temperature':85}))
    def test_bound_model_rejects_teaching_backend(self):
        p=example('inverter');p['pdk']['simulation']={'devices':{'NMOS':{'model':'foundry_n'}}}
        with self.assertRaisesRegex(ValueError,'ngspice'):run(p,p['top'],{'type':'op'})
    def test_unlabeled_conductors_use_extracted_terminal_net(self):
        p=physical_rc();expected=capacitance_estimate(p,p['top'])['capacitors']
        for s in p['cells'][0]['shapes']:s['net']=''
        self.assertEqual(capacitance_estimate(p,p['top'])['capacitors'],expected)
        p['cells'][0]['shapes'][0]['net']='wrong'
        self.assertIn('LVS.LABEL',{i['code'] for i in connectivity(p,p['top'])['issues']})
    def test_resistor_temperature_coefficient(self):
        p=example();c=p['cells'][0];c['devices'][0]['source']['type']='dc';c['devices'][2]=device('R','R2',nets={'p':'vout','n':'0'});c['devices'][1]['params']['tc1']='0.01'
        cold=run(p,p['top'],{'type':'op','temperature':27});hot=run(p,p['top'],{'type':'op','temperature':127})
        self.assertAlmostEqual(cold['traces']['vout'][0],.9,places=7);self.assertAlmostEqual(hot['traces']['vout'][0],.6,places=7)
    def test_directory_commit_failure_and_corruption(self):
        p=example()
        with tempfile.TemporaryDirectory() as td:
            save_directory(p,td);self.assertEqual(load_directory(td),p);q=clone(p);q['name']='edited'
            import icstudio.project_store as store
            write=store.atomic_write
            def fail(path,data):
                if Path(path).name=='project.icstudio':raise OSError('interrupted')
                return write(path,data)
            with patch('icstudio.project_store.atomic_write',side_effect=fail):
                with self.assertRaises(OSError):save_directory(q,td)
            self.assertEqual(load_directory(td),p)
            manifest=json.loads((Path(td)/'project.icstudio').read_text());(Path(td)/manifest['cell_files'][0]['path']).write_text('{}')
            with self.assertRaises(ValueError):load_directory(td)
    def test_pdk_pin_lock_verify_and_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)/'source';base.mkdir();(base/'model.spice').write_text('* test model\n');tech=example()['pdk'];tech['simulation']={'includes':[{'path':'model.spice'}]};manifest={'schema':1,'id':'test','revision':'1','technology':tech,'files':{'model.spice':file_digest(base/'model.spice')}};(base/'package.json').write_text(json.dumps(manifest));r=PDKRegistry(Path(td)/'registry');key=r.install(base/'package.json');locked=r.technology(key);self.assertIn('.include',model_lines(locked)[0]);self.assertEqual(r.install(base/'package.json'),key)
            from icstudio.interchange import export_handoff,import_layout
            import shutil
            bound=example();bound['pdk']=locked;handoff=Path(td)/'handoff';export_handoff(bound,handoff);moved=Path(td)/'moved';shutil.move(handoff,moved);reloaded=load_project(moved/'project.icproj')
            self.assertEqual(Path(reloaded['pdk']['package_root']),moved/'technology'/'package');self.assertTrue(model_lines(reloaded['pdk']));self.assertNotIn(str(Path(td)),(moved/'simulation.cir').read_text());physical,_=import_layout(moved/'layout.gds');self.assertEqual(physical['pdk']['package_root'],reloaded['pdk']['package_root'])
            (Path(locked['package_root'])/'model.spice').write_text('* tamper')
            with self.assertRaises(ValueError):model_lines(locked)
            with self.assertRaises(ValueError):r.verify(key)
    def test_generator_hierarchy_array_and_export(self):
        p=example('empty');child=recipe_cell('ring',{'kind':'guard_ring','width':3000,'height':3000,'thickness':300});p['cells'].append(child);p['cells'][0]['layout_instances']=[{'id':uid(),'name':'I1','cell':child['id'],'x':5000,'y':1000,'rotation':90,'nx':2,'ny':1,'dx':5000,'dy':0}];validate(p);shapes=flatten_layout(p,p['top']);self.assertEqual(len(shapes),8)
        db=kdb();expected=db.Region()
        for s in shapes:expected.insert(polygon(s))
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'hier.gds';export_layout(p,path);ly=db.Layout();ly.read(str(path));self.assertEqual(sum(1 for _ in ly.cell('top').each_inst()),1);actual=db.Region(ly.cell('top').begin_shapes_rec(ly.layer(4,0)));self.assertTrue((actual^expected).is_empty())
        old=child['shapes'][0]['points'];regenerate(child,{**child['generator']['spec'],'width':5000});self.assertNotEqual(old,child['shapes'][0]['points'])
        child['layout_instances']=[{'id':uid(),'name':'loop','cell':p['top'],'x':0,'y':0}]
        with self.assertRaises(ValueError):validate(p)
    def test_route_avoids_obstacle_and_erase_preserves_area(self):
        p=example('empty');c=p['cells'][0];c['shapes']=[rect('metal1',4000,-1000,2000,2000,net='other')];s=route(p,p['top'],'metal1',[0,0],[10000,0],400,'signal');self.assertGreater(len(s['points']),2);self.assertTrue((kdb().Region(polygon(s))&kdb().Region(polygon(c['shapes'][0])).sized(200)).is_empty())
        c['shapes']=[rect('metal1',0,0,1000,1000,net='a')];erase(c,'metal1',[250,250,750,750]);self.assertEqual(sum(polygon(s).area() for s in c['shapes']),750000);self.assertTrue(all(s['net']=='a' for s in c['shapes']))
    def test_connectivity_detects_real_shorts_and_opens(self):
        p=physical_rc();self.assertFalse(connectivity(p,p['top'])['issues']);p['cells'][0]['shapes'].append(rect('metal1',900,1000,400,2400));self.assertIn('LVS.SHORT',{i['code'] for i in connectivity(p,p['top'])['issues']})
        p=physical_rc();erase(p['cells'][0],'metal1',[1900,2900,2100,3500]);self.assertIn('LVS.OPEN',{i['code'] for i in connectivity(p,p['top'])['issues']})
    def test_extraction_stale_guard_and_post_layout_response(self):
        p=physical_rc();c=p['cells'][0];c['devices'][2]['value']='10f';s={**p['analysis'],'type':'ac','start':'1meg','end':'1g','points':10};ex=capacitance_estimate(p,p['top']);q=with_parasitics(p,p['top'],ex);before=run(p,p['top'],s);after=run(q,q['top'],s);self.assertLess(after['traces']['vout'][-1],before['traces']['vout'][-1]);p['revision']+=1
        with self.assertRaisesRegex(ValueError,'stale'):with_parasitics(p,p['top'],ex)
    def test_import_xor_review_and_no_silent_apply(self):
        p=physical_rc();before=digest(p)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'edit.gds';export_layout(p,path);q,report=propose_layout_change(p,path);self.assertEqual(q,p);db=kdb();ly=db.Layout();ly.read(str(path));ly.cell('top').shapes(ly.layer(4,0)).insert(db.Box(10000,0,11000,1000));ly.write(str(path));q,report=propose_layout_change(p,path);self.assertNotEqual(q,p);self.assertTrue(any('XOR area' in line for line in report));self.assertEqual(digest(p),before);self.assertEqual(q['cells'][0]['devices'],p['cells'][0]['devices'])
    def test_spatial_index_agrees_with_linear_query(self):
        entries=[((i*10,0,i*10+5,5),i) for i in range(2000)];index=SpatialIndex(entries);self.assertEqual(sorted(index.query((305,0,435,5))),list(range(30,44)))
    def test_xschem_continued_edit_import(self):
        from icstudio.interchange import export_xschem
        from icstudio.xschem_io import import_package
        p=example()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);export_xschem(p,root);file=root/'top.sch';text=file.read_text();file.write_text(text.replace('value="10k"','value="22k"'));q,report=import_package(root)
            self.assertEqual(q['cells'][0]['devices'][1]['value'],'22k');self.assertEqual(q['cells'][0]['devices'][1]['nets'],p['cells'][0]['devices'][1]['nets']);self.assertEqual(q['cells'][0]['devices'][0]['source']['type'],'pulse')
            file.write_text(text.replace('symbols/', 'unknown/').replace(p['cells'][0]['devices'][1]['id']+'.sym','unknown.sym'))
            with self.assertRaisesRegex(ValueError,'Unrecognized symbol'):import_package(root)

    def test_magic_extraction_profiles_are_distinct(self):
        from icstudio.engines import magic_extract
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);gds=root/'a.gds';tech=root/'tech';gds.write_bytes(b'fixture');tech.write_text('fixture');scripts=[]
            def fake(args,cwd,**kwargs):scripts.append(kwargs['input_text']);(Path(cwd)/'top.spice').write_text('* fixture');return 'fixture runner'
            with patch('icstudio.engines.execute',side_effect=fake):
                magic_extract('magic',gds,tech,'top',root/'lvs','lvs');magic_extract('magic',gds,tech,'top',root/'rc','rc')
            self.assertNotIn('extresist tolerance',scripts[0]);self.assertIn('extresist tolerance',scripts[1]);self.assertIn('ext2spice cthresh 0',scripts[1])

if __name__=='__main__':unittest.main()
