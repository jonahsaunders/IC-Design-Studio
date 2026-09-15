"""Cross-workflow numerical, identity, interpolation and budget regressions."""
import os
import tempfile
import unittest
from pathlib import Path
from icstudio.model import example,clone,device,validate,design_digest,file_digest
from icstudio import analog_guided as guided,analog_adaptive as adaptive,analog_characterization as lib,analog_optimizer as opt
from icstudio.specifications import evaluate_rows
from icstudio.simulation import run
from tests.test_analog_optimizer import mos_project,setup,prepare_job,search_spec,completed


def library_spec(**kw):
    return dict(length=['.5u','1u'],vgs=['.55','.65','.75','.85','.95'],vds=['1','1.8'],vsb=[0],temperature=[27],corner=['nominal'],**kw)


class GuidedTests(unittest.TestCase):
    def test_all_templates_produce_editable_valid_fixtures_with_real_measurements(self):
        for template in guided.TEMPLATES:
            p,cid=guided.teaching_example(example('empty'),template);before=clone(p);cell=next(c for c in p['cells'] if c['id']==cid)
            q,report=guided.generate(p,cid,dict(template=template,ports=guided.port_defaults(cell,template)))
            self.assertEqual(p,before);self.assertEqual(len(q['testbenches']),len(report['tests']))
            for entry in report['tests']:
                fixture=next(c for c in q['cells'] if c['id']==entry['cell'])
                result=run(q,entry['cell'],entry['settings']);rows=evaluate_rows(fixture['specifications'],result)
                self.assertTrue(rows);self.assertTrue(all(not row['error'] for row in rows),rows)
            self.assertEqual(q['test_plans'][0]['entries'],report['tests'])

    def test_transient_settling_units_and_live_dut_reference(self):
        p,cid=guided.teaching_example(example('empty'),'amplifier');cell=next(c for c in p['cells'] if c['id']==cid)
        q,report=guided.generate(p,cid,dict(template='amplifier',ports=guided.port_defaults(cell,'amplifier'),values={'settling_max':'20u'}))
        e=report['tests'][-1];self.assertEqual(e['settings']['type'],'tran');r=run(q,e['cell'],e['settings'])
        rows=evaluate_rows(next(c for c in q['cells'] if c['id']==e['cell'])['specifications'],r)
        self.assertFalse(rows[0]['error'],rows);self.assertGreaterEqual(rows[0]['value'],0)
        before=run(q,report['tests'][0]['cell'],report['tests'][0]['settings'])['operating_point']['vout']
        opt.set_target(q,cid,'M1.params.w','4u')
        after=run(q,report['tests'][0]['cell'],report['tests'][0]['settings'])['operating_point']['vout']
        self.assertNotEqual(before,after)

    def test_generated_legacy_testbench_retains_supply_current_for_power(self):
        from icstudio.testbenches import deck
        p,cid=guided.teaching_example(example('empty'),'current_mirror');c=next(c for c in p['cells'] if c['id']==cid)
        q,_=guided.generate(p,cid,dict(template='current_mirror',ports=guided.port_defaults(c,'current_mirror')))
        text=deck(q,q['testbenches'][0],'dut.spice')
        from icstudio.interchange import spice_name
        fixture=next(c for c in q['cells'] if c['id']==q['testbenches'][0]['bench_cell'])
        for d in fixture['devices']:
            if d['name'] in ('VDD','VLOAD'):self.assertIn('i('+spice_name(d)+')',text)

    def test_port_mapping_unused_bias_and_duplicate_names_are_checked(self):
        p,cid=guided.teaching_example(example('empty'),'amplifier');c=next(c for c in p['cells'] if c['id']==cid);roles=guided.port_defaults(c,'amplifier')
        with self.assertRaisesRegex(ValueError,'distinct'):guided.generate(p,cid,dict(template='amplifier',ports={**roles,'output':roles['input']}))
        q,_=guided.generate(p,cid,dict(template='amplifier',ports=roles))
        with self.assertRaisesRegex(ValueError,'already used'):guided.generate(q,cid,dict(template='amplifier',ports=roles))
        c['ports'].append('BIAS')
        with self.assertRaisesRegex(ValueError,'every remaining'):guided.generate(p,cid,dict(template='amplifier',ports=roles))


class AdaptiveTests(unittest.TestCase):
    def setUp(self):
        self.p=mos_project();self.plan=opt.source_plan(setup(self.p));self.spec=search_spec();self.spec.update(strategy='adaptive',budget=9);self.spec['axes'][0].update(count=11)

    def finish(self,m):
        rows=[]
        while True:
            done={r['job']['case']['index'] for r in rows};part={**m,'jobs':[j for j in m['jobs'] if j['case']['index'] not in done]};rows+=completed(part)
            if opt.evaluate(m,rows)['complete']:return m,rows
            m,jobs=adaptive.advance(m,rows,prepare_job)
            self.assertTrue(jobs)

    def test_sensitivity_first_then_adapts_without_overrunning_budget(self):
        self.spec['objective'].update(target='.94')
        m=opt.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job);self.assertEqual(len(m['jobs']),3)
        self.assertFalse(opt.evaluate(m,completed(m))['complete'])
        m,rows=self.finish(m);report=opt.evaluate(m,rows)
        self.assertEqual(len(m['jobs']),9);self.assertEqual(len({tuple(c) for c in m['adaptive']['coordinates']}),9)
        self.assertLess(report['best']['score'],.020001)
        sensitivity=adaptive.sensitivity(m,report)[0];self.assertAlmostEqual(sensitivity['slope'],1.);self.assertAlmostEqual(sensitivity['span_effect'],.4)
        self.assertEqual(self.p['cells'][0]['devices'][1]['value'],'0.8')

    def test_seed_budget_counts_conditions_before_engine_preparation(self):
        self.plan['temperatures']=[0,27,80];self.spec['budget']=8;calls=[]
        with self.assertRaisesRegex(ValueError,'at least 9'):opt.prepare(self.p,self.p['top'],self.plan,self.spec,lambda *a:calls.append(a))
        self.assertFalse(calls)

    def test_multiobjective_front_preserves_opposing_tradeoffs_and_dominance(self):
        self.spec.pop('strategy');self.spec['axes'][0]['count']=3
        self.spec['objectives']=[dict(entry_id='op',expression='final(V("g"))',unit='V',goal='minimize'),dict(entry_id='op',expression='final(V("g"))',unit='V',goal='maximize')]
        m=opt.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job);report=opt.evaluate(m,completed(m))
        self.assertEqual(report['pareto'],[1,2,3]);self.assertIsNone(report['best'])
        self.spec['objectives'][1]['goal']='minimize';m=opt.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job)
        self.assertEqual(opt.evaluate(m,completed(m))['pareto'],[1])

    def test_multiobjective_requires_every_metric_with_exact_units(self):
        self.spec['objectives']=[self.spec['objective'],dict(entry_id='op',expression='final(V("g"))',unit='A',goal='minimize')]
        m=opt.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job)
        self.assertFalse(opt.evaluate(m,completed(m))['pareto'])

    def test_resume_keeps_provenance_and_duplicate_free_proposals(self):
        m=opt.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job);rows=completed(m)
        a,jobs=adaptive.advance(m,rows,prepare_job);b,again=adaptive.advance(clone(m),clone(rows),prepare_job)
        self.assertEqual(a['adaptive']['coordinates'],b['adaptive']['coordinates'])
        self.assertEqual(jobs[0]['case']['group'],m['id']);self.assertEqual(jobs[0]['case']['candidate'],4)
        m['adaptive']['active']=False;paused,new=adaptive.advance(m,rows,prepare_job);self.assertEqual(paused,m);self.assertFalse(new)
        m['adaptive']['active']=True;rows[0]['state']='Interrupted';paused,new=adaptive.advance(m,rows,prepare_job)
        self.assertFalse(paused['adaptive']['active']);self.assertFalse(new)

    def test_failures_carry_exact_saved_requirement_and_run_links(self):
        self.p['cells'][0]['specifications']=[dict(name='Gate limit',expression='final(V("g"))',max='.5',unit='V')]
        m=opt.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job);r=opt.evaluate(m,completed(m))
        f=r['candidates'][0]['failure_details'][0];self.assertEqual(f['run_id'],'1');self.assertEqual(f['definition']['name'],'Gate limit')
        from icstudio.analog_debug import requirement_waveform
        self.assertEqual(requirement_waveform(completed(m)[0]['result'],f['definition'])['expression'],"V('g')")


class CharacterizationTests(unittest.TestCase):
    def setUp(self):self.p=mos_project()
    def table(self,spec=None,p=None):
        p=p or self.p;m=lib.prepare(p,p['top'],'M1',spec or library_spec(),prepare_job)
        return m,lib.collect(m,completed(m))

    def test_isolated_sweep_polarity_density_and_unmodified_design(self):
        for polarity in ('NMOS','PMOS'):
            p=mos_project(polarity);before=clone(p);m,t=self.table(p=p)
            self.assertEqual(p,before);self.assertTrue(t['complete']);self.assertEqual(len(t['points']),20)
            self.assertTrue(all(v['status']=='Passed' for v in t['points']))
            point=t['points'][0];self.assertAlmostEqual(point['values']['gmid'],2/(.55-.45),places=5)
            self.assertAlmostEqual(point['values']['current_density'],abs(point['values']['id'])/t['width'])
            self.assertEqual(point['values']['vgs']>0,polarity=='NMOS')

    def test_interpolation_and_inverse_sizing_preserve_units_and_no_extrapolation(self):
        m,t=self.table();query=dict(length=.75e-6,vgs=.7,vds=1.4,vsb=0,temperature=27,corner='nominal')
        point=lib.interpolate(t,query);self.assertTrue(point['interpolated']);self.assertEqual(len(point['run_ids']),8)
        estimates=lib.size(t,query,10,'10u');self.assertEqual(len(estimates),1);self.assertGreater(estimates[0]['width'],0)
        vgs=estimates[0]['vgs'];estimated=lib.interpolate(t,{**query,'vgs':vgs})
        self.assertAlmostEqual(estimated['current_density']*estimates[0]['width'],1e-5)
        with self.assertRaisesRegex(ValueError,'outside'):lib.interpolate(t,{**query,'length':2e-6})
        with self.assertRaisesRegex(ValueError,'bracketing'):lib.size(t,query,1000,'10u')
        t['points'][0]['status']='Failed'
        with self.assertRaisesRegex(ValueError,'neighboring'):lib.interpolate(t,{**query,'vgs':.6})

    def test_model_engine_and_grid_cache_identity_and_corruption(self):
        m,t=self.table()
        again=lib.prepare(clone(self.p),self.p['top'],'M1',library_spec(),prepare_job);self.assertEqual(m['library']['key'],again['library']['key'])
        p=clone(self.p);p['cells'][0]['devices'][0]['params']['kp']='250u'
        changed=lib.prepare(p,p['top'],'M1',library_spec(),prepare_job);self.assertNotEqual(m['library']['key'],changed['library']['key'])
        with tempfile.TemporaryDirectory() as directory:
            path=lib.save_cache(t,directory);self.assertEqual(lib.load_cache(t['key'],directory),t)
            path.write_text(path.read_text().replace('20.000000000', '30.000000000')+' ')
            import json
            corrupted=json.loads(path.read_text());corrupted['width']=99;path.write_text(json.dumps(corrupted))
            with self.assertRaisesRegex(ValueError,'changed'):lib.load_cache(t['key'],directory)

    def test_missing_or_mismatched_result_never_becomes_valid_library_sample(self):
        m,_=self.table();rows=completed(m);rows[0]['result']['device_operating_point']={};rows[1]['result']['design_hash']='wrong'
        t=lib.collect(m,rows);self.assertEqual(t['points'][0]['status'],'Failed');self.assertEqual(t['points'][1]['status'],'Failed')
        m['jobs'][0]['case']['fingerprint']='wrong';self.assertFalse(lib.collect(m,rows)['complete'])

    def test_limits_and_unsupported_teaching_conditions(self):
        for key,values in [('vsb',[.2]),('temperature',[80]),('corner',['tt']),('length',[0]),('vgs',[-1])]:
            spec=library_spec();spec[key]=values
            with self.assertRaises(ValueError):lib.prepare(self.p,self.p['top'],'M1',spec,prepare_job)
        spec=library_spec();spec['vgs']=list(range(100));spec['vds']=list(range(1,7))
        with self.assertRaisesRegex(ValueError,'500'):lib.prepare(self.p,self.p['top'],'M1',spec,prepare_job)

    def test_sky130_adapter_checks_real_locked_definition_units_and_multiplicity(self):
        p=clone(self.p);root=Path(__file__).resolve().parents[1]/'icstudio/assets/pdks/sky130A';model='sky130_fd_pr__nfet_01v8';rel='libs.ref/sky130_fd_pr/spice/'+model+'.pm3.spice'
        binding=dict(model=model,prefix='X',pin_order=['d','g','s','b'],parameter_scale={'w':1e6,'l':1e6},parameters={'nf':dict(default=1),'mult':dict(default=1)})
        p['pdk'].update(package_root=str(root),package_lock=dict(id='sky130A',revision='test',files={rel:file_digest(root/rel)}),simulation=dict(devices={'NMOS':binding}))
        c=lib.contract(p,p['top'],'M1');self.assertEqual(c['internal'],'m'+model);self.assertEqual(c['width'],2e-6)
        binding['parameters']['nf']['default']=2
        with self.assertRaisesRegex(ValueError,'single finger'):lib.contract(p,p['top'],'M1')
        binding['parameters']['nf']['default']=1;binding['parameter_scale']['w']=1
        with self.assertRaisesRegex(ValueError,'micrometre'):lib.contract(p,p['top'],'M1')

    @unittest.skipUnless(os.environ.get('ICSTUDIO_TEST_NGSPICE'),'Real ngspice qualification runs in desktop CI.')
    def test_real_engine_isolated_pmos_gmid_library(self):
        from icstudio.engines import run_ngspice
        p=mos_project('PMOS');executable=os.environ['ICSTUDIO_TEST_NGSPICE']
        def prepare(settings,engine,project,cid):return {**prepare_job(settings,engine,project,cid),'executable':executable}
        spec=library_spec(engine='ngspice');spec['length']=['1u'];spec['vds']=['1.8']
        m=lib.prepare(p,p['top'],'M1',spec,prepare);rows=[]
        with tempfile.TemporaryDirectory() as directory:
            for j in m['jobs']:
                result=run_ngspice(j['project'],j['cell'],j['settings'],executable,Path(directory)/str(j['case']['index']))
                rows.append(dict(id=str(j['case']['index']),job=j,state='Complete',result=result))
        t=lib.collect(m,rows);self.assertTrue(all(p['status']=='Passed' for p in t['points']),t)


class NativeFixtureTests(unittest.TestCase):
    def test_guided_native_root_model_scope_is_preserved_on_run_clone(self):
        from icstudio.native_analysis import deck
        p,cid=guided.teaching_example(example('empty'),'amplifier');p['spice']=dict(version=1,assets={})
        p['cells'][0]['spice_statements']=['.param fixture_proof=42']
        c=next(c for c in p['cells'] if c['id']==cid);q,r=guided.generate(p,cid,dict(template='amplifier',ports=guided.port_defaults(c,'amplifier'),engine='ngspice'))
        original=clone(q)
        with tempfile.TemporaryDirectory() as directory:
            text,_=deck(q,r['tests'][0]['cell'],r['tests'][0]['settings'],directory)
        self.assertEqual(q,original);self.assertEqual(text.count('.param fixture_proof=42'),1)
        self.assertLess(text.index('.param fixture_proof=42'),text.index('.subckt'))
        self.assertIn('.op',text)

    def test_real_catalog_fixture_uses_isolated_locked_library_and_explicit_vector_path(self):
        import json,sys
        from icstudio.catalog import create_device
        from icstudio.catalog_migration import catalog_signature
        from icstudio.operating_data import save_directive
        root=Path(__file__).resolve().parents[1]/'icstudio/assets/pdks/sky130A';package=json.loads((root/'package.json').read_text())
        p=example('empty');p['pdk']=package['technology'];p['pdk'].update(package_root=str(root),package_lock={k:package[k] for k in ('id','revision','files')})
        p['cells'][0]['devices']=[create_device(p['pdk'],'sky130_fd_pr/nfet_01v8.sym','M1')];p['cells'][0]['devices'][0]['model_ref']['instance_prefix']='X';p['spice']=dict(version=1,assets={})
        before=catalog_signature(p['pdk'])
        spec=library_spec(engine='ngspice');spec.update(length=['.15u'],vgs=['.6'],vds=['1.8'])
        def prepare(s,e,p,c):return {**prepare_job(s,e,p,c),'executable':sys.executable}
        m=lib.prepare(p,p['top'],'M1',spec,prepare);job=m['jobs'][0]
        self.assertEqual(catalog_signature(job['project']['pdk']),before);self.assertEqual(len(job['project']['cells']),1)
        self.assertNotIn('spice',job['project']);self.assertNotIn('instance_prefix',job['project']['cells'][0]['devices'][0]['model_ref']);directive,aliases=save_directive(job['project'],job['cell'])
        self.assertIn('@m.X_MCHAR.msky130_fd_pr__nfet_01v8[gm]',directive)
        self.assertIn('MCHAR',aliases.values())

    @unittest.skipUnless(os.environ.get('ICSTUDIO_TEST_NGSPICE'),'Real SKY130/ngspice qualification runs in desktop CI.')
    def test_real_sky130_polarities_body_temperature_corners_and_density(self):
        import json
        from icstudio.catalog import create_device
        from icstudio.engines import run_ngspice
        root=Path(__file__).resolve().parents[1]/'icstudio/assets/pdks/sky130A';package=json.loads((root/'package.json').read_text());executable=os.environ['ICSTUDIO_TEST_NGSPICE']
        def prepare(s,e,p,c):return {**prepare_job(s,e,p,c),'executable':executable}
        for polarity in ('nfet','pfet'):
            p=example('empty');p['pdk']=clone(package['technology']);p['pdk'].update(package_root=str(root),package_lock={k:package[k] for k in ('id','revision','files')})
            p['cells'][0]['devices']=[create_device(p['pdk'],'sky130_fd_pr/'+polarity+'_01v8.sym','M1')]
            spec=library_spec(engine='ngspice');spec.update(length=['.15u'],vgs=['.7'],vds=['1.0'],vsb=[0,.2],temperature=[27,80],corner=['tt','ss'])
            m=lib.prepare(p,p['top'],'M1',spec,prepare);rows=[]
            with tempfile.TemporaryDirectory() as directory:
                for j in m['jobs']:
                    result=run_ngspice(j['project'],j['cell'],j['settings'],executable,Path(directory)/str(j['case']['index']))
                    rows.append(dict(id=str(j['case']['index']),job=j,state='Complete',result=result))
            table=lib.collect(m,rows);self.assertTrue(all(p['status']=='Passed' for p in table['points']),table)
            self.assertGreater(len({p['values']['id'] for p in table['points']}),4)
            for point in table['points']:
                v=point['values'];self.assertGreater(v['gmid'],0);self.assertAlmostEqual(v['current_density']*table['width'],abs(v['id']))
                self.assertGreater(v['gds'],0);self.assertGreater(v['cgg'],0)
                self.assertAlmostEqual(v['intrinsic_gain'],abs(v['gm'])/v['gds'])
                self.assertGreater(v['ft_estimate'],0)
            point=table['points'][0];values=point['values']
            estimate=dict(width=table['width'],length=point['condition']['length'],condition=point['condition'],desired_current=abs(values['id']),desired_gmid=values['gmid'])
            verification=lib.prepare_verification(m,estimate,prepare);job=verification['jobs'][0]
            with tempfile.TemporaryDirectory() as directory:
                result=run_ngspice(job['project'],job['cell'],job['settings'],executable,Path(directory))
            verified=lib.verification_result(verification,[dict(id='verify',job=job,state='Complete',result=result)])
            self.assertEqual(verified['state'],'Verified',verified)

    @unittest.skipUnless(os.environ.get('ICSTUDIO_TEST_NGSPICE'),'Native guided testbench qualification runs in desktop CI.')
    def test_real_native_guided_saved_testbench(self):
        from icstudio.testbenches import simulate
        p,cid=guided.teaching_example(example('empty'),'amplifier');p['spice']=dict(version=1,assets={})
        cell=next(c for c in p['cells'] if c['id']==cid);q,_=guided.generate(p,cid,dict(template='amplifier',ports=guided.port_defaults(cell,'amplifier'),engine='ngspice'))
        with tempfile.TemporaryDirectory() as directory:
            for mode in ('native','legacy'):
                if mode=='legacy':q.pop('spice')
                for t in q['testbenches']:
                    r=simulate(q,t,os.environ['ICSTUDIO_TEST_NGSPICE'],Path(directory)/mode/t['name'])
                    self.assertTrue(all(row['status']=='PASS' for row in r['specifications']),r['specifications'])
                    self.assertEqual(r['design_hash'],design_digest(q))

if __name__=='__main__':unittest.main()
