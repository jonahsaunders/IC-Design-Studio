import json
import math
from pathlib import Path
import statistics
import tempfile
import unittest
from icstudio.model import clone,device,validate
from icstudio.test_plans import iter_prepare,case_count,matrix,validate_plans
from icstudio.campaign_statistics import configuration,samples,report
from icstudio.verification_campaigns import create,run
from tests.test_verification_campaigns import fixture,prepare_job


def statistical_fixture(count=8):
    project,plan=fixture(2)
    project['cells'][0]['devices'].append(device('R','R2',value='10k',nets={'p':'vout','n':'0'}))
    plan['statistics']=dict(kind='monte_carlo',cell=project['top'],count=count,seed=72,
                            variations=[dict(target='R1.value',relative_sigma=.05,distribution='normal')])
    return project,plan


class CampaignStatisticsTests(unittest.TestCase):
    def test_independent_samples_match_existing_monte_carlo_exactly(self):
        from icstudio.studies import cases
        p,plan=statistical_fixture();spec=configuration(p,plan)
        expected=cases(p,p['top'],plan['statistics'])
        actual=list(samples(p,plan,spec))
        self.assertEqual([changes for _,changes in actual],[changes for _,changes,_ in expected])
        jobs=list(iter_prepare(p,plan,prepare_job));self.assertEqual(len(jobs),16)
        self.assertEqual(case_count(plan),16)
        for trial in range(8):
            pair=jobs[trial*2:trial*2+2]
            self.assertEqual(pair[0]['case']['statistics']['changes'],pair[1]['case']['statistics']['changes'])
            self.assertEqual([j['case']['labels']['trial'] for j in pair],[trial+1]*2)
        m=matrix([dict(id=str(i),job=j,state='Queued') for i,j in enumerate(jobs)],jobs[0]['case']['group'])
        self.assertEqual(len(m['conditions']),16,'Trials at the same PVT must not overwrite each other')

    def test_correlated_draws_preserve_existing_sequence_and_loading_semantics(self):
        from icstudio.analog_robustness import draw
        p,plan=statistical_fixture(4000)
        rows=[dict(target='R1.value',absolute_sigma=10,group='matched',rho=.8),dict(target='R2.value',absolute_sigma=10,group='matched',rho=-.5)]
        plan['statistics'].update(kind='correlated',variations=rows)
        actual=[changes for _,changes in samples(p,plan)]
        self.assertEqual(actual,draw(p,p['top'],plan,rows,4000,72,'tolerance'))
        self.assertAlmostEqual(statistics.correlation([p['R1.value'] for p in actual],[p['R2.value'] for p in actual]),-.4,delta=.035)
        self.assertAlmostEqual(statistics.stdev(p['R1.value'] for p in actual),10,delta=.3)
        rows[0]['rho']=rows[1]['rho']=1
        actual=list(samples(p,plan))
        self.assertTrue(all(changes['R1.value']==changes['R2.value'] for _,changes in actual))

    def test_model_mismatch_requires_evidence_and_preserves_declared_mapping(self):
        p,plan=statistical_fixture();plan['statistics'].update(kind='model_mismatch',model='declared')
        with self.assertRaisesRegex(ValueError,'validated PDK'):configuration(p,plan)
        p['pdk']['statistical_models']={'declared':dict(validated=True,evidence={'qualification':'unit fixture only'},variations=clone(plan['statistics']['variations']))}
        captured=list(iter_prepare(p,plan,prepare_job))
        self.assertEqual(captured[0]['case']['statistics']['model_evidence'],p['pdk']['statistical_models']['declared'])
        p['pdk']['statistical_models']['declared']['variations'][0]['relative_sigma']=.99
        self.assertEqual(captured[0]['case']['statistics']['model_evidence']['variations'][0]['relative_sigma'],.05)

    def test_invalid_mappings_seeds_and_masked_pvt_are_rejected(self):
        p,plan=statistical_fixture()
        plan['statistics']['seed']=True
        with self.assertRaisesRegex(ValueError,'integer sampling seed'):validate_plans({**p,'test_plans':[plan]})
        plan['statistics']['seed']=3;plan['statistics']['variations']=[dict(target='V1.value',relative_sigma=.05)]
        p['cells'][0]['devices'][0]['source']['type']='dc'
        plan['entries'][0]['supply']='V1.value';plan['voltages']=[1.8]
        with self.assertRaisesRegex(ValueError,'masks the statistical'):list(iter_prepare(p,plan,prepare_job))

    def test_yield_uses_trials_not_cases_and_unresolved_is_not_a_circuit_failure(self):
        _,plan=statistical_fixture(4)
        def row(trial,temp,outcome='PASS',state='Complete'):
            return dict(entry_id=plan['entries'][0]['id'],labels={'corner':'nominal','temperature':temp,'voltage':None,'trial':trial,'seed':plan['statistics']['seed']},state=state,
                        summary={'requirements':[{'status':outcome}]})
        rows=[row(trial,temp,'FAIL' if trial==1 and temp==1 else 'PASS') for trial in range(1,5) for temp in (0,1)]
        result=report(plan,rows)
        self.assertEqual(result['joint']['trials'],4);self.assertEqual(result['joint']['pass_fraction'],.75)
        self.assertEqual([r['pass_fraction'] for r in result['pvt']],[1,.75])
        self.assertAlmostEqual(result['joint']['confidence_95'][0],.30064184,places=6)
        wrong_seed=clone(rows);wrong_seed[0]['labels']['seed']=0
        self.assertEqual(report(plan,wrong_seed)['joint']['unresolved'],1)
        rows[-1]['state']='Failed';result=report(plan,rows)
        self.assertEqual(result['joint']['unresolved'],1);self.assertEqual(result['joint']['failed'],1)
        self.assertIsNone(result['joint']['pass_fraction']);self.assertIsNone(result['joint']['confidence_95'])
        self.assertEqual(result['joint']['unresolved_bounds'],[.5,.75])
        rows[-1]['state']='Complete';rows[-1]['summary']['requirements'][0]['status']='ERROR'
        self.assertEqual(report(plan,rows)['joint']['unresolved'],1)

    def test_expired_trial_resume_preserves_values_seeds_and_statistical_outcomes(self):
        p,plan=statistical_fixture(4)
        with tempfile.TemporaryDirectory() as directory:
            campaign=create(Path(directory)/'statistics',p,plan,prepare_job)
            claim=campaign.claim('crashed',5);original=campaign.job(claim['case_index'])
            with campaign.connect() as db:db.execute('UPDATE cases SET lease_until=0 WHERE case_index=?',(claim['case_index'],))
            self.assertEqual(campaign.statistics()['joint']['unresolved'],4)
            counts=run(campaign.path,workers=2,trusted=True,lease_seconds=5)
            self.assertEqual(counts.get('Complete'),8,campaign.page())
            saved=campaign.job(claim['case_index']);self.assertEqual(saved,original)
            self.assertEqual(saved['campaign_provenance']['seeds']['/case/statistics/seed'],72)
            self.assertEqual(campaign.page()[0]['attempts'],2)
            self.assertEqual(campaign.statistics()['joint']['unresolved'],0)
            self.assertIsNotNone(campaign.statistics()['joint']['confidence_95'])
            self.assertFalse(campaign.finish(claim['case_index'],claim['token'],'Complete'))

    def test_invalid_draw_is_retained_as_unresolved_instead_of_clipped_or_redrawn(self):
        p,plan=statistical_fixture(4)
        plan['statistics'].update(kind='correlated',variations=[dict(target='R1.value',absolute_sigma=1e6)])
        jobs=list(iter_prepare(p,plan,prepare_job));self.assertEqual(len(jobs),8)
        self.assertLess(jobs[-1]['case']['statistics']['changes']['R1.value'],0)
        self.assertIn('not clipped or resampled',jobs[-1]['preparation_error'])
        with tempfile.TemporaryDirectory() as directory:
            campaign=create(Path(directory)/'invalid-draw',p,plan,prepare_job)
            counts=run(campaign.path,workers=2,trusted=True)
            self.assertEqual(counts.get('Failed'),2,campaign.page())
            self.assertEqual(campaign.statistics()['joint']['unresolved'],1)
            self.assertIsNone(campaign.statistics()['joint']['confidence_95'])

    def test_saved_diagnostic_measurements_keep_physical_units(self):
        from icstudio.test_plans import requirements
        p,plan=statistical_fixture()
        p['testbenches']=[dict(id='diagnostics',bench_cell=p['top'],measurements=[
            dict(name=kind,kind=kind) for kind in ('phase_margin','unity_frequency','input_noise','output_noise','startup_settling')])]
        job=prepare_job({'type':'testbench','testbench':'diagnostics'},'ngspice',p,p['top'])
        units={row['name']:row['unit'] for row in requirements(job)}
        self.assertEqual({key:units[key] for key in ('phase_margin','unity_frequency','input_noise','output_noise','startup_settling')},
                         dict(phase_margin='deg',unity_frequency='Hz',input_noise='V',output_noise='V',startup_settling='s'))


if __name__=='__main__':unittest.main()
