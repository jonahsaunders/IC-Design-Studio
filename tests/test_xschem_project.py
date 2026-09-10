import unittest,tempfile,json
from pathlib import Path
from icstudio.model import clone,flatten,save_project,load_project,validate,scalar
from icstudio.xschem_project import review_schematic,apply_review,export_project
from icstudio.interchange import spice
from icstudio.simulation import run
from tests.xschem_fixtures import amplifier


class DirectXschemTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.path=amplifier(self.root/'input')
    def tearDown(self):self.tmp.cleanup()
    def project(self):
        r=review_schematic(self.path);self.assertEqual(r['errors'],[],r['errors']);return apply_review(r)
    def test_hierarchy_parameters_geometry(self):
        p=self.project();self.assertEqual(len(p['cells']),2);ds={d['name']:d for d in flatten(p)}
        self.assertEqual(ds['XAMP/RD']['nets'],{'p':'vdd','n':'vout'})
        self.assertEqual(scalar(ds['XAMP/RD']['value']),8000);self.assertAlmostEqual(scalar(ds['XAMP/M1']['params']['w']),12e-6)
        self.assertEqual(ds['XAMP/M1']['nets'],{'d':'vout','g':'vin','s':'0','b':'0'})
        self.assertEqual(next(d for c in p['cells'] for d in c['devices'] if d['name']=='RD')['symbol']['pins'],{'p':[0.,-30.],'n':[0.,30.]})
        self.assertEqual(p['analysis']['type'],'ac');self.assertEqual(scalar(ds['VDD']['source']['ac']),0)
    def test_export_reimport_and_simulation(self):
        p=self.project();out=self.root/'export';report=export_project(p,out);q=apply_review(review_schematic(out/report['top']))
        signature=lambda p:[(d['name'],d['kind'],d['nets'],d['value'],d['params'],d['source']) for d in flatten(p)]
        self.assertEqual(signature(p),signature(q))
        settings={**p['analysis'],'points':8,'end':'1meg'}
        a=run(p,p['top'],settings);b=run(q,q['top'],settings);self.assertEqual(a['traces'],b['traces'])
        text=(out/report['top']).read_text();self.assertIn('keep me',text);self.assertIn('dash=3',text)
        self.assertTrue(any('custom_note' in path.read_text() for path in out.rglob('*.sym')))
    def test_missing_dependency_and_stale_review(self):
        r=review_schematic(self.path);self.assertFalse(r['errors']);(self.path.parent/'models/nmos.spice').write_text('* changed')
        with self.assertRaisesRegex(ValueError,'changed after review'):apply_review(r)
        (self.path.parent/'devices/res.sym').unlink();r=review_schematic(self.path);self.assertIsNone(r['candidate']);self.assertTrue(any(d['status']=='Missing' for d in r['dependencies']))
    def test_model_edit_export(self):
        p=self.project();d=next(d for c in p['cells'] for d in c['devices'] if d['kind']=='NMOS');d['params']['kp']='150u';out=self.root/'out';r=export_project(p,out);q=apply_review(review_schematic(out/r['top']));self.assertEqual(scalar(next(d for c in q['cells'] for d in c['devices'] if d['kind']=='NMOS')['params']['kp']),150e-6)
    def test_saved_project_exports_without_source_files(self):
        p=self.project();save_project(p,self.root/'saved.icproj');import shutil;shutil.rmtree(self.path.parent);q=load_project(self.root/'saved.icproj');r=export_project(q,self.root/'out');self.assertTrue((self.root/'out'/r['top']).exists())
    def test_no_execution_and_unknown_models(self):
        text=self.path.read_text().replace('value=1.8','value="tcleval(exec touch NEVER)"');self.path.write_text(text);r=review_schematic(self.path);self.assertIsNone(r['candidate']);self.assertIn('Executable',' '.join(r['errors']));self.assertFalse((self.path.parent/'NEVER').exists())
    def test_edit_values_override_move_and_rewire(self):
        p=self.project();top=next(c for c in p['cells'] if c['id']==p['top']);amp=next(d for d in top['devices'] if d['kind']=='X');amp['parameters']['resistance']='6k';cap=next(d for d in top['devices'] if d['kind']=='C');cap['value']='2p'
        from icstudio.capture_ops import transform
        transform(p,top['id'],[amp['id']],20,40)
        validate(p);out=self.root/'edited';r=export_project(p,out);q=apply_review(review_schematic(out/r['top']));ds={d['name']:d for d in flatten(q)}
        self.assertEqual(scalar(ds['XAMP/RD']['value']),6000);self.assertEqual(scalar(ds['CL']['value']),2e-12)
        self.assertEqual(ds['XAMP/M1']['nets'],next(d for d in flatten(p) if d['name']=='XAMP/M1')['nets'])
    def test_reordered_primitive_format_and_pin_metadata(self):
        file=self.path.parent/'devices/voltage.sym';file.write_text(file.read_text().replace('@name @pinlist @value','@name @@M @@P @value'))
        p=self.project();d=next(d for d in flatten(p) if d['name']=='VDD');self.assertEqual(d['nets'],{'p':'0','n':'vdd'})
        out=self.root/'out';r=export_project(p,out);q=apply_review(review_schematic(out/r['top']));self.assertEqual(next(d for d in flatten(q) if d['name']=='VDD')['nets'],d['nets'])
    def test_symbol_edits_do_not_change_other_instances(self):
        p=self.project();top=next(c for c in p['cells'] if c['id']==p['top']);v=next(d for d in top['devices'] if d['name']=='VIN');v['symbol']['primitives'][0]['points'][0][0]-=5
        out=self.root/'out';r=export_project(p,out);q=apply_review(review_schematic(out/r['top']));top=next(c for c in q['cells'] if c['id']==q['top']);ds={d['name']:d for d in top['devices']}
        self.assertNotEqual(ds['VIN']['symbol']['primitives'][0],ds['VDD']['symbol']['primitives'][0])
    def test_external_library_root_and_recursive_hierarchy(self):
        import shutil
        library=self.root/'shared';library.mkdir();shutil.move(str(self.path.parent/'devices'),library/'devices');r=review_schematic(self.path);self.assertIsNone(r['candidate']);r=review_schematic(self.path,[library]);self.assertFalse(r['errors'],r['errors'])
        child=self.path.parent/'blocks/gain.sch';child.write_text(child.read_text()+'C {blocks/gain.sym} 0 0 0 0 {name=XLOOP}\n');r=review_schematic(self.path,[library]);self.assertIsNone(r['candidate']);self.assertIn('Recursive',' '.join(r['errors']))
    def test_unsupported_model_is_explicit(self):
        file=self.path.parent/'models/nmos.spice';file.write_text(file.read_text().replace('level=1','level=54'));r=review_schematic(self.path);self.assertIsNone(r['candidate']);self.assertIn('unsupported',' '.join(r['errors']).lower())
    def test_crossing_vs_t_junction(self):
        p=self.project();top=next(c for c in p['cells'] if c['id']==p['top']);from icstudio.wiring import graph,rebuild
        from icstudio.model import uid
        a,b=uid(),uid();top['wires'].extend([{'id':a,'points':[[700,100],[800,100]]},{'id':b,'points':[[750,50],[750,150]]}]);rebuild(top,p);g=graph(top,p,labels=False);self.assertNotEqual(g[('wire',a)],g[('wire',b)])
        out=self.root/'out';r=export_project(p,out);q=apply_review(review_schematic(out/r['top']));top=next(c for c in q['cells'] if c['id']==q['top']);ws=[w for w in top['wires'] if w['points'][0][0]>=700];g=graph(top,q,labels=False);self.assertNotEqual(g[('wire',ws[0]['id'])],g[('wire',ws[1]['id'])])
    def test_nested_property_quotes(self):
        from icstudio.xschem_project import properties,property_text
        raw=r'''template="name=C1 device=\\"ceramic capacitor\\"" comment="keep spaces"'''
        props=properties(raw);self.assertEqual(properties(props['template'])['device'],'ceramic capacitor')
        self.assertEqual(properties(property_text(props)),props)
    def test_standard_voltage_template_and_optional_mos_fields(self):
        voltage=self.path.parent/'devices/voltage.sym';text=voltage.read_text().replace('format="@name @pinlist @value"',r'''format="tcleval([expr \{@savecurrent ? \\"@name @pinlist @value
.save I( ?1 @name )\\" : \\"@name @pinlist @value \\"\}])"''').replace('name=V1 value=0','name=V1 value=0 savecurrent=false');voltage.write_text(text)
        mos=self.path.parent/'devices/nmos.sym';mos.write_text(mos.read_text().replace('@name @pinlist @model w=@w l=@l','@spiceprefix@name @pinlist @model w=@w l=@l @extra m=@m').replace('w=10u l=1u','w=10u l=1u m=1'))
        p=self.project();self.assertEqual(len(flatten(p)),5)
        out=self.root/'out';r=export_project(p,out);q=apply_review(review_schematic(out/r['top']));self.assertEqual(len(flatten(q)),5)
    def test_conflicting_labels_and_invalid_port_order(self):
        self.path.write_text(self.path.read_text()+'C {devices/label.sym} 100 70 0 0 {name=bad lab=wrong}\n');r=review_schematic(self.path);self.assertIsNone(r['candidate']);self.assertIn('conflicting',' '.join(r['errors']).lower())
        self.path=amplifier(self.path.parent);symbol=self.path.parent/'blocks/gain.sym';symbol.write_text(symbol.read_text().replace('sim_pinnumber=4','sim_pinnumber=1'));r=review_schematic(self.path);self.assertIsNone(r['candidate']);self.assertIn('sim_pinnumber',' '.join(r['errors']))
    def test_nonempty_export_is_protected(self):
        p=self.project();out=self.root/'out';out.mkdir();(out/'keep.txt').write_text('keep')
        with self.assertRaisesRegex(ValueError,'empty'):export_project(p,out)
        self.assertEqual((out/'keep.txt').read_text(),'keep')
    def test_native_specifications_physical_views_and_identity_survive(self):
        p=self.project();top=next(c for c in p['cells'] if c['id']==p['top']);from icstudio.layout import rect
        top['shapes']=[rect('metal1',0,0,400,400)];top['specifications']=[{'name':'Gain','expression':'max(V("vout"))','min':'.01','unit':'V'}];p['analysis'].update(type='op');ids={d['name']:d['id'] for d in top['devices']}
        out=self.root/'out';r=export_project(p,out);q=apply_review(review_schematic(out/r['top']));cell=next(c for c in q['cells'] if c['id']==q['top'])
        self.assertEqual(q['id'],p['id']);self.assertEqual(q['revision'],p['revision']+1);self.assertEqual(cell['shapes'],top['shapes']);self.assertEqual(cell['specifications'],top['specifications']);self.assertEqual(q['analysis']['type'],'op');self.assertEqual({d['name']:d['id'] for d in cell['devices']},ids)
    def test_native_metadata_tamper_is_visible(self):
        p=self.project();out=self.root/'out';r=export_project(p,out);file=out/'studio-project.icproj';file.write_text(file.read_text()+' ');r=review_schematic(out/r['top']);self.assertIsNone(r['candidate']);self.assertIn('metadata',' '.join(r['errors']))
    def test_linked_pdk_models_keep_their_binding(self):
        from tests.test_project_pdk import ProjectPDKTests
        assets=self.root/'technology';assets.mkdir();technology=ProjectPDKTests().technology(assets)
        symbol=self.path.parent/'devices/nmos.sym';symbol.write_text(symbol.read_text().replace('type=nmos','type=primitive').replace('@name @pinlist','X@name @pinlist'))
        child=self.path.parent/'blocks/gain.sch';child.write_text(child.read_text().replace('model=nch w=width l=1u','model=nmos_a w=2 l=0.15'))
        self.path.write_text(self.path.read_text().replace('.include models/nmos.spice','.include '+str(Path(technology['package_root'])/'models.lib')))
        record=review_schematic(self.path,technology=technology);self.assertFalse(record['errors'],record['errors']);p=apply_review(record);d=next(d for d in flatten(p) if d['kind']=='NMOS');self.assertEqual(d['model_ref']['device'],'nmos_a');self.assertAlmostEqual(scalar(d['params']['w']),2e-6)
        out=self.root/'out';r=export_project(p,out);q=apply_review(review_schematic(out/r['top']));self.assertEqual(next(d for d in flatten(q) if d['kind']=='NMOS')['model_ref'],d['model_ref'])
    def test_global_parameter_edits_export_and_reimport(self):
        self.path.write_text(self.path.read_text().replace('name=CL value=1p','name=CL value=loadcap').replace('.ac dec 20','.param loadcap=1p\n.ac dec 20'))
        p=self.project();p['parameters']['loadcap']='2p';out=self.root/'out';r=export_project(p,out);q=apply_review(review_schematic(out/r['top']));self.assertEqual(scalar(next(d for d in flatten(q) if d['name']=='CL')['value']),2e-12)
    def test_ground_alias_labels_join_zero(self):
        self.path.write_text(self.path.read_text()+'C {devices/label.sym} 100 130 0 0 {name=ground_alias lab=GND}\n')
        p=self.project();self.assertEqual(next(d for d in flatten(p) if d['name']=='VDD')['nets']['n'],'0')


if __name__=='__main__':unittest.main()
