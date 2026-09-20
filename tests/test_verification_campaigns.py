import csv
import itertools
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from icstudio.model import clone, example, file_digest
from icstudio.test_plans import case_count, iter_prepare, prepare, sources, validate_plans
from icstudio.verification_campaigns import Campaign, create, run, main, locking_probe


def fixture(count=3):
    project=example('rc');cell=project['cells'][0]
    cell['specifications']=[dict(name='Output',expression='final(V("vout"))',min='0',max='2',unit='V')]
    project['simulation_setups']=[dict(name='Operating point',cell=cell['id'],engine='builtin',settings={**clone(project['analysis']),'type':'op'})]
    plan=dict(id='verification',name='Verification',entries=sources(project),corners=['nominal'],
              temperatures=list(range(count)),voltages=[])
    return project,plan


def prepare_job(settings,engine,project,cell):
    return dict(settings=clone(settings),engine=engine,project=clone(project),cell=cell)


class VerificationCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def campaign(self,count=3):
        p,plan=fixture(count)
        return create(self.root/('campaign-'+str(count)),p,plan,prepare_job)

    def test_large_plan_is_lazy_and_interactive_memory_stays_bounded(self):
        p,plan=fixture(10000);validate_plans({**p,'test_plans':[plan]})
        prepared=[]
        def capture(*args):prepared.append(1);return prepare_job(*args)
        jobs=iter_prepare(p,plan,capture)
        self.assertEqual(prepared,[])
        first=list(itertools.islice(jobs,2))
        self.assertEqual(len(prepared),2);self.assertEqual([j['case']['index'] for j in first],[1,2])
        self.assertEqual(case_count(plan),10000)
        with self.assertRaisesRegex(ValueError,'resumable campaign'):prepare(p,plan,capture)
        plan['temperatures'].append(10000)
        with self.assertRaisesRegex(ValueError,'10,000'):validate_plans({**p,'test_plans':[plan]})

    def test_rtl_case_count_does_not_multiply_by_analog_conditions(self):
        self.assertEqual(case_count(dict(entries=[{'engine':'digital'},{'engine':'builtin'}],
            corners=['a','b'],temperatures=[0,27],voltages=[1,2])),9)

    def test_thousand_case_capture_pages_without_loading_waveforms(self):
        campaign=self.campaign(1001)
        self.assertEqual(campaign.counts()['total'],1001)
        page=campaign.page(900)
        self.assertEqual(len(page),100);self.assertEqual(page[0]['case_index'],901)
        self.assertEqual(len(campaign.page(1000)),1)
        self.assertNotIn('project',page[0]);self.assertNotIn('result',page[0])
        with self.assertRaisesRegex(ValueError,'1–100'):campaign.page(limit=101)
        self.assertEqual(Campaign(campaign.path).job(1001)['case']['labels']['temperature'],1000)

    def test_parallel_claims_are_unique_and_expired_worker_cannot_publish(self):
        campaign=self.campaign(12);locking_probe(campaign.path)
        with ThreadPoolExecutor(max_workers=6) as pool:claims=list(pool.map(lambda i:campaign.claim('worker-'+str(i)),range(12)))
        self.assertEqual(len({c['case_index'] for c in claims}),12)
        old=claims[0]
        with campaign.connect() as db:db.execute('UPDATE cases SET lease_until=0 WHERE case_index=?',(old['case_index'],))
        new=campaign.claim('replacement')
        self.assertEqual(new['case_index'],old['case_index']);self.assertNotEqual(new['token'],old['token'])
        self.assertFalse(campaign.finish(old['case_index'],old['token'],'Complete'))
        self.assertTrue(campaign.finish(new['case_index'],new['token'],'Failed',error='exact diagnostic'))
        self.assertEqual(campaign.counts()['Failed'],1)
        campaign.resume(retry_failed=True)
        third=campaign.claim('third');self.assertEqual(third['attempts'],3)

    def test_pause_reopen_resume_retains_inputs_and_stops_claims(self):
        campaign=self.campaign();claim=campaign.claim('worker');before=campaign.job(1)
        campaign.pause();self.assertIsNone(campaign.claim('second'))
        self.assertFalse(campaign.heartbeat(claim['case_index'],claim['token']))
        campaign.finish(claim['case_index'],claim['token'],'Interrupted',error='paused')
        reopened=Campaign(campaign.path);reopened.resume()
        again=reopened.claim('resumed');self.assertEqual(again['case_index'],1)
        self.assertEqual(before,reopened.job(1));self.assertEqual(again['attempts'],2)

    def test_tampered_inputs_and_manifest_are_rejected(self):
        campaign=self.campaign();path=campaign.path/'cases/00001/input.json'
        data=json.loads(path.read_text());data['settings']['temperature']=999;path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'input changed'):campaign.job(1)
        path=campaign.path/'manifest.json';manifest=json.loads(path.read_text());manifest['name']='changed';path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'manifest changed'):Campaign(campaign.path)

    def test_locked_model_assets_are_copied_once_and_do_not_follow_source_edits(self):
        p,plan=fixture(2);models=self.root/'models';models.mkdir();model=models/'model.spice';model.write_text('* locked model\n')
        p['pdk'].update(package_root=str(models),package_lock={'id':'test','revision':'1','files':{'model.spice':file_digest(model)}},
                        simulation={'includes':[{'path':'model.spice'}]})
        campaign=create(self.root/'models-campaign',p,plan,prepare_job)
        model.write_text('* changed original\n')
        job=campaign.job(1);saved=Path(job['project']['pdk']['package_root'])/'model.spice'
        self.assertEqual(saved.read_text(),'* locked model\n')
        self.assertEqual(job['campaign_provenance']['models']['files']['model.spice'],file_digest(saved))
        self.assertEqual(len(list((campaign.path/'assets').rglob('model.spice'))),1)
        saved.write_text('* changed snapshot\n')
        counts=run(campaign.path,workers=1,trusted=True)
        self.assertEqual(counts['Failed'],2)
        self.assertIn('Locked PDK asset',campaign.page()[0]['error'])

    def test_creation_failure_leaves_no_partially_published_campaign(self):
        p,plan=fixture();attempts=[]
        def fail(*args):
            attempts.append(1)
            if len(attempts)==2:raise ValueError('Invalid second case')
            return prepare_job(*args)
        with self.assertRaisesRegex(ValueError,'second case'):create(self.root/'partial',p,plan,fail)
        self.assertFalse((self.root/'partial').exists());self.assertEqual(list(self.root.iterdir()),[])

    def test_real_worker_results_survive_reopen_and_resume_does_not_rerun_complete(self):
        campaign=self.campaign(2)
        with self.assertRaisesRegex(ValueError,'trust-project'):run(campaign.path)
        counts=run(campaign.path,workers=2,trusted=True)
        self.assertEqual(counts.get('Complete'),2, campaign.page());self.assertEqual(counts['specification_failures'],0)
        reopened=Campaign(campaign.path);row=reopened.row(1)
        self.assertTrue(row['result']['traces']);self.assertEqual(row['job']['case']['group'],campaign.manifest['id'])
        again=run(campaign.path,workers=1,trusted=True);self.assertEqual(again['Complete'],2)
        self.assertEqual([r['attempts'] for r in reopened.page()],[1,1])
        report=self.root/'summary.csv';campaign.export(report)
        with report.open() as stream:rows=list(csv.DictReader(stream))
        self.assertEqual(len(rows),2);self.assertTrue(rows[0]['result_directory'])
        result_path=row['path']/'result.json';data=json.loads(result_path.read_text());data['traces']['vout'][0]=999
        result_path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'result changed'):reopened.row(1)

    def test_source_change_during_execution_prevents_completion_publication(self):
        campaign=self.campaign(1);identity=campaign.manifest['source']
        with patch('icstudio.verification_campaigns.source_identity',side_effect=[identity,identity,{'changed':True}]):
            counts=run(campaign.path,workers=1,trusted=True)
        self.assertEqual(counts['Failed'],1)
        self.assertIn('source changed',campaign.page()[0]['error'])

    def test_cli_fails_electrical_specifications_and_retains_diagnostics(self):
        p,plan=fixture(1);p['cells'][0]['specifications'][0]['max']='-1';p['cells'][0]['specifications'][0]['min']='-2'
        campaign=create(self.root/'failed-spec',p,plan,prepare_job)
        self.assertEqual(main(['run',str(campaign.path),'--workers','1','--trust-project']),2)
        self.assertEqual(campaign.counts()['specification_failures'],1)
        self.assertEqual(campaign.page(failures_only=True)[0]['state'],'Complete')
        self.assertEqual(json.loads(campaign.page()[0]['summary'])['requirements'][0]['status'],'FAIL')
        campaign.resume(retry_failed=True);self.assertEqual(campaign.counts()['Queued'],1)

    def test_stop_interrupts_running_case_and_original_input_can_resume(self):
        campaign=self.campaign(5);stop=threading.Event();out=[]
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(run,campaign.path,1,3600,stop,True)
            deadline=time.monotonic()+10
            while not campaign.counts().get('Running') and time.monotonic()<deadline:time.sleep(.02)
            stop.set();out.append(future.result(timeout=10))
        self.assertGreater(out[0].get('Interrupted',0)+out[0].get('Queued',0),0)
        self.assertEqual(run(campaign.path,2,trusted=True)['Complete'],5)


if __name__=='__main__':unittest.main()
