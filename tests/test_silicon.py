import tempfile,unittest
from pathlib import Path
from icstudio.model import example,clone,digest,History,validate,uid
from icstudio.sky130_layout import MASKS,MODELS,reference_project,generate_inverter,install_mos,audit,specification
from icstudio.physical import connectivity
from icstudio.interchange import export_layout
from icstudio.import_review import propose_layout_change
from icstudio.layout import kdb,rect


def technology():
    t=example('empty')['pdk'];t['package_lock']={'id':'sky130A','revision':'fixture','files':{}};t['revision']='fixture';t['grid']=5
    t['layers']=[{'name':k,'gds':v[0],'datatype':v[1],'color':'#68a6f4','width':0,'space':0} for k,v in MASKS.items()]
    t['simulation']={'catalog':{kind:{'kind':kind,'label':kind,'model':model,'prefix':'X','pin_order':['d','g','s','b'],'parameters':{'w':{'default':'1','positive':True},'l':{'default':'.15','positive':True},'nf':{'default':'1','positive':True,'integer':True}},'parameter_scale':{'w':1e6,'l':1e6},'emit_parameters':{'w':'w','l':'l','nf':'nf'}} for kind,model in MODELS.items()}}
    return t


class SiliconTests(unittest.TestCase):
    def design(self):
        p,cid=reference_project(technology());generate_inverter(p,cid);return p,cid,next(c for c in p['cells'] if c['id']==cid)

    def test_generator_terminal_connectivity_and_real_masks(self):
        p,cid,c=self.design();self.assertFalse(connectivity(p,cid)['issues']);self.assertFalse(audit(p,cid));self.assertEqual(len(c['layout_pins']),8)
        self.assertEqual({t['text'] for t in c['layout_texts']},set(c['ports']));self.assertEqual(c['layout_label_mode'],'explicit')
        for d in c['devices']:
            poly=[s for s in c['shapes'] if s.get('device_id')==d['id'] and s['layer']=='poly'][0]
            self.assertEqual(poly['points'][1][0]-poly['points'][0][0],150)

    def test_dimensions_regeneration_and_undo(self):
        p,cid,c=self.design();h=History(p);did=c['devices'][0]['id']
        h.commit(lambda q:next(c for c in q['cells'] if c['id']==cid)['devices'][0]['params'].update(w='1.5u'),'Resize MOS')
        self.assertTrue(audit(h.project,cid));before=clone(h.project)
        h.commit(lambda q:generate_inverter(q,cid,True),'Regenerate');self.assertFalse(audit(h.project,cid));self.assertFalse(connectivity(h.project,cid)['issues']);h.undo();self.assertEqual(h.project['cells'],before['cells'])

    def test_refuse_wrong_family_variants_and_non_grid(self):
        p,cid,c=self.design();d=c['devices'][0]
        for params,extra in [({'w':'1.001u'},{}),({}, {'nf':3})]:
            q=clone(d);q['params'].update(params);q['model_params'].update(extra)
            with self.assertRaises(ValueError):specification(p['pdk'],q)
        t=clone(p['pdk']);t['package_lock']['id']='gf180mcuC'
        with self.assertRaises(ValueError):specification(t,d)
        with self.assertRaises(ValueError):generate_inverter(p,cid)

    def test_open_short_and_guidance(self):
        p,cid,c=self.design();c['shapes']=[s for s in c['shapes'] if not(s.get('generated_route') and s['net']=='Y')]
        result=connectivity(p,cid);self.assertTrue(any(i['code']=='LVS.OPEN' for i in result['issues']));self.assertEqual(len(result['guides']),1);self.assertEqual(result['guides'][0]['net'],'Y')
        p,cid,c=self.design();c['shapes'].append(rect('m1',-2500,0,4500,9000))
        self.assertTrue(any(i['code']=='LVS.SHORT' for i in connectivity(p,cid)['issues']))

    def test_import_edits_preserve_hierarchy_and_apply_labels(self):
        p,cid,c=self.design();top=p['cells'][0];top['layout_instances']=[{'id':uid(),'name':'DUT','cell':cid,'x':20000,'y':0,'rotation':90,'nx':2,'ny':1,'a':[20000,0],'b':[0,0]}]
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'edit.oas';export_layout(p,f);q,report=propose_layout_change(p,f);self.assertEqual(q,p)
            db=kdb();ly=db.Layout();ly.read(str(f));cell=ly.cell(c['name']);cell.shapes(ly.layer(*MASKS['m1'])).insert(db.Box(9000,0,9500,500));cell.shapes(ly.layer(*MASKS['m1label'])).insert(db.Text('probe',db.Trans(9250,250)));ly.write(str(f))
            q,report=propose_layout_change(p,f);self.assertEqual(q['cells'][0]['layout_instances'],top['layout_instances']);self.assertEqual(next(cc for cc in q['cells'] if cc['id']==cid)['devices'],c['devices']);self.assertTrue(any(t['text']=='probe' for t in next(cc for cc in q['cells'] if cc['id']==cid)['layout_texts']));self.assertTrue(any('XOR area' in s for s in report))

    def test_missing_tool_reports_blocked_with_no_false_success(self):
        from icstudio.silicon_flow import run
        p,cid,c=self.design()
        with tempfile.TemporaryDirectory() as td:
            r=run(p,cid,td,{});self.assertEqual(r['status'],'blocked');self.assertEqual(r['stages'][0]['status'],'failed');self.assertTrue(all(s['status']=='not_run' for s in r['stages'][1:]));self.assertTrue((Path(td)/'report.json').is_file())

    def test_xschem_parameterized_component_exchange(self):
        from icstudio.model import load_project,flatten
        from icstudio.interchange import export_xschem
        from icstudio.xschem_io import import_package
        p=load_project(Path(__file__).resolve().parents[1]/'examples/reusable-divider.icproj')
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);export_xschem(p,out);q,_=import_package(out)
            self.assertEqual([(d['name'],d['value'],d['nets']) for d in flatten(q)],[(d['name'],d['value'],d['nets']) for d in flatten(p)])
            f=out/'top.sch';f.write_text(f.read_text().replace('ratio="2"','ratio="3"'));q,_=import_package(out)
            self.assertEqual(next(d['value'] for d in flatten(q) if d['name'].endswith('/R1')),'30000.0')

if __name__=='__main__':unittest.main()
