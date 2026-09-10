"""Small, numerical contracts for the unified native workflow. No long benchmark."""
import hashlib, json, os, tempfile, unittest
from pathlib import Path
from icstudio.model import clone, digest, validate, design_digest, device
from icstudio.native_migration import review_path
from icstudio.native_exchange import export_project, review_project
from icstudio.native_analysis import corner_sections, dc_parameter, circuit_text
from icstudio.studies import targets, supply_targets, set_target, get_target, cases
from icstudio.electrical_identity import partition
from tests.test_native_migration import divider

ENGINE=os.environ.get('ICSTUDIO_TEST_NGSPICE','')


class NativeWorkflowTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def project(self,hierarchy=False,include=False):
        result=review_path(divider(self.root/'source',hierarchical=hierarchy,include=include))
        self.assertEqual(result['status'],'Complete',result['items']);return result['candidate']
    def run_analysis(self,p,typ='op',**settings):
        from icstudio.engines import run_ngspice
        out=self.root/('run'+str(len(list(self.root.glob('run*')))));out.mkdir()
        return run_ngspice(p,p['top'],{**p['analysis'],'type':typ,'source':'V1','output':'out','step':'10u','stop':'100u',**settings},ENGINE,out)

    def test_numeric_targets_exclude_inactive_fields_and_programs(self):
        p=self.project();values=targets(p,p['top'])
        self.assertIn('R1.native.value',values);self.assertIn('V1.native.dc_level',values)
        self.assertFalse(any(t.startswith('sim.') for t in values))
        self.assertEqual(supply_targets(p,p['top']),['V1.native.dc_level'])
        set_target(p,p['top'],'V1.native.dc_level',2)
        source=next(d for d in p['cells'][0]['devices'] if d['name']=='V1')
        self.assertEqual(dc_parameter(source),2);self.assertIn('ac 1',source['native_spice']['parameters']['value'].lower())

    def test_pvt_and_tolerances_on_migrated_devices(self):
        p=self.project();before=digest(p)
        self.assertEqual(len(cases(p,p['top'],{'kind':'pvt','target':'V1.native.dc_level','voltages':[1,2],'temperatures':[0,27],'corners':['nominal']})),4)
        spec={'kind':'monte_carlo','count':4,'seed':42,'variations':[{'target':'R1.native.value','relative_sigma':.05}]}
        self.assertEqual(cases(p,p['top'],spec),cases(p,p['top'],spec));self.assertEqual(digest(p),before)

    def test_graphical_deck_preserves_models_but_removes_control_effects(self):
        text='* test\n.control\nalter R1 99k\ntran 1n 5n\n.endc\n.include models/a.spice\n.tran 1u 2u\n+ 1u\n.param r=1k\n.end\n'
        clean=circuit_text(text);self.assertNotIn('alter',clean);self.assertNotIn('.tran',clean);self.assertNotIn('+',clean);self.assertIn('.include',clean);self.assertIn('.param',clean)
        with self.assertRaises(ValueError):circuit_text('.control\nop')

    def test_corner_intersection_is_from_actual_embedded_libraries(self):
        p=self.project();text='.lib tt\n.param r=1k\n.endl tt\n.lib ff\n.param r=2k\n.endl ff\n';ident='a'*24
        p['spice']['assets'][ident]={'name':'corners.spice','text':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}
        p['cells'][0]['spice_statements']=['.lib "models/'+ident+'.spice" tt']
        self.assertEqual(corner_sections(p),['ff','tt'])
        from icstudio.native_analysis import deck
        s={**p['analysis'],'type':'op','corner':'ff'};text,_=deck(p,p['top'],s,self.root/'deck')
        self.assertIn('.spice" ff',text)
        with self.assertRaises(ValueError):deck(p,p['top'],{**s,'corner':'missing'},self.root/'bad')

    def test_exchange_preserves_ids_geometry_specs_and_parameters(self):
        from icstudio.native_physical import bind
        from icstudio.parametric import install,audit
        p=self.project(include=True);c=p['cells'][0];d=next(d for d in c['devices'] if d['name']=='R1')
        binding={'kind':'R','terminals':dict(zip(('p','n'),d['symbol']['pin_order'])),'parameters':{'value':{'name':'value','scale':1}}}
        bind(p,c['id'],d['id'],binding);install(p,c['id'],d['id'],{'x':0,'y':0,'width':1000})
        c['specifications']=[{'name':'Output','expression':'final(V("out"))','min':0,'max':1,'unit':'V'}]
        output=export_project(p,self.root/'exchange');top=Path(output['directory'])/output['top']
        record=review_project(top);self.assertEqual(record['errors'],[]);q=record['candidate'];qc=next(x for x in q['cells'] if x['id']==c['id'])
        self.assertEqual(partition(qc),partition(c));self.assertEqual(qc['shapes'],c['shapes']);self.assertEqual(qc['specifications'],c['specifications'])
        self.assertEqual(next(x for x in qc['devices'] if x['id']==d['id'])['net_ids'],d['net_ids'])
        self.assertFalse(audit(q,c['id']))
        text=top.read_text();text=text.replace('value="1k"','value="3k"',1);top.write_text(text)
        changed=review_project(top);self.assertEqual(changed['errors'],[]);q=changed['candidate']
        self.assertEqual(get_target(q,c['id'],'R1.native.value'),3000);self.assertTrue(audit(q,c['id']))
        from icstudio.xschem_project import apply_review
        top.write_text(text+'\n')
        with self.assertRaisesRegex(ValueError,'changed after review'):apply_review(changed)

    def test_hierarchy_exchange_parameter_defaults(self):
        p=self.project(hierarchy=True);set_target(p,p['top'],'X1.native.r','3k')
        out=export_project(p,self.root/'exchange');record=review_project(Path(out['directory'])/out['top'])
        self.assertEqual(record['errors'],[]);q=record['candidate'];self.assertEqual(len(q['cells']),2)
        self.assertEqual(get_target(q,q['top'],'X1.native.r'),3000)
        child=next(c for c in q['cells'] if c['id']!=q['top']);self.assertEqual(child['spice_parameters']['r'],'1k')
        for c in q['cells']:self.assertEqual(partition(c),partition(next(old for old in p['cells'] if old['id']==c['id'])))

    def test_native_geometry_mapping_regenerates_with_stable_ids(self):
        from icstudio.native_physical import bind
        from icstudio.parametric import install,audit
        p=self.project();c=p['cells'][0];d=next(d for d in c['devices'] if d['name']=='R1');info=clone(d['native_spice'])
        binding={'kind':'R','terminals':dict(zip(('p','n'),d['symbol']['pin_order'])),'parameters':{'value':{'name':'value','scale':1}}}
        bind(p,c['id'],d['id'],binding);record=install(p,c['id'],d['id'],{'x':0,'y':0,'width':1000});ids=[s['id'] for s in c['shapes']];pins=[pin['id'] for pin in c['layout_pins']]
        self.assertEqual(d['native_spice'],info);set_target(p,c['id'],'R1.native.value','2k');self.assertTrue(audit(p,c['id']))
        record=install(p,c['id'],d['id'],record['spec']);self.assertEqual(ids,[s['id'] for s in c['shapes']]);self.assertEqual(pins,[pin['id'] for pin in c['layout_pins']]);self.assertFalse(audit(p,c['id']));self.assertEqual(record['electrical']['target'],2000);validate(p)
        with self.assertRaises(ValueError):bind(p,c['id'],d['id'],{**binding,'terminals':{'p':'p','n':'p'}})

    def test_klayout_report_reads_real_geometry_and_hierarchical_categories(self):
        import klayout.rdb as rdb
        import klayout.db as db
        from icstudio.klayout_verification import read_report
        r=rdb.ReportDatabase('test');r.top_cell_name='top';cell=r.create_cell('child');category=r.create_category('Metal');sub=r.create_category(category,'Width')
        item=r.create_item(cell.rdb_id(),sub.rdb_id());item.add_value(db.DBox(1,2,3,4));item.add_value('Too narrow')
        path=self.root/'report.lyrdb';r.save(str(path));report=read_report(path)
        self.assertEqual(report['count'],1);self.assertEqual(report['findings'][0]['cell'],'child');self.assertEqual(report['findings'][0]['boxes_um'],[[1,2,3,4]])

    @unittest.skipUnless(ENGINE,'Set ICSTUDIO_TEST_NGSPICE for numerical acceptance')
    def test_all_five_graphical_analyses_are_numerical(self):
        p=self.project()
        for typ in ('op','tran','dc','ac','noise'):
            with self.subTest(typ=typ):
                r=self.run_analysis(p,typ,points=5)
                self.assertTrue(r['traces']['out']);self.assertTrue(all(v>=0 for v in r['traces']['out']))
                if typ in ('op','tran','ac'):self.assertAlmostEqual(r['traces']['out'][-1],.5,places=8)
                if typ=='dc':self.assertAlmostEqual(r['traces']['out'][-1],.9,places=8)
                if typ=='noise':self.assertAlmostEqual(r['traces']['out'][-1],(4*1.380649e-23*300.15*500)**.5,delta=1e-14)

    @unittest.skipUnless(ENGINE,'Set ICSTUDIO_TEST_NGSPICE for numerical acceptance')
    def test_native_mos_returns_actual_operating_vectors(self):
        from icstudio.symbol_io import device_symbol
        p=self.project();c=p['cells'][0];source=next(d for d in c['devices'] if d['name']=='V1')
        from icstudio.wiring import set_label
        pin=next(pin for pin,n in source['nets'].items() if n!='0');set_label(c,source['id'],pin,'vin',p);vin='vin'
        d=device('NMOS','Mtest',500,500,nets={'d':'out','g':vin,'s':'0','b':'0'});symbol=device_symbol(d);symbol['pin_order']=['d','g','s','b'];d['symbol']=symbol;d['kind']='SPICE'
        d['native_spice']={'version':1,'type':'device','label':'testn','model_name':'testn','tokens':[{'kind':'instance'},{'kind':'literal','value':' '},{'kind':'terminals'},{'kind':'literal','value':' testn W=1u L=1u'}],'parameters':{},'definition':'.model testn nmos (level=1 vto=.4 kp=1m)'}
        d['net_labels']=dict(d['nets']);c['devices'].append(d);validate(p)
        r=self.run_analysis(p);values=r['device_operating_point']['Mtest'];self.assertGreater(values['gm'],0);self.assertGreater(values['id'],0);self.assertIn('headroom',values)

    @unittest.skipUnless(ENGINE,'Set ICSTUDIO_TEST_NGSPICE for numerical acceptance')
    def test_sensitivity_and_search_use_measured_results(self):
        from icstudio.variation_runs import prepare
        from icstudio.design_search import evaluate,apply_best
        from icstudio.specifications import attach
        p=self.project();c=p['cells'][0];c['specifications']=[{'name':'Output','expression':'final(V("out"))','min':0,'max':1,'unit':'V'}]
        job={'project':p,'cell':p['top'],'engine':'ngspice','executable':ENGINE,'settings':{**p['analysis'],'type':'op'}}
        for spec in ({'kind':'sensitivity','targets':['R1.native.value'],'relative_step':.01,'metric':'Output'},{'kind':'optimization','axes':[{'target':'R1.native.value','lower':1000,'upper':3000,'count':3}],'goal':'target','objective':.25,'metric':'Output'}):
            m=prepare(job,spec);rows=[]
            for j in m['jobs']:
                r=self.run_analysis(j['project']);attach(j,r);rows.append({'job':j,'state':'Complete','result':r})
            report=evaluate(m,rows);self.assertTrue(report['complete'])
            if spec['kind']=='sensitivity':self.assertAlmostEqual(report['sensitivities'][0]['normalized'],-.5,places=4)
            else:
                self.assertEqual(report['best']['case'],3);self.assertAlmostEqual(report['best']['value'],.25)
                q=clone(p);apply_best(q,m,rows);self.assertEqual(get_target(q,q['top'],'R1.native.value'),3000)
                with self.assertRaises(ValueError):apply_best(q,m,rows)
                with self.assertRaises(ValueError):apply_best(p,m,rows[:1])

    @unittest.skipUnless(ENGINE,'Set ICSTUDIO_TEST_NGSPICE for numerical acceptance')
    def test_exchanged_hierarchical_model_runs(self):
        p=self.project(hierarchy=True,include=True);set_target(p,p['top'],'X1.native.r','3k');out=export_project(p,self.root/'exchange');record=review_project(Path(out['directory'])/out['top']);self.assertEqual(record['errors'],[])
        r=self.run_analysis(record['candidate']);self.assertAlmostEqual(r['traces']['out'][0],.25)

    @unittest.skipUnless(ENGINE,'Set ICSTUDIO_TEST_NGSPICE for numerical acceptance')
    def test_native_distributed_rc_changes_waveform_with_same_requirements(self):
        from icstudio.model import load_project
        from icstudio.distributed_rc import compare_job
        p=load_project(Path(__file__).resolve().parents[1]/'examples/native-rc.icproj');validate(p)
        job={'project':p,'cell':p['top'],'engine':'ngspice','executable':ENGINE,'settings':{'type':'rc_compare','analysis':p['analysis']}}
        r=compare_job(p,job,self.root/'rc');self.assertEqual(len(r['rc_comparison']),1)
        self.assertNotEqual(r['before_waveform']['traces']['vout'],r['after_waveform']['traces']['vout'])
        from icstudio.wavecalc import evaluate
        before=evaluate('crossing(V("vout"),0.5,1)',r['before_waveform']).values[0]
        after=evaluate('crossing(V("vout"),0.5,1)',r['after_waveform']).values[0]
        self.assertGreater(after,before)


if __name__=='__main__':unittest.main()
