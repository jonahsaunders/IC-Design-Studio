"""Analytic numerical checks and measured-evidence contracts for six extensions."""
import math
import os
import statistics
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import clone,device,example,validate,design_digest
from icstudio import analog_optimizer as opt,analog_adaptive as adaptive,analog_sensitivity as sensitivity
from icstudio import analog_bayesian as bayes,analog_robustness as robust,analog_automation as automation
from icstudio import analog_diagnostics as diagnostic,analog_fidelity as fidelity
from tests.test_analog_optimizer import mos_project,setup,prepare_job,search_spec,completed


def rc_project():
    p=example('empty');c=p['cells'][0]
    c['devices']=[device('V','V1',value='1',nets={'p':'in','n':'0'}),device('R','R1',value='1k',nets={'p':'in','n':'out'}),
        device('R','R2',value='1k',nets={'p':'out','n':'0'}),device('C','C1',value='1n',nets={'p':'out','n':'0'})]
    c['devices'][0]['source']['ac']='1';validate(p);return p


class SensitivityTests(unittest.TestCase):
    def test_morris_linear_effect_and_seed(self):
        d=sensitivity.design([21,21],'morris',40,72)
        self.assertEqual(d,sensitivity.design([21,21],'morris',40,72))
        values={i+1:2*p[0]/20+3*p[1]/20 for i,p in enumerate(d['coordinates'])}
        for b in d['blocks']:self.assertAlmostEqual((values[b['after']]-values[b['before']])/b['dx'],[2,3][b['axis']])

    def test_sobol_additive_and_interaction_known_indices(self):
        d=sensitivity.design([101,101],'sobol',4096,72)
        additive={i+1:p[0]/100+2*p[1]/100 for i,p in enumerate(d['coordinates'])}
        for axis,expected in enumerate((.2,.8)):
            first,total=sensitivity.indices(d['blocks'],additive,axis);self.assertAlmostEqual(first,expected,delta=.04);self.assertAlmostEqual(total,expected,delta=.04)
        product={i+1:(p[0]/50-1)*(p[1]/50-1) for i,p in enumerate(d['coordinates'])}
        for axis in (0,1):
            first,total=sensitivity.indices(d['blocks'],product,axis);self.assertAlmostEqual(first,0,delta=.08);self.assertAlmostEqual(total,1,delta=.08)
        self.assertIsNone(sensitivity.indices(d['blocks'],{i:1 for i in product},0))

    def test_real_samples_missing_evidence_and_pvt_budget(self):
        p=mos_project();plan=opt.source_plan(setup(p));spec=search_spec();m=sensitivity.prepare(p,p['top'],plan,spec,prepare_job)
        rows=completed(m);result=sensitivity.analyze(m,rows);self.assertEqual(result['rows'][0]['status'],'Complete')
        rows[0]['state']='Failed';self.assertEqual(sensitivity.analyze(m,rows)['rows'][0]['status'],'Incomplete')
        plan['temperatures']=[0,27,80];spec['budget']=2
        with self.assertRaisesRegex(ValueError,'simulations'):sensitivity.prepare(p,p['top'],plan,spec,prepare_job)


class BayesianTests(unittest.TestCase):
    def test_gp_training_uncertainty_and_constant_output(self):
        x=[[i/6,j/6] for i in range(4) for j in range(4)];y=[math.sin(4*a)+.1*b for a,b in x];g=bayes.FittedGP(x,y)
        for point,value in zip(x,y):
            mean,sd=g.predict(point);self.assertAlmostEqual(mean,value,delta=.003);self.assertLess(sd,.003)
        self.assertTrue(all(math.isfinite(v) for v in bayes.FittedGP([[0],[1]],[2,2]).predict([.5])))
        tiny=bayes.FittedGP([[0],[.5],[1]],[1e-15,3e-15,1e-15]);self.assertAlmostEqual(tiny.predict([.5])[0]/3e-15,1,places=4)

    def test_exact_hypervolume_one_two_three_dimensions(self):
        self.assertAlmostEqual(bayes.hypervolume([[1],[2]],[4]),3)
        self.assertAlmostEqual(bayes.hypervolume([[1,2],[2,1],[2,2]],[3,3]),3)
        self.assertAlmostEqual(bayes.hypervolume([[1,2,1],[2,1,1]],[3,3,3]),6)
        self.assertAlmostEqual(bayes.hypervolume([(1,2,1),[2,1,1]],[3,3,3]),6)

    def test_three_objective_proposals_with_parallel_pending_coordinate(self):
        coords=[[i,i%3] for i in range(8)];m={'adaptive':{'coordinates':coords+[[8,2]],'batches':3}}
        report={'candidates':[dict(candidate=i+1,complete=1,total=1,state='Passed',pareto=True,evidence_errors=[],metrics=[dict(score=v) for v in (i/8,1-i/8,(i%3)/3)],constraints={'safety':-.1}) for i in range(8)]}
        point=bayes.propose(m,report,[list(range(10)),list(range(3))])
        self.assertNotIn(point,m['adaptive']['coordinates']);self.assertEqual(len(m['adaptive']['proposal_evidence']['score_means']),3)

    def test_constrained_search_reproducible_excludes_solver_failures(self):
        p=mos_project();p['cells'][0]['specifications']=[dict(name='Bias',expression='final(V("g"))',min='.7',unit='V')]
        spec=search_spec(strategy='bayesian');spec['axes'][0]['count']=21;spec['budget']=7
        m=opt.prepare(p,p['top'],opt.source_plan(setup(p)),spec,prepare_job);rows=completed(m)
        a,jobs=adaptive.advance(m,rows,prepare_job);b,_=adaptive.advance(m,rows,prepare_job)
        self.assertEqual(a['adaptive']['coordinates'],b['adaptive']['coordinates']);self.assertIn('proposal',jobs[0]['case'])
        self.assertIn('Model estimates only',jobs[0]['case']['proposal']['note'])
        self.assertEqual(opt.evaluate(a,rows)['candidates'][-1]['state'],'Pending')
        rows[0]['state']='Failed';report=opt.evaluate(m,rows)
        self.assertIsNone(bayes.propose(clone(m),report,adaptive.axes(p,p['top'],spec)))


class RobustnessTests(unittest.TestCase):
    def setUp(self):
        self.p=mos_project();self.plan=opt.source_plan(setup(self.p));self.spec=search_spec()
        self.p['cells'][0]['specifications']=[dict(name='Gate',expression='final(V("g"))',min='.7',max='.9',unit='V')]

    def test_correlated_normal_loadings_and_reproducibility(self):
        variables=[dict(target=t,absolute_sigma=.01,group='shared',rho=1) for t in ('VG.value','VD.value')]
        a=robust.draw(self.p,self.p['top'],self.plan,variables,100,22,'tolerance');b=robust.draw(self.p,self.p['top'],self.plan,variables,100,22,'tolerance')
        self.assertEqual(a,b)
        for p in a:self.assertAlmostEqual(p['VG.value']-.8,p['VD.value']-1.8)
        variables[1]['rho']=-1;a=robust.draw(self.p,self.p['top'],self.plan,variables,100,22,'tolerance')
        for p in a:self.assertAlmostEqual(p['VG.value']-.8,-(p['VD.value']-1.8))

    def test_worst_conditions_refine_and_stay_within_bounds(self):
        variables=[dict(target='VG.value',lower=.5,upper=1.1)];m=robust.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job,variables,count=13)
        before=clone(self.p)
        while not m['advanced']['done']:m,_=robust.advance(m,completed(m),prepare_job)
        self.assertEqual(self.p,before);self.assertEqual(len(m['jobs']),13)
        self.assertTrue(all(.5<=j['case']['changes']['VG.value']<=1.1 for j in m['jobs']))
        self.assertTrue(all(j['case']['labels']['sample']==j['case']['candidate'] for j in m['jobs']))
        report=robust.analyze(m,completed(m));self.assertTrue(report['complete']);self.assertGreater(report['failed'],0);self.assertIsNone(report['pass_fraction'])

    def test_tolerance_intervals_unresolved_and_statistical_guard(self):
        variables=[dict(target='VG.value',absolute_sigma=.03)];m=robust.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job,variables,'tolerance',20,5)
        rows=completed(m);r=robust.analyze(m,rows);self.assertIsNotNone(r['confidence_95']);self.assertIn('not foundry',r['scope'])
        rows[0]['state']='Failed';r=robust.analyze(m,rows);self.assertEqual(r['unresolved'],1);self.assertIsNone(r['pass_fraction'])
        with self.assertRaisesRegex(ValueError,'validated statistical'):robust.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job,[],'statistical',20,5,'missing')
        self.assertAlmostEqual(robust.wilson(10,10)[0],.7224672,places=6)

    def test_uncertain_parameter_overrides_are_rejected(self):
        self.plan['entries'][0]['supply']='VG.value';self.plan['voltages']=[.8]
        with self.assertRaisesRegex(ValueError,'masks'):robust.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job,[dict(target='VG.value',lower=.6,upper=1)])


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.p=mos_project();self.p['cells'][0]['specifications']=[dict(name='Gate',expression='final(V("g"))',min='.7',unit='V')]
        self.plan=opt.source_plan(setup(self.p));self.plan['entries'] += [{**clone(self.plan['entries'][0]),'id':'tran','name':'Transient','settings':{**self.p['analysis'],'type':'tran','step':'1u','stop':'1u'}}]
        self.spec=search_spec();self.spec['workflow']=dict(stages=[dict(name='Bias',entries=['op']),dict(name='Transient',entries=['tran'])],retries=1,runtime_seconds=10,reuse=True)

    def test_stage_failure_skips_later_tests_solver_failure_blocks(self):
        m=opt.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job);ready=opt.ready_jobs(m,[])
        self.assertEqual(len(ready),3);rows=completed({**m,'jobs':ready});r=opt.evaluate(m,rows)
        self.assertEqual(r['skipped'],1);self.assertEqual(len(opt.ready_jobs(m,rows)),2)
        rows[0]['state']='Failed';r=opt.evaluate(m,rows);self.assertEqual(r['skipped'],0);self.assertEqual(len(automation.retries(m,rows)),1)
        repeat=clone(rows[0]);repeat['id']='retry';rows.append(repeat);self.assertFalse(automation.retries(m,rows))
        rows+=completed({**m,'jobs':opt.ready_jobs(m,rows)});self.assertTrue(automation.blocked(m,rows));self.assertFalse(opt.evaluate(m,rows)['complete'])

    def test_reserves_retries_validates_assignment_and_worker_budget(self):
        self.spec['budget']=11
        with self.assertRaisesRegex(ValueError,'12 simulations'):opt.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job)
        self.spec['budget']=100;m=opt.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job);rows=completed(m)
        for row in rows:row['elapsed']=2
        self.assertTrue(automation.exhausted(m,rows));self.assertEqual(automation.worker_seconds(m,rows),12)
        self.spec['workflow']['stages'][0]['entries'].append('tran')
        with self.assertRaisesRegex(ValueError,'exactly one'):opt.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job)

    def test_exact_cache_identity_and_saved_report(self):
        m=opt.prepare(self.p,self.p['top'],self.plan,self.spec,prepare_job);rows=completed(m);job=clone(m['jobs'][0]);job['case']['group']='different'
        self.assertIs(automation.reusable(job,rows),rows[0])
        changed=clone(job);changed['settings']['temperature']=80;self.assertIsNone(automation.reusable(changed,rows))
        bad=clone(rows);bad[0]['result']['design_hash']='wrong';self.assertIsNone(automation.reusable(job,bad))
        changed=clone(job);changed['environment']['workflow_hash']='obsolete'
        with self.assertRaisesRegex(ValueError,'changed'):automation.reusable(changed,rows)
        with tempfile.TemporaryDirectory() as d:
            path=automation.save_report(m,automation.report(m,rows),d);self.assertTrue(path.is_file());self.assertEqual(variation_load(d,m),[])


def variation_load(root,m):
    from icstudio.variation_runs import load
    return load(root,m['project_id'])


class DiagnosticMathTests(unittest.TestCase):
    def test_noise_integrates_power_and_keeps_overlapping_subtotals_explicit(self):
        report=diagnostic.noise_report(['frequency','onoise_spectrum','inoise_spectrum','onoise_r1','onoise_r1_thermal'],[[1,2,4,2,2],[101,2,4,2,2]])
        self.assertEqual(report['output_rms_V'],20);self.assertEqual(report['input_rms_V'],40);self.assertEqual(report['contributors'][0]['fraction_of_output'],1)
        self.assertTrue(any(r['subtotal'] for r in report['contributors']))

    def test_poles_units_and_unstable_half_plane(self):
        r=diagnostic.pole_zero_report(['v(pole(1))','v(zero(1))'],[[-2e6+0j,2e6+3e6j]])
        self.assertAlmostEqual(r['poles'][0]['frequency_Hz'],2e6/(2*math.pi));self.assertFalse(r['poles'][0]['right_half_plane']);self.assertTrue(r['zeros'][0]['right_half_plane'])

    def test_loop_crossings_and_missing_margin(self):
        r=dict(settings={'type':'ac'},x=[1,10,100,1000],traces={'r':[10,1,.1,.01],'i':[1]*4},phase={'r':[-80,-120,-170,150],'i':[0]*4})
        d=diagnostic.loop_report(r,'r','i');self.assertEqual(len(d['unity_crossings']),1);self.assertAlmostEqual(d['unity_crossings'][0]['phase_margin_deg'],60)
        self.assertAlmostEqual(d['negative_real_crossings'][0]['gain_margin_dB'],25)
        r['traces']['r']=[.1]*4;self.assertEqual(diagnostic.loop_report(r,'r','i')['unity_crossings'],[])
        r['traces']['i'][0]=0
        with self.assertRaisesRegex(ValueError,'zero magnitude'):diagnostic.loop_report(r,'r','i')

    def test_startup_tail_and_bias_unknown_regions(self):
        r=dict(x=[0,1,2,3,4],traces={'out':[0,.8,1,1,1]});c=dict(output='out',minimum=.9,maximum=1.1,tail_fraction=.5,ramp=1)
        d=diagnostic.startup_report(r,c);self.assertTrue(d['passed']);self.assertEqual(d['settled_by_s'],2)
        r['traces']['out'][-1]=.2;self.assertFalse(diagnostic.startup_report(r,c)['passed'])
        d=diagnostic.bias_report(dict(device_operating_point={'M1':dict(id=1e-5,gm=1e-4,vds=.3,vdsat=.4)}))['devices'][0]
        self.assertIsNone(d['region']);self.assertEqual(d['bias_status'],'Below model VDSAT');self.assertAlmostEqual(d['gm_Id_per_V'],10)

    def test_startup_finds_ngspice_vectors_without_changing_net_spelling(self):
        result=dict(x=[0,1,2,3,4],traces={'vref':[0,.5,.6,.6,.6]})
        config=dict(output='VREF',minimum=.594,maximum=.606,tail_fraction=.5,ramp=1)
        before=clone(result);saved_config=clone(config)
        report=diagnostic.startup_report(result,config)
        self.assertTrue(report['passed']);self.assertEqual(report['settled_by_s'],2)
        self.assertEqual(result,before);self.assertEqual(config,saved_config)
        result['traces']={'VrEf':result['traces']['vref']}
        self.assertEqual(diagnostic.startup_report(result,config),report)
        config['output']='unconnected'
        with self.assertRaisesRegex(ValueError,'not captured'):diagnostic.startup_report(result,config)

    def test_diagnostic_deck_edits_only_connected_top_level_source(self):
        p=rc_project();c=dict(kind='startup',source='V1',output='out',initial_node='out',minimum=0,maximum=1,supply=1,ramp='1u',stop='10u',initial_voltage='.2')
        text='test\nV1 in 0 DC 1\n.subckt fixture a\nV1 a 0 1\n.ends\n.tran 1n 10u\n.end\n'
        deck=diagnostic.alter_deck(p,p['top'],dict(diagnostic=c),text)
        self.assertIn('V1 a 0 1',deck);self.assertIn('PWL(0 0',deck);self.assertIn('uic',deck);self.assertIn('.ic v(out)=0.2',deck)
        c['initial_node']='out)\n.shell bad'
        with self.assertRaises(ValueError):diagnostic.alter_deck(p,p['top'],dict(diagnostic=c),text)


class FidelityTests(unittest.TestCase):
    def test_full_resolution_promotions_preserve_snapshot_and_budget(self):
        p=rc_project();p['analysis'].update(type='ac',start='10',end='10Meg',points=40)
        entry={**setup(p),'engine':'ngspice'};plan=opt.source_plan(entry);spec=search_spec();spec['axes']=[dict(target='R1.value',lower=500,upper=1500,count=11)];spec['objective'].update(expression='final(abs(V("out")))',goal='maximize');spec['budget']=10
        def measured(m):
            rows=completed(m)
            # Construction/progression unit fixture. Real engine qualification
            # is separate and never patches engine identity in production.
            for row in rows:row['result']['engine_hash']='test'
            return rows
        with patch('icstudio.run_environment.stamp',return_value=dict(engine='ngspice',executable_sha256='test')):
            m=fidelity.prepare(p,p['top'],plan,spec,prepare_job,pool=6,finalists=4)
            rows=measured(m);self.assertEqual(len(m['jobs']),9)
            self.assertFalse(fidelity.analyze(m,rows)['complete'])
            with self.assertRaises(ValueError):fidelity.apply_candidate(clone(p),m,rows,1)
            m,jobs=fidelity.advance(m,rows,prepare_job);self.assertEqual(len(jobs),1);self.assertEqual(len(m['jobs']),10)
            self.assertEqual(jobs[0]['settings']['points'],40);self.assertEqual(jobs[0]['case']['fidelity']['level'],'full')
            self.assertTrue(fidelity.analyze(m,measured(m))['complete']);self.assertTrue(m['advanced']['predictions'])
            self.assertEqual(p['cells'][0]['devices'][1]['value'],'1k')
            passing=fidelity.analyze(m,measured(m))['full_candidates'][0]['candidate'];q=clone(p);fidelity.apply_candidate(q,m,measured(m),passing)
            self.assertEqual(q['analysis'],p['analysis'])
            spec['budget']=9
            with self.assertRaisesRegex(ValueError,'reserves 10'):fidelity.prepare(p,p['top'],plan,spec,prepare_job,pool=6,finalists=4)


@unittest.skipUnless(os.environ.get('ICSTUDIO_TEST_NGSPICE'),'Set ICSTUDIO_TEST_NGSPICE for real diagnostic workers')
class RealSpiceDiagnosticTests(unittest.TestCase):
    def test_real_noise_poles_startup_and_saved_identity(self):
        from icstudio.engines import run_ngspice
        executable=os.environ['ICSTUDIO_TEST_NGSPICE'];p=rc_project();plan=opt.source_plan({**setup(p),'engine':'ngspice'})
        def prepare(s,e,p,cid):return {**prepare_job(s,e,p,cid),'executable':executable}
        configs=[dict(kind='noise',output='out',source='V1',start='10',end='1Meg',points=20),dict(kind='pole_zero',input='in',input_return='0',output='out',output_return='0'),
            dict(kind='startup',output='out',source='V1',supply=1,ramp='1u',stop='10u',step='10n',initial_node='out',initial_voltage=0,minimum=.49,maximum=.51)]
        for config in configs:
            with self.subTest(kind=config['kind']),tempfile.TemporaryDirectory() as d:
                m=diagnostic.prepare(p,p['top'],plan,prepare,config);j=m['jobs'][0];r=run_ngspice(j['project'],j['cell'],j['settings'],executable,Path(d));e=r['diagnostics']
                report=diagnostic.analyze(m,[dict(id='real',state='Complete',job=j,result=r)]);self.assertEqual(report['rows'][0]['state'],'Complete')
                if config['kind']=='pole_zero':self.assertAlmostEqual(e['poles'][0]['real_rad_s']/-2e6,1,places=5)
                elif config['kind']=='startup':self.assertTrue(e['passed']);self.assertAlmostEqual(e['final_V'],.5,places=4)
                else:
                    self.assertGreater(len(e['contributors']),1);self.assertGreater(e['output_rms_V'],0);self.assertGreater(e['input_rms_V']/e['output_rms_V'],2)


if __name__=='__main__':unittest.main()
