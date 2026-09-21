"""Offscreen campaign lifecycle and bounded table smoke tests."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import time
import unittest
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication,QWidget,QLabel,QDialog
from icstudio.model import clone
from icstudio.run_manager import RunManager
from icstudio.test_plans import prepare
from icstudio.test_plan_ui import TestPlanWindow
from icstudio.campaign_ui import CampaignWindow,prepare_campaign
from icstudio.verification_campaigns import create
from tests.test_verification_campaigns import fixture,prepare_job


class StudioFixture(QWidget):
    def __init__(self,project):
        super().__init__();self.project=project;self.dark=False;self.run_manager=RunManager(self)
    def prepare_simulation(self,settings,engine='builtin',project=None,cid=None):
        return prepare_job(settings,engine,project or self.project,cid or self.project['top'])
    def flush_inspector(self):return True


class CampaignGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.windows=[]
        self.addCleanup(self.close_windows)

    def close_windows(self):
        for window in self.windows:
            if isinstance(window,CampaignWindow):window.shutdown()
            window.close();window.deleteLater()
        self.app.processEvents()

    def until(self,condition,timeout=20):
        deadline=time.monotonic()+timeout
        while not condition() and time.monotonic()<deadline:
            self.app.processEvents();time.sleep(.01)
        self.app.processEvents();self.assertTrue(condition(),'Timed out waiting for GUI campaign state')

    def test_interactive_matrix_pages_conditions_without_losing_export_data(self):
        p,plan=fixture(85);p['test_plans']=[plan];studio=StudioFixture(p);self.windows.append(studio)
        jobs=prepare(p,plan,prepare_job)
        studio.run_manager.rows=[dict(id=str(i),job=job,state='Queued',log='') for i,job in enumerate(jobs)]
        window=TestPlanWindow(studio);self.windows.insert(0,window)
        self.assertEqual(window.table.columnCount(),42);self.assertEqual(len(window.data['conditions']),85)
        window.move_conditions(1);self.assertIn('41–80',window.condition_label.text())
        window.move_conditions(1);self.assertEqual(window.table.columnCount(),7)
        self.assertFalse(window.next_conditions.isEnabled());self.assertTrue(window.previous_conditions.isEnabled())

    def test_background_capture_uses_saved_revision_and_results_are_paged(self):
        p,plan=fixture(105);studio=StudioFixture(p);self.windows.append(studio);note=QLabel(studio)
        original=clone(p)
        capture=prepare_campaign(studio,plan,self.root/'background',note)
        studio.project['name']='Edited during capture'
        self.until(lambda:not capture.isRunning() and bool(getattr(studio,'_campaign_windows',[])))
        window=studio._campaign_windows[0];self.windows.insert(0,window)
        self.assertEqual(window.campaign.job(1)['project']['name'],original['name'])
        self.assertEqual(studio.project['name'],'Edited during capture')
        self.assertEqual(window.table.rowCount(),100);window.move(1);self.assertEqual(window.table.rowCount(),5)
        window.close();self.assertFalse(window.campaign.counts()['paused'],'Closing an inspector must not pause other workers')

    def test_worker_pause_reopen_resume_preserves_project_and_waveforms(self):
        p,plan=fixture(5);studio=StudioFixture(p);self.windows.append(studio)
        campaign=create(self.root/'lifecycle',p,plan,prepare_job)
        window=CampaignWindow(studio,campaign.path);self.windows.insert(0,window);window.show();window.workers.setValue(1)
        window.run();self.until(lambda:bool(campaign.counts().get('Running')))
        studio.project['name']='Current unsaved work';window.close()
        self.until(lambda:window.process.state()==QProcess.NotRunning)
        self.assertTrue(campaign.counts()['paused'])
        reopened=CampaignWindow(studio,campaign.path);self.windows.insert(0,reopened);reopened.show();reopened.run()
        self.until(lambda:reopened.process.state()==QProcess.NotRunning,30)
        self.assertEqual(campaign.counts().get('Complete'),5,campaign.page())
        reopened.refresh();reopened.table.selectRow(0);reopened.open_case()
        self.windows.insert(0,reopened.inspector)
        self.assertTrue(reopened.inspector.result['traces'])
        self.assertEqual(studio.project['name'],'Current unsaved work')
        self.assertNotEqual(reopened.inspector.project['name'],studio.project['name'])

    def test_statistical_editor_save_reopen_trial_matrix_and_yield(self):
        from tests.test_campaign_statistics import statistical_fixture
        from icstudio.campaign_statistics_ui import StatisticsEditor,StatisticsReport
        from icstudio.test_plan_ui import PlanEditor
        from icstudio.verification_campaigns import run
        p,plan=statistical_fixture(4);p['test_plans']=[plan]
        studio=StudioFixture(p);studio.commit=lambda edit,title:edit(studio.project);self.windows.append(studio)
        window=TestPlanWindow(studio);self.windows.insert(0,window)
        distribution=StatisticsEditor(window,p,plan,plan['statistics']);self.windows.insert(0,distribution)
        distribution.count.setValue(6);distribution.seed.setText('31415');distribution.save()
        self.assertEqual(distribution.result(),QDialog.Accepted)
        editor=PlanEditor(window,plan);self.windows.insert(0,editor);editor.statistics_config=distribution.value;editor.save()
        self.assertEqual(editor.result(),QDialog.Accepted,editor.error.text())
        saved=p['test_plans'][0];reopened=PlanEditor(window,saved);self.windows.insert(0,reopened)
        self.assertEqual(reopened.statistics_config['count'],6);self.assertEqual(reopened.statistics_config['seed'],31415)
        jobs=prepare(p,saved,prepare_job)
        studio.run_manager.rows=[dict(id=str(i),job=j,state='Queued',log='') for i,j in enumerate(jobs)]
        window.refresh();self.assertEqual(len(window.data['conditions']),12)
        self.assertIn('trial 1 / seed 31415',window.table.horizontalHeaderItem(2).text())
        campaign=create(self.root/'statistical-editor',p,saved,prepare_job)
        report=StatisticsReport(window,campaign);self.windows.insert(0,report)
        self.assertEqual(report.table.item(0,4).text(),'6');self.assertEqual(report.table.item(0,6).text(),'Unresolved')
        counts=run(campaign.path,workers=2,trusted=True)
        self.assertEqual(counts.get('Complete'),12,campaign.page())
        report.refresh();self.assertEqual(report.table.item(0,1).text(),'6')
        self.assertEqual(report.table.item(0,4).text(),'0');self.assertEqual(report.table.item(0,5).text(),'100.00%')
        self.assertIn('–',report.table.item(0,6).text());self.assertEqual(report.table.rowCount(),3)

    def test_small_statistical_plan_keeps_invalid_trials_through_interactive_workers(self):
        from tests.test_campaign_statistics import statistical_fixture
        from icstudio.model import validate
        from icstudio.campaign_statistics import report
        from icstudio.verification_campaigns import _summary
        p,plan=statistical_fixture(4)
        plan['statistics'].update(kind='correlated',variations=[dict(target='R1.value',absolute_sigma=1e6)])
        p['test_plans']=[plan];original=clone(p)
        studio=StudioFixture(p);studio.jobs_dir=self.root/'interactive';self.windows.append(studio)
        def validating_prepare(settings,engine,project,cid):
            validate(project)
            return prepare_job(settings,engine,project,cid)
        studio.prepare_simulation=validating_prepare
        window=TestPlanWindow(studio);self.windows.insert(0,window)
        window.run();self.assertEqual(len(studio.run_manager.rows),8)
        self.until(lambda:not studio.run_manager.busy,30)
        rows=studio.run_manager.rows;failed=[row for row in rows if row['state']=='Failed']
        self.assertEqual(len(failed),2,[row['log'] for row in rows])
        self.assertEqual(sum(row['state']=='Complete' for row in rows),6)
        for row in failed:
            self.assertEqual(row['job']['case']['labels']['trial'],4)
            self.assertEqual(row['job']['case']['labels']['seed'],72)
            self.assertLess(row['job']['case']['statistics']['changes']['R1.value'],0)
            self.assertIn('not clipped or resampled',row['log'])
            self.assertFalse((row['path']/'result.json').exists())
        result=report(plan,[dict(entry_id=row['job']['case']['entry_id'],labels=row['job']['case']['labels'],state=row['state'],
                                summary=_summary(row['job'],row.get('result',{}))) for row in rows])
        self.assertEqual(result['joint']['unresolved'],1)
        self.assertIsNone(result['joint']['confidence_95'])
        self.assertEqual(p,original)


if __name__=='__main__':unittest.main()
