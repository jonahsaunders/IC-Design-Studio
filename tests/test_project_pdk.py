import json,tempfile,unittest
from pathlib import Path
from icstudio.model import example,device,clone,uid,History,save_project,load_project,file_digest
from icstudio.catalog import create_device,link_technology,numeric_formula
from icstudio.pdks import PDKRegistry
from icstudio.interchange import spice,export_xschem,import_layout,export_layout
from icstudio.xschem_io import import_package
from icstudio.project_manager import ProjectIndex,delete_cell
from icstudio.project_store import save_directory
from icstudio.symbol_io import symbol_text,import_symbol
from icstudio.spice_import import import_spice

class ProjectPDKTests(unittest.TestCase):
    def technology(self,root):
        (root/'models.lib').write_text('.subckt nmos_a d g s b w=1 l=1\nR1 d s 1k\n.ends\n.subckt nmos_b d g s b w=1 l=1\nR2 d s 2k\n.ends\n')
        tech=example('empty')['pdk'];tech['simulation']={'includes':[{'path':'models.lib'}],'devices':{},'catalog':{}}
        for model in ('nmos_a','nmos_b'):
            tech['simulation']['catalog'][model]={'kind':'NMOS','label':model,'model':model,'pin_order':['d','g','s','b'],'prefix':'X','parameter_scale':{'w':1e6,'l':1e6},'parameters':{'w':{'default':'1','positive':True},'l':{'default':'.15','positive':True}},'emit_parameters':{'w':'w','l':'l'}}
        manifest={'schema':1,'id':'test_pdk','revision':'r1','technology':tech,'files':{'models.lib':file_digest(root/'models.lib')}};(root/'package.json').write_text(json.dumps(manifest));r=PDKRegistry(root/'registry');key=r.install(root/'package.json');return r.technology(key)
    def test_distinct_models_history_hierarchy_and_xschem(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);tech=self.technology(root);p=example('empty');p['pdk']=tech;c=p['cells'][0]
            c['devices']=[create_device(tech,k,'MN'+str(i),i*300,100) for i,k in enumerate(('nmos_a','nmos_b'))]
            c['devices'][1]['params']['w']='3u';h=History(p);h.commit(lambda q:q['cells'][0]['devices'][0]['params'].update(w='2u'));h.undo();h.redo();text=spice(h.project);self.assertIn('nmos_a w=2 l=0.15',text);self.assertIn('nmos_b w=3 l=0.15',text)
            save_project(h.project,root/'c.icproj');q=load_project(root/'c.icproj');self.assertEqual(q['cells'][0]['devices'][1]['model_ref']['device'],'nmos_b');export_xschem(q,root/'x');r,_=import_package(root/'x');self.assertEqual([d['model_ref'] for d in r['cells'][0]['devices']],[d['model_ref'] for d in q['cells'][0]['devices']]);self.assertAlmostEqual(float(r['cells'][0]['devices'][1]['params']['w']),3e-6)
    def test_changed_models_and_revision_fail_visibly(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);tech=self.technology(root);p=example('empty');p['pdk']=tech;p['cells'][0]['devices']=[create_device(tech,'nmos_a','M1')]
            other=clone(tech);other['package_lock']['revision']='r2'
            with self.assertRaisesRegex(ValueError,'different PDK'):link_technology(p,other)
            (Path(tech['package_root'])/'models.lib').write_text('changed')
            with self.assertRaisesRegex(ValueError,'missing or changed'):spice(p)
    def test_layout_link_cannot_silently_change_mask_numbers(self):
        from icstudio.layout import rect
        p=example('empty');p['cells'][0]['shapes']=[rect('metal1',0,0,100,100)];other=clone(p['pdk']);other['layers'][3]['gds']=99
        with self.assertRaisesRegex(ValueError,'mapping'):link_technology(p,other)
    def test_project_delete_restore_is_recoverable_and_leaves_other_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=example();path=root/'project.icproj';save_project(p,path);other=root/'notes.txt';other.write_text('keep');index=ProjectIndex(root/'index');index.remember(p,path);record=index.trash(path,file_digest(path));self.assertFalse(path.exists());self.assertTrue(other.exists());self.assertEqual(len(index.deleted()),1);index.restore(record);self.assertEqual(load_project(path)['id'],p['id']);self.assertEqual(other.read_text(),'keep')
    def test_project_folder_delete_restores_manifest_and_cell_snapshots(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=example();path=save_directory(p,root/'design');index=ProjectIndex(root/'index');record=index.trash(path);self.assertTrue((path.parent/'cells').exists());index.restore(record);self.assertEqual(load_project(path)['id'],p['id'])
    def test_delete_cell_prevents_dangling_hierarchy(self):
        p=example('empty');c={'id':uid(),'name':'child','ports':['a'],'devices':[],'shapes':[]};p['cells'].append(c);p['cells'][0]['devices'].append(device('X','X1',cell=c['id'],nets={'a':'a'}))
        with self.assertRaisesRegex(ValueError,'used by'):delete_cell(p,c['id'])
        p['cells'][0]['devices']=[];delete_cell(p,c['id']);self.assertEqual(len(p['cells']),1)
    def test_formula_interpreter_handles_pdk_geometry_without_execution(self):
        self.assertAlmostEqual(numeric_formula('int((nf+1)/2) * W/nf * 0.18u',{'nf':1,'w':1e-6}),.18e-12)
        with self.assertRaises(ValueError):numeric_formula('__import__("os").getcwd()',{})
    def test_symbol_static_roundtrip(self):
        symbol={'pins':{'in':[-60,0],'out':[60,0]},'primitives':[{'kind':'line','points':[[-40,-30],[40,0]]},{'kind':'rect','points':[[-20,-10],[20,10]]}]}
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'custom.sym';path.write_text(symbol_text(symbol));result,_,_=import_symbol(path);self.assertEqual(result["pins"],symbol["pins"]);self.assertEqual(result["primitives"],symbol["primitives"]);self.assertEqual(result["pin_order"],["in","out"])
    def test_spice_roundtrip_keeps_models_and_hierarchy(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=example('inverter');path=root/'design.cir';path.write_text(spice(p,settings=p['analysis']));q,_=import_spice(path);self.assertEqual(len(q['cells'][0]['devices']),len(p['cells'][0]['devices']));self.assertEqual(q['analysis']['type'],'tran')
            path.write_text('* unsupported\nB1 out 0 V=sin(time)\n.end\n')
            with self.assertRaisesRegex(ValueError,'Unsupported SPICE device'):import_spice(path)
    def test_gds_external_hierarchy_arrays_and_text_roundtrip(self):
        import klayout.db as db
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);ly=db.Layout();ly.dbu=.001;top=ly.create_cell('top');child=ly.create_cell('child');layer=ly.layer(9,2);child.shapes(layer).insert(db.Box(0,0,500,600));child.shapes(layer).insert(db.Text('terminal',db.Trans(20,30)));top.insert(db.CellInstArray(child.cell_index(),db.Trans(1,True,1000,2000),db.Vector(2000,300),db.Vector(400,3000),2,3));path=root/'external.gds';ly.write(str(path));p,_=import_layout(path);self.assertEqual(len(p['cells']),2);c=next(c for c in p['cells'] if c['id']==p['top']);self.assertEqual(c['layout_instances'][0]['a'],[2000,300]);self.assertTrue(c['layout_instances'][0]['mirror']);out=root/'roundtrip.gds';export_layout(p,out);r=db.Layout();r.read(str(out));self.assertTrue((db.Region(r.top_cell().begin_shapes_rec(r.layer(9,2)))^db.Region(top.begin_shapes_rec(layer))).is_empty());self.assertEqual(len(list(r.cell('child').shapes(r.layer(9,2)).each())),2)
